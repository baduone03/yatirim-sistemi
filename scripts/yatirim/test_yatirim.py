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
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    Ayarlar,
    hafta_sonu_mu,
    BayatlikEsikleri,
    Bekleme,
    DevreKesici,
    Esikler,
    KurumsalOlayAyarlari,
    Varlik,
    VeriKaynaklari,
    Yapilandirma,
    sablonu_reddet,
    yapilandirmayi_oku,
)
from fetch import (
    FiyatVerisi,
    _serileri_hazirla,
    kripto_ucgenlemesi,
    kurumsal_olay_supheleri,
)
from kaynaklar import (
    DURDUR,
    OLCULEMEDI,
    PRIM,
    TAMAM,
    AnlikFiyat,
    KurKotasyonu,
    Ucgenleme,
    UcgenlemeAyarlari,
    UcgenlemeSonucu,
    btcturk_fiyatlari,
    tcmb_kayitlari,
    tcmb_yuzde_orani,
    ucgenle,
)
from kurumsal_olay import KurumsalOlay, olaylari_oku
from ledger import durumu_hesapla, islemleri_oku
from maliyet import (
    IslemProfili,
    MaliyetDagilimi,
    MaliyetKalemi,
    MaliyetModeli,
    asiri_getiri,
    donem_orani,
    modeli_kur,
    reel_getiri,
)
from bildirim import (
    ATLANDI,
    BIRIKTIRILDI,
    GONDERILDI,
    Bildirim,
    BildirimAyarlari,
    ayarlari_oku,
    bol,
    kuyrugu_oku,
    kuyrugu_yaz,
    son_saatteki_gonderim,
)
from mesaj import (
    Etki,
    GunSonuOzeti,
    IslemOnerisi,
    Tetikleyici,
    _islem_satirlari,
    gun_sonu_mesaji,
    islem_karari_mesaji,
    kacis,
    uyari_mesaji,
    uyarilari_topla,
)
from notify import (
    TelegramHatasi,
    env_oku,
    idempotent_gonder,
    kanaldan_gonder,
    kuyrugu_bosalt,
)
from piyasa import BRIFING, GUN_SONU, TARAMA, takvimi_coz  # noqa: F401
from portfolio import (
    KurAyristirmasi,
    Portfoy,
    PozisyonDegeri,
    SinifSapmasi,
    degisim_24s,
    kur_maruziyeti,
    portfoyu_hesapla,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from report import _dagilim_bolumu, _devre_kesici_bolumu, _risk_bolumu
from risk import (
    RiskRaporu,
    VarlikRiski,
    _max_drawdown,
    ortak_getiriler,
    riski_hesapla,
    yillik_periyot_sayisi,
)
from sinyal import (
    ARTIR,
    AZALT,
    BEKLEME,
    DEVRE_KESICI,
    EKSIK_MALIYET,
    HAFTA_SONU,
    KIS,
    SEMBOL,
    SINIF,
    SinyalDurumu,
    SinyalGecmisi,
    gecmisi_oku,
    gecmisi_yaz,
    gonderildi_yaz,
    gonderilen_anahtarlar,
    islem_anahtari,
    kararlari_uret,
    ozet_anahtari,
)

AYARLAR = Ayarlar(kur_sembolu="USDTRY=X", gecmis_gun=365, islem_gunu_yil=252)
ESIKLER = Esikler(rebalancing_sapma=0.03, risk_katkisi_ust=0.20,
                  rebalancing_geri_donus=0.015, risk_katkisi_geri_donus=0.17)
BEKLEME_YOK = Bekleme(ayni_sembol_saat=0.0)
BEKLEME_20 = Bekleme(ayni_sembol_saat=20.0)
KESICI = DevreKesici(gunluk_maks_islem=6)
BUGUN = "2026-08-17"


def karar_ver(sapmalar=(), risk=None, esikler=ESIKLER, bekleme=BEKLEME_YOK,
              kesici=KESICI, gecmis=None, maliyet=None, simdi=None):
    """Testlerde karar uretmenin kisa yolu."""
    return kararlari_uret(
        list(sapmalar),
        risk if risk is not None else RiskRaporu(0.0, 0.0, [], pd.DataFrame(), 0, []),
        esikler, bekleme, kesici, gecmis or SinyalGecmisi(), BUGUN, maliyet,
        simdi or datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc))


def gecici_yaz(icerik: str, ad: str = "test.yaml") -> Path:
    dosya = Path(tempfile.mkdtemp()) / ad
    dosya.write_text(icerik, encoding="utf-8")
    return dosya


def defter_durumu(islemler: str, nakit: float = 10000.0, komisyon: float = 0.0):
    icerik = (f"baslangic_nakit_try: {nakit}\nkomisyon_orani: {komisyon}\n"
              f"islemler:\n{islemler}")
    kayitlar, baslangic, oran, _ = islemleri_oku(gecici_yaz(icerik))
    return durumu_hesapla(kayitlar, baslangic, oran)


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
        self.assertEqual(kacis("a & b < c > d"), "a &amp; b &lt; c &gt; d")

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

        mesaj = gun_sonu_mesaji(GunSonuOzeti(
            portfoy=portfoy, risk=rapor, veri_zamani="2026-08-17",
            uyarilar=uyarilari_topla(fiyatlar, portfoy,
                                     karar_ver(sapmalar, rapor), None, None)))
        self.assertIn("Gun sonu", mesaj)
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
        kayitlar, nakit, komisyon, _ = islemleri_oku(gecici_yaz(icerik))
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


class UcgenlemeTesti(unittest.TestCase):
    """BTCTurk + CoinGecko + TCMB capraz kontrolu. Tamami cevrimdisi."""

    SIMDI = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    AYAR = UcgenlemeAyarlari(prim_esigi=0.03, durdurma_esigi=0.08,
                             btcturk_bayatlik_dakika=15)

    def _tl(self, deger: float, dakika_once: float = 0.0) -> AnlikFiyat:
        return AnlikFiyat("BTC-USD", deger,
                          self.SIMDI - timedelta(minutes=dakika_once), "btcturk")

    def _kur(self, deger: float = 40.0, gun_once: int = 0) -> KurKotasyonu:
        return KurKotasyonu(deger, date(2026, 8, 17) - timedelta(days=gun_once),
                            "tcmb")

    # --- 2.1 / 2.4 adim 1: BTCTurk bayatlik ---

    def test_btcturk_timestamp_bayatlik(self):
        """15 dk'dan eski kotasyon reddedilir - degerleme dogrulanmamis sayilir."""
        taze = ucgenle("BTC-USD", self._tl(2_500_000, 5), 62_500.0, self._kur(),
                       self.AYAR, self.SIMDI)
        self.assertEqual(taze.durum, TAMAM)

        bayat = ucgenle("BTC-USD", self._tl(2_500_000, 20), 62_500.0, self._kur(),
                        self.AYAR, self.SIMDI)
        self.assertEqual(bayat.durum, OLCULEMEDI)
        self.assertIn("bayat", bayat.gerekce)
        self.assertIsNone(bayat.tr_primi)

    def test_btcturk_timestamp_milisaniye_okunur(self):
        """timestamp ms cinsinden; saniye sanilirsa tarih 1970 olur."""
        ms = int(self.SIMDI.timestamp() * 1000)
        fiyatlar = btcturk_fiyatlari(
            "http://sahte",
            {"BTC-USD": "BTCTRY"},
            lambda url, **k: {"data": [{"pair": "BTCTRY", "last": "2500000",
                                        "timestamp": ms}]},
        )
        self.assertAlmostEqual(
            fiyatlar["BTC-USD"].gecikme_dakika(self.SIMDI), 0.0, places=3)

    # --- 2.4: esikler ---

    def test_ucgenleme_sapma_esikleri(self):
        """%3 alti tamam, %3-%8 arasi prim, %8 ustu durdur."""
        beklenen = 62_500.0 * 40.0        # 2.500.000 TL
        senaryolar = [
            (beklenen * 1.01, TAMAM),      # %1
            (beklenen * 1.05, PRIM),       # %5
            (beklenen * 1.10, DURDUR),     # %10
            (beklenen * 0.90, DURDUR),     # -%10, isaret fark etmez
            (beklenen * 0.95, PRIM),       # -%5
        ]
        for tl_deger, beklenen_durum in senaryolar:
            with self.subTest(tl=tl_deger):
                sonuc = ucgenle("BTC-USD", self._tl(tl_deger), 62_500.0,
                                self._kur(), self.AYAR, self.SIMDI)
                self.assertEqual(sonuc.durum, beklenen_durum)

    def test_esik_tam_sinirda_asilmis_sayilmaz(self):
        """Karsilastirma kesin buyuk (>): tam %3 prim esigini ASMAZ."""
        beklenen = 62_500.0 * 40.0
        sonuc = ucgenle("BTC-USD", self._tl(beklenen * 1.03), 62_500.0,
                        self._kur(), self.AYAR, self.SIMDI)
        self.assertEqual(sonuc.durum, TAMAM)

    # --- 2.4: TR primi ---

    def test_tr_primi_hesabi(self):
        """prim = (BTCTRY - BTC_USD x USD_TRY) / beklenen, ISARETLI."""
        sonuc = ucgenle("BTC-USD", self._tl(2_625_000.0), 62_500.0,
                        self._kur(40.0), self.AYAR, self.SIMDI)
        self.assertAlmostEqual(sonuc.beklenen_tl, 2_500_000.0)
        self.assertAlmostEqual(sonuc.tr_primi, 0.05)       # +%5
        self.assertAlmostEqual(sonuc.sapma, 0.05)

    def test_tr_primi_negatif_olabilir(self):
        """TL tarafi ucuzsa prim negatiftir - mutlak deger alinmaz."""
        sonuc = ucgenle("BTC-USD", self._tl(2_375_000.0), 62_500.0,
                        self._kur(40.0), self.AYAR, self.SIMDI)
        self.assertAlmostEqual(sonuc.tr_primi, -0.05)
        self.assertAlmostEqual(sonuc.sapma, 0.05)

    # --- 2.4: eksik kaynak DURDUR degildir ---

    def test_eksik_kaynak_durdurmaz_olculemedi_olur(self):
        """CoinGecko dusmesi tum gunun raporunu sildirmemeli."""
        for usd, kur in ((None, self._kur()), (62_500.0, None)):
            with self.subTest(usd=usd, kur=kur):
                sonuc = ucgenle("BTC-USD", self._tl(2_500_000), usd, kur,
                                self.AYAR, self.SIMDI)
                self.assertEqual(sonuc.durum, OLCULEMEDI)


