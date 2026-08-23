"""Haber arsivi testleri - tamami cevrimdisi, sahte besleme ile."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import haber_arsivi as A  # noqa: E402
from haber import Haber  # noqa: E402

SIMDI = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _rss(ogeler: list[tuple[str, str]], tarih="Sat, 22 Aug 2026 10:00:00 +0000") -> str:
    govde = "".join(
        f"<item><title>{baslik}</title><link>{link}</link>"
        f"<pubDate>{tarih}</pubDate></item>"
        for baslik, link in ogeler)
    return f"<rss version='2.0'><channel>{govde}</channel></rss>"


class YeniKayitTesti(unittest.TestCase):
    def _haber(self, baslik, link):
        return Haber(baslik=baslik, baglanti=link, kaynak="K",
                     kategori="piyasa", tarih=date(2026, 8, 22))

    def test_bos_arsive_hepsi_yazilir(self):
        haberler = [self._haber("A", "u1"), self._haber("B", "u2")]
        self.assertEqual(len(A.yeni_kayitlar(haberler, [], SIMDI)), 2)

    def test_bilinen_baglanti_tekrar_yazilmaz(self):
        mevcut = [A.ArsivKaydi("A", "u1", "K", "piyasa", "2026-08-22", "x")]
        haberler = [self._haber("A", "u1"), self._haber("B", "u2")]
        yeni = A.yeni_kayitlar(haberler, mevcut, SIMDI)
        self.assertEqual([k.baglanti for k in yeni], ["u2"])

    def test_ayni_kosuda_tekrarlanan_baglanti_bir_kez(self):
        haberler = [self._haber("A", "u1"), self._haber("A tekrar", "u1")]
        self.assertEqual(len(A.yeni_kayitlar(haberler, [], SIMDI)), 1)

    def test_anahtar_BAGLANTI_baslik_degil(self):
        """Editoryal baslik duzeltmesi kaydi COKLAMAMALI."""
        mevcut = [A.ArsivKaydi("Eski baslik", "u1", "K", "piyasa", "", "x")]
        haberler = [self._haber("Duzeltilmis baslik", "u1")]
        self.assertEqual(A.yeni_kayitlar(haberler, mevcut, SIMDI), [])

    def test_baglantisiz_haber_atlanir(self):
        self.assertEqual(A.yeni_kayitlar([self._haber("A", "")], [], SIMDI), [])

    def test_tarihsiz_haber_bos_tarihle_yazilir(self):
        """Tarihsiz baslik ELENMEZ - olcemedigimiz sey yok sayilmaz."""
        haber = Haber("A", "u1", "K", "piyasa", None)
        self.assertEqual(A.yeni_kayitlar([haber], [], SIMDI)[0].tarih, "")

    def test_ilk_gorulme_damgasi_yazilir(self):
        kayit = A.yeni_kayitlar([self._haber("A", "u1")], [], SIMDI)[0]
        self.assertEqual(kayit.ilk_gorulme, "2026-08-23T12:00:00+00:00")


class ArsivDosyasiTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.beslemeler = [{"ad": "K", "url": "http://x", "kategori": "piyasa"}]

    def _getir(self, ogeler):
        return lambda url: _rss(ogeler)

    def test_ilk_kosu_dosya_olusturur(self):
        sayi, uyarilar = A.arsivle(
            self.beslemeler, date(2026, 8, 23), SIMDI,
            getir=self._getir([("A", "u1"), ("B", "u2")]), dizin=self.dizin)
        self.assertEqual(sayi, 2)
        self.assertEqual(uyarilar, [])
        self.assertTrue(A.arsiv_dosyasi(date(2026, 8, 23), self.dizin).exists())

    def test_ikinci_kosu_ayni_icerik_yeni_kayit_yazmaz(self):
        arg = (self.beslemeler, date(2026, 8, 23), SIMDI)
        getir = self._getir([("A", "u1")])
        A.arsivle(*arg, getir=getir, dizin=self.dizin)
        sayi, _ = A.arsivle(*arg, getir=getir, dizin=self.dizin)
        self.assertEqual(sayi, 0)

    def test_ikinci_kosu_yeni_baslik_ekler_eskisini_korur(self):
        arg = (self.beslemeler, date(2026, 8, 23), SIMDI)
        A.arsivle(*arg, getir=self._getir([("A", "u1")]), dizin=self.dizin)
        A.arsivle(*arg, getir=self._getir([("A", "u1"), ("B", "u2")]),
                  dizin=self.dizin)
        kayitlar = A.arsivi_oku(A.arsiv_dosyasi(date(2026, 8, 23), self.dizin))
        self.assertEqual(sorted(k.baglanti for k in kayitlar), ["u1", "u2"])

    def test_gidis_donus_bozulmaz(self):
        kayitlar = [A.ArsivKaydi("Türkçe başlık: %5 artış", "u1", "K",
                                 "piyasa", "2026-08-22", "2026-08-23T12:00:00")]
        dosya = self.dizin / "t.yaml"
        A.arsivi_yaz(kayitlar, dosya)
        self.assertEqual(A.arsivi_oku(dosya), kayitlar)

    def test_dusen_besleme_uyari_verir_kosuyu_kirmaz(self):
        """Haber baglamdir; bir beslemenin hickirigi kosuyu kirmamali."""
        def patlayan(url):
            raise __import__("haber").HaberHatasi("baglanti yok")
        sayi, uyarilar = A.arsivle(self.beslemeler, date(2026, 8, 23), SIMDI,
                                   getir=patlayan, dizin=self.dizin)
        self.assertEqual(sayi, 0)
        self.assertEqual(len(uyarilar), 1)

    def test_gun_basina_ayri_dosya(self):
        self.assertNotEqual(A.arsiv_dosyasi(date(2026, 8, 23), self.dizin),
                            A.arsiv_dosyasi(date(2026, 8, 24), self.dizin))


class TavanTesti(unittest.TestCase):
    def test_arsiv_tavani_ozet_tavanindan_YUKSEK(self):
        """Ozet okunabilir kalmali, arsivin boyle bir derdi yok."""
        from config import HaberAyarlari
        self.assertGreater(A.ARSIV_BESLEME_BASINA,
                           HaberAyarlari().besleme_basina)

    def test_tavan_sinirsiz_degil(self):
        """Bozuk besleme binlerce oge dondurse gunluk dosya sismesin."""
        self.assertLess(A.ARSIV_BESLEME_BASINA, 200)


class HaberArsiviIzolasyonTesti(unittest.TestCase):
    """Arsiv karar yoluna baglanmaz - haber baglamdir, sinyal kaynagi degil."""

    def _kaynak(self, ad):
        return (Path(__file__).resolve().parent / ad).read_text(encoding="utf-8")

    def test_main_arsivi_import_etmez(self):
        self.assertNotIn("import haber_arsivi", self._kaynak("main.py"))

    def test_sinyal_arsivi_import_etmez(self):
        self.assertNotIn("import haber_arsivi", self._kaynak("sinyal.py"))

    def test_arsiv_sinyal_uretmez(self):
        kaynak = self._kaynak("haber_arsivi.py")
        for yasak in ("import sinyal", "import main", "gonder_islem_karari"):
            self.assertNotIn(yasak, kaynak)


if __name__ == "__main__":
    unittest.main()
