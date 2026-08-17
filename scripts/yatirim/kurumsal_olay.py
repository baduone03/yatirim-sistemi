"""Kurumsal olay defteri: bedelsiz, split, ters split.

Bu olaylar islem defterine YAZILMAZ. Ledger append-only'dir ve yalnizca
kullanicinin yaptigi alim/satimi tutar; bedelsiz ise sirketin yaptigi bir
istir, nakit akisi yoktur. Ayri defter tutulur, pozisyon hesaplanirken
islemlerle tarih sirasinda harmanlanir.

Muhasebe kurali:
    adet           x= oran
    TOPLAM maliyet degismez
    birim maliyet  /= oran   (turetilir)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

BEDELSIZ = "bedelsiz"
SPLIT = "split"
TERS_SPLIT = "ters_split"
TIPLER = (BEDELSIZ, SPLIT, TERS_SPLIT)


@dataclass(frozen=True)
class KurumsalOlay:
    tarih: str
    sembol: str
    tip: str
    oran: float
    aciklama: str = ""


def _dogrula(olay: KurumsalOlay) -> None:
    etiket = f"{olay.tarih} {olay.sembol}"
    if olay.tip not in TIPLER:
        raise ValueError(f"{etiket}: tip {' | '.join(TIPLER)} olmali, '{olay.tip}' geldi")
    if olay.oran <= 0:
        raise ValueError(f"{etiket}: oran pozitif olmali, {olay.oran} geldi")
    # Yon hatasi en pahali hata: 4:1 split'e 0.25 yazmak adedi 16 kat yanlis
    # yapar. Tip ile oranin yonu tutarli olmali.
    if olay.tip in (BEDELSIZ, SPLIT) and olay.oran <= 1:
        raise ValueError(
            f"{etiket}: {olay.tip} adedi ARTIRIR, oran 1'den buyuk olmali "
            f"({olay.oran} geldi). Adet azaliyorsa tip 'ters_split' olmali."
        )
    if olay.tip == TERS_SPLIT and olay.oran >= 1:
        raise ValueError(
            f"{etiket}: ters_split adedi AZALTIR, oran 1'den kucuk olmali "
            f"({olay.oran} geldi). 1:10 ters split icin 0.1 yaz."
        )


def olaylari_oku(dosya: Path) -> list[KurumsalOlay]:
    """Defteri okur, tarihe gore sirali doner.

    Dosya yoksa HATA verir, bos liste donmez: sessizce bos donmek, defteri
    silinmis bir sistemde pozisyonlarin duzeltilmemis adetle hesaplanmasi
    ve kimsenin fark etmemesi demektir.
    """
    if not dosya.exists():
        raise FileNotFoundError(f"Kurumsal olay defteri yok: {dosya}")
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}

    olaylar = [
        KurumsalOlay(
            tarih=str(kayit["tarih"]),
            sembol=kayit["sembol"],
            tip=str(kayit["tip"]).lower(),
            oran=float(kayit["oran"]),
            aciklama=str(kayit.get("not", "")),
        )
        for kayit in ham.get("olaylar") or []
    ]
    for olay in olaylar:
        _dogrula(olay)
    return sorted(olaylar, key=lambda o: o.tarih)


def bilinen_olay_anahtarlari(olaylar: list[KurumsalOlay]) -> set[tuple[str, str]]:
    """(sembol, tarih) kumesi - otomatik tespitin tekrar uyarmamasi icin.

    Olay deftere yazildiktan sonra fiyat sicramasi hala veride duruyor.
    Bu kume olmadan sistem her calismada ayni olayi "supheli" diye isaretler
    ve o sembolun degerlemesini sonsuza kadar durdurur.
    """
    return {(olay.sembol, olay.tarih) for olay in olaylar}
