"""Hesaplanan portfoy ve risk verisini markdown rapora cevirir."""

from __future__ import annotations

from datetime import date

import pandas as pd

from config import Yapilandirma
from fetch import FiyatVerisi
from portfolio import Portfoy, SinifSapmasi
from risk import RiskRaporu

REBALANCING_ESIGI = 0.05          # hedeften 5 puan sapma -> uyari
OZET_BASLANGIC = "<!-- OZET:BASLANGIC -->"
OZET_BITIS = "<!-- OZET:BITIS -->"


def _tl(deger: float) -> str:
    return f"{deger:,.0f} TL".replace(",", ".")


def _yuzde(oran: float, basamak: int = 1) -> str:
    return f"{oran * 100:+.{basamak}f}%"


def _oran(oran: float, basamak: int = 1) -> str:
    return f"{oran * 100:.{basamak}f}%"


def _frontmatter(bugun: str, fiyat_tarihi: str, baslik: str = "Yatirim Raporu") -> list[str]:
    return [
        "---",
        f"title: {baslik} {bugun}",
        f"date_created: {bugun}",
        "tags: [yatirim, portfoy, risk, rapor]",
        "status: processed",
        'related: ["[[00-sistem]]"]',
        f"fiyat_tarihi: {fiyat_tarihi}",
        "---",
        "",
    ]


def _ozet_bolumu(portfoy: Portfoy, risk: RiskRaporu, fiyatlar: FiyatVerisi) -> list[str]:
    kar_zarar = portfoy.toplam_deger_try - portfoy.toplam_maliyet_try
    getiri = kar_zarar / portfoy.toplam_maliyet_try if portfoy.toplam_maliyet_try else 0.0
    return [
        "## Ozet",
        "",
        "| Olcut | Deger |",
        "|---|---|",
        f"| Toplam deger | {_tl(portfoy.toplam_deger_try)} |",
        f"| Toplam maliyet | {_tl(portfoy.toplam_maliyet_try)} |",
        f"| Kar/zarar | {_tl(kar_zarar)} ({_yuzde(getiri)}) |",
        f"| Nakit | {_tl(portfoy.nakit_try)} |",
        f"| USD/TRY | {fiyatlar.usdtry:,.2f} |",
        f"| Yillik volatilite | {_oran(risk.portfoy_volatilitesi)} |",
        f"| Max drawdown (1y) | {_oran(risk.portfoy_max_drawdown)} |",
        "",
    ]


