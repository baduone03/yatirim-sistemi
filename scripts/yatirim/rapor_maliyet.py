"""Raporun maliyet modeli bolumleri: eksik kalem uyarisi, getiri satirlari,
maliyet dagilimi.

`report.py` icinde kalsaydi dosya 650 satiri geciyordu. Bu bolumler tek bir
konuya bakiyor - maliyetin getiriye etkisi - o yuzden birlikte duruyorlar.
"""

from __future__ import annotations

import math

from bicim import oran, tl, yuzde
from duyarlilik import GERCEK, HEDEF, YEDEK, DuyarlilikRaporu
from maliyet import (
    SENARYOLAR,
    TEMEL,
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
        # Sabit referans varsaymak sonucu belirler: ayni varlik 3.000 TL'de
        # "ekonomik degil", 12.000 TL'de "olc" cikar. Buyukluk yazilmazsa
        # tablo hangi dunyayi anlattigini soylemiyor demektir.
        "Pozisyon sutunu: tutulan varlikta GERCEK deger, tutulmayanda hedef "
        "dagilimda alacagi deger. Sonuc bu buyukluge BAGLI - sabit komisyonun "
        "payi pozisyonla kuculur.",
        "",
        "| Varlik | Pozisyon | Iyimser | Temel | Kotumser | Sonuc |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for sembol, varlik in sorted(rapor.varliklar.items()):
        maliyetler = " | ".join(
            oran(varlik.maliyetler[ad], 2) if ad in varlik.maliyetler else "-"
            for ad in SENARYOLAR)
        satirlar.append(
            f"| {varlik_adlari.get(sembol, sembol)} | "
            f"{tl(varlik.pozisyon_try)} | {maliyetler} | {varlik.etiket} |")
    satirlar.append("")

    gerekenler = rapor.olculmesi_gerekenler
    if not gerekenler:
        satirlar += [
            "Olculmesi gereken parametre yok: karar olcutune giren tahminlerin "
            "hicbiri karari cevirmiyor. Genis aralikla bile karar ayni cikiyorsa "
            "o sayiyi olcmek islem kararini degistirmez.",
            "",
        ]
        return (satirlar + _kapsam_disi_satirlari(rapor)
                + kapsam_dokumu_bolumu(rapor))

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
    return (satirlar + _kapsam_disi_satirlari(rapor)
            + kapsam_dokumu_bolumu(rapor))


def _kapsam_disi_satirlari(rapor: DuyarlilikRaporu) -> list[str]:
    """Karar olcutune hic girmeyen tahminler.

    Yazilmazsa tablo bu kalemleri "sinandi ve gecti" gibi gosterir; oysa
    hesaba hic girmediler. Ayrimi kaldirmak, sinanmamis bir tahminle acilan
    bir sinyali sinanmis sanmak demek.
    """
    kapsam_disi = rapor.kapsam_disi_tahminler
    if not kapsam_disi:
        return []
    return [
        "### Duyarlilik testinin KAPSAMADIGI tahminler",
        "",
        "Bu kalemler karar olcutune (gidis-donus islem maliyeti) HIC GIRMIYOR: "
        "tasima maliyetidir, yani varligi TUTMANIN bedeli, ALIP SATMANIN degil. "
        "Uc senaryoda kosulsalar da karari degistiremezler - dolayisiyla "
        "\"karari cevirmiyor\" demek onlar icin **test edildi** anlamina gelmez.",
        "",
        "Net getiri raporunu ETKILERLER; islem kapisini etkilemezler.",
        "",
        "| Parametre | Etkilenen varlik | Semboller |",
        "|---|---:|---|",
        *[f"| `{parametre}` | {len(semboller)} | "
          + ", ".join(f"`{s}`" for s in semboller) + " |"
          for parametre, semboller in sorted(kapsam_disi.items())],
        "",
    ]



POZISYON_KAYNAGI = {
    GERCEK: "gercek",
    HEDEF: "hedef dagilim",
    YEDEK: "YAML yedegi",
}


def ekonomik_olmayanlar_bolumu(rapor: DuyarlilikRaporu) -> list[str]:
    """Pozisyon buyuklugu yuzunden islem yapilamayan varliklar.

    Neden AYRI bolum: parametre belirsizliginde yapilacak sey bir sayiyi
    OLCMEK, burada pozisyonu BUYUTMEK ya da varliktan CIKMAK. Ayni listede
    gosterilirse, cozumu para olan bir sorun olculecek bir soru gibi gorunur
    ve sonsuza kadar "sonra bakarim" kutusunda kalir.
    """
    ekonomik_olmayanlar = rapor.ekonomik_olmayanlar
    if not ekonomik_olmayanlar:
        return []

    satirlar = [
        "## Ekonomik olmayan pozisyonlar",
        "",
        "Bu varliklarda gidis-donus maliyeti, sistemin islem yapmaya deger "
        f"gordugu en kucuk sapmadan ({oran(rapor.esik)}) BUYUK. Yani sinyal ne "
        "derse desin islem, duzelttigi sapmadan fazlasini goturur.",
        "",
        "**Sorun parametre belirsizligi DEGIL** - uc senaryoda da ayni sonuc "
        "cikiyor. Olculecek bir sey yok; ya pozisyon buyuyecek ya da varliktan "
        "cikilacak.",
        "",
        "| Varlik | Pozisyon | Kaynak | Maliyet (temel) | Minimum ekonomik | Kotumserde |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for sembol, varlik in ekonomik_olmayanlar.items():
        maliyet = varlik.maliyetler.get(TEMEL)
        satirlar.append(
            f"| `{sembol}` | {tl(varlik.pozisyon_try)} | "
            f"{POZISYON_KAYNAGI.get(varlik.pozisyon_kaynagi, varlik.pozisyon_kaynagi)} | "
            f"{oran(maliyet, 2) if maliyet is not None else '-'} | "
            f"{_minimum(varlik.minimum_pozisyon)} | "
            f"{_minimum(varlik.minimum_pozisyon_kotumser)} |")

    satirlar += [
        "",
        "**Minimum ekonomik pozisyon**: gidis-donus maliyetini esigin altina "
        "indiren en kucuk pozisyon. Yalnizca SABIT komisyonun payi pozisyonla "
        "kuculur; spread ve kambiyo vergisi oransaldir ve hicbir buyuklukte "
        "kuculmez. `hicbir buyukluk` yazan satirda maliyet TABANI zaten esigin "
        "ustunde - o varlikta islem matematiksel olarak kaybettirir.",
        "",
    ]
    buyutulebilir = [v for v in ekonomik_olmayanlar.values() if v.buyutmek_ise_yarar]
    if buyutulebilir:
        satirlar += ["> **Karar**: her varlik icin ya pozisyonu minimumun "
                     "ustune cikar ya da varliktan tamamen cik. Arada kalmak "
                     "en pahali secenek - pozisyon duruyor ama rebalance "
                     "edilemiyor, yani hedef dagilim fiilen uygulanamiyor.",
                     ""]
    return satirlar


def _minimum(deger: float | None) -> str:
    if deger is None:
        return "-"
    if not math.isfinite(deger):
        return "hicbir buyukluk"
    if deger <= 0:
        return "sinir yok"
    return tl(deger)



def kapsam_dokumu_bolumu(rapor: DuyarlilikRaporu) -> list[str]:
    """Varlik basina: hangi tahmin sinandi, hangisi sinanmadi, blokaji ne kaldirdi.

    Bu tablo olmadan "karar dayanikli" satiri, hangi varsayimlarin sinandigini
    gizler. Bir varligin sinyali sinanmamis bir tahminle acilmissa bunu
    goren tek yer burasidir.
    """
    if not rapor.varliklar:
        return []
    satirlar = [
        "### Tahmin kapsam dokumu",
        "",
        "`Blokaji kaldiran`: bu alan `null` olsaydi varlik sinyal uretemezdi; "
        "tahmin oldugu icin uretiyor. `Kapsam ici` olanlar duyarlilik "
        "testinden gecti, `kapsam disi` olanlar HIC SINANMADI.",
        "",
        "| Varlik | Kapsam ici (sinandi) | Kapsam disi (sinanmadi) | Durum |",
        "|---|---|---|---|",
    ]
    for sembol, varlik in sorted(rapor.varliklar.items()):
        if not varlik.blokaji_kaldiran:
            continue
        isaret = "**DOGRULANMAMIS ACILIM**" if varlik.dogrulanmamis_acilim else "ok"
        satirlar.append(
            f"| `{sembol}` | "
            + (", ".join(f"`{p}`" for p in varlik.kapsam_ici_parametreler) or "-")
            + " | "
            + (", ".join(f"`{p}`" for p in varlik.kapsam_disi_parametreler) or "-")
            + f" | {isaret} |")
    satirlar.append("")

    if rapor.dogrulanmamis_acilimlar:
        satirlar += [
            "> **DOGRULANMAMIS ACILIM**: bu varliklarin sinyalini, hicbir "
            "duyarlilik boyutundan gecmemis bir tahmin aciyor. `null` "
            "disiplininin amaci tam da bunu onlemekti - ya parametreyi olc "
            "ya da onu kapsayan boyutu calistir "
            "(`maliyet.tutma` eksikse basabas boyutu kosmaz).",
            "",
        ]
    return satirlar


def basabas_bolumu(rapor: DuyarlilikRaporu) -> list[str]:
    """Ikinci duyarlilik boyutu: basabas tutma suresi.

    Birinci boyut "islem maliyeti sapmayi yutuyor mu" diye sorar; bu boyut
    "bu varlik planladigim surede o maliyeti CIKARIYOR mu" diye sorar.
    Ikisi farkli sorular: dusuk islem maliyetli ama getirisi risksiz orani
    zor asan bir varlik birinciyi gecer, ikinciyi gecemez.
    """
    olculenler = {s: v for s, v in sorted(rapor.varliklar.items())
                  if v.tutma_olculdu}
    if not olculenler:
        return []
    satirlar = [
        "## Basabas tutma suresi (tasima duyarliligi)",
        "",
        "T = gidis-donus / (beklenen getiri - yillik tasima - TL risksiz). "
        "Payda ASIRI getiridir: getirinin risksiz orani asan kismi. Islem "
        "maliyeti yalnizca o fazladan geri odenir.",
        "",
        "> `beklenen getiri` bir TAHMIN DEGIL, `varliklar.yaml -> maliyet.tutma` "
        "icindeki BEYANDIR. Sistem fiyat tahmini uretmez.",
        "",
        "| Varlik | Planlanan | T iyimser | T temel | T kotumser | Sonuc |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for sembol, varlik in olculenler.items():
        sureler = " | ".join(_sure(varlik.basabas.get(ad)) for ad in SENARYOLAR)
        sonuc = ("gecti" if varlik.tutma_dayanikli
                 else "tasima maliyeti belirsizligi: "
                      + ", ".join(varlik.tasima_belirsiz_parametreler))
        satirlar.append(
            f"| `{sembol}` | {varlik.planlanan_yil:.1f} yil | {sureler} | {sonuc} |")
    satirlar.append("")

    belirsizler = rapor.tasima_belirsizleri
    if belirsizler:
        satirlar += [
            "> Bir senaryoda bile planlanan sureyi asan varlikta sinyal "
            "BASTIRILIR. \"Muhtemelen cikarir\" diye almak, maliyeti kesin "
            "olarak odemek demektir. Cozum: parametreyi olc ya da "
            "`maliyet.tutma` icindeki planlanan sureyi gercekci hale getir.",
            "",
        ]
    return satirlar


def _sure(yil: float | None) -> str:
    if yil is None:
        return "-"
    if not math.isfinite(yil):
        return "hicbir zaman"
    if yil < 1:
        return f"{yil * 365:.0f} gun"
    return f"{yil:.2f} yil"


def maliyet_kalemleri(portfoy: Portfoy, durum, maliyet: MaliyetModeli,
                      donem_gun: int, taban_try: float) -> list[MaliyetKalemi]:
    """Brut getiriden dusulecek kalemler. Olculemeyen kalem None KALIR.

    Kismi olcum yapilmaz: bir sembolun gider orani bilinmiyorsa "gider orani"
    kalemi tumuyle olculemedi sayilir. Bilinenleri toplayip kalemi olculmus
    gibi gostermek, maliyeti oldugundan dusuk raporlar.
    """
    if taban_try <= 0:
        return []
    # Tahminli kalemler TEMEL senaryoya indirgenir. Ham `Tahmin` nesnesiyle
    # carpma TypeError verir; burada indirgenmezse rapor hic uretilmez.
    # Kullanilan tahminler kalem aciklamasinda isaretlenir - "olculmus" gibi
    # gorunen bir tahmin, modelin kapatmaya calistigi hatanin ta kendisi.
    tahminli = {s for s, v in maliyet.varliklar.items() if v.tahminler}
    maliyet = maliyet.senaryoyla(TEMEL)
    tahmin_notu = " [TAHMIN: temel senaryo]" if tahminli else ""
    return [
        MaliyetKalemi("Komisyon",
                      durum.toplam_komisyon_try / taban_try if durum else None,
                      "defterden, fiilen odenen"),
        MaliyetKalemi("Kur spread", _kur_spreadi(durum, maliyet, taban_try),
                      "TL<->USD cevrimi, islem basina" + tahmin_notu),
        *_tasima_kalemleri(portfoy, maliyet, donem_gun, taban_try, tahmin_notu),
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
                      taban_try: float, tahmin_notu: str = "") -> list[MaliyetKalemi]:
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
                      "fon gideri, donem orantili" + tahmin_notu),
        MaliyetKalemi("Temettu stopaji", stopaj / taban_try if stopaj_olculdu else None,
                      "kaynakta kesilir, ekstrede gorunmez" + tahmin_notu),
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
