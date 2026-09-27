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
    BozanKosul,
    Karar,
    Olcum,
    kosul_durumu,
    rapor_olustur,
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
        self.islemler, self.nakit, self.komisyon, _ = islemleri_oku(defter)
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


def _olcum(gun: int, portfoy: float = 0.0, getiriler=None) -> Olcum:
    return Olcum(karar_id="k", gun=gun, olcum_tarihi="2026-10-01",
                 portfoy_degeri=20_000.0, portfoy_getirisi=portfoy,
                 fiyatlar={}, getiriler=getiriler or {})


class BozanKosulTesti(unittest.TestCase):
    """bozan_kosul: yazim hatasi okumada patlar, veri yoksa 'tutuyor' denmez,
    ilk tetiklenme kalicidir."""

    def _yaml(self, kosul: str, tarih: str = "2026-10-01",
              alinan: str = "[TUPRS.IS]", satilan: str = "[GARAN.IS]") -> Path:
        return gecici(
            "kararlar:\n"
            f"  - id: k\n    tarih: {tarih}\n    tip: TAKAS\n"
            f"    beklenti: x\n    alinan: {alinan}\n    satilan: {satilan}\n"
            + kosul, "kararlar.yaml")

    def test_yeni_kararda_zorunlu(self):
        with self.assertRaisesRegex(ValueError, "zorunlu"):
            kararlari_oku(self._yaml(""))

    def test_eski_karar_muaf(self):
        # Sonucu gorulmus karara sonradan kosul yazilmaz.
        self.assertIsNone(kararlari_oku(self._yaml("", tarih="2026-08-13"))[0].bozan_kosul)

    def test_gecerli_kosul_okunur(self):
        karar = kararlari_oku(self._yaml(
            "    bozan_kosul:\n      olcut: takas_farki\n      yon: alti\n"
            "      esik: -0.05\n"))[0]
        self.assertEqual(karar.bozan_kosul,
                         BozanKosul("takas_farki", "alti", -0.05))

    def test_yuzde_yazilan_esik_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "KESIR"):
            kararlari_oku(self._yaml(
                "    bozan_kosul:\n      olcut: portfoy_getirisi\n"
                "      yon: alti\n      esik: -5\n"))

    def test_listede_olmayan_sembol_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "alinan/satilan"):
            kararlari_oku(self._yaml(
                "    bozan_kosul:\n      olcut: getiri:ASELS.IS\n"
                "      yon: alti\n      esik: -0.1\n"))

    def test_gecersiz_olcut_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "olcut gecersiz"):
            kararlari_oku(self._yaml(
                "    bozan_kosul:\n      olcut: volatilite\n"
                "      yon: ustu\n      esik: 0.3\n"))

    def test_takassiz_kararda_takas_farki_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "alinan VE satilan"):
            kararlari_oku(self._yaml(
                "    bozan_kosul:\n      olcut: takas_farki\n"
                "      yon: alti\n      esik: -0.05\n", satilan="[]"))

    def _karar(self, kosul: BozanKosul) -> Karar:
        return Karar(id="k", tarih="2026-10-01", tip="TAKAS", ozet="", beklenti="",
                     satilan=["GARAN.IS"], alinan=["TUPRS.IS"], bozan_kosul=kosul)

    def test_ilk_tetiklenme_kalici(self):
        karar = self._karar(BozanKosul("takas_farki", "alti", -0.05))
        olcumler = [
            _olcum(5, getiriler={"TUPRS.IS": 0.0, "GARAN.IS": 0.02}),
            _olcum(10, getiriler={"TUPRS.IS": -0.04, "GARAN.IS": 0.03}),  # -7%
            _olcum(15, getiriler={"TUPRS.IS": 0.10, "GARAN.IS": 0.0}),    # toparlandi
        ]
        durum = kosul_durumu(karar, olcumler)
        self.assertIn("TEZ BOZULDU", durum)
        self.assertIn("10. gunde", durum)

    def test_tetiklenmedi(self):
        karar = self._karar(BozanKosul("portfoy_getirisi", "alti", -0.05))
        self.assertIn("Tez tutuyor", kosul_durumu(karar, [_olcum(5, -0.01)]))

    def test_eksik_veri_tutuyor_sayilmaz(self):
        # takas_farki eksik sembolu 0 sayarsa kosul sessizce "tutuyor" derdi.
        karar = self._karar(BozanKosul("takas_farki", "alti", -0.05))
        durum = kosul_durumu(karar, [_olcum(5, getiriler={"TUPRS.IS": -0.2})])
        self.assertIn("Olculemedi", durum)

    def test_raporda_gorunur(self):
        karar = self._karar(BozanKosul("getiri:TUPRS.IS", "alti", -0.1, "dip"))
        rapor = rapor_olustur([karar], [
            Olcum("k", 5, "2026-10-06", 20_000.0, 0.0, {}, {"TUPRS.IS": -0.12})])
        self.assertIn("*Bozan kosul:* TUPRS.IS getirisi -10.0% altina inerse tez bozulur - dip", rapor)
        self.assertIn("-12.0% ❌", rapor)
        self.assertIn("TEZ BOZULDU", rapor)