class CiftCevrimTesti(unittest.TestCase):
    """Kripto degerlemesi BTCTurk TL cifti uzerinden - carpim degil."""

    SIMDI = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    BTCTURK_TL = 2_600_000.0          # BTCTurk'un gercek kotasyonu
    COINGECKO_USD = 62_500.0
    KUR = 40.0                        # carpim -> 2.500.000, TL cifti -> 2.600.000

    def _yapilandirma(self) -> Yapilandirma:
        return Yapilandirma(
            ayarlar=AYARLAR,
            esikler=ESIKLER,
            hedef_dagilim={"kripto": 1.0},
            varliklar={"BTC-USD": Varlik("BTC-USD", "Bitcoin", "kripto", "USD")},
            nakit_try=0.0,
            kaynaklar=VeriKaynaklari(
                btcturk_url="http://sahte/ticker",
                btcturk_ciftleri={"BTC-USD": "BTCTRY"},
                coingecko_url="http://sahte/gecko",
                coingecko_kimlikleri={"BTC-USD": "bitcoin"},
                tcmb_url="",                     # anahtar yok -> Yahoo kuru
                prim_esigi=0.03,
                durdurma_esigi=0.08,
            ),
        )

    def _getir(self, url, params=None, headers=None):
        if "ticker" in url:
            return {"data": [{"pair": "BTCTRY", "last": str(self.BTCTURK_TL),
                              "timestamp": int(self.SIMDI.timestamp() * 1000)}]}
        return {"bitcoin": {"usd": self.COINGECKO_USD}}

    def test_cift_cevrim_yapilmiyor(self):
        """Degerleme BTCTRY'yi DOGRUDAN kullanir, BTC_USD x USD_TRY'yi degil.

        Ikisi %4 farkli; carpim kullanilsaydi portfoy degeri TR primi kadar
        yanlis cikardi ve ustelik prim hep 0 olcuurdu - kendi kendini
        dogrulayan bir hesap.
        """
        sonuc = kripto_ucgenlemesi(
            self._yapilandirma(), yahoo_usdtry=self.KUR, env={},
            getir=self._getir, simdi=self.SIMDI, bugun=date(2026, 8, 17))

        gunler = pd.date_range("2026-08-10", periods=8, freq="D")
        # Yahoo serisi kasten YANLIS bir TL fiyat tasiyor; ezilmeli.
        gecmis = pd.DataFrame({"BTC-USD": 9_999_999.0}, index=gunler)
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=self.KUR,
                               eksik_semboller=[], ucgenleme=sonuc)

        self.assertAlmostEqual(fiyatlar.son_fiyatlar["BTC-USD"], self.BTCTURK_TL)
        self.assertNotAlmostEqual(
            fiyatlar.son_fiyatlar["BTC-USD"], self.COINGECKO_USD * self.KUR)
        # Prim gercekten olculmus: 2.600.000 / 2.500.000 - 1 = %4
        self.assertAlmostEqual(sonuc.sonuclar["BTC-USD"].tr_primi, 0.04)
        self.assertEqual(sonuc.sonuclar["BTC-USD"].durum, PRIM)

    def test_coingecko_degerlemeye_girmez(self):
        """CoinGecko yalnizca dogrulama - fiyati portfoye asla girmez."""
        sonuc = kripto_ucgenlemesi(
            self._yapilandirma(), yahoo_usdtry=self.KUR, env={},
            getir=self._getir, simdi=self.SIMDI, bugun=date(2026, 8, 17))
        self.assertEqual(set(sonuc.degerleme_fiyatlari()), {"BTC-USD"})
        self.assertAlmostEqual(
            sonuc.degerleme_fiyatlari()["BTC-USD"], self.BTCTURK_TL)

    def test_durdurma_durumunda_sembol_degerlemeden_cikar(self):
        gunler = pd.date_range("2026-08-10", periods=8, freq="D")
        gecmis = pd.DataFrame({"BTC-USD": 100.0, "AAPL": 200.0}, index=gunler)
        durduran = Ucgenleme("BTC-USD", DURDUR, "test", tl_fiyat=2_600_000.0)
        fiyatlar = FiyatVerisi(
            try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[],
            ucgenleme=UcgenlemeSonucu(sonuclar={"BTC-USD": durduran}))
        self.assertNotIn("BTC-USD", fiyatlar.son_fiyatlar)
        self.assertIn("AAPL", fiyatlar.son_fiyatlar)

    def test_kaynak_kapaliysa_yahoo_davranisi_korunur(self):
        """veri_kaynaklari bos -> FAZ 2 oncesi davranis, hicbir sey degismez."""
        yapilandirma = self._yapilandirma()
        kapali = Yapilandirma(
            ayarlar=yapilandirma.ayarlar, esikler=yapilandirma.esikler,
            hedef_dagilim=yapilandirma.hedef_dagilim,
            varliklar=yapilandirma.varliklar, nakit_try=0.0)
        sonuc = kripto_ucgenlemesi(kapali, yahoo_usdtry=40.0, env={})
        self.assertEqual(sonuc.sonuclar, {})
        self.assertEqual(sonuc.degerleme_fiyatlari(), {})


class TcmbKurTesti(unittest.TestCase):
    """TCMB birincil, Yahoo yedek. Bayat TCMB kuru kabul edilmez."""

    BUGUN = date(2026, 8, 17)          # Pazartesi

    def _yapilandirma(self, **kaynak) -> Yapilandirma:
        varsayilan = dict(
            btcturk_url="http://sahte/ticker",
            btcturk_ciftleri={"BTC-USD": "BTCTRY"},
            coingecko_url="http://sahte/gecko",
            coingecko_kimlikleri={"BTC-USD": "bitcoin"},
            tcmb_url="http://sahte/sk-seriler",
            tcmb_seri="TP.DK.USD.A.EF.YTL", tcmb_bayatlik_gun=1,
        )
        varsayilan.update(kaynak)
        return Yapilandirma(
            ayarlar=AYARLAR, esikler=ESIKLER, hedef_dagilim={"kripto": 1.0},
            varliklar={"BTC-USD": Varlik("BTC-USD", "Bitcoin", "kripto", "USD")},
            nakit_try=0.0, kaynaklar=VeriKaynaklari(**varsayilan))

    def _getir_fabrikasi(self, kur_tarihi: str, seri: str = "TP.DK.USD.A.EF.YTL"):
        """Gercek `sk-seriler` cevabinin sekli: dict degil LISTE."""
        self.cagrilar = []

        def getir(url, params=None, headers=None):
            self.cagrilar.append((url, params, headers))
            if "ticker" in url:
                return {"data": [{"pair": "BTCTRY", "last": "2500000",
                                  "timestamp": int(
                                      datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
                                      .timestamp() * 1000)}]}
            if "gecko" in url:
                return {"bitcoin": {"usd": 62_500.0}}
            return [
                {"seriKodu": "TP.DK.EUR.A.EF.YTL", "tarih": kur_tarihi,
                 "deger": 55.1},
                {"seriKodu": seri, "tarih": kur_tarihi, "deger": 47.6872},
            ]
        return getir

    def _kur_kaynagi(self, sonuc) -> str:
        return sonuc.sonuclar["BTC-USD"].kur_kaynagi

    def _calistir(self, getir):
        return kripto_ucgenlemesi(
            self._yapilandirma(), yahoo_usdtry=40.0, env={}, getir=getir,
            simdi=datetime(2026, 8, 17, 12, tzinfo=timezone.utc), bugun=self.BUGUN)

    def test_taze_tcmb_kuru_kullanilir(self):
        sonuc = self._calistir(self._getir_fabrikasi("17-08-2026"))
        self.assertEqual(self._kur_kaynagi(sonuc), "tcmb")

    def test_bayat_tcmb_kuru_reddedilir(self):
        """TCMB hafta sonu kur yayimlamaz. Cuma kuruyla Pazar ucgenlemesi,
        TR primi diye kurun bayatligini olcer."""
        sonuc = self._calistir(self._getir_fabrikasi("14-08-2026"))   # Cuma
        self.assertEqual(self._kur_kaynagi(sonuc), "yahoo (tcmb bayat)")
        self.assertTrue(any("bayat" in u for u in sonuc.uyarilar))

    def test_tcmb_cagrisinda_ANAHTAR_GONDERILMIYOR(self):
        """Guvenlik: bu uc nokta kimlik istemiyor, sir de gonderilmemeli."""
        self._calistir(self._getir_fabrikasi("17-08-2026"))
        tcmb_cagrilari = [c for c in self.cagrilar if "sk-seriler" in c[0]]
        self.assertEqual(len(tcmb_cagrilari), 1)
        _, params, headers = tcmb_cagrilari[0]
        self.assertIsNone(headers)
        self.assertIsNone(params)

    def test_seri_bulunamazsa_yahooya_duser(self):
        """Uc nokta calisir ama seri kodu degisirse sessizce yanlis kur alma."""
        sonuc = self._calistir(
            self._getir_fabrikasi("17-08-2026", seri="TP.DK.BASKA"))
        self.assertEqual(self._kur_kaynagi(sonuc), "yahoo")
        self.assertTrue(any("TCMB okunamadi" in u for u in sonuc.uyarilar))

    def test_uc_nokta_tanimsizsa_yahoo(self):
        yapilandirma = self._yapilandirma(tcmb_url="")
        sonuc = kripto_ucgenlemesi(
            yapilandirma, yahoo_usdtry=40.0, env={},
            getir=self._getir_fabrikasi("17-08-2026"),
            simdi=datetime(2026, 8, 17, 12, tzinfo=timezone.utc), bugun=self.BUGUN)
        self.assertEqual(self._kur_kaynagi(sonuc), "yahoo")


