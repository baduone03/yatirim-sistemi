"""Vault otomatik gozden gecirme.

Elle bakilmadigi surece sessizce bozulan seyleri bulur:
  - kirik [[wikilink]]'ler
  - yetim notlar (hicbir yerden baglanti almayan)
  - islenmemis girdiler (status: inbox veya girdi klasorunde status'suz)
  - frontmatter'i eksik notlar
  - money_angle alani hic yazilmamis kaynak notlari
  - kaynak zinciri beyan edilmemis wiki sayfalari
  - uzun suredir dokunulmamis aktif projeler
  - vadesi gelmis karar kontrol gunleri

Cikti: 05-daily/YYYY-AA-GG-gozden-gecirme.md
Eylem gerektiren bulgu varsa Telegram'a ozet gonderilebilir (--telegram).

Kullanim:
    python scripts/vault/gozden_gecir.py
    python scripts/vault/gozden_gecir.py --telegram
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "scripts" / "yatirim"))

GUNLUK_DIZINI = VAULT / "05-daily"
INBOX_DIZINI = VAULT / "01-inbox"

# Disaridan not dusen klasorler. `Clippings` Obsidian Web Clipper'in varsayilan
# hedefi - kupurler vault sablonunu kullanmaz, `status` alani hic yazilmaz.
GIRDI_DIZINLERI = {"01-inbox", "Clippings"}

# Tarama disi: kod, ayar, surum kontrolu, uretilmis ciktilar
ATLANAN = {".git", ".obsidian", ".claude", "__pycache__", "loglar",
           "scripts", ".github"}

BAGLANTI_DESENI = re.compile(r"\[\[([^\]|#]+)")
BAYAT_PROJE_GUN = 14
KONTROL_GUNLERI = (5, 10, 15, 20, 25, 30)

# Muaf notlar - normal vault kurallarina tabi degiller:
#   CLAUDE / README     : ornek [[sablon]] baglantilari icerir, kirik sayilmaz
#   Hoş geldiniz        : Obsidian'in kendi karsilama dosyasi
#   memory              : vault CLAUDE.md'de "Tarih + kisa madde" formatinda
#                         tanimli, frontmatter beklenmiyor
MUAF_NOTLAR = {"CLAUDE", "Hoş geldiniz", "README", "memory"}


@dataclass
class Bulgu:
    baslik: str
    eylem_gerek: bool
    satirlar: list[str] = field(default_factory=list)

    @property
    def var(self) -> bool:
        return bool(self.satirlar)


def notlari_topla() -> list[Path]:
    return [
        p for p in VAULT.rglob("*.md")
        if not any(k in p.parts for k in ATLANAN)
    ]


def _frontmatter_blok(metin: str) -> str | None:
    """Notun basindaki --- ... --- blogu. Yoksa None."""
    eslesme = re.match(r"﻿?\s*---\r?\n(.*?)\r?\n---", metin, re.DOTALL)
    return eslesme.group(1) if eslesme else None


def _frontmatter_alani(metin: str, alan: str) -> str | None:
    """Alani YALNIZCA frontmatter blogunda arar.

    Tum metinde aramak yanlis pozitif uretir: boru hattini anlatan bir not
    govdesinde ornek olarak `status: inbox` yazabilir ve islenmemis girdi
    sayilir.
    """
    blok = _frontmatter_blok(metin)
    if blok is None:
        return None
    eslesme = re.search(rf"^{alan}:\s*(.+)$", blok, re.MULTILINE)
    return eslesme.group(1).strip() if eslesme else None


def kirik_baglantilar(notlar: list[Path]) -> Bulgu:
    adlar = {n.stem for n in notlar}
    bulgu = Bulgu("Kirik wikilink", eylem_gerek=True)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        if not_.stem in MUAF_NOTLAR:
            continue
        metin = not_.read_text(encoding="utf-8", errors="ignore")
        kirik = sorted({
            ham.strip().split("/")[-1]
            for ham in BAGLANTI_DESENI.findall(metin)
            if ham.strip().split("/")[-1] not in adlar
        })
        if kirik:
            bulgu.satirlar.append(f"`{not_.stem}` -> {', '.join(kirik)}")
    return bulgu


def yetim_notlar(notlar: list[Path]) -> Bulgu:
    """Hicbir yerden baglanti almayan notlar.

    Uretilmis raporlar dogal olarak yetimdir (her gun yenisi olusur),
    onlari ayri isaretliyoruz ki gercek yetimler gorunsun.
    """
    gelen: set[str] = set()
    for not_ in notlar:
        metin = not_.read_text(encoding="utf-8", errors="ignore")
        for ham in BAGLANTI_DESENI.findall(metin):
            gelen.add(ham.strip().split("/")[-1])

    bulgu = Bulgu("Yetim not (gelen baglanti yok)", eylem_gerek=False)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        if not_.stem in gelen or not_.stem in MUAF_NOTLAR:
            continue
        if not_.stem.endswith("-gozden-gecirme"):
            continue          # bu betigin kendi ciktisi, her gun yenisi olusur
        # Tarihli rapor ciktilarini eleyelim - bunlar zaten birikir
        if re.fullmatch(r"(tarama-)?\d{4}-\d{2}-\d{2}", not_.stem):
            continue
        bulgu.satirlar.append(f"`{not_.stem}` ({not_.parent.name}/)")
    return bulgu


def islenmemis_girdiler(notlar: list[Path]) -> Bulgu:
    """Bekleyen girdiler: `status: inbox` olanlar + girdi klasorunde durumu
    hic yazilmamis olanlar.

    Ikinci kosul olmadan boru hattinin ana giris kanali gorunmezdi: Web
    Clipper kendi sablonunu yazar, `status` alani koymaz. Yalnizca
    `status: inbox` arayan bir kontrol her kupuru "islenmis" sayardi.
    """
    bulgu = Bulgu("Islenmemis girdi", eylem_gerek=True)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        metin = not_.read_text(encoding="utf-8", errors="ignore")
        durum = _frontmatter_alani(metin, "status")
        if durum == "inbox":
            gun = _frontmatter_alani(metin, "date_created") or "?"
            bulgu.satirlar.append(f"`{not_.stem}` (olusturulma: {gun})")
        elif durum is None and GIRDI_DIZINLERI & set(not_.parts):
            bulgu.satirlar.append(
                f"`{not_.stem}` ({not_.parent.name}/ - status alani yok)")
    return bulgu


def frontmatter_eksikleri(notlar: list[Path]) -> Bulgu:
    """Vault kurali: her notun YAML frontmatter'i olmali."""
    bulgu = Bulgu("Frontmatter eksik", eylem_gerek=False)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        if not_.stem in MUAF_NOTLAR:
            continue
        metin = not_.read_text(encoding="utf-8", errors="ignore")
        # `lstrip().startswith("---")` yetmez: BOM bosluk sayilmadigi icin
        # UTF-8-BOM ile yazilmis her not yanlislikla eksik gorunur (PowerShell
        # `Set-Content -Encoding utf8` boyle yazar). Ayrica kapanis satiri
        # olmayan yarim blok da eksik sayilmalidir.
        if _frontmatter_blok(metin) is None:
            bulgu.satirlar.append(f"`{not_.stem}` ({not_.parent.name}/)")
    return bulgu


