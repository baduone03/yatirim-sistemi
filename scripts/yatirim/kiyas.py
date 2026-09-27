"""Alternatif kiyasi: ayni sermaye baslangicta TEK bir yere konsaydi bugun ne olurdu.

Portfoyun kendi getirisi tek basina bir sey soylemez: %3 kar, BIST 100 %8
yukseldiyse kotu, mevduat %4 verdiyse de sifirdir. Soru "nerede
degerlendirmeli" ise cevap bu karsilastirmadadir.

Kiyas sembolleri `varliklar.yaml -> kiyas` icinde, kodda DEGIL. Mevduat satiri
sembol degildir: TL risksiz oran (`maliyet.tl_risksiz_yillik`) donem gunune
bilesik uygulanir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from maliyet import donem_orani


@dataclass(frozen=True)
class KiyasSatiri:
    ad: str
    deger_try: float | None       # None = olculemedi, `not_` sebebini yazar
    getiri: float | None
    not_: str = ""
    portfoy: bool = False         # raporda vurgulanan "bu portfoy" satiri


def baslangic_fiyati(seri: pd.Series, baslangic: str) -> float | None:
    """Baslangic gunu veya sonrasindaki ILK gercek kapanis.

    ffill YAPILMAZ: baslangictan onceki bir fiyati kullanmak, o gun
    alinamayacak bir fiyattan alim yapmis gibi davranir. Baslangic gunu piyasa
    kapaliysa (hafta sonu, tatil) ilk acik gun kullanilir - gercek alim da o
    gun olurdu.
    """
    gun = date.fromisoformat(baslangic)
    temiz = seri.dropna()
    sonrasi = temiz[temiz.index.date >= gun]
    return float(sonrasi.iloc[0]) if len(sonrasi) else None


def kiyaslari_hesapla(sermaye: float, baslangic: str, portfoy_degeri: float,
                      semboller: list[str], adlar: dict[str, str],
                      try_gecmis: pd.DataFrame, son_fiyatlar: dict[str, float],
                      komisyon_orani: float, risksiz_yillik: float | None,
                      gun: int) -> list[KiyasSatiri]:
    """Portfoy + her kiyas sembolu + mevduat. Degere gore azalan sirali.

    Tek seferlik alim varsayilir: `sermaye * (1 - komisyon)` baslangic
    fiyatindan alinir, bugunku fiyattan degerlenir. Satis komisyonu dusulmez -
    portfoy de acik pozisyonlarini satmadan degerleniyor.
    """
    satirlar = [KiyasSatiri("Bu portfoy", portfoy_degeri,
                            portfoy_degeri / sermaye - 1, portfoy=True)]

    for sembol in semboller:
        ad = adlar.get(sembol, sembol)
        seri = try_gecmis[sembol] if sembol in try_gecmis.columns else None
        ilk = baslangic_fiyati(seri, baslangic) if seri is not None else None
        # Son fiyat AYNI seriden: `son_fiyatlar` kriptoda BTCTurk ile ezilir,
        # Yahoo baslangicina BTCTurk bitisi bolmek TR primini getiri sayar.
        # `son_fiyatlar` yalnizca kapi: supheli/durdurulan sembol orada yok.
        son = (float(seri.dropna().iloc[-1])
               if seri is not None and sembol in son_fiyatlar
               and seri.notna().any() else None)
        if ilk is None or son is None:
            eksik = "baslangic fiyati yok" if ilk is None else "guncel fiyat yok"
            satirlar.append(KiyasSatiri(ad, None, None, eksik))
            continue
        deger = sermaye * (1 - komisyon_orani) * son / ilk
        satirlar.append(KiyasSatiri(ad, deger, deger / sermaye - 1))

    if risksiz_yillik is None:
        satirlar.append(KiyasSatiri("Mevduat", None, None, "risksiz oran yok"))
    else:
        oran = donem_orani(risksiz_yillik, gun)
        satirlar.append(KiyasSatiri(
            "Mevduat", sermaye * (1 + oran), oran,
            "BRUT, bugunku yillik oran geriye uygulandi"))

    olculen = sorted((s for s in satirlar if s.deger_try is not None),
                     key=lambda s: s.deger_try, reverse=True)
    return olculen + [s for s in satirlar if s.deger_try is None]