class MaliyetModeliTesti(unittest.TestCase):
    """Bilinmeyen maliyet SIFIR SAYILMAZ; eksik kalem sinyali bastirir."""

    HAM = {
        "maliyet": {
            "sinif_profili": {"bist": "bist", "nasdaq": "abd"},
            "islem": {
                "bist": {"komisyon_tip": "oransal", "komisyon_oran": 0.0015,
                         "kur_cevrimi": False, "menkul_spread": 0.001},
                "abd": {"komisyon_tip": "sabit", "komisyon_usd": 1.5,
                        "kur_cevrimi": True, "kur_spread_tek_yon": None,
                        "kambiyo_vergisi": None, "menkul_spread": 0.00002},
            },
            "tasima": {
                "A.IS": {"gider_orani_yillik": 0.0, "temettu_verimi": 0.0},
                "QQQ": {"gider_orani_yillik": 0.002, "temettu_verimi": None},
            },
            "firsat": {"tl_risksiz_yillik": 0.48},
        },
        "enflasyon": {"yillik": 0.25},
    }
    SINIFLAR = {"A.IS": "bist", "QQQ": "nasdaq"}

    def _model(self, ham=None) -> MaliyetModeli:
        return modeli_kur(ham or self.HAM, self.SINIFLAR)

    def test_eksik_maliyet_sinyal_uretmiyor(self):
        """`null` kalemi olan varlik icin islem sinyali cikmaz.

        Bu kuralin tamami: bilinmeyen maliyeti sifir saymak, karsiz bir
        islemi karli gosteren sessiz basarisizliktir.
        """
        model = self._model()
        self.assertFalse(model.sinyal_acik("QQQ"))
        self.assertIn("QQQ", model.engellenenler)
        # Gerekce SOMUT olmali: hangi kalem eksik, YAML'da nereye yazilacak.
        eksik = model.engellenenler["QQQ"]
        self.assertIn("abd.kur_spread_tek_yon", eksik)
        self.assertIn("abd.kambiyo_vergisi", eksik)
        self.assertIn("QQQ.temettu_verimi", eksik)

    def test_sifir_bilinmiyor_degildir(self):
        """0.0 olculmus bir degerdir, null degildir. Ikisini karistiran bir
        model ya hisse senedini sonsuza kadar bloklar ya da bilinmeyeni
        sifir sayar."""
        model = self._model()
        self.assertTrue(model.sinyal_acik("A.IS"))
        self.assertEqual(model.engellenenler, {"QQQ": unittest.mock.ANY})

    def test_profil_tanimsizsa_bloklanir(self):
        """Sinif haritasinda olmayan sinif = maliyeti bilinmeyen sinif."""
        model = modeli_kur(self.HAM, {"BTC-USD": "kripto"})
        self.assertFalse(model.sinyal_acik("BTC-USD"))
        self.assertIn("profili tanimsiz", model.engellenenler["BTC-USD"][0])

    def test_bilinmeyen_sembol_sinyal_uretmez(self):
        """Modelde hic gecmeyen sembol icin de sinyal cikmamali."""
        self.assertFalse(self._model().sinyal_acik("YOK.IS"))

    def test_sinif_sinyali_tum_semboller_blokluysa_kapanir(self):
        model = self._model()
        self.assertTrue(model.sinif_sinyali_acik("bist"))
        self.assertFalse(model.sinif_sinyali_acik("nasdaq"))

    def test_maliyet_tabani_pozisyon_buyutmekle_asilmaz(self):
        """Sabit komisyon kuculur, oransal spread KUCULMEZ.

        Bu yuzden ABD isleminin pozisyon boyutlandirmasiyla asilamayan bir
        maliyet tabani vardir; onceki model bu tabani hic gormuyordu.
        """
        profil = IslemProfili(
            ad="abd", komisyon_tip="sabit", komisyon_usd=1.5, kur_cevrimi=True,
            kur_spread_tek_yon=0.004, kambiyo_vergisi=0.0, menkul_spread=0.00002)
        kucuk = profil.gidis_donus(4_000, usdtry=47.69)
        buyuk = profil.gidis_donus(200_000, usdtry=47.69)
        self.assertLess(buyuk, kucuk)                 # komisyon payi eridi
        self.assertGreater(buyuk, 2 * 0.004)          # ama spread tabani duruyor

    def test_eksik_kalemli_profil_maliyet_hesaplamaz(self):
        """Eksik kalemle hesaplanan bir maliyet, eksik kismi sifir sayar."""
        self.assertIsNone(self._model().gidis_donus("QQQ", 10_000, 47.69))

    def test_canli_oran_okunamazsa_yedek_kalir(self):
        """TCMB'nin bir gunluk kesintisi hurdle rate'i SIFIRLAMAMALI."""
        model = self._model().oranlarla(None, None, ["TCMB okunamadi"])
        self.assertAlmostEqual(model.tl_risksiz_yillik, 0.48)
        self.assertEqual(model.risksiz_kaynagi, "yapilandirma")
        self.assertIn("TCMB okunamadi", model.uyarilar)

    def test_canli_oran_yedegi_ezer(self):
        model = self._model().oranlarla((0.5191, "tcmb TP.TRY.MT02"), None, [])
        self.assertAlmostEqual(model.tl_risksiz_yillik, 0.5191)
        self.assertIn("tcmb", model.risksiz_kaynagi)
        # Yeni nesne dondu, eskisi degismedi.
        self.assertAlmostEqual(self._model().tl_risksiz_yillik, 0.48)


class HurdleReelGetiriTesti(unittest.TestCase):
    """Sifira gore degil, risksiz getiriye ve enflasyona gore olcum."""

    def test_hurdle_rate_asiri_getiri(self):
        """Risksizin ALTINDAKI getiri negatif asiri getiri verir.

        Sifira gore pozitif ama mevduata gore negatif bir portfoy basarili
        degildir; eski rapor bunu basari olarak gosteriyordu.
        """
        risksiz = donem_orani(0.48, 365)
        self.assertAlmostEqual(risksiz, 0.48, places=9)
        self.assertLess(asiri_getiri(0.20, risksiz), 0)     # %20 < %48 -> kotu
        self.assertGreater(asiri_getiri(0.60, risksiz), 0)

    def test_donem_orani_bilesik(self):
        """Yillik oran doneme BILESIK indirgenir, dogrusal degil."""
        yarim = donem_orani(0.48, 182.5)
        self.assertAlmostEqual((1 + yarim) ** 2 - 1, 0.48, places=9)
        self.assertLess(yarim, 0.24)               # dogrusal olsaydi tam %24
        self.assertEqual(donem_orani(0.48, 0), 0.0)
        self.assertEqual(donem_orani(0.48, -5), 0.0)

    def test_reel_getiri_carpimsal(self):
        """(1+n)/(1+e)-1 kullanilir; toplamsal (n-e) DEGIL.

        %40 nominal / %25 enflasyonda toplamsal %15 der, dogrusu %12.0.
        Yuksek enflasyonda bu fark yanlis karar verdirecek buyukluktedir.
        """
        reel = reel_getiri(0.40, 0.25)
        self.assertAlmostEqual(reel, 0.12, places=9)
        self.assertNotAlmostEqual(reel, 0.40 - 0.25, places=3)

    def test_reel_getiri_enflasyon_uzerinde_pozitif(self):
        self.assertGreater(reel_getiri(0.30, 0.25), 0)
        self.assertLess(reel_getiri(0.20, 0.25), 0)


class NakitGetirisiTesti(unittest.TestCase):
    """Yatirilmamis TL sifir getiriyle DURMAZ."""

    def _durum(self, islemler: str = "", **ek):
        icerik = (f"baslangic_nakit_try: 10000\nkomisyon_orani: 0\n"
                  f"baslangic_tarihi: 2026-01-01\nislemler:\n{islemler}")
        kayitlar, nakit, komisyon, baslangic = islemleri_oku(gecici_yaz(icerik))
        return durumu_hesapla(kayitlar, nakit, komisyon, None,
                              baslangic_tarihi=baslangic, **ek)

    def test_nakit_getirisi(self):
        """Nakit risksiz oranda isler. Sifir getiri modellemek 'nakitte
        beklemek maliyetsiz' yanilgisi uretir."""
        durum = self._durum(nakit_getirisi_yillik=0.48, bugun="2026-12-31")
        beklenen = 10000 * ((1.48) ** (364 / 365) - 1)
        self.assertAlmostEqual(durum.nakit_getirisi_try, beklenen, places=6)
        self.assertGreater(durum.nakit_getirisi_try, 0)
        self.assertAlmostEqual(durum.nakit_try, 10000 + beklenen, places=6)

    def test_oran_verilmezse_davranis_degismez(self):
        """Geriye uyum: faiz kapaliyken defter eskisi gibi calisir."""
        durum = self._durum(bugun="2026-12-31")
        self.assertEqual(durum.nakit_getirisi_try, 0.0)
        self.assertEqual(durum.nakit_try, 10000)

    def test_faiz_islem_sonrasi_bakiyeye_isler(self):
        """Alimdan sonra kalan bakiyeye faiz isler - tum sermayeye degil."""
        durum = self._durum(
            "  - {tarih: 2026-07-01, yon: AL, sembol: X, adet: 10, fiyat_try: 600}\n",
            nakit_getirisi_yillik=0.48, bugun="2026-12-31")
        ilk = 10000 * ((1.48) ** (181 / 365) - 1)          # 01-01 -> 07-01
        kalan = 10000 + ilk - 6000
        ikinci = kalan * ((1.48) ** (183 / 365) - 1)       # 07-01 -> 12-31
        self.assertAlmostEqual(durum.nakit_getirisi_try, ilk + ikinci, places=6)

    def test_ayni_gun_islemde_faiz_islemez(self):
        durum = self._durum(
            "  - {tarih: 2026-01-01, yon: AL, sembol: X, adet: 1, fiyat_try: 100}\n"
            "  - {tarih: 2026-01-01, yon: AL, sembol: Y, adet: 1, fiyat_try: 100}\n",
            nakit_getirisi_yillik=0.48, bugun="2026-01-01")
        self.assertEqual(durum.nakit_getirisi_try, 0.0)


