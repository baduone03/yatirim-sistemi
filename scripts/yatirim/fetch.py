"""Yahoo Finance'ten fiyat gecmisi ceker ve TL bazina cevirir."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import yfinance as yf

from config import (
    BayatlikEsikleri,
    KurumsalOlayAyarlari,
    Yapilandirma,
    hafta_sonu_mu,
    simdi_utc,
)
from kaynaklar import (
    KaynakHatasi,
    KurKotasyonu,
    UcgenlemeAyarlari,
    UcgenlemeSonucu,
    btcturk_fiyatlari,
    coingecko_usd,
    http_json,
    tcmb_kayitlari,
    tcmb_usdtry,
    tcmb_yuzde_orani,
    ucgenle,
)
from maliyet import MaliyetModeli


BAYAT_ESIGI_GUN = 7

# Gecici indirme hatasi tum kosuyu dusurmesin. Iki ek deneme ~6 saniye
# tutuyor ve YALNIZCA hata halinde harcaniyor - basarili kosunun suresi
# (35-50 sn, fatura esigi 60 sn) degismez.
INDIRME_DENEMESI = 3
INDIRME_BEKLEMESI_SN = 3


@dataclass(frozen=True)
class FiyatVerisi:
    """TL bazina cevrilmis gunluk kapanis serileri."""

    try_gecmis: pd.DataFrame          # sutun = sembol, deger = TL fiyat
    usdtry: float
    eksik_semboller: list[str]
    sinif_haritasi: dict[str, str] = field(default_factory=dict)
    kurumsal_olay_supheleri: dict[str, str] = field(default_factory=dict)
    ucgenleme: UcgenlemeSonucu = field(default_factory=UcgenlemeSonucu)
    # Kur ayristirmasi icin: varligin kendi para birimindeki seri + kur serisi.
    # try_gecmis'ten geri bolunerek turetilemez, bkz. _serileri_hazirla.
    yerel_gecmis: pd.DataFrame = field(default_factory=pd.DataFrame)
    kur_gecmis: pd.Series = field(default_factory=pd.Series)

    @property
    def son_fiyatlar(self) -> dict[str, float]:
        """Degerleme fiyatlari. Bosluklar ffill'lenir - son BILINEN fiyat kullanilir.

        Uc filtre sirayla uygulanir:
          1. Kurumsal olay suphesi olan sembol DISARIDA kalir - sicrama gercek
             kayip mi kayitli olmayan bedelsiz mi belli degil.
          2. Ucgenlemede DURDUR alan sembol DISARIDA kalir - fiyati var ama
             uc kaynak birbirini tutmuyor.
          3. Kalan kriptolar icin BTCTurk TL fiyati Yahoo'yu EZER. TL cifti
             dogrudan alindigi icin cift cevrim (BTC/USD x USD/TRY) hatasi
             tasimaz.
        """
        son = self.try_gecmis.ffill().iloc[-1]
        fiyatlar = {
            sembol: float(deger) for sembol, deger in son.items()
            if pd.notna(deger) and sembol not in self.kurumsal_olay_supheleri
        }
        for durduran in self.ucgenleme.durduranlar:
            fiyatlar.pop(durduran.sembol, None)
        for sembol, tl in self.ucgenleme.degerleme_fiyatlari().items():
            if sembol not in self.kurumsal_olay_supheleri:
                fiyatlar[sembol] = tl
        return fiyatlar

    @property
    def son_tarih(self) -> str:
        return self.try_gecmis.index[-1].date().isoformat()

    def _sinif_takvimi(self, sinif: str) -> pd.Index:
        """Sinifin GOZLENEN islem takvimi: o siniftan herhangi bir sembolun
        veri verdigi gunler.

        Bayatligi takvim gunuyle olcmek her Pazartesi yanlis alarm verir -
        BIST Cuma'dan Pazartesi'ye 3 takvim gunu gecirir, 1 islem gunu. Sinifin
        kendi takvimi bunu veriden turetir, sabit piyasa takvimi gerekmez.
        """
        semboller = [s for s in self.try_gecmis.columns
                     if self.sinif_haritasi.get(s) == sinif]
        if not semboller:
            return self.try_gecmis.index
        altkume = self.try_gecmis[semboller]
        return altkume.index[altkume.notna().any(axis=1)]

    def bayat_semboller(self, esikler: BayatlikEsikleri | None = None) -> dict[str, int]:
        """Bayat semboller -> gecikme. Sinif bazli esik uygulanir.

        Iki kontrol birden:
          1. Sinif esigi - kacirilan ISLEM GUNU sayisi (sinifin kendi takvimi).
          2. Guvenlik agi - takvim gunu cinsinden `varsayilan`. Sinifta tek
             sembol varsa o sembolun kendi takvimi referans olur ve 1. kontrol
             hicbir zaman tetiklenmez; bu kontrol o bosluğu kapatir.

        ffill sessizce eski fiyati tasir; delist olmus veya veri akisi kesilmis
        bir varlik dogru fiyatliymis gibi gorunur. Bu, sorunu gorunur kilar.
        """
        esikler = esikler or BayatlikEsikleri()
        son_gun = self.try_gecmis.index[-1]
        bayatlar: dict[str, int] = {}
        for sembol in self.try_gecmis.columns:
            gecerli = self.try_gecmis[sembol].dropna()
            if gecerli.empty:
                continue
            son_veri = gecerli.index[-1]
            sinif = self.sinif_haritasi.get(sembol, "")
            esik = esikler.gun(sinif)
            # Esik 1 gunun altindaysa piyasa SUREKLI demektir (kripto 7/24):
            # kapali gunu yok, dolayisiyla referans takvim tum takvimdir.
            # Sinifin kendi takvimini kullanmak burada ise yaramaz - sinifta
            # tek sembol kalirsa kendi takvimi kendisiyle biter ve hicbir
            # zaman bayat cikmaz.
            takvim = self.try_gecmis.index if esik < 1 else self._sinif_takvimi(sinif)
            kacirilan = int((takvim > son_veri).sum())
            takvim_gunu = (son_gun - son_veri).days
            if kacirilan > esik:
                bayatlar[sembol] = kacirilan
            elif takvim_gunu > esikler.varsayilan:
                bayatlar[sembol] = takvim_gunu
        return bayatlar


def _alani_cek(ham: pd.DataFrame, alan: str, semboller: list[str]) -> pd.DataFrame:
    if alan not in ham:
        return pd.DataFrame(index=ham.index)
    veri = ham[alan]
    if isinstance(veri, pd.Series):
        veri = veri.to_frame(semboller[0])
    return veri


def kapanislari_indir(semboller: list[str], gun: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(kapanis, hacim) doner.

    Hacim kurumsal olay tespiti icin gerekli: bedelsiz/split fiyati sicratir
    ama hacimde karsilik gelen patlama olmaz; gercek cokus hacimle gelir.
    Ikisini ayirt eden tek gozlenebilir sinyal budur.
    """
    ham = None
    for deneme in range(INDIRME_DENEMESI):
        # Ilk deneme paralel (hizli), sonrakiler TEK IS PARCACIGI. Sebep:
        # yfinance sembol basina zaman dilimi/cerez bilgisini ortak bir SQLite
        # dosyasinda tutar ve paralel indirmede is parcaciklari o dosyada
        # kilitlenip "database is locked" ile TUM sembolleri dusurebiliyor
        # (2026-08-26 kosusu boyle kirildi). Sirali indirme kendisiyle
        # yarisamaz, yani ikinci deneme bu hataya yapisal olarak kapalidir.
        ham = yf.download(
            semboller,
            period=f"{gun}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=(deneme == 0),
        )
        if ham is not None and not ham.empty:
            break
        if deneme < INDIRME_DENEMESI - 1:
            time.sleep(INDIRME_BEKLEMESI_SN)
    if ham is None or ham.empty:
        raise RuntimeError("Yahoo Finance bos veri dondurdu - ag baglantisini kontrol et")

    kapanis = _alani_cek(ham, "Close", semboller)
    hacim = _alani_cek(ham, "Volume", semboller)
    return kapanis.dropna(how="all"), hacim


