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

import math
from dataclasses import dataclass, field, replace

ORANSAL = "oransal"
SABIT = "sabit"
GUN_YIL = 365.0

IYIMSER = "iyimser"
TEMEL = "temel"
KOTUMSER = "kotumser"
SENARYOLAR = (IYIMSER, TEMEL, KOTUMSER)


@dataclass(frozen=True)
class Tahmin:
    """Olculmemis bir kalemin uc senaryolu tahmini.

    `null` ile arasindaki fark: null "bilmiyorum, hicbir sey soyleyemem"
    demektir ve sinyali tamamen kapatir. Tahmin "olcmedim ama sinirlarini
    biliyorum" demektir - karar UC senaryoda da ayni cikiyorsa parametreyi
    olcmeden de guvenle islem yapilabilir. Karar degisiyorsa sinyal yine
    bastirilir; fark, artik HANGI sayinin olculmesi gerektiginin bilinmesi.

    Tek bir "ortalama" tahmine dusurmek bu ayrimi yok eder: ortalama daima
    bir karar uretir ve o kararin tahmine mi olcume mi dayandigi kaybolur.
    """

    iyimser: float
    temel: float
    kotumser: float
    kaynak: str = ""

    def deger(self, senaryo: str) -> float:
        if senaryo not in SENARYOLAR:
            raise ValueError(
                f"senaryo {' | '.join(SENARYOLAR)} olmali, '{senaryo}' geldi")
        return float(getattr(self, senaryo))

    @property
    def genislik(self) -> float:
        """Kotumser - iyimser. Belirsizligin buyuklugu."""
        return abs(self.kotumser - self.iyimser)


def _cozumle(deger, senaryo: str):
    """Tahmin ise senaryo degerine indirger, degilse oldugu gibi birakir."""
    return deger.deger(senaryo) if isinstance(deger, Tahmin) else deger


def _pozitif_olabilir(deger) -> bool:
    """Kalem sifirdan buyuk OLABILIR mi?

    Tahmin'de en KOTUMSER senaryoya bakilir: temettu verimi iyimserde 0 ama
    kotumserde %8 ise stopaj sorusu DUSMEZ. Iyimsere bakan bir kontrol,
    belirsiz bir kalemi "yapisal sifir" sayip stopaji sessizce atlardi.
    """
    if deger is None:
        return False
    return deger.kotumser > 0 if isinstance(deger, Tahmin) else deger > 0


def _senaryo_sec(senaryo: str, yalniz: str, alan: str) -> str:
    """Tek parametre oynatilirken digerleri TEMEL'de kalir."""
    if not yalniz:
        return senaryo
    return senaryo if alan == yalniz else TEMEL


# --------------------------------------------------------------------------
# Islem maliyeti (gidis-donus, bir kez)
# --------------------------------------------------------------------------

TAHMINLI_ISLEM_ALANLARI = ("komisyon_oran", "komisyon_usd",
                           "kur_spread_tek_yon", "kambiyo_vergisi",
                           "menkul_spread")
TAHMINLI_TASIMA_ALANLARI = ("gider_orani_yillik", "temettu_verimi",
                            "temettu_stopaji")


