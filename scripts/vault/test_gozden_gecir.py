"""gozden_gecir.py testleri.

Tamami cevrimdisi: gecici dizinde sahte not agaci kurulur, gercek vault
okunmaz. Calistirma:
    python -m unittest discover -s scripts/vault -p "test_*.py"
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import gozden_gecir as gg


class NotAgaciTesti(unittest.TestCase):
    """Gecici dizinde not olusturan yardimci taban."""

    def setUp(self) -> None:
        self._gecici = tempfile.TemporaryDirectory()
        self.kok = Path(self._gecici.name)

    def tearDown(self) -> None:
        self._gecici.cleanup()

    def _not(self, goreli_yol: str, icerik: str) -> Path:
        yol = self.kok / goreli_yol
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8")
        return yol


class FrontmatterKapsamiTesti(NotAgaciTesti):
    """Alan aramasi yalnizca frontmatter blogunda yapilmali."""

    def test_govdedeki_status_satiri_frontmatter_sayilmaz(self) -> None:
        yol = self._not("04-projects/boru-hatti.md", (
            "---\n"
            "title: Boru Hatti\n"
            "status: evergreen\n"
            "---\n\n"
            "Isleme kurali soyle yazilir:\n"
            "status: inbox\n"
        ))
        self.assertEqual(
            gg._frontmatter_alani(yol.read_text(encoding="utf-8"), "status"),
            "evergreen",
        )

    def test_frontmattersiz_notta_alan_yok(self) -> None:
        yol = self._not("kok-not.md", "Sadece govde.\nstatus: inbox\n")
        self.assertIsNone(
            gg._frontmatter_alani(yol.read_text(encoding="utf-8"), "status"))


class IslenmemisGirdiTesti(NotAgaciTesti):
    """Bekleyen girdi tespiti - iki kosul birden aranir."""

    def _bulgu_satirlari(self, *notlar: Path) -> list[str]:
        return gg.islenmemis_girdiler(list(notlar)).satirlar

    def test_status_inbox_bekleyen_sayilir(self) -> None:
        yol = self._not("01-inbox/ham.md",
                        "---\nstatus: inbox\ndate_created: 2026-08-15\n---\n")
        satirlar = self._bulgu_satirlari(yol)
        self.assertEqual(len(satirlar), 1)
        self.assertIn("2026-08-15", satirlar[0])

    def test_girdi_klasorunde_statussuz_not_bekleyen_sayilir(self) -> None:
        """Web Clipper senaryosu: kupur kendi sablonunu yazar, status koymaz."""
        yol = self._not("Clippings/kupur.md",
                        '---\ntitle: "Bir Yazi"\ntags:\n  - "clippings"\n---\n')
        satirlar = self._bulgu_satirlari(yol)
        self.assertEqual(len(satirlar), 1)
        self.assertIn("status alani yok", satirlar[0])

    def test_inbox_klasorunde_statussuz_not_da_sayilir(self) -> None:
        yol = self._not("01-inbox/kupur.md", '---\ntitle: "Bir Yazi"\n---\n')
        self.assertEqual(len(self._bulgu_satirlari(yol)), 1)

    def test_girdi_klasoru_disinda_statussuz_not_sayilmaz(self) -> None:
        """Proje ve wiki notlarinda status beklenmiyor - yanlis pozitif olmaz."""
        yol = self._not("04-projects/sartname.md", '---\ntitle: "Sartname"\n---\n')
        self.assertEqual(self._bulgu_satirlari(yol), [])

    def test_islenmis_girdi_sayilmaz(self) -> None:
        yol = self._not("01-inbox/islenmis.md", "---\nstatus: processed\n---\n")
        self.assertEqual(self._bulgu_satirlari(yol), [])


class FrontmatterEksigiTesti(NotAgaciTesti):

    def _bulgu_satirlari(self, *notlar: Path) -> list[str]:
        return gg.frontmatter_eksikleri(list(notlar)).satirlar

    def test_bom_ile_yazilmis_not_eksik_sayilmaz(self) -> None:
        """PowerShell `Set-Content -Encoding utf8` BOM yazar; BOM bosluk degil."""
        yol = self._not("01-inbox/bomlu.md", "﻿---\ntitle: X\n---\nGovde\n")
        self.assertEqual(self._bulgu_satirlari(yol), [])

    def test_frontmattersiz_not_isaretlenir(self) -> None:
        yol = self._not("01-inbox/ham.md", "Sadece govde.\n")
        self.assertEqual(len(self._bulgu_satirlari(yol)), 1)

    def test_kapanmamis_blok_eksik_sayilir(self) -> None:
        yol = self._not("01-inbox/yarim.md", "---\ntitle: X\nGovde devam ediyor\n")
        self.assertEqual(len(self._bulgu_satirlari(yol)), 1)


class KaynaksizWikiTesti(NotAgaciTesti):
    """Wiki sayfalari kaynagini beyan etmeli (yanki odasi kontrolu)."""

    def _bulgu_satirlari(self, *notlar: Path) -> list[str]:
        return gg.kaynaksiz_wiki_sayfalari(list(notlar)).satirlar

    def test_kaynak_zinciri_olmayan_sayfa_isaretlenir(self) -> None:
        yol = self._not("03-wiki/concepts/kavram.md",
                        "---\ntitle: Kavram\nstatus: processed\n---\n")
        satirlar = self._bulgu_satirlari(yol)
        self.assertEqual(len(satirlar), 1)
        self.assertIn("kavram", satirlar[0])

    def test_model_bilgisi_beyani_yeterlidir(self) -> None:
        """Kaynaksiz sayfa yasak degil; beyan edilmemis sayfa sorun."""
        yol = self._not("03-wiki/concepts/kavram.md", (
            "---\ntitle: Kavram\nkaynak_zinciri: [\"model-bilgisi\"]\n---\n"))
        self.assertEqual(self._bulgu_satirlari(yol), [])

    def test_wiki_disi_not_kontrol_edilmez(self) -> None:
        yol = self._not("02-sources/kaynak.md", "---\ntitle: Kaynak\n---\n")
        self.assertEqual(self._bulgu_satirlari(yol), [])

    def test_frontmattersiz_sayfa_burada_sayilmaz(self) -> None:
        """frontmatter_eksikleri zaten raporluyor - cift bildirim olmasin."""
        yol = self._not("03-wiki/concepts/bos.md", "Frontmatter yok.\n")
        self.assertEqual(self._bulgu_satirlari(yol), [])


if __name__ == "__main__":
    unittest.main()
