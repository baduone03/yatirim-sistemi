"""Telegram mesaj sablonlari.

`notify.py` tasima katmani (HTTPS POST, kimlik, hiz siniri); bu dosya metin
uretir. Ayri durmalarinin sebebi: sablon degistirmek icin tasima kodunu
okumak zorunda kalmamak ve sablonlari agsiz test edebilmek.

HTML parse modu kullanilir - kacilacak yalnizca `& < >` var. MarkdownV2'ye
gecilseydi 18 karakter kacmak gerekirdi ve her tablo satiri risk olurdu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portfolio import Portfoy


def kacis(metin: str) -> str:
    """Telegram HTML parse modu icin: yalnizca bu uc karakter kacirilir.

    Sira onemli: `&` ilk sirada olmali, yoksa `&lt;` icindeki `&` yeniden
    kacirilir ve okuyucu `&amp;lt;` gorur.
    """
    return metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tl(deger: float) -> str:
    return f"{deger:,.0f} TL".replace(",", ".")


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
        return f"{sayi:.2f}"
    return f"{sayi * 100:.2f}%"


def islem_karari_mesaji(islem: IslemOnerisi, tetikleyen: list[Tetikleyici],
                        etki: list[Etki], gidis_donus: float | None,
                        komisyon_try: float | None,
                        uyarilar: list[str] | None = None) -> str:
    """Islem karari bildirimi.

    VERI ZAMANI yazar, mesaj zamani DEGIL. Ayrim kritik: mesaj 19:04'te gitse
    de fiyat Cuma kapanisina aitse karar Cuma verisiyle verilmistir. Mesaj
    zamanini gostermek bayat veriyi guncel gibi sunar - bu sistemde en pahali
    hata turu.
    """
    simge = {"AL": "🟩", "SAT": "🟥"}.get(islem.yon, "🟨")
    satirlar = [
        f"<b>{simge} {kacis(islem.yon)} {kacis(islem.sembol)}</b>",
        f"{islem.adet:g} adet x {_tl(islem.fiyat_try)} = {_tl(islem.tutar_try)}",
        "",
        f"<b>Veri:</b> {kacis(islem.veri_zamani)} "
        f"({kacis(islem.veri_kaynagi)})",
    ]
    if tetikleyen:
        satirlar += ["", "<b>Tetikleyen</b>"]
        satirlar += [f"• {t.satir()}" for t in tetikleyen]
    if etki:
        satirlar += ["", "<b>Etki</b>"]
        satirlar += [f"• {e.satir()}" for e in etki]

    satirlar += ["", "<b>Maliyet</b>"]
    satirlar.append(f"• Bu islemin komisyonu: "
                    f"{_tl(komisyon_try) if komisyon_try is not None else 'OLCULEMEDI'}")
    satirlar.append(f"• Gidis-donus maliyeti: "
                    f"{f'{gidis_donus * 100:.2f}%' if gidis_donus is not None else 'OLCULEMEDI'}")
    if gidis_donus is None:
        satirlar.append("  ⚠️ Eksik maliyet kalemi - bu islem KARSIZ olabilir.")

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
    baslik: str = "🌙 Gun sonu"
    # Anlati icin gereken uc alan. Hepsi opsiyonel: eksikse ilgili bolum
    # mesajdan tumuyle DUSER, uydurma cumle uretilmez.
    karar: object | None = None          # sinyal.Karar - islem bolumu icin
    adlar: dict = field(default_factory=dict)   # sembol -> okunur ad
    baslangic_try: float = 0.0           # sermaye tabani; 0 ise oran yazilmaz


AYLAR = ("Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz",
         "Agustos", "Eylul", "Ekim", "Kasim", "Aralik")


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


def _buyukluk(oran: float) -> str:
    mutlak = abs(oran)
    if mutlak < 0.005:
        return "neredeyse yatay kaldi"
    if mutlak < 0.02:
        return "sinirli hareket etti"
    return "belirgin bicimde hareket etti"


def _hareket_anlatisi(ozet: GunSonuOzeti) -> list[str]:
    """Portfoy neden oynadi: varliklarin kendisi mi, kur mu?

    Bu ayrim mesajin en cok is goren cumlesi. +%3 TL getirisi, dolar %3
    degerlendigi icin cikmissa bu bir yatirim basarisi DEGIL - ayni sonucu
    doviz tutarak da alirdin. Sayilari yan yana dizip okuyanin cikarmasini
    beklemek, tam da bu ayrimin kacirilmasi demek.
    """
    if ozet.degisim_24s is None:
        return ["Gunluk degisim olculemedi - yeterli fiyat verisi yok. "
                "Asagidaki toplam deger yine de guncel fiyatlarla hesaplandi."]

    satirlar = [f"Portfoy son 24 saatte {_buyukluk(ozet.degisim_24s)} "
                f"({ozet.degisim_24s * 100:+.1f}%)."]

    usd = [a for a in ozet.ayrimlar if a.para_birimi == "USD"]
    if not usd:
        return satirlar

    ort_kur = sum(a.kur_getirisi for a in usd) / len(usd)

    # KUR PAYI: her varlikta TL getirisinin ne kadari kurdan geldi.
    # |kur| / (|kur| + |yerel|) -> 1'e yakinsa hareket kurun, 0'a yakinsa
    # varligin. Ortalama mutlak getirileri karsilastirmak yerine bunu
    # kullanmanin sebebi: tek bir buyuk yerel hareket ortalamayi ele gecirip
    # geri kalan varliklarda kurun hakim oldugunu gizliyordu.
    paylar = []
    for a in usd:
        toplam_hareket = abs(a.kur_getirisi) + abs(a.yerel_getiri)
        if toplam_hareket > 0.0005:          # olcek altini oranlamak gurultu
            paylar.append(abs(a.kur_getirisi) / toplam_hareket)
    if not paylar:
        return satirlar
    kur_payi = sum(paylar) / len(paylar)

    if kur_payi >= 0.6:
        yon = "degerlendi" if ort_kur > 0 else "geriledi"
        satirlar.append(
            f"Hareketin kaynagi varliklar degil KUR: dolar "
            f"{abs(ort_kur) * 100:.1f}% {yon} ve dolarla tuttugumuz "
            f"{len(usd)} varligi TL bazinda "
            f"{'yukari' if ort_kur > 0 else 'asagi'} tasidi.")
        # Ornek olarak dolar bazinda EN KOTU giden varlik secilir: kurun ne
        # kadarini yuttugunu en net o gosterir.
        ornek = min(usd, key=lambda a: a.yerel_getiri)
        if ornek.toplam_tl > ornek.yerel_getiri:
            satirlar.append(
                f"En net ornek {_ad(ornek.sembol, ozet.adlar)}: dolar bazinda "
                f"{ornek.yerel_getiri * 100:+.1f}%, ama kur sayesinde TL'de "
                f"{ornek.toplam_tl * 100:+.1f}%.")
    elif kur_payi <= 0.4:
        satirlar.append(
            f"Hareket varliklarin kendisinden geldi; kur bu donemde "
            f"{ort_kur * 100:+.1f}% ile belirleyici olmadi.")
    else:
        satirlar.append(
            f"Hareketi tek bir sebebe baglamak dogru olmaz: varlik fiyatlari "
            f"ve kur ({ort_kur * 100:+.1f}%) birlikte etkili oldu.")
    return satirlar


def _islem_anlatisi(ozet: GunSonuOzeti) -> list[str]:
    """Islem yapildi mi, yapilmadiysa NEDEN yapilmadi.

    "Islem yok" tek basina bilgi degil - sistem mi sessiz, yoksa fren mi
    devrede? Ikisi cok farkli durumlar ve ayni mesaji uretirlerse okuyan
    calisan sistemle donmus sistemi ayirt edemez.
    """
    karar = ozet.karar
    if karar is None:
        return []
    if karar.devre_kesildi:
        return [f"Gunluk islem siniri doldu ({karar.gunluk_maks} karar) ve "
                "devre kesici devreye girdi. Yeni sinyaller yarina birakildi - "
                "bu bir ariza degil, tek gunde asiri islem yapmayi engelleyen fren."]
    acik = karar.sinyaller()
    if not acik:
        return ["Islem yapilmadi: hicbir varlik sinifi hedefinden esigi asacak "
                "kadar sapmadi. Sistem sapma olmadan islem onermez - komisyon "
                "odemeye deger bir sebep yoksa beklemek dogru karardir."]
    adlar = ", ".join(_ad(s.ad, ozet.adlar) for s in acik)
    return [f"{len(acik)} sinyal acik: {adlar}. Ayrintilari ekli raporda."]


def _kazanc_anlatisi(ozet: GunSonuOzeti) -> list[str]:
    """Getiriyi risksiz alternatife gore konumlandirir.

    Ciplak "+%4,2 kazandin" cumlesi eksik: ayni parayi mevduatta tutmak da
    kazandiriyordu. Olcut mutlak getiri degil, risksiz getirinin USTUNE ne
    konuldugu. TL'de risksiz oran %48 civarindayken bu ayrim her seydir.
    """
    if ozet.asiri_getiri is None or ozet.risksiz is None:
        return ["Risksiz getiri okunamadigi icin bu donemde 'riske deger miydi' "
                "sorusu olculemedi."]
    kazandi = ozet.asiri_getiri >= 0
    return [
        f"Ayni parayi mevduatta tutsaydin {ozet.donem_gun} gunde "
        f"{ozet.risksiz * 100:.2f}% kazanirdin. Portfoy bunun "
        f"{'USTUNDE' if kazandi else 'ALTINDA'} kaldi: "
        f"{ozet.asiri_getiri * 100:+.2f}%.",
        ("Yani riski almanin bir karsiligi oldu." if kazandi else
         "Yani su ana kadar risk almak, beklemekten daha iyi sonuc vermedi."),
    ]


def gun_sonu_mesaji(ozet: GunSonuOzeti) -> str:
    """Gun sonu / brifing ozeti - ANLATI bicimi.

    Tasarim karari: mesaj "ne oldu"yu cumleyle anlatir, tum sayilar ekli
    rapora birakilir. Onceki surum 15 sayiyi alt alta diziyordu ve en onemli
    bilgi (hareketin kurdan gelmesi gibi) hicbir yerde yazmiyordu - okuyanin
    cikarmasi bekleniyordu. Sayi listesi okunmaz, cumle okunur.
    """
    portfoy = ozet.portfoy
    baslik = f"<b>{ozet.baslik} — {_gun_adi(ozet.veri_zamani)}</b>"

    fark = portfoy.toplam_deger_try - ozet.baslangic_try
    yon = "uzerinde" if fark >= 0 else "altinda"
    oran = fark / ozet.baslangic_try if ozet.baslangic_try else 0.0
    satirlar = [
        baslik,
        "",
        f"{_tl(portfoy.toplam_deger_try)}. Basladigimiz "
        f"{_tl(ozet.baslangic_try)}'nin {_tl(abs(fark))} {yon} "
        f"({oran * 100:+.1f}%).",
    ]

    for baslik_metni, govde in (
        ("Bugun ne oldu", _hareket_anlatisi(ozet)),
        ("Islem yapildi mi", _islem_anlatisi(ozet)),
        ("Kazanc gercek mi", _kazanc_anlatisi(ozet)),
    ):
        if govde:
            satirlar += ["", f"<b>{baslik_metni}</b>"] + govde

    if ozet.uyarilar:
        satirlar += ["", "<b>⚠️ Dikkat</b>"]
        satirlar += [f"• {kacis(u)}" for u in ozet.uyarilar]

    satirlar += ["", "<i>Bu kagit para - gercek islem yok. "
                 "Tum sayilar ekli raporda.</i>"]
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
        uyarilar.append(
            f"ANORMAL ISLEM YOGUNLUGU: bugun {karar.gunluk_sayi} sinyal olustu "
            f"(tavan {karar.gunluk_maks}). Sinyal uretimi DURDURULDU - bu "
            "genellikle portfoyun degil verinin bozuk oldugunu gosterir.")

    # Hurdle YEDEK kaynaktan geliyor. Bu satir bastirilamaz: yedek politika
    # faizi mevduattan ~11 puan dusuk, yani gereken getiri citasi da o kadar
    # DUSUK hesaplaniyor. Sessizce gevsemis bir cita, gevsemis olduguna dair
    # hicbir isaret tasimayan bir citadir.
    if maliyet is not None and maliyet.risksiz_yedege_dusuldu:
        uyarilar.append(
            f"Hurdle YEDEK kaynaktan: {maliyet.risksiz_kaynagi} "
            f"(%{(maliyet.tl_risksiz_yillik or 0) * 100:.2f}). Birincil kaynak "
            f"kullanilamadi. Gercek mevduat alternatifin bundan YUKSEK "
            f"olabilir - o durumda cita oldugundan dusuk, varliklar "
            f"oldugundan iyi gorunur.")

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
                f"Hurdle rate {yas} GUNLUK ({maliyet.risksiz_serisi}, "
                f"{maliyet.risksiz_tarih}) - taze esigi "
                f"{maliyet.risksiz_bayatlik_gun} gun. Gereken getiri, asiri "
                f"getiri ve nakit getirisi bu orandan turuyor; "
                f"{maliyet.risksiz_durdurma_gun} gunu asarsa {sonrasi}.")

    engellenenler = maliyet.engellenenler if maliyet is not None else {}
    if engellenenler:
        kalemler = ", ".join(maliyet.eksik_kalem_ozeti)
        uyarilar.append(
            f"Eksik maliyet kalemi - {len(engellenenler)} varlikta sinyal yok "
            f"({kalemler}). Degerler: varliklar.yaml -> maliyet")

    for uyari in (karar.uyarilar if karar is not None else []):
        uyarilar.append(uyari)

    if karar is not None:
        for sonuc in karar.hafta_sonu_uyarilari:
            uyarilar.append(
                f"{sonuc.ad}: esik asildi ({sonuc.yon}) ama hafta sonu genis "
                "esigi asilmadi - ince likidite, yalnizca uyari.")

    supheliler = fiyatlar.kurumsal_olay_supheleri if fiyatlar is not None else {}
    for sembol, gerekce in sorted(supheliler.items()):
        uyarilar.append(f"Olasi kurumsal olay {sembol}: {gerekce} "
                        "- degerleme durduruldu, risk hesabindan cikarildi.")

    if risk is not None and risk.gozlem_guvenilirligi_dustu:
        uyarilar.append(
            f"Volatilite tahmini guvenilirligi dustu: dislama risk verisinin "
            f"%{risk.gozlem_dususu * 100:.0f}'ini goturdu "
            f"(esik %{risk.gozlem_dusus_esigi * 100:.0f}).")

    for parametre, semboller in (duyarlilik.olculmesi_gerekenler
                                 if duyarlilik is not None else []):
        uyarilar.append(
            f"Olculmemis parametre {parametre}: {len(semboller)} varlikta "
            f"karar degistiriyor ({', '.join(semboller)}) - sinyal bastirildi.")

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
        uyarilar.append(
            f"Fiyatlanamayan pozisyon: {', '.join(portfoy.fiyatlanamayan)}. "
            "Agirliklar ve rebalancing tavsiyesi bu yuzden guvenilmez.")

    bayatlar = (fiyatlar.bayat_semboller(bayatlik)
                if fiyatlar is not None and bayatlik is not None else {})
    for sembol, gecikme in sorted(bayatlar.items()):
        uyarilar.append(f"Bayat fiyat {sembol}: {gecikme} islem gunu "
                        "guncellenmedi.")
    return uyarilar
