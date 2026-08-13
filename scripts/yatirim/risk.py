"""Risk metrikleri: volatilite, korelasyon, max drawdown, risk katkisi.

Tum hesaplar TL bazli gunluk getiriler uzerinden yapilir, yani kur
hareketi de risk olarak sayilir. Gecmis volatilite gelecek riski
garanti etmez - bu sayilar olcum, tahmin degil.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import Yapilandirma
from fetch import FiyatVerisi
from portfolio import Portfoy

MIN_GOZLEM = 30


@dataclass(frozen=True)
class VarlikRiski:
    sembol: str
    yillik_volatilite: float
    max_drawdown: float
    risk_katkisi: float          # portfoy volatilitesinin bu varliktan gelen orani
    agirlik: float = 0.0         # portfoy icindeki sermaye agirligi

    @property
    def beta(self) -> float:
        """Risk katkisi / agirlik = varligin portfoye betasi.

        1'in ustu: parasindan fazla risk tasiyor.
        1'in alti: parasindan az risk tasiyor (verimli tasiyici).

        Pozisyonu kucultmek katkiyi dusurur ama betayi degistirmez -
        beta varligin ozelligidir. Bu yuzden "kis" karari icin dogru
        olcut ham katki degil, katki VE beta birlikte.
        """
        return self.risk_katkisi / self.agirlik if self.agirlik > 0 else 0.0


@dataclass(frozen=True)
class RiskRaporu:
    portfoy_volatilitesi: float
    portfoy_max_drawdown: float
    varlik_riskleri: list[VarlikRiski]
    korelasyon: pd.DataFrame
    gozlem_sayisi: int
    yetersiz_veri: list[str]
    yillik_periyot: float = 252.0     # yillicklastirmada kullanilan gercek carpan


def ortak_getiriler(gecmis: pd.DataFrame) -> pd.DataFrame:
    """Karisik takvimli varliklar icin dogru gunluk getiri matrisi.

    Sorun: BIST hafta sonu kapali, kripto acik, ABD'nin tatilleri farkli.
      - ffill edip getiri alirsan kapali gunler sifir getiri olur ->
        volatilite sistematik olarak dusuk cikar.
      - ffill etmeden getiri alirsan NaN'den sonraki gun de NaN olur ->
        her Pazartesi BIST getirisi silinir, veri %30 azalir.

    Cozum: once TUM varliklarin gercekten islem gordugu ortak takvime
    hizala, sonra getiri al. Boylece her varligin getirisi ayni zaman
    araligini kapsar (Cuma->Pazartesi herkeste 3 gun), kriptonun hafta
    sonu hareketi de Pazartesi getirisine dogru sekilde katilir.
    """
    takvim = None
    for sutun in gecmis.columns:
        gunler = gecmis[sutun].dropna().index
        takvim = gunler if takvim is None else takvim.intersection(gunler)
    if takvim is None or len(takvim) < 2:
        raise RuntimeError("Varliklarin ortak islem gunu yok - risk hesaplanamaz")
    return gecmis.reindex(takvim).pct_change().dropna(how="all")


def _gunluk_getiriler(fiyatlar: FiyatVerisi) -> pd.DataFrame:
    return ortak_getiriler(fiyatlar.try_gecmis)


def yillik_periyot_sayisi(getiriler: pd.DataFrame, varsayilan: int) -> float:
    """Yillicklastirma carpanini VERIDEN turetir, sabit varsaymaz.

    Ortak islem takvimi kesisim oldugu icin yilda ~252 degil ~238 gun kalir.
    sqrt(252) ile carpmak volatiliteyi yaklasik %3 sisirir. Gercekte gozlenen
    periyot yogunlugunu kullanmak daha dogru.

    Cok kisa pencerede tahmin guvenilmez olacagi icin varsayilana dusulur.
    """
    if len(getiriler) < 2:
        return float(varsayilan)
    gun_araligi = (getiriler.index[-1] - getiriler.index[0]).days
    if gun_araligi <= 0:
        return float(varsayilan)
    return len(getiriler) * 365.25 / gun_araligi


def _max_drawdown(seri: pd.Series) -> float:
    """En yuksek tepeden en dip noktaya gorulen maksimum yuzde dusus (negatif)."""
    temiz = seri.dropna()
    if temiz.empty:
        return 0.0
    zirve = temiz.cummax()
    return float((temiz / zirve - 1.0).min())


def _risk_katkilari(kovaryans: pd.DataFrame, agirliklar: pd.Series) -> tuple[float, pd.Series]:
    """Euler ayristirmasi: katki_i = w_i * (Sigma w)_i / sigma_p."""
    varyans = float(agirliklar @ kovaryans @ agirliklar)
    if varyans <= 0:
        return 0.0, pd.Series(0.0, index=agirliklar.index)
    sigma = np.sqrt(varyans)
    marjinal = kovaryans @ agirliklar
    return sigma, (agirliklar * marjinal) / sigma


def riski_hesapla(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi,
                  portfoy: Portfoy) -> RiskRaporu:
    getiriler = _gunluk_getiriler(fiyatlar)
    yeterli = [s for s in getiriler.columns if getiriler[s].count() >= MIN_GOZLEM]
    yetersiz = sorted(set(getiriler.columns) - set(yeterli))
    getiriler = getiriler[yeterli].dropna()

    if getiriler.empty:
        raise RuntimeError(f"Risk hesabi icin yeterli veri yok (min {MIN_GOZLEM} gozlem)")

    yil = yillik_periyot_sayisi(getiriler, yapilandirma.ayarlar.islem_gunu_yil)
    kovaryans = getiriler.cov() * yil
    volatiliteler = getiriler.std() * np.sqrt(yil)

    tum_agirliklar = portfoy.agirliklar
    agirliklar = pd.Series(
        {s: tum_agirliklar.get(s, 0.0) for s in getiriler.columns}, dtype=float
    )
    portfoy_vol, katkilar = _risk_katkilari(kovaryans, agirliklar)

    portfoy_getirisi = getiriler @ agirliklar
    portfoy_seyri = (1.0 + portfoy_getirisi).cumprod()

    riskler = [
        VarlikRiski(
            sembol=sembol,
            yillik_volatilite=float(volatiliteler[sembol]),
            max_drawdown=_max_drawdown(fiyatlar.try_gecmis[sembol]),
            risk_katkisi=float(katkilar[sembol] / portfoy_vol) if portfoy_vol > 0 else 0.0,
            agirlik=float(agirliklar[sembol]),
        )
        for sembol in getiriler.columns
    ]
    riskler.sort(key=lambda r: r.risk_katkisi, reverse=True)

    return RiskRaporu(
        portfoy_volatilitesi=portfoy_vol,
        portfoy_max_drawdown=_max_drawdown(portfoy_seyri),
        varlik_riskleri=riskler,
        korelasyon=getiriler.corr(),
        gozlem_sayisi=len(getiriler),
        yetersiz_veri=yetersiz,
        yillik_periyot=yil,
    )
