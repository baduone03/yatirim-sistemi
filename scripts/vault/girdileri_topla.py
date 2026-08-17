"""Girdi normalizasyonu: kupurleri boru hattina sokar.

Iki is yapar:
  1. Clippings/ altina dusen notlari 01-inbox/ altina tasir.
  2. Frontmatter'inda `status` alani olmayan girdi notlarina `status: inbox`
     ekler.

Neden gerekli: Obsidian Web Clipper vault sablonunu kullanmaz. Hedef klasoru
uzanti ayarindadir, `status` alanini ise hicbir ayar yazdirmaz. Yani klasor
ayari duzeltilse bile 2. adim gerekli kalir - kupur 01-inbox'a duser ama
durumsuz duser ve isleme hatti onu goremez.

Mevcut `status` degeri ASLA degistirilmez; yalnizca hic yoksa eklenir.

Kullanim:
    python scripts/vault/girdileri_topla.py            # uygula
    python scripts/vault/girdileri_topla.py --kuru     # yalnizca goster
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
INBOX = VAULT / "01-inbox"
CLIPPINGS = VAULT / "Clippings"

FRONTMATTER = re.compile(r"\A(﻿?\s*---\r?\n)(.*?)(\r?\n---)", re.DOTALL)


def status_ekle(metin: str) -> str | None:
    """Frontmatter'a `status: inbox` ekler.

    None doner: frontmatter yoksa veya `status` alani zaten varsa.
    Alan sirasi korunur, yeni alan blogun sonuna yazilir.
    """
    eslesme = FRONTMATTER.match(metin)
    if eslesme is None:
        return None
    bas, govde, kapanis = eslesme.groups()
    if re.search(r"^status:", govde, re.MULTILINE):
        return None
    satir_sonu = "\r\n" if kapanis.startswith("\r\n") else "\n"
    return f"{bas}{govde}{satir_sonu}status: inbox{kapanis}{metin[eslesme.end():]}"


def kupurleri_tasi(kuru: bool) -> list[str]:
    """Clippings/ altindaki notlari 01-inbox/ altina tasir."""
    if not CLIPPINGS.is_dir():
        return []
    islemler: list[str] = []
    INBOX.mkdir(parents=True, exist_ok=True)
    for kaynak in sorted(CLIPPINGS.rglob("*.md")):
        hedef = INBOX / kaynak.name
        if hedef.exists():
            islemler.append(f"ATLANDI - 01-inbox'ta ayni adli not var: {kaynak.name}")
            continue
        islemler.append(f"tasindi: Clippings/{kaynak.name} -> 01-inbox/")
        if not kuru:
            kaynak.rename(hedef)
    return islemler


def durumlari_isaretle(kuru: bool) -> list[str]:
    """01-inbox'ta durumu yazilmamis notlari `status: inbox` yapar."""
    if not INBOX.is_dir():
        return []
    islemler: list[str] = []
    for not_ in sorted(INBOX.glob("*.md")):
        metin = not_.read_text(encoding="utf-8")
        if FRONTMATTER.match(metin) is None:
            islemler.append(f"UYARI - frontmatter yok, elle bakilmali: {not_.name}")
            continue
        yeni = status_ekle(metin)
        if yeni is None:
            continue
        islemler.append(f"status: inbox eklendi: {not_.name}")
        if not kuru:
            not_.write_text(yeni, encoding="utf-8")
    return islemler


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Girdi normalizasyonu")
    ayristirici.add_argument("--kuru", action="store_true",
                             help="degisiklik yapma, yalnizca ne olacagini yaz")
    argumanlar = ayristirici.parse_args()

    islemler = kupurleri_tasi(argumanlar.kuru) + durumlari_isaretle(argumanlar.kuru)
    if not islemler:
        print("Normalize edilecek girdi yok.")
        return 0

    if argumanlar.kuru:
        print("KURU CALISMA - hicbir dosya degismedi")
    for satir in islemler:
        print(f"  {satir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
