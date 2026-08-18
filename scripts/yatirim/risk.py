"""Risk metrikleri: volatilite, korelasyon, max drawdown, risk katkisi.

Tum hesaplar TL bazli gunluk getiriler uzerinden yapilir, yani kur
hareketi de risk olarak sayilir. Gecmis volatilite gelecek riski
garanti etmez - bu sayilar olcum, tahmin degil.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import RISK_DUZELT, Yapilandirma
from fetch import FiyatVerisi
from kurumsal_olay import KurumsalOlay
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
    dislanan: dict[str, str] = field(default_factory=dict)    # sembol -> gerekce
    duzeltilen: dict[str, str] = field(default_factory=dict)  # sembol -> gerekce
    gozlem_dususu: float = 0.0      # dislama yuzunden kaybedilen veri orani
    gozlem_dusus_esigi: float = 0.20

    @property
    def gozlem_guvenilirligi_dustu(self) -> bool:
        return self.gozlem_dususu > self.gozlem_dusus_esigi


def ortak_getiriler(gecmis: pd.DataFrame,
                    min_gozlem: int = MIN_GOZLEM) -> tuple[pd.DataFrame, list[str]]:
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

    Yetersiz gecmisli semboller kesisimden ONCE elenir. Aksi halde yeni
    listelenmis tek bir hisse tum portfoyun penceresini kendi gecmisine
    kirpar (365 gun beklerken 40 gunden hesap yapilir) veya hic veri
    yoksa kesisimi bosaltip tum raporu cokertir.

    Doner: (getiri matrisi, elenen semboller)
    """
    yeterli = [s for s in gecmis.columns if gecmis[s].count() >= min_gozlem]
    yetersiz = sorted(set(gecmis.columns) - set(yeterli))
    if not yeterli:
        raise RuntimeError(
            f"Hicbir varlikta yeterli gecmis yok (min {min_gozlem} gozlem)"
        )

    takvim = None
    for sutun in yeterli:
        gunler = gecmis[sutun].dropna().index
        takvim = gunler if takvim is None else takvim.intersection(gunler)
    if takvim is None or len(takvim) < 2:
        raise RuntimeError("Varliklarin ortak islem gunu yok - risk hesaplanamaz")

    return gecmis[yeterli].reindex(takvim).pct_change().dropna(how="all"), yetersiz


def _seriyi_duzelt(seri: pd.Series, olaylar: list[KurumsalOlay]) -> pd.Series:
    """Defterdeki oranla geri-duzeltme: olay tarihinden ONCEKI fiyatlar orana bolunur.

    Yahoo'nun `auto_adjust` ile kendi bildigi split'lere yaptigi islemin ayni.
    2.0 bedelsizde ex-tarihten onceki 100 TL, sonraki 50 TL ile ayni olceye
    gelsin diye 50'ye cekilir; boylece o gunun getirisi -%50 degil ~0 cikar.

    Adet/maliyet muhasebesiyle KARISTIRMA: orada toplam maliyet degismez
    (bkz. kurumsal_olay). Burada olcek birligi icin FIYAT serisi duzeltilir,
    portfoy degeri degil.
    """
    duzeltilmis = seri.astype(float).copy()
    for olay in olaylar:
        oncesi = duzeltilmis.index < pd.Timestamp(olay.tarih)
        duzeltilmis[oncesi] = duzeltilmis[oncesi] / olay.oran
    return duzeltilmis