class MaliyetDagilimiTesti(unittest.TestCase):
    """Brut -> net -> asiri yolu. Olculemeyen kalem sifir SAYILMAZ."""

    def _dagilim(self, **ek) -> MaliyetDagilimi:
        varsayilan = dict(
            brut_getiri=0.0840,
            kalemler=[
                MaliyetKalemi("Komisyon", 0.0120),
                MaliyetKalemi("Kur spread", None),
                MaliyetKalemi("Gider orani", 0.0009),
                MaliyetKalemi("Temettu stopaji", None),
                MaliyetKalemi("Vergi", None),
            ],
            risksiz=0.0500,
            donem_gun=365,
        )
        varsayilan.update(ek)
        return MaliyetDagilimi(**varsayilan)

    def test_maliyet_dagilimi_toplami(self):
        """Net = brut - OLCULEN kalemler. Olculemeyenler toplama girmez."""
        dagilim = self._dagilim()
        self.assertAlmostEqual(dagilim.olculen_maliyet, 0.0129)
        self.assertAlmostEqual(dagilim.net_getiri, 0.0840 - 0.0129)
        self.assertAlmostEqual(dagilim.asiri_getiri, 0.0840 - 0.0129 - 0.0500)

    def test_olculemeyen_kalem_sifir_sayilmaz(self):
        """None'i 0.0 yapan bir uygulama ayni sonucu verirdi - ayrimi
        `eksik_kalemler` gorunur kilar, yoksa rapor net getiriyi kesin
        sanip ust sinir oldugunu soylemez."""
        dagilim = self._dagilim()
        self.assertEqual(dagilim.eksik_kalemler,
                         ["Kur spread", "Temettu stopaji", "Vergi"])
        sifirli = self._dagilim(kalemler=[
            MaliyetKalemi(k.ad, k.oran if k.olculdu else 0.0)
            for k in dagilim.kalemler])
        self.assertEqual(sifirli.eksik_kalemler, [])
        self.assertAlmostEqual(sifirli.net_getiri, dagilim.net_getiri)

    def test_sifir_olculmus_kalem_eksik_sayilmaz(self):
        """0.0 bir olcumdur: yapisal sifir (kur cevrimi yok) eksik degildir."""
        dagilim = self._dagilim(kalemler=[MaliyetKalemi("Kur spread", 0.0)])
        self.assertEqual(dagilim.eksik_kalemler, [])
        self.assertAlmostEqual(dagilim.net_getiri, 0.0840)


class SinyalBastirmaTesti(unittest.TestCase):
    """Eksik maliyet kalemi hem raporda hem Telegram'da sinyali bastirir."""

    def setUp(self):
        self.model = modeli_kur(MaliyetModeliTesti.HAM, MaliyetModeliTesti.SINIFLAR)

    def _risk(self):
        return RiskRaporu(
            portfoy_volatilitesi=0.3, portfoy_max_drawdown=0.1,
            varlik_riskleri=[VarlikRiski("QQQ", 0.4, 0.2, 0.35, 0.15)],
            korelasyon=pd.DataFrame(), gozlem_sayisi=100, yetersiz_veri=[])

    def test_rebalancing_tavsiyesi_bastirilir(self):
        sapmalar = [SinifSapmasi("nasdaq", 0.40, 0.25),
                    SinifSapmasi("bist", 0.10, 0.30)]
        karar = karar_ver(sapmalar, maliyet=self.model)
        metin = "\n".join(_dagilim_bolumu(sapmalar, 20_000, 0.03, [], karar))
        self.assertIn(EKSIK_MALIYET, metin)
        self.assertNotIn("azalt", metin)        # nasdaq blokluydu
        self.assertIn("artir", metin)           # bist acik

    def test_maliyet_modelsiz_davranis_degismez(self):
        sapmalar = [SinifSapmasi("nasdaq", 0.40, 0.25)]
        metin = "\n".join(
            _dagilim_bolumu(sapmalar, 20_000, 0.03, [], karar_ver(sapmalar)))
        self.assertIn("azalt", metin)

    def test_kisma_sinyali_bastirilir(self):
        risk = self._risk()
        karar = karar_ver(risk=risk, maliyet=self.model)
        metin = "\n".join(_risk_bolumu(risk, {}, ESIKLER, karar))
        self.assertIn(EKSIK_MALIYET, metin)
        self.assertNotIn("**Kisilmali:**", metin)

    def test_telegram_da_bastirir(self):
        """Rapor bastirip Telegram bastirmazsa kural bosa duser - Dodo
        mesaja bakip islem yapar."""
        portfoy = Portfoy(
            pozisyonlar=[PozisyonDegeri("QQQ", "QQQ", "nasdaq", 1, 8000, 8000)],
            nakit_try=2000.0, fiyatlanamayan=[])
        risk = self._risk()
        sapmalar = [SinifSapmasi("nasdaq", 0.80, 0.25)]

        acik = karar_ver(sapmalar, risk)
        self.assertTrue(acik.sinyaller(SEMBOL))
        self.assertTrue(acik.sinyaller(SINIF))

        # Eksik maliyet modeliyle HICBIR sinyal uretilmemeli - islem karari
        # mesaji sinyal listesinden uretildigi icin Telegram'a da hicbir sey
        # gitmez. Bastirma tek noktada oldugu icin ikinci bir kontrol gereksiz.
        kapali = karar_ver(sapmalar, risk, maliyet=self.model)
        self.assertEqual(kapali.sinyaller(), [])

        uyarilar = "\n".join(
            uyarilari_topla(None, portfoy, kapali, self.model, None))
        self.assertIn("Eksik maliyet kalemi", uyarilar)
        self.assertIn("temettu_verimi", uyarilar)

    def test_telegram_ozeti_kalem_bazli_gruplar(self):
        """Gunluk mesaj her gun 11 ayni satir basmamali - okunmayan uyari
        yok hukmundedir. Sembol oneki tasima kaleminden dusulur, profil
        oneki islem kaleminde KALIR (hangi profil duzeltilecek bilgisi)."""
        ozet = self.model.eksik_kalem_ozeti
        self.assertEqual(ozet["temettu_verimi"], ["QQQ"])
        self.assertEqual(ozet["abd.kur_spread_tek_yon"], ["QQQ"])
        self.assertNotIn("QQQ.temettu_verimi", ozet)


class TcmbOranTesti(unittest.TestCase):
    """Yuzde cinsinden yayimlanan seriler ve tarih bicimleri."""

    KAYITLAR = [
        {"seriKodu": "TP.TRY.MT02", "tarih": "07-08-2026", "deger": 47.91},
        {"seriKodu": "TP.PKAUO.S01.E.U", "tarih": "AĞUSTOS 2026", "deger": 23.69},
    ]

    def _kayitlar(self):
        return tcmb_kayitlari("http://sahte", getir=lambda *a, **k: self.KAYITLAR)

    def test_yuzde_ondalik_orana_cevrilir(self):
        """47.91 yuzdedir; 47.91 kat getiri degil %47.91."""
        oran, kaynak = tcmb_yuzde_orani(
            self._kayitlar(), "TP.TRY.MT02", 21, date(2026, 8, 17))
        self.assertAlmostEqual(oran, 0.4791)
        self.assertIn("TP.TRY.MT02", kaynak)

    def test_aylik_tarih_cozulur(self):
        """Aylik seri 'AGUSTOS 2026' yazar, gunluk seri '07-08-2026'."""
        kayitlar = self._kayitlar()
        self.assertEqual(kayitlar["TP.PKAUO.S01.E.U"].tarih, date(2026, 8, 1))
        self.assertEqual(kayitlar["TP.TRY.MT02"].tarih, date(2026, 8, 7))

    def test_bayat_seri_reddedilir(self):
        """Bayat oran sessizce kullanilirsa hurdle rate aylarca yanlis kalir."""
        self.assertIsNone(tcmb_yuzde_orani(
            self._kayitlar(), "TP.TRY.MT02", 21, date(2026, 10, 1)))

    def test_olmayan_seri_none_doner(self):
        self.assertIsNone(tcmb_yuzde_orani(
            self._kayitlar(), "TP.YOK", 21, date(2026, 8, 17)))


def _riskler(*varliklar: VarlikRiski) -> RiskRaporu:
    return RiskRaporu(portfoy_volatilitesi=0.3, portfoy_max_drawdown=-0.1,
                      varlik_riskleri=list(varliklar), korelasyon=pd.DataFrame(),
                      gozlem_sayisi=100, yetersiz_veri=[])


class HisterezisTesti(unittest.TestCase):
    """Sinyal tetikte acilir, geri donuse inmeden kapanmaz."""

    def _sapma(self, sapma: float) -> SinifSapmasi:
        # SinifSapmasi.sapma = guncel - hedef
        return SinifSapmasi("bist", 0.30 + sapma, 0.30)

    def test_histerezis_salinim(self):
        """Esik etrafinda salinan deger her kosuda sinyal URETMEMELI.

        Tek esikli kural 2.9 -> 3.1 -> 2.9 puan salinimda ac/kapa/ac yapardi;
        bant sayesinde sinyal 1.5'in altina inene kadar acik KALIR ve
        arada ters islem cikmaz.
        """
        gecmis = SinyalGecmisi()
        gorulen = []
        for puan in (0.029, 0.031, 0.029, 0.020, 0.016, 0.014, 0.020):
            karar = karar_ver([self._sapma(puan)], gecmis=gecmis)
            gorulen.append(karar.acik_mi(SINIF, "bist"))
            gecmis = karar.gecmis
        #                2.9    3.1   2.9   2.0   1.6   1.4    2.0
        self.assertEqual(gorulen,
                         [False, True, True, True, True, False, False])

    def test_geri_donus_altinda_latch_kapanir(self):
        acik = karar_ver([self._sapma(0.04)]).gecmis
        self.assertTrue(acik.durum(SINIF, "bist").acik)
        kapali = karar_ver([self._sapma(0.010)], gecmis=acik).gecmis
        self.assertFalse(kapali.durum(SINIF, "bist").acik)

    def test_ters_yon_tetigi_yeniden_asmali(self):
        """+2 puandan -2 puana gecen sinif ters islem onerisi URETMEMELI.

        Geri donus esigi (1.5) yalnizca AYNI yondeki sinyali ayakta tutar.
        Ters yon icin tetigi (3 puan) yeniden asmak sart - yoksa bant, hic
        tetiklenmemis bir ters islemi mesrulastirir.
        """
        acik = karar_ver([self._sapma(0.04)])          # +4 puan -> azalt
        self.assertEqual(acik.sonuc(SINIF, "bist").yon, AZALT)

        ters = karar_ver([self._sapma(-0.02)], gecmis=acik.gecmis)
        self.assertFalse(ters.acik_mi(SINIF, "bist"))

        buyuk_ters = karar_ver([self._sapma(-0.04)], gecmis=acik.gecmis)
        self.assertTrue(buyuk_ters.acik_mi(SINIF, "bist"))
        self.assertEqual(buyuk_ters.sonuc(SINIF, "bist").yon, ARTIR)

    def test_kisma_bandi_katkiya_uygulanir(self):
        """Katki %20 tetigini asip %18'e dustugunde sinyal acik kalir."""
        yuksek = _riskler(VarlikRiski("A", 0.4, -0.2, 0.22, 0.10))   # beta 2.20
        orta = _riskler(VarlikRiski("A", 0.4, -0.2, 0.18, 0.10))     # beta 1.80
        dusuk = _riskler(VarlikRiski("A", 0.4, -0.2, 0.16, 0.10))    # beta 1.60

        self.assertFalse(karar_ver(risk=orta).acik_mi(SEMBOL, "A"))
        acik = karar_ver(risk=yuksek)
        self.assertTrue(acik.acik_mi(SEMBOL, "A"))
        surdu = karar_ver(risk=orta, gecmis=acik.gecmis)
        self.assertTrue(surdu.acik_mi(SEMBOL, "A"))
        self.assertFalse(
            karar_ver(risk=dusuk, gecmis=surdu.gecmis).acik_mi(SEMBOL, "A"))

    def test_gecersiz_bant_reddedilir(self):
        """Geri donus tetigin ustundeyse bant yoktur - sessiz kalmamali."""
        varliklar = gecici_yaz(
            "ayarlar: {kur_sembolu: 'USDTRY=X', gecmis_gun: 365, islem_gunu_yil: 252}\n"
            "esikler: {rebalancing_sapma: 0.03, rebalancing_geri_donus: 0.05,\n"
            "          risk_katkisi_ust: 0.2, risk_katkisi_geri_donus: 0.17}\n"
            "hedef_dagilim: {bist: 1.0}\n"
            "varliklar:\n  - {sembol: A.IS, ad: A, sinif: bist, kur: TRY}\n",
            ad="varliklar.yaml")
        with self.assertRaisesRegex(ValueError, "rebalancing_geri_donus"):
            yapilandirmayi_oku(
                varliklar_dosyasi=varliklar,
                portfoy_dosyasi=gecici_yaz("nakit_try: 0\npozisyonlar: []\n",
                                           ad="portfoy.yaml"))


