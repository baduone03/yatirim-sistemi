"""Sinyal uretimi ve frenler: histerezis, bekleme suresi, devre kesici, log.

Hepsi tek bir soruya bakiyor: ayni bilgi kac kere islem onerisine donusur?

Esik TEK bir sayi oldugunda deger esigin etrafinda salinirken her kosuda ters
sinyal cikar - komisyon oder, pozisyon degismez. Bu modul dort fren koyar:

  1. Histerezis  - sinyal tetik esiginde acilir, geri donus esigine kadar
                   inmeden kapanmaz. Ters yon icin tetigi YENIDEN asmak sart.
  2. Bekleme     - ayni sembolde son sinyalden N saat gecmeden ikincisi cikmaz.
  3. Devre kesici- gunluk sinyal sayisi tavani asarsa HICBIRI uretilmez.
  4. Gonderim logu - ayni mesaj iki kere gonderilmez.

Ilk uc frenin hafizasi `sinyal-durumu.yaml`, dorduncunun `gonderilen.log`.
Ikisi de makine uretir ve Actions repoya commit eder - yoksa her kosu sifirdan
baslar ve latch hicbir zaman "acik" durumunu hatirlamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import yaml

from config import PROJE_DIZINI, hafta_sonu_mu, simdi_utc  # noqa: F401
from duyarlilik import SEBEP_EKONOMIK, SEBEP_PARAMETRE, SEBEP_TASIMA

DURUM_DOSYASI = PROJE_DIZINI / "sinyal-durumu.yaml"
GONDERILEN_LOG = PROJE_DIZINI / "gonderilen.log"

SINIF = "sinif"
SEMBOL = "sembol"

AZALT = "azalt"
ARTIR = "artir"
KIS = "kis"

# Bastirma sebepleri. Bos sebep = sinyal acik.
DENGEDE = "dengede"
EKSIK_MALIYET = "SINYAL YOK (eksik maliyet)"
PARAMETRE_BELIRSIZLIGI = "PARAMETRE BELIRSIZLIGI"
MALIYET_YUTUYOR = "MALIYET YUTUYOR"
TASIMA_BELIRSIZLIGI = "TASIMA MALIYETI BELIRSIZLIGI"

# Duyarlilik modulu KOD dondurur, etiketi bu tablo secer. Eskiden sebep
# etiket metninde "belirsizligi" arayarak bulunuyordu; ucuncu bir sebep
# eklendiginde o eslestirme sessizce yanlis etiket uretti.
SEBEP_ETIKETLERI = {
    SEBEP_PARAMETRE: PARAMETRE_BELIRSIZLIGI,
    SEBEP_TASIMA: TASIMA_BELIRSIZLIGI,
    SEBEP_EKONOMIK: MALIYET_YUTUYOR,
}
BEKLEME = "BEKLEME"
DEVRE_KESICI = "DEVRE KESICI"
HAFTA_SONU = "HAFTA SONU (yalnizca uyari)"


@dataclass(frozen=True)
class SinyalSonucu:
    """Bir sinif/sembol icin nihai karar: sinyal ya da bastirma sebebi."""

    tur: str
    ad: str
    yon: str = ""
    sebep: str = ""
    kalan_saat: float = 0.0        # BEKLEME ise kalan sure
    detay: str = ""                # belirsizlikte sorumlu parametreler

    @property
    def acik(self) -> bool:
        return not self.sebep

    @property
    def etiket(self) -> str:
        if self.sebep == BEKLEME:
            return f"{BEKLEME} ({self.kalan_saat:.0f} saat)"
        if self.sebep and self.detay:
            return f"{self.sebep}: {self.detay}"
        return self.sebep


@dataclass(frozen=True)
class SinyalDurumu:
    """Bir sinif/sembolun latch durumu ve son URETILEN sinyalin zamani.

    `son_sinyal` yalnizca sinyal gercekten uretildiginde guncellenir. Bastirilan
    bir sinyal saati ilerletirse bekleme suresi kendi kendini uzatir ve sembol
    bir daha asla sinyal uretmez.
    """

    acik: bool = False
    yon: str = ""
    son_sinyal: str = ""

    @property
    def sozluk(self) -> dict:
        return {"acik": self.acik, "yon": self.yon, "son_sinyal": self.son_sinyal}


BOS_DURUM = SinyalDurumu()


@dataclass(frozen=True)
class SinyalGecmisi:
    siniflar: dict[str, SinyalDurumu] = field(default_factory=dict)
    semboller: dict[str, SinyalDurumu] = field(default_factory=dict)
    gun: str = ""
    gunluk_sayi: int = 0
    uyarilar: list[str] = field(default_factory=list)

    def durum(self, tur: str, ad: str) -> SinyalDurumu:
        harita = self.siniflar if tur == SINIF else self.semboller
        return harita.get(ad, BOS_DURUM)

    def bugunku_sayi(self, bugun: str) -> int:
        """Sayac gun degisince sifirlanir - tarih damgasi bunun icin var."""
        return self.gunluk_sayi if self.gun == bugun else 0


@dataclass(frozen=True)
class Karar:
    """Tum sinif/sembollerin sonucu + yazilacak yeni gecmis."""

    sonuclar: dict[tuple[str, str], SinyalSonucu]
    gecmis: SinyalGecmisi
    devre_kesildi: bool = False
    gunluk_sayi: int = 0
    gunluk_maks: int = 0
    uyarilar: list[str] = field(default_factory=list)

    def sonuc(self, tur: str, ad: str) -> SinyalSonucu | None:
        return self.sonuclar.get((tur, ad))

    def acik_mi(self, tur: str, ad: str) -> bool:
        sonuc = self.sonuc(tur, ad)
        return sonuc is not None and sonuc.acik

    def sinyaller(self, tur: str = "") -> list[SinyalSonucu]:
        return [s for s in self.sonuclar.values()
                if s.acik and (not tur or s.tur == tur)]

    def sebepli(self, sebep: str) -> list[SinyalSonucu]:
        return [s for s in self.sonuclar.values() if s.sebep == sebep]

    @property
    def hafta_sonu_uyarilari(self) -> list[SinyalSonucu]:
        """Esigi asti ama hafta sonu genis esigini asmadi.

        Bunlar bastirilmis sinyal DEGIL, sinifi dusurulmus sinyaldir: islem
        onerisi olarak gitmez, uyari olarak gider.
        """
        return self.sebepli(HAFTA_SONU)


def _kalan_saat(durum: SinyalDurumu, simdi: datetime, bekleme_saat: float) -> float:
    """Bekleme suresinden kalan saat. 0 = bekleme yok."""
    if bekleme_saat <= 0 or not durum.son_sinyal:
        return 0.0
    onceki = datetime.fromisoformat(durum.son_sinyal)
    gecen = (simdi - onceki).total_seconds() / 3600.0
    return max(bekleme_saat - gecen, 0.0)


def _kapilar(tur: str, ad: str, yon: str, onceki: SinyalDurumu, gecti_genis: bool,
             maliyet, sinyal_acik, simdi, bekleme_saat,
             duyarlilik=None, dayanikli=None, belirsizlik="",
             sebep_kodu="") -> SinyalSonucu:
    """Esik asildiktan SONRAKI kapilar.

    Sira: hafta sonu -> eksik maliyet -> parametre belirsizligi -> bekleme.

    Hafta sonu ilk sirada cunku digerlerinden farkli bir sey soyluyor: bu bir
    bastirma degil, sinyalin SINIFININ dusurulmesi. Ince likiditede islem
    onerisi vermek yerine uyari veriyoruz.

    Eksik maliyet, parametre belirsizliginden ONCE gelir: ikisi de maliyetin
    bilinmedigini soyler ama eksik kalem hakkinda hicbir sey soylenemez,
    tahminli kalem hakkinda "su parametreyi olc" denebilir. Once daha karanlik
    olani raporlanir; aksi halde olculebilir bir oneri, olculemez bir boslugu
    gizler.
    """
    if not gecti_genis:
        return SinyalSonucu(tur, ad, yon, HAFTA_SONU)
    if maliyet is not None and not sinyal_acik():
        return SinyalSonucu(tur, ad, yon, EKSIK_MALIYET)
    if duyarlilik is not None and not dayanikli():
        # Uc ayri sebep, uc ayri yapilacak is:
        #   PARAMETRE  - islem maliyeti senaryolar arasi karari ceviriyor -> OLC
        #   TASIMA     - basabas suresi planlanani asabiliyor -> OLC veya sureyi uzat
        #   EKONOMIK   - maliyet kesin olarak sapmadan buyuk -> BUYUT veya CIK
        # Tek etikete toplamak, olculemez bir durumu "su sayiyi olc" onerisiyle
        # karistirirdi.
        return SinyalSonucu(tur, ad, yon,
                            SEBEP_ETIKETLERI.get(sebep_kodu(),
                                                 PARAMETRE_BELIRSIZLIGI),
                            detay=belirsizlik)
    kalan = _kalan_saat(onceki, simdi, bekleme_saat)
    if kalan > 0:
        return SinyalSonucu(tur, ad, yon, BEKLEME, kalan)
    return SinyalSonucu(tur, ad, yon)


def _sinif_sonucu(sapma, esikler, maliyet, gecmis, simdi, bekleme_saat,
                  hafta_sonu: bool, duyarlilik=None
                  ) -> tuple[SinyalSonucu, SinyalDurumu]:
    onceki = gecmis.durum(SINIF, sapma.sinif)
    yon = AZALT if sapma.sapma > 0 else ARTIR
    # Ters yon geri donus esigini KULLANMAZ: +2 puandan -2 puana gecen bir
    # sinif, tetigi (3 puan) hic asmadan ters islem onerisi uretmemeli.
    latch = onceki.acik and onceki.yon == yon
    if not esikler.sapma_asildi(sapma.sapma, latch):
        return (SinyalSonucu(SINIF, sapma.sinif, sebep=DENGEDE),
                replace(onceki, acik=False, yon=""))

    yeni = replace(onceki, acik=True, yon=yon)
    genis = esikler.sapma_asildi(sapma.sapma, latch, hafta_sonu)
    return _kapilar(SINIF, sapma.sinif, yon, onceki, genis, maliyet,
                    lambda: maliyet.sinif_sinyali_acik(sapma.sinif),
                    simdi, bekleme_saat, duyarlilik,
                    lambda: duyarlilik.sinif_sinyali_acik_mi(sapma.sinif),
                    duyarlilik.sinif_etiketi(sapma.sinif) if duyarlilik else "",
                    lambda: duyarlilik.sinif_sebep_kodu(sapma.sinif)), yeni


def _sembol_sonucu(varlik_riski, esikler, maliyet, gecmis, simdi, bekleme_saat,
                   hafta_sonu: bool, duyarlilik=None
                   ) -> tuple[SinyalSonucu, SinyalDurumu]:
    sembol = varlik_riski.sembol
    onceki = gecmis.durum(SEMBOL, sembol)
    if not esikler.kisilmali(varlik_riski, onceki.acik):
        return (SinyalSonucu(SEMBOL, sembol, sebep=DENGEDE),
                replace(onceki, acik=False, yon=""))

    yeni = replace(onceki, acik=True, yon=KIS)
    genis = esikler.kisilmali(varlik_riski, onceki.acik, hafta_sonu)
    return _kapilar(SEMBOL, sembol, KIS, onceki, genis, maliyet,
                    lambda: maliyet.sinyal_acik(sembol),
                    simdi, bekleme_saat, duyarlilik,
                    lambda: duyarlilik.sinyal_acik_mi(sembol),
                    duyarlilik.etiket(sembol) if duyarlilik else "",
                    lambda: duyarlilik.sebep_kodu(sembol)), yeni


def kararlari_uret(sapmalar, risk, esikler, bekleme, devre_kesici,
                   gecmis: SinyalGecmisi, bugun: str, maliyet=None,
                   simdi: datetime | None = None, duyarlilik=None) -> Karar:
    """Tek karar noktasi.

    Esik testi iki yerde (rapor + Telegram) ayri ayri yapilsaydi biri
    bastirirken digeri sinyal gosterirdi. FAZ 3'te bu hata iki kez yasandi;
    burada esik BIR kere olculur, iki renderer yalnizca sonucu okur.
    """
    simdi = simdi or simdi_utc()
    # Hafta sonu esigi GENISLER. Kripto 7/24 acik ama likiditesi ince; ustelik
    # BIST ve Nasdaq kapali oldugu icin hafta sonunda tum siniflarin agirligini
    # tek basina kripto oynatir. Yani genisletme her sinifa uygulanir ama
    # pratikte yalnizca kriptoyu isirir.
    hafta_sonu = hafta_sonu_mu(simdi)
    sonuclar: dict[tuple[str, str], SinyalSonucu] = {}
    # Mevcut gecmisin UZERINE yazilir, sifirdan kurulmaz: veri boslugu yuzunden
    # bir kosuda risk raporuna girmeyen sembolun latch'i ve bekleme saati
    # kaybolmamali. Sifirdan kurulsaydi tek gunluk bir veri kesintisi tum
    # frenleri sifirlardi.
    yeni_siniflar = dict(gecmis.siniflar)
    yeni_semboller = dict(gecmis.semboller)

    for sapma in sapmalar:
        sonuc, durum = _sinif_sonucu(sapma, esikler, maliyet, gecmis, simdi,
                                     bekleme.ayni_sembol_saat, hafta_sonu,
                                     duyarlilik)
        sonuclar[(SINIF, sapma.sinif)] = sonuc
        yeni_siniflar[sapma.sinif] = durum

    for varlik_riski in risk.varlik_riskleri:
        sonuc, durum = _sembol_sonucu(varlik_riski, esikler, maliyet, gecmis,
                                      simdi, bekleme.ayni_sembol_saat, hafta_sonu,
                                      duyarlilik)
        sonuclar[(SEMBOL, varlik_riski.sembol)] = sonuc
        yeni_semboller[varlik_riski.sembol] = durum

    onceki_sayi = gecmis.bugunku_sayi(bugun)
    adaylar = [s for s in sonuclar.values() if s.acik]
    gunluk_sayi = onceki_sayi + len(adaylar)
    devre_kesildi = gunluk_sayi > devre_kesici.gunluk_maks_islem
    if devre_kesildi:
        # Sinyal URETILMEZ ama sayac ilerlemez: kosul surdukce alarm her
        # kosuda yeniden calar. Sayac ilerlerse devre bir daha asla kapanmaz.
        sonuclar = {anahtar: (replace(sonuc, sebep=DEVRE_KESICI)
                              if sonuc.acik else sonuc)
                    for anahtar, sonuc in sonuclar.items()}

    damga = simdi.isoformat(timespec="seconds")
    for sonuc in sonuclar.values():
        if not sonuc.acik:
            continue
        harita = yeni_siniflar if sonuc.tur == SINIF else yeni_semboller
        harita[sonuc.ad] = replace(harita[sonuc.ad], son_sinyal=damga)

    return Karar(
        sonuclar=sonuclar,
        gecmis=SinyalGecmisi(
            siniflar=yeni_siniflar,
            semboller=yeni_semboller,
            gun=bugun,
            gunluk_sayi=onceki_sayi if devre_kesildi else gunluk_sayi,
        ),
        devre_kesildi=devre_kesildi,
        gunluk_sayi=gunluk_sayi,
        gunluk_maks=devre_kesici.gunluk_maks_islem,
        uyarilar=list(gecmis.uyarilar),
    )


def _durumlari_ayristir(ham: dict, etiket: str, uyarilar: list[str]
                        ) -> dict[str, SinyalDurumu]:
    """Bozuk zaman damgasi olan kaydi ATAR ve uyari birakir.

    Sessizce 0 dondurmek yerine atmak sart: bozuk damga ya beklemeyi sonsuza
    kilitler ya da tamamen devre disi birakir; ikisi de gorunmez olmamali.
    """
    durumlar: dict[str, SinyalDurumu] = {}
    for ad, kayit in (ham or {}).items():
        damga = str((kayit or {}).get("son_sinyal", ""))
        if damga:
            try:
                datetime.fromisoformat(damga)
            except ValueError:
                uyarilar.append(
                    f"{DURUM_DOSYASI.name}: {etiket}.{ad}.son_sinyal cozulemedi "
                    f"('{damga}') - kayit yok sayildi, bekleme suresi sifirlandi.")
                damga = ""
        durumlar[ad] = SinyalDurumu(
            acik=bool((kayit or {}).get("acik", False)),
            yon=str((kayit or {}).get("yon", "")),
            son_sinyal=damga,
        )
    return durumlar


def gecmisi_oku(dosya: Path = DURUM_DOSYASI) -> SinyalGecmisi:
    """Dosya yoksa bos gecmis doner - ilk kosu latch'i kapali baslatir."""
    if not dosya.exists():
        return SinyalGecmisi()
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    uyarilar: list[str] = []
    return SinyalGecmisi(
        siniflar=_durumlari_ayristir(ham.get("siniflar"), "siniflar", uyarilar),
        semboller=_durumlari_ayristir(ham.get("semboller"), "semboller", uyarilar),
        gun=str(ham.get("gun", "")),
        gunluk_sayi=int(ham.get("gunluk_sayi", 0)),
        uyarilar=uyarilar,
    )