def _risk_gecmisi(fiyatlar: FiyatVerisi, modu: str, olaylar: list[KurumsalOlay]
                  ) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    """Risk hesabina girecek seri + (dislananlar, duzeltilenler).

    Kurumsal olay suphesi olan sembolun HAM serisi risk hesabina giremez.
    Suphe, kayitli olmayan bir bedelsiz/split'in fiyati sicratmis olabilecegi
    demektir; sicrama getiri serisinde tek gunluk %25-50'lik hareket olarak
    durur ve volatiliteyi, korelasyonu, betayi sisirir. Degerlemeyi durdurup
    ayni seriden risk olcmek, fiyata guvenmedigimizi soyleyip o fiyattan
    turetilen riske guvenmek olurdu.

    Iki mod (`varliklar.yaml -> kurumsal_olay.risk_modu`):
      disla  - supheli sembol seriden cikarilir. Varsayilan.
      duzelt - defterdeki TUM olaylar geri-duzeltme olarak uygulanir, sonra
               hala supheli olan sembol dislanir.

    `duzelt` yalnizca defterdeki olaylari duzeltebilir; supheli sembol tam da
    olay defterde OLMADIGI icin supheli sayilir (bkz.
    kurumsal_olay.bilinen_olay_anahtarlari), yani ona uygulanacak oran yoktur
    ve dislanir. Modun asil isi, deftere YAZILMIS olayin seride birakigi
    sicramayi temizlemek: kayit suphe filtresini kapatir ama sicramayi silmez.
    """
    supheliler = {sembol: gerekce
                  for sembol, gerekce in fiyatlar.kurumsal_olay_supheleri.items()
                  if sembol in fiyatlar.try_gecmis.columns}
    if modu != RISK_DUZELT:
        return fiyatlar.try_gecmis.drop(columns=list(supheliler)), supheliler, {}

    sembol_olaylari: dict[str, list[KurumsalOlay]] = {}
    for olay in olaylar:
        if olay.sembol in fiyatlar.try_gecmis.columns:
            sembol_olaylari.setdefault(olay.sembol, []).append(olay)

    gecmis = fiyatlar.try_gecmis.copy()
    duzeltilen: dict[str, str] = {}
    for sembol, kendi in sembol_olaylari.items():
        gecmis[sembol] = _seriyi_duzelt(gecmis[sembol], kendi)
        duzeltilen[sembol] = ", ".join(
            f"{olay.tarih} {olay.tip} x{olay.oran:g}" for olay in kendi)

    dislanan = {
        sembol: f"{gerekce} - defterde oran yok, duzeltilemedi"
        for sembol, gerekce in supheliler.items() if sembol not in sembol_olaylari
    }
    return gecmis.drop(columns=list(dislanan)), dislanan, duzeltilen


def _gunluk_getiriler(gecmis: pd.DataFrame,
                      dislanan: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    if gecmis.columns.empty:
        raise RuntimeError(
            "Tum semboller kurumsal olay suphesiyle dislandi, risk hesaplanamaz: "
            + ", ".join(f"{s} ({g})" for s, g in sorted(dislanan.items()))
        )
    return ortak_getiriler(gecmis)


def _gozlem_dususu(dislanmis: pd.DataFrame, ham: pd.DataFrame) -> float:
    """Dislama veri setinin ne kadarini goturdu? 0 = kayip yok.

    Olcu GOZLEM HUCRESI (gun x sembol). Yalnizca gun sayisina bakmak yanlis
    olurdu: ortak takvim bir KESISIM oldugu icin sembol cikarmak gun sayisini
    dusurmez, artirir. Kaybedilen sey gun degil, kapsam - portfoy
    volatilitesi ve korelasyon matrisi eksik sembolle olculur.
    """
    tam = int(ham.notna().to_numpy().sum())
    if tam == 0:
        return 0.0
    kalan = int(dislanmis.notna().to_numpy().sum())
    return max(0.0, 1.0 - kalan / tam)


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
                  portfoy: Portfoy,
                  olaylar: list[KurumsalOlay] | None = None) -> RiskRaporu:
    ayarlar = yapilandirma.kurumsal_olay
    gecmis, dislanan, duzeltilen = _risk_gecmisi(
        fiyatlar, ayarlar.risk_modu, list(olaylar or []))
    getiriler, yetersiz = _gunluk_getiriler(gecmis, dislanan)
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
            # Portfoy drawdown'i ile AYNI pencereden olculur (ortak takvim).
            # Ham 365 gunluk seriden olcmek ayni tablonun iki sutununu
            # farkli zaman araliklarina dayandiriyordu.
            max_drawdown=_max_drawdown(
                (1.0 + getiriler[sembol]).cumprod()
            ),
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
        dislanan=dislanan,
        duzeltilen=duzeltilen,
        gozlem_dususu=_gozlem_dususu(gecmis, fiyatlar.try_gecmis),
        gozlem_dusus_esigi=ayarlar.gozlem_dusus_esigi,
    )
