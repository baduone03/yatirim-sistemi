"""Uc sinifli maliyet modeli: islem, tasima, firsat.

TEMEL KURAL: bilinmeyen kalem `null` kalir, sifir SAYILMAZ. Bilinmeyen bir
maliyeti sifir varsaymak sessiz basarisizligin en tehlikeli turudur - sistem
hata vermez, yalnizca karsiz bir islemi karli gosterir. Bu yuzden eksik kalemi
olan varlik icin ISLEM SINYALI URETILMEZ; rapor uretilmeye devam eder.

SIFIR ile NULL ayrimi kritik:
    0.0  = olculdu, sifir cikti   (hisse senedinin fon gider orani yoktur)
    None = bilinmiyor             (kur spread'i platformdan sorulmadi)

Bu modul saf hesaptir: YAML okumaz, aga cikmaz. Ham sozlukten model kurmak
icin `modeli_kur`, canli oranlari baglamak icin `MaliyetModeli.oranlarla`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

ORANSAL = "oransal"
SABIT = "sabit"
GUN_YIL = 365.0


# --------------------------------------------------------------------------
# Islem maliyeti (gidis-donus, bir kez)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IslemProfili:
    """Bir islem yeri/araci icin gidis-donus maliyet kalemleri."""

    ad: str
    komisyon_tip: str = ORANSAL
    komisyon_oran: float | None = None
    komisyon_usd: float | None = None
    kur_cevrimi: bool | None = None
    kur_spread_tek_yon: float | None = None
    kambiyo_vergisi: float | None = None
    menkul_spread: float | None = None

    @property
    def eksik_kalemler(self) -> list[str]:
        """Bilinmeyen kalemlerin adlari. Bos liste = model tam.

        Hangi kalemin ZORUNLU oldugu profilin kendi beyanina baglidir:
        oransal komisyonda `komisyon_usd` sorulmaz, kur cevrimi olmayan bir
        profilde spread ve kambiyo vergisi sorulmaz. Boylece "uygulanmaz" ile
        "bilinmiyor" birbirine karismaz.
        """
        eksik: list[str] = []
        if self.komisyon_tip == SABIT:
            if self.komisyon_usd is None:
                eksik.append(f"{self.ad}.komisyon_usd")
        elif self.komisyon_oran is None:
            eksik.append(f"{self.ad}.komisyon_oran")

        if self.kur_cevrimi is None:
            eksik.append(f"{self.ad}.kur_cevrimi")
        elif self.kur_cevrimi:
            if self.kur_spread_tek_yon is None:
                eksik.append(f"{self.ad}.kur_spread_tek_yon")
            if self.kambiyo_vergisi is None:
                eksik.append(f"{self.ad}.kambiyo_vergisi")

        if self.menkul_spread is None:
            eksik.append(f"{self.ad}.menkul_spread")
        return eksik

    def gidis_donus(self, pozisyon_try: float, usdtry: float) -> float | None:
        """Gidis-donus islem maliyeti orani. Eksik kalem varsa None.

        c(X) = komisyon_payi + 2*kur_spread + kambiyo_vergisi + 2*menkul_spread

        Sabit komisyon pozisyon buyudukce oransal olarak KUCULUR; kur spread'i
        ve kambiyo vergisi oransaldir, ASLA kuculmez. Bu yuzden ABD islemlerinin
        pozisyon boyutlandirmasiyla asilamayan bir maliyet TABANI vardir.
        """
        if self.eksik_kalemler or pozisyon_try <= 0:
            return None
        if self.komisyon_tip == SABIT:
            komisyon = (2 * self.komisyon_usd * usdtry) / pozisyon_try
        else:
            komisyon = 2 * self.komisyon_oran
        spread = 2 * (self.kur_spread_tek_yon or 0.0) if self.kur_cevrimi else 0.0
        vergi = (self.kambiyo_vergisi or 0.0) if self.kur_cevrimi else 0.0
        return komisyon + spread + vergi + 2 * self.menkul_spread


# --------------------------------------------------------------------------
# Tasima maliyeti (yillik, surekli)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TasimaKalemleri:
    """Tuttugun her gun isleyen maliyetler. Bilesiktir; uzun vadede
    tek seferlik islem maliyetini gecer."""

    sembol: str
    beyan_edildi: bool = True
    gider_orani_yillik: float | None = None
    temettu_verimi: float | None = None
    temettu_stopaji: float | None = None

    @property
    def eksik_kalemler(self) -> list[str]:
        if not self.beyan_edildi:
            return [f"{self.sembol}.tasima (hic beyan edilmemis)"]
        eksik: list[str] = []
        if self.gider_orani_yillik is None:
            eksik.append(f"{self.sembol}.gider_orani_yillik")
        if self.temettu_verimi is None:
            eksik.append(f"{self.sembol}.temettu_verimi")
        # Temettu odemeyen varlikta stopaj sorusu DUSER - sorulursa altin ve
        # kripto sonsuza kadar bloklu kalir.
        elif self.temettu_verimi > 0 and self.temettu_stopaji is None:
            eksik.append(f"{self.sembol}.temettu_stopaji")
        return eksik

    @property
    def yillik(self) -> float | None:
        """h = gider_orani + temettu_verimi * stopaj_orani"""
        if self.eksik_kalemler:
            return None
        return self.gider_orani_yillik + self.temettu_verimi * (self.temettu_stopaji or 0.0)


# --------------------------------------------------------------------------
# Varlik basina birlesik durum
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class VarlikMaliyeti:
    sembol: str
    sinif: str
    profil: IslemProfili | None
    tasima: TasimaKalemleri

    @property
    def eksik_kalemler(self) -> list[str]:
        if self.profil is None:
            profil_eksigi = [f"{self.sinif} sinifi icin islem maliyeti profili tanimsiz"]
        else:
            profil_eksigi = self.profil.eksik_kalemler
        return profil_eksigi + self.tasima.eksik_kalemler

    @property
    def sinyal_acik(self) -> bool:
        return not self.eksik_kalemler


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MaliyetModeli:
    varliklar: dict[str, VarlikMaliyeti] = field(default_factory=dict)
    tl_risksiz_yillik: float | None = None
    risksiz_kaynagi: str = "yapilandirma"
    risksiz_serisi: str = ""
    risksiz_bayatlik_gun: int = 21
    enflasyon_yillik: float | None = None
    enflasyon_kaynagi: str = "yapilandirma"
    enflasyon_serisi: str = ""
    enflasyon_bayatlik_gun: int = 45
    nakit_stopaji: float | None = None
    uyarilar: list[str] = field(default_factory=list)

    def oranlarla(self, risksiz: tuple[float, str] | None,
                  enflasyon: tuple[float, str] | None,
                  uyarilar: list[str]) -> MaliyetModeli:
        """Canli okunan oranlarla YENI model doner - mevcut model degismez.

        Canli okuma basarisizsa yapilandirmadaki yedek deger korunur. TCMB'nin
        bir gunluk kesintisi hurdle rate'i sifirlamamali; sifirlarsa her
        pozitif getiri yeniden "basari" gorunur.
        """
        yeni = replace(self, uyarilar=[*self.uyarilar, *uyarilar])
        if risksiz is not None:
            yeni = replace(yeni, tl_risksiz_yillik=risksiz[0], risksiz_kaynagi=risksiz[1])
        if enflasyon is not None:
            yeni = replace(yeni, enflasyon_yillik=enflasyon[0],
                           enflasyon_kaynagi=enflasyon[1])
        return yeni

    def sinyal_acik(self, sembol: str) -> bool:
        varlik = self.varliklar.get(sembol)
        return varlik.sinyal_acik if varlik else False

    @property
    def engellenenler(self) -> dict[str, list[str]]:
        return {s: v.eksik_kalemler for s, v in sorted(self.varliklar.items())
                if not v.sinyal_acik}

    @property
    def eksik_kalem_ozeti(self) -> dict[str, list[str]]:
        """Kalem -> etkilenen semboller. Telegram ozeti icin.

        Varlik bazli liste her gun 11 ayni satir basar ve okunmaz hale gelir;
        okunmayan uyari yok hukmundedir. Kalem bazli grup "su 4 sayiyi gir"
        diye somut is cikarir. Tasima kalemleri sembol onekinden arindirilir
        (`THYAO.IS.temettu_verimi` -> `temettu_verimi`), islem kalemleri
        profil onekini KORUR - hangi profilin duzeltilecegi bilgi tasir.
        """
        ozet: dict[str, list[str]] = {}
        for sembol, kalemler in self.engellenenler.items():
            for kalem in kalemler:
                ozet.setdefault(_kalem_adi(sembol, kalem), []).append(sembol)
        return dict(sorted(ozet.items(), key=lambda k: (-len(k[1]), k[0])))

    def sinif_sinyali_acik(self, sinif: str) -> bool:
        """Sinif duzeyinde rebalancing tavsiyesi verilebilir mi?

        Tavsiye ancak sinifta uygulanabilir en az bir varlik varsa anlamlidir:
        "bist'i 2.000 TL azalt" demek, o sinifta satilabilecek bir sembol
        gerektirir. Hepsi blokluysa tavsiye uygulanamaz bir emirdir.
        """
        adaylar = [v for v in self.varliklar.values() if v.sinif == sinif]
        if not adaylar:
            # Nakit gibi sembolu olmayan sinif: kendi basina islem gormez,
            # digerlerinin karsi tarafidir. En az bir sinif acikken anlamli.
            return any(v.sinyal_acik for v in self.varliklar.values())
        return any(v.sinyal_acik for v in adaylar)

    def gidis_donus(self, sembol: str, pozisyon_try: float,
                    usdtry: float) -> float | None:
        varlik = self.varliklar.get(sembol)
        if varlik is None or varlik.profil is None:
            return None
        return varlik.profil.gidis_donus(pozisyon_try, usdtry)

    def yillik_tasima(self, sembol: str) -> float | None:
        varlik = self.varliklar.get(sembol)
        return None if varlik is None else varlik.tasima.yillik


def modeli_kur(ham: dict, sinif_haritasi: dict[str, str]) -> MaliyetModeli:
    """varliklar.yaml -> MaliyetModeli. Ag'a cikmaz, yalnizca ayristirir."""
    maliyet_ham = ham.get("maliyet") or {}
    profil_haritasi = maliyet_ham.get("sinif_profili") or {}
    islem_ham = maliyet_ham.get("islem") or {}
    tasima_ham = maliyet_ham.get("tasima") or {}
    firsat_ham = maliyet_ham.get("firsat") or {}
    nakit_ham = ham.get("nakit") or {}
    enflasyon_ham = ham.get("enflasyon") or {}

    profiller = {
        ad: IslemProfili(
            ad=ad,
            komisyon_tip=str(k.get("komisyon_tip", ORANSAL)),
            komisyon_oran=_sayi(k.get("komisyon_oran")),
            komisyon_usd=_sayi(k.get("komisyon_usd")),
            kur_cevrimi=k.get("kur_cevrimi"),
            kur_spread_tek_yon=_sayi(k.get("kur_spread_tek_yon")),
            kambiyo_vergisi=_sayi(k.get("kambiyo_vergisi")),
            menkul_spread=_sayi(k.get("menkul_spread")),
        )
        for ad, k in islem_ham.items()
    }

    varliklar = {}
    for sembol, sinif in sinif_haritasi.items():
        kalem = tasima_ham.get(sembol)
        varliklar[sembol] = VarlikMaliyeti(
            sembol=sembol,
            sinif=sinif,
            profil=profiller.get(profil_haritasi.get(sinif, "")),
            tasima=TasimaKalemleri(
                sembol=sembol,
                beyan_edildi=kalem is not None,
                gider_orani_yillik=_sayi((kalem or {}).get("gider_orani_yillik")),
                temettu_verimi=_sayi((kalem or {}).get("temettu_verimi")),
                temettu_stopaji=_sayi((kalem or {}).get("temettu_stopaji")),
            ),
        )

    return MaliyetModeli(
        varliklar=varliklar,
        tl_risksiz_yillik=_sayi(firsat_ham.get("tl_risksiz_yillik")),
        risksiz_serisi=str(firsat_ham.get("tcmb_serisi", "")),
        risksiz_bayatlik_gun=int(firsat_ham.get("bayatlik_gun", 21)),
        enflasyon_yillik=_sayi(enflasyon_ham.get("yillik")),
        enflasyon_serisi=str(enflasyon_ham.get("tcmb_serisi", "")),
        enflasyon_bayatlik_gun=int(enflasyon_ham.get("bayatlik_gun", 45)),
        nakit_stopaji=_sayi(nakit_ham.get("stopaj")),
    )


