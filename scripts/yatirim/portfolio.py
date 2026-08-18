"""Pozisyon degerleme, kar/zarar ve varlik sinifi dagilimi."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import Yapilandirma
from fetch import FiyatVerisi

NAKIT_SINIFI = "nakit"


@dataclass(frozen=True)
class PozisyonDegeri:
    sembol: str
    ad: str
    sinif: str
    adet: float
    maliyet_try: float
    deger_try: float

    @property
    def kar_zarar_try(self) -> float:
        return self.deger_try - self.maliyet_try

    @property
    def kar_zarar_yuzde(self) -> float:
        return 0.0 if self.maliyet_try == 0 else self.kar_zarar_try / self.maliyet_try


@dataclass(frozen=True)
class SinifSapmasi:
    sinif: str
    guncel_agirlik: float
    hedef_agirlik: float

    @property
    def sapma(self) -> float:
        return self.guncel_agirlik - self.hedef_agirlik


@dataclass(frozen=True)
class KurAyristirmasi:
    """TL getirisinin kaci varliktan, kaci kurdan geldi.

    Ayrim olmadan +%30 TL getirisi "iyi secim" gorunur; oysa kur %28 arttiysa
    varlik dolar bazinda neredeyse hic kazandirmamistir. Yanlis dersi cikarip
    ayni secimi tekrarlamanin en kolay yolu bu ikisini ayirmamak.
    """

    sembol: str
    para_birimi: str
    yerel_getiri: float           # varligin kendi para biriminde
    kur_getirisi: float           # USD/TRY hareketi (TRY varlikta 0)

    @property
    def toplam_tl(self) -> float:
        """CARPIMSAL: (1+yerel)(1+kur)-1.

        Toplamsal yaklasim (yerel + kur) yuksek kur hareketinde ciddi sapar:
        %20 yerel / %25 kur -> toplamsal %45 der, dogrusu %50.0.
        """
        return (1.0 + self.yerel_getiri) * (1.0 + self.kur_getirisi) - 1.0


@dataclass(frozen=True)
class Portfoy:
    pozisyonlar: list[PozisyonDegeri]
    nakit_try: float
    fiyatlanamayan: list[str]

    @property
    def pozisyon_degeri_try(self) -> float:
        return sum(p.deger_try for p in self.pozisyonlar)

    @property
    def toplam_deger_try(self) -> float:
        return self.pozisyon_degeri_try + self.nakit_try

    @property
    def pozisyon_maliyet_try(self) -> float:
        return sum(p.maliyet_try for p in self.pozisyonlar)

    @property
    def gerceklesmemis_kar_try(self) -> float:
        """Aciktaki pozisyonlarin kar/zarari.

        Dogrudan olculur (deger - maliyet). Net sonuctan gerceklesen kari
        cikararak turetmek komisyon muhasebesi yuzunden hataliydi: kayitli
        gerceklesen kar satis komisyonu dusulmus (yari-net), toplam komisyon
        ise ayrica ekleniyordu; sonuc satis komisyonu kadar sisiyordu.
        """
        return self.pozisyon_degeri_try - self.pozisyon_maliyet_try

    @property
    def toplam_maliyet_try(self) -> float:
        return self.pozisyon_maliyet_try + self.nakit_try

    @property
    def agirliklar(self) -> dict[str, float]:
        """Sembol -> portfoy icindeki agirlik. Payda nakiti ICERIR.

        Ayni sembolden birden fazla lot varsa TOPLANIR. Dict comprehension
        kullanilsaydi son lot oncekileri ezer, agirlik ve tum risk metrikleri
        sessizce yanlis cikardi.
        """
        toplam = self.toplam_deger_try
        if toplam == 0:
            return {}
        birikim: dict[str, float] = {}
        for pozisyon in self.pozisyonlar:
            birikim[pozisyon.sembol] = (
                birikim.get(pozisyon.sembol, 0.0) + pozisyon.deger_try / toplam
            )
        return birikim


def _maliyeti_tl_yap(maliyet: float, adet: float, kur: str, usdtry: float) -> float:
    """Maliyet varligin kendi para biriminde tutulur; guncel kurla TL'ye cevrilir.

    Not: gecmis alis kuru degil guncel kur kullanilir, yani kur farki
    kar/zarara yansimaz. Kur etkisini ayirmak istersen pozisyona alis
    kuru alani eklemek gerekir.
    """
    tutar = maliyet * adet
    return tutar * usdtry if kur == "USD" else tutar


def portfoyu_hesapla(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi) -> Portfoy:
    son = fiyatlar.son_fiyatlar
    degerler: list[PozisyonDegeri] = []
    fiyatlanamayan: list[str] = []

    for pozisyon in yapilandirma.pozisyonlar:
        varlik = yapilandirma.varliklar[pozisyon.sembol]
        if pozisyon.sembol not in son:
            fiyatlanamayan.append(pozisyon.sembol)
            continue
        degerler.append(
            PozisyonDegeri(
                sembol=pozisyon.sembol,
                ad=varlik.ad,
                sinif=varlik.sinif,
                adet=pozisyon.adet,
                maliyet_try=_maliyeti_tl_yap(
                    pozisyon.maliyet, pozisyon.adet, varlik.kur, fiyatlar.usdtry
                ),
                # son fiyat zaten TL ve carpan uygulanmis halde geliyor (fetch.py)
                deger_try=son[pozisyon.sembol] * pozisyon.adet,
            )
        )

    return Portfoy(
        pozisyonlar=degerler,
        nakit_try=yapilandirma.nakit_try,
        fiyatlanamayan=sorted(fiyatlanamayan),
    )


def portfoyu_ledgerdan_hesapla(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi,
                               durum) -> Portfoy:
    """Simulasyon defterinden portfoy uretir.

    Ledger maliyeti zaten islem anindaki TL tutaridir - kur cevrimi yapilmaz.
    """
    son = fiyatlar.son_fiyatlar
    degerler: list[PozisyonDegeri] = []
    fiyatlanamayan: list[str] = []

    bilinmeyen = sorted(set(durum.pozisyonlar) - set(yapilandirma.varliklar))
    if bilinmeyen:
        raise ValueError(
            f"islemler.yaml'da varliklar.yaml'da tanimsiz sembol var: {bilinmeyen}. "
            "Once varliklar.yaml'a ekle (sinif ve kur bilgisi gerekli)."
        )

    for sembol, ledger_pozisyonu in durum.pozisyonlar.items():
        varlik = yapilandirma.varliklar[sembol]
        if sembol not in son:
            fiyatlanamayan.append(sembol)
            continue
        degerler.append(
            PozisyonDegeri(
                sembol=sembol,
                ad=varlik.ad,
                sinif=varlik.sinif,
                adet=ledger_pozisyonu.adet,
                maliyet_try=ledger_pozisyonu.maliyet_try,
                deger_try=son[sembol] * ledger_pozisyonu.adet,
            )
        )

    return Portfoy(
        pozisyonlar=degerler,
        nakit_try=durum.nakit_try,
        fiyatlanamayan=sorted(fiyatlanamayan),
    )


def _pencere_getirisi(seri, gun: int) -> float | None:
    """Serinin son `gun` gozlemlik getirisi. Veri yetmezse None.

    None ile 0.0 ayrimi burada da gecerli: veri yoksa "degismedi" demek,
    olculemeyeni olculmus gostermektir.
    """
    if seri is None:
        return None
    temiz = seri.dropna()
    if len(temiz) < 2:
        return None
    ilk = temiz.iloc[max(len(temiz) - gun - 1, 0)]
    son = temiz.iloc[-1]
    return float(son / ilk - 1.0) if ilk else None


def kur_ayristir(fiyatlar: FiyatVerisi, varliklar: dict, semboller,
                 gun: int) -> list[KurAyristirmasi]:
    """Aciktaki pozisyonlar icin yerel/kur getirisi ayrimi.

    Kur getirisi TRY varliklarda 0.0'dir - bu bir OLCUM, eksik veri degil:
    TL hesaptan alinan TL hissede kur cevrimi yoktur.
    """
    ayrimlar = []
    kur_getirisi = _pencere_getirisi(fiyatlar.kur_gecmis, gun)
    for sembol in semboller:
        varlik = varliklar.get(sembol)
        if varlik is None or sembol not in fiyatlar.yerel_gecmis:
            continue
        yerel = _pencere_getirisi(fiyatlar.yerel_gecmis[sembol], gun)
        if yerel is None:
            continue
        usd = varlik.kur == "USD"
        if usd and kur_getirisi is None:
            continue
        ayrimlar.append(KurAyristirmasi(
            sembol=sembol, para_birimi=varlik.kur, yerel_getiri=yerel,
            kur_getirisi=kur_getirisi if usd else 0.0))
    return ayrimlar


def degisim_24s(portfoy: Portfoy, fiyatlar: FiyatVerisi) -> float | None:
    """Portfoyun bir onceki gozleme gore TL degisimi. Veri yetmezse None.

    Pozisyonlar SABIT tutulur, yalnizca fiyatlar geriye alinir - yani bu saf
    fiyat etkisidir, alim/satim etkisi degil. Nakit iki tarafta da ayni oldugu
    icin yuzdeyi sonumler; bu dogru davranis, portfoyun gercek degisimi bu.

    Bir onceki GOZLEM, bir onceki takvim gunu degil: BIST Pazartesi raporunda
    Cuma kapanisini kullanir, aradaki hafta sonunu "degisim yok" saymaz.
    """
    gecmis = fiyatlar.try_gecmis.ffill()
    if len(gecmis) < 2:
        return None
    onceki = gecmis.iloc[-2]
    deger = 0.0
    for pozisyon in portfoy.pozisyonlar:
        fiyat = onceki.get(pozisyon.sembol)
        if fiyat is None or not pd.notna(fiyat):
            return None          # tek eksik fiyat tum degisimi yanlis yapar
        deger += float(fiyat) * pozisyon.adet
    taban = deger + portfoy.nakit_try
    return portfoy.toplam_deger_try / taban - 1.0 if taban else None


def kur_maruziyeti(portfoy: Portfoy, varliklar: dict) -> float:
    """USD cinsi varliklarin TL degeri / toplam portfoy.

    Nakit TL kabul edilir. Bu oran, portfoyun kur hareketine ne kadar acik
    oldugunu tek sayiyla verir: %60 maruziyet, kurdaki %10 dususun portfoyu
    tek basina %6 dusurmesi demektir.
    """
    toplam = portfoy.toplam_deger_try
    if toplam == 0:
        return 0.0
    usd_degeri = sum(
        p.deger_try for p in portfoy.pozisyonlar
        if (varliklar.get(p.sembol) is not None
            and varliklar[p.sembol].kur == "USD"))
    return usd_degeri / toplam


def sinif_sapmalari(portfoy: Portfoy, hedef_dagilim: dict[str, float]) -> list[SinifSapmasi]:
    toplam = portfoy.toplam_deger_try
    if toplam == 0:
        return []

    guncel: dict[str, float] = {NAKIT_SINIFI: portfoy.nakit_try / toplam}
    for pozisyon in portfoy.pozisyonlar:
        guncel[pozisyon.sinif] = guncel.get(pozisyon.sinif, 0.0) + pozisyon.deger_try / toplam

    siniflar = sorted(set(guncel) | set(hedef_dagilim))
    return [
        SinifSapmasi(
            sinif=sinif,
            guncel_agirlik=guncel.get(sinif, 0.0),
            hedef_agirlik=hedef_dagilim.get(sinif, 0.0),
        )
        for sinif in siniflar
    ]