class BeklemeSuresiTesti(unittest.TestCase):
    """Ayni sembolde asgari sure gecmeden ikinci sinyal cikmaz."""

    ZAMAN = datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc)

    def _risk(self):
        return _riskler(VarlikRiski("A", 0.4, -0.2, 0.30, 0.10))

    def test_bekleme_suresi_24saat(self):
        """24 saatlik pencerede ikinci sinyal engellenir, sonrasinda cikar."""
        bekleme = Bekleme(ayni_sembol_saat=24.0)
        ilk = karar_ver(risk=self._risk(), bekleme=bekleme, simdi=self.ZAMAN)
        self.assertTrue(ilk.acik_mi(SEMBOL, "A"))

        erken = karar_ver(risk=self._risk(), bekleme=bekleme,
                          gecmis=ilk.gecmis, simdi=self.ZAMAN + timedelta(hours=5))
        self.assertFalse(erken.acik_mi(SEMBOL, "A"))
        self.assertEqual(erken.sonuc(SEMBOL, "A").sebep, BEKLEME)
        self.assertAlmostEqual(erken.sonuc(SEMBOL, "A").kalan_saat, 19.0)

        gec = karar_ver(risk=self._risk(), bekleme=bekleme,
                        gecmis=ilk.gecmis, simdi=self.ZAMAN + timedelta(hours=25))
        self.assertTrue(gec.acik_mi(SEMBOL, "A"))

    def test_24_saat_gunluk_kadansla_carpisir(self):
        """Yapilandirmadaki 20 saatin gerekcesi.

        Actions gunde bir kez calisiyor -> iki kosu arasi tam 24.0 saat, cron
        gecikmesiyle bazen 23.7 bazen 24.3. Esik 24 olsaydi gunlerin yaklasik
        yarisinda TUM sembol sinyalleri sessizce dusurulurdu. 20 saat gunluk
        kadansta hicbir seyi engellemez, kadans saatlige cikinca devreye girer.
        """
        ilk = karar_ver(risk=self._risk(), bekleme=Bekleme(24.0), simdi=self.ZAMAN)
        gec = self.ZAMAN + timedelta(hours=23, minutes=42)   # cron gecikmesi
        self.assertFalse(
            karar_ver(risk=self._risk(), bekleme=Bekleme(24.0),
                      gecmis=ilk.gecmis, simdi=gec).acik_mi(SEMBOL, "A"))
        self.assertTrue(
            karar_ver(risk=self._risk(), bekleme=BEKLEME_20,
                      gecmis=ilk.gecmis, simdi=gec).acik_mi(SEMBOL, "A"))

    def test_bastirilan_sinyal_saati_ilerletmez(self):
        """Bastirilan sinyal saati ilerletseydi bekleme kendini uzatir ve
        sembol bir daha ASLA sinyal uretmezdi."""
        ilk = karar_ver(risk=self._risk(), bekleme=BEKLEME_20, simdi=self.ZAMAN)
        damga = ilk.gecmis.durum(SEMBOL, "A").son_sinyal

        erken = karar_ver(risk=self._risk(), bekleme=BEKLEME_20,
                          gecmis=ilk.gecmis, simdi=self.ZAMAN + timedelta(hours=5))
        self.assertEqual(erken.gecmis.durum(SEMBOL, "A").son_sinyal, damga)

    def test_rapor_bekleme_etiketini_basar(self):
        """Bos hucre "dengede" der; okuyan esigin asilmadigini sanar."""
        ilk = karar_ver(risk=self._risk(), bekleme=BEKLEME_20, simdi=self.ZAMAN)
        erken = karar_ver(risk=self._risk(), bekleme=BEKLEME_20,
                          gecmis=ilk.gecmis, simdi=self.ZAMAN + timedelta(hours=5))
        metin = "\n".join(_risk_bolumu(self._risk(), {}, ESIKLER, erken))
        self.assertIn("BEKLEME (15 saat)", metin)

    def test_bekleme_kapaliyken_engel_yok(self):
        ilk = karar_ver(risk=self._risk(), simdi=self.ZAMAN)
        ikinci = karar_ver(risk=self._risk(), gecmis=ilk.gecmis,
                           simdi=self.ZAMAN + timedelta(minutes=1))
        self.assertTrue(ikinci.acik_mi(SEMBOL, "A"))


class DevreKesiciTesti(unittest.TestCase):
    """Gunluk tavan asilirsa HICBIR sinyal uretilmez."""

    def _riskler_n(self, adet: int) -> RiskRaporu:
        return _riskler(*[VarlikRiski(f"S{i}", 0.4, -0.2, 0.30, 0.10)
                          for i in range(adet)])

    def test_devre_kesici_6_islem(self):
        """6 sinyal gecer, 7. tumunu durdurur - tavan ASILINCA kesilir."""
        alti = karar_ver(risk=self._riskler_n(6))
        self.assertFalse(alti.devre_kesildi)
        self.assertEqual(len(alti.sinyaller()), 6)

        yedi = karar_ver(risk=self._riskler_n(7))
        self.assertTrue(yedi.devre_kesildi)
        self.assertEqual(yedi.sinyaller(), [])
        self.assertEqual(yedi.gunluk_sayi, 7)
        self.assertEqual(yedi.sonuc(SEMBOL, "S0").sebep, DEVRE_KESICI)

    def test_gun_icinde_birikir(self):
        """Siklik artinca tavan tek kosuya degil GUNE uygulanmali."""
        ilk = karar_ver(risk=self._riskler_n(4))
        self.assertFalse(ilk.devre_kesildi)
        self.assertEqual(ilk.gecmis.gunluk_sayi, 4)

        ikinci = karar_ver(risk=self._riskler_n(4), gecmis=ilk.gecmis)
        self.assertTrue(ikinci.devre_kesildi)
        self.assertEqual(ikinci.gunluk_sayi, 8)

    def test_sayac_gun_degisince_sifirlanir(self):
        dun = SinyalGecmisi(gun="2026-08-16", gunluk_sayi=99)
        karar = karar_ver(risk=self._riskler_n(2), gecmis=dun)
        self.assertFalse(karar.devre_kesildi)
        self.assertEqual(karar.gunluk_sayi, 2)

    def test_kesilen_gunde_sayac_ilerlemez(self):
        """Sayac ilerleseydi devre bir daha asla kapanmazdi."""
        kesik = karar_ver(risk=self._riskler_n(7))
        self.assertEqual(kesik.gecmis.gunluk_sayi, 0)

    def test_rapor_ve_mesaj_uyariyi_basar(self):
        risk = self._riskler_n(7)
        karar = karar_ver(risk=risk)
        rapor = "\n".join(_risk_bolumu(risk, {}, ESIKLER, karar))
        self.assertIn(DEVRE_KESICI, rapor)
        self.assertNotIn("**Kisilmali:**", rapor)

        # Uyari raporun EN USTUNDE olmali - asagida kalirsa kimse gormez.
        ust = "\n".join(_devre_kesici_bolumu(karar))
        self.assertIn("ANORMAL ISLEM YOGUNLUGU", ust)
        self.assertIn("7 islem sinyali", ust)
        self.assertEqual(_devre_kesici_bolumu(karar_ver(risk=self._riskler_n(2))), [])

        portfoy = Portfoy(pozisyonlar=[], nakit_try=1000.0, fiyatlanamayan=[])
        uyarilar = uyarilari_topla(None, portfoy, karar, None, None)
        self.assertIn("ANORMAL ISLEM YOGUNLUGU", uyarilar[0])
        mesaj = gun_sonu_mesaji(GunSonuOzeti(
            portfoy=portfoy, risk=risk, veri_zamani="2026-08-17",
            uyarilar=uyarilar))
        self.assertIn("ANORMAL ISLEM YOGUNLUGU", mesaj)


