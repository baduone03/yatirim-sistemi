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
from datetime import datetime, time

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

    def yerel(self, an: datetime) -> datetime:
        return an + TR_OFSET

    def acik_seanslar(self, an: datetime) -> list[str]:
        yerel = self.yerel(an)
        return [s.ad for s in self.seanslar if s.acik_mi(yerel)]

    def gorev(self, an: datetime) -> str:
        """Bu kosunun isi. Sira onemli: gun sonu brifingi ezmez cunku ikisi
        farkli saatlerde, ama cakisirlarsa gun sonu daha bilgilendirici."""
        yerel = self.yerel(an)
        if yerel.time() >= self.gun_sonu_saati:
            # Haftalik, gun sonunu EZER: haftalik ozet gunun kapanisini da
            # icerir. Ikisi ayri gitseydi Cuma aksami neredeyse ayni iki
            # mesaj arka arkaya duserdi.
            if yerel.weekday() == self.haftalik_gunu:
                return HAFTALIK
            return GUN_SONU
        if self._brifing_gunu_mu(yerel) and self._brifing_penceresi(yerel):
            return BRIFING
        return TARAMA

    def _brifing_gunu_mu(self, yerel: datetime) -> bool:
        return (self.brifing_gunu == HER_GUN_KODU
                or yerel.weekday() == self.brifing_gunu)

    def _brifing_penceresi(self, yerel: datetime) -> bool:
        """Brifing saatinden sonraki bir saat. Cron gecikirse kacirmasin.

        Tam saat esitligi arasaydik Actions cron'unun 5-30 dakikalik gecikmesi
        brifingi her hafta dusururdu.
        """
        baslangic = self.brifing_saati
        gecen = ((yerel.hour - baslangic.hour) * 60
                 + (yerel.minute - baslangic.minute))
        return 0 <= gecen < 60


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
    )
