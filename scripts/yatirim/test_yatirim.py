"""Yatirim sistemi testleri.

Calistirma:
    python -m unittest discover -s scripts/yatirim -v
    python scripts/yatirim/test_yatirim.py

Tamami CEVRIMDISI: sentetik veriyle calisir, Yahoo Finance'e gitmez.
Boylece test agdan ve piyasa saatlerinden bagimsiz, tekrarlanabilir kalir.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Ayarlar, Varlik, Yapilandirma, sablonu_reddet, yapilandirmayi_oku
from fetch import FiyatVerisi
from ledger import durumu_hesapla, islemleri_oku
from notify import _kacis, env_oku, ozet_mesaji
from portfolio import portfoyu_hesapla, portfoyu_ledgerdan_hesapla, sinif_sapmalari
from risk import (
    _max_drawdown,
    ortak_getiriler,
    riski_hesapla,
    yillik_periyot_sayisi,
)

AYARLAR = Ayarlar(kur_sembolu="USDTRY=X", gecmis_gun=365, islem_gunu_yil=252)


def gecici_yaz(icerik: str, ad: str = "test.yaml") -> Path:
    dosya = Path(tempfile.mkdtemp()) / ad
    dosya.write_text(icerik, encoding="utf-8")
    return dosya


def defter_durumu(islemler: str, nakit: float = 10000.0, komisyon: float = 0.0):
    icerik = (f"baslangic_nakit_try: {nakit}\nkomisyon_orani: {komisyon}\n"
              f"islemler:\n{islemler}")
    return durumu_hesapla(*islemleri_oku(gecici_yaz(icerik)))


class LedgerTesti(unittest.TestCase):
    """Islem defteri: agirlikli ortalama maliyet ve gerceklesen kar."""

    def test_kismi_satis_agirlikli_ortalama_maliyet(self):
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-02, yon: AL,  sembol: X, adet: 10, fiyat_try: 200}\n"
            "  - {tarih: 2026-01-03, yon: SAT, sembol: X, adet: 5,  fiyat_try: 300}\n"
        )
        pozisyon = durum.pozisyonlar["X"]
        self.assertAlmostEqual(pozisyon.adet, 15.0)
        self.assertAlmostEqual(pozisyon.maliyet_try, 2250.0)   # 15 x 150 ortalama
        self.assertAlmostEqual(durum.gerceklesen_kar_try, 750.0)  # 5 x (300-150)
        self.assertAlmostEqual(durum.nakit_try, 8500.0)

    def test_tam_satis_pozisyonu_kapatir(self):
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-02, yon: SAT, sembol: X, adet: 10, fiyat_try: 150}\n"
        )
        self.assertNotIn("X", durum.pozisyonlar)
        self.assertAlmostEqual(durum.gerceklesen_kar_try, 500.0)

    def test_komisyon_nakitten_duser_ve_kari_azaltir(self):
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-02, yon: SAT, sembol: X, adet: 10, fiyat_try: 100}\n",
            komisyon=0.001,
        )
        # Ayni fiyattan alip satmak: brut kar 0, komisyon kadar zarar.
        self.assertAlmostEqual(durum.toplam_komisyon_try, 2.0)
        self.assertAlmostEqual(durum.gerceklesen_kar_try, -1.0)  # satis komisyonu
        self.assertAlmostEqual(durum.nakit_try, 9998.0)

    def test_elde_olandan_fazla_satis_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "satilamaz"):
            defter_durumu(
                "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 5,  fiyat_try: 100}\n"
                "  - {tarih: 2026-01-02, yon: SAT, sembol: X, adet: 10, fiyat_try: 100}\n"
            )

    def test_nakit_yetersizligi_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "nakit yetersiz"):
            defter_durumu(
                "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 100, fiyat_try: 300}\n",
                nakit=1000.0,
            )

    def test_gecersiz_yon_ve_negatif_adet_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "AL veya SAT"):
            defter_durumu(
                "  - {tarih: 2026-01-01, yon: TUT, sembol: X, adet: 5, fiyat_try: 100}\n")
        with self.assertRaisesRegex(ValueError, "pozitif olmali"):
            defter_durumu(
                "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: -5, fiyat_try: 100}\n")


class CarpanTesti(unittest.TestCase):
    """carpan (ons -> gram) tam olarak BIR kez uygulanmali.

    Regresyon: ilk surumde hem fetch hem portfolio carpiyordu,
    altin degeri 31 kat dusuk cikiyordu.
    """

    def _altin_yapilandirmasi(self) -> Yapilandirma:
        return Yapilandirma(
            ayarlar=AYARLAR,
            hedef_dagilim={"maden": 1.0},
            varliklar={"GC=F": Varlik("GC=F", "Altin", "maden", "USD", carpan=0.1)},
            nakit_try=0.0,
            pozisyonlar=[],
        )

    def test_ledger_degerlemesinde_carpan_tekrar_uygulanmaz(self):
        # try_gecmis ZATEN carpan uygulanmis TL fiyat tasir: 100 USD * 0.1 * 40 = 400 TL
        gecmis = pd.DataFrame(
            {"GC=F": [400.0, 400.0]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL, sembol: 'GC=F', adet: 10, fiyat_try: 400}\n")
        portfoy = portfoyu_ledgerdan_hesapla(self._altin_yapilandirmasi(), fiyatlar, durum)
        # 10 gram x 400 TL = 4000 TL. Carpan ikinci kez uygulansaydi 400 TL cikardi.
        self.assertAlmostEqual(portfoy.pozisyon_degeri_try, 4000.0)


class SinifDagilimiTesti(unittest.TestCase):
    def test_nakit_agirliga_dahil_edilir(self):
        yapilandirma = Yapilandirma(
            ayarlar=AYARLAR,
            hedef_dagilim={"bist": 0.5, "nakit": 0.5},
            varliklar={"A.IS": Varlik("A.IS", "A", "bist", "TRY")},
            nakit_try=500.0,
            pozisyonlar=[],
        )
        gecmis = pd.DataFrame(
            {"A.IS": [100.0, 100.0]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL, sembol: A.IS, adet: 5, fiyat_try: 100}\n",
            nakit=1000.0)
        portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)

        self.assertAlmostEqual(portfoy.toplam_deger_try, 1000.0)  # 500 hisse + 500 nakit
        sapmalar = {s.sinif: s for s in sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)}
        self.assertAlmostEqual(sapmalar["bist"].guncel_agirlik, 0.5)
        self.assertAlmostEqual(sapmalar["nakit"].guncel_agirlik, 0.5)
        self.assertAlmostEqual(sapmalar["bist"].sapma, 0.0)


class TakvimHizalamaTesti(unittest.TestCase):
    """Regresyon: karisik islem takvimi volatiliteyi bozuyordu.

    BIST hafta sonu kapali, kripto acik.
      - ffill edilirse hafta sonu sifir getiri olur -> volatilite dusuk cikar
      - ffill edilmezse NaN sonrasi gun silinir -> her Pazartesi kaybolur
    Dogrusu: once ortak takvime hizala, sonra getiri al.
    """

    def _karisik_gecmis(self) -> pd.DataFrame:
        gunler = pd.date_range("2026-01-01", periods=10, freq="D")
        hisse = pd.Series(
            [100, 101, 102, np.nan, np.nan, 103, 104, 105, np.nan, np.nan],
            index=gunler, dtype=float)
        kripto = pd.Series(
            [200, 202, 204, 206, 208, 210, 212, 214, 216, 218],
            index=gunler, dtype=float)
        return pd.DataFrame({"HISSE.IS": hisse, "KRIPTO": kripto})

    def test_yalnizca_ortak_islem_gunleri_kalir(self):
        getiriler = ortak_getiriler(self._karisik_gecmis())
        # Hissenin gercekten islem gordugu 6 gun var -> 5 getiri.
        self.assertEqual(len(getiriler), 5)
        self.assertFalse(getiriler.isna().any().any())

    def test_hafta_sonu_bosluğu_sifir_getiri_uretmez(self):
        getiriler = ortak_getiriler(self._karisik_gecmis())
        self.assertFalse(
            (getiriler["HISSE.IS"] == 0).any(),
            "Kapali gun sifir getiri olarak sizmis - volatilite dusuk cikar",
        )

    def test_bosluk_sonrasi_getiri_tam_araligi_kapsar(self):
        getiriler = ortak_getiriler(self._karisik_gecmis())
        # 102 -> 103 (bosluktan sonra) tek getiri olarak gorunmeli.
        self.assertTrue(np.isclose(getiriler["HISSE.IS"], 103 / 102 - 1).any())
        # Kripto ayni satirda 204 -> 210 yapmali (hafta sonu hareketi dahil).
        self.assertTrue(np.isclose(getiriler["KRIPTO"], 210 / 204 - 1).any())

    def test_ortak_gun_yoksa_hata_verir(self):
        gunler = pd.date_range("2026-01-01", periods=4, freq="D")
        kesisimsiz = pd.DataFrame({
            "A": pd.Series([1.0, 2.0, np.nan, np.nan], index=gunler),
            "B": pd.Series([np.nan, np.nan, 3.0, 4.0], index=gunler),
        })
        with self.assertRaisesRegex(RuntimeError, "ortak islem gunu"):
            ortak_getiriler(kesisimsiz)


class YillicklastirmaTesti(unittest.TestCase):
    """Yillicklastirma carpani veriden turetilmeli, 252 varsayilmamali.

    Ortak islem takvimi kesisim oldugu icin yilda ~238 gozlem kalir;
    252 varsaymak volatiliteyi yaklasik %3 sisirir.
    """

    def test_carpan_gozlenen_yogunluktan_turetilir(self):
        # 240 is gunu, tam 1 yila yayilmis -> carpan ~240 olmali, 252 degil.
        gunler = pd.bdate_range("2025-01-01", periods=240)
        getiriler = pd.DataFrame({"A": np.zeros(240)}, index=gunler)
        carpan = yillik_periyot_sayisi(getiriler, varsayilan=252)
        self.assertGreater(carpan, 230)
        self.assertLess(carpan, 265)

    def test_seyrek_gozlem_dusuk_carpan_verir(self):
        # Haftada 1 gozlem -> yilda ~52 periyot.
        gunler = pd.date_range("2025-01-01", periods=52, freq="7D")
        getiriler = pd.DataFrame({"A": np.zeros(52)}, index=gunler)
        self.assertAlmostEqual(yillik_periyot_sayisi(getiriler, 252), 52.2, delta=2)

    def test_cok_kisa_pencerede_varsayilana_duser(self):
        tek = pd.DataFrame({"A": [0.0]}, index=pd.to_datetime(["2026-01-01"]))
        self.assertEqual(yillik_periyot_sayisi(tek, varsayilan=252), 252.0)


class BayatFiyatTesti(unittest.TestCase):
    """ffill eski fiyati sessizce tasir - bu gorunur olmali."""

    def _gecmis(self) -> pd.DataFrame:
        gunler = pd.date_range("2026-01-01", periods=30, freq="D")
        taze = pd.Series(np.linspace(100, 130, 30), index=gunler)
        bayat = pd.Series(np.linspace(50, 55, 30), index=gunler)
        bayat.iloc[10:] = np.nan          # 20 gundur veri yok
        return pd.DataFrame({"TAZE.IS": taze, "BAYAT.IS": bayat})

    def test_bayat_sembol_tespit_edilir(self):
        fiyatlar = FiyatVerisi(try_gecmis=self._gecmis(), usdtry=40.0,
                               eksik_semboller=[])
        bayatlar = fiyatlar.bayat_semboller(esik_gun=7)
        self.assertIn("BAYAT.IS", bayatlar)
        self.assertNotIn("TAZE.IS", bayatlar)
        self.assertGreaterEqual(bayatlar["BAYAT.IS"], 19)

    def test_bayat_fiyat_yine_de_degerlemede_kullanilir(self):
        """Uyarir ama degerlemeyi bozmaz - son bilinen fiyat en iyi tahmindir."""
        fiyatlar = FiyatVerisi(try_gecmis=self._gecmis(), usdtry=40.0,
                               eksik_semboller=[])
        self.assertIn("BAYAT.IS", fiyatlar.son_fiyatlar)

    def test_taze_veride_uyari_yok(self):
        gunler = pd.date_range("2026-01-01", periods=10, freq="D")
        gecmis = pd.DataFrame({"A.IS": np.linspace(10, 20, 10)}, index=gunler)
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        self.assertEqual(fiyatlar.bayat_semboller(), {})


class RiskTesti(unittest.TestCase):
    def test_max_drawdown_tepeden_dibe_olculur(self):
        seri = pd.Series([100.0, 120.0, 60.0, 80.0])
        self.assertAlmostEqual(_max_drawdown(seri), -0.5)  # 120 -> 60

    def test_max_drawdown_surekli_yukseliste_sifir(self):
        self.assertAlmostEqual(_max_drawdown(pd.Series([10.0, 11.0, 12.0])), 0.0)

    def test_euler_risk_katkilari_bire_toplanir(self):
        """Risk katkilari portfoy volatilitesini tam olarak boler."""
        rastgele = np.random.default_rng(42)
        gunler = pd.bdate_range("2025-01-01", periods=200)
        gecmis = pd.DataFrame(
            {
                "A.IS": 100 * np.exp(np.cumsum(rastgele.normal(0, 0.01, 200))),
                "B.IS": 200 * np.exp(np.cumsum(rastgele.normal(0, 0.02, 200))),
            },
            index=gunler,
        )
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        yapilandirma = Yapilandirma(
            ayarlar=AYARLAR,
            hedef_dagilim={"bist": 0.9, "nakit": 0.1},
            varliklar={
                "A.IS": Varlik("A.IS", "A", "bist", "TRY"),
                "B.IS": Varlik("B.IS", "B", "bist", "TRY"),
            },
            nakit_try=0.0,
            pozisyonlar=[],
        )
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL, sembol: A.IS, adet: 30, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-01, yon: AL, sembol: B.IS, adet: 20, fiyat_try: 200}\n",
            nakit=100000.0)
        portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
        rapor = riski_hesapla(yapilandirma, fiyatlar, portfoy)

        toplam_katki = sum(r.risk_katkisi for r in rapor.varlik_riskleri)
        self.assertAlmostEqual(toplam_katki, 1.0, places=6)
        self.assertGreater(rapor.portfoy_volatilitesi, 0.0)

    def test_cesitlendirme_portfoy_volatilitesini_dusurur(self):
        """Ters korele iki varlik -> portfoy volatilitesi ikisinden de dusuk."""
        gunler = pd.bdate_range("2025-01-01", periods=200)
        dalga = np.sin(np.linspace(0, 40, 200)) * 0.02
        gecmis = pd.DataFrame(
            {"A.IS": 100 * np.exp(np.cumsum(dalga)),
             "B.IS": 100 * np.exp(np.cumsum(-dalga))},
            index=gunler,
        )
        getiriler = ortak_getiriler(gecmis)
        self.assertLess(getiriler.corr().iloc[0, 1], -0.9)

        yil = AYARLAR.islem_gunu_yil
        tekil_vol = (getiriler.std() * np.sqrt(yil)).min()
        agirlik = pd.Series({"A.IS": 0.5, "B.IS": 0.5})
        portfoy_vol = float(np.sqrt(agirlik @ (getiriler.cov() * yil) @ agirlik))
        self.assertLess(portfoy_vol, tekil_vol)


class BildirimTesti(unittest.TestCase):
    def test_html_kacisi(self):
        self.assertEqual(_kacis("a & b < c > d"), "a &amp; b &lt; c &gt; d")

    def test_env_yorum_satirini_atlar(self):
        dosya = gecici_yaz(
            "# TELEGRAM_BOT_TOKEN : sahte-token\n"
            "TELEGRAM_CHAT_ID=123\n",
            ad=".env")
        env = env_oku(dosya)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", env)  # yorumdaki deger okunmamali
        self.assertEqual(env["TELEGRAM_CHAT_ID"], "123")

    def test_env_tirnak_temizler(self):
        dosya = gecici_yaz('TELEGRAM_CHAT_ID="123"\n', ad=".env")
        self.assertEqual(env_oku(dosya)["TELEGRAM_CHAT_ID"], "123")

    def test_ortam_degiskeni_dosyasiz_calisir(self):
        """GitHub Actions yolu: .env yok, secrets ortamdan gelir."""
        yok = Path(tempfile.mkdtemp()) / "olmayan.env"
        with unittest.mock.patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "ortam-token", "TELEGRAM_CHAT_ID": "999"},
        ):
            env = env_oku(yok)
        self.assertEqual(env["TELEGRAM_BOT_TOKEN"], "ortam-token")
        self.assertEqual(env["TELEGRAM_CHAT_ID"], "999")

    def test_ortam_degiskeni_dosyayi_ezer(self):
        dosya = gecici_yaz("TELEGRAM_CHAT_ID=dosyadan\n", ad=".env")
        with unittest.mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "ortamdan"}):
            self.assertEqual(env_oku(dosya)["TELEGRAM_CHAT_ID"], "ortamdan")

    def test_bos_ortam_degiskeni_dosyayi_ezmez(self):
        dosya = gecici_yaz("TELEGRAM_CHAT_ID=dosyadan\n", ad=".env")
        with unittest.mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": ""}):
            self.assertEqual(env_oku(dosya)["TELEGRAM_CHAT_ID"], "dosyadan")

    def test_ozet_mesaji_esik_asilmadiginda_sakin(self):
        yapilandirma = Yapilandirma(
            ayarlar=AYARLAR,
            hedef_dagilim={"bist": 0.5, "nakit": 0.5},
            varliklar={"A.IS": Varlik("A.IS", "A", "bist", "TRY")},
            nakit_try=500.0,
            pozisyonlar=[],
        )
        gunler = pd.bdate_range("2025-01-01", periods=100)
        rastgele = np.random.default_rng(7)
        gecmis = pd.DataFrame(
            {"A.IS": 100 * np.exp(np.cumsum(rastgele.normal(0, 0.005, 100)))},
            index=gunler)
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        durum = defter_durumu(
            f"  - {{tarih: 2026-01-01, yon: AL, sembol: A.IS, adet: 5, "
            f"fiyat_try: {gecmis['A.IS'].iloc[-1]:.4f}}}\n",
            nakit=10000.0)
        portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
        sapmalar = sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)
        rapor = riski_hesapla(yapilandirma, fiyatlar, portfoy)

        mesaj = ozet_mesaji(portfoy, sapmalar, rapor, durum, "Test")
        self.assertIn("Test", mesaj)
        self.assertNotIn("<script", mesaj.lower())


class SablonKorumasiTesti(unittest.TestCase):
    """Sablon portfoy gercek veri gibi raporlanmamali."""

    def _yapilandirma_oku(self, portfoy_icerigi: str) -> Yapilandirma:
        varliklar = gecici_yaz(
            "ayarlar: {kur_sembolu: 'USDTRY=X', gecmis_gun: 365, islem_gunu_yil: 252}\n"
            "hedef_dagilim: {bist: 0.5, nakit: 0.5}\n"
            "varliklar:\n"
            "  - {sembol: A.IS, ad: A, sinif: bist, kur: TRY}\n",
            ad="varliklar.yaml")
        return yapilandirmayi_oku(
            varliklar_dosyasi=varliklar,
            portfoy_dosyasi=gecici_yaz(portfoy_icerigi, ad="portfoy.yaml"),
        )

    def test_sablon_gercek_portfoy_yolunda_reddedilir(self):
        yapilandirma = self._yapilandirma_oku(
            "sablon: true\nnakit_try: 0\npozisyonlar: []\n")
        self.assertTrue(yapilandirma.sablon)
        with self.assertRaisesRegex(ValueError, "sablon"):
            sablonu_reddet(yapilandirma)

    def test_sablon_okuma_asamasinda_hata_vermez(self):
        """Simulasyon yolu ayni dosyayi okur - okuma patlamamali."""
        yapilandirma = self._yapilandirma_oku(
            "sablon: true\nnakit_try: 0\npozisyonlar: []\n")
        self.assertEqual(yapilandirma.pozisyonlar, [])

    def test_doldurulmus_portfoy_kabul_edilir(self):
        yapilandirma = self._yapilandirma_oku(
            "nakit_try: 100\npozisyonlar:\n"
            "  - {sembol: A.IS, adet: 1, maliyet: 10}\n")
        self.assertFalse(yapilandirma.sablon)
        sablonu_reddet(yapilandirma)   # hata vermemeli


if __name__ == "__main__":
    unittest.main(verbosity=2)
