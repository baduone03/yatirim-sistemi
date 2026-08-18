"""Bildirim kanali: hiz siniri, sessiz saatler, 4096 karakter bolme.

Tek gonderim kapisi. Sikligi artirmanin bedeli mesaj enflasyonudur: gunde 20
bildirim alan biri hicbirini okumaz, uyarilar gurultuye karisir ve sistem
sessizce ise yaramaz hale gelir. Uc kural bunu engelliyor:

  1. Hiz siniri  - saatte N mesajdan fazlasi tek bir ozete BIRLESTIRILIR.
  2. Sessiz saat - gece bildirimi birikir, sabah tek mesaj olarak gider.
  3. 4096 bolme - Telegram siniri; bolunmezse mesaj HIC gitmez.

Biriken bildirimler `bildirim-kuyrugu.yaml` icinde diskte tutulur. Kuyruk
commit edilmezse sessiz saatte biriken her sey bir sonraki kosuda kaybolur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

import yaml

from config import PROJE_DIZINI, TR_OFSET
from piyasa import Takvim, takvimi_coz
from sinyal import GONDERILEN_LOG, gonderim_kayitlari

AYAR_DOSYASI = PROJE_DIZINI / "bildirim.yaml"
KUYRUK_DOSYASI = PROJE_DIZINI / "bildirim-kuyrugu.yaml"

# Telegram sendMessage siniri. Bolme payi: HTML etiketi ortadan kesilmesin.
TELEGRAM_SINIRI = 4096
BOLME_PAYI = 96

# Sessiz saatler YEREL saattir; UTC uzerinden hesaplanirsa gece 01:00 yasagi
# 04:00'te baslar. TR_OFSET config.py'da, piyasa.py ile paylasilir.

GONDERILDI = "gonderildi"
BIRIKTIRILDI = "biriktirildi"
ATLANDI = "atlandi"


@dataclass(frozen=True)
class BildirimAyarlari:
    saatlik_maks_mesaj: int = 5
    sessiz_baslangic: time = time(1, 0)
    sessiz_bitis: time = time(8, 0)
    takvim: Takvim = field(default_factory=Takvim)

    def yerel(self, an: datetime) -> time:
        return (an + TR_OFSET).time()

    def sessiz_mi(self, an: datetime) -> bool:
        """Gece yarisini asan araligi da dogru cozer (01:00-08:00 asmaz,
        23:00-07:00 asar)."""
        saat = self.yerel(an)
        if self.sessiz_baslangic <= self.sessiz_bitis:
            return self.sessiz_baslangic <= saat < self.sessiz_bitis
        return saat >= self.sessiz_baslangic or saat < self.sessiz_bitis


@dataclass(frozen=True)
class Bildirim:
    """Gonderilecek tek bildirim. `anahtar` idempotency anahtaridir."""

    tip: str
    anahtar: str
    metin: str
    olusma: str = ""

    @property
    def sozluk(self) -> dict:
        return {"tip": self.tip, "anahtar": self.anahtar,
                "metin": self.metin, "olusma": self.olusma}


@dataclass(frozen=True)
class GonderimSonucu:
    durum: str
    gonderilen: int = 0
    kuyruk: list[Bildirim] = field(default_factory=list)


def _saati_coz(ham, varsayilan: time) -> time:
    if ham is None:
        return varsayilan
    if isinstance(ham, time):
        return ham
    saat, _, dakika = str(ham).partition(":")
    return time(int(saat), int(dakika or 0))


def ayarlari_oku(dosya: Path = AYAR_DOSYASI) -> BildirimAyarlari:
    """Dosya yoksa varsayilanlar. Sessiz saat/hiz siniri olmadan da calisir -
    yalnizca fren yok demektir, sistem durmaz."""
    if not dosya.exists():
        return BildirimAyarlari()
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    hiz = ham.get("hiz_siniri") or {}
    sessiz = ham.get("sessiz_saatler") or {}
    ayarlar = BildirimAyarlari(
        saatlik_maks_mesaj=int(hiz.get("saatlik_maks_mesaj", 5)),
        sessiz_baslangic=_saati_coz(sessiz.get("baslangic"), time(1, 0)),
        sessiz_bitis=_saati_coz(sessiz.get("bitis"), time(8, 0)),
        takvim=takvimi_coz(ham.get("takvim")),
    )
    if ayarlar.saatlik_maks_mesaj < 1:
        raise ValueError(
            "bildirim.yaml -> hiz_siniri.saatlik_maks_mesaj en az 1 olmali, "
            f"{ayarlar.saatlik_maks_mesaj} geldi (0 = hicbir mesaj gitmez)")
    if ayarlar.sessiz_baslangic == ayarlar.sessiz_bitis:
        raise ValueError(
            "bildirim.yaml -> sessiz_saatler baslangic ve bitis ayni "
            f"({ayarlar.sessiz_baslangic}); bu 24 saat sessizlik demek. "
            "Sessiz saat istemiyorsan blogu tamamen sil.")
    return ayarlar


def kuyrugu_oku(dosya: Path = KUYRUK_DOSYASI) -> list[Bildirim]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    return [Bildirim(tip=str(k.get("tip", "")), anahtar=str(k.get("anahtar", "")),
                     metin=str(k.get("metin", "")), olusma=str(k.get("olusma", "")))
            for k in (ham.get("bekleyenler") or [])]


def kuyrugu_yaz(bildirimler: list[Bildirim], dosya: Path = KUYRUK_DOSYASI) -> None:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    govde = yaml.safe_dump({"bekleyenler": [b.sozluk for b in bildirimler]},
                           allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=10_000)
    dosya.write_text(
        "# MAKINE URETIR - elle duzenleme.\n"
        "# Sessiz saatte veya hiz siniri asilirken biriken bildirimler.\n"
        "# Silinirse biriken bildirimler kaybolur, sistem durmaz.\n"
        f"{govde}",
        encoding="utf-8",
    )


def son_saatteki_gonderim(simdi: datetime, log: Path = GONDERILEN_LOG) -> int:
    """Son 60 dakikada giden mesaj sayisi.

    `ozet:`/`islem:` ayrimi YAPILMAZ: hiz siniri okuyanin dikkatini korur,
    mesajin turu bunu degistirmez. Ek anahtarlar da ayni mesajla gittigi icin
    yalnizca birincil anahtarlarin sayilmasi gerekir - bunu cagiran taraf
    saglar (`gonderildi_yaz` her mesaj icin bir birincil anahtar yazar).
    """
    esik = simdi - timedelta(hours=1)
    return sum(1 for zaman, anahtar in gonderim_kayitlari(log)
               if zaman >= esik and not anahtar.startswith("islem:"))


def bol(metin: str, sinir: int = TELEGRAM_SINIRI) -> list[str]:
    """4096 siniri asan mesaji satir sinirlarinda boler.

    Bolunmeyen mesaj Telegram tarafindan REDDEDILIR - yani uzun ozet hic
    gitmez. Bolme satir bazlidir: bir tablo satirinin ortasindan kesmek
    mesaji okunmaz yapar. Tek satir tek basina siniri asarsa (olmamali)
    ham kesilir, cunku gondermemektense kesmek yeglenir.
    """
    if len(metin) <= sinir:
        return [metin]
    pay = sinir - BOLME_PAYI
    parcalar, mevcut = [], ""
    for satir in metin.split("\n"):
        while len(satir) > pay:
            if mevcut:
                parcalar.append(mevcut)
                mevcut = ""
            parcalar.append(satir[:pay])
            satir = satir[pay:]
        aday = f"{mevcut}\n{satir}" if mevcut else satir
        if len(aday) > pay:
            parcalar.append(mevcut)
            mevcut = satir
        else:
            mevcut = aday
    if mevcut:
        parcalar.append(mevcut)
    toplam = len(parcalar)
    return [f"{p}\n\n<i>({i}/{toplam})</i>" for i, p in enumerate(parcalar, 1)]


def birlestir(bildirimler: list[Bildirim], baslik: str) -> str:
    """Biriken bildirimleri TEK mesaja cevirir.

    Ayri ayri gondermek hiz sinirinin varlik sebebini ortadan kaldirir;
    birlestirilmis mesaj hem sinira uyar hem okunur kalir.
    """
    satirlar = [f"<b>{baslik}</b>", f"{len(bildirimler)} bildirim birikti.", ""]
    for sira, bildirim in enumerate(bildirimler, 1):
        satirlar.append(f"<b>— {sira}. {bildirim.tip} —</b>")
        satirlar.append(bildirim.metin)
        satirlar.append("")
    return "\n".join(satirlar).rstrip()