def _hacim_dogruluyor(hacim: pd.DataFrame, sembol: str, tarih,
                      ayarlar: KurumsalOlayAyarlari) -> bool:
    """Hareketi hacim dogruluyor mu? Doguruyorsa hareket GERCEK, olay degil.

    Hacim verisi yoksa False doner - yani sembol supheli kalir. Bilincli
    secim: dogrulayamadigimiz bir sicramayi 'gercek' saymak, yanlis degeri
    dogruymus gibi raporlamak demektir. Degerlemeyi durdurmak geri
    alinabilir, yanlis rakama gore islem yapmak degil.
    """
    if sembol not in hacim.columns:
        return False
    seri = hacim[sembol].dropna()
    seri = seri[seri > 0]
    if tarih not in seri.index:
        return False
    onceki = seri[seri.index < tarih].tail(ayarlar.hacim_penceresi)
    if onceki.empty:
        return False
    return float(seri.loc[tarih]) >= float(onceki.median()) * ayarlar.hacim_carpani


def kurumsal_olay_supheleri(kapanis: pd.DataFrame, hacim: pd.DataFrame,
                            ayarlar: KurumsalOlayAyarlari,
                            bilinen: set[tuple[str, str]] | None = None) -> dict[str, str]:
    """Kayitli olmayan bedelsiz/split suphesi. sembol -> gerekce.

    `auto_adjust=True` Yahoo'nun BILDIGI split/temettuyu zaten geri duzeltir.
    Bu kontrol Yahoo'nun KACIRDIKLARI icin var - ozellikle BIST bedelsiz
    sermaye artirimlari, ki duzeltilmeden gelir ve fiyat bir gunde yariya
    duser gibi gorunur.

    Ham (TL'ye cevrilmemis) seri uzerinde calisir: TL cevrimi tum USD
    varliklarina ortak kur hareketi ekler, kur soku her sembolu supheli
    gosterirdi.
    """
    bilinen = bilinen or set()
    supheliler: dict[str, str] = {}
    for sembol in kapanis.columns:
        seri = kapanis[sembol].dropna()
        if len(seri) < 2:
            continue
        son_getiriler = seri.pct_change().dropna().tail(ayarlar.tarama_gunu)
        for tarih, getiri in son_getiriler.items():
            if abs(getiri) <= ayarlar.getiri_esigi:
                continue
            gun = tarih.date().isoformat()
            if (sembol, gun) in bilinen:
                continue          # deftere yazilmis, artik supheli degil
            if _hacim_dogruluyor(hacim, sembol, tarih, ayarlar):
                continue          # hacim var - gercek hareket
            supheliler[sembol] = (
                f"{gun}: %{getiri * 100:+.1f} fiyat hareketi, hacimde karsiligi yok"
            )
    return supheliler