def money_angle_eksikleri(notlar: list[Path]) -> Bulgu:
    """CLAUDE.md frontmatter sablonunda money_angle var; alani hic olmayan
    kaynak notlarini isaretler.

    Iki bilincli sinirlama:
      - Yalnizca 01-inbox ve 02-sources taranir. Para acisi degerlendirmesi
        isleme hattinin adimi; uretilmis raporlarda ve proje notlarinda
        anlamsiz olurdu.
      - Alan BOS ise bulgu degildir. CLAUDE.md "zorla firsat uydurma" diyor,
        yani bos money_angle gecerli bir cevap. Yalnizca alanin hic
        yazilmamis olmasi eksiklik sayilir.
    """
    kapsam = {"01-inbox", "02-sources"}
    bulgu = Bulgu("money_angle alani yok (kaynak notu)", eylem_gerek=False)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        if not kapsam & set(not_.parts):
            continue
        blok = _frontmatter_blok(not_.read_text(encoding="utf-8", errors="ignore"))
        if blok is None:
            continue          # frontmatter_eksikleri zaten raporluyor
        if not re.search(r"^money_angle:", blok, re.MULTILINE):
            bulgu.satirlar.append(f"`{not_.stem}` ({not_.parent.name}/)")
    return bulgu


def kaynaksiz_wiki_sayfalari(notlar: list[Path]) -> Bulgu:
    """03-wiki sayfalari kaynagini beyan etmeli.

    `vault-olceklenme-halusinasyon-onleme` kurali: wiki cikti klasorudur,
    kanit kaynagi degil. Kaynagi yazilmamis bir sayfa zamanla "vault boyle
    diyor" diye kendine atif yapilan bir iddiaya doner. Model bilgisiyle
    yazilmis sayfa da gecerlidir - yeter ki
    `kaynak_zinciri: ["model-bilgisi"]` diye acikca soylensin. Amac sayfayi
    engellemek degil, kaynagi gorunur kilmak.
    """
    bulgu = Bulgu("Kaynak zinciri beyan edilmemis wiki sayfasi",
                  eylem_gerek=False)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        if "03-wiki" not in not_.parts:
            continue
        blok = _frontmatter_blok(not_.read_text(encoding="utf-8", errors="ignore"))
        if blok is None:
            continue          # frontmatter_eksikleri zaten raporluyor
        if not re.search(r"^kaynak_zinciri:", blok, re.MULTILINE):
            bulgu.satirlar.append(f"`{not_.stem}` ({not_.parent.name}/)")
    return bulgu