def _pozisyon_bolumu(portfoy: Portfoy) -> list[str]:
    satirlar = [
        "## Pozisyonlar",
        "",
        "| Varlik | Sinif | Adet | Maliyet | Deger | K/Z | K/Z % | Agirlik |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    agirliklar = portfoy.agirliklar
    for pozisyon in sorted(portfoy.pozisyonlar, key=lambda p: p.deger_try, reverse=True):
        satirlar.append(
            f"| {pozisyon.ad} | {pozisyon.sinif} | {pozisyon.adet:g} | "
            f"{_tl(pozisyon.maliyet_try)} | {_tl(pozisyon.deger_try)} | "
            f"{_tl(pozisyon.kar_zarar_try)} | {_yuzde(pozisyon.kar_zarar_yuzde)} | "
            f"{_oran(agirliklar.get(pozisyon.sembol, 0.0))} |"
        )
    satirlar.append("")
    return satirlar


def _dagilim_bolumu(sapmalar: list[SinifSapmasi], toplam_deger: float) -> list[str]:
    satirlar = [
        "## Varlik dagilimi ve rebalancing",
        "",
        "| Sinif | Guncel | Hedef | Sapma | Eylem |",
        "|---|---:|---:|---:|---|",
    ]
    uyarilar = []
    for sapma in sapmalar:
        tutar = abs(sapma.sapma) * toplam_deger
        if abs(sapma.sapma) < REBALANCING_ESIGI:
            eylem = "dengede"
        elif sapma.sapma > 0:
            eylem = f"{_tl(tutar)} azalt"
            uyarilar.append(f"`{sapma.sinif}` hedefin {_oran(sapma.sapma)} uzerinde")
        else:
            eylem = f"{_tl(tutar)} artir"
            uyarilar.append(f"`{sapma.sinif}` hedefin {_oran(-sapma.sapma)} altinda")
        satirlar.append(
            f"| {sapma.sinif} | {_oran(sapma.guncel_agirlik)} | "
            f"{_oran(sapma.hedef_agirlik)} | {_yuzde(sapma.sapma)} | {eylem} |"
        )

    satirlar.append("")
    if uyarilar:
        satirlar.append(f"> Rebalancing uyarisi (esik {_oran(REBALANCING_ESIGI, 0)}):")
        satirlar.extend(f"> - {u}" for u in uyarilar)
        satirlar.append("")
    return satirlar


def _risk_bolumu(risk: RiskRaporu, varlik_adlari: dict[str, str]) -> list[str]:
    satirlar = [
        "## Risk metrikleri",
        "",
        f"Pencere: son {risk.gozlem_sayisi} islem gunu, TL bazli gunluk getiriler. "
        f"Yillicklastirma carpani {risk.yillik_periyot:.0f} (veriden turetildi).",
        "",
        "| Varlik | Yillik volatilite | Max drawdown | Risk katkisi |",
        "|---|---:|---:|---:|",
    ]
    for varlik_riski in risk.varlik_riskleri:
        satirlar.append(
            f"| {varlik_adlari.get(varlik_riski.sembol, varlik_riski.sembol)} | "
            f"{_oran(varlik_riski.yillik_volatilite)} | "
            f"{_oran(varlik_riski.max_drawdown)} | "
            f"{_oran(varlik_riski.risk_katkisi)} |"
        )
    satirlar += ["", "Risk katkisi = varligin portfoy volatilitesindeki payi. "
                 "Agirligindan buyukse portfoyu tek basina o varlik suruyor.", ""]
    return satirlar


def _korelasyon_bolumu(korelasyon: pd.DataFrame) -> list[str]:
    semboller = list(korelasyon.columns)
    satirlar = [
        "## Korelasyon matrisi",
        "",
        "| | " + " | ".join(semboller) + " |",
        "|---|" + "---:|" * len(semboller),
    ]
    for satir in semboller:
        degerler = " | ".join(f"{korelasyon.loc[satir, sutun]:.2f}" for sutun in semboller)
        satirlar.append(f"| **{satir}** | {degerler} |")
    satirlar += ["", "1'e yakin = birlikte hareket eder, cesitlendirme saglamaz.", ""]
    return satirlar


def _uyari_bolumu(portfoy: Portfoy, fiyatlar: FiyatVerisi, risk: RiskRaporu) -> list[str]:
    sorunlar = []
    if fiyatlar.eksik_semboller:
        sorunlar.append(f"Fiyat verisi gelmeyen sembol: {', '.join(fiyatlar.eksik_semboller)}")
    bayatlar = fiyatlar.bayat_semboller()
    if bayatlar:
        detay = ", ".join(f"{s} ({g} gun)" for s, g in sorted(bayatlar.items()))
        sorunlar.append(
            f"**Bayat fiyat** - degerleme eski fiyatla yapildi: {detay}"
        )
    if portfoy.fiyatlanamayan:
        sorunlar.append(
            f"Fiyatlanamadigi icin toplama girmeyen pozisyon: {', '.join(portfoy.fiyatlanamayan)}"
        )
    if risk.yetersiz_veri:
        sorunlar.append(
            f"Risk hesabina girmeyen (yetersiz gecmis): {', '.join(risk.yetersiz_veri)}"
        )
    if not sorunlar:
        return []
    return ["## Veri uyarilari", "", *[f"- {s}" for s in sorunlar], ""]


def _sim_bolumu(durum, portfoy: Portfoy) -> list[str]:
    """Simulasyon defterine ozel bolum: baslangic sermayesine gore performans."""
    baslangic = durum.baslangic_nakit_try
    net = portfoy.toplam_deger_try - baslangic
    getiri = net / baslangic if baslangic else 0.0
    gerceklesmemis = net - durum.gerceklesen_kar_try + durum.toplam_komisyon_try

    satirlar = [
        "## Simulasyon performansi",
        "",
        "| Olcut | Deger |",
        "|---|---|",
        f"| Baslangic sermayesi | {_tl(baslangic)} |",
        f"| Guncel deger | {_tl(portfoy.toplam_deger_try)} |",
        f"| Net sonuc | {_tl(net)} ({_yuzde(getiri)}) |",
        f"| Gerceklesen kar (satislardan) | {_tl(durum.gerceklesen_kar_try)} |",
        f"| Gerceklesmemis kar (aciktaki) | {_tl(gerceklesmemis)} |",
        f"| Odenen komisyon | {_tl(durum.toplam_komisyon_try)} "
        f"(oran {_oran(durum.komisyon_orani, 2)}) |",
        f"| Islem sayisi | {len(durum.islemler)} |",
        "",
    ]
    return satirlar


def _islem_gecmisi_bolumu(durum) -> list[str]:
    satirlar = [
        "## Islem gecmisi",
        "",
        "| Tarih | Yon | Varlik | Adet | Fiyat | Tutar | Gerekce |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for islem in durum.islemler:
        satirlar.append(
            f"| {islem.tarih} | {islem.yon} | {islem.sembol} | {islem.adet:g} | "
            f"{_tl(islem.fiyat_try)} | {_tl(islem.tutar_try)} | {islem.gerekce} |"
        )
    satirlar.append("")
    return satirlar


def _limitler() -> list[str]:
    return [
        "## Limitler",
        "",
        "- Veri Yahoo Finance kaynakli, gecikmeli olabilir; BIST sembollerinde bosluk gorulur.",
        "- Gecmis volatilite ve korelasyon gelecek riski garanti etmez.",
        "- Maliyet TL cevrimi guncel kurla yapilir, alis kuru farki K/Z'ye yansimaz.",
        "- Bu rapor olcum ve uyari uretir; yatirim tavsiyesi degildir.",
        "",
    ]


def rapor_olustur(yapilandirma: Yapilandirma, fiyatlar: FiyatVerisi,
                  portfoy: Portfoy, sapmalar: list[SinifSapmasi],
                  risk: RiskRaporu, durum=None) -> str:
    bugun = date.today().isoformat()
    varlik_adlari = {s: v.ad for s, v in yapilandirma.varliklar.items()}
    baslik = "Simulasyon Raporu" if durum else "Yatirim Raporu"

    satirlar = _frontmatter(bugun, fiyatlar.son_tarih, baslik)
    satirlar += [f"# {baslik} {bugun}", ""]
    if durum:
        satirlar += _sim_bolumu(durum, portfoy)
    satirlar += _ozet_bolumu(portfoy, risk, fiyatlar)
    satirlar += _pozisyon_bolumu(portfoy)
    satirlar += _dagilim_bolumu(sapmalar, portfoy.toplam_deger_try)
    satirlar += _risk_bolumu(risk, varlik_adlari)
    satirlar += _korelasyon_bolumu(risk.korelasyon)
    if durum:
        satirlar += _islem_gecmisi_bolumu(durum)
    satirlar += _uyari_bolumu(portfoy, fiyatlar, risk)
    satirlar += _limitler()
    return "\n".join(satirlar)


def sistem_ozeti(portfoy: Portfoy, risk: RiskRaporu, rapor_adi: str) -> str:
    kar_zarar = portfoy.toplam_deger_try - portfoy.toplam_maliyet_try
    getiri = kar_zarar / portfoy.toplam_maliyet_try if portfoy.toplam_maliyet_try else 0.0
    return "\n".join([
        OZET_BASLANGIC,
        f"Son guncelleme: {date.today().isoformat()}",
        "",
        "| Olcut | Deger |",
        "|---|---|",
        f"| Toplam deger | {_tl(portfoy.toplam_deger_try)} |",
        f"| Kar/zarar | {_tl(kar_zarar)} ({_yuzde(getiri)}) |",
        f"| Yillik volatilite | {_oran(risk.portfoy_volatilitesi)} |",
        f"| Max drawdown | {_oran(risk.portfoy_max_drawdown)} |",
        "",
        f"Detay: [[{rapor_adi}]]",
        OZET_BITIS,
    ])
