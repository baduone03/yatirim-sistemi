"""Pozisyon degerleme, kar/zarar ve varlik sinifi dagilimi."""

from __future__ import annotations

from dataclasses import dataclass

from config import Yapilandirma
from fetch import FiyatVerisi

NAKIT_SINIFI = "nakit"


@dataclass(frozen=True)
class PozisyonDegeri:
    sembol: str
    ad: str
    sinif: str
    adet: float
    maliyet_try: float
    deger_try: float

    @property
    def kar_zarar_try(self) -> float:
        return self.deger_try - self.maliyet_try

    @property
    def kar_zarar_yuzde(self) -> float:
        return 0.0 if self.maliyet_try == 0 else self.kar_zarar_try / self.maliyet_try


@dataclass(frozen=True)
class SinifSapmasi:
    sinif: str
    guncel_agirlik: float
    hedef_agirlik: float

    @property
    def sapma(self) -> float:
        return self.guncel_agirlik - self.hedef_agirlik


@dataclass(frozen=True)
class Portfoy:
    pozisyonlar: list[PozisyonDegeri]
    nakit_try: float
    fiyatlanamayan: list[str]

    @property
    def pozisyon_degeri_try(self) -> float:
        return sum(p.deger_try for p in self.pozisyonlar)

    @property
    def toplam_deger_try(self) -> float:
        return self.pozisyon_degeri_try + self.nakit_try

    @property
    def toplam_maliyet_try(self) -> float:
        return sum(p.maliyet_try for p in self.pozisyonlar) + self.nakit_try

    @property
    def agirliklar(self) -> dict[str, float]:
        """Sembol -> toplam portfoy icindeki agirlik (nakit haric)."""
        toplam = self.toplam_deger_try
        if toplam == 0:
            return {}
        return {p.sembol: p.deger_try / toplam for p in self.pozisyonlar}


def _maliyeti_tl_yap(maliyet: float, adet: float, kur: str, usdtry: float) -> float:
    """Maliyet varligin kendi para biriminde tutulur; guncel kurla TL'ye cevrilir.

    Not: gecmis alis kuru degil guncel kur kullanilir, yani kur farki
    kar/zarara yansimaz. Kur etkisini ayirmak istersen pozisyona alis
    kuru alani eklemek gerekir.
    """
    tutar = maliyet * adet
    return tutar * usdtry if kur == "USD" else tutar


def portfoyu_hesapla(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi) -> Portfoy:
    son = fiyatlar.son_fiyatlar
    degerler: list[PozisyonDegeri] = []
    fiyatlanamayan: list[str] = []

    for pozisyon in yapilandirma.pozisyonlar:
        varlik = yapilandirma.varliklar[pozisyon.sembol]
        if pozisyon.sembol not in son:
            fiyatlanamayan.append(pozisyon.sembol)
            continue
        degerler.append(
            PozisyonDegeri(
                sembol=pozisyon.sembol,
                ad=varlik.ad,
                sinif=varlik.sinif,
                adet=pozisyon.adet,
                maliyet_try=_maliyeti_tl_yap(
                    pozisyon.maliyet, pozisyon.adet, varlik.kur, fiyatlar.usdtry
                ),
                # son fiyat zaten TL ve carpan uygulanmis halde geliyor (fetch.py)
                deger_try=son[pozisyon.sembol] * pozisyon.adet,
            )
        )

    return Portfoy(
        pozisyonlar=degerler,
        nakit_try=yapilandirma.nakit_try,
        fiyatlanamayan=sorted(fiyatlanamayan),
    )


def portfoyu_ledgerdan_hesapla(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi,
                               durum) -> Portfoy:
    """Simulasyon defterinden portfoy uretir.

    Ledger maliyeti zaten islem anindaki TL tutaridir - kur cevrimi yapilmaz.
    """
    son = fiyatlar.son_fiyatlar
    degerler: list[PozisyonDegeri] = []
    fiyatlanamayan: list[str] = []

    for sembol, ledger_pozisyonu in durum.pozisyonlar.items():
        varlik = yapilandirma.varliklar[sembol]
        if sembol not in son:
            fiyatlanamayan.append(sembol)
            continue
        degerler.append(
            PozisyonDegeri(
                sembol=sembol,
                ad=varlik.ad,
                sinif=varlik.sinif,
                adet=ledger_pozisyonu.adet,
                maliyet_try=ledger_pozisyonu.maliyet_try,
                deger_try=son[sembol] * ledger_pozisyonu.adet,
            )
        )

    return Portfoy(
        pozisyonlar=degerler,
        nakit_try=durum.nakit_try,
        fiyatlanamayan=sorted(fiyatlanamayan),
    )


def sinif_sapmalari(portfoy: Portfoy, hedef_dagilim: dict[str, float]) -> list[SinifSapmasi]:
    toplam = portfoy.toplam_deger_try
    if toplam == 0:
        return []

    guncel: dict[str, float] = {NAKIT_SINIFI: portfoy.nakit_try / toplam}
    for pozisyon in portfoy.pozisyonlar:
        guncel[pozisyon.sinif] = guncel.get(pozisyon.sinif, 0.0) + pozisyon.deger_try / toplam

    siniflar = sorted(set(guncel) | set(hedef_dagilim))
    return [
        SinifSapmasi(
            sinif=sinif,
            guncel_agirlik=guncel.get(sinif, 0.0),
            hedef_agirlik=hedef_dagilim.get(sinif, 0.0),
        )
        for sinif in siniflar
    ]