def bayat_projeler(notlar: list[Path]) -> Bulgu:
    """status: active ama uzun suredir dosyaya dokunulmamis."""
    bulgu = Bulgu(f"Bayat aktif proje ({BAYAT_PROJE_GUN}+ gun dokunulmamis)",
                  eylem_gerek=False)
    esik = datetime.now() - timedelta(days=BAYAT_PROJE_GUN)
    for not_ in sorted(notlar, key=lambda p: p.stem):
        metin = not_.read_text(encoding="utf-8", errors="ignore")
        if _frontmatter_alani(metin, "status") != "active":
            continue
        degisim = datetime.fromtimestamp(not_.stat().st_mtime)
        if degisim < esik:
            gecen = (datetime.now() - degisim).days
            bulgu.satirlar.append(f"`{not_.stem}` ({gecen} gun once)")
    return bulgu


def bekleyen_karar_olcumleri() -> Bulgu:
    """Vadesi gelmis ama henuz olculmemis karar kontrol gunleri."""
    bulgu = Bulgu("Bekleyen karar olcumu", eylem_gerek=True)
    try:
        from karar_takip import kararlari_oku, olcumleri_oku
    except ImportError as hata:
        bulgu.satirlar.append(f"karar_takip yuklenemedi: {hata}")
        return bulgu

    yapilmis = {(o.karar_id, o.gun) for o in olcumleri_oku()}
    bugun = date.today()
    for karar in kararlari_oku():
        for gun in KONTROL_GUNLERI:
            if (karar.id, gun) in yapilmis:
                continue
            if karar.tarih_gun + timedelta(days=gun) <= bugun:
                bulgu.satirlar.append(f"`{karar.id}` gun {gun} olculmedi")
    return bulgu


