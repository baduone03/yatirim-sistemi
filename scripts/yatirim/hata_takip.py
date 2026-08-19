"""Tekrarlayan hata bildirimlerini bastirir.

SORUN: gunluk rapor hattinda kalici bir ariza (bayat hurdle rate, cokmus
kaynak, kirik yapilandirma) her kosuda ayni Telegram mesajini uretir. Iki
saatlik gridde bu gunde 12 ayni mesaj demek. Sonuc paradoksal: bildirim ne
kadar cok gelirse o kadar az okunur, ve gercekten YENI bir ariza o gurultunun
icinde kaybolur.

KURAL:
  - Yeni hata kodu          -> HEMEN bildir.
  - Ayni kod, 24 saat icinde -> BASTIR (sessiz).
  - Ayni kod, 24 saat sonra  -> "hala devam ediyor" ozeti (gunde bir).
  - Hata kodu DEGISTI        -> HEMEN bildir (yeni ariza, eskisi maskeledi).
  - Hata COZULDU             -> HEMEN bildir (bir kez).

Bastirma yalnizca BILDIRIMI etkiler; hatanin kendisi her kosuda yine
loglanir ve kosu yine kirmizi olur. Sessizlestirilen sey gurultu, bilgi degil.

Durum `simulasyon/hata-durumu.yaml` icinde tutulur ve COMMIT EDILMEK
ZORUNDADIR - Actions her kosuda temiz checkout alir, commit edilmezse her
kosu "yeni hata" sanir ve bastirma hicbir zaman devreye girmez.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from config import PROJE_DIZINI, simdi_utc

DURUM_DOSYASI = PROJE_DIZINI / "simulasyon" / "hata-durumu.yaml"

# Ayni hatanin tekrar bildirilmesi icin gecmesi gereken sure.
# 24 saat: gunde bir "hala devam ediyor" hatirlatmasi, daha sik degil.
VARSAYILAN_ARALIK_SAAT = 24

YENI = "yeni"
DEVAM = "devam"
BASTIR = "bastir"
COZULDU = "cozuldu"


@dataclass(frozen=True)
class AktifHata:
    kod: str
    ilk_gorulme: datetime
    son_bildirim: datetime
    bildirim_sayisi: int = 1

    @property
    def sozluk(self) -> dict:
        return {
            "kod": self.kod,
            "ilk_gorulme": self.ilk_gorulme.isoformat(),
            "son_bildirim": self.son_bildirim.isoformat(),
            "bildirim_sayisi": self.bildirim_sayisi,
        }


@dataclass(frozen=True)
class Karar:
    """Doner: ne yapilacagi ve (bildirilecekse) mesaj oneki."""

    durum: str
    yeni_kayit: AktifHata | None
    onek: str = ""

    @property
    def bildirilecek(self) -> bool:
        return self.durum != BASTIR


def _tarih(ham) -> datetime | None:
    if isinstance(ham, datetime):
        return ham
    try:
        return datetime.fromisoformat(str(ham))
    except (TypeError, ValueError):
        return None


def durumu_oku(dosya: Path = DURUM_DOSYASI) -> AktifHata | None:
    if not dosya.exists():
        return None
    ham = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("aktif")
    if not ham or not ham.get("kod"):
        return None
    ilk = _tarih(ham.get("ilk_gorulme"))
    son = _tarih(ham.get("son_bildirim"))
    if ilk is None or son is None:
        # Bozuk kayit: "hic kayit yok" say. Alternatif olan "bastir" secimi,
        # bozuk bir dosyanin butun hata bildirimlerini kalici olarak
        # susturmasi demekti.
        return None
    return AktifHata(kod=str(ham["kod"]), ilk_gorulme=ilk, son_bildirim=son,
                     bildirim_sayisi=int(ham.get("bildirim_sayisi", 1)))


def durumu_yaz(aktif: AktifHata | None, dosya: Path = DURUM_DOSYASI) -> None:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    govde = yaml.safe_dump({"aktif": aktif.sozluk if aktif else None},
                           allow_unicode=True, sort_keys=False)
    dosya.write_text(
        "# MAKINE URETIR - elle duzenleme.\n"
        "# Aktif hata ve son bildirim zamani. Silinirse bir sonraki hata\n"
        "# 'yeni' sayilir ve tekrar bildirilir; sistem durmaz.\n"
        f"{govde}",
        encoding="utf-8",
    )


def karar_ver(kod: str, onceki: AktifHata | None, simdi: datetime,
              aralik_saat: int = VARSAYILAN_ARALIK_SAAT) -> Karar:
    """Bu hata bildirilecek mi?

    `kod` bos ise "hata yok" demektir: aktif bir hata varsa COZULDU uretir.

    Kod karsilastirmasi TAM esitlik: hata metni degil KOD kullanilmasinin
    sebebi, ayni arizanin mesajinda degisken bir parca (kosu URL'i, tarih,
    sembol sayisi) bulunmasi. Metne bakan bir karsilastirma her kosuda
    "yeni hata" gorur ve bastirma hicbir zaman calismazdi.
    """
    if not kod:
        if onceki is None:
            return Karar(BASTIR, None)
        return Karar(COZULDU, None,
                     onek=f"COZULDU ({onceki.kod}) - "
                          f"{_sure_metni(simdi - onceki.ilk_gorulme)} surdu.")

    if onceki is None or onceki.kod != kod:
        # Yeni ariza. Eskisi hala duruyor olabilir ama artik gorunen bu.
        return Karar(YENI, AktifHata(kod=kod, ilk_gorulme=simdi,
                                     son_bildirim=simdi, bildirim_sayisi=1))

    if simdi - onceki.son_bildirim >= timedelta(hours=aralik_saat):
        return Karar(
            DEVAM,
            AktifHata(kod=kod, ilk_gorulme=onceki.ilk_gorulme,
                      son_bildirim=simdi,
                      bildirim_sayisi=onceki.bildirim_sayisi + 1),
            onek=f"HALA DEVAM EDIYOR - "
                 f"{_sure_metni(simdi - onceki.ilk_gorulme)} once basladi.")

    # Bastirilan bildirim son_bildirim'i ILERLETMEZ. Ilerletseydi her kosu
    # 24 saatlik sayaci sifirlar ve "hala devam ediyor" ozeti hicbir zaman
    # gonderilmezdi - bekleme suresi latch'indeki ayni tuzak.
    return Karar(BASTIR, onceki)


def _sure_metni(fark: timedelta) -> str:
    saat = int(fark.total_seconds() // 3600)
    if saat < 1:
        return f"{int(fark.total_seconds() // 60)} dakika"
    if saat < 48:
        return f"{saat} saat"
    return f"{saat // 24} gun"


def bildir(kod: str, mesaj: str, gonder, dosya: Path = DURUM_DOSYASI,
           simdi: datetime | None = None,
           aralik_saat: int = VARSAYILAN_ARALIK_SAAT) -> Karar:
    """Karari uygular: gerekiyorsa gonderir, durumu her halukarda yazar.

    `gonder` enjekte edilir - testler ag'a cikmaz.
    """
    simdi = simdi or simdi_utc()
    karar = karar_ver(kod, durumu_oku(dosya), simdi, aralik_saat)
    if karar.bildirilecek:
        govde = f"{karar.onek}\n\n{mesaj}" if karar.onek else mesaj
        gonder(govde)
    durumu_yaz(karar.yeni_kayit, dosya)
    return karar


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Tekrarlayan hata bildirimini bastirarak Telegram'a yollar")
    ayristirici.add_argument("--kod", default="",
                             help="hata kodu; bos birakilirsa 'cozuldu' islenir")
    ayristirici.add_argument("--mesaj", default="", help="gonderilecek metin")
    argumanlar = ayristirici.parse_args()

    # Gec import: notify ag katmanini cekiyor, testler bu modulu onsuz kullanir.
    from notify import TelegramHatasi, env_oku, mesaj_gonder

    ortam = env_oku()

    def gonder(metin: str) -> None:
        try:
            mesaj_gonder(metin, ortam)
        except TelegramHatasi as hata:
            print(f"UYARI - hata bildirimi gonderilemedi: {hata}", file=sys.stderr)

    karar = bildir(argumanlar.kod, argumanlar.mesaj or argumanlar.kod, gonder)
    print(f"Hata bildirimi: {karar.durum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
