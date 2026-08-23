"""Haber arsivi: RSS basliklarini diske yazar, boylece sonradan atif yapilabilir.

NEDEN: `haber.py` beslemeleri cekiyor ama hicbir sey saklamiyordu - basliklar
Telegram'a basilip unutuluyordu. Ongoru defterinin `dayanak` alani tam da bunu
bekliyor: uc ay sonra "bunu neden dusunmustum" sorusunun cevabi burada durur.

TELEGRAM OZETIYLE AYNI SEY DEGIL. Ozet gunde 6 baslik/besleme ile sinirli
cunku okunabilir kalmali; arsivin boyle bir derdi yok ve tavani cok daha
yuksek. Ayni fonksiyonu iki farkli tavanla cagirmamizin sebebi bu.

BU MODUL DE KARAR YOLUNA BAGLANMAZ. Haber baglam icindir; sistemin kararlari
fiyat ve orana bakar. Arsiv, sonradan okunacak bir kayittir - sinyal kaynagi
degil. Bkz. HaberArsiviIzolasyonTesti.

Gunluk dosya: haber-arsivi/YYYY-AA-GG.yaml
Ayni baslik iki kez yazilmaz (baglanti anahtardir); dosya gun icinde buyur.

Kullanim:
    python scripts/yatirim/haber_arsivi.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PROJE_DIZINI, yapilandirmayi_oku  # noqa: E402
from haber import haberleri_topla, http_metin  # noqa: E402

ARSIV_DIZINI = PROJE_DIZINI / "haber-arsivi"

# Ozetin tavani 6; arsivinki yuksek cunku arsivin okunabilirlik derdi yok.
# Yine de sinirsiz degil: bozuk bir besleme binlerce oge dondurse gunluk
# dosya sismesin.
ARSIV_BESLEME_BASINA = 40
ARSIV_AZAMI_GUN = 3


@dataclass(frozen=True)
class ArsivKaydi:
    baslik: str
    baglanti: str
    kaynak: str
    kategori: str
    tarih: str          # beslemenin verdigi tarih, "" = besleme tarih vermedi
    ilk_gorulme: str    # bizim ilk gordugumuz an (UTC)


def arsiv_dosyasi(gun: date, dizin: Path = ARSIV_DIZINI) -> Path:
    return dizin / f"{gun.isoformat()}.yaml"


def arsivi_oku(dosya: Path) -> list[ArsivKaydi]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    return [
        ArsivKaydi(
            baslik=str(k.get("baslik", "")),
            baglanti=str(k.get("baglanti", "")),
            kaynak=str(k.get("kaynak", "")),
            kategori=str(k.get("kategori", "")),
            tarih=str(k.get("tarih") or ""),
            ilk_gorulme=str(k.get("ilk_gorulme", "")),
        )
        for k in (ham.get("basliklar") or [])
    ]


def arsivi_yaz(kayitlar: list[ArsivKaydi], dosya: Path) -> None:
    icerik = {
        "basliklar": [
            {
                "baslik": k.baslik, "baglanti": k.baglanti, "kaynak": k.kaynak,
                "kategori": k.kategori, "tarih": k.tarih,
                "ilk_gorulme": k.ilk_gorulme,
            }
            for k in sorted(kayitlar, key=lambda x: (x.ilk_gorulme, x.baglanti))
        ]
    }
    baslik = (
        "# MAKINE URETIR - elle duzenleme.\n"
        "# haber_arsivi.py yazar. Ayni baglanti iki kez yazilmaz.\n"
        "# Bu dosya KAYITTIR, kaynak degil: buradaki bir baslik tek basina\n"
        "# bir iddiayi desteklemez, yalnizca o gun ne okundugunu gosterir.\n\n"
    )
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(
        baslik + yaml.safe_dump(icerik, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def yeni_kayitlar(haberler, mevcut: list[ArsivKaydi], simdi: datetime
                  ) -> list[ArsivKaydi]:
    """Arsivde olmayan basliklari kayda cevirir. Anahtar: baglanti.

    Baslik degil baglanti anahtar: ayni haberi iki kaynak farkli baslikla
    verebilir, ama ayni besleme ayni baglantiyi her kosuda tekrar verir.
    Baslik anahtar olsaydi kucuk bir editoryal duzeltme kaydi coklardi.
    """
    bilinen = {k.baglanti for k in mevcut if k.baglanti}
    damga = simdi.isoformat(timespec="seconds")
    yeni = []
    goruldu = set()
    for haber in haberler:
        if not haber.baglanti or haber.baglanti in bilinen or haber.baglanti in goruldu:
            continue
        goruldu.add(haber.baglanti)
        yeni.append(ArsivKaydi(
            baslik=haber.baslik, baglanti=haber.baglanti, kaynak=haber.kaynak,
            kategori=haber.kategori,
            tarih=haber.tarih.isoformat() if haber.tarih else "",
            ilk_gorulme=damga,
        ))
    return yeni


def arsivle(beslemeler: list[dict], gun: date, simdi: datetime,
            getir=http_metin, dizin: Path = ARSIV_DIZINI
            ) -> tuple[int, list[str]]:
    """Beslemeleri cekip gunluk arsive ekler. Doner: (yeni_sayi, uyarilar)."""
    haberler, uyarilar = haberleri_topla(
        beslemeler, getir=getir, bugun=gun,
        azami_gun=ARSIV_AZAMI_GUN, besleme_basina=ARSIV_BESLEME_BASINA)

    dosya = arsiv_dosyasi(gun, dizin)
    mevcut = arsivi_oku(dosya)
    yeni = yeni_kayitlar(haberler, mevcut, simdi)
    if yeni:
        arsivi_yaz(mevcut + yeni, dosya)
    return len(yeni), uyarilar


def main() -> int:
    yapilandirma = yapilandirmayi_oku()
    beslemeler = yapilandirma.haber.beslemeler
    if not beslemeler:
        print("Haber beslemesi tanimli degil - arsivleme atlandi.")
        return 0

    simdi = datetime.now(timezone.utc)
    yeni_sayi, uyarilar = arsivle(beslemeler, simdi.date(), simdi)

    for uyari in uyarilar:
        print(f"UYARI - {uyari}")

    # Besleme dusmesi kosuyu BASARISIZ YAPMAZ: haber baglamdir, karar
    # girdisi degil. CoinDesk'in bir hickirigi tum kosuyu kirmamali.
    if yeni_sayi:
        print(f"{yeni_sayi} yeni baslik arsivlendi: "
              f"{arsiv_dosyasi(simdi.date())}")
    else:
        print("Yeni baslik yok, arsive dokunulmadi.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