@dataclass(frozen=True)
class IslemProfili:
    """Bir islem yeri/araci icin gidis-donus maliyet kalemleri."""

    ad: str
    komisyon_tip: str = ORANSAL
    komisyon_oran: float | Tahmin | None = None
    komisyon_usd: float | Tahmin | None = None
    kur_cevrimi: bool | None = None
    kur_spread_tek_yon: float | Tahmin | None = None
    kambiyo_vergisi: float | Tahmin | None = None
    menkul_spread: float | Tahmin | None = None

    def senaryoyla(self, senaryo: str, yalniz: str = "") -> IslemProfili:
        return replace(self, **{
            alan: _cozumle(getattr(self, alan), _senaryo_sec(senaryo, yalniz, alan))
            for alan in TAHMINLI_ISLEM_ALANLARI})

    @property
    def tahminler(self) -> dict[str, Tahmin]:
        return {f"{self.ad}.{alan}": getattr(self, alan)
                for alan in TAHMINLI_ISLEM_ALANLARI
                if isinstance(getattr(self, alan), Tahmin)}

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

    @property
    def tahminli(self) -> bool:
        return bool(self.tahminler)

    def maliyet_tabani(self, senaryo: str = TEMEL) -> float | None:
        """Pozisyon buyuklugunden BAGIMSIZ maliyet. Eksik kalem varsa None.

        Oransal kalemler (kur spread'i, kambiyo vergisi, menkul spread ve
        oransal komisyon) pozisyon buyudukce KUCULMEZ. Yani bu sayi, pozisyon
        ne kadar buyutulurse buyutulsun asilamayan bir TABANDIR. Yalnizca
        SABIT komisyon disarida kalir - tek kuculebilen kalem odur.
        """
        cozulmus = self.senaryoyla(senaryo) if self.tahminli else self
        if cozulmus.eksik_kalemler:
            return None
        komisyon = 0.0 if cozulmus.komisyon_tip == SABIT else 2 * cozulmus.komisyon_oran
        spread = 2 * (cozulmus.kur_spread_tek_yon or 0.0) if cozulmus.kur_cevrimi else 0.0
        vergi = (cozulmus.kambiyo_vergisi or 0.0) if cozulmus.kur_cevrimi else 0.0
        return komisyon + spread + vergi + 2 * cozulmus.menkul_spread

    def minimum_pozisyon(self, esik: float, usdtry: float,
                         senaryo: str = TEMEL) -> float | None:
        """Gidis-donus maliyetini `esik` altina indiren en kucuk pozisyon (TL).

        Doner:
          None      - kalem eksik, hesaplanamaz
          0.0       - her buyuklukte zaten esigin altinda
          math.inf  - TABAN esigi asiyor; pozisyonu buyutmek ISE YARAMAZ
          sayi      - bu buyuklugun ustunde islem ekonomik olur

        Sabit komisyon pozisyona BOLUNUR, oransal kalemler bolunmez:
            2*komisyon_usd*usdtry / P + taban = esik
        """
        taban = self.maliyet_tabani(senaryo)
        if taban is None:
            return None
        if taban >= esik:
            return math.inf
        if self.komisyon_tip != SABIT:
            return 0.0
        cozulmus = self.senaryoyla(senaryo) if self.tahminli else self
        return 2 * cozulmus.komisyon_usd * usdtry / (esik - taban)

    def gidis_donus(self, pozisyon_try: float, usdtry: float) -> float | None:
        """Gidis-donus islem maliyeti orani. Eksik kalem varsa None.

        c(X) = komisyon_payi + 2*kur_spread + kambiyo_vergisi + 2*menkul_spread

        Sabit komisyon pozisyon buyudukce oransal olarak KUCULUR; kur spread'i
        ve kambiyo vergisi oransaldir, ASLA kuculmez. Bu yuzden ABD islemlerinin
        pozisyon boyutlandirmasiyla asilamayan bir maliyet TABANI vardir.
        """
        if self.eksik_kalemler or pozisyon_try <= 0:
            return None
        # Tahminli kalem TEMEL senaryoya indirgenir: ham Tahmin nesnesiyle
        # aritmetik TypeError verir. Senaryo bazli hesap icin cagiran taraf
        # zaten modeli `senaryoyla` ile cozer.
        birim = self.senaryoyla(TEMEL) if self.tahminli else self
        if birim.komisyon_tip == SABIT:
            komisyon = (2 * birim.komisyon_usd * usdtry) / pozisyon_try
        else:
            komisyon = 2 * birim.komisyon_oran
        spread = 2 * (birim.kur_spread_tek_yon or 0.0) if birim.kur_cevrimi else 0.0
        vergi = (birim.kambiyo_vergisi or 0.0) if birim.kur_cevrimi else 0.0
        return komisyon + spread + vergi + 2 * birim.menkul_spread


