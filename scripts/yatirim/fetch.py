"""Yahoo Finance'ten fiyat gecmisi ceker ve TL bazina cevirir."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from config import Yapilandirma


BAYAT_ESIGI_GUN = 7


@dataclass(frozen=True)
class FiyatVerisi:
    """TL bazina cevrilmis gunluk kapanis serileri."""

    try_gecmis: pd.DataFrame          # sutun = sembol, deger = TL fiyat
    usdtry: float
    eksik_semboller: list[str]

    @property
    def son_fiyatlar(self) -> dict[str, float]:
        """Degerleme fiyatlari. Bosluklar ffill'lenir - son BILINEN fiyat kullanilir."""
        son = self.try_gecmis.ffill().iloc[-1]
        return {sembol: float(deger) for sembol, deger in son.items() if pd.notna(deger)}

    @property
    def son_tarih(self) -> str:
        return self.try_gecmis.index[-1].date().isoformat()

    def bayat_semboller(self, esik_gun: int = BAYAT_ESIGI_GUN) -> dict[str, int]:
        """Fiyati esikten eski olan semboller -> kac gundur guncellenmedigi.

        ffill sessizce eski fiyati tasir; delist olmus veya veri akisi kesilmis
        bir varlik dogru fiyatliymis gibi gorunur. Bu, sorunu gorunur kilar.
        """
        son_gun = self.try_gecmis.index[-1]
        bayatlar: dict[str, int] = {}
        for sembol in self.try_gecmis.columns:
            gecerli = self.try_gecmis[sembol].dropna()
            if gecerli.empty:
                continue
            gecikme = (son_gun - gecerli.index[-1]).days
            if gecikme > esik_gun:
                bayatlar[sembol] = gecikme
        return bayatlar


def kapanislari_indir(semboller: list[str], gun: int) -> pd.DataFrame:
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

    kapanis = ham["Close"]
    if isinstance(kapanis, pd.Series):
        kapanis = kapanis.to_frame(semboller[0])
    return kapanis.dropna(how="all")


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
        if sembol not in kapanis:
            continue
        seri = kapanis[sembol] * varlik.carpan
        sutunlar[sembol] = seri * kur_serisi if varlik.kur == "USD" else seri
    return pd.DataFrame(sutunlar).dropna(how="all")


def fiyatlari_getir(yapilandirma: Yapilandirma) -> FiyatVerisi:
    semboller = yapilandirma.fiyat_sembolleri
    kapanis = kapanislari_indir(semboller, yapilandirma.ayarlar.gecmis_gun)

    kur_sembolu = yapilandirma.ayarlar.kur_sembolu
    if kur_sembolu not in kapanis or kapanis[kur_sembolu].isna().all():
        raise RuntimeError(f"Kur verisi ({kur_sembolu}) alinamadi - TL cevrimi yapilamaz")

    eksik = sorted(
        sembol for sembol in yapilandirma.varliklar
        if sembol not in kapanis or kapanis[sembol].isna().all()
    )
    return FiyatVerisi(
        try_gecmis=_tl_bazina_cevir(kapanis, yapilandirma),
        usdtry=float(kapanis[kur_sembolu].ffill().iloc[-1]),
        eksik_semboller=eksik,
    )
