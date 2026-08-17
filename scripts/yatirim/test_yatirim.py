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
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    Ayarlar,
    BayatlikEsikleri,
    Esikler,
    KurumsalOlayAyarlari,
    Varlik,
    Yapilandirma,
    sablonu_reddet,
    yapilandirmayi_oku,
)
from fetch import FiyatVerisi, kurumsal_olay_supheleri
from kurumsal_olay import KurumsalOlay, olaylari_oku
from ledger import durumu_hesapla, islemleri_oku
from notify import _islem_satirlari, _kacis, env_oku, ozet_mesaji
from portfolio import (
    Portfoy,
    PozisyonDegeri,
    portfoyu_hesapla,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from risk import (
    VarlikRiski,
    _max_drawdown,
    ortak_getiriler,
    riski_hesapla,
    yillik_periyot_sayisi,
)

AYARLAR = Ayarlar(kur_sembolu="USDTRY=X", gecmis_gun=365, islem_gunu_yil=252)
ESIKLER = Esikler(rebalancing_sapma=0.03, risk_katkisi_ust=0.20)


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
            esikler=ESIKLER,
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
            esikler=ESIKLER,
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
        getiriler, _ = ortak_getiriler(self._karisik_gecmis(), min_gozlem=2)
        # Hissenin gercekten islem gordugu 6 gun var -> 5 getiri.
        self.assertEqual(len(getiriler), 5)
        self.assertFalse(getiriler.isna().any().any())

    def test_hafta_sonu_bosluÄŸu_sifir_getiri_uretmez(self):
        getiriler, _ = ortak_getiriler(self._karisik_gecmis(), min_gozlem=2)
        self.assertFalse(
            (getiriler["HISSE.IS"] == 0).any(),
            "Kapali gun sifir getiri olarak sizmis - volatilite dusuk cikar",
        )

    def test_bosluk_sonrasi_getiri_tam_araligi_kapsar(self):
        getiriler, _ = ortak_getiriler(self._karisik_gecmis(), min_gozlem=2)
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
            ortak_getiriler(kesisimsiz, min_gozlem=2)

    def test_yetersiz_gecmisli_sembol_kesisimden_once_elenir(self):
        """Regresyon: yeni listelenmis tek hisse tum portfoyun penceresini kirpiyordu."""
        gunler = pd.date_range("2026-01-01", periods=100, freq="D")
        uzun = pd.Series(np.linspace(100, 200, 100), index=gunler)
        kisa = pd.Series(np.nan, index=gunler)
        kisa.iloc[-10:] = np.linspace(50, 55, 10)   # yalnizca 10 gozlem
        gecmis = pd.DataFrame({"UZUN.IS": uzun, "YENI.IS": kisa})

        getiriler, elenen = ortak_getiriler(gecmis, min_gozlem=30)
        self.assertEqual(elenen, ["YENI.IS"])
        self.assertNotIn("YENI.IS", getiriler.columns)
        # Kisa sembol elenmeseydi pencere 10 gune inerdi.
        self.assertGreater(len(getiriler), 90)


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
        bayatlar = fiyatlar.bayat_semboller(BayatlikEsikleri(varsayilan=7))
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


class DenetimRegresyonTesti(unittest.TestCase):
    """2026-08-14 kod denetiminde bulunan hatalarin regresyon testleri."""

    def _yapilandirma(self, semboller: dict) -> Yapilandirma:
        return Yapilandirma(
            ayarlar=AYARLAR, esikler=ESIKLER,
            hedef_dagilim={"bist": 0.5, "nakit": 0.5},
            varliklar=semboller, nakit_try=0.0, pozisyonlar=[],
        )

    # --- A1: mukerrer sembol agirliklari eziyordu ---
    def test_mukerrer_sembol_agirliklari_toplanir(self):
        pozisyonlar = [
            PozisyonDegeri("A.IS", "A", "bist", 10, 1000.0, 1000.0),
            PozisyonDegeri("A.IS", "A", "bist", 5, 500.0, 500.0),
        ]
        portfoy = Portfoy(pozisyonlar=pozisyonlar, nakit_try=0.0, fiyatlanamayan=[])
        # Dict comprehension olsaydi son lot ezer, agirlik 1/3 cikardi.
        self.assertAlmostEqual(portfoy.agirliklar["A.IS"], 1.0)

    def test_portfoy_yamlde_mukerrer_sembol_reddedilir(self):
        varliklar = gecici_yaz(
            "ayarlar: {kur_sembolu: 'USDTRY=X', gecmis_gun: 365, islem_gunu_yil: 252}\n"
            "hedef_dagilim: {bist: 1.0}\n"
            "varliklar:\n  - {sembol: A.IS, ad: A, sinif: bist, kur: TRY}\n",
            ad="varliklar.yaml")
        portfoy = gecici_yaz(
            "nakit_try: 0\npozisyonlar:\n"
            "  - {sembol: A.IS, adet: 10, maliyet: 100}\n"
            "  - {sembol: A.IS, adet: 5, maliyet: 120}\n", ad="portfoy.yaml")
        with self.assertRaisesRegex(ValueError, "birden fazla satirda"):
            yapilandirmayi_oku(varliklar_dosyasi=varliklar, portfoy_dosyasi=portfoy)

    # --- A3: gerceklesmemis kar satis komisyonu kadar sisiyordu ---
    def test_gerceklesmemis_kar_dogrudan_olculur(self):
        pozisyonlar = [PozisyonDegeri("A.IS", "A", "bist", 10, 1000.0, 1250.0)]
        portfoy = Portfoy(pozisyonlar=pozisyonlar, nakit_try=500.0, fiyatlanamayan=[])
        self.assertAlmostEqual(portfoy.gerceklesmemis_kar_try, 250.0)
        self.assertAlmostEqual(portfoy.pozisyon_maliyet_try, 1000.0)

    def test_sim_ozdesligi_tutar(self):
        """net = gerceklesmemis + gerceklesen + alis_komisyonu(negatif)."""
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-02, yon: SAT, sembol: X, adet: 4,  fiyat_try: 150}\n",
            nakit=5000.0, komisyon=0.001)
        gecmis = pd.DataFrame({"X": [100.0, 200.0]},
                              index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        yapilandirma = self._yapilandirma({"X": Varlik("X", "X", "bist", "TRY")})
        portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)

        net = portfoy.toplam_deger_try - durum.baslangic_nakit_try
        alis_komisyonu = 10 * 100 * 0.001
        self.assertAlmostEqual(
            net,
            portfoy.gerceklesmemis_kar_try + durum.gerceklesen_kar_try - alis_komisyonu,
            places=6,
        )

    # --- C2: tanimsiz sembol ciplak KeyError firlatiyordu ---
    def test_ledgerda_tanimsiz_sembol_anlamli_hata_verir(self):
        durum = defter_durumu(
            "  - {tarih: 2026-01-01, yon: AL, sembol: YOKBOYLE, adet: 1, fiyat_try: 10}\n")
        gecmis = pd.DataFrame({"X": [1.0, 2.0]},
                              index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        yapilandirma = self._yapilandirma({"X": Varlik("X", "X", "bist", "TRY")})
        with self.assertRaisesRegex(ValueError, "tanimsiz sembol"):
            portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)