def _sayi(deger) -> float | None:
    return None if deger is None else float(deger)


def _kalem_adi(sembol: str, kalem: str) -> str:
    onek = f"{sembol}."
    return kalem[len(onek):] if kalem.startswith(onek) else kalem


# --------------------------------------------------------------------------
# Getiri matematigi
# --------------------------------------------------------------------------

def donem_orani(yillik: float, gun: float) -> float:
    """Yillik orani `gun` gunluk doneme indirger. BILESIK.

    Dogrusal olcekleme (yillik * gun/365) yuksek faiz ortaminda kisa donemde
    fark etmez ama uzun donemde ciddi sapar; ayni formulu her yerde kullanmak
    tutarliligi garanti eder.
    """
    if gun <= 0:
        return 0.0
    return (1.0 + yillik) ** (gun / GUN_YIL) - 1.0


def asiri_getiri(nominal: float, risksiz: float) -> float:
    """Hurdle rate duzeltmesi. Sifira gore pozitif ama risksize gore
    negatif bir portfoy BASARISIZ portfoydur."""
    return nominal - risksiz


def reel_getiri(nominal: float, enflasyon: float) -> float:
    """Enflasyon duzeltmesi - CARPIMSAL, toplamsal degil.

    Toplamsal (nominal - enflasyon) yaklasimi dusuk enflasyonda kabul edilebilir
    hata verir; %25-50 bandinda ciddi sapar. %40 nominal / %25 enflasyonda
    toplamsal %15 der, dogrusu %12.0'dir.
    """
    return (1.0 + nominal) / (1.0 + enflasyon) - 1.0