def _yazilacaklar(durumlar: dict[str, SinyalDurumu]) -> dict[str, dict]:
    """Bilgi tasimayan kayit YAZILMAZ.

    Kapali ve hic sinyal uretmemis bir kayit varsayilanla ayni; 80 satir
    `acik: false` yazmak dosyayi okunmaz yapar. Kapali ama zaman damgasi olan
    kayit KALIR - bekleme suresi latch kapandiktan sonra da isler.
    """
    return {ad: durum.sozluk for ad, durum in sorted(durumlar.items())
            if durum.acik or durum.son_sinyal}


def gecmisi_yaz(gecmis: SinyalGecmisi, dosya: Path = DURUM_DOSYASI) -> None:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    govde = yaml.safe_dump(
        {
            "gun": gecmis.gun,
            "gunluk_sayi": gecmis.gunluk_sayi,
            "siniflar": _yazilacaklar(gecmis.siniflar),
            "semboller": _yazilacaklar(gecmis.semboller),
        },
        allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    dosya.write_text(
        "# MAKINE URETIR - elle duzenleme.\n"
        "# Histerezis latch'i, bekleme suresi saati ve gunluk sinyal sayaci.\n"
        "# Silinirse latch kapali baslar: acik bir sinyal tetik esigini\n"
        "# yeniden asmak zorunda kalir (tek seferlik gurultu, veri kaybi degil).\n"
        f"{govde}",
        encoding="utf-8",
    )


def ozet_anahtari(tarih: str) -> str:
    return f"ozet:{tarih}"


def islem_anahtari(sembol: str, yon: str, simdi: datetime) -> str:
    return f"islem:{sembol}:{simdi.date().isoformat()}:{simdi.hour:02d}:{yon}"


def karar_anahtarlari(karar: Karar, simdi: datetime) -> list[str]:
    return [islem_anahtari(s.ad, s.yon, simdi) for s in karar.sinyaller()]


def gonderim_kayitlari(dosya: Path = GONDERILEN_LOG) -> list[tuple[datetime, str]]:
    """Log satiri: '<gonderim zamani> <anahtar>'. Anahtar son alandir.

    Cozulemeyen zaman damgasi olan satir ATLANIR - anahtari da sayilmaz;
    idempotency'de bozuk satiri "gonderilmemis" saymak en fazla bir mesaji
    tekrarlar, hiz siniri hesabinda ise sayiyi eksik gosterirdi.
    """
    if not dosya.exists():
        return []
    kayitlar = []
    for satir in dosya.read_text(encoding="utf-8").splitlines():
        alanlar = satir.split()
        if len(alanlar) < 2 or satir.lstrip().startswith("#"):
            continue
        try:
            kayitlar.append((datetime.fromisoformat(alanlar[0]), alanlar[-1]))
        except ValueError:
            continue
    return kayitlar


def gonderilen_anahtarlar(dosya: Path = GONDERILEN_LOG) -> set[str]:
    return {anahtar for _, anahtar in gonderim_kayitlari(dosya)}


def gonderildi_yaz(anahtarlar: list[str], simdi: datetime,
                   dosya: Path = GONDERILEN_LOG) -> None:
    """Append-only. Gonderim BASARILI olduktan sonra cagrilir.

    Once yazip sonra gonderirsek basarisiz gonderim "gonderildi" isaretlenir ve
    mesaj bir daha asla denenmez.
    """
    if not anahtarlar:
        return
    dosya.parent.mkdir(parents=True, exist_ok=True)
    damga = simdi.isoformat(timespec="seconds")
    with dosya.open("a", encoding="utf-8") as akis:
        for anahtar in anahtarlar:
            akis.write(f"{damga} {anahtar}\n")
