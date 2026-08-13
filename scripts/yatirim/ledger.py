"""Simulasyon islem defteri: alis/satislari okur, guncel pozisyon durumunu cikarir.

Defter append-only'dir - gecmis islem duzeltilmez, ters islemle kapatilir.
Maliyet agirlikli ortalama yontemiyle tutulur ve islem anindaki TL fiyati
uzerinden kaydedilir (yani kur farki maliyete dahildir).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ALIS = "AL"
SATIS = "SAT"


@dataclass(frozen=True)
class Islem:
    tarih: str
    yon: str
    sembol: str
    adet: float
    fiyat_try: float
    gerekce: str

    @property
    def tutar_try(self) -> float:
        return self.adet * self.fiyat_try


@dataclass(frozen=True)
class LedgerPozisyonu:
    sembol: str
    adet: float
    maliyet_try: float           # kalan adetin toplam maliyeti


@dataclass(frozen=True)
class LedgerDurumu:
    pozisyonlar: dict[str, LedgerPozisyonu]
    nakit_try: float
    baslangic_nakit_try: float
    gerceklesen_kar_try: float
    toplam_komisyon_try: float
    islemler: list[Islem]
    komisyon_orani: float


def islemleri_oku(dosya: Path) -> tuple[list[Islem], float, float]:
    """Defteri okur; (islemler, baslangic_nakit, komisyon_orani) doner."""
    if not dosya.exists():
        raise FileNotFoundError(f"Islem defteri yok: {dosya}")
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8"))

    islemler = [
        Islem(
            tarih=str(kayit["tarih"]),
            yon=kayit["yon"].upper(),
            sembol=kayit["sembol"],
            adet=float(kayit["adet"]),
            fiyat_try=float(kayit["fiyat_try"]),
            gerekce=kayit.get("gerekce", ""),
        )
        for kayit in ham.get("islemler") or []
    ]
    for islem in islemler:
        if islem.yon not in (ALIS, SATIS):
            raise ValueError(f"{islem.tarih} {islem.sembol}: yon AL veya SAT olmali")
        if islem.adet <= 0 or islem.fiyat_try <= 0:
            raise ValueError(f"{islem.tarih} {islem.sembol}: adet ve fiyat pozitif olmali")

    return (
        sorted(islemler, key=lambda i: i.tarih),
        float(ham["baslangic_nakit_try"]),
        float(ham.get("komisyon_orani", 0.0)),
    )


def _alis_uygula(mevcut: LedgerPozisyonu | None, islem: Islem) -> LedgerPozisyonu:
    if mevcut is None:
        return LedgerPozisyonu(islem.sembol, islem.adet, islem.tutar_try)
    return LedgerPozisyonu(
        sembol=islem.sembol,
        adet=mevcut.adet + islem.adet,
        maliyet_try=mevcut.maliyet_try + islem.tutar_try,
    )


def _satis_uygula(mevcut: LedgerPozisyonu | None, islem: Islem) -> tuple[LedgerPozisyonu, float]:
    """Satisi uygular; (kalan pozisyon, gerceklesen kar) doner."""
    if mevcut is None or islem.adet > mevcut.adet + 1e-9:
        elde = 0.0 if mevcut is None else mevcut.adet
        raise ValueError(
            f"{islem.tarih} {islem.sembol}: {islem.adet:g} satilamaz, elde {elde:g} var"
        )
    birim_maliyet = mevcut.maliyet_try / mevcut.adet
    cikan_maliyet = birim_maliyet * islem.adet
    kalan = LedgerPozisyonu(
        sembol=islem.sembol,
        adet=mevcut.adet - islem.adet,
        maliyet_try=mevcut.maliyet_try - cikan_maliyet,
    )
    return kalan, islem.tutar_try - cikan_maliyet


def durumu_hesapla(islemler: list[Islem], baslangic_nakit: float,
                   komisyon_orani: float) -> LedgerDurumu:
    pozisyonlar: dict[str, LedgerPozisyonu] = {}
    nakit = baslangic_nakit
    gerceklesen = 0.0
    komisyon_toplami = 0.0

    for islem in islemler:
        komisyon = islem.tutar_try * komisyon_orani
        komisyon_toplami += komisyon
        mevcut = pozisyonlar.get(islem.sembol)

        if islem.yon == ALIS:
            nakit -= islem.tutar_try + komisyon
            pozisyonlar[islem.sembol] = _alis_uygula(mevcut, islem)
        else:
            nakit += islem.tutar_try - komisyon
            kalan, kar = _satis_uygula(mevcut, islem)
            gerceklesen += kar - komisyon
            pozisyonlar[islem.sembol] = kalan

        if nakit < -1e-6:
            raise ValueError(
                f"{islem.tarih} {islem.sembol}: nakit yetersiz ({nakit:,.2f} TL)"
            )

    return LedgerDurumu(
        pozisyonlar={s: p for s, p in pozisyonlar.items() if p.adet > 1e-12},
        nakit_try=nakit,
        baslangic_nakit_try=baslangic_nakit,
        gerceklesen_kar_try=gerceklesen,
        toplam_komisyon_try=komisyon_toplami,
        islemler=islemler,
        komisyon_orani=komisyon_orani,
    )
