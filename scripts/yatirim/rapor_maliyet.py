"""Raporun maliyet modeli bolumleri: eksik kalem uyarisi, getiri satirlari,
maliyet dagilimi.

`report.py` icinde kalsaydi dosya 650 satiri geciyordu. Bu bolumler tek bir
konuya bakiyor - maliyetin getiriye etkisi - o yuzden birlikte duruyorlar.
"""

from __future__ import annotations

from bicim import oran, yuzde
from duyarlilik import DuyarlilikRaporu
from maliyet import (
    SENARYOLAR,
    MaliyetDagilimi,
    MaliyetKalemi,
    MaliyetModeli,
    donem_orani,
    reel_getiri,
)
from portfolio import Portfoy


def kaynak_etiketi(kaynak: str) -> str:
    return kaynak if kaynak != "yapilandirma" else "varliklar.yaml (yedek deger)"


def getiri_satirlari(model: MaliyetModeli | None, donem_getirisi: float | None,
                     donem_gun: int) -> list[str]:
    """Brut getirinin yaninda asiri ve reel getiri.

    Sifira gore pozitif ama risksize gore negatif bir portfoy BASARISIZ
    portfoydur; yalnizca brut getiriyi gostermek bunu gizler.
    """
    if model is None or donem_getirisi is None or donem_gun <= 0:
        return []
    if model.tl_risksiz_yillik is None:
        return []
    risksiz = donem_orani(model.tl_risksiz_yillik, donem_gun)
    satirlar = [
        f"| Brut getiri ({donem_gun} gun) | {yuzde(donem_getirisi, 2)} |",
        f"| TL risksiz getiri (ayni donem) | {yuzde(risksiz, 2)} "
        f"({kaynak_etiketi(model.risksiz_kaynagi)}) |",
        f"| **Asiri getiri** | **{yuzde(donem_getirisi - risksiz, 2)}** |",
    ]
    # Enflasyon yoksa nominal getiriyi reel gibi gostermek yasak: %48 mevduat
    # faizi olan bir ulkede enflasyonsuz "reel getiri" cumlesi anlamsizdir.
    if model.enflasyon_yillik is None:
        satirlar.append("| Reel getiri | OLCULEMEDI - enflasyon verisi yok |")
    else:
        enflasyon = donem_orani(model.enflasyon_yillik, donem_gun)
        satirlar.append(
            f"| Reel getiri (enflasyon {oran(enflasyon, 2)}) | "
            f"{yuzde(reel_getiri(donem_getirisi, enflasyon), 2)} |")
    return satirlar


def eksik_maliyet_bolumu(maliyet: MaliyetModeli) -> list[str]:
    """Raporun EN USTUNE basilan blok.

    Bilinmeyen bir maliyeti sifir saymak yerine gorunur kilmak bu modelin tum
    amacidir. Uyari asagida bir yerde kalirsa kimse gormez ve sistem yeniden
    eksik modelle islem onerir.
    """
    engellenenler = maliyet.engellenenler
    if not engellenenler:
        return []
    satirlar = [
        "> ## 🛑 EKSIK MALIYET KALEMI",
        ">",
        "> Asagidaki varliklarin maliyet modeli TAM DEGIL. Rapor uretildi ama "
        "**bu varliklar icin islem sinyali URETILMEDI** - bilinmeyen maliyeti "
        "sifir saymak, karsiz bir islemi karli gostermek demektir.",
        ">",
        "> | Varlik | Eksik kalem |",
        "> |---|---|",
    ]
    for sembol, kalemler in engellenenler.items():
        satirlar.append(f"> | `{sembol}` | {', '.join(f'`{k}`' for k in kalemler)} |")
    satirlar += [
        ">",
        "> Degerleri `varliklar.yaml` -> `maliyet` altina yaz. `null` = "
        "bilinmiyor, `0.0` = olculdu ve sifir cikti; ikisi ayni sey degildir.",
        "",
    ]
    return satirlar