# --------------------------------------------------------------------------
# Maliyet dagilimi (brut -> net -> asiri)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MaliyetKalemi:
    ad: str
    oran: float | None            # None = OLCULEMEDI, 0.0 = olculdu ve sifir
    aciklama: str = ""

    @property
    def olculdu(self) -> bool:
        return self.oran is not None


@dataclass(frozen=True)
class MaliyetDagilimi:
    """Brut getiriden asiri getiriye giden yol. Olculmeyen maliyet optimize
    edilemez; bu tablo hangi kalemin canini yaktigini gorunur kilar."""

    brut_getiri: float
    kalemler: list[MaliyetKalemi]
    risksiz: float
    donem_gun: int

    @property
    def olculen_maliyet(self) -> float:
        return sum(k.oran for k in self.kalemler if k.olculdu)

    @property
    def eksik_kalemler(self) -> list[str]:
        return [k.ad for k in self.kalemler if not k.olculdu]

    @property
    def net_getiri(self) -> float:
        """UST SINIR: olculemeyen kalemler bunu yalnizca ASAGI ceker.

        Eksik kalemleri sifir sayip "net getiri" demek, tam da modelin
        kapatmaya calistigi hatadir - bu yuzden deger tek basina degil,
        "ust sinir" etiketiyle raporlanir.
        """
        return self.brut_getiri - self.olculen_maliyet

    @property
    def asiri_getiri(self) -> float:
        return asiri_getiri(self.net_getiri, self.risksiz)
