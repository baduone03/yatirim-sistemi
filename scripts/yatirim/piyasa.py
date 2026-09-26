"""Piyasa takvimi: hangi seans acik, hangi kosu ne yapar.

TEK workflow var. Ayri workflow'lar (kripto/BIST/ABD) ayri checkout + pip
install ederdi ve Actions dakika butcesi ikiye katlanirdi; bunun yerine tek
cron gridi calisir ve script bu tabloya bakarak ne yapacagina karar verir.

Saatler YEREL (TR). Turkiye kalici UTC+3, yaz saati yok - bu yuzden sabit
ofset guvenli; DST uygulayan bir ulke olsaydi zoneinfo sart olurdu.

BU MODUL TAKVIM BILGISI VERMEZ: BIST tatilleri (bayram, resmi tatil) burada
tanimli DEGIL. Tatilde seans "acik" gorunur, ama fiyat verisi gelmedigi icin
bayatlik kontrolu (FiyatVerisi.bayat_semboller) zaten isaretler. Tatil takvimi
eklemek yerine bayatliga guvenmek bilincli: sabit tatil listesi her yil
elle guncellenmezse sessizce yanlislasir, bayatlik olcumu ise kendini duzeltir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from config import TR_OFSET

HER_GUN = "her_gun"
HAFTA_ICI = "hafta_ici"

GUN_SONU = "gun_sonu"
BRIFING = "brifing"
TARAMA = "tarama"
HAFTALIK = "haftalik"

# brifing_gunu bu degerdeyse brifing HER GUN calisir. Ayri bir bayrak
# ("brifing_gunluk_mu: true") eklemek iki alani tutarli tutma yuku getirirdi;
# tek alan, tek dogruluk kaynagi.
HER_GUN_KODU = -1


class Plan(NamedTuple):
    """Kosunun isi ve ozetin ait oldugu TR gunu.

    `gun` telafide DUNDUR: gece 02:00'de giden gun sonu ozeti dunun
    kapanisidir, anahtari ve rapor dosyasi da dunun adini tasir.
    """
    gorev: str
    gun: date


def gorev_anahtari(gorev: str, gun: date) -> str:
    """gonderilen.log anahtari. notify.gonder_gun_sonu ile AYNI bicim.

    Haftalik ozet gun sonunun YERINE gectigi icin onunla ayni anahtari
    paylasir - ikisi ayni gun ayri ayri gitmesin.
    """
    tur = "brifing" if gorev == BRIFING else "gunsonu"
    return f"{tur}:{gun.isoformat()}"


@dataclass(frozen=True)
class Seans:
    ad: str
    gunler: str
    baslangic: time
    bitis: time

    def acik_mi(self, yerel: datetime) -> bool:
        if self.gunler == HAFTA_ICI and yerel.weekday() >= 5:
            return False
        return self.baslangic <= yerel.time() <= self.bitis


@dataclass(frozen=True)
class Takvim:
    seanslar: list[Seans] = field(default_factory=list)
    gun_sonu_saati: time = time(23, 30)
    brifing_gunu: int = 0
    brifing_saati: time = time(9, 0)
    # Haftalik ozet gunu (datetime.weekday; 4 = Cuma). Gun sonu saatinde
    # calisir ve o gunun GUN_SONU'nun YERINE gecer - ikisini ayri ayri
    # gondermek ayni sayilari iki kez yollamak olurdu.
    haftalik_gunu: int = 4

    # Brifing saatinden sonra kac saat boyunca "bugunun brifingi gitmedi mi"
    # diye bakilir. 1 saat, cron birkac saat gecikince brifingi dusuruyordu
    # (2026-09-06 -> 09-26 arasi hic gitmedi); gonderilen.log kontrolu
    # tekrari engelledigi icin pencereyi genisletmek bedava.
    brifing_penceresi_saat: int = 1
    # Kacan gun sonu ozeti ertesi gun bu saate kadar TELAFI edilir. None =
    # brifing saati: dunun ozeti bugunun brifingiyle cakismasin.
    gun_sonu_telafi_bitis: time | None = None

    def yerel(self, an: datetime) -> datetime:
        return an + TR_OFSET

    def acik_seanslar(self, an: datetime) -> list[str]:
        yerel = self.yerel(an)
        return [s.ad for s in self.seanslar if s.acik_mi(yerel)]

    def gorev(self, an: datetime,
              yapilan: frozenset[str] | set[str] = frozenset()) -> str:
        return self.planla(an, yapilan).gorev

    def planla(self, an: datetime,
               yapilan: frozenset[str] | set[str] = frozenset()) -> Plan:
        """Bu kosunun isi. `yapilan`: gonderilmis VEYA kuyrukta bekleyen
        ozet anahtarlari (`gorev_anahtari`).

        GitHub zamanlanmis kosulari SAATLERCE geciktirebiliyor (2026-09'da
        `7 */2` gunde 12 yerine 5-6 kosu verdi). Sabit pencereye bagli ozet
        o pencereye kosu dusmezse sessizce kaybolur; bu yuzden pencere
        "gitmediyse ilk firsatta" mantigiyla calisir:
          - gun sonu esiginden sonra: bugunun gun sonu (gitmediyse)
          - ertesi gun telafi bitisine kadar: dunun gun sonu (gitmediyse)
          - brifing penceresinde: bugunun brifingi (gitmediyse)
        Ozet zaten gittiyse kosu TARAMA'dir - LLM onsozu ve rapor yeniden
        uretilmez (kosu 60 sn esigini asmasin).
        """
        yerel = self.yerel(an)
        bugun = yerel.date()
        if yerel.time() >= self.gun_sonu_saati:
            if gorev_anahtari(GUN_SONU, bugun) not in yapilan:
                return Plan(self._kapanis(bugun), bugun)
            return Plan(TARAMA, bugun)
        dun = bugun - timedelta(days=1)
        telafi_bitis = self.gun_sonu_telafi_bitis or self.brifing_saati
        if (yerel.time() < telafi_bitis
                and gorev_anahtari(GUN_SONU, dun) not in yapilan):
            return Plan(self._kapanis(dun), dun)
        if (self._brifing_gunu_mu(yerel) and self._brifing_penceresi(yerel)
                and gorev_anahtari(BRIFING, bugun) not in yapilan):
            return Plan(BRIFING, bugun)
        return Plan(TARAMA, bugun)

    def _kapanis(self, gun: date) -> str:
        # Haftalik, gun sonunu EZER: haftalik ozet gunun kapanisini da
        # icerir. Ikisi ayri gitseydi Cuma aksami neredeyse ayni iki
        # mesaj arka arkaya duserdi. Telafide de ozetin GUNUNE bakilir:
        # Cuma'nin kacan kapanisi Cumartesi sabahi yine haftaliktir.
        return HAFTALIK if gun.weekday() == self.haftalik_gunu else GUN_SONU

    def _brifing_gunu_mu(self, yerel: datetime) -> bool:
        return (self.brifing_gunu == HER_GUN_KODU
                or yerel.weekday() == self.brifing_gunu)

    def _brifing_penceresi(self, yerel: datetime) -> bool:
        """Brifing saatinden sonraki `brifing_penceresi_saat` saat, gun sonu
        esigine kadar. Cron gecikirse kacirmasin."""
        baslangic = self.brifing_saati
        gecen = ((yerel.hour - baslangic.hour) * 60
                 + (yerel.minute - baslangic.minute))
        return (0 <= gecen < self.brifing_penceresi_saat * 60
                and yerel.time() < self.gun_sonu_saati)


def _saat(ham, varsayilan: time) -> time:
    if ham is None:
        return varsayilan
    if isinstance(ham, time):
        return ham
    saat, _, dakika = str(ham).partition(":")
    return time(int(saat), int(dakika or 0))


def _gun(ham, alan: str) -> int:
    """Gun alani: 0-6 arasi sayi veya brifing icin 'her_gun'.

    Aralik disi sayi sessizce kabul edilseydi (ornegin 7) o gorev HIC
    calismazdi - haftanin hicbir gunu 7 degil. Sessiz devre disi kalma,
    hata vermekten cok daha pahali.
    """
    if str(ham) == HER_GUN:
        if alan != "brifing_gunu":
            raise ValueError(
                f"bildirim.yaml -> takvim.{alan} '{HER_GUN}' olamaz; "
                "yalnizca brifing her gun calisabilir.")
        return HER_GUN_KODU
    try:
        gun = int(ham)
    except (TypeError, ValueError):
        raise ValueError(
            f"bildirim.yaml -> takvim.{alan}: 0-6 arasi sayi bekleniyor, "
            f"'{ham}' geldi") from None
    if not 0 <= gun <= 6:
        raise ValueError(
            f"bildirim.yaml -> takvim.{alan}: 0-6 arasi olmali (0=Pazartesi), "
            f"{gun} geldi")
    return gun


def _pencere(ham) -> int:
    """Brifing penceresi, saat. 0 brifingi sessizce kapatirdi - hata ver."""
    try:
        saat = int(ham)
    except (TypeError, ValueError):
        raise ValueError(
            "bildirim.yaml -> takvim.brifing_penceresi_saat: tam sayi "
            f"bekleniyor, '{ham}' geldi") from None
    if not 1 <= saat <= 23:
        raise ValueError(
            "bildirim.yaml -> takvim.brifing_penceresi_saat: 1-23 arasi "
            f"olmali, {saat} geldi")
    return saat


def takvimi_coz(ham: dict | None) -> Takvim:
    """`bildirim.yaml -> takvim` blogunu cozer. Blok yoksa varsayilanlar."""
    ham = ham or {}
    seanslar = []
    for ad, kayit in (ham.get("seanslar") or {}).items():
        gunler = str((kayit or {}).get("gunler", HAFTA_ICI))
        if gunler not in (HER_GUN, HAFTA_ICI):
            raise ValueError(
                f"bildirim.yaml -> takvim.seanslar.{ad}.gunler "
                f"'{HER_GUN}' veya '{HAFTA_ICI}' olmali, '{gunler}' geldi")
        seans = Seans(
            ad=ad, gunler=gunler,
            baslangic=_saat((kayit or {}).get("baslangic"), time(0, 0)),
            bitis=_saat((kayit or {}).get("bitis"), time(23, 59)),
        )
        if seans.baslangic >= seans.bitis:
            raise ValueError(
                f"bildirim.yaml -> takvim.seanslar.{ad}: baslangic "
                f"({seans.baslangic}) bitisten ({seans.bitis}) kucuk olmali. "
                "Gece yarisini asan seans bu sistemde tanimsiz.")
        seanslar.append(seans)
    return Takvim(
        seanslar=sorted(seanslar, key=lambda s: s.ad),
        gun_sonu_saati=_saat(ham.get("gun_sonu_saati"), time(23, 30)),
        brifing_gunu=_gun(ham.get("brifing_gunu", 0), "brifing_gunu"),
        brifing_saati=_saat(ham.get("brifing_saati"), time(9, 0)),
        haftalik_gunu=_gun(ham.get("haftalik_gunu", 4), "haftalik_gunu"),
        brifing_penceresi_saat=_pencere(ham.get("brifing_penceresi_saat", 1)),
        gun_sonu_telafi_bitis=(_saat(ham["gun_sonu_telafi_bitis"], time(0, 0))
                               if ham.get("gun_sonu_telafi_bitis") else None),
    )