class IdempotencyTesti(unittest.TestCase):
    """Ayni mesaj iki kere gonderilmez."""

    def setUp(self):
        self.log = Path(tempfile.mkdtemp()) / "gonderilen.log"
        self.zaman = datetime(2026, 8, 17, 16, 30, tzinfo=timezone.utc)

    def test_idempotency_ayni_mesaj_iki_kez(self):
        cagrilar = []
        with unittest.mock.patch("notify.mesaj_gonder",
                                 side_effect=lambda m, e=None: cagrilar.append(m)):
            ilk = idempotent_gonder("ozet", ozet_anahtari(BUGUN), [], {},
                                    self.log, self.zaman)
            ikinci = idempotent_gonder("ozet", ozet_anahtari(BUGUN), [], {},
                                       self.log, self.zaman + timedelta(hours=1))
        self.assertTrue(ilk)
        self.assertFalse(ikinci)
        self.assertEqual(len(cagrilar), 1)

    def test_ertesi_gun_yeniden_gonderilir(self):
        gonderildi_yaz([ozet_anahtari(BUGUN)], self.zaman, self.log)
        with unittest.mock.patch("notify.mesaj_gonder"):
            self.assertTrue(idempotent_gonder(
                "ozet", ozet_anahtari("2026-08-18"), [], {}, self.log, self.zaman))

    def test_gonderim_basarisizsa_log_yazilmaz(self):
        """Once yazip sonra gonderseydik basarisiz mesaj bir daha denenmezdi."""
        with unittest.mock.patch("notify.mesaj_gonder",
                                 side_effect=TelegramHatasi("ag yok")):
            with self.assertRaises(TelegramHatasi):
                idempotent_gonder("ozet", ozet_anahtari(BUGUN), [], {},
                                  self.log, self.zaman)
        self.assertEqual(gonderilen_anahtarlar(self.log), set())

    def test_islem_anahtari_saat_icerir(self):
        """Siklik artinca ayni gun ayni sembolde iki farkli sinyal olabilir."""
        sabah = islem_anahtari("A.IS", KIS,
                               datetime(2026, 8, 17, 9, 5, tzinfo=timezone.utc))
        aksam = islem_anahtari("A.IS", KIS,
                               datetime(2026, 8, 17, 17, 5, tzinfo=timezone.utc))
        self.assertEqual(sabah, "islem:A.IS:2026-08-17:09:kis")
        self.assertNotEqual(sabah, aksam)

    def test_ek_anahtarlar_kaydedilir(self):
        with unittest.mock.patch("notify.mesaj_gonder"):
            idempotent_gonder("ozet", ozet_anahtari(BUGUN),
                              ["islem:A.IS:2026-08-17:16:kis"], {}, self.log,
                              self.zaman)
        self.assertEqual(
            gonderilen_anahtarlar(self.log),
            {ozet_anahtari(BUGUN), "islem:A.IS:2026-08-17:16:kis"})


class SinyalDurumuDosyasiTesti(unittest.TestCase):
    """Latch hafizasi diskte kalici olmali - yoksa histerezis calismaz."""

    def setUp(self):
        self.dosya = Path(tempfile.mkdtemp()) / "sinyal-durumu.yaml"

    def test_yazilip_okunan_durum_ayni(self):
        gecmis = SinyalGecmisi(
            siniflar={"bist": SinyalDurumu(True, AZALT, "2026-08-17T16:00:00+00:00")},
            semboller={"A.IS": SinyalDurumu(True, KIS, "2026-08-17T16:00:00+00:00")},
            gun=BUGUN, gunluk_sayi=2)
        gecmisi_yaz(gecmis, self.dosya)
        okunan = gecmisi_oku(self.dosya)
        self.assertEqual(okunan.durum(SINIF, "bist"), gecmis.siniflar["bist"])
        self.assertEqual(okunan.durum(SEMBOL, "A.IS"), gecmis.semboller["A.IS"])
        self.assertEqual(okunan.gunluk_sayi, 2)

    def test_dosya_yoksa_bos_gecmis(self):
        bos = gecmisi_oku(self.dosya)
        self.assertFalse(bos.durum(SINIF, "bist").acik)
        self.assertEqual(bos.bugunku_sayi(BUGUN), 0)

    def test_bozuk_zaman_damgasi_atilir_ve_uyarir(self):
        """Sessizce yok saymak beklemeyi ya sonsuza kilitler ya devre disi
        birakir; ikisi de gorunmez olmamali."""
        self.dosya.write_text(
            "gun: '2026-08-17'\ngunluk_sayi: 1\nsiniflar: {}\n"
            "semboller:\n  A.IS: {acik: true, yon: kis, son_sinyal: 'dun'}\n",
            encoding="utf-8")
        okunan = gecmisi_oku(self.dosya)
        self.assertEqual(okunan.durum(SEMBOL, "A.IS").son_sinyal, "")
        self.assertTrue(okunan.durum(SEMBOL, "A.IS").acik)
        self.assertTrue(any("son_sinyal" in u for u in okunan.uyarilar))


class HizSiniriTesti(unittest.TestCase):
    """Saatlik tavan asilirsa mesajlar TEK ozete birlesir."""

    def setUp(self):
        dizin = Path(tempfile.mkdtemp())
        self.log = dizin / "gonderilen.log"
        self.kuyruk = dizin / "kuyruk.yaml"
        self.ayarlar = BildirimAyarlari(saatlik_maks_mesaj=2)
        self.zaman = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)  # TR 15:00

    def _gonder(self, sira: int, simdi=None):
        return kanaldan_gonder(
            Bildirim("uyari", f"uyari:test:{sira}", f"mesaj {sira}"),
            self.ayarlar, {}, self.log, self.kuyruk, simdi or self.zaman)

    def test_hiz_siniri_toplama(self):
        cagrilar = []
        with unittest.mock.patch("notify.mesaj_gonder",
                                 side_effect=lambda m, e=None: cagrilar.append(m)):
            self.assertEqual(self._gonder(1).durum, GONDERILDI)
            self.assertEqual(self._gonder(2).durum, GONDERILDI)
            ucuncu = self._gonder(3)          # tavani asiyor -> toplu gider
        self.assertEqual(ucuncu.durum, GONDERILDI)
        self.assertEqual(len(cagrilar), 3)
        self.assertIn("Hiz siniri", cagrilar[2])
        self.assertIn("mesaj 3", cagrilar[2])
        self.assertEqual(kuyrugu_oku(self.kuyruk), [])

    def test_saatlik_pencere_kayar(self):
        """Bir saat sonra sayac sifirlanir - sinir kalici sansur degil."""
        with unittest.mock.patch("notify.mesaj_gonder"):
            self._gonder(1)
            self._gonder(2)
            self.assertEqual(son_saatteki_gonderim(self.zaman, self.log), 2)
            sonra = self.zaman + timedelta(hours=1, minutes=1)
            self.assertEqual(son_saatteki_gonderim(sonra, self.log), 0)
            self.assertEqual(self._gonder(3, sonra).durum, GONDERILDI)

    def test_islem_anahtarlari_sayilmaz(self):
        """Islem kararlari devre kesiciyle sinirli; hiz sinirini doldurup
        gun sonu ozetini bastirmamalari gerekir."""
        gonderildi_yaz(["islem:A:2026-08-17:12:kis"] * 9, self.zaman, self.log)
        self.assertEqual(son_saatteki_gonderim(self.zaman, self.log), 0)

    def test_kuyruktaki_anahtar_ikilenmez(self):
        kuyrugu_yaz([Bildirim("uyari", "uyari:test:1", "mesaj 1")], self.kuyruk)
        sessiz = BildirimAyarlari(sessiz_baslangic=time(0, 0),
                                  sessiz_bitis=time(23, 59))
        sonuc = kanaldan_gonder(Bildirim("uyari", "uyari:test:1", "mesaj 1"),
                                sessiz, {}, self.log, self.kuyruk, self.zaman)
        self.assertEqual(sonuc.durum, ATLANDI)
        self.assertEqual(len(kuyrugu_oku(self.kuyruk)), 1)


class SessizSaatTesti(unittest.TestCase):
    """Gece bildirimi birikir, sabah tek mesaj olarak gider."""

    def setUp(self):
        dizin = Path(tempfile.mkdtemp())
        self.log = dizin / "gonderilen.log"
        self.kuyruk = dizin / "kuyruk.yaml"
        self.ayarlar = BildirimAyarlari()          # 01:00-08:00 TR

    def _an(self, tr_saat: int) -> datetime:
        """TR saatini UTC damgaya cevirir (kalici UTC+3)."""
        return datetime(2026, 8, 17, (tr_saat - 3) % 24, 0, tzinfo=timezone.utc)

    def test_sessiz_saat_biriktirme(self):
        cagrilar = []
        with unittest.mock.patch("notify.mesaj_gonder",
                                 side_effect=lambda m, e=None: cagrilar.append(m)):
            gece = kanaldan_gonder(Bildirim("uyari", "uyari:gece", "gece uyarisi"),
                                   self.ayarlar, {}, self.log, self.kuyruk,
                                   self._an(3))
            self.assertEqual(gece.durum, BIRIKTIRILDI)
            self.assertEqual(cagrilar, [])
            sonuc = kuyrugu_bosalt(self.ayarlar, {}, self.log, self.kuyruk,
                                   self._an(9))
        self.assertEqual(sonuc.durum, GONDERILDI)
        self.assertEqual(len(cagrilar), 1)
        self.assertIn("gece uyarisi", cagrilar[0])
        self.assertEqual(kuyrugu_oku(self.kuyruk), [])

    def test_sessiz_saatte_bosaltma_yapilmaz(self):
        kuyrugu_yaz([Bildirim("uyari", "u:1", "m")], self.kuyruk)
        with unittest.mock.patch("notify.mesaj_gonder") as sahte:
            sonuc = kuyrugu_bosalt(self.ayarlar, {}, self.log, self.kuyruk,
                                   self._an(4))
        self.assertEqual(sonuc.durum, ATLANDI)
        sahte.assert_not_called()
        self.assertEqual(len(kuyrugu_oku(self.kuyruk)), 1)

    def test_sessiz_sinir_saatleri(self):
        self.assertFalse(self.ayarlar.sessiz_mi(self._an(0)))   # 00:00 acik
        self.assertTrue(self.ayarlar.sessiz_mi(self._an(1)))    # 01:00 sessiz
        self.assertTrue(self.ayarlar.sessiz_mi(self._an(7)))
        self.assertFalse(self.ayarlar.sessiz_mi(self._an(8)))   # 08:00 acik

    def test_gece_yarisini_asan_aralik(self):
        gece = BildirimAyarlari(sessiz_baslangic=time(23, 0), sessiz_bitis=time(7, 0))
        self.assertTrue(gece.sessiz_mi(self._an(23)))
        self.assertTrue(gece.sessiz_mi(self._an(2)))
        self.assertFalse(gece.sessiz_mi(self._an(12)))

    def _kanal(self, tip: str, an: datetime, ayarlar=None):
        cagrilar = []
        with unittest.mock.patch("notify.mesaj_gonder",
                                 side_effect=lambda m, e=None: cagrilar.append(m)):
            sonuc = kanaldan_gonder(Bildirim(tip, f"{tip}:test", f"{tip} metni"),
                                    ayarlar or self.ayarlar, {}, self.log,
                                    self.kuyruk, an)
        return sonuc, cagrilar

    def test_islem_karari_sessiz_saatte_gecer(self):
        """Kripto 7/24. Gece 03:00'te uretilen islem sinyalini sabaha
        biriktirmek onu islem olarak degersiz kilar - fiyat 8 saat sonra
        orada olmayabilir."""
        sonuc, cagrilar = self._kanal("islem", self._an(3))
        self.assertEqual(sonuc.durum, GONDERILDI)
        self.assertEqual(len(cagrilar), 1)
        self.assertEqual(kuyrugu_oku(self.kuyruk), [])

    def test_ozet_sessiz_saatte_yine_birikir(self):
        """Istisna DAR olmali: gun sonu ozeti aciliyet tasimaz, birikmeli.
        Istisna tum tiplere yayilsaydi sessiz saat kurali anlamsizlasirdi."""
        sonuc, cagrilar = self._kanal("gunsonu", self._an(3))
        self.assertEqual(sonuc.durum, BIRIKTIRILDI)
        self.assertEqual(cagrilar, [])

    def test_istisna_bos_birakilirsa_islem_de_birikir(self):
        """`istisna_tipler: []` -> gece hic uyanma. Ayar gercekten kapanmali."""
        kapali = BildirimAyarlari(sessiz_istisna_tipler=frozenset())
        sonuc, cagrilar = self._kanal("islem", self._an(3), kapali)
        self.assertEqual(sonuc.durum, BIRIKTIRILDI)
        self.assertEqual(cagrilar, [])

    def test_istisna_gece_kuyrugunu_bosaltmaz(self):
        """Sessiz saatte gecen islem sinyali hiz siniri BIRLESTIRMESINI
        tetiklememeli. Tetikleseydi 01:05'teki tek bir kripto sinyali, saat
        00:55'te dolan sinir yuzunden tum gece kuyrugunu yollardi."""
        gece_yarisi = self._an(0) + timedelta(minutes=55)
        gonderildi_yaz([f"uyari:dolgu:{i}" for i in range(5)],
                       gece_yarisi, self.log)
        kuyrugu_yaz([Bildirim("uyari", "uyari:gece", "gece uyarisi")], self.kuyruk)

        sonuc, cagrilar = self._kanal("islem", self._an(1) + timedelta(minutes=5))

        self.assertEqual(sonuc.durum, GONDERILDI)
        self.assertEqual(len(cagrilar), 1)
        self.assertIn("islem metni", cagrilar[0])
        self.assertNotIn("gece uyarisi", cagrilar[0])
        self.assertEqual(len(kuyrugu_oku(self.kuyruk)), 1)

    def test_ayni_sessiz_aralik_reddedilir(self):
        dosya = gecici_yaz(
            "sessiz_saatler: {baslangic: '01:00', bitis: '01:00'}\n",
            ad="bildirim.yaml")
        with self.assertRaisesRegex(ValueError, "24 saat sessizlik"):
            ayarlari_oku(dosya)