class KismaKuraliTesti(unittest.TestCase):
    """Kisma karari katki VE beta birlikte tavani asinca verilmeli.

    Regresyon: yalnizca ham katkiya bakan kural, parasindan AZ risk tasiyan
    verimli varliklari (QQQ beta 0.85) sattiriyordu.
    """

    def _risk(self, katki: float, agirlik: float) -> VarlikRiski:
        return VarlikRiski(sembol="X", yillik_volatilite=0.3,
                           max_drawdown=-0.2, risk_katkisi=katki, agirlik=agirlik)

    def test_yuksek_katki_yuksek_beta_kisilir(self):
        # ASELS ornegi: katki %23.2, agirlik %11.6 -> beta 2.00
        self.assertTrue(ESIKLER.kisilmali(self._risk(0.232, 0.116)))

    def test_yuksek_katki_dusuk_beta_kisilmaz(self):
        # QQQ ornegi: katki %20.6 tavanin ustunde AMA beta 0.83 - verimli tasiyici
        self.assertFalse(ESIKLER.kisilmali(self._risk(0.206, 0.249)))

    def test_altin_gibi_agirlik_kaynakli_katki_kisilmaz(self):
        # Altin: katki %24.2, agirlik %19.5 -> beta 1.24, cesitlendirici
        self.assertFalse(ESIKLER.kisilmali(self._risk(0.242, 0.195)))

    def test_dusuk_katki_yuksek_beta_kisilmaz(self):
        # Beta yuksek ama pozisyon kucuk - portfoyu suruklemiyor
        self.assertFalse(ESIKLER.kisilmali(self._risk(0.08, 0.04)))

    def test_agirliksiz_varlik_beta_sifir(self):
        self.assertEqual(self._risk(0.0, 0.0).beta, 0.0)

    def test_gecersiz_beta_esigi_reddedilir(self):
        varliklar = gecici_yaz(
            "ayarlar: {kur_sembolu: 'USDTRY=X', gecmis_gun: 365, islem_gunu_yil: 252}\n"
            "esikler: {rebalancing_sapma: 0.03, risk_katkisi_ust: 0.2, risk_beta_ust: 0.8}\n"
            "hedef_dagilim: {bist: 1.0}\n"
            "varliklar:\n  - {sembol: A.IS, ad: A, sinif: bist, kur: TRY}\n",
            ad="varliklar.yaml")
        with self.assertRaisesRegex(ValueError, "risk_beta_ust"):
            yapilandirmayi_oku(
                varliklar_dosyasi=varliklar,
                portfoy_dosyasi=gecici_yaz("nakit_try: 0\npozisyonlar: []\n",
                                           ad="portfoy.yaml"))


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
            esikler=ESIKLER,
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
        getiriler, _ = ortak_getiriler(gecmis)
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

    def test_bugunku_islemler_mesaja_girer(self):
        bugun = date.today().isoformat()
        durum = defter_durumu(
            f"  - {{tarih: {bugun}, yon: AL, sembol: X, adet: 3, "
            f"fiyat_try: 100, gerekce: 'test gerekcesi'}}\n"
            "  - {tarih: 2020-01-01, yon: AL, sembol: Y, adet: 1, fiyat_try: 50}\n"
        )
        satirlar = "\n".join(_islem_satirlari(durum, bugun))
        self.assertIn("ALDIM", satirlar)
        self.assertIn("X", satirlar)
        self.assertIn("test gerekcesi", satirlar)
        self.assertNotIn("Y", satirlar)   # eski islem girmemeli

    def test_islem_yoksa_bolum_hic_cikmaz(self):
        durum = defter_durumu(
            "  - {tarih: 2020-01-01, yon: AL, sembol: X, adet: 1, fiyat_try: 50}\n")
        self.assertEqual(_islem_satirlari(durum, date.today().isoformat()), [])

    def test_satis_islemi_isaretlenir(self):
        bugun = date.today().isoformat()
        durum = defter_durumu(
            f"  - {{tarih: 2020-01-01, yon: AL,  sembol: X, adet: 5, fiyat_try: 100}}\n"
            f"  - {{tarih: {bugun}, yon: SAT, sembol: X, adet: 5, fiyat_try: 120}}\n"
        )
        satirlar = "\n".join(_islem_satirlari(durum, bugun))
        self.assertIn("SATTIM", satirlar)
        self.assertNotIn("ALDIM", satirlar)

    def test_ozet_mesaji_esik_asilmadiginda_sakin(self):
        yapilandirma = Yapilandirma(
            ayarlar=AYARLAR,
            esikler=ESIKLER,
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


class KurumsalOlayDefteriTesti(unittest.TestCase):
    """Bedelsiz/split: adet artar, TOPLAM maliyet degismez."""

    def _durum(self, islemler: str, olaylar: list[KurumsalOlay]):
        icerik = f"baslangic_nakit_try: 10000\nkomisyon_orani: 0\nislemler:\n{islemler}"
        kayitlar, nakit, komisyon = islemleri_oku(gecici_yaz(icerik))
        return durumu_hesapla(kayitlar, nakit, komisyon, olaylar)

    def test_bedelsiz_efektif_adet(self):
        """%100 bedelsiz: 10 lot -> 20 lot, maliyet 1000 TL'de KALIR."""
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 10, fiyat_try: 100}\n",
            [KurumsalOlay("2026-02-01", "X", "bedelsiz", 2.0)],
        )
        pozisyon = durum.pozisyonlar["X"]
        self.assertAlmostEqual(pozisyon.adet, 20.0)
        self.assertAlmostEqual(pozisyon.maliyet_try, 1000.0)
        # Birim maliyet turetilir ve yariya iner - kar/zarar uydurulmaz.
        self.assertAlmostEqual(pozisyon.maliyet_try / pozisyon.adet, 50.0)

    def test_olaydan_sonraki_alim_carpilmaz(self):
        """Zaman cizgisi tuzagi: olay yalnizca o an ELDEKI lota uygulanir."""
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-03-01, yon: AL, sembol: X, adet: 10, fiyat_try: 50}\n",
            [KurumsalOlay("2026-02-01", "X", "split", 2.0)],
        )
        # 10 -> 20 (split) + 10 (yeni alim) = 30. Toplu carpimda 40 cikardi.
        self.assertAlmostEqual(durum.pozisyonlar["X"].adet, 30.0)
        self.assertAlmostEqual(durum.pozisyonlar["X"].maliyet_try, 1500.0)

    def test_olaydan_sonraki_satis_yeni_adetle_dogrulanir(self):
        """Split sonrasi 15 lot satilabilir - split oncesi 10 lot vardi."""
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL,  sembol: X, adet: 10, fiyat_try: 100}\n"
            "  - {tarih: 2026-03-01, yon: SAT, sembol: X, adet: 15, fiyat_try: 60}\n",
            [KurumsalOlay("2026-02-01", "X", "split", 2.0)],
        )
        self.assertAlmostEqual(durum.pozisyonlar["X"].adet, 5.0)

    def test_ters_split_adedi_azaltir(self):
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 100, fiyat_try: 10}\n",
            [KurumsalOlay("2026-02-01", "X", "ters_split", 0.1)],
        )
        self.assertAlmostEqual(durum.pozisyonlar["X"].adet, 10.0)
        self.assertAlmostEqual(durum.pozisyonlar["X"].maliyet_try, 1000.0)

    def test_elde_olmayan_sembolun_olayi_yok_sayilir(self):
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 10, fiyat_try: 100}\n",
            [KurumsalOlay("2026-02-01", "Y", "bedelsiz", 2.0)],
        )
        self.assertNotIn("Y", durum.pozisyonlar)
        self.assertAlmostEqual(durum.pozisyonlar["X"].adet, 10.0)

    def test_yon_hatasi_reddedilir(self):
        """split'e 0.5 yazmak adedi 4 kat yanlis yapar - okurken yakalanmali."""
        dosya = gecici_yaz(
            "olaylar:\n"
            "  - {tarih: 2026-02-01, sembol: X, tip: split, oran: 0.5}\n")
        with self.assertRaises(ValueError) as baglam:
            olaylari_oku(dosya)
        self.assertIn("ters_split", str(baglam.exception))

    def test_defter_yoksa_sessizce_gecilmez(self):
        with self.assertRaises(FileNotFoundError):
            olaylari_oku(Path(tempfile.mkdtemp()) / "yok.yaml")