def rapor_olustur(bulgular: list[Bulgu], not_sayisi: int) -> str:
    bugun = date.today().isoformat()
    eylemli = [b for b in bulgular if b.var and b.eylem_gerek]
    bilgi = [b for b in bulgular if b.var and not b.eylem_gerek]

    satirlar = [
        "---",
        f"title: Vault Gozden Gecirme {bugun}",
        f"date_created: {bugun}",
        "tags: [vault, bakim, gozden-gecirme]",
        "status: processed",
        'related: ["[[00-sistem]]"]',
        "---",
        "",
        f"# Vault Gozden Gecirme {bugun}",
        "",
        f"{not_sayisi} not tarandi.",
        "",
    ]

    if not eylemli and not bilgi:
        satirlar += ["Bulgu yok. Vault temiz.", ""]
        return "\n".join(satirlar)

    if eylemli:
        satirlar += ["## Eylem gerekiyor", ""]
        for bulgu in eylemli:
            satirlar += [f"### {bulgu.baslik} ({len(bulgu.satirlar)})", ""]
            satirlar += [f"- {s}" for s in bulgu.satirlar]
            satirlar.append("")

    if bilgi:
        satirlar += ["## Bilgi", ""]
        for bulgu in bilgi:
            satirlar += [f"### {bulgu.baslik} ({len(bulgu.satirlar)})", ""]
            satirlar += [f"- {s}" for s in bulgu.satirlar]
            satirlar.append("")

    return "\n".join(satirlar)


def telegram_ozeti(bulgular: list[Bulgu]) -> str | None:
    """Yalnizca EYLEM GEREKTIREN bulgu varsa mesaj uretir.

    Her calismada 'her sey yolunda' mesaji atmak bildirim korlugu yaratir;
    sessizlik iyi haberdir.
    """
    eylemli = [b for b in bulgular if b.var and b.eylem_gerek]
    if not eylemli:
        return None
    satirlar = [f"<b>Vault gozden gecirme {date.today().isoformat()}</b>", ""]
    for bulgu in eylemli:
        satirlar.append(f"<b>{bulgu.baslik}</b> ({len(bulgu.satirlar)})")
        for satir in bulgu.satirlar[:5]:
            temiz = satir.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            satirlar.append(f"• {temiz}")
        if len(bulgu.satirlar) > 5:
            satirlar.append(f"• ... +{len(bulgu.satirlar) - 5} tane daha")
        satirlar.append("")
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Vault gozden gecirme")
    ayristirici.add_argument("--telegram", action="store_true",
                             help="eylem gerektiren bulgu varsa Telegram'a gonder")
    argumanlar = ayristirici.parse_args()

    notlar = notlari_topla()
    bulgular = [
        kirik_baglantilar(notlar),
        islenmemis_girdiler(notlar),
        bekleyen_karar_olcumleri(),
        yetim_notlar(notlar),
        frontmatter_eksikleri(notlar),
        money_angle_eksikleri(notlar),
        kaynaksiz_wiki_sayfalari(notlar),
        bayat_projeler(notlar),
    ]

    GUNLUK_DIZINI.mkdir(parents=True, exist_ok=True)
    dosya = GUNLUK_DIZINI / f"{date.today().isoformat()}-gozden-gecirme.md"
    dosya.write_text(rapor_olustur(bulgular, len(notlar)), encoding="utf-8")
    print(f"Rapor: {dosya}")

    for bulgu in bulgular:
        if bulgu.var:
            isaret = "!" if bulgu.eylem_gerek else "-"
            print(f"  {isaret} {bulgu.baslik}: {len(bulgu.satirlar)}")

    if argumanlar.telegram:
        mesaj = telegram_ozeti(bulgular)
        if mesaj is None:
            print("Eylem gerektiren bulgu yok, Telegram'a gonderilmedi.")
        else:
            from notify import TelegramHatasi, mesaj_gonder
            try:
                mesaj_gonder(mesaj)
                print("Telegram ozeti gonderildi.")
            except TelegramHatasi as hata:
                print(f"UYARI - Telegram gonderilemedi: {hata}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