class MesajBolmeTesti(unittest.TestCase):
    """4096 asan mesaj bolunmezse Telegram REDDEDER - mesaj hic gitmez."""

    def test_mesaj_4096_bolme(self):
        satir = "- " + "x" * 78
        uzun = "\n".join([satir] * 120)          # ~9600 karakter
        parcalar = bol(uzun)
        self.assertGreater(len(parcalar), 1)
        for parca in parcalar:
            self.assertLessEqual(len(parca), 4096)
        self.assertEqual("".join(parcalar).count(satir), 120)
        self.assertIn("(1/", parcalar[0])

    def test_sinirin_altinda_bolunmez(self):
        self.assertEqual(bol("kisa mesaj"), ["kisa mesaj"])

    def test_satir_ortasindan_kesilmez(self):
        """Tablo satirinin ortasindan kesmek mesaji okunmaz yapar."""
        satirlar = [f"- sembol{i} 1.000 TL (10.0%) +1.5%" for i in range(200)]
        for parca in bol("\n".join(satirlar)):
            govde = parca.split("\n\n<i>(")[0]
            for satir in govde.split("\n"):
                if satir:
                    self.assertIn(satir, satirlar)

    def test_tek_dev_satir_kesilir(self):
        """Gondermemektense kesmek yeglenir."""
        parcalar = bol("y" * 9000)
        self.assertGreater(len(parcalar), 1)
        for parca in parcalar:
            self.assertLessEqual(len(parca), 4096)


class HtmlKacisTesti(unittest.TestCase):
    """HTML parse modunda kacilmayan karakter mesaji BOZAR."""

    def test_html_kacis_ampersand(self):
        self.assertEqual(kacis("A&B"), "A&amp;B")
        # Sira kritik: & ilk sirada olmali, yoksa &lt; icindeki & yeniden
        # kacirilir ve okuyucu &amp;lt; gorur.
        self.assertEqual(kacis("<b>"), "&lt;b&gt;")
        self.assertEqual(kacis("a & <b> & c"), "a &amp; &lt;b&gt; &amp; c")

    def test_kacis_iki_kez_cagrilmamali(self):
        bir = kacis("A&B")
        self.assertEqual(bir, "A&amp;B")
        self.assertNotEqual(kacis(bir), bir)     # ikinci cagri BOZAR

    def test_uyari_mesajinda_kacis(self):
        sonuc = uyari_mesaji("veri", "fiyat < 0 & bayat")
        self.assertIn("&lt; 0 &amp;", sonuc)
        self.assertNotIn("< 0 &", sonuc)


class VeriZamaniTesti(unittest.TestCase):
    """Mesajda VERI zamani yazar, MESAJ zamani degil."""

    def _islem(self):
        return IslemOnerisi(sembol="QQQ", yon="SAT", adet=2.5, fiyat_try=1000.0,
                            veri_zamani="2026-08-14", veri_kaynagi="yahoo")

    def test_veri_zamani_mesajda(self):
        """Mesaj 17'sinde gitse de fiyat 14'une aitse karar 14 verisiyle
        verilmistir. Mesaj zamanini gostermek bayat veriyi guncel gibi sunar."""
        metin = islem_karari_mesaji(
            self._islem(), [Tetikleyici("Risk katkisi", 0.25, 0.20)],
            [Etki("Agirlik", 0.30, 0.20)], 0.0318, 15.9)
        self.assertIn("2026-08-14", metin)
        self.assertIn("yahoo", metin)
        self.assertNotIn(date.today().isoformat(), metin)

    def test_tetikleyen_ve_etki_yazilir(self):
        metin = islem_karari_mesaji(
            self._islem(),
            [Tetikleyici("Risk katkisi", 0.25, 0.20),
             Tetikleyici("Beta", 1.90, 1.50, "sayi")],
            [Etki("Agirlik", 0.30, 0.20)], 0.0318, 15.9)
        self.assertIn("Risk katkisi 25.00% (esik 20.00%)", metin)
        self.assertIn("Beta 1.90 (esik 1.50)", metin)
        self.assertIn("30.00% → 20.00%", metin)
        self.assertIn("3.18%", metin)

    def test_eksik_maliyet_uyarisi(self):
        """Gidis-donus olculemezse islem KARSIZ olabilir - bu yazilmali."""
        metin = islem_karari_mesaji(self._islem(), [], [], None, None)
        self.assertIn("OLCULEMEDI", metin)
        self.assertIn("KARSIZ olabilir", metin)


class HaftaSonuEsigiTesti(unittest.TestCase):
    """Hafta sonu esigi genisler; arada kalan sinyal UYARI olur, islem olmaz."""

    CUMA = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    CUMARTESI = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    GENIS = Esikler(rebalancing_sapma=0.03, risk_katkisi_ust=0.20,
                    rebalancing_geri_donus=0.015, risk_katkisi_geri_donus=0.17,
                    hafta_sonu_carpani=1.5)

    def _risk(self, katki: float):
        # agirlik 0.10 -> beta = katki/0.10, her durumda 1.50 uzerinde
        return _riskler(VarlikRiski("BTC-USD", 0.6, -0.4, katki, 0.10))

    def test_hafta_sonu_esik_genis(self):
        """Katki %25: hafta ici sinyal (esik %20), hafta sonu yalnizca uyari
        (genis esik %20 x 1.5 = %30)."""
        hafta_ici = karar_ver(risk=self._risk(0.25), esikler=self.GENIS,
                              simdi=self.CUMA)
        self.assertTrue(hafta_ici.acik_mi(SEMBOL, "BTC-USD"))

        hafta_sonu = karar_ver(risk=self._risk(0.25), esikler=self.GENIS,
                               simdi=self.CUMARTESI)
        self.assertFalse(hafta_sonu.acik_mi(SEMBOL, "BTC-USD"))
        self.assertEqual(hafta_sonu.sonuc(SEMBOL, "BTC-USD").sebep, HAFTA_SONU)
        self.assertEqual(len(hafta_sonu.hafta_sonu_uyarilari), 1)

    def test_genis_esigi_asan_hafta_sonunda_da_gecer(self):
        """Bilgi kesilmiyor, cita yukseliyor: %35 katki hafta sonu da sinyal."""
        karar = karar_ver(risk=self._risk(0.35), esikler=self.GENIS,
                          simdi=self.CUMARTESI)
        self.assertTrue(karar.acik_mi(SEMBOL, "BTC-USD"))

    def test_carpan_1_ise_hafta_sonu_ayrimi_yok(self):
        karar = karar_ver(risk=self._risk(0.25), simdi=self.CUMARTESI)
        self.assertTrue(karar.acik_mi(SEMBOL, "BTC-USD"))

    def test_hafta_sonu_uyarisi_listeye_girer(self):
        """Sinyal bastirilmadi, SINIFI dusuruldu - kaybolmamali."""
        karar = karar_ver(risk=self._risk(0.25), esikler=self.GENIS,
                          simdi=self.CUMARTESI)
        uyarilar = "\n".join(uyarilari_topla(None, None, karar, None, None))
        self.assertIn("BTC-USD", uyarilar)
        self.assertIn("hafta sonu genis esigi", uyarilar)

    def test_daralan_carpan_reddedilir(self):
        dosya = gecici_yaz(
            "ayarlar: {kur_sembolu: 'USDTRY=X', gecmis_gun: 365, islem_gunu_yil: 252}\n"
            "esikler: {rebalancing_sapma: 0.03, rebalancing_geri_donus: 0.015,\n"
            "          risk_katkisi_ust: 0.2, risk_katkisi_geri_donus: 0.17,\n"
            "          hafta_sonu_carpani: 0.8}\n"
            "hedef_dagilim: {bist: 1.0}\n"
            "varliklar:\n  - {sembol: A.IS, ad: A, sinif: bist, kur: TRY}\n",
            ad="varliklar.yaml")
        with self.assertRaisesRegex(ValueError, "hafta_sonu_carpani"):
            yapilandirmayi_oku(
                varliklar_dosyasi=dosya,
                portfoy_dosyasi=gecici_yaz("nakit_try: 0\npozisyonlar: []\n",
                                           ad="portfoy.yaml"))


