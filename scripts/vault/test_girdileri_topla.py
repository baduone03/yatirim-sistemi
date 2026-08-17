"""girdileri_topla.py testleri. Tamami cevrimdisi, gecici dizinde calisir."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import girdileri_topla as gt


class StatusEklemeTesti(unittest.TestCase):
    """Saf metin donusumu - dosya sistemi kullanmaz."""

    def test_alan_yoksa_eklenir_ve_sira_korunur(self) -> None:
        metin = '---\ntitle: "Yazi"\ntags:\n  - "clippings"\n---\nGovde\n'
        sonuc = gt.status_ekle(metin)
        self.assertEqual(
            sonuc,
            '---\ntitle: "Yazi"\ntags:\n  - "clippings"\nstatus: inbox\n---\nGovde\n',
        )

    def test_mevcut_status_asla_degistirilmez(self) -> None:
        metin = "---\ntitle: X\nstatus: processed\n---\nGovde\n"
        self.assertIsNone(gt.status_ekle(metin))

    def test_frontmatter_yoksa_dokunulmaz(self) -> None:
        self.assertIsNone(gt.status_ekle("Frontmatter yok.\nstatus: inbox\n"))

    def test_crlf_satir_sonu_korunur(self) -> None:
        sonuc = gt.status_ekle("---\r\ntitle: X\r\n---\r\nGovde\r\n")
        self.assertEqual(sonuc, "---\r\ntitle: X\r\nstatus: inbox\r\n---\r\nGovde\r\n")

    def test_govdedeki_status_satiri_mevcut_sayilmaz(self) -> None:
        """Alan aramasi yalnizca frontmatter blogunda yapilir."""
        metin = "---\ntitle: X\n---\nOrnek: status: processed\n"
        self.assertIn("status: inbox", gt.status_ekle(metin))


class DosyaIslemleriTesti(unittest.TestCase):

    def setUp(self) -> None:
        self._gecici = tempfile.TemporaryDirectory()
        kok = Path(self._gecici.name)
        self.inbox = kok / "01-inbox"
        self.clippings = kok / "Clippings"
        self.inbox.mkdir()
        self.clippings.mkdir()
        yamalar = mock.patch.multiple(gt, INBOX=self.inbox, CLIPPINGS=self.clippings)
        yamalar.start()
        self.addCleanup(yamalar.stop)

    def tearDown(self) -> None:
        self._gecici.cleanup()

    def _yaz(self, dizin: Path, ad: str, icerik: str) -> Path:
        yol = dizin / ad
        yol.write_text(icerik, encoding="utf-8")
        return yol

    def test_kupur_inboxa_tasinir(self) -> None:
        self._yaz(self.clippings, "kupur.md", '---\ntitle: "K"\n---\n')
        gt.kupurleri_tasi(kuru=False)
        self.assertTrue((self.inbox / "kupur.md").exists())
        self.assertFalse((self.clippings / "kupur.md").exists())

    def test_ayni_adli_not_varsa_uzerine_yazilmaz(self) -> None:
        self._yaz(self.inbox, "kupur.md", "ESKI\n")
        self._yaz(self.clippings, "kupur.md", "YENI\n")
        islemler = gt.kupurleri_tasi(kuru=False)
        self.assertEqual(self.inbox.joinpath("kupur.md").read_text(encoding="utf-8"),
                         "ESKI\n")
        self.assertTrue((self.clippings / "kupur.md").exists())
        self.assertIn("ATLANDI", islemler[0])

    def test_kuru_calisma_dosyaya_dokunmaz(self) -> None:
        self._yaz(self.clippings, "kupur.md", '---\ntitle: "K"\n---\n')
        islemler = gt.kupurleri_tasi(kuru=True)
        self.assertTrue((self.clippings / "kupur.md").exists())
        self.assertFalse((self.inbox / "kupur.md").exists())
        self.assertEqual(len(islemler), 1)

    def test_durumsuz_inbox_notu_isaretlenir(self) -> None:
        yol = self._yaz(self.inbox, "kupur.md", '---\ntitle: "K"\n---\nGovde\n')
        gt.durumlari_isaretle(kuru=False)
        self.assertIn("status: inbox", yol.read_text(encoding="utf-8"))

    def test_islenmis_not_yeniden_acilmaz(self) -> None:
        icerik = "---\ntitle: K\nstatus: processed\n---\n"
        yol = self._yaz(self.inbox, "islenmis.md", icerik)
        gt.durumlari_isaretle(kuru=False)
        self.assertEqual(yol.read_text(encoding="utf-8"), icerik)

    def test_frontmattersiz_not_uyari_verir_degismez(self) -> None:
        yol = self._yaz(self.inbox, "ham.md", "Sadece govde.\n")
        islemler = gt.durumlari_isaretle(kuru=False)
        self.assertEqual(yol.read_text(encoding="utf-8"), "Sadece govde.\n")
        self.assertIn("UYARI", islemler[0])

    def test_clippings_klasoru_yoksa_hata_vermez(self) -> None:
        with mock.patch.object(gt, "CLIPPINGS", self.clippings / "yok"):
            self.assertEqual(gt.kupurleri_tasi(kuru=False), [])


if __name__ == "__main__":
    unittest.main()