class KurumsalOlayTespitiTesti(unittest.TestCase):
    """Kayitli olmayan bedelsiz/split suphesi - hacimle ayirt edilir."""

    AYAR = KurumsalOlayAyarlari(getiri_esigi=0.25, hacim_carpani=1.5,
                                hacim_penceresi=20, tarama_gunu=5)

    def _veri(self, sok_orani: float, sok_hacim_carpani: float):
        """30 gunluk duz seri; son gun fiyat sok_orani kadar siciyor."""
        gunler = pd.date_range("2026-07-01", periods=30, freq="D")
        fiyat = pd.Series(100.0, index=gunler)
        fiyat.iloc[-1] = 100.0 * (1 + sok_orani)
        hacim = pd.Series(1_000_000.0, index=gunler)
        hacim.iloc[-1] = 1_000_000.0 * sok_hacim_carpani
        return pd.DataFrame({"X.IS": fiyat}), pd.DataFrame({"X.IS": hacim})

    def test_kurumsal_olay_otomatik_tespit(self):
        """%50 dusus + hacimde artis YOK -> supheli."""
        kapanis, hacim = self._veri(sok_orani=-0.50, sok_hacim_carpani=1.0)
        supheliler = kurumsal_olay_supheleri(kapanis, hacim, self.AYAR)
        self.assertIn("X.IS", supheliler)
        self.assertIn("-50.0", supheliler["X.IS"])

    def test_hacimli_cokus_supheli_sayilmaz(self):
        """Ayni dusus ama hacim 5 kat -> gercek satis dalgasi, olay degil."""
        kapanis, hacim = self._veri(sok_orani=-0.50, sok_hacim_carpani=5.0)
        self.assertEqual(kurumsal_olay_supheleri(kapanis, hacim, self.AYAR), {})

    def test_esik_altindaki_hareket_isaretlenmez(self):
        kapanis, hacim = self._veri(sok_orani=-0.10, sok_hacim_carpani=1.0)
        self.assertEqual(kurumsal_olay_supheleri(kapanis, hacim, self.AYAR), {})

    def test_deftere_yazilmis_olay_tekrar_uyarmaz(self):
        """Olay kaydedildikten sonra fiyat sicramasi veride kalir; sonsuza
        kadar 'supheli' demek o sembolu kalici olarak degerlemesiz birakir."""
        kapanis, hacim = self._veri(sok_orani=-0.50, sok_hacim_carpani=1.0)
        bilinen = {("X.IS", "2026-07-30")}
        self.assertEqual(
            kurumsal_olay_supheleri(kapanis, hacim, self.AYAR, bilinen), {})

    def test_hacim_verisi_yoksa_supheli_kalir(self):
        """Dogrulanamayan sicrama gercek sayilmaz - guvenli taraf."""
        kapanis, _ = self._veri(sok_orani=-0.50, sok_hacim_carpani=1.0)
        bos_hacim = pd.DataFrame(index=kapanis.index)
        self.assertIn("X.IS", kurumsal_olay_supheleri(kapanis, bos_hacim, self.AYAR))

    def test_supheli_sembol_degerlemeye_girmez(self):
        gunler = pd.date_range("2026-07-01", periods=5, freq="D")
        gecmis = pd.DataFrame({"X.IS": 100.0, "Y.IS": 50.0}, index=gunler)
        fiyatlar = FiyatVerisi(
            try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[],
            kurumsal_olay_supheleri={"X.IS": "test"},
        )
        self.assertNotIn("X.IS", fiyatlar.son_fiyatlar)
        self.assertIn("Y.IS", fiyatlar.son_fiyatlar)