def duyarlilik_bolumu(rapor: DuyarlilikRaporu,
                      varlik_adlari: dict[str, str]) -> list[str]:
    """Uc senaryolu maliyet duyarliligi + olculmesi gereken parametre sirasi.

    Amac tek bir soruyu cevaplamak: SIRADA HANGI SAYIYI OLCMELI. Bir parametre
    kac varligin kararini ceviriyorsa o kadar oncelikli.
    """
    if not rapor.varliklar:
        return []
    satirlar = [
        "## Maliyet duyarliligi",
        "",
        "Karar olcutu: gidis-donus maliyeti < islem yapmaya deger en kucuk "
        f"sapma ({oran(rapor.esik)}). Maliyet bu sinirin ustundeyse islem, "
        "duzelttigi sapmadan fazlasini goturur.",
        "",
        "| Varlik | Iyimser | Temel | Kotumser | Sonuc |",
        "|---|---:|---:|---:|---|",
    ]
    for sembol, varlik in sorted(rapor.varliklar.items()):
        maliyetler = " | ".join(
            oran(varlik.maliyetler[ad], 2) if ad in varlik.maliyetler else "-"
            for ad in SENARYOLAR)
        satirlar.append(
            f"| {varlik_adlari.get(sembol, sembol)} | {maliyetler} | "
            f"{varlik.etiket} |")
    satirlar.append("")

    gerekenler = rapor.olculmesi_gerekenler
    if not gerekenler:
        satirlar += [
            "Olculmesi gereken parametre yok: tahminli kalemlerin hicbiri karari "
            "cevirmiyor. Genis aralikla bile karar ayni cikiyorsa o sayiyi olcmek "
            "islem kararini degistirmez.",
            "",
        ]
        return satirlar

    satirlar += [
        "### OLCULMESI GEREKEN PARAMETRELER",
        "",
        "Etki sirasina gore. Ustteki sayiyi olcmek en cok varligin sinyalini acar.",
        "",
        "| # | Parametre | Etkilenen varlik | Semboller |",
        "|---:|---|---:|---|",
    ]
    for sira, (parametre, semboller) in enumerate(gerekenler, start=1):
        satirlar.append(
            f"| {sira} | `{parametre}` | {len(semboller)} | "
            + ", ".join(f"`{s}`" for s in semboller) + " |")
    satirlar += [
        "",
        "> Bu parametreler olculene kadar ilgili varliklarda islem sinyali "
        "URETILMEZ. Tahmin araliklari `varliklar.yaml` icinde "
        "`kaynak: olculmedi-genis-aralik` ile isaretli; olculen deger "
        "girildiginde aralik tek sayiya iner ve varlik kendiliginden acilir.",
        "",
    ]
    return satirlar


def maliyet_kalemleri(portfoy: Portfoy, durum, maliyet: MaliyetModeli,
                      donem_gun: int, taban_try: float) -> list[MaliyetKalemi]:
    """Brut getiriden dusulecek kalemler. Olculemeyen kalem None KALIR.

    Kismi olcum yapilmaz: bir sembolun gider orani bilinmiyorsa "gider orani"
    kalemi tumuyle olculemedi sayilir. Bilinenleri toplayip kalemi olculmus
    gibi gostermek, maliyeti oldugundan dusuk raporlar.
    """
    if taban_try <= 0:
        return []
    return [
        MaliyetKalemi("Komisyon",
                      durum.toplam_komisyon_try / taban_try if durum else None,
                      "defterden, fiilen odenen"),
        MaliyetKalemi("Kur spread", _kur_spreadi(durum, maliyet, taban_try),
                      "TL<->USD cevrimi, islem basina"),
        *_tasima_kalemleri(portfoy, maliyet, donem_gun, taban_try),
        MaliyetKalemi("Vergi", None,
                      "gerceklesen kazanc uzerinden; oran modele girilmedi"),
    ]


def _kur_spreadi(durum, maliyet: MaliyetModeli, taban_try: float) -> float | None:
    """Kur spread'i bir ISLEM maliyetidir: TL<->USD cevriminde odenir."""
    toplam = 0.0
    for islem in (durum.islemler if durum else []):
        varlik = maliyet.varliklar.get(islem.sembol)
        profil = varlik.profil if varlik else None
        if profil is None or profil.kur_cevrimi is None:
            return None
        if not profil.kur_cevrimi:
            continue                          # cevrim yok - yapisal sifir
        if profil.kur_spread_tek_yon is None:
            return None
        toplam += islem.tutar_try * profil.kur_spread_tek_yon
    return toplam / taban_try