def _serileri_hazirla(kapanis: pd.DataFrame, yapilandirma: Yapilandirma
                      ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Uc seri dondurur: TL, varligin KENDI para birimi, USD/TRY kuru.

    Yalnizca KUR serisi ffill edilir (carpan olarak her gun gerekli).
    Varlik serileri ffill EDILMEZ: BIST hafta sonu kapali, kripto acik.
    Kapali gunu doldurmak yapay sifir-getirili gun uretir ve volatiliteyi
    sistematik olarak dusuk gosterir. Bosluklar NaN kalir; degerleme
    son_fiyatlar icinde ayrica ffill'lenir.

    Yerel seri, TL serisinden GERI BOLUNEREK uretilmez. Kur serisi ffill'li,
    varlik serisi degil; bolme islemi ffill artifaktlarini yerel seriye tasir
    ve kur ayristirmasi ((1+yerel)(1+kur)-1) toplam TL getirisini tutmaz.
    Ikisi de ham `kapanis`tan bagimsiz kurulur.
    """
    kur_serisi = kapanis[yapilandirma.ayarlar.kur_sembolu].ffill()
    yerel, tl = {}, {}
    for sembol, varlik in yapilandirma.varliklar.items():
        # Hepsi NaN olan sembol tamamen DISARIDA birakilir. Sutun olarak
        # kalirsa ortak takvim kesisimini bosaltip tum risk hesabini cokertir;
        # zaten eksik_semboller icinde raporlaniyor.
        if sembol not in kapanis or kapanis[sembol].isna().all():
            continue
        seri = kapanis[sembol] * varlik.carpan
        yerel[sembol] = seri
        tl[sembol] = seri * kur_serisi if varlik.kur == "USD" else seri
    if not tl:
        raise RuntimeError("Hicbir varlik icin fiyat verisi alinamadi")
    try_gecmis = pd.DataFrame(tl).dropna(how="all")
    return (try_gecmis,
            pd.DataFrame(yerel).reindex(try_gecmis.index),
            kur_serisi.reindex(try_gecmis.index))


def _kur_kotasyonu(kaynaklar, env, yahoo_usdtry: float, getir,
                   bugun=None, yahoo_tarihi=None
                   ) -> tuple[KurKotasyonu, list[str]]:
    """USD/TRY: once TCMB, erisilemez veya BAYATSA Yahoo.

    TCMB kuru yalnizca is gunu ~15:30'da yayimlanir. Hafta sonu ve tatilde
    yeni kur yoktur. Cuma kuruyla Pazar gunu ucgenleme yapmak, "TR primi"
    adi altinda kurun bayatligini olcmek demektir - kripto 7/24 hareket
    ederken kur donmus kalir.
    """
    bugun = bugun or date.today()
    uyarilar: list[str] = []
    # Yahoo kuru serinin SON GERCEK gozleminden gelir ve o gozlem hafta sonu
    # veya tatilde gunlerce eski olabilir (`.ffill()` degeri tasiyor).
    # Kotasyona `bugun` damgasi vurmak bayat bir kuru guncelmis gibi
    # gostermek olurdu - TCMB tarafinda titizlikle olculen bayatligin
    # Yahoo tarafinda hic olculmemesi tutarsizdi.
    yedek = KurKotasyonu(yahoo_usdtry, yahoo_tarihi or bugun, "yahoo")

    if not kaynaklar.tcmb_url:
        return yedek, uyarilar
    try:
        kur = tcmb_usdtry(kaynaklar.tcmb_url, kaynaklar.tcmb_seri, getir=getir)
    except KaynakHatasi as hata:
        uyarilar.append(f"TCMB okunamadi ({hata}) - USD/TRY Yahoo'dan alindi.")
        return yedek, uyarilar
    if kur.bayat_mi(kaynaklar.tcmb_bayatlik_gun, bugun):
        uyarilar.append(
            f"TCMB kuru {kur.tarih} tarihli, bayat - USD/TRY Yahoo'dan alindi. "
            "TCMB yalnizca is gunu kur yayimlar.")
        return (KurKotasyonu(yahoo_usdtry, yahoo_tarihi or bugun,
                             "yahoo (tcmb bayat)"), uyarilar)
    return kur, uyarilar


def kripto_ucgenlemesi(yapilandirma: Yapilandirma, yahoo_usdtry: float,
                       env: dict | None = None, getir=http_json,
                       simdi=None, bugun=None,
                       kur_tarihi=None) -> UcgenlemeSonucu:
    """BTCTurk + CoinGecko + TCMB capraz kontrolu.

    Kaynaklardan biri dusse bile HATA FIRLATMAZ: eksik kaynak OLCULEMEDI
    demektir, rapor uretilmeye devam eder. Yalnizca uc kaynak da tazeyken
    gercek bir kopukluk goruldugunde DURDUR cikar.
    """
    kaynaklar = yapilandirma.kaynaklar
    if not kaynaklar.btcturk_acik:
        return UcgenlemeSonucu()

    uyarilar: list[str] = []
    try:
        tl_fiyatlar = btcturk_fiyatlari(
            kaynaklar.btcturk_url, kaynaklar.btcturk_ciftleri, getir)
    except KaynakHatasi as hata:
        uyarilar.append(f"BTCTurk okunamadi: {hata}")
        tl_fiyatlar = {}

    usd_fiyatlar: dict[str, float] = {}
    if kaynaklar.coingecko_url:
        try:
            usd_fiyatlar = coingecko_usd(
                kaynaklar.coingecko_url, kaynaklar.coingecko_kimlikleri, getir)
        except KaynakHatasi as hata:
            uyarilar.append(f"CoinGecko okunamadi: {hata}")

    kur, kur_uyarilari = _kur_kotasyonu(kaynaklar, env, yahoo_usdtry, getir,
                                        bugun, kur_tarihi)
    uyarilar += kur_uyarilari

    ayarlar = UcgenlemeAyarlari(
        prim_esigi=kaynaklar.prim_esigi,
        durdurma_esigi=kaynaklar.durdurma_esigi,
        btcturk_bayatlik_dakika=kaynaklar.btcturk_bayatlik_dakika,
        tcmb_bayatlik_gun=kaynaklar.tcmb_bayatlik_gun,
    )
    # Hafta sonu kur piyasasi kapali - degerleme bundan etkilenmez (BTCTurk TL
    # fiyati dogrudan alinir), yalnizca CAPRAZ KONTROL yapilamaz.
    kapali = hafta_sonu_mu(simdi or simdi_utc())
    if kapali:
        uyarilar.append(
            "Hafta sonu: USD/TRY donmus, kripto ucgenlemesi yapilamadi. "
            "Degerleme BTCTurk TL fiyatindan devam ediyor.")
    sonuclar = {
        sembol: ucgenle(sembol, tl_fiyatlar.get(sembol), usd_fiyatlar.get(sembol),
                        kur, ayarlar, simdi, kapali)
        for sembol in sorted(kaynaklar.btcturk_ciftleri)
    }
    return UcgenlemeSonucu(sonuclar=sonuclar, uyarilar=uyarilar)


def maliyet_modelini_coz(yapilandirma: Yapilandirma, getir=http_json,
                         bugun: date | None = None) -> MaliyetModeli:
    """Hurdle rate ve enflasyonu TCMB'den canli okur, yedege dusebilir.

    Neden canli: %48 mevduat faizi ortaminda YAML'a yazilmis bir hurdle rate
    aylar icinde sessizce yanlislasir ve her pozitif getiri yeniden "basari"
    gorunur. Neden yedek: TCMB'nin bir gunluk kesintisi hurdle rate'i
    SIFIRLAMAMALI - USD/TRY'de kurulan ayni Yahoo yedegi mantigi.

    Fiyat ucgenlemesi de ayni uctan USD/TRY cekiyor; iki ayri istek atiliyor.
    Tek istekte birlestirmek cagri grafigini iki modul arasinda dolastirirdi,
    kazanci kucuk statik bir JSON'un ikinci kez okunmasi olurdu.
    """
    model = yapilandirma.maliyet
    url = yapilandirma.kaynaklar.tcmb_url
    if not url or not (model.risksiz_serisi or model.enflasyon_serisi):
        return model
    try:
        kayitlar = tcmb_kayitlari(url, getir)
    except KaynakHatasi as hata:
        return model.oranlarla(None, None, [
            f"TCMB oran serileri okunamadi ({hata}) - hurdle rate ve enflasyon "
            "yapilandirmadaki yedek degerlerden alindi."])

    uyarilar: list[str] = []
    canli: dict[str, tuple[float, str] | None] = {}
    # Hurdle rate'te KABUL esigi taze esigi degil DURDURMA esigidir. Sebep:
    # canli deger reddedilirse yerine elle yazilmis YAML yedegi geciyor ve o
    # yedek daha da eski olabilir. Taze esigiyle elenseydi 12 gunluk canli
    # sayiyi atip 60 gunluk yedegi kullanabilirdik - tam tersi. Canli deger
    # kullanilabilir oldugu surece alinir; kac gunluk oldugu tarihiyle birlikte
    # modele tasinir ve bayatlik kararini tek yerde `risksiz_durduruyor_mu`
    # verir.
    # `birincil_seri`, o an KAZANAN kaynak degil zincirdeki ilk seri. Kazanana
    # bakmak, ilan edilmis oran one gectiginde canli seriyi hic yenilememek
    # demekti - seri sonsuza kadar bayat kalir ve zincir bir daha asla
    # birinciye donemezdi.
    for alan, seri, esik, etiket in (
        ("risksiz", model.birincil_seri, model.risksiz_durdurma_gun, "hurdle rate"),
        ("enflasyon", model.enflasyon_serisi, model.enflasyon_bayatlik_gun, "enflasyon"),
    ):
        canli[alan] = tcmb_yuzde_orani(kayitlar, seri, esik, bugun) if seri else None
        if seri and canli[alan] is None:
            uyarilar.append(
                f"TCMB {seri} serisi yok veya {esik} gunden bayat - {etiket} "
                "yapilandirmadaki yedek degerden alindi.")
    return model.oranlarla(canli["risksiz"], canli["enflasyon"], uyarilar, bugun)


def fiyatlari_getir(yapilandirma: Yapilandirma,
                    bilinen_olaylar: set[tuple[str, str]] | None = None,
                    env: dict | None = None, getir=http_json) -> FiyatVerisi:
    semboller = yapilandirma.fiyat_sembolleri
    kapanis, hacim = kapanislari_indir(semboller, yapilandirma.ayarlar.gecmis_gun)

    kur_sembolu = yapilandirma.ayarlar.kur_sembolu
    if kur_sembolu not in kapanis or kapanis[kur_sembolu].isna().all():
        raise RuntimeError(f"Kur verisi ({kur_sembolu}) alinamadi - TL cevrimi yapilamaz")

    eksik = sorted(
        sembol for sembol in yapilandirma.varliklar
        if sembol not in kapanis or kapanis[sembol].isna().all()
    )

    # Tespit yalnizca varliklarda calisir; kur sembolundeki %25'lik hareket
    # kurumsal olay degil, kur sokudur.
    varlik_sutunlari = [s for s in kapanis.columns if s in yapilandirma.varliklar]
    supheliler = kurumsal_olay_supheleri(
        kapanis[varlik_sutunlari], hacim, yapilandirma.kurumsal_olay, bilinen_olaylar
    )

    # ffill son GERCEK gozlemi tasir; o gozlemin tarihi kurun gercek yasidir.
    # Hafta sonu/tatilde Cuma kuru tasinir ve bunu bugunun kuru saymak tum
    # TL degerlemesini sessizce bayat bir kura baglar.
    kur_serisi = kapanis[kur_sembolu].dropna()
    yahoo_usdtry = float(kur_serisi.iloc[-1])
    kur_tarihi = kur_serisi.index[-1].date() if len(kur_serisi) else None
    try_gecmis, yerel_gecmis, kur_gecmis = _serileri_hazirla(kapanis, yapilandirma)
    return FiyatVerisi(
        try_gecmis=try_gecmis,
        usdtry=yahoo_usdtry,
        eksik_semboller=eksik,
        sinif_haritasi=yapilandirma.sinif_haritasi,
        kurumsal_olay_supheleri=supheliler,
        ucgenleme=kripto_ucgenlemesi(yapilandirma, yahoo_usdtry, env, getir,
                                     kur_tarihi=kur_tarihi),
        yerel_gecmis=yerel_gecmis,
        kur_gecmis=kur_gecmis,
    )
