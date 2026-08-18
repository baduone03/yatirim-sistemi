"""Maliyet duyarlilik testi (sartname I7).

SORUN: bilinmeyen bir maliyet kalemini `null` birakmak sinyali tamamen kapatir.
11 varligin hepsi bu yuzden bloklu. Ama her bilinmeyen esit derecede onemli
degil: bazi parametreler ne deger alirsa alsin karari degistirmez, bazilari
tek basina karari ters cevirir. Olculecek sayilarin sirasini bu ayrim belirler.

COZUM: olculmemis kalem `null` yerine UC SENARYOLU tahmin olarak yazilir
(iyimser / temel / kotumser). Sistem karari uc senaryoda da kosar:

    karar uc senaryoda da AYNI  -> karar DAYANIKLI, sinyal uretilir
    karar senaryolar arasi DEGISIYOR -> sinyal bastirilir, hangi parametrenin
                                        sorumlu oldugu yazilir

Ikinci durumda parametre TEK TEK oynatilarak (digerleri temelde sabit)
sorumlusu bulunur. Boylece "her sey belirsiz" demek yerine "su iki sayiyi
olc" denebilir.

KARAR NEDIR: bu modulde karar, "bu varlikta islem yapmak maliyeti karsilar
mi" sorusudur. Gidis-donus maliyeti, sistemin islem yapmaya deger gordugu en
kucuk sapmadan (rebalancing esigi) buyukse, o sapmayi duzeltmek icin yapilan
islem duzelttiginden fazlasini goturur. Iki taraf da portfoy orani cinsinden
oldugu icin dogrudan karsilastirilabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import math

from maliyet import (
    BLOKE_EDEBILEN_ALANLAR,
    KOTUMSER,
    SENARYOLAR,
    TAHMINLI_ISLEM_ALANLARI,
    TAHMINLI_TASIMA_ALANLARI,
    TEMEL,
    YAPISAL_ALANLAR,
    MaliyetModeli,
)

# --- Boyut 1: islem maliyeti (gidis-donus) ---
ISLEM_MANTIKLI = "islem-mantikli"

# --- Boyut 2: tasima maliyeti (basabas tutma suresi) ---
TUTMA_MANTIKLI = "tutma-mantikli"
TUTMA_UZUN = "basabas-planlanandan-uzun"

# Bastirma sebebi kodlari. Sinyal modulu bunlari kendi etiketlerine cevirir;
# duyarlilik modulu sinyal modulunu import ETMEZ (bagimlilik tek yonlu kalir).
SEBEP_PARAMETRE = "parametre-belirsizligi"
SEBEP_TASIMA = "tasima-belirsizligi"
SEBEP_EKONOMIK = "maliyet-yutuyor"

# Hangi boyut hangi alanlari sinaniyor. Kapsam denetiminin dayanagi bu.
BOYUT_ALANLARI = {
    "islem": set(TAHMINLI_ISLEM_ALANLARI),
    "tutma": set(TAHMINLI_TASIMA_ALANLARI),
}
GERCEK = "gercek"          # pozisyon tutuluyor, degeri bu
HEDEF = "hedef"            # tutulmuyor, hedef dagilimda alacagi deger
YEDEK = "yedek"            # portfoy bos - YAML sabiti
MALIYET_YUTUYOR = "maliyet-yutuyor"
OLCULEMEDI = "olculemedi"


@dataclass(frozen=True)
class VarlikDuyarliligi:
    """Bir varligin uc senaryodaki karari ve sorumlu parametreler."""

    sembol: str
    sinif: str = ""
    kararlar: dict[str, str] = field(default_factory=dict)
    belirsiz_parametreler: list[str] = field(default_factory=list)
    maliyetler: dict[str, float] = field(default_factory=dict)
    tahminler: list[str] = field(default_factory=list)
    pozisyon_try: float = 0.0
    pozisyon_kaynagi: str = GERCEK
    minimum_pozisyon: float | None = None      # temel senaryo
    minimum_pozisyon_kotumser: float | None = None
    kapsam_disi_parametreler: list[str] = field(default_factory=list)
    tutma_kararlari: dict[str, str] = field(default_factory=dict)
    basabas: dict[str, float] = field(default_factory=dict)
    planlanan_yil: float | None = None
    tasima_belirsiz_parametreler: list[str] = field(default_factory=list)

    @property
    def tahminli(self) -> bool:
        """Kararin tahmine dayanip dayanmadigi. Olculmus varlikta duyarlilik
        testi calisir ama sonucu her zaman dayaniklidir - uc senaryo ayni
        sayilardan hesaplanir."""
        return bool(self.maliyetler) and len(set(self.maliyetler.values())) > 1

    @property
    def dayanikli(self) -> bool:
        """Karar uc senaryoda da ayni mi? Kararin YONU hakkinda bir sey demez."""
        kararlar = set(self.kararlar.values())
        return len(kararlar) == 1 and OLCULEMEDI not in kararlar

    @property
    def tutma_dayanikli(self) -> bool:
        """Basabas suresi UC senaryoda da planlanan sureden kisa mi?

        Tek senaryoda bile asiyorsa sinyal bastirilir: bir varligi
        "muhtemelen" maliyetini cikaracak diye almak, maliyeti kesinlikle
        odemek demektir. Boyut hic kosulamadiysa (tutma varsayimi yok)
        DAYANIKLI SAYILMAZ - kosulmamis bir testi gecmis saymak, kapsami
        oldugundan genis gostermenin en kolay yolu.
        """
        if not self.tutma_kararlari:
            return False
        return set(self.tutma_kararlari.values()) == {TUTMA_MANTIKLI}

    @property
    def tutma_olculdu(self) -> bool:
        return bool(self.tutma_kararlari)

    @property
    def sinyal_acik(self) -> bool:
        """Sinyal uretilebilir mi? IKI boyut da gecmeli.

        Dayaniklilik TEK BASINA yetmez: uc senaryoda da "maliyet yutuyor"
        cikan varlikta karar dayaniklidir ama yapilmasi gereken sey islem
        DEGIL, beklemektir. Yalnizca dayanikliliga bakan bir kapi, maliyeti
        kesinlikle sapmadan buyuk olan varlikta islem onerirdi.

        Ikinci boyut ayri bir soru soruyor: islem maliyeti kabul edilebilir
        olsa bile, bu varlik planlanan surede o maliyeti CIKARIYOR mu?
        """
        islem_tamam = (self.dayanikli
                       and self.kararlar.get(TEMEL) == ISLEM_MANTIKLI)
        if not islem_tamam:
            return False
        return self.tutma_dayanikli if self.tutma_olculdu else True

    @property
    def blokaji_kaldiran(self) -> list[str]:
        """Bu varligin sinyalini `null` olsa KAPATACAK, tahmin oldugu icin ACAN
        parametreler.

        Her tahminli kalem bu tanima girer: alan `null` olsaydi varlik
        `eksik_kalemler` yuzunden bloklu kalirdi. Yani listedeki her sayi,
        varligi acan bir varsayimdir.
        """
        return sorted({ad.rsplit(".", 1)[-1] for ad in self.tahminler})

    @property
    def dogrulanmamis_acilim(self) -> bool:
        """Blokaji SINANMAMIS bir tahmin mi kaldirdi?

        Kapsam disi bir parametre varligi acmissa, o varlik hicbir duyarlilik
        boyutundan gecmemis bir sayi sayesinde sinyal uretebiliyor demektir.
        `null` disiplininin amaci tam da buydu; isaretlenmezse disiplin
        sessizce bosa duser.
        """
        return bool(set(self.kapsam_disi_parametreler) & set(self.blokaji_kaldiran))

    @property
    def kapsam_ici_parametreler(self) -> list[str]:
        """Duyarlilik testinden GECEN tahminler."""
        return sorted(set(self.blokaji_kaldiran) - set(self.kapsam_disi_parametreler))

    @property
    def ekonomik_degil(self) -> bool:
        """Karar dayanikli ama yonu "islem yapma" - yani sorun BELIRSIZLIK DEGIL.

        Bu ayrim raporun ana faydasi: belirsizlikte yapilacak sey bir sayiyi
        OLCMEK, burada ise pozisyonu BUYUTMEK ya da varliktan CIKMAK. Ikisini
        ayni kutuya koymak, cozulemeyecek bir sorunu olculecek bir soru gibi
        gostermek olurdu.
        """
        return self.dayanikli and not self.sinyal_acik

    @property
    def buyutmek_ise_yarar(self) -> bool:
        """Pozisyonu buyutmek maliyeti esigin altina indirir mi?

        Oransal maliyet (spread, kambiyo vergisi) pozisyonla KUCULMEZ; yalnizca
        sabit komisyonun payi kuculur. Taban zaten esigin ustundeyse hicbir
        buyukluk yetmez - o varliktan cikmaktan baska secenek yok.
        """
        return (self.minimum_pozisyon is not None
                and math.isfinite(self.minimum_pozisyon))

    @property
    def sebep_kodu(self) -> str:
        """Sinyal neden bastirildi? Bos string = bastirilmadi."""
        if self.sinyal_acik or not self.kararlar:
            return ""
        if OLCULEMEDI in self.kararlar.values():
            return ""
        if not self.dayanikli:
            return SEBEP_PARAMETRE
        if self.kararlar.get(TEMEL) != ISLEM_MANTIKLI:
            return SEBEP_EKONOMIK
        return SEBEP_TASIMA

    @property
    def etiket(self) -> str:
        if not self.kararlar or OLCULEMEDI in self.kararlar.values():
            return "olculemedi"
        if not self.dayanikli:
            return "parametre belirsizligi: " + ", ".join(self.belirsiz_parametreler)
        if self.kararlar.get(TEMEL) != ISLEM_MANTIKLI:
            if self.buyutmek_ise_yarar:
                return (f"pozisyon cok kucuk (min {self.minimum_pozisyon:,.0f} TL)"
                        .replace(",", "."))
            return "maliyet tabani esigin ustunde - buyutmek ise yaramaz"
        if self.sinyal_acik:
            return "karar dayanikli"
        if not self.tutma_olculdu:
            return "tutma varsayimi yok - basabas suresi olculemedi"
        return ("tasima maliyeti belirsizligi: "
                + ", ".join(self.tasima_belirsiz_parametreler))


@dataclass(frozen=True)
class DuyarlilikRaporu:
    varliklar: dict[str, VarlikDuyarliligi] = field(default_factory=dict)
    esik: float = 0.0

    def sinyal_acik_mi(self, sembol: str) -> bool:
        """Bilinmeyen sembol icin True: duyarlilik testi ek bir kapidir,
        eksik maliyet kapisinin yerine gecmez. Modelde hic olmayan sembolu
        burada bastirmak, bastirma sebebini yanlis gosterirdi."""
        varlik = self.varliklar.get(sembol)
        return True if varlik is None else varlik.sinyal_acik

    def etiket(self, sembol: str) -> str:
        varlik = self.varliklar.get(sembol)
        return varlik.etiket if varlik else ""

    def sebep_kodu(self, sembol: str) -> str:
        varlik = self.varliklar.get(sembol)
        return varlik.sebep_kodu if varlik else ""

    @property
    def dogrulanmamis_acilimlar(self) -> dict[str, VarlikDuyarliligi]:
        """Blokaji sinanmamis bir tahminle kalkan varliklar."""
        return {s: v for s, v in sorted(self.varliklar.items())
                if v.dogrulanmamis_acilim}

    @property
    def tasima_belirsizleri(self) -> dict[str, list[str]]:
        """Parametre -> basabas suresini planlanan surenin ustune cikaran varliklar."""
        etki: dict[str, list[str]] = {}
        for sembol, varlik in sorted(self.varliklar.items()):
            if varlik.tutma_olculdu and not varlik.tutma_dayanikli:
                for parametre in varlik.tasima_belirsiz_parametreler:
                    etki.setdefault(parametre, []).append(sembol)
        return etki

    def _sinif_adaylari(self, sinif: str) -> list[VarlikDuyarliligi]:
        return [v for v in self.varliklar.values() if v.sinif == sinif]

    def sinif_sinyali_acik_mi(self, sinif: str) -> bool:
        """Sinif tavsiyesi ancak dayanikli EN AZ BIR varlikla uygulanabilir.

        `MaliyetModeli.sinif_sinyali_acik` ile ayni mantik: bir sinifi azaltmak
        demek, o sinifta guvenle satilabilecek bir sembol gerektirir. Hepsi
        belirsizse tavsiye uygulanamaz bir emirdir.
        """
        adaylar = self._sinif_adaylari(sinif)
        return True if not adaylar else any(v.sinyal_acik for v in adaylar)

    def sinif_etiketi(self, sinif: str) -> str:
        belirsiz = sorted({p for v in self._sinif_adaylari(sinif)
                           for p in v.belirsiz_parametreler})
        if belirsiz:
            return "parametre belirsizligi: " + ", ".join(belirsiz)
        return "maliyet sapmayi yutuyor"

    @property
    def belirsizler(self) -> dict[str, VarlikDuyarliligi]:
        return {s: v for s, v in sorted(self.varliklar.items()) if not v.dayanikli}

    @property
    def kapsam_disi_tahminler(self) -> dict[str, list[str]]:
        """Karar olcutune HIC GIRMEYEN tahminler: parametre -> varliklar.

        Karar `gidis_donus` uzerinden veriliyor ve o hesap yalnizca ISLEM
        maliyetini kullaniyor. Tasima kalemleri (gider orani, temettu verimi,
        stopaj) bir varligin TUTULMA maliyetidir, ALIP SATMA maliyeti degil -
        dolayisiyla "islem yapmaya deger mi" sorusunu degistiremezler.

        Ayri raporlanmalari sart: uc senaryoda kosulup karari degistirmedikleri
        icin "hicbiri karari cevirmiyor" satirina dusuyorlar ve test edilmis
        gibi gorunuyorlar. Oysa test edilmediler, hesaba hic girmediler.
        Bu kalemler net getiri raporunu etkiler, islem kapisini etkilemez.
        """
        kapsam_disi: dict[str, list[str]] = {}
        for sembol, varlik in sorted(self.varliklar.items()):
            for parametre in varlik.kapsam_disi_parametreler:
                kapsam_disi.setdefault(parametre, []).append(sembol)
        return kapsam_disi

    def sinif_sebep_kodu(self, sinif: str) -> str:
        kodlar = [v.sebep_kodu for v in self._sinif_adaylari(sinif) if v.sebep_kodu]
        return kodlar[0] if kodlar else SEBEP_PARAMETRE

    @property
    def ekonomik_olmayanlar(self) -> dict[str, VarlikDuyarliligi]:
        """Pozisyon buyuklugu yuzunden islem yapilamayan varliklar.

        `belirsizler` ile KARISTIRMA: orada eksik olan bir SAYI, burada eksik
        olan PARA. Cozumleri de farkli - biri olculur, digeri buyutulur veya
        varliktan cikilir.
        """
        return {s: v for s, v in sorted(self.varliklar.items()) if v.ekonomik_degil}

    @property
    def maliyet_yutanlar(self) -> dict[str, VarlikDuyarliligi]:
        """Karar dayanikli ama yonu "islem yapma". Belirsizlikle KARISTIRMA:
        burada olculecek bir sey yok, maliyet gercekten sapmadan buyuk."""
        return {s: v for s, v in sorted(self.varliklar.items())
                if v.dayanikli and not v.sinyal_acik}

    @property
    def olculmesi_gerekenler(self) -> list[tuple[str, list[str]]]:
        """Parametre -> karari degisen varliklar. ETKI SIRASINA gore.

        Siralama olcusu etkilenen varlik SAYISI; esitlikte alfabetik, boylece
        ayni girdi ayni sirayi uretir (rapor diff'i gurultulenmez). Bu liste
        "once hangi sayiyi olc" sorusunun cevabidir.
        """
        etki: dict[str, list[str]] = {}
        for sembol, varlik in self.varliklar.items():
            for parametre in varlik.belirsiz_parametreler:
                etki.setdefault(parametre, []).append(sembol)
        return sorted(((p, sorted(s)) for p, s in etki.items()),
                      key=lambda kayit: (-len(kayit[1]), kayit[0]))


def kapsam_denetimi() -> list[str]:
    """Bloke edebilen her alan bir duyarlilik boyutu tarafindan kapsaniyor mu?

    KURAL: bir parametre `null` birakildiginda varligin sinyalini kapatabiliyorsa
    (yani "bloke edebilen" bir alansa), o parametrenin uc senaryolu tahminle
    doldurulmasi da sinyali ACABILIR. Acilisi saglayan sayinin SINANMAMIS olmasi
    kabul edilemez - sinanmamis bir tahminle acilan sinyal, `null` disiplininin
    tamamen bosa dusmesi demektir.

    Tek istisna YAPISAL alanlar: `kur_cevrimi` bool'dur, uc senaryosu olamaz.
    Onlar tahminle DOLDURULAMAZ, yani sinyali tahminle acamazlar.

    Doner: ihlal aciklamalari. Bos liste = kapsam tam.
    """
    kapsanan = set().union(*BOYUT_ALANLARI.values())
    ihlaller = []
    for alan in BLOKE_EDEBILEN_ALANLAR:
        if alan in YAPISAL_ALANLAR or alan in kapsanan:
            continue
        ihlaller.append(
            f"{alan}: bloke edebiliyor ama hicbir duyarlilik boyutu kapsamiyor - "
            "tahminle doldurulursa sinyal SINANMADAN acilir")
    return ihlaller


def _karar(model: MaliyetModeli, sembol: str, pozisyon_try: float,
           usdtry: float, esik: float) -> str:
    """Gidis-donus maliyeti, islem yapmaya deger en kucuk sapmayi asiyor mu?

    Asiyorsa islem duzelttigi sapmadan fazlasini goturur - sinyal ne derse
    desin o varlikta islem yapmak matematiksel olarak kaybettirir.
    """
    maliyet = model.gidis_donus(sembol, pozisyon_try, usdtry)
    if maliyet is None:
        return OLCULEMEDI
    return ISLEM_MANTIKLI if maliyet < esik else MALIYET_YUTUYOR


def _tutma_karari(model: MaliyetModeli, sembol: str, pozisyon_try: float,
                  usdtry: float, planlanan_yil: float | None) -> str:
    """Basabas tutma suresi planlanan sureyi asiyor mu?

    Asiyorsa varlik, tutmayi planladigin surede islem maliyetini CIKARMIYOR -
    beklenen getiri gerceklesse bile. Sonsuz sure (payda <= 0) bu kontrolu
    dogal olarak gecemez.
    """
    if planlanan_yil is None:
        return OLCULEMEDI
    sure = model.basabas_yil(sembol, pozisyon_try, usdtry)
    if sure is None:
        return OLCULEMEDI
    return TUTMA_MANTIKLI if sure <= planlanan_yil else TUTMA_UZUN


def _sorumlulari_bul(kararlar: dict[str, str], varlik, karar_fn,
                     model: MaliyetModeli) -> list[str]:
    """Karari ceviren parametreleri TEK TEK oynatarak izole eder.

    Hepsini birden oynatmak "karar degisiyor" der ama sebebini soylemez.
    Hicbiri tek basina cevirmiyorsa sorumlu birlesimdir; hepsini yazmak
    "hangisini olceyim" sorusunu cevapsiz birakmaktan iyidir.
    """
    if len(set(kararlar.values())) <= 1:
        return []
    sorumlular = []
    for tam_ad in sorted(varlik.tahminler):
        parametre = tam_ad.rsplit(".", 1)[-1]
        tekil = {karar_fn(model.senaryoyla(ad, yalniz=parametre))
                 for ad in SENARYOLAR}
        if len(tekil) > 1:
            sorumlular.append(parametre)
    return sorumlular or sorted(
        {ad.rsplit(".", 1)[-1] for ad in varlik.tahminler})


def referans_pozisyonlar(portfoy, hedef_dagilim: dict[str, float],
                         sinif_haritasi: dict[str, str],
                         yedek_try: float) -> dict[str, tuple[float, str]]:
    """Her sembol icin duyarlilik hesabinda kullanilacak pozisyon buyuklugu.

    Sabit bir referans varsaymak sonucu belirler: ayni varlik 3.000 TL'de
    "ekonomik degil", 12.000 TL'de "olcmen gereken parametre var" cikiyor.
    Bu yuzden buyukluk portfoyden TURETILIR:

      GERCEK - varlik tutuluyorsa pozisyonun bugunku degeri.
      HEDEF  - tutulmuyorsa, hedef dagilimda alacagi deger: toplam x sinif
               hedefi / o siniftaki sembol sayisi. "Alsaydim ne kadar
               olurdu" sorusunun cevabi budur.
      YEDEK  - portfoy bos veya hedef tanimsizsa YAML'daki sabit deger.
               Yalnizca ilk kosuda devreye girer.
    """
    toplam = portfoy.toplam_deger_try if portfoy is not None else 0.0
    tutulan = {p.sembol: p.deger_try for p in (portfoy.pozisyonlar if portfoy else [])}
    sinif_sayisi: dict[str, int] = {}
    for sinif in sinif_haritasi.values():
        sinif_sayisi[sinif] = sinif_sayisi.get(sinif, 0) + 1

    sonuc: dict[str, tuple[float, str]] = {}
    for sembol, sinif in sinif_haritasi.items():
        if tutulan.get(sembol, 0.0) > 0:
            sonuc[sembol] = (tutulan[sembol], GERCEK)
            continue
        hedef = hedef_dagilim.get(sinif, 0.0) if toplam > 0 else 0.0
        pay = toplam * hedef / max(sinif_sayisi.get(sinif, 1), 1)
        sonuc[sembol] = (pay, HEDEF) if pay > 0 else (yedek_try, YEDEK)
    return sonuc


def duyarliligi_olc(model: MaliyetModeli, esik: float,
                    pozisyon_degerleri: dict[str, float] | dict[str, tuple[float, str]],
                    usdtry: float) -> DuyarlilikRaporu:
    """Her varlik icin uc senaryoyu kosar, sorumlu parametreleri isaretler.

    `esik` = rebalancing sapma esigi. Sistem bundan kucuk bir sapmayi zaten
    islem yapmaya degmez sayiyor; gidis-donus maliyeti bu sinirin ustundeyse
    islem sapmadan cok maliyeti buyutur.

    `pozisyon_degerleri` ya {sembol: TL} ya da `referans_pozisyonlar`
    ciktisidir ({sembol: (TL, kaynak)}); ikincisi buyuklugun nereden geldigini
    de tasir ve rapor bunu yazar.
    """
    senaryo_modelleri = {ad: model.senaryoyla(ad) for ad in SENARYOLAR}
    varliklar: dict[str, VarlikDuyarliligi] = {}

    for sembol, varlik in model.varliklar.items():
        ham = pozisyon_degerleri.get(sembol)
        if ham is None:
            pozisyon, kaynak = model.referans_pozisyon_try, YEDEK
        elif isinstance(ham, tuple):
            pozisyon, kaynak = ham
        else:
            pozisyon, kaynak = float(ham), GERCEK
        kararlar, maliyetler = {}, {}
        for ad, senaryo_modeli in senaryo_modelleri.items():
            kararlar[ad] = _karar(senaryo_modeli, sembol, pozisyon, usdtry, esik)
            gidis_donus = senaryo_modeli.gidis_donus(sembol, pozisyon, usdtry)
            if gidis_donus is not None:
                maliyetler[ad] = gidis_donus

        sorumlular = _sorumlulari_bul(
            kararlar, varlik, lambda m: _karar(m, sembol, pozisyon, usdtry, esik),
            model)

        # --- Boyut 2: basabas tutma suresi ---
        planlanan = model.planlanan_yil(sembol)
        tutma_kararlari: dict[str, str] = {}
        basabas: dict[str, float] = {}
        if planlanan is not None:
            for ad in SENARYOLAR:
                sure = model.basabas_yil(sembol, pozisyon, usdtry, ad)
                if sure is None:
                    tutma_kararlari = {}
                    basabas = {}
                    break
                basabas[ad] = sure
                tutma_kararlari[ad] = (
                    TUTMA_MANTIKLI if sure <= planlanan else TUTMA_UZUN)
        tasima_sorumlulari = _sorumlulari_bul(
            tutma_kararlari, varlik,
            lambda m: _tutma_karari(m, sembol, pozisyon, usdtry, planlanan),
            model)

        # Boyut 2 kosulamadiysa tasima tahminleri SINANMAMIS kalir; kosulduysa
        # kapsam icindedir. "Sinanmadi" ile "sinandi ve gecti" ayri seyler.
        kapsam_disi = [] if tutma_kararlari else sorted({
            ad.rsplit(".", 1)[-1] for ad in varlik.tahminler
            if ad.rsplit(".", 1)[-1] in TAHMINLI_TASIMA_ALANLARI})

        varliklar[sembol] = VarlikDuyarliligi(
            sembol=sembol, sinif=varlik.sinif, kararlar=kararlar,
            belirsiz_parametreler=sorumlular, maliyetler=maliyetler,
            tahminler=sorted(varlik.tahminler),
            pozisyon_try=pozisyon, pozisyon_kaynagi=kaynak,
            minimum_pozisyon=model.minimum_pozisyon(sembol, esik, usdtry, TEMEL),
            minimum_pozisyon_kotumser=model.minimum_pozisyon(
                sembol, esik, usdtry, KOTUMSER),
            kapsam_disi_parametreler=kapsam_disi,
            tutma_kararlari=tutma_kararlari, basabas=basabas,
            planlanan_yil=planlanan,
            tasima_belirsiz_parametreler=tasima_sorumlulari)

    return DuyarlilikRaporu(varliklar=varliklar, esik=esik)
