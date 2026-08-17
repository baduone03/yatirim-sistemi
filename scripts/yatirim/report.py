"""Hesaplanan portfoy ve risk verisini markdown rapora cevirir."""

from __future__ import annotations

from datetime import date

import pandas as pd

from config import Yapilandirma
from fetch import FiyatVerisi
from portfolio import Portfoy, SinifSapmasi
from risk import RiskRaporu

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


def _ozet_bolumu(portfoy: Portfoy, risk: RiskRaporu, fiyatlar: FiyatVerisi,
                 sim: bool = False) -> list[str]:
    """Portfoy ozeti.

    Sim modunda 'toplam maliyet' satiri YAZILMAZ: nakit zaten satis hasilatini
    ve odenen komisyonlari icerdigi icin deger-maliyet farki ekonomik anlam
    tasimaz ve 'Simulasyon performansi' bolumundeki net sonucla celisirdi.
    Sim modunda gecerli tek K/Z olcutu aciktaki pozisyonlarin karidir.
    """
    maliyet = portfoy.pozisyon_maliyet_try if sim else portfoy.toplam_maliyet_try
    kar_zarar = portfoy.gerceklesmemis_kar_try if sim else (
        portfoy.toplam_deger_try - portfoy.toplam_maliyet_try)
    getiri = kar_zarar / maliyet if maliyet else 0.0
    etiket = "Gerceklesmemis K/Z (aciktaki)" if sim else "Kar/zarar"
    return [
        "## Ozet",
        "",
        "| Olcut | Deger |",
        "|---|---|",
        f"| Toplam deger | {_tl(portfoy.toplam_deger_try)} |",
        f"| {'Pozisyon maliyeti' if sim else 'Toplam maliyet'} | {_tl(maliyet)} |",
        f"| {etiket} | {_tl(kar_zarar)} ({_yuzde(getiri)}) |",
        f"| Nakit | {_tl(portfoy.nakit_try)} |",
        f"| USD/TRY | {fiyatlar.usdtry:,.2f} |",
        f"| Yillik volatilite | {_oran(risk.portfoy_volatilitesi)} |",
        f"| Max drawdown (hipotetik) | {_oran(risk.portfoy_max_drawdown)} |",
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


def _dagilim_bolumu(sapmalar: list[SinifSapmasi], toplam_deger: float,
                    esik: float, eksik_pozisyon: list[str]) -> list[str]:
    satirlar = ["## Varlik dagilimi ve rebalancing", ""]

    if eksik_pozisyon:
        # Fiyatlanamayan pozisyon toplam degere girmiyor -> o sinifin agirligi
        # dusuk cikar -> "artir" tavsiyesi uretilir. Tavsiye guvenilmez.
        satirlar += [
            f"> ⚠️ **Bu tablo eksik veri uzerinden hesaplandi.** "
            f"Fiyatlanamayan pozisyon: {', '.join(eksik_pozisyon)}. "
            "Bu pozisyonlar toplam degere girmedigi icin ait olduklari sinifin "
            "agirligi oldugundan DUSUK gorunur; asagidaki rebalancing tavsiyesine "
            "veri duzelene kadar guvenme.",
            "",
        ]

    satirlar += [
        "| Sinif | Guncel | Hedef | Sapma | Eylem |",
        "|---|---:|---:|---:|---|",
    ]
    uyarilar = []
    for sapma in sapmalar:
        tutar = abs(sapma.sapma) * toplam_deger
        if abs(sapma.sapma) < esik:
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
        satirlar.append(f"> Rebalancing uyarisi (esik {_oran(esik, 0)}):")
        satirlar.extend(f"> - {u}" for u in uyarilar)
        satirlar.append("")
    return satirlar


def _risk_bolumu(risk: RiskRaporu, varlik_adlari: dict[str, str],
                 esikler) -> list[str]:
    satirlar = [
        "## Risk metrikleri",
        "",
        f"Pencere: son {risk.gozlem_sayisi} islem gunu, TL bazli gunluk getiriler. "
        f"Yillicklastirma carpani {risk.yillik_periyot:.0f} (veriden turetildi).",
        "",
        "> **Max drawdown hipotetiktir.** Gecmiste yasadigin kayip degil, "
        "*bugunku agirliklarini bir yil boyunca gunluk sabit tutsaydin* ne "
        "yasardin sorusunun cevabi. Portfoy dun kurulmus olsa bile bir yillik "
        "rakam yazar.",
        "",
        "| Varlik | Yillik volatilite | Max drawdown | Agirlik | Risk katkisi | Beta |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    kisilacaklar = []
    for varlik_riski in risk.varlik_riskleri:
        kis = esikler.kisilmali(varlik_riski)
        if kis:
            kisilacaklar.append(varlik_riski)
        satirlar.append(
            f"| {varlik_adlari.get(varlik_riski.sembol, varlik_riski.sembol)} | "
            f"{_oran(varlik_riski.yillik_volatilite)} | "
            f"{_oran(varlik_riski.max_drawdown)} | "
            f"{_oran(varlik_riski.agirlik)} | "
            f"{_oran(varlik_riski.risk_katkisi)} | "
            f"{varlik_riski.beta:.2f}{' **>**' if kis else ''} |"
        )
    satirlar += [
        "",
        "**Beta = risk katkisi / agirlik.** 1'in ustu parasindan fazla risk "
        "tasiyor demek; 1'in alti verimli tasiyici.",
        "",
        f"Kisma karari IKI kosul birden ister: katki > {_oran(esikler.risk_katkisi_ust, 0)} "
        f"**ve** beta > {esikler.risk_beta_ust:.2f}. Tek basina katki yetmez - "
        "6 pozisyonda ortalama katki %16.7'dir, birilerinin tavani asmasi zorunludur.",
        "",
    ]

    if kisilacaklar:
        satirlar.append("> **Kisilmali:**")
        for varlik_riski in kisilacaklar:
            satirlar.append(
                f"> - `{varlik_riski.sembol}` katki "
                f"{_oran(varlik_riski.risk_katkisi)}, beta {varlik_riski.beta:.2f}"
            )
        satirlar.append("")
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


def _ucgenleme_bolumu(fiyatlar: FiyatVerisi) -> list[str]:
    """TR primi: BTCTurk TL fiyati ile CoinGecko x USD/TRY arasindaki fark.

    Ayri metrik olarak gosterilir cunku kar/zarar degildir - Turkiye
    piyasasinin dunya fiyatina gore tasidigi primdir. Pozitif deger TL
    tarafinin pahali oldugunu soyler.
    """
    ucgenleme = fiyatlar.ucgenleme
    if not ucgenleme.sonuclar:
        return []
    satirlar = [
        "## TR primi (ucgenleme)",
        "",
        "| Sembol | BTCTurk TL | Beklenen TL | TR primi | Durum |",
        "|---|---:|---:|---:|---|",
    ]
    for sembol in sorted(ucgenleme.sonuclar):
        sonuc = ucgenleme.sonuclar[sembol]
        tl = f"{sonuc.tl_fiyat:,.0f}" if sonuc.tl_fiyat is not None else "—"
        beklenen = f"{sonuc.beklenen_tl:,.0f}" if sonuc.beklenen_tl is not None else "—"
        prim = f"{sonuc.tr_primi * 100:+.2f}%" if sonuc.tr_primi is not None else "—"
        satirlar.append(f"| {sembol} | {tl} | {beklenen} | {prim} | {sonuc.durum} |")
    kur_kaynaklari = {s.kur_kaynagi for s in ucgenleme.sonuclar.values() if s.kur_kaynagi}
    satirlar += [
        "",
        f"USD/TRY kaynagi: {', '.join(sorted(kur_kaynaklari)) or 'yok'}.",
        "Degerleme BTCTurk TL cifti uzerinden - cift cevrim yok. **Risk "
        "metrikleri (volatilite, korelasyon, beta) hala Yahoo'nun gunluk "
        "serisinden hesaplanir**; BTCTurk ticker gecmis vermez.",
        "",
    ]
    return satirlar


def _uyari_bolumu(portfoy: Portfoy, fiyatlar: FiyatVerisi, risk: RiskRaporu,
                  bayatlik=None) -> list[str]:
    sorunlar = []
    for sonuc in fiyatlar.ucgenleme.durduranlar:
        sorunlar.append(
            f"**UCGENLEME DURDURDU - {sonuc.sembol}**: {sonuc.gerekce}. "
            "Uc kaynak da taze ama birbirini tutmuyor.")
    for sonuc in fiyatlar.ucgenleme.primliler:
        sorunlar.append(f"TR primi esigi asildi - {sonuc.sembol}: {sonuc.gerekce}")
    for sonuc in fiyatlar.ucgenleme.dogrulanmayanlar:
        sorunlar.append(
            f"Ucgenleme yapilamadi - {sonuc.sembol}: {sonuc.gerekce}. "
            "Degerleme yapildi ama dogrulanmadi.")
    sorunlar += fiyatlar.ucgenleme.uyarilar
    for sembol, gerekce in sorted(fiyatlar.kurumsal_olay_supheleri.items()):
        sorunlar.append(
            f"**Olasi kurumsal olay - {sembol}**: {gerekce}. Degerleme DURDURULDU. "
            "Bedelsiz/split ise `simulasyon/kurumsal-olaylar.yaml` dosyasina yaz; "
            "gercek hareketse hacim esigini gozden gecir. "
            "UYARI: risk metrikleri bu sembol icin hala ham seriden hesaplaniyor, "
            "volatilite ve korelasyon sisirilmis olabilir."
        )
    if fiyatlar.eksik_semboller:
        sorunlar.append(f"Fiyat verisi gelmeyen sembol: {', '.join(fiyatlar.eksik_semboller)}")
    bayatlar = fiyatlar.bayat_semboller(bayatlik)
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
    gerceklesmemis = portfoy.gerceklesmemis_kar_try

    # Ozdeslik: net = gerceklesmemis + gerceklesen - alis_komisyonu.
    # Kalan farki gizlemek yerine yazdiriyoruz; tutmuyorsa muhasebe bozuk demektir.
    fark = net - gerceklesmemis - durum.gerceklesen_kar_try

    satirlar = [
        "## Simulasyon performansi",
        "",
        "| Olcut | Deger |",
        "|---|---|",
        f"| Baslangic sermayesi | {_tl(baslangic)} |",
        f"| Guncel deger | {_tl(portfoy.toplam_deger_try)} |",
        f"| **Net sonuc** | **{_tl(net)} ({_yuzde(getiri)})** |",
        f"| Gerceklesen kar (satislardan) | {_tl(durum.gerceklesen_kar_try)} |",
        f"| Gerceklesmemis kar (aciktaki) | {_tl(gerceklesmemis)} |",
        f"| Alis komisyonu (maliyete girmez) | {_tl(-fark)} |",
        f"| Odenen komisyon (toplam) | {_tl(durum.toplam_komisyon_try)} "
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
    satirlar += _ozet_bolumu(portfoy, risk, fiyatlar, sim=bool(durum))
    satirlar += _pozisyon_bolumu(portfoy)
    satirlar += _dagilim_bolumu(sapmalar, portfoy.toplam_deger_try,
                                yapilandirma.esikler.rebalancing_sapma,
                                portfoy.fiyatlanamayan)
    satirlar += _risk_bolumu(risk, varlik_adlari, yapilandirma.esikler)
    satirlar += _korelasyon_bolumu(risk.korelasyon)
    if durum:
        satirlar += _islem_gecmisi_bolumu(durum)
    satirlar += _ucgenleme_bolumu(fiyatlar)
    satirlar += _uyari_bolumu(portfoy, fiyatlar, risk, yapilandirma.bayatlik)
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