# --------------------------------------------------------------------------
# Tasima maliyeti (yillik, surekli)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TasimaKalemleri:
    """Tuttugun her gun isleyen maliyetler. Bilesiktir; uzun vadede
    tek seferlik islem maliyetini gecer."""

    sembol: str
    beyan_edildi: bool = True
    gider_orani_yillik: float | Tahmin | None = None
    temettu_verimi: float | Tahmin | None = None
    temettu_stopaji: float | Tahmin | None = None

    def senaryoyla(self, senaryo: str, yalniz: str = "") -> TasimaKalemleri:
        return replace(self, **{
            alan: _cozumle(getattr(self, alan), _senaryo_sec(senaryo, yalniz, alan))
            for alan in TAHMINLI_TASIMA_ALANLARI})

    @property
    def tahminler(self) -> dict[str, Tahmin]:
        return {f"{self.sembol}.{alan}": getattr(self, alan)
                for alan in TAHMINLI_TASIMA_ALANLARI
                if isinstance(getattr(self, alan), Tahmin)}

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
        # kripto sonsuza kadar bloklu kalirdi. Tahminli verimde OLCUT
        # kotumser senaryodur, bkz. _pozitif_olabilir.
        elif _pozitif_olabilir(self.temettu_verimi) and self.temettu_stopaji is None:
            eksik.append(f"{self.sembol}.temettu_stopaji")
        return eksik

    @property
    def yillik(self) -> float | None:
        """h = gider_orani + temettu_verimi * stopaj_orani

        Tahminli kalem TEMEL senaryoya indirgenir. Ham `Tahmin` nesnesiyle
        carpma yapmak TypeError verirdi; sessizce None donmek ise olculmus
        bir kalemi olculmemis gostermek olurdu.
        """
        if self.eksik_kalemler:
            return None
        cozulmus = self.senaryoyla(TEMEL)
        return (cozulmus.gider_orani_yillik
                + cozulmus.temettu_verimi * (cozulmus.temettu_stopaji or 0.0))


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

    @property
    def tahminler(self) -> dict[str, Tahmin]:
        profil = self.profil.tahminler if self.profil else {}
        return {**profil, **self.tasima.tahminler}

    def senaryoyla(self, senaryo: str, yalniz: str = "") -> VarlikMaliyeti:
        return replace(
            self,
            profil=self.profil.senaryoyla(senaryo, yalniz) if self.profil else None,
            tasima=self.tasima.senaryoyla(senaryo, yalniz))


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
    referans_pozisyon_try: float = 3000.0   # tutulmayan varlikta sabit komisyon payi
    uyarilar: list[str] = field(default_factory=list)

    def senaryoyla(self, senaryo: str, yalniz: str = "") -> MaliyetModeli:
        """Tahmin kalemlerini tek senaryonun degerine indirger.

        Boylece mevcut hesap kodu (gidis_donus, yillik) hic degismeden senaryo
        bazinda kosulabilir - duyarlilik testi ayri bir matematik degil, ayni
        matematigin farkli girdiyle tekrari.

        `yalniz` verilirse SADECE o alan senaryoya gecer, digerleri temelde
        kalir. Hepsini birden oynatmak "karar degisiyor" der ama sebebini
        soylemez; tek tek oynatmak sorumlu parametreyi izole eder.
        """
        return replace(self, varliklar={s: v.senaryoyla(senaryo, yalniz)
                                        for s, v in self.varliklar.items()})

    @property
    def tahminler(self) -> dict[str, Tahmin]:
        """Kalem adi -> tahmin. Sembol oneki temizlenir (kalem bazli gruplama)."""
        toplu: dict[str, Tahmin] = {}
        for sembol, varlik in self.varliklar.items():
            for tam_ad, tahmin in varlik.tahminler.items():
                toplu[_kalem_adi(sembol, tam_ad)] = tahmin
        return toplu

    def tahminli_mi(self, sembol: str) -> bool:
        varlik = self.varliklar.get(sembol)
        return bool(varlik and varlik.tahminler)

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

    def minimum_pozisyon(self, sembol: str, esik: float, usdtry: float,
                         senaryo: str = TEMEL) -> float | None:
        varlik = self.varliklar.get(sembol)
        if varlik is None or varlik.profil is None:
            return None
        return varlik.profil.minimum_pozisyon(esik, usdtry, senaryo)


def modeli_kur(ham: dict, sinif_haritasi: dict[str, str]) -> MaliyetModeli:
    """varliklar.yaml -> MaliyetModeli. Ag'a cikmaz, yalnizca ayristirir."""
    maliyet_ham = ham.get("maliyet") or {}
    profil_haritasi = maliyet_ham.get("sinif_profili") or {}
    spread_ham = maliyet_ham.get("sembol_spreadi") or {}
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
        # Sembol bazli spread profildeki degeri EZER. Tek global spread,
        # likiditesi cok farkli hisseleri ayni kefeye koyar: BIST30'da dar,
        # kucuk hissede genis. Listede olmayan sembol profilin degerini alir.
        profil = profiller.get(profil_haritasi.get(sinif, ""))
        if profil is not None and sembol in spread_ham:
            profil = replace(profil, menkul_spread=_sayi(spread_ham[sembol]))
        varliklar[sembol] = VarlikMaliyeti(
            sembol=sembol,
            sinif=sinif,
            profil=profil,
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
        referans_pozisyon_try=float(
            (maliyet_ham.get("duyarlilik") or {}).get("referans_pozisyon_try", 3000.0)),
    )


def _sayi(deger) -> float | Tahmin | None:
    """YAML degerini kaleme cevirir: sayi, uc senaryolu Tahmin, ya da None.

    Tahmin bloguna `tahmin: true` yazilmasi ZORUNLU: uc senaryo alanini
    yanlislikla yazmis bir blok sessizce tahmin olarak islenirse, olculmus
    bir sayiymis gibi davranan ama aslinda uydurulmus bir deger sisteme girer.
    """
    if deger is None:
        return None
    if not isinstance(deger, dict):
        return float(deger)
    if not deger.get("tahmin"):
        raise ValueError(
            f"maliyet kalemi sozluk olarak yazilmis ama 'tahmin: true' yok: {deger}")
    eksik = [ad for ad in SENARYOLAR if deger.get(ad) is None]
    if eksik:
        raise ValueError(f"tahmin blogunda eksik senaryo: {eksik} ({deger})")
    tahmin = Tahmin(
        iyimser=float(deger[IYIMSER]),
        temel=float(deger[TEMEL]),
        kotumser=float(deger[KOTUMSER]),
        kaynak=str(deger.get("kaynak", "")),
    )
    if not tahmin.iyimser <= tahmin.temel <= tahmin.kotumser:
        raise ValueError(
            "tahmin senaryolari iyimser <= temel <= kotumser olmali "
            f"(maliyet kalemi icin iyimser DAIMA en dusuk maliyettir): {deger}")
    return tahmin


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