class RiskKosuluTesti(unittest.TestCase):
    """volatilite / risk_katkisi: raporla ayni yontem, o gunku pozisyonlar."""

    def setUp(self):
        self.karar_gunu = date.today() - timedelta(days=40)
        gunler = pd.date_range(self.karar_gunu - timedelta(days=200),
                               periods=240, freq="D")
        rng = np.random.default_rng(7)
        seri = lambda vol: 100 * np.cumprod(1 + rng.normal(0, vol, 240))  # noqa: E731
        self.fiyatlar = FiyatVerisi(
            try_gecmis=pd.DataFrame({"A.IS": seri(0.02), "B.IS": seri(0.01),
                                     "QQQ": seri(0.015)}, index=gunler),
            usdtry=40.0, eksik_semboller=[])
        self.yapilandirma = Yapilandirma(
            ayarlar=AYARLAR, esikler=ESIKLER,
            hedef_dagilim={"bist": 0.5, "nasdaq": 0.5},
            varliklar={"A.IS": Varlik("A.IS", "A", "bist", "TRY"),
                       "B.IS": Varlik("B.IS", "B", "bist", "TRY"),
                       "QQQ": Varlik("QQQ", "Q", "nasdaq", "TRY")},
            nakit_try=0.0, pozisyonlar=[])
        # Tek pozisyon (A) + nakit: portfoy vol = agirlik x A vol, A katkisi 1.
        defter = gecici(
            "baslangic_nakit_try: 10000\nkomisyon_orani: 0.0\nislemler:\n"
            f"  - {{tarih: {self.karar_gunu.isoformat()}, yon: AL, "
            "sembol: A.IS, adet: 10, fiyat_try: 100}\n", "islemler.yaml")
        self.islemler, self.nakit, self.komisyon, _ = islemleri_oku(defter)

    def _karar(self, olcut: str, yon: str = "ustu", esik: float = 0.9) -> Karar:
        return Karar(id="r", tarih=self.karar_gunu.isoformat(), tip="ALIS",
                     ozet="", beklenti="", satilan=[], alinan=["A.IS"],
                     bozan_kosul=BozanKosul(olcut, yon, esik))

    def _olc(self, olcut: str, gun: int = 10) -> Olcum:
        return olcum_yap(self._karar(olcut), gun, self.yapilandirma, self.fiyatlar,
                         self.islemler, self.komisyon, self.nakit)

    def _a_vol(self, gun: int) -> float:
        olcum = self._olc("volatilite:A.IS", gun)
        return olcum.kosul_degeri

    def test_portfoy_volatilitesi_agirlikla_olcekli(self):
        olcum = self._olc("volatilite:portfoy")
        o_gun = self.karar_gunu + timedelta(days=10)
        fiyat = float(self.fiyatlar.try_gecmis["A.IS"][:pd.Timestamp(o_gun)].iloc[-1])
        agirlik = 10 * fiyat / (10 * fiyat + self.nakit - 1000)
        self.assertAlmostEqual(olcum.kosul_degeri, agirlik * self._a_vol(10), places=6)

    def test_sinif_bacagi_nakitsiz(self):
        # BIST bacaginda yalnizca A var -> bacak vol = A vol (nakit seyreltmez).
        self.assertAlmostEqual(self._olc("volatilite:bist").kosul_degeri,
                               self._a_vol(10), places=6)

    def test_tek_pozisyonun_risk_katkisi_tam(self):
        self.assertAlmostEqual(self._olc("risk_katkisi:A.IS").kosul_degeri, 1.0, places=6)

    def test_pozisyonu_olmayan_sinif_olculemez(self):
        self.assertIsNone(self._olc("volatilite:nasdaq").kosul_degeri)

    def test_karar_gunu_de_olculur_ve_saklanir(self):
        karar = self._karar("volatilite:bist")
        yeni = eksik_olcumleri_tamamla([karar], [], self.yapilandirma, self.fiyatlar,
                                       self.islemler, self.komisyon, self.nakit)
        self.assertEqual(yeni[0].gun, 0)
        self.assertIsNotNone(yeni[0].kosul_degeri)
        dosya = Path(tempfile.mkdtemp()) / "olcum.yaml"
        olcumleri_yaz(yeni, dosya)
        self.assertEqual([o.kosul_degeri for o in olcumleri_oku(dosya)],
                         [round(o.kosul_degeri, 6) for o in yeni])

    def test_karar_gunu_saglanan_kosul_anlamsiz(self):
        karar = self._karar("volatilite:bist", yon="ustu", esik=0.01)
        olcumler = [Olcum("r", 0, "x", 1.0, 0.0, {}, {}, kosul_degeri=0.30),
                    Olcum("r", 5, "x", 1.0, 0.0, {}, {}, kosul_degeri=0.31)]
        self.assertIn("Kosul anlamsiz", kosul_durumu(karar, olcumler))

    def test_tutuyor_mesaji_karar_gununu_ve_mesafeyi_verir(self):
        olcumler = [Olcum("r", 0, "x", 1.0, 0.0, {}, {}, kosul_degeri=0.292),
                    Olcum("r", 20, "x", 1.0, 0.0, {}, {}, kosul_degeri=0.265)]
        karar = self._karar("volatilite:bist", yon="ustu", esik=0.30)
        self.assertEqual(
            kosul_durumu(karar, olcumler),
            "✅ **Tez tutuyor** - BIST bacaginin volatilitesi: karar gunu 29.2% → "
            "20. gun 26.5%. Sinir 30.0%, araya 3.5 puan var.")

    def test_dogrulama(self):
        def oku(olcut, esik="0.3"):
            return kararlari_oku(gecici(
                "kararlar:\n  - id: r\n    tarih: 2026-10-01\n    alinan: [A.IS]\n"
                f"    bozan_kosul: {{olcut: '{olcut}', yon: ustu, esik: {esik}}}\n",
                "k.yaml"), siniflar={"bist", "nasdaq"})
        self.assertIsNotNone(oku("volatilite:portfoy")[0].bozan_kosul)
        self.assertIsNotNone(oku("volatilite:bist")[0].bozan_kosul)
        self.assertIsNotNone(oku("risk_katkisi:A.IS")[0].bozan_kosul)
        with self.assertRaisesRegex(ValueError, "varlik sinifi"):
            oku("volatilite:kripto")
        with self.assertRaisesRegex(ValueError, "alinan/satilan"):
            oku("risk_katkisi:B.IS")
        with self.assertRaisesRegex(ValueError, "pozitif"):
            oku("volatilite:bist", esik="-0.1")
