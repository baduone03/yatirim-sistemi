"""Yahoo Finance'ten fiyat gecmisi ceker ve TL bazina cevirir."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from config import BayatlikEsikleri, KurumsalOlayAyarlari, Yapilandirma


BAYAT_ESIGI_GUN = 7


@dataclass(frozen=True)
class FiyatVerisi:
    """TL bazina cevrilmis gunluk kapanis serileri."""

    try_gecmis: pd.DataFrame          # sutun = sembol, deger = TL fiyat
    usdtry: float
    eksik_semboller: list[str]
    sinif_haritasi: dict[str, str] = field(default_factory=dict)
    kurumsal_olay_supheleri: dict[str, str] = field(default_factory=dict)

    @property
    def son_fiyatlar(self) -> dict[str, float]:
        """Degerleme fiyatlari. Bosluklar ffill'lenir - son BILINEN fiyat kullanilir.

        Kurumsal olay suphesi olan sembol DISARIDA birakilir: fiyat sicramasi
        gercek kayip mi yoksa kayitli olmayan bedelsiz/split mi belli degilse
        deger uretmek, yanlis rakami dogruymus gibi sunmaktir. Disarida kalan
        sembol portfoy.fiyatlanamayan icinde raporlanir.
        """
        son = self.try_gecmis.ffill().iloc[-1]
        return {
            sembol: float(deger) for sembol, deger in son.items()
            if pd.notna(deger) and sembol not in self.kurumsal_olay_supheleri
        }

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
    ham = yf.download(
        semboller,
        period=f"{gun}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
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


def _tl_bazina_cevir(kapanis: pd.DataFrame, yapilandirma: Yapilandirma) -> pd.DataFrame:
    """Fiyatlari TL'ye cevirir.

    Yalnizca KUR serisi ffill edilir (carpan olarak her gun gerekli).
    Varlik serileri ffill EDILMEZ: BIST hafta sonu kapali, kripto acik.
    Kapali gunu doldurmak yapay sifir-getirili gun uretir ve volatiliteyi
    sistematik olarak dusuk gosterir. Bosluklar NaN kalir; degerleme
    son_fiyatlar icinde ayrica ffill'lenir.
    """
    kur_serisi = kapanis[yapilandirma.ayarlar.kur_sembolu].ffill()
    sutunlar = {}
    for sembol, varlik in yapilandirma.varliklar.items():
        # Hepsi NaN olan sembol tamamen DISARIDA birakilir. Sutun olarak
        # kalirsa ortak takvim kesisimini bosaltip tum risk hesabini cokertir;
        # zaten eksik_semboller icinde raporlaniyor.
        if sembol not in kapanis or kapanis[sembol].isna().all():
            continue
        seri = kapanis[sembol] * varlik.carpan
        sutunlar[sembol] = seri * kur_serisi if varlik.kur == "USD" else seri
    if not sutunlar:
        raise RuntimeError("Hicbir varlik icin fiyat verisi alinamadi")
    return pd.DataFrame(sutunlar).dropna(how="all")


def fiyatlari_getir(yapilandirma: Yapilandirma,
                    bilinen_olaylar: set[tuple[str, str]] | None = None) -> FiyatVerisi:
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

    return FiyatVerisi(
        try_gecmis=_tl_bazina_cevir(kapanis, yapilandirma),
        usdtry=float(kapanis[kur_sembolu].ffill().iloc[-1]),
        eksik_semboller=eksik,
        sinif_haritasi=yapilandirma.sinif_haritasi,
        kurumsal_olay_supheleri=supheliler,
    )
