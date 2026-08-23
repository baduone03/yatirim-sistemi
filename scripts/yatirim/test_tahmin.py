"""Ongoru defteri testleri - tamami cevrimdisi, sentetik fiyat serisiyle."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tahmin as T  # noqa: E402


def _gecmis(seriler: dict[str, list[float]], baslangic="2026-08-01") -> pd.DataFrame:
    gunler = pd.date_range(baslangic, periods=len(next(iter(seriler.values()))))
    return pd.DataFrame(seriler, index=gunler)


def _tahmin(**degisiklik) -> T.Tahmin:
    alanlar = dict(id="t1", tarih="2026-08-01", ufuk_gun=5, olasilik=0.6,
                   tip="esik_asar", sembol="A.IS", esik=0.0, kiyas="",
                   gerekce="", dayanak="")
    alanlar.update(degisiklik)
    return T.Tahmin(**alanlar)


class KayitDogrulamaTesti(unittest.TestCase):
    """Olculemeyen kayit GIRISTE reddedilir - sessizce atlanmaz.

    Sessiz atlama defteri sessizce kirletirdi: karne n=40 der ama
    12 tanesi hic olculmemis olurdu.
    """

    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())

    def _oku(self, kayit):
        dosya = self.dizin / "t.yaml"
        dosya.write_text(yaml.safe_dump({"tahminler": [kayit]}), encoding="utf-8")
        return T.tahminleri_oku(dosya)

    def _gecerli(self):
        return {"id": "x", "tarih": "2026-08-01", "ufuk_gun": 5,
                "olasilik": 0.6, "tip": "esik_asar", "sembol": "A.IS", "esik": 0.0}

    def test_gecerli_kayit_okunur(self):
        self.assertEqual(len(self._oku(self._gecerli())), 1)

    def test_serbest_metin_tipi_reddedilir(self):
        with self.assertRaises(T.TahminHatasi):
            self._oku(self._gecerli() | {"tip": "piyasa_iyi_olacak"})

    def test_olasilik_1_reddedilir(self):
        """Kesinlik iddiasi olculemez ve Brier skorunu bozar."""
        with self.assertRaises(T.TahminHatasi):
            self._oku(self._gecerli() | {"olasilik": 1.0})

    def test_olasilik_0_reddedilir(self):
        with self.assertRaises(T.TahminHatasi):
            self._oku(self._gecerli() | {"olasilik": 0.0})

    def test_gecer_tipi_kiyassiz_reddedilir(self):
        kayit = self._gecerli() | {"tip": "gecer"}
        kayit.pop("esik")
        with self.assertRaises(T.TahminHatasi):
            self._oku(kayit)

    def test_esik_asar_esiksiz_reddedilir(self):
        kayit = self._gecerli()
        kayit.pop("esik")
        with self.assertRaises(T.TahminHatasi):
            self._oku(kayit)

    def test_tekrarlanan_id_reddedilir(self):
        dosya = self.dizin / "t.yaml"
        dosya.write_text(yaml.safe_dump(
            {"tahminler": [self._gecerli(), self._gecerli()]}), encoding="utf-8")
        with self.assertRaises(T.TahminHatasi):
            T.tahminleri_oku(dosya)


class OlcumTesti(unittest.TestCase):
    def test_yukselen_fiyat_esik_asar_tutar(self):
        gecmis = _gecmis({"A.IS": [100, 101, 102, 103, 104, 110]})
        sonuc = T.olc(_tahmin(esik=0.05), gecmis)
        self.assertTrue(sonuc.tuttu)
        self.assertAlmostEqual(sonuc.getiri, 0.10)

    def test_esigin_altinda_kalan_tutmaz(self):
        gecmis = _gecmis({"A.IS": [100, 100, 100, 100, 100, 102]})
        self.assertFalse(T.olc(_tahmin(esik=0.05), gecmis).tuttu)

    def test_gecer_tipi_goreli_olculur(self):
        """Iki sembol de duserse bile gecen taraf DOGRU sayilir."""
        gecmis = _gecmis({"A.IS": [100, 100, 100, 100, 100, 95],
                          "B.IS": [100, 100, 100, 100, 100, 90]})
        sonuc = T.olc(_tahmin(tip="gecer", kiyas="B.IS"), gecmis)
        self.assertTrue(sonuc.tuttu)
        self.assertAlmostEqual(sonuc.getiri, -0.05)
        self.assertAlmostEqual(sonuc.kiyas_getirisi, -0.10)

    def test_fiyat_yoksa_YANLIS_degil_NONE(self):
        """Bizim korlugumuz, ongorunun tutmadigi anlamina gelmez."""
        self.assertIsNone(T.olc(_tahmin(), _gecmis({"B.IS": [1, 2, 3, 4, 5, 6]})))

    def test_kiyas_fiyati_yoksa_olcum_ertelenir(self):
        gecmis = _gecmis({"A.IS": [100, 100, 100, 100, 100, 110]})
        self.assertIsNone(T.olc(_tahmin(tip="gecer", kiyas="YOK.IS"), gecmis))

    def test_piyasa_kapaliysa_onceki_gun_fiyati(self):
        """Vade gunu tatilse seri kisa kalir; son bilinen fiyat kullanilir."""
        gecmis = _gecmis({"A.IS": [100, 110]})
        self.assertAlmostEqual(T.olc(_tahmin(esik=0.0), gecmis).getiri, 0.10)

    def test_vadesi_dolmayan_olculmez(self):
        gecmis = _gecmis({"A.IS": [100, 110]})
        yeni = T.vadesi_dolanlari_olc([_tahmin()], [], gecmis, date(2026, 8, 3))
        self.assertEqual(yeni, [])

    def test_ayni_tahmin_iki_kez_olculmez(self):
        gecmis = _gecmis({"A.IS": [100, 101, 102, 103, 104, 110]})
        mevcut = [T.Sonuc("t1", "2026-08-06", True, 0.10, None)]
        yeni = T.vadesi_dolanlari_olc([_tahmin()], mevcut, gecmis, date(2026, 8, 10))
        self.assertEqual(yeni, [])


class KarneTesti(unittest.TestCase):
    def _cift(self, n, olasilik, tutan):
        tahminler = [_tahmin(id=f"t{i}", olasilik=olasilik) for i in range(n)]
        sonuclar = [T.Sonuc(f"t{i}", "2026-08-06", i < tutan, 0.0, None)
                    for i in range(n)]
        return tahminler, sonuclar

    def test_hep_yuzde_50_demek_brier_0_25_verir(self):
        karne = T.karne_hesapla(*self._cift(10, 0.5, 5))
        self.assertAlmostEqual(karne.brier, 0.25)

    def test_isabet_orani_dogru(self):
        karne = T.karne_hesapla(*self._cift(10, 0.6, 7))
        self.assertEqual(karne.isabet, 7)
        self.assertAlmostEqual(karne.isabet_orani, 0.7)

    def test_kotu_kalibrasyon_taban_orani_gecemez(self):
        """Hep %90 deyip %30 tutturmak taban orandan kotu Brier verir."""
        karne = T.karne_hesapla(*self._cift(10, 0.9, 3))
        self.assertGreater(karne.brier, karne.brier_referans)

    def test_sonucsuz_karne_none(self):
        self.assertIsNone(T.karne_hesapla([_tahmin()], []))

    def test_olculmemis_tahmin_karneye_girmez(self):
        tahminler = [_tahmin(id="t1"), _tahmin(id="t2")]
        sonuclar = [T.Sonuc("t1", "2026-08-06", True, 0.1, None)]
        self.assertEqual(T.karne_hesapla(tahminler, sonuclar).n, 1)

    def test_kalibrasyon_kovalari(self):
        tahminler = [_tahmin(id="a", olasilik=0.1), _tahmin(id="b", olasilik=0.9)]
        sonuclar = [T.Sonuc("a", "2026-08-06", False, 0.0, None),
                    T.Sonuc("b", "2026-08-06", True, 0.0, None)]
        kovalar = T.kalibrasyon(tahminler, sonuclar)
        self.assertEqual(len(kovalar), 2)
        self.assertEqual(kovalar[0][3], 0.0)    # %0-20 kovasi hic tutmadi
        self.assertEqual(kovalar[-1][3], 1.0)   # %80-100 kovasi hep tuttu


class HukumEsigiTesti(unittest.TestCase):
    """Az gozlemle hukum verilmez - sistemin en kolay yalan soyleyecegi yer."""

    def _karne_metni(self, n):
        tahminler = [_tahmin(id=f"t{i}") for i in range(n)]
        sonuclar = [T.Sonuc(f"t{i}", "2026-08-06", True, 0.1, None) for i in range(n)]
        return T.karne_raporu(tahminler, sonuclar, date(2026, 8, 10))

    def test_az_gozlemde_hukum_yok_yazar(self):
        self.assertIn("Hukum yok", self._karne_metni(5))

    def test_otuz_gozlemde_egilim_yazar(self):
        metin = self._karne_metni(T.EGILIM_N)
        self.assertIn("Egilim", metin)
        self.assertNotIn("Hukum yok", metin)

    def test_yuz_gozlemde_isaret_yazar(self):
        self.assertIn("Isaret", self._karne_metni(T.ISARET_N))


class IzolasyonTesti(unittest.TestCase):
    """Ongoru defteri karar yoluna BAGLANMAZ.

    Bir ongoruye dayanarak pozisyon acmak, kalibre oldugu kanitlanmamis
    bir modele para baglamaktir. Kural yorumda kalirsa unutulur; burada
    her kosuda dogrulanir.
    """

    def _kaynak(self, ad):
        return (Path(__file__).resolve().parent / ad).read_text(encoding="utf-8")

    def test_main_tahmin_modulunu_import_etmez(self):
        self.assertNotIn("import tahmin", self._kaynak("main.py"))

    def test_sinyal_tahmin_modulunu_import_etmez(self):
        self.assertNotIn("import tahmin", self._kaynak("sinyal.py"))

    def test_tahmin_sinyal_uretmez(self):
        kaynak = self._kaynak("tahmin.py")
        for yasak in ("import sinyal", "import main", "gonder_islem_karari"):
            self.assertNotIn(yasak, kaynak)


class DefterDosyasiTesti(unittest.TestCase):
    def test_gercek_defter_ayristirilabilir(self):
        """Ornekler yorumda; ciplak yazilirsa defter onlari gercek sanar."""
        self.assertEqual(T.tahminleri_oku(), [])


if __name__ == "__main__":
    unittest.main()