class HaftaSonuUcgenlemeTesti(unittest.TestCase):
    """7/24 calismanin on kosulu: hafta sonu kur donmus, kripto hareketli.

    Forex Cuma 22:00 - Pazar 22:00 UTC arasi kapali, TCMB is gunu disinda kur
    yayimlamaz. Bu yuzden hafta sonu "beklenen TL" Cuma kuruyla hesaplanir ve
    BTCTurk'un canli fiyatiyla arasindaki fark TR primi DEGIL, kurun
    bayatligidir. Gercek kopukluk sayilsaydi DURDUR cikar ve rapor hic
    uretilmezdi - simulasyon hafta sonu tamamen susardi.
    """

    AYARLAR_U = UcgenlemeAyarlari(prim_esigi=0.03, durdurma_esigi=0.08)

    def _ucgenle(self, tl: float, kapali: bool):
        return ucgenle(
            "BTC-USD",
            AnlikFiyat("BTC-USD", tl,
                       datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
                       "btcturk"),
            1000.0,
            KurKotasyonu(40.0, date(2026, 8, 14), "yahoo (tcmb bayat)"),
            self.AYARLAR_U,
            datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
            kapali)

    def test_hafta_sonu_buyuk_sapma_durdurmaz(self):
        """Beklenen 40.000, gercek 44.000 -> %10 sapma, durdurma esigi %8."""
        hafta_ici = self._ucgenle(44_000.0, False)
        self.assertEqual(hafta_ici.durum, DURDUR)      # eski davranis

        hafta_sonu = self._ucgenle(44_000.0, True)
        self.assertEqual(hafta_sonu.durum, OLCULEMEDI)
        self.assertIn("kur piyasasi kapali", hafta_sonu.gerekce)

    def test_hafta_sonu_degerleme_fiyati_korunur(self):
        """Ucgenleme yapilamasa da BTCTurk TL fiyati elimizde - degerleme
        durmaz, yalnizca capraz kontrol yapilmaz."""
        sonuc = self._ucgenle(40_500.0, True)
        self.assertAlmostEqual(sonuc.tl_fiyat, 40_500.0)

    def test_hafta_ici_normal_calisir(self):
        sonuc = self._ucgenle(40_100.0, False)
        self.assertEqual(sonuc.durum, TAMAM)

    def test_hafta_sonu_tespiti_tr_takvimiyle(self):
        # Cuma TR 23:00 = UTC 20:00 -> hala hafta ici
        self.assertFalse(hafta_sonu_mu(
            datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc)))
        # Cumartesi TR 01:00 = Cuma UTC 22:00 -> hafta sonu
        self.assertTrue(hafta_sonu_mu(
            datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)))
        # Pazartesi TR 01:00 = Pazar UTC 22:00 -> hafta ici
        self.assertFalse(hafta_sonu_mu(
            datetime(2026, 8, 16, 22, 0, tzinfo=timezone.utc)))


class TakvimTesti(unittest.TestCase):
    """Hangi kosu ne yapar, hangi seans acik."""

    HAM = {
        "seanslar": {
            "kripto": {"gunler": "her_gun", "baslangic": "00:00", "bitis": "23:59"},
            "bist": {"gunler": "hafta_ici", "baslangic": "10:00", "bitis": "18:00"},
            "abd": {"gunler": "hafta_ici", "baslangic": "16:30", "bitis": "23:00"},
        },
        "gun_sonu_saati": "23:30",
        "brifing_gunu": 0,
        "brifing_saati": "09:00",
    }

    def setUp(self):
        self.takvim = takvimi_coz(self.HAM)

    def _an(self, gun: int, tr_saat: int, tr_dakika: int = 0) -> datetime:
        """TR saatini UTC damgaya cevirir. 2026-08-17 Pazartesi."""
        return (datetime(2026, 8, gun, tr_saat, tr_dakika, tzinfo=timezone.utc)
                - timedelta(hours=3))

    def test_bist_hafta_ici_saatleri(self):
        self.assertIn("bist", self.takvim.acik_seanslar(self._an(17, 12)))
        self.assertNotIn("bist", self.takvim.acik_seanslar(self._an(17, 9)))
        self.assertNotIn("bist", self.takvim.acik_seanslar(self._an(17, 19)))

    def test_kripto_hafta_sonu_da_acik(self):
        self.assertEqual(self.takvim.acik_seanslar(self._an(15, 12)), ["kripto"])

    def test_abd_seansi(self):
        self.assertIn("abd", self.takvim.acik_seanslar(self._an(17, 17)))
        self.assertNotIn("abd", self.takvim.acik_seanslar(self._an(17, 16)))

    def test_gorev_gun_sonu(self):
        self.assertEqual(self.takvim.gorev(self._an(17, 23, 35)), GUN_SONU)
        self.assertEqual(self.takvim.gorev(self._an(17, 23, 0)), TARAMA)

    def test_gorev_brifing_pazartesi(self):
        self.assertEqual(self.takvim.gorev(self._an(17, 9, 20)), BRIFING)
        # Cron gecikmesi brifingi dusurmemeli: bir saatlik pencere var
        self.assertEqual(self.takvim.gorev(self._an(17, 9, 55)), BRIFING)
        self.assertEqual(self.takvim.gorev(self._an(17, 10, 5)), TARAMA)
        self.assertEqual(self.takvim.gorev(self._an(18, 9, 20)), TARAMA)  # Sali

    def test_gecersiz_gunler_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "hafta_ici"):
            takvimi_coz({"seanslar": {"bist": {"gunler": "salilar"}}})

    def test_ters_seans_saatleri_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "baslangic"):
            takvimi_coz({"seanslar": {
                "bist": {"baslangic": "18:00", "bitis": "10:00"}}})


class KurAyristirmaTesti(unittest.TestCase):
    """USD getirisi ile kur getirisi CARPIMSAL birlesir."""

    def test_kur_ayristirma_carpimsal(self):
        ayrim = KurAyristirmasi("QQQ", "USD", 0.20, 0.25)
        # Toplamsal %45 der; dogrusu 1.20 x 1.25 - 1 = %50
        self.assertAlmostEqual(ayrim.toplam_tl, 0.50)
        self.assertNotAlmostEqual(ayrim.toplam_tl, 0.45)

    def test_try_varlikta_kur_getirisi_sifir(self):
        self.assertAlmostEqual(
            KurAyristirmasi("THYAO.IS", "TRY", 0.10, 0.0).toplam_tl, 0.10)

    def test_kur_maruziyeti(self):
        varliklar = {"QQQ": Varlik("QQQ", "QQQ", "nasdaq", "USD"),
                     "THYAO.IS": Varlik("THYAO.IS", "THY", "bist", "TRY")}
        portfoy = Portfoy(
            pozisyonlar=[PozisyonDegeri("QQQ", "QQQ", "nasdaq", 1, 5000, 6000),
                         PozisyonDegeri("THYAO.IS", "THY", "bist", 1, 2000, 2000)],
            nakit_try=2000.0, fiyatlanamayan=[])
        self.assertAlmostEqual(kur_maruziyeti(portfoy, varliklar), 0.60)

    def test_yerel_seri_geri_bolunerek_uretilmez(self):
        """Kur serisi ffill'li, varlik serisi degil.

        try_gecmis / kur ile yerel seriyi turetmek, BIST'in kapali oldugu gunde
        kurun tasidigi Cuma degerini yerel seriye yansitirdi ve carpimsal
        ayristirma tutmazdi.
        """
        # Gercek hafta sonu senaryosu: 15 Agustos Cumartesi. BIST kapali (NaN),
        # kripto acik. Satir dusmez cunku kriptonun verisi var.
        gunler = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-15"])
        kapanis = pd.DataFrame({"QQQ": [100.0, 110.0, np.nan],
                                "BTC-USD": [1000.0, 1010.0, 1030.0],
                                "USDTRY=X": [40.0, 41.0, 42.0]}, index=gunler)
        yapilandirma = Yapilandirma(
            ayarlar=AYARLAR, esikler=ESIKLER,
            hedef_dagilim={"nasdaq": 0.5, "kripto": 0.5},
            varliklar={"QQQ": Varlik("QQQ", "QQQ", "nasdaq", "USD"),
                       "BTC-USD": Varlik("BTC-USD", "BTC", "kripto", "USD")},
            nakit_try=0.0)
        tl, yerel, kur = _serileri_hazirla(kapanis, yapilandirma)
        self.assertEqual(len(tl), 3)
        self.assertAlmostEqual(yerel["QQQ"].iloc[0], 100.0)
        self.assertAlmostEqual(yerel["QQQ"].iloc[1], 110.0)
        # Kapali gun yerel seride NaN KALIR - ffill edilseydi Cumartesi icin
        # yapay sifir-getirili gun uretilir ve volatilite dusuk cikardi.
        self.assertTrue(pd.isna(yerel["QQQ"].iloc[2]))
        self.assertAlmostEqual(tl["QQQ"].iloc[1], 4510.0)
        self.assertAlmostEqual(kur.iloc[2], 42.0)      # kur ffill'li ve tam
        # Kriptonun Cumartesi hareketi kaybolmaz: 1030 x 42 = 43.260
        self.assertAlmostEqual(tl["BTC-USD"].iloc[2], 43_260.0)

    def test_24s_degisim_onceki_gozleme_gore(self):
        gunler = pd.to_datetime(["2026-08-13", "2026-08-14"])
        fiyatlar = FiyatVerisi(
            try_gecmis=pd.DataFrame({"A.IS": [100.0, 110.0]}, index=gunler),
            usdtry=40.0, eksik_semboller=[])
        portfoy = Portfoy(
            pozisyonlar=[PozisyonDegeri("A.IS", "A", "bist", 10, 900, 1100)],
            nakit_try=0.0, fiyatlanamayan=[])
        self.assertAlmostEqual(degisim_24s(portfoy, fiyatlar), 0.10)

    def test_tek_gozlemde_olculemez(self):
        fiyatlar = FiyatVerisi(
            try_gecmis=pd.DataFrame({"A.IS": [100.0]},
                                    index=pd.to_datetime(["2026-08-14"])),
            usdtry=40.0, eksik_semboller=[])
        self.assertIsNone(degisim_24s(
            Portfoy(pozisyonlar=[], nakit_try=100.0, fiyatlanamayan=[]), fiyatlar))


if __name__ == "__main__":
    unittest.main(verbosity=2)