def _tasima_kalemleri(portfoy: Portfoy, maliyet: MaliyetModeli, donem_gun: int,
                      taban_try: float) -> list[MaliyetKalemi]:
    """Tasima kalemleri aciktaki pozisyonlarda, donem boyunca isler."""
    gider = 0.0
    stopaj = 0.0
    gider_olculdu = True
    stopaj_olculdu = True
    for pozisyon in portfoy.pozisyonlar:
        varlik = maliyet.varliklar.get(pozisyon.sembol)
        tasima = varlik.tasima if varlik else None
        if tasima is None or tasima.gider_orani_yillik is None:
            gider_olculdu = False
        else:
            gider += pozisyon.deger_try * donem_orani(
                tasima.gider_orani_yillik, donem_gun)
        if tasima is None or tasima.temettu_verimi is None:
            stopaj_olculdu = False
        elif tasima.temettu_verimi > 0 and tasima.temettu_stopaji is None:
            stopaj_olculdu = False
        else:
            stopaj += pozisyon.deger_try * donem_orani(
                tasima.temettu_verimi * (tasima.temettu_stopaji or 0.0), donem_gun)
    return [
        MaliyetKalemi("Gider orani", gider / taban_try if gider_olculdu else None,
                      "fon gideri, donem orantili"),
        MaliyetKalemi("Temettu stopaji", stopaj / taban_try if stopaj_olculdu else None,
                      "kaynakta kesilir, ekstrede gorunmez"),
    ]


def _kalem_orani(kalem: MaliyetKalemi) -> str:
    """Maliyet kaleminin gosterimi.

    Sifira yuvarlanan ama sifir OLMAYAN kalem "-0.00%" yazilirsa okuyan
    "olculdu mu, sifir mi?" diye tereddut eder - bu modelin tum meselesi o
    ayrim. "<0.01%" tereddut birakmaz.
    """
    if not kalem.olculdu:
        return "OLCULEMEDI"
    if kalem.oran == 0:
        return "0.00%"
    if abs(kalem.oran) < 0.00005:
        return "<0.01%"
    return f"{-kalem.oran * 100:+.2f}%"


def maliyet_dagilimi_bolumu(dagilim: MaliyetDagilimi,
                            maliyet: MaliyetModeli) -> list[str]:
    """Brut getiriden asiri getiriye giden yol. Olculmeyen maliyet optimize
    edilemez; bu tablo hangi kalemin canini yaktigini gorunur kilar."""
    satirlar = [
        "## Maliyet dagilimi",
        "",
        f"Donem: {dagilim.donem_gun} gun. Taban: baslangic sermayesi.",
        "",
        "| Kalem | Oran | Not |",
        "|---|---:|---|",
        f"| **Brut getiri** | **{yuzde(dagilim.brut_getiri, 2)}** | maliyet oncesi |",
    ]
    for kalem in dagilim.kalemler:
        satirlar.append(f"| {kalem.ad} | {_kalem_orani(kalem)} | {kalem.aciklama} |")
    satirlar += [
        f"| **Net getiri** | **{yuzde(dagilim.net_getiri, 2)}** | "
        "olculemeyen kalemler haric - **UST SINIR** |",
        f"| TL risksiz getiri | {-dagilim.risksiz * 100:+.2f}% | "
        f"{kaynak_etiketi(maliyet.risksiz_kaynagi)} |",
        f"| **Asiri getiri** | **{yuzde(dagilim.asiri_getiri, 2)}** | "
        "risksize gore fazla/eksik |",
        "",
    ]
    if dagilim.eksik_kalemler:
        satirlar += [
            f"> ⚠️ Olculemeyen kalem: {', '.join(dagilim.eksik_kalemler)}. "
            "Bunlar yalnizca net getiriyi **asagi** ceker; yukaridaki net ve "
            "asiri getiri bu yuzden bir **ust sinirdir**, gercek deger daha "
            "dusuktur.",
            "",
        ]
    return satirlar