class SinifBazliBayatlikTesti(unittest.TestCase):
    """Bayatlik takvim gunuyle degil, kacirilan ISLEM GUNU ile olculur."""

    ESIKLER = BayatlikEsikleri(varsayilan=7,
                               sinif_bazli={"bist": 1, "kripto": 0})

    def _gecmis(self):
        """2026-08-03 Pazartesi'den 14 gun. BIST yalnizca hafta ici veri verir."""
        gunler = pd.date_range("2026-08-03", periods=14, freq="D")
        hafta_ici = gunler[gunler.dayofweek < 5]
        bist = pd.Series(100.0, index=hafta_ici).reindex(gunler)
        return gunler, pd.DataFrame({
            "AAA.IS": bist,
            "BBB.IS": bist * 2,
            "BTC-USD": pd.Series(50.0, index=gunler),
            "ETH-USD": pd.Series(30.0, index=gunler),
        })

    def _fiyatlar(self, gecmis):
        return FiyatVerisi(
            try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[],
            sinif_haritasi={"AAA.IS": "bist", "BBB.IS": "bist",
                            "BTC-USD": "kripto", "ETH-USD": "kripto"},
        )

    def test_bayatlik_varlik_sinifi_bazli(self):
        """Hafta sonu BIST'i bayat yapmaz - takvim gunu sayan kural her
        Pazartesi 4 hisseyi yanlis isaretlerdi."""
        gunler, gecmis = self._gecmis()
        self.assertEqual(gunler[-1].dayofweek, 6)          # son gun Pazar
        bayatlar = self._fiyatlar(gecmis).bayat_semboller(self.ESIKLER)
        self.assertEqual(bayatlar, {})

    def test_kripto_4_gunluk_veri_reddediliyor(self):
        """Kripto 7/24 acik: 4 gun bar yoksa bu veri kesintisidir."""
        _, gecmis = self._gecmis()
        gecmis.loc[gecmis.index[-4:], "BTC-USD"] = np.nan
        bayatlar = self._fiyatlar(gecmis).bayat_semboller(self.ESIKLER)
        self.assertIn("BTC-USD", bayatlar)
        self.assertEqual(bayatlar["BTC-USD"], 4)
        self.assertNotIn("ETH-USD", bayatlar)

    def test_bist_gercek_kesintisi_yakalanir(self):
        """Hafta sonu affedilir ama 3 islem gunu kacirmak affedilmez."""
        _, gecmis = self._gecmis()
        gecmis.loc[gecmis.index[-6:], "AAA.IS"] = np.nan
        bayatlar = self._fiyatlar(gecmis).bayat_semboller(self.ESIKLER)
        self.assertIn("AAA.IS", bayatlar)
        self.assertNotIn("BBB.IS", bayatlar)

    def test_sinifi_tanimsiz_sembol_varsayilana_duser(self):
        _, gecmis = self._gecmis()
        gecmis["BILINMEYEN"] = np.nan
        gecmis.loc[gecmis.index[0], "BILINMEYEN"] = 10.0
        bayatlar = self._fiyatlar(gecmis).bayat_semboller(self.ESIKLER)
        self.assertIn("BILINMEYEN", bayatlar)       # 13 gun > varsayilan 7


if __name__ == "__main__":
    unittest.main(verbosity=2)



