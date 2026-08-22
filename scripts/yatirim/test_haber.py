"""Haber beslemesi testleri. Tamami CEVRIMDISI - sahte getirici kullanir."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from haber import (
    Haber,
    HaberHatasi,
    beslemeyi_coz,
    haberleri_topla,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Ornek</title>
  <item>
    <title>TCMB faizi sabit tuttu</title>
    <link>https://ornek/1</link>
    <pubDate>Fri, 21 Aug 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Eski haber</title>
    <link>https://ornek/2</link>
    <pubDate>Fri, 01 Aug 2026 09:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Bitcoin 70 bin dolari asti</title>
    <link href="https://ornek/atom1"/>
    <updated>2026-08-21T12:00:00Z</updated>
  </entry>
</feed>"""

TARIHSIZ = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Tarihsiz baslik</title><link>https://ornek/3</link></item>
</channel></rss>"""

BUGUN = date(2026, 8, 22)


class AyristirmaTesti(unittest.TestCase):
    def test_rss_ogeleri_cozulur(self):
        haberler = beslemeyi_coz(RSS, "Ornek", "makro")
        self.assertEqual(len(haberler), 2)
        self.assertEqual(haberler[0].baslik, "TCMB faizi sabit tuttu")
        self.assertEqual(haberler[0].baglanti, "https://ornek/1")
        self.assertEqual(haberler[0].tarih, date(2026, 8, 21))
        self.assertEqual(haberler[0].kategori, "makro")

    def test_atom_ogeleri_cozulur(self):
        """Atom farkli isim alani VE baglantiyi href niteliginde tasir."""
        haberler = beslemeyi_coz(ATOM, "Ornek", "kripto")
        self.assertEqual(len(haberler), 1)
        self.assertEqual(haberler[0].baslik, "Bitcoin 70 bin dolari asti")
        self.assertEqual(haberler[0].baglanti, "https://ornek/atom1")
        self.assertEqual(haberler[0].tarih, date(2026, 8, 21))

    def test_bozuk_xml_anlamli_hata(self):
        with self.assertRaises(HaberHatasi):
            beslemeyi_coz("<rss><channel>", "Ornek", "genel")

    def test_tarihsiz_haber_BUGUN_sayilmaz(self):
        """Tarihsiz basligi guncel varsaymak, bayat fiyat tuzaginin ta kendisi."""
        haberler = beslemeyi_coz(TARIHSIZ, "Ornek", "genel")
        self.assertTrue(haberler[0].tarihsiz)
        self.assertIsNone(haberler[0].tarih)

    def test_basliksiz_oge_elenir(self):
        bos = '<?xml version="1.0"?><rss><channel><item><link>x</link></item></channel></rss>'
        self.assertEqual(beslemeyi_coz(bos, "Ornek", "genel"), [])


class ToplamaTesti(unittest.TestCase):
    def _getir(self, esleme):
        def sahte(url):
            if url not in esleme:
                raise HaberHatasi(f"{url} yok")
            return esleme[url]
        return sahte

    def test_eski_haber_suzulur(self):
        haberler, _ = haberleri_topla(
            [{"ad": "Ornek", "url": "a", "kategori": "makro"}],
            getir=self._getir({"a": RSS}), bugun=BUGUN, azami_gun=2)
        self.assertEqual([h.baslik for h in haberler],
                         ["TCMB faizi sabit tuttu"])

    def test_tarihsiz_haber_ELENMEZ(self):
        """Olcemedigimiz seyi yok saymak, olcmus gibi davranmak kadar yanlis."""
        haberler, _ = haberleri_topla(
            [{"ad": "Ornek", "url": "a", "kategori": "genel"}],
            getir=self._getir({"a": TARIHSIZ}), bugun=BUGUN)
        self.assertEqual(len(haberler), 1)
        self.assertTrue(haberler[0].tarihsiz)

    def test_dusen_besleme_digerlerini_DURDURMAZ(self):
        """OLCULEMEDI != DURDUR ayriminin haber tarafindaki karsiligi."""
        haberler, uyarilar = haberleri_topla(
            [{"ad": "Calisan", "url": "a", "kategori": "makro"},
             {"ad": "Cokmus", "url": "yok", "kategori": "kripto"}],
            getir=self._getir({"a": RSS}), bugun=BUGUN)
        self.assertEqual(len(haberler), 1)
        self.assertTrue(any("Cokmus okunamadi" in u for u in uyarilar))

    def test_hepsi_bayatsa_uyari_dusuyor(self):
        haberler, uyarilar = haberleri_topla(
            [{"ad": "Ornek", "url": "a", "kategori": "makro"}],
            getir=self._getir({"a": RSS}), bugun=date(2026, 9, 30))
        self.assertEqual(haberler, [])
        self.assertTrue(any("gunden eski" in u for u in uyarilar))

    def test_besleme_basina_tavan(self):
        """Tek yuksek hacimli kaynak ozeti ele gecirmemeli."""
        cok = ('<?xml version="1.0"?><rss><channel>'
               + "".join(f"<item><title>H{i}</title><link>l</link></item>"
                         for i in range(50))
               + "</channel></rss>")
        haberler, _ = haberleri_topla(
            [{"ad": "Ornek", "url": "a", "kategori": "kripto"}],
            getir=self._getir({"a": cok}), bugun=BUGUN, besleme_basina=6)
        self.assertEqual(len(haberler), 6)

    def test_urlsiz_besleme_atlanir(self):
        haberler, uyarilar = haberleri_topla(
            [{"ad": "Eksik", "kategori": "genel"}],
            getir=self._getir({}), bugun=BUGUN)
        self.assertEqual(haberler, [])
        self.assertTrue(any("url tanimsiz" in u for u in uyarilar))


class MesajTesti(unittest.TestCase):
    """Ozet YORUM URETMEZ - gruplar ve tazeligi isaretler."""

    def _h(self, baslik, kategori="kripto", tarih=BUGUN):
        return Haber(baslik, "https://x", "Kaynak", kategori, tarih)

    def test_kategoriler_gruplanir_ve_siralanir(self):
        from mesaj import haber_mesaji
        metin = haber_mesaji(
            [self._h("K", "kripto"), self._h("M", "makro"),
             self._h("P", "piyasa")], [], BUGUN)
        self.assertLess(metin.index("Makro"), metin.index("Piyasa"))
        self.assertLess(metin.index("Piyasa"), metin.index("Kripto"))

    def test_tarihsiz_baslik_ISARETLENIR(self):
        from mesaj import haber_mesaji
        metin = haber_mesaji([self._h("X", tarih=None)], [], BUGUN)
        self.assertIn("tarihsiz", metin)
        self.assertIn("VARSAYILMADI", metin)

    def test_okunamayan_kaynak_GIZLENMEZ(self):
        from mesaj import haber_mesaji
        metin = haber_mesaji([self._h("X")], ["CNBC okunamadi: HTTP 500"], BUGUN)
        self.assertIn("Okunamayan kaynak", metin)
        self.assertIn("CNBC", metin)

    def test_bos_sonuc_sebebini_yazar(self):
        from mesaj import haber_mesaji
        metin = haber_mesaji([], ["Ornek okunamadi"], BUGUN)
        self.assertIn("Taze baslik bulunamadi", metin)
        self.assertIn("Ornek okunamadi", metin)

    def test_dosya_baglantilari_tasir(self):
        from mesaj import haber_dosyasi
        metin = haber_dosyasi([self._h("Baslik")], [], BUGUN)
        self.assertIn("[Baslik](https://x)", metin)
        self.assertIn("KARAR URETMEZ", metin)

    def test_telegram_sinirinin_altinda(self):
        from mesaj import haber_mesaji
        cok = [self._h(f"Baslik {i}" * 5, "kripto") for i in range(40)]
        self.assertLess(len(haber_mesaji(cok, [], BUGUN)), 4096)


if __name__ == "__main__":
    unittest.main()
