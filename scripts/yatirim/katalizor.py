"""Katalizor takvimi: onumuzdeki gunlerde fiyati oynatabilecek bilinen olaylar.

PPK faiz karari, TUFE aciklamasi, FOMC, bilanco tarihi gibi olaylar ONCEDEN
bilinir. Sistem fiyat tahmini yapmaz; bu modul de yapmaz. Yalnizca "bu hafta
su olay var, su pozisyonuna dokunuyor" der - sinyale, esige veya agirliga
DONUSMEZ.

Kaynak elle tutulan `katalizorler.yaml`. Elle tutulan liste sessizce
bayatlar: son olay yaklastiginda "takvimi guncelle" uyarisi uretilir, yoksa
bos bir takvim "bu hafta olay yok" gibi okunurdu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

MAKRO = "makro"
ETKILER = ("yuksek", "orta", "dusuk")
GUN_KISA = ("Pzt", "Sal", "Car", "Per", "Cum", "Cmt", "Paz")


@dataclass(frozen=True)
class Katalizor:
    tarih: date
    olay: str
    kapsam: str                  # makro | sinif (bist) | sembol (THYAO.IS)
    etki: str
    saat: str = ""               # TR saati, bilinmiyorsa bos
    kaynak: str = ""

    def ilgili_mi(self, semboller: set[str], siniflar: set[str]) -> bool:
        """Tutulan bir pozisyona DOGRUDAN dokunuyor mu. Makro olay herkese
        dokunur; onu isaretlemek her satiri isaretlemek olurdu."""
        return self.kapsam in semboller or self.kapsam in siniflar


@dataclass(frozen=True)
class Takvim:
    olaylar: list[Katalizor] = field(default_factory=list)
    pencere_gun: int = 7
    kapsama_uyari_gun: int = 21

    def yaklasanlar(self, bugun: date) -> list[Katalizor]:
        son = bugun + timedelta(days=self.pencere_gun)
        return sorted((k for k in self.olaylar if bugun <= k.tarih <= son),
                      key=lambda k: (k.tarih, k.saat))

    def kapsama_uyarisi(self, bugun: date) -> str | None:
        """Takvim `kapsama_uyari_gun` sonrasini kapsamiyorsa uyari."""
        if not self.olaylar:
            return None
        en_son = max(k.tarih for k in self.olaylar)
        sinir = bugun + timedelta(days=self.kapsama_uyari_gun)
        if en_son >= sinir:
            return None
        return (f"Katalizor takvimi {en_son.isoformat()} sonrasini kapsamiyor - "
                "katalizorler.yaml'a yeni tarihleri ekle (PPK, TUFE, FOMC, bilanco)")


def takvimi_oku(dosya: Path, semboller: set[str], siniflar: set[str]) -> Takvim:
    """Takvimi okur ve dogrular. Dosya yoksa bos takvim (ozellik opsiyonel).

    Yazim hatasi okumada patlar: kapsami yanlis yazilmis olay sessizce
    "pozisyonuna dokunmuyor" gorunur.
    """
    if not dosya.exists():
        return Takvim()
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    olaylar = []
    for kayit in ham.get("olaylar") or []:
        tarih = kayit.get("tarih")
        if not isinstance(tarih, date):
            raise ValueError(f"katalizor tarihi YYYY-AA-GG olmali: {kayit}")
        olay = Katalizor(
            tarih=tarih, olay=str(kayit.get("olay", "")).strip(),
            kapsam=str(kayit.get("kapsam", "")), etki=str(kayit.get("etki", "")),
            saat=str(kayit.get("saat", "") or ""), kaynak=str(kayit.get("kaynak", "") or ""))
        if not olay.olay:
            raise ValueError(f"{tarih}: katalizor 'olay' bos")
        if olay.etki not in ETKILER:
            raise ValueError(f"{tarih} {olay.olay}: etki {'|'.join(ETKILER)} olmali, "
                             f"'{olay.etki}' geldi")
        if olay.kapsam not in (MAKRO, *siniflar, *semboller):
            raise ValueError(
                f"{tarih} {olay.olay}: kapsam '{olay.kapsam}' tanimsiz. Gecerli: "
                f"makro, bir sinif ({', '.join(sorted(siniflar))}) veya "
                "varliklar.yaml'daki bir sembol")
        olaylar.append(olay)
    return Takvim(olaylar=olaylar,
                  pencere_gun=int(ham.get("pencere_gun", 7)),
                  kapsama_uyari_gun=int(ham.get("kapsama_uyari_gun", 21)))


def gun_etiketi(tarih: date, aylar: tuple[str, ...]) -> str:
    """'Pzt 5 Ekim'. Ay adlari cagirandan gelir (mesaj.AYLAR) - iki kopya
    tutulursa biri degisir, digeri degismez."""
    return f"{GUN_KISA[tarih.weekday()]} {tarih.day} {aylar[tarih.month - 1]}"
