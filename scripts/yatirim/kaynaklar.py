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
              headers: dict | None = None) -> dict | list:
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


@dataclass(frozen=True)
class TcmbKaydi:
    seri: str
    deger: float
    tarih: date

    def bayat_mi(self, esik_gun: int, bugun: date | None = None) -> bool:
        return ((bugun or date.today()) - self.tarih).days > esik_gun


# Aylik seriler tarihi "AGUSTOS 2026" gibi yazar, gunluk seriler "07-08-2026".
_AYLAR = {
    "OCAK": 1, "SUBAT": 2, "MART": 3, "NISAN": 4, "MAYIS": 5, "HAZIRAN": 6,
    "TEMMUZ": 7, "AGUSTOS": 8, "EYLUL": 9, "EKIM": 10, "KASIM": 11, "ARALIK": 12,
}
_TR_HARFLER = str.maketrans("ŞİĞÜÖÇşiğüöç", "SIGUOCSIGUOC")


def _tcmb_tarihi(ham: str) -> date:
    """TCMB tarihini cozer. Aylik seride ayin ILK gunu alinir.

    Ilk gun bilincli: aylik veriyi oldugundan TAZE gostermek, bayat bir
    enflasyon rakamini guncel sanmak demektir. Yanlis tarafa yuvarliyoruz.
    """
    metin = str(ham).strip()
    try:
        return datetime.strptime(metin, "%d-%m-%Y").date()
    except ValueError:
        pass
    parcalar = metin.translate(_TR_HARFLER).upper().split()
    if len(parcalar) == 2 and parcalar[0] in _AYLAR:
        return date(int(parcalar[1]), _AYLAR[parcalar[0]], 1)
    raise KaynakHatasi(f"TCMB tarihi cozulemedi: '{ham}'")


def tcmb_kayitlari(url: str, getir=http_json) -> dict[str, TcmbKaydi]:
    """TCMB'nin "sik kullanilan seriler" ucu -> {seri_kodu: TcmbKaydi}.

    ANAHTAR GEREKMIYOR - bilincli secim. Eski `/service/evds/series=...` yolu
    (anahtar isteyen) 2026 arayuz gecisiyle JSON dondurmeyi birakti; bu uc
    ayni verileri kimliksiz veriyor. Sirri gerekmeyen bir yere gondermemek,
    gondermekten iyidir.

    Uctan yalnizca birkac seri doner (USD, EUR, mevduat faizi, TUFE beklentisi
    vb.). Tam EVDS seri arsivi `POST /fe` ucundadir ve WAF arkasindadir -
    tarayici disindan cekilemez.
    """
    ham = getir(url)
    kayitlar: dict[str, TcmbKaydi] = {}
    for kayit in ham or []:
        kod = kayit.get("seriKodu")
        if not kod or kod in kayitlar:
            continue          # ilk kayit en gunceli
        try:
            kayitlar[kod] = TcmbKaydi(
                seri=kod,
                deger=float(kayit["deger"]),
                tarih=_tcmb_tarihi(kayit["tarih"]),
            )
        except (KeyError, TypeError, ValueError) as hata:
            raise KaynakHatasi(f"TCMB {kod} kaydi okunamadi: {hata}") from hata
    return kayitlar


def tcmb_usdtry(url: str, seri: str, getir=http_json) -> KurKotasyonu:
    """Guncel USD/TRY.

    Kaydin TARIHI de dondurulur ki cagiran bayatligi olcebilsin: TCMB kuru
    yalnizca is gunu yayimlanir, hafta sonu yeni kur yoktur. Cuma kurunu
    Pazar gunu taze sanmak "TR primi" olcumunu bozar - olculen sey prim
    degil kurun bayatligi olur.
    """
    kayitlar = tcmb_kayitlari(url, getir)
    kayit = kayitlar.get(seri)
    if kayit is None:
        raise KaynakHatasi(
            f"TCMB {seri} serisi cevapta yok. Donen seriler: {sorted(kayitlar)[:6]}")
    return KurKotasyonu(deger=kayit.deger, tarih=kayit.tarih, kaynak="tcmb")


def tcmb_yuzde_orani(kayitlar: dict[str, TcmbKaydi], seri: str,
                     bayatlik_gun: int, bugun: date | None = None,
                     ) -> tuple[float, str] | None:
    """Yuzde cinsinden yayimlanan seriyi ONDALIK orana cevirir (47.91 -> 0.4791).

    Ag'a CIKMAZ - onceden cekilmis kayitlar uzerinde calisir. Seri yoksa veya
    bayatsa None doner; cagiran yapilandirmadaki yedek degere duser.
    """
    kayit = kayitlar.get(seri)
    if kayit is None or kayit.bayat_mi(bayatlik_gun, bugun):
        return None
    return kayit.deger / 100.0, f"tcmb {seri} ({kayit.tarih.isoformat()})"


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
            simdi: datetime | None = None,
            kur_piyasasi_kapali: bool = False) -> Ucgenleme:
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
    if kur_piyasasi_kapali:
        # HAFTA SONU TUZAGI. Forex Cuma 22:00 - Pazar 22:00 UTC arasi kapali;
        # TCMB de is gunu disinda kur yayimlamaz. Yani hafta sonu kur DONMUS,
        # kripto ise hareket ediyor. Bu durumda "beklenen TL" Cuma kuruyla
        # hesaplanir ve BTCTurk'un canli TL fiyatiyla arasindaki fark TR primi
        # DEGIL, kurun bayatligidir.
        #
        # Bu ayrim 7/24 calismanin on kosulu: hafta sonu farki gercek kopukluk
        # sayilsaydi DURDUR cikar ve rapor hic uretilmezdi. OLCULEMEDI dogru
        # cevap - bizim korlugumuz, piyasa bulgusu degil.
        return Ucgenleme(
            sembol, OLCULEMEDI,
            "kur piyasasi kapali (hafta sonu) - TR primi olculemez, "
            "kripto hareket ederken USD/TRY donmus",
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
