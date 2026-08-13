"""BIST Yildiz Pazar evrenini mevcut portfoye gore tarar.

Soru: "hangi hisse yukselir?" degil - o soruya cevap veremiyoruz.
Soru: "hangi hisse mevcut portfoyume EN AZ benzeyen risk getirir?"

Siralama korelasyona gore yapilir cunku portfoy volatilitesini dusuren sey
varligin kendi getirisi degil, portfoyle olan dusuk korelasyonudur.

Kullanim:
    python scripts/yatirim/tarama.py            # gercek portfoye gore
    python scripts/yatirim/tarama.py --sim      # simulasyon portfoyune gore
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    PROJE_DIZINI,
    RAPOR_DIZINI,
    sablonu_reddet,
    yapilandirmayi_oku,
)
from fetch import fiyatlari_getir, kapanislari_indir  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from portfolio import portfoyu_hesapla, portfoyu_ledgerdan_hesapla  # noqa: E402
from risk import ortak_getiriler  # noqa: E402

EVREN_DOSYASI = PROJE_DIZINI / "bist-evreni.yaml"
SIM_DEFTERI = PROJE_DIZINI / "simulasyon" / "islemler.yaml"
MIN_GOZLEM = 60
BIST_SONEKI = ".IS"


@dataclass(frozen=True)
class Aday:
    ticker: str
    korelasyon: float
    yillik_volatilite: float
    yillik_getiri: float
    max_drawdown: float
    gozlem: int

    @property
    def getiri_risk(self) -> float:
        return self.yillik_getiri / self.yillik_volatilite if self.yillik_volatilite else 0.0


def evreni_oku(dosya: Path = EVREN_DOSYASI) -> list[str]:
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8"))
    return [f"{t}{BIST_SONEKI}" for t in ham["tickerlar"]]


def _max_drawdown(seri: pd.Series) -> float:
    temiz = seri.dropna()
    if temiz.empty:
        return 0.0
    return float((temiz / temiz.cummax() - 1.0).min())


def _portfoy_getirisi(fiyatlar, portfoy) -> pd.Series:
    """Mevcut portfoyun agirlikli gunluk TL getiri serisi."""
    getiriler = ortak_getiriler(fiyatlar.try_gecmis)
    agirliklar = portfoy.agirliklar
    ortak = [s for s in getiriler.columns if agirliklar.get(s, 0.0) > 0]
    if not ortak:
        raise RuntimeError("Portfoyde fiyatlanabilir pozisyon yok - tarama yapilamaz")
    vektor = pd.Series({s: agirliklar[s] for s in ortak}, dtype=float)
    return (getiriler[ortak].dropna() @ vektor).rename("portfoy")


def adaylari_degerlendir(evren: list[str], portfoy_getirisi: pd.Series,
                         gun: int, yil: int) -> list[Aday]:
    kapanis = kapanislari_indir(evren, gun)

    adaylar: list[Aday] = []
    for ticker in kapanis.columns:
        # Once o hissenin kendi islem gunlerine in, sonra getiri al:
        # aradaki bosluktan sonraki gunu NaN yapip silmesin.
        seri = kapanis[ticker].dropna().pct_change().dropna()
        hizali = pd.concat([seri, portfoy_getirisi], axis=1, join="inner").dropna()
        if len(hizali) < MIN_GOZLEM:
            continue
        fiyat_serisi = kapanis[ticker].dropna()
        adaylar.append(
            Aday(
                ticker=ticker,
                korelasyon=float(hizali.iloc[:, 0].corr(hizali.iloc[:, 1])),
                yillik_volatilite=float(seri.std() * np.sqrt(yil)),
                yillik_getiri=float(fiyat_serisi.iloc[-1] / fiyat_serisi.iloc[0] - 1.0),
                max_drawdown=_max_drawdown(fiyat_serisi),
                gozlem=len(hizali),
            )
        )
    adaylar.sort(key=lambda a: a.korelasyon)
    return adaylar


def _oran(deger: float) -> str:
    return f"{deger * 100:.1f}%"


def rapor_yaz(adaylar: list[Aday], elde_tutulan: set[str], kaynak: str) -> str:
    bugun = date.today().isoformat()
    satirlar = [
        "---",
        f"title: BIST Evren Taramasi {bugun}",
        f"date_created: {bugun}",
        "tags: [yatirim, bist, tarama]",
        "status: processed",
        'related: ["[[00-sistem]]", "[[korelasyon]]", "[[risk-butcesi]]"]',
        "---",
        "",
        f"# BIST Evren Taramasi {bugun}",
        "",
        f"Referans portfoy: **{kaynak}**. {len(adaylar)} hisse degerlendirildi.",
        "",
        "Siralama **portfoyle korelasyona** gore, dusukten yuksege. Ustteki hisseler "
        "portfoyune en az benzeyen riski getirir - yani en cok cesitlendirme saglar. "
        "Bu bir getiri tahmini degildir. Bkz. [[korelasyon]]",
        "",
        "| # | Hisse | Korelasyon | Yillik vol | 1y getiri | Max DD | Getiri/Risk | Not |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for sira, aday in enumerate(adaylar, 1):
        not_alani = "**elde**" if aday.ticker in elde_tutulan else ""
        satirlar.append(
            f"| {sira} | {aday.ticker} | {aday.korelasyon:.2f} | "
            f"{_oran(aday.yillik_volatilite)} | {_oran(aday.yillik_getiri)} | "
            f"{_oran(aday.max_drawdown)} | {aday.getiri_risk:.2f} | {not_alani} |"
        )

    satirlar += [
        "",
        "## Nasil okunur",
        "",
        "- **Korelasyon dusuk + volatilite makul** -> iyi cesitlendirici aday.",
        "- **Korelasyon dusuk ama volatilite cok yuksek** -> cesitlendirir ama "
        "kendi basina risk ekler; kucuk agirlikla girilir.",
        "- **Korelasyon yuksek** -> zaten sahip oldugun riskin kopyasi, eklemek "
        "pozisyon buyutmekten farksiz.",
        "- **Getiri/Risk** gecmis getirinin volatiliteye orani. Gecmise bakar, "
        "gelecege dair soz vermez.",
        "",
        "## Limitler",
        "",
        "- Evren 2026-06 tarihli Yildiz Pazar bilesen listesi; guncel olmayabilir.",
        "- Korelasyon sakin donemde olculur, kriz aninda 1'e kosar. Bkz. [[korelasyon]]",
        "- Bu tablo aday siralar, karar vermez. Yatirim tavsiyesi degildir.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="BIST evrenini portfoye gore tarar")
    ayristirici.add_argument("--sim", action="store_true", help="simulasyon portfoyunu kullan")
    argumanlar = ayristirici.parse_args()

    yapilandirma = yapilandirmayi_oku()
    if not argumanlar.sim:
        sablonu_reddet(yapilandirma)   # aga cikmadan once dur
    fiyatlar = fiyatlari_getir(yapilandirma)

    if argumanlar.sim:
        islemler, nakit, komisyon = islemleri_oku(SIM_DEFTERI)
        durum = durumu_hesapla(islemler, nakit, komisyon)
        portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
        kaynak = "simulasyon"
    else:
        portfoy = portfoyu_hesapla(yapilandirma, fiyatlar)
        kaynak = "portfoy.yaml"

    evren = evreni_oku()
    print(f"{len(evren)} BIST hissesi taraniyor ({kaynak} portfoyune gore)...")

    adaylar = adaylari_degerlendir(
        evren,
        _portfoy_getirisi(fiyatlar, portfoy),
        yapilandirma.ayarlar.gecmis_gun,
        yapilandirma.ayarlar.islem_gunu_yil,
    )
    if not adaylar:
        print("HATA - hicbir aday yeterli veri saglamadi")
        return 1

    elde = {p.sembol for p in portfoy.pozisyonlar}
    RAPOR_DIZINI.mkdir(parents=True, exist_ok=True)
    dosya = RAPOR_DIZINI / f"tarama-{date.today().isoformat()}.md"
    dosya.write_text(rapor_yaz(adaylar, elde, kaynak), encoding="utf-8")

    print(f"\nEn dusuk korelasyonlu 8 aday:")
    for aday in adaylar[:8]:
        print(f"  {aday.ticker:12} kor={aday.korelasyon:+.2f}  "
              f"vol={_oran(aday.yillik_volatilite):>6}  1y={_oran(aday.yillik_getiri):>8}")
    print(f"\nRapor: {dosya}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
