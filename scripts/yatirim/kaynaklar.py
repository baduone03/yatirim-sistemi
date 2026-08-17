"""Dis veri kaynaklari: BTCTurk, CoinGecko, TCMB EVDS + ucgenleme.

Neden ayri modul: fetch.py Yahoo tarafini tutuyor ve zaten ~250 satir. Uc
HTTP istemcisi + ucgenleme mantigi oraya eklenseydi dosya 500 satiri asardi.

NE YAPAR, NE YAPMAZ
  BTCTurk `/api/v2/ticker` ANLIK fiyattir, gecmis seri vermez. Bu yuzden
  yalnizca DEGERLEME fiyatini ezer. Korelasyon, volatilite ve beta hala
  Yahoo'nun 365 gunluk serisinden hesaplanir. Yani bir varligin degeri
  BTCTurk'ten, getirisi Yahoo'dan gelir - rapor bunu acikca yazar.

Tum ag cagrilari `getir` parametresinden gecer; testler kendi sahte
fonksiyonunu enjekte eder, ag'a cikilmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

ZAMAN_ASIMI = 15
TCMB_SERI_ALANI = "TP_DK_USD_A"


class KaynakHatasi(RuntimeError):
    """Dis kaynak okunamadi. Cagiran yedege dusmeye karar verir."""


def http_json(url: str, params: dict | None = None,
              headers: dict | None = None) -> dict:
    """Varsayilan ag katmani. Testlerde bu fonksiyon YERINE sahte gecirilir."""
    try:
        cevap = requests.get(url, params=params, headers=headers,
                             timeout=ZAMAN_ASIMI)
        cevap.raise_for_status()
    except requests.RequestException as hata:
        raise KaynakHatasi(f"{url} okunamadi: {hata}") from hata

    # HTTP 200 + HTML, "anahtar gecersiz" ile karistirilmamali. Sunucu web
    # arayuzunu donduruyorsa istek kimlik dogrulama katmanina HIC ulasmamistir;
    # sorun anahtarda degil, uc nokta adresindedir. Bu ayrimi yapmayan bir
    # hata mesaji saatlerce yanlis yerde anahtar aratir.
    govde = cevap.text.lstrip()
    if govde[:1] == "<":
        raise KaynakHatasi(
            f"{url} JSON degil HTML dondurdu (HTTP {cevap.status_code}). "
            "Uc nokta adresi degismis olabilir - anahtari degil ADRESI "
            "kontrol et. Adres varliklar.yaml icinde, kodda degil."
        )
    try:
        return cevap.json()
    except ValueError as hata:
        raise KaynakHatasi(f"{url} JSON dondurmedi: {hata}") from hata


@dataclass(frozen=True)
class AnlikFiyat:
    """Tek bir anlik kotasyon."""

    sembol: str
    deger: float
    zaman: datetime
    kaynak: str

    def gecikme_dakika(self, simdi: datetime | None = None) -> float:
        simdi = simdi or datetime.now(timezone.utc)
        return (simdi - self.zaman).total_seconds() / 60.0

    def bayat_mi(self, esik_dakika: float, simdi: datetime | None = None) -> bool:
        return self.gecikme_dakika(simdi) > esik_dakika


# --------------------------------------------------------------------------
# BTCTurk - kripto birincil kaynagi
# --------------------------------------------------------------------------

def btcturk_fiyatlari(url: str, ciftler: dict[str, str], getir=http_json,
                      ) -> dict[str, AnlikFiyat]:
    """BTCTurk ticker -> {portfoy_sembolu: AnlikFiyat}.

    TL cifti (BTCTRY) DOGRUDAN alinir. BTC/USD alip kurla carpmak cift
    cevrim demektir: hem BTC/USD hem USD/TRY hatasini tasirsin, ustelik
    Turkiye'deki gercek islem fiyatini degil turetilmis bir fiyati raporlarsin.

    `timestamp` milisaniye cinsindendir - saniye sanip cevirmek tarihi
    1970'e goturur ve her fiyat "bayat" cikar.
    """
    ham = getir(url)
    kayitlar = ham.get("data") or []
    cift_ters = {tl_cifti: sembol for sembol, tl_cifti in ciftler.items()}

    fiyatlar: dict[str, AnlikFiyat] = {}
    for kayit in kayitlar:
        sembol = cift_ters.get(kayit.get("pair"))
        if sembol is None:
            continue
        try:
            deger = float(kayit["last"])
            zaman = datetime.fromtimestamp(float(kayit["timestamp"]) / 1000.0,
                                           tz=timezone.utc)
        except (KeyError, TypeError, ValueError) as hata:
            raise KaynakHatasi(
                f"BTCTurk {kayit.get('pair')} kaydi okunamadi: {hata}") from hata
        if deger <= 0:
            raise KaynakHatasi(f"BTCTurk {kayit.get('pair')} fiyati pozitif degil")
        fiyatlar[sembol] = AnlikFiyat(sembol, deger, zaman, "btcturk")
    return fiyatlar


# --------------------------------------------------------------------------
# CoinGecko - yalnizca DOGRULAMA. Degerlemeye girmez.
# --------------------------------------------------------------------------

def coingecko_usd(url: str, kimlikler: dict[str, str],
                  getir=http_json) -> dict[str, float]:
    """CoinGecko USD fiyatlari. Rolu yalnizca ucgenlemede referans olmak.

    Bu deger HICBIR kosulda degerlemeye girmez: girseydi kripto fiyati bazen
    BTCTurk'ten bazen CoinGecko'dan gelir, portfoy degeri kaynaga gore
    ziplardi.
    """
    if not kimlikler:
        return {}
    ham = getir(url, params={"ids": ",".join(sorted(set(kimlikler.values()))),
                             "vs_currencies": "usd"})
    sonuc: dict[str, float] = {}
    for sembol, kimlik in kimlikler.items():
        deger = (ham.get(kimlik) or {}).get("usd")
        if deger is None:
            continue
        sonuc[sembol] = float(deger)
    return sonuc


# --------------------------------------------------------------------------
# TCMB EVDS - USD/TRY birincil kaynagi, Yahoo yedek
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class KurKotasyonu:
    deger: float
    tarih: date
    kaynak: str

    def bayat_mi(self, esik_gun: int, bugun: date | None = None) -> bool:
        return ((bugun or date.today()) - self.tarih).days > esik_gun


def tcmb_usdtry(url: str, seri: str, anahtar: str, gun: int = 10,
                getir=http_json, bugun: date | None = None) -> KurKotasyonu:
    """TCMB EVDS'ten en son yayimlanan USD/TRY.

    TCMB kuru yalnizca IS GUNLERI, ~15:30'da yayimlanir. Hafta sonu ve resmi
    tatilde yeni kur YOKTUR. Bu yuzden tek gun degil bir aralik istenir ve
    donen en son kayit alinir; kaydin TARIHI de dondurulur ki cagiran
    bayatligi olcebilsin. Cuma kurunu Pazar gunu taze sanmak, kriptodaki
    "TR primi" olcumunu tamamen bozar - olculen sey prim degil kurun
    bayatligi olur.
    """
    bugun = bugun or date.today()
    basla = bugun - timedelta(days=gun)
    ham = getir(
        f"{url}/series={seri}&startDate={basla:%d-%m-%Y}"
        f"&endDate={bugun:%d-%m-%Y}&type=json",
        headers={"key": anahtar},
    )
    kayitlar = [k for k in (ham.get("items") or []) if k.get(TCMB_SERI_ALANI)]
    if not kayitlar:
        raise KaynakHatasi(
            f"TCMB EVDS {seri} icin {basla}..{bugun} araliginda veri dondurmedi")
    son = kayitlar[-1]
    try:
        return KurKotasyonu(
            deger=float(son[TCMB_SERI_ALANI]),
            tarih=datetime.strptime(son["Tarih"], "%d-%m-%Y").date(),
            kaynak="tcmb",
        )
    except (KeyError, ValueError) as hata:
        raise KaynakHatasi(f"TCMB EVDS kaydi okunamadi: {hata}") from hata


# --------------------------------------------------------------------------
# Ucgenleme
# --------------------------------------------------------------------------

TAMAM = "tamam"
PRIM = "prim"
DURDUR = "durdur"
OLCULEMEDI = "olculemedi"


@dataclass(frozen=True)
class Ucgenleme:
    """Tek bir kripto varliginin uc kaynakli capraz kontrolu."""

    sembol: str
    durum: str                    # TAMAM | PRIM | DURDUR | OLCULEMEDI
    gerekce: str
    tl_fiyat: float | None = None
    beklenen_tl: float | None = None
    tr_primi: float | None = None      # ISARETLI: + ise TL tarafi pahali
    kur_kaynagi: str = ""

    @property
    def sapma(self) -> float | None:
        """Mutlak sapma - esik karsilastirmasi bunun uzerinden yapilir."""
        return None if self.tr_primi is None else abs(self.tr_primi)


@dataclass(frozen=True)
class UcgenlemeAyarlari:
    prim_esigi: float = 0.03
    durdurma_esigi: float = 0.08
    btcturk_bayatlik_dakika: float = 15.0
    tcmb_bayatlik_gun: int = 1


def ucgenle(sembol: str, tl_fiyat: AnlikFiyat | None, usd_fiyat: float | None,
            kur: KurKotasyonu | None, ayarlar: UcgenlemeAyarlari,
            simdi: datetime | None = None) -> Ucgenleme:
    """Uc kaynagi capraz kontrol eder.

    OLCULEMEDI ile DURDUR farkli seylerdir ve karistirilmamalidir:
      OLCULEMEDI = kaynaklardan biri yok/bayat. Bu bir piyasa bulgusu degil,
                   bizim korlugumuz. Rapor uretilmeye devam eder, yalnizca
                   bu sembol dogrulanmamis sayilir.
      DURDUR     = uc kaynak da TAZE ve aralarinda gercek bir kopukluk var.
                   Bu bir piyasa bulgusudur ve rapor uretilmez.
    Ayrimi yapmazsak CoinGecko'nun bir dakikalik hikkirigi tum gunun
    raporunu (BIST, altin, Nasdaq dahil) sildirir.
    """
    if tl_fiyat is None:
        return Ucgenleme(sembol, OLCULEMEDI, "BTCTurk fiyati alinamadi")
    if tl_fiyat.bayat_mi(ayarlar.btcturk_bayatlik_dakika, simdi):
        gecikme = tl_fiyat.gecikme_dakika(simdi)
        return Ucgenleme(
            sembol, OLCULEMEDI,
            f"BTCTurk fiyati {gecikme:.0f} dk bayat "
            f"(esik {ayarlar.btcturk_bayatlik_dakika:.0f} dk)",
            tl_fiyat=tl_fiyat.deger,
        )
    if usd_fiyat is None:
        return Ucgenleme(sembol, OLCULEMEDI, "CoinGecko fiyati alinamadi",
                         tl_fiyat=tl_fiyat.deger)
    if kur is None:
        return Ucgenleme(sembol, OLCULEMEDI, "USD/TRY kuru alinamadi",
                         tl_fiyat=tl_fiyat.deger)

    beklenen = usd_fiyat * kur.deger
    if beklenen <= 0:
        return Ucgenleme(sembol, OLCULEMEDI, "beklenen TL fiyati pozitif degil",
                         tl_fiyat=tl_fiyat.deger)

    prim = (tl_fiyat.deger - beklenen) / beklenen
    ortak = {
        "tl_fiyat": tl_fiyat.deger,
        "beklenen_tl": beklenen,
        "tr_primi": prim,
        "kur_kaynagi": kur.kaynak,
    }
    if abs(prim) > ayarlar.durdurma_esigi:
        return Ucgenleme(
            sembol, DURDUR,
            f"sapma %{abs(prim) * 100:.1f} > durdurma esigi "
            f"%{ayarlar.durdurma_esigi * 100:.0f}", **ortak)
    if abs(prim) > ayarlar.prim_esigi:
        return Ucgenleme(
            sembol, PRIM,
            f"TR primi %{prim * 100:+.1f} (esik "
            f"%{ayarlar.prim_esigi * 100:.0f})", **ortak)
    return Ucgenleme(sembol, TAMAM, f"sapma %{prim * 100:+.1f}", **ortak)


@dataclass(frozen=True)
class UcgenlemeSonucu:
    sonuclar: dict[str, Ucgenleme] = field(default_factory=dict)
    uyarilar: list[str] = field(default_factory=list)

    @property
    def durduranlar(self) -> list[Ucgenleme]:
        return [u for u in self.sonuclar.values() if u.durum == DURDUR]

    @property
    def primliler(self) -> list[Ucgenleme]:
        return [u for u in self.sonuclar.values() if u.durum == PRIM]

    @property
    def dogrulanmayanlar(self) -> list[Ucgenleme]:
        return [u for u in self.sonuclar.values() if u.durum == OLCULEMEDI]

    def degerleme_fiyatlari(self) -> dict[str, float]:
        """DURDUR olanlar disarida - fiyati var ama guvenilmez."""
        return {
            u.sembol: u.tl_fiyat for u in self.sonuclar.values()
            if u.tl_fiyat is not None and u.durum in (TAMAM, PRIM)
        }
