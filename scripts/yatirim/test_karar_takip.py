"""Karar sonuc takibi testleri. Cevrimdisi, sentetik veri."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Ayarlar, Esikler, Varlik, Yapilandirma
from fetch import FiyatVerisi
from karar_takip import (
    KONTROL_GUNLERI,
    Karar,
    _fiyat_o_gun,
    _portfoy_degeri,
    eksik_olcumleri_tamamla,
    kararlari_oku,
    olcum_yap,
    olcumleri_oku,
    olcumleri_yaz,
)
from ledger import islemleri_oku

AYARLAR = Ayarlar(kur_sembolu="USDTRY=X", gecmis_gun=365, islem_gunu_yil=252)
ESIKLER = Esikler(rebalancing_sapma=0.03, risk_katkisi_ust=0.20)


def gecici(icerik: str, ad: str) -> Path:
    dosya = Path(tempfile.mkdtemp()) / ad
    dosya.write_text(icerik, encoding="utf-8")
    return dosya


class FiyatOGunTesti(unittest.TestCase):
    def _seri(self) -> pd.Series:
        gunler = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
        return pd.Series([100.0, 110.0, 120.0], index=gunler)

    def test_tam_gun_esleseni_alir(self):
        self.assertEqual(_fiyat_o_gun(self._seri(), date(2026, 1, 2)), 110.0)

    def test_piyasa_kapaliysa_onceki_gunu_alir(self):
        # 3-4 Ocak veri yok -> 2 Ocak fiyati kullanilmali
        self.assertEqual(_fiyat_o_gun(self._seri(), date(2026, 1, 4)), 110.0)

    def test_seriden_once_ise_none(self):
        self.assertIsNone(_fiyat_o_gun(self._seri(), date(2025, 12, 31)))

    def test_serinin_sonrasi_son_fiyati_verir(self):
        self.assertEqual(_fiyat_o_gun(self._seri(), date(2026, 6, 1)), 120.0)


class GecmiseDonukOlcumTesti(unittest.TestCase):
    """Sistem kapali kalsa bile kacan kontrol gunleri geriye donuk dolmali."""

    def setUp(self):
        self.karar_gunu = date.today() - timedelta(days=40)
        gunler = pd.date_range(self.karar_gunu - timedelta(days=5),
                               periods=60, freq="D")
        # SATILAN duz gider, ALINAN istikrarli yukselir -> takas farki pozitif
        self.gecmis = pd.DataFrame(
            {
                "SATILAN.IS": np.full(60, 100.0),
                "ALINAN.IS": np.linspace(100.0, 160.0, 60),
            },
            index=gunler,
        )
        self.fiyatlar = FiyatVerisi(try_gecmis=self.gecmis, usdtry=40.0,
                                    eksik_semboller=[])
        self.yapilandirma = Yapilandirma(
            ayarlar=AYARLAR, esikler=ESIKLER,
            hedef_dagilim={"bist": 1.0},
            varliklar={
                "SATILAN.IS": Varlik("SATILAN.IS", "S", "bist", "TRY"),
                "ALINAN.IS": Varlik("ALINAN.IS", "A", "bist", "TRY"),
            },
            nakit_try=0.0, pozisyonlar=[],
        )
        defter = gecici(
            "baslangic_nakit_try: 10000\nkomisyon_orani: 0.0\nislemler:\n"
            f"  - {{tarih: {self.karar_gunu.isoformat()}, yon: AL, "
            "sembol: ALINAN.IS, adet: 50, fiyat_try: 105}\n",
            "islemler.yaml")
        self.islemler, self.nakit, self.komisyon = islemleri_oku(defter)
        self.karar = Karar(
            id="test-takas", tarih=self.karar_gunu.isoformat(), tip="TAKAS",
            ozet="test", beklenti="test",
            satilan=["SATILAN.IS"], alinan=["ALINAN.IS"],
        )

    def test_tum_kontrol_gunleri_geriye_donuk_dolar(self):
        yeni = eksik_olcumleri_tamamla(
            [self.karar], [], self.yapilandirma, self.fiyatlar,
            self.islemler, self.komisyon, self.nakit)
        self.assertEqual([o.gun for o in yeni], list(KONTROL_GUNLERI))

    def test_olcum_esik_tetiklenmese_de_fiyat_kaydeder(self):
        """Kritik: eski bot vadesi dolanlarin fiyatini NULL birakmisti."""
        olcum = olcum_yap(self.karar, 10, self.yapilandirma, self.fiyatlar,
                          self.islemler, self.komisyon, self.nakit)
        self.assertIsNotNone(olcum)
        self.assertIn("SATILAN.IS", olcum.fiyatlar)   # hic hareket etmedi, yine kayitli
        self.assertIn("ALINAN.IS", olcum.fiyatlar)
        self.assertAlmostEqual(olcum.getiriler["SATILAN.IS"], 0.0, places=6)
        self.assertGreater(olcum.getiriler["ALINAN.IS"], 0.0)

    def test_getiri_karar_gununden_olculur(self):
        """Getiri serinin basindan degil KARAR GUNUNDEN olculmeli.

        Seri karar gununden 5 gun ONCE basliyor; taban fiyat 100 degil,
        karar gunundeki fiyat (100 + 5 adim).
        """
        olcum = olcum_yap(self.karar, 30, self.yapilandirma, self.fiyatlar,
                          self.islemler, self.komisyon, self.nakit)
        adim = 60.0 / 59                  # 100 -> 160, 60 gozlem
        taban = 100 + 5 * adim            # karar gunu (seri basindan 5 gun sonra)
        beklenen = (taban + 30 * adim) / taban - 1
        self.assertAlmostEqual(olcum.getiriler["ALINAN.IS"], beklenen, places=4)

    def test_zaten_olculmus_gun_tekrar_olculmez(self):
        ilk = eksik_olcumleri_tamamla(
            [self.karar], [], self.yapilandirma, self.fiyatlar,
            self.islemler, self.komisyon, self.nakit)
        ikinci = eksik_olcumleri_tamamla(
            [self.karar], ilk, self.yapilandirma, self.fiyatlar,
            self.islemler, self.komisyon, self.nakit)
        self.assertEqual(ikinci, [])

    def test_vadesi_gelmemis_gun_olculmez(self):
        yeni_karar = Karar(
            id="dun", tarih=(date.today() - timedelta(days=1)).isoformat(),
            tip="ACILIS", ozet="", beklenti="", satilan=[], alinan=[])
        yeni = eksik_olcumleri_tamamla(
            [yeni_karar], [], self.yapilandirma, self.fiyatlar,
            self.islemler, self.komisyon, self.nakit)
        self.assertEqual(yeni, [])

    def test_portfoy_degeri_defteri_o_gune_kadar_oynatir(self):
        # Karar gununden ONCE pozisyon yok -> None donmeli
        onceki = _portfoy_degeri(
            self.yapilandirma, self.fiyatlar, self.islemler, self.komisyon,
            self.nakit, self.karar_gunu - timedelta(days=3))
        self.assertIsNone(onceki)
        # Karar gununde pozisyon var
        sonraki = _portfoy_degeri(
            self.yapilandirma, self.fiyatlar, self.islemler, self.komisyon,
            self.nakit, self.karar_gunu)
        self.assertIsNotNone(sonraki)


class DiskYuvarlakSeferTesti(unittest.TestCase):
    def test_olcumler_yazilip_ayni_sekilde_okunur(self):
        from karar_takip import Olcum
        dosya = Path(tempfile.mkdtemp()) / "olcum.yaml"
        olcum = Olcum(karar_id="k1", gun=5, olcum_tarihi="2026-01-06",
                      portfoy_degeri=20000.0, portfoy_getirisi=0.015,
                      fiyatlar={"A.IS": 123.45}, getiriler={"A.IS": 0.0234})
        olcumleri_yaz([olcum], dosya)
        geri = olcumleri_oku(dosya)
        self.assertEqual(len(geri), 1)
        self.assertEqual(geri[0].karar_id, "k1")
        self.assertAlmostEqual(geri[0].portfoy_getirisi, 0.015)
        self.assertAlmostEqual(geri[0].getiriler["A.IS"], 0.0234)

    def test_dosya_yoksa_bos_liste(self):
        self.assertEqual(olcumleri_oku(Path("olmayan-dosya.yaml")), [])
        self.assertEqual(kararlari_oku(Path("olmayan-dosya.yaml")), [])


class GercekKararDosyasiTesti(unittest.TestCase):
    def test_kararlar_yaml_okunabiliyor(self):
        kararlar = kararlari_oku()
        self.assertGreater(len(kararlar), 0)
        for karar in kararlar:
            self.assertTrue(karar.beklenti, f"{karar.id}: beklenti bos olamaz")
            self.assertRegex(karar.tarih, r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
