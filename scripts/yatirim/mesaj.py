"""Telegram mesaj sablonlari.

`notify.py` tasima katmani (HTTPS POST, kimlik, hiz siniri); bu dosya metin
uretir. Ayri durmalarinin sebebi: sablon degistirmek icin tasima kodunu
okumak zorunda kalmamak ve sablonlari agsiz test edebilmek.

HTML parse modu kullanilir - kacilacak yalnizca `& < >` var. MarkdownV2'ye
gecilseydi 18 karakter kacmak gerekirdi ve her tablo satiri risk olurdu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from haber_analiz import YUKSEK
from portfolio import Portfoy


def kacis(metin: str) -> str:
    """Telegram HTML parse modu icin: yalnizca bu uc karakter kacirilir.

    Sira onemli: `&` ilk sirada olmali, yoksa `&lt;` icindeki `&` yeniden
    kacirilir ve okuyucu `&amp;lt;` gorur.
    """
    return metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tl(deger: float) -> str:
    return f"{deger:,.0f} TL".replace(",", ".")


def _yuzde(oran: float, isaret: bool = True) -> str:
    """0.0114 -> '+%1,1'. Turkce yazim: yuzde isareti onde, ondalik virgul."""
    metin = f"%{abs(oran) * 100:.1f}".replace(".", ",")
    if not isaret:
        return metin
    return ("+" if oran >= 0 else "-") + metin


class Uyari(str):
    """Uyari metni + Telegram'da gosterilecek SADE karsiligi.

    `str` alt sinifi: rapor ve diger tuketiciler uzun metni oldugu gibi
    kullanmaya devam eder. `sade` doluysa uyari telefonda acik cumleyle
    gosterilir; bossa "teknik not" sayilir ve yalnizca SAYISI mesaja girer,
    metni ekli raporda kalir. Ayrim kaynakta (uyarilari_topla) yapilir -
    mesaj metnine bakip kategori tahmin etmek, yeni bir uyari eklendiginde
    sessizce yanlis siniflardi.
    """

    sade: str

    def __new__(cls, metin: str, sade: str = ""):
        nesne = super().__new__(cls, metin)
        nesne.sade = sade
        return nesne


def _islem_satirlari(durum, tarih: str) -> list[str]:
    """O gun yapilan alim/satimlari mesaja ekler.

    Islem yoksa bos doner - "bugun islem yok" demek gurultu, esik
    asilmadigini zaten ozet satiri soyluyor.
    """
    bugunku = [i for i in durum.islemler if i.tarih == tarih]
    if not bugunku:
        return []

    satirlar = ["", "<b>Bugunku islemler</b>"]
    for islem in bugunku:
        simge = "🟩 ALDIM" if islem.yon == "AL" else "🟥 SATTIM"
        satirlar.append(
            f"{simge}  <b>{kacis(islem.sembol)}</b>  {islem.adet:g} adet"
        )
        satirlar.append(
            f"     {_tl(islem.fiyat_try)} x {islem.adet:g} = {_tl(islem.tutar_try)}"
        )
        if islem.gerekce:
            satirlar.append(f"     <i>{kacis(islem.gerekce)}</i>")
    return satirlar


def ucgenleme_durdurma_mesaji(durduranlar, baslik: str) -> str:
    """Rapor URETILMEDIGINDE gonderilen mesaj.

    Rapor yoksa sessiz kalmak en kotu secenek: kimse bir seyin durdugunu
    bilmez ve bayat raporu guncel sanir.
    """
    satirlar = [f"<b>🛑 {kacis(baslik)} - RAPOR URETILMEDI</b>", ""]
    for sonuc in sorted(durduranlar, key=lambda u: u.sembol):
        satirlar.append(f"• {kacis(sonuc.sembol)}: {kacis(sonuc.gerekce)}")
        if sonuc.tl_fiyat is not None and sonuc.beklenen_tl is not None:
            satirlar.append(
                f"  BTCTurk {sonuc.tl_fiyat:,.0f} TL / beklenen "
                f"{sonuc.beklenen_tl:,.0f} TL (kur: {kacis(sonuc.kur_kaynagi)})")
    satirlar += [
        "",
        "Uc kaynak da taze ama birbirini tutmuyor. Once kaynaklari kontrol et; "
        "gercek bir kopukluksa esigi degil pozisyonu gozden gecir.",
    ]
    return "\n".join(satirlar)


def hurdle_eksik_mesaji(baslik: str, seri: str, tarih: str = "",
                        esik_gun: int = 0) -> str:
    """Hurdle rate yok VEYA bayat - rapor uretilmez.

    Bayatlik eksiklikten daha tehlikeli: eksiklik gorunur, bayatlik gorunmez.
    Bu sayi gereken getiriyi, asiri getiriyi, nakit getirisini ve sinyal
    kapisini birden belirliyor; eski bir degerle uretilen rapor "calisti"
    diye guvenilir olmaz.
    """
    bayat = bool(tarih)
    satirlar = [
        f"<b>🛑 {kacis(baslik)} - RAPOR URETILMEDI</b>",
        "",
        (f"TL risksiz getiri (hurdle rate) BAYAT: {kacis(tarih)} tarihli, "
         f"esik {esik_gun} gun."
         if bayat else "TL risksiz getiri (hurdle rate) yok."),
        f"Canli seri: {kacis(seri) or '(tanimsiz)'}",
        "Yedek: varliklar.yaml -> maliyet.firsat.tl_risksiz_yillik "
        "(+ tl_risksiz_tarih)",
        "",
        "Bu deger gereken getiriyi, asiri getiriyi ve nakit getirisini birden "
        "belirliyor; " + ("bayat" if bayat else "eksik")
        + " haliyle uretilen rapor sessizce yanlis olur.",
    ]
    return "\n".join(satirlar)


@dataclass(frozen=True)
class Tetikleyici:
    """Hangi esik tetikledi. Sinyali dogrulanabilir kilan alan.

    "SAT" demek yetmez: hangi olcut, hangi degerde, hangi esige gore? Bu ucu
    yazmayan bir bildirim, okuyanin ya kor guvenmesini ya hic guvenmemesini
    ister. Ikisi de yanlis.
    """

    olcut: str
    deger: float
    esik: float
    bicim: str = "oran"

    def satir(self) -> str:
        return (f"{kacis(self.olcut)} {_deger(self.deger, self.bicim)} "
                f"(esik {_deger(self.esik, self.bicim)})")


@dataclass(frozen=True)
class Etki:
    """Oncesi -> sonrasi. Islemin ne degistirdigini gosterir."""

    olcut: str
    once: float
    sonra: float
    bicim: str = "oran"

    def satir(self) -> str:
        return (f"{kacis(self.olcut)}: {_deger(self.once, self.bicim)} → "
                f"{_deger(self.sonra, self.bicim)}")


@dataclass(frozen=True)
class IslemOnerisi:
    sembol: str
    yon: str
    adet: float
    fiyat_try: float
    veri_zamani: str
    veri_kaynagi: str

    @property
    def tutar_try(self) -> float:
        return self.adet * self.fiyat_try


def _deger(sayi: float, bicim: str) -> str:
    if bicim == "tl":
        return _tl(sayi)
    if bicim == "sayi":
        return f"{sayi:.2f}".replace(".", ",")
    if bicim == "puan":
        return f"{abs(sayi) * 100:.1f} puan".replace(".", ",")
    return _yuzde(sayi, isaret=False)


def islem_karari_mesaji(islem: IslemOnerisi, tetikleyen: list[Tetikleyici],
                        etki: list[Etki], gidis_donus: float | None,
                        komisyon_try: float | None,
                        uyarilar: list[str] | None = None,
                        adlar: dict[str, str] | None = None,
                        sapma_esigi: float | None = None) -> str:
    """Islem karari bildirimi - SADE bicim (2026-11-07).

    Dort soru, dort satir: ne yapilacak, neden, sonra ne olacak, maliyeti ne.
    Ayrinti ekli raporda.

    VERI ZAMANI yazar, mesaj zamani DEGIL: mesaj 19:04'te gitse de fiyat Cuma
    kapanisina aitse karar Cuma verisiyle verilmistir. Mesaj zamanini
    gostermek bayat veriyi guncel gibi sunar.
    """
    eylem = {"AL": "🟩 AL", "SAT": "🟥 SAT"}.get(islem.yon, f"🟨 {kacis(islem.yon)}")
    ad = _ad(islem.sembol, adlar)
    satirlar = [
        f"<b>{eylem}: {ad}</b>",
        f"≈ {_tl(islem.tutar_try)} ({islem.adet:g} adet × {_tl(islem.fiyat_try)})",
        "",
    ]

    if tetikleyen:
        ilk = tetikleyen[0]
        satirlar.append(f"<b>Neden:</b> {kacis(ilk.olcut)} {_deger(ilk.deger, ilk.bicim)}"
                        f" (sınır {_deger(ilk.esik, ilk.bicim)})")
    for e in etki[:1]:
        satirlar.append(f"<b>Sonra:</b> {kacis(e.olcut)} {_deger(e.once, e.bicim)}"
                        f" → {_deger(e.sonra, e.bicim)}")

    if komisyon_try is None or gidis_donus is None:
        satirlar.append("<b>Maliyet:</b> tam ölçülemedi ⚠️ (eksik maliyet "
                        "kalemi, ayrıntı raporda)")
    else:
        maliyet = f"<b>Maliyet:</b> ≈ {_tl(komisyon_try)}"
        if sapma_esigi is not None and gidis_donus >= sapma_esigi:
            maliyet += " ⚠️ düzelttiğinden pahalı"
        satirlar.append(maliyet)

    satirlar += ["", f"<i>{_gun_adi(islem.veri_zamani)} fiyatı · "
                 f"{kacis(islem.veri_kaynagi)} · kağıt portföy</i>"]
    for uyari in uyarilar or []:
        satirlar.append(f"⚠️ {kacis(uyari)}")
    return "\n".join(satirlar)


@dataclass(frozen=True)
class GunSonuOzeti:
    """Gun sonu mesajinin tum girdisi.

    Tek nesne: 11 alani konumsal argumana cevirmek cagri yerini okunmaz yapar
    ve bir alani atlamak sessizce yanlis mesaj uretir.
    """

    portfoy: Portfoy
    risk: object
    veri_zamani: str
    degisim_24s: float | None = None
    asiri_getiri: float | None = None
    risksiz: float | None = None
    donem_gun: int = 0
    komisyon_try: float | None = None
    kur_maruziyeti: float = 0.0
    ayrimlar: list = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)
    baslik: str = "🌙 Gün sonu"
    # Anlati icin gereken uc alan. Hepsi opsiyonel: eksikse ilgili bolum
    # mesajdan tumuyle DUSER, uydurma cumle uretilmez.
    karar: object | None = None          # sinyal.Karar - islem bolumu icin
    adlar: dict = field(default_factory=dict)   # sembol -> okunur ad
    baslangic_try: float = 0.0           # sermaye tabani; 0 ise oran yazilmaz
    # Model uretimi uc cumlelik giris. Bos ise mesaj eskisi gibi baslar -
    # ozet bir kolayliktir, mesajin gecerliligi ona bagli DEGIL.
    onsoz: str = ""
    # kiyas.KiyasSatiri listesi, degere gore sirali. Bossa satir DUSER.
    kiyaslar: list = field(default_factory=list)


AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def _gun_adi(iso: str) -> str:
    """'2026-08-19' -> '19 Agustos'. Cozulemezse ham metni birakir.

    Ham ISO tarih makine icin dogru, okuyan icin degil. Cozulemeyen bir
    tarihi uydurmaktansa oldugu gibi gostermek dogru - veri zamani bu
    sistemde asla tahmin edilmez.
    """
    try:
        yil, ay, gun = (int(p) for p in iso.split("-")[:3])
        return f"{gun} {AYLAR[ay - 1]}"
    except (ValueError, IndexError):
        return iso


def _ad(sembol: str, adlar: dict[str, str] | None) -> str:
    """Sembolun okunur adi. Yoksa sembolun kendisi.

    'GC=F' okuyana hicbir sey soylemez, 'Altin (gram)' soyler. Ad
    yapilandirmadan gelir; eksikse sembol gosterilir, uydurulmaz.
    """
    return kacis((adlar or {}).get(sembol, sembol))


def _kur_satiri(ozet: GunSonuOzeti) -> str:
    """Hareket KURDAN geldiyse tek satir; gelmediyse bos.

    +%3 TL getirisi dolar %3 degerlendigi icin cikmissa bu yatirim basarisi
    DEGIL - ayni sonucu doviz tutarak da alirdin. Kur belirleyici degilse
    satir DUSER.
    """
    if ozet.degisim_24s is None:
        return ""
    usd = [a for a in ozet.ayrimlar if a.para_birimi == "USD"]
    # KUR PAYI: her varlikta TL getirisinin ne kadari kurdan geldi. Ortalama
    # mutlak getiri kullanilsaydi tek bir buyuk yerel hareket ortalamayi ele
    # gecirip geri kalan varliklarda kurun hakim oldugunu gizlerdi.
    paylar = []
    for a in usd:
        toplam_hareket = abs(a.kur_getirisi) + abs(a.yerel_getiri)
        if toplam_hareket > 0.0005:          # olcek altini oranlamak gurultu
            paylar.append(abs(a.kur_getirisi) / toplam_hareket)
    if not paylar or sum(paylar) / len(paylar) < 0.6:
        return ""
    ort_kur = sum(a.kur_getirisi for a in usd) / len(usd)
    yon = "yükseldi" if ort_kur > 0 else "düştü"
    return (f"💱 Bugünkü hareketin çoğu KURDAN: dolar {_yuzde(ort_kur, False)} "
            f"{yon}")


def _durum_satirlari(ozet: GunSonuOzeti) -> list[str]:
    toplam = ozet.portfoy.toplam_deger_try
    satirlar = [f"💰 Portföy: <b>{_tl(toplam)}</b>"]
    if ozet.baslangic_try:
        fark = toplam - ozet.baslangic_try
        satirlar.append(
            f"{'📈' if fark >= 0 else '📉'} Başlangıçtan beri: "
            f"{'+' if fark >= 0 else '-'}{_tl(abs(fark))} "
            f"({_yuzde(fark / ozet.baslangic_try)})")
    if ozet.degisim_24s is None:
        satirlar.append("📊 Son 24 saat: ölçülemedi (fiyat verisi eksik)")
    else:
        satirlar.append(f"📊 Son 24 saat: {_yuzde(ozet.degisim_24s)}")
    return satirlar


def _kazanc_satiri(ozet: GunSonuOzeti) -> str:
    """Riske deger miydi: ayni para mevduatta olsaydi ne olurdu.

    Ciplak "+%1 kazandin" eksik - mevduat da kazandiriyordu. TL karsiligi
    yuzde farkindan daha kolay okunur.
    """
    if ozet.asiri_getiri is None or ozet.risksiz is None:
        return "❔ Mevduat karşılaştırması yapılamadı (faiz verisi yok)"
    if not ozet.baslangic_try:
        getiri = ozet.asiri_getiri + ozet.risksiz
        return (f"🏦 Portföy {_yuzde(getiri)}, mevduat "
                f"{_yuzde(ozet.risksiz)} ({ozet.donem_gun} günde)")
    mevduat = ozet.baslangic_try * (1 + ozet.risksiz)
    fark = ozet.portfoy.toplam_deger_try - mevduat
    durum = "önde ✅" if fark >= 0 else "geride 🔻"
    return (f"🏦 Mevduatta olsaydı: {_tl(mevduat)} → portföy "
            f"{_tl(abs(fark))} {durum}")


def _islem_satiri(ozet: GunSonuOzeti) -> str:
    """Islem durumu. Frenlenmis sistem sessiz sistemle ayni satiri uretirse
    okuyan calisan sistemle donmus sistemi ayirt edemez."""
    karar = ozet.karar
    if karar is None:
        return ""
    if karar.devre_kesildi:
        return ("🛑 Sistem kendini durdurdu: bugün sınırdan fazla sinyal "
                "çıktı, yeni öneriler yarın")
    acik = karar.sinyaller()
    if not acik:
        return "✅ Bugün yapılacak işlem yok"
    return (f"🔔 {len(acik)} işlem önerisi: "
            + ", ".join(_ad(s.ad, ozet.adlar) for s in acik)
            + " (ayrı mesajda)")


MESAJDA_AZAMI_UYARI = 3     # gerisi ekli raporda


def _uyari_kisalt(metin: str) -> str:
    """Ilk ' - ' ve ilk cumle sonrasini keser: gerekce ve cozum yolu raporda
    duruyor, telefonda okunan sey sorunun kendisi."""
    return metin.split(" - ", 1)[0].split(". ", 1)[0].rstrip(" .")


def _uyari_satirlari(uyarilar: list[str]) -> list[str]:
    """Sade karsiligi olan uyari acik cumleyle, geri kalani SAYI olarak.

    Teknik notlar (kur ucgenlemesi, olculmemis maliyet parametresi, bayat
    seri...) bakim isidir; telefonda okunmalari hicbir karari degistirmez.
    Yok sayilmazlar: sayilari her mesajda gorunur, metinleri ekli raporda.
    """
    onemli = list(dict.fromkeys(
        u.sade for u in uyarilar if getattr(u, "sade", "")))
    teknik = sum(1 for u in uyarilar if not getattr(u, "sade", ""))
    satirlar = [f"⚠️ {kacis(u)}" for u in onemli[:MESAJDA_AZAMI_UYARI]]
    if len(onemli) > MESAJDA_AZAMI_UYARI:
        teknik += len(onemli) - MESAJDA_AZAMI_UYARI
    if teknik:
        satirlar.append(f"ℹ️ {teknik} teknik not (raporda)")
    return satirlar


def gun_sonu_mesaji(ozet: GunSonuOzeti) -> str:
    """Gun sonu / brifing ozeti - SADE bicim (2026-11-07).

    Her satir tek soruya cevap: ne kadar, bugun ne oldu, mevduattan iyi mi,
    islem var mi. Teknik uyarilar yalnizca SAYI olarak girer. Tum tablolar
    ekli raporda; mesaj silmez, SIKISTIRIR.
    """
    satirlar = [f"<b>{ozet.baslik} · {_gun_adi(ozet.veri_zamani)}</b>", ""]
    satirlar += _durum_satirlari(ozet)
    satirlar += [s for s in (_kur_satiri(ozet), _kazanc_satiri(ozet),
                             _islem_satiri(ozet)) if s]
    if ozet.onsoz:
        # Kaynagi isaretlenir: ustteki her sayi olculmustur, bu satir ise bir
        # modelin AYNI MESAJI okuyup yazdigi yorumdur.
        satirlar += ["", f"🤖 <i>{kacis(ozet.onsoz)}</i> (model yorumu)"]

    uyari = _uyari_satirlari(ozet.uyarilar)
    if uyari:
        satirlar += [""] + uyari

    satirlar += ["", "<i>Kağıt portföy, gerçek para yok. Ayrıntı ekteki "
                 "raporda.</i>"]
    return "\n".join(satirlar)


UYARI_SIMGELERI = {
    "veri": "📉", "maliyet": "💸", "devre": "🛑", "kaynak": "🔌", "sistem": "⚙️",
}


def uyari_mesaji(tip: str, mesaj: str) -> str:
    """Tek satirlik uyari. Tip bilinmiyorsa genel simge - tanimsiz tip
    yuzunden uyari GONDERILMEMESI en kotu sonuc."""
    return f"<b>{UYARI_SIMGELERI.get(tip, '⚠️')} {kacis(tip.upper())}</b>\n{kacis(mesaj)}"


def uyarilari_topla(fiyatlar, portfoy, karar, maliyet, bayatlik,
                    risk=None, duyarlilik=None) -> list[str]:
    """Gun sonu ozetine girecek TUM veri/model uyarilari.

    Tek yerde toplanmasi sart: eskiden uyari bloklari mesaj sablonunun icine
    dagilmisti ve yeni bir uyari turu eklendiginde rapora girip Telegram'a
    girmemesi cok kolaydi. Simdi liste tek noktada uretilir, sablon yalnizca
    basar.

    Sira ONEM sirasina gore: model bozuklugu > degerleme bozuklugu > veri
    bayatligi. Okuyan ilk satirdan itibaren en agirini gorur.
    """
    uyarilar: list[str] = []

    if karar is not None and karar.devre_kesildi:
        uyarilar.append(Uyari(
            f"ANORMAL ISLEM YOGUNLUGU: bugun {karar.gunluk_sayi} sinyal olustu "
            f"(tavan {karar.gunluk_maks}). Sinyal uretimi DURDURULDU - bu "
            "genellikle portfoyun degil verinin bozuk oldugunu gosterir.",
            sade=f"Bugün {karar.gunluk_sayi} sinyal çıktı (sınır "
                 f"{karar.gunluk_maks}); veri bozuk olabilir, öneriler durdu"))

    # Hurdle YEDEK kaynaktan geliyor. Bu satir bastirilamaz: yedek politika
    # faizi mevduattan ~11 puan dusuk, yani gereken getiri citasi da o kadar
    # DUSUK hesaplaniyor. Sessizce gevsemis bir cita, gevsemis olduguna dair
    # hicbir isaret tasimayan bir citadir.
    if maliyet is not None and maliyet.risksiz_yedege_dusuldu:
        uyarilar.append(Uyari(
            f"Mevduat kiyasi iyimser olabilir: faiz YEDEK kaynaktan "
            f"({maliyet.risksiz_kaynagi}, "
            f"%{(maliyet.tl_risksiz_yillik or 0) * 100:.2f}) - birincil kaynak "
            f"kullanilamadi. Gercek mevduat alternatifin bundan YUKSEK "
            f"olabilir; o durumda cita oldugundan dusuk, varliklar "
            f"oldugundan iyi gorunur.",
            sade="Güncel mevduat faizi alınamadı; karşılaştırma eski oranla"))

    # Hurdle rate durdurmayacak kadar ama guvenilecek kadar da taze degil.
    # Rapor uretiliyor; bayatligin GORUNMEMESI asil tehlike oldugu icin
    # gereken getiri / asiri getiri / nakit getirisi okunmadan once bu satir
    # okunmali - bu yuzden listenin en ustune yakin.
    if maliyet is not None and not maliyet.risksiz_taze_mi():
        yas = maliyet.risksiz_gun_yasi()
        if yas is not None:
            sonrasi = ("bir sonraki kaynaga dusulur"
                       if len(maliyet.risksiz_zincir) > 1 else "rapor uretilmez")
            uyarilar.append(
                f"Mevduat faizi verisi {yas} GUNLUK, kiyas eski orana dayaniyor"
                f" - {maliyet.risksiz_bayatlik_gun} "
                f"gunden eskisi bayat sayilir (kaynak {maliyet.risksiz_serisi}, "
                f"{maliyet.risksiz_tarih}); "
                f"{maliyet.risksiz_durdurma_gun} gunu asarsa {sonrasi}.")

    engellenenler = maliyet.engellenenler if maliyet is not None else {}
    if engellenenler:
        kalemler = ", ".join(maliyet.eksik_kalem_ozeti)
        uyarilar.append(
            f"Eksik maliyet kalemi: {len(engellenenler)} varlikta sinyal yok "
            f"({kalemler}) - degerler varliklar.yaml -> maliyet")

    for uyari in (karar.uyarilar if karar is not None else []):
        uyarilar.append(uyari)

    if karar is not None:
        for sonuc in karar.hafta_sonu_uyarilari:
            uyarilar.append(Uyari(
                f"{sonuc.ad}: hedeften sapti ({sonuc.yon}) ama hafta sonu "
                "islem onerilmedi - ince likidite, hafta sonu genis esigi "
                "asilmadi, yalnizca uyari.",
                sade=f"{sonuc.ad} hedeften saptı; hafta sonu olduğu için "
                     "öneri verilmedi"))

    supheliler = fiyatlar.kurumsal_olay_supheleri if fiyatlar is not None else {}
    for sembol, gerekce in sorted(supheliler.items()):
        uyarilar.append(Uyari(
            f"Olasi kurumsal olay {sembol}: {gerekce} "
            "- degerleme durduruldu, risk hesabindan cikarildi.",
            sade=f"{sembol} fiyatında açıklanamayan sıçrama; değerlemesi "
                 "durduruldu"))

    if risk is not None and risk.gozlem_guvenilirligi_dustu:
        uyarilar.append(
            f"Volatilite tahmini guvenilirligi dustu: dislama risk verisinin "
            f"%{risk.gozlem_dususu * 100:.0f}'ini goturdu "
            f"(esik %{risk.gozlem_dusus_esigi * 100:.0f}).")

    for parametre, semboller in (duyarlilik.olculmesi_gerekenler
                                 if duyarlilik is not None else []):
        uyarilar.append(
            f"{len(semboller)} varlikta sinyal bastirildi: '{parametre}' "
            f"maliyeti olculmedi ({', '.join(semboller)}) - bu parametre "
            "karari degistirebildigi icin olculene kadar islem onerilmez.")

    ucgenleme = fiyatlar.ucgenleme if fiyatlar is not None else None
    for sonuc in sorted(getattr(ucgenleme, "dogrulanmayanlar", []),
                        key=lambda u: u.sembol):
        uyarilar.append(f"Dogrulanmamis kripto fiyati {sonuc.sembol}: "
                        f"{sonuc.gerekce}")
    for sonuc in sorted(getattr(ucgenleme, "primliler", []),
                        key=lambda u: u.sembol):
        uyarilar.append(f"TR primi {sonuc.sembol}: {sonuc.tr_primi * 100:+.2f}% "
                        f"(kur: {sonuc.kur_kaynagi})")

    if portfoy is not None and portfoy.fiyatlanamayan:
        uyarilar.append(Uyari(
            f"Fiyatlanamayan pozisyon: {', '.join(portfoy.fiyatlanamayan)}. "
            "Agirliklar ve rebalancing tavsiyesi bu yuzden guvenilmez.",
            sade=f"Fiyatı alınamadı: {', '.join(portfoy.fiyatlanamayan)}; "
                 "dağılım güvenilmez"))

    bayatlar = (fiyatlar.bayat_semboller(bayatlik)
                if fiyatlar is not None and bayatlik is not None else {})
    for sembol, gecikme in sorted(bayatlar.items()):
        uyarilar.append(f"Bayat fiyat {sembol}: {gecikme} islem gunu "
                        "guncellenmedi.")
    return uyarilar


# --------------------------------------------------------------------------
# Haber ozeti
# --------------------------------------------------------------------------

KATEGORI_BASLIKLARI = {
    "makro": "Makro (kur, faiz, enflasyon)",
    "piyasa": "Piyasa",
    "kripto": "Kripto",
}

MESAJDA_AZAMI = 5      # kategori basina; gerisi ekli dosyada


def _kategori_sirasi(ikili) -> tuple[int, str]:
    sira = {"makro": 0, "piyasa": 1, "kripto": 2}
    return (sira.get(ikili[0], 9), ikili[0])


def _haberleri_grupla(haberler: list) -> list[tuple[str, list]]:
    gruplar: dict[str, list] = {}
    for h in haberler:
        gruplar.setdefault(h.kategori, []).append(h)
    return sorted(gruplar.items(), key=_kategori_sirasi)


def _degerlendirme_satirlari(degerlendirme) -> list[str]:
    """Bir basligin altina gelen model ozeti. Degerlendirme yoksa hicbir sey.

    Yalnizca YUKSEK ilgi ozet yazdirir: her basliga bir cumle eklemek mesaji
    ikiye katlar ve secici olmayan bir vurgu hicbir seyi vurgulamaz.
    """
    if degerlendirme is None or degerlendirme.ilgi != YUKSEK:
        return []
    etkilenen = (f" [{', '.join(degerlendirme.etkilenen)}]"
                 if degerlendirme.etkilenen else "")
    if not degerlendirme.ozet:
        return [f"  <i>{kacis(etkilenen.strip())}</i>"] if etkilenen else []
    return [f"  <i>{kacis(degerlendirme.ozet + etkilenen)}</i>"]


def haber_mesaji(haberler: list, uyarilar: list[str], bugun,
                 degerlendirmeler: dict | None = None) -> str:
    """Telegram'a giden KISA haber ozeti.

    Sistemin geri kalanindan farkli olarak burasi YORUM URETMEZ - basliklari
    gruplar ve tazeligini isaretler. Sebep: bu sistemin hicbir yerinde
    olculmemis bir sey iddia edilmiyor; haber basligindan piyasa yorumu
    turetmek tam olarak bunu yapmak olurdu. Basliklar okuyana ait.
    """
    satirlar = [f"<b>📰 Haberler — {_gun_adi(str(bugun))}</b>", ""]

    if not haberler:
        satirlar.append("Taze baslik bulunamadi.")
        if uyarilar:
            satirlar += ["", "<b>Sebep</b>"]
            satirlar += [f"• {kacis(u)}" for u in uyarilar]
        else:
            satirlar.append("Beslemeler cevap verdi ama esikteki gun "
                            "araliginda yeni baslik yoktu.")
        return "\n".join(satirlar)

    kaynaklar = sorted({h.kaynak for h in haberler})
    satirlar.append(f"{len(kaynaklar)} kaynaktan {len(haberler)} taze baslik.")

    for kategori, grup in _haberleri_grupla(haberler):
        satirlar += ["", f"<b>{KATEGORI_BASLIKLARI.get(kategori, kategori)}</b>"]
        for h in grup[:MESAJDA_AZAMI]:
            damga = " <i>(tarihsiz)</i>" if h.tarihsiz else ""
            satirlar.append(f"• {kacis(h.baslik)}{damga}")
            satirlar += _degerlendirme_satirlari(
                (degerlendirmeler or {}).get(h.baslik))
        if len(grup) > MESAJDA_AZAMI:
            kalan = len(grup) - MESAJDA_AZAMI
            satirlar.append(f"<i>… {kalan} baslik daha, ekli dosyada</i>")

    tarihsiz = sum(1 for h in haberler if h.tarihsiz)
    if tarihsiz:
        satirlar += ["", f"<i>{tarihsiz} baslik tarih bildirmedi - guncel "
                     "olduklari VARSAYILMADI, oldugu gibi listelendi.</i>"]
    if uyarilar:
        satirlar += ["", "<b>⚠️ Okunamayan kaynak</b>"]
        satirlar += [f"• {kacis(u)}" for u in uyarilar]

    satirlar += ["", "<i>Basliklar ham kaynaktan gelir; sistem bunlardan "
                 "KARAR URETMEZ. Baglantilar ekli dosyada.</i>"]
    if degerlendirmeler:
        satirlar.append("<i>Sira ve ozetler model uretimi; ilgi etiketi bir "
                        "fiyat tahmini DEGIL, okuma sirasi onerisidir.</i>")
    return "\n".join(satirlar)


def haber_dosyasi(haberler: list, uyarilar: list[str], bugun,
                  degerlendirmeler: dict | None = None) -> str:
    """Ekte giden AYRINTI dosyasi: tum basliklar, baglantilar, tarihler."""
    satirlar = [
        "---",
        f'title: "Haber Ozeti {bugun}"',
        f"date_created: {bugun}",
        "tags: [yatirim, haber]",
        "status: processed",
        "---",
        "",
        f"# Haber Ozeti - {_gun_adi(str(bugun))}",
        "",
        "Ham besleme ciktisi. Sistem bu basliklardan KARAR URETMEZ; fiyat ve",
        "oran disinda hicbir girdi karar yoluna girmez. Burasi baglam icin.",
        "",
    ]
    if not haberler:
        satirlar += ["Taze baslik bulunamadi.", ""]
    for kategori, grup in _haberleri_grupla(haberler):
        satirlar += [f"## {KATEGORI_BASLIKLARI.get(kategori, kategori)}", ""]
        for h in grup:
            tarih = h.tarih.isoformat() if h.tarih else "tarihsiz"
            if h.baglanti:
                satirlar.append(f"- [{h.baslik}]({h.baglanti}) - {h.kaynak}, {tarih}")
            else:
                satirlar.append(f"- {h.baslik} - {h.kaynak}, {tarih}")
            degerlendirme = (degerlendirmeler or {}).get(h.baslik)
            if degerlendirme is not None and degerlendirme.ozet:
                etkilenen = (" - " + ", ".join(degerlendirme.etkilenen)
                             if degerlendirme.etkilenen else "")
                satirlar.append(f"  - ilgi: {degerlendirme.ilgi}{etkilenen}. "
                                f"{degerlendirme.ozet}")
        satirlar.append("")
    if uyarilar:
        satirlar += ["## Okunamayan kaynaklar", ""]
        satirlar += [f"- {u}" for u in uyarilar]
        satirlar += ["",
                     "Bir beslemenin dusmesi ozeti durdurmaz; eksik kaynak",
                     "burada acikca yazilir - sessizce kisalan bir ozet,",
                     "kisaldigini bilmeyen okuyucu uretir.", ""]
    return "\n".join(satirlar)
