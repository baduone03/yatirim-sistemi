"""Haber basliklarini portfoye gore degerlendirir. KARAR URETMEZ.

SORUN: `haberleri_topla` besleme basina ILK 6 basligi aliyor. Besleme
kronolojik siralidir, alaka duzeyine gore degil - yani "Tesla hissesi dustu"
ve sponsorlu urun tanitimi listeye giriyor, TCMB faiz karari besleme basina
tavan yuzunden disarida kalabiliyor. Secim olcusu ZAMANDI, oysa okuyanin
sordugu soru "bu benim portfoyumu ilgilendiriyor mu".

COZUM: basliklar modele portfoy varlik listesiyle birlikte verilir, model
portfoyu dogrudan ilgilendirenleri ve alakasizlari isaretler, ilkine tek
cumle Turkce ozet yazar. Siralama bu etikete gore yapilir.

SINIR - bu modul sayilar uretmez ve karar yoluna GIRMEZ:
  * Hicbir cikti sinyal, agirlik veya esige donusmez.
  * "ilgi" etiketi bir FIYAT TAHMINI DEGILDIR; "bu basligi once oku"
    demektir, "bu varligi al" demez.
  * Model cagrisi duserse basliklar HAM haliyle, eski sirada gosterilir.
    Analiz bir kolayliktir; kaybi haberi kaybettirmez.

TASARIM: `gonder` enjekte edilir; test paketi ag'a cikmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from llm import LLMAyarlari, LLMHatasi, http_llm, json_coz, sor

YUKSEK, DUSUK, ALAKASIZ = "yuksek", "dusuk", "alakasiz"
ILGI_SIRASI = {YUKSEK: 0, DUSUK: 1, ALAKASIZ: 2}
# Modele giden baslik tavani. Istemi sinirsiz buyutmek hem gecikmeyi hem de
# modelin baslik atlama olasiligini artirir.
AZAMI_BASLIK = 30
# Kac baslik YUKSEK isaretlenebilir. Tavansiz birakildiginda model 30
# basligin 24'unu yuksek sayiyor (olculdu) - o etiket artik hicbir seyi
# siralamaz ve cikti jeton tavanini asip cevabi yarida kesiyor. Sinirli bir
# kota modeli SECIM yapmaya zorlar; siralamanin degeri secimin kendisinde.
AZAMI_YUKSEK = 8

SATIR = "\n"


@dataclass(frozen=True)
class Degerlendirme:
    ilgi: str
    etkilenen: tuple[str, ...] = ()
    ozet: str = ""

    @property
    def sira(self) -> int:
        return ILGI_SIRASI.get(self.ilgi, ILGI_SIRASI[DUSUK])


def istem_uret(basliklar: list[str], varlik_adlari: dict[str, str]) -> str:
    """Numarali baslik listesi + portfoy tanimindan istem kurar.

    Basliklar NUMARAYLA eslesir, metinle degil: modelin basligi yeniden
    yazmasi (kisaltmasi, cevirmesi) eslesmesi gereken anahtari bozardi.

    CIKTI NEDEN ASIMETRIK: her baslik icin tam kayit istendiginde 30 baslik
    ~1350 jeton uretiyor ve cagri 25 saniyelik butceyi asip zaman asimina
    dusuyor (olculdu: 6 baslik 10 sn, 30 baslik >25 sn). Oysa mesajda
    yalnizca YUKSEK ilgililerin ozeti gorunuyor - geri kalani icin uretilen
    her cumle bosa yanan suredir. Bu yuzden ozet yalnizca yuksek
    ilgililerden istenir, alakasizlar ciplak numara olarak doner,
    listelenmeyen baslik DUSUK sayilir.
    """
    portfoy = ", ".join(f"{sembol} ({ad})" for sembol, ad
                        in sorted(varlik_adlari.items())) or "tanimsiz"
    liste = SATIR.join(f"{i}. {b}" for i, b in enumerate(basliklar, 1))
    kurallar = [
        f"Portfoydeki varliklar: {portfoy}.",
        "",
        "Asagidaki haber basliklarini bu portfoy acisindan degerlendir.",
        "",
        "Cikti kurallari:",
        f'- "yuksek": portfoyu EN COK ilgilendiren EN FAZLA {AZAMI_YUKSEK} '
        "baslik. Her biri icin numara, etkilenen sembol kodlari ve TEK cumle "
        f"Turkce ozet. {AZAMI_YUKSEK} tanesini doldurmak zorunda degilsin; "
        "gercekten onemli olan yoksa listeyi bos birak.",
        "- Ozet yalnizca basligin soyledigini yazsin. Fiyat tahmini yapma, "
        "yorum ekleme, tavsiye verme.",
        '- "alakasiz": reklam, sponsorlu icerik, urun tanitimi ve portfoyle '
        "ilgisiz basliklarin numaralari. Yalnizca numara, aciklama yok.",
        "- Iki listeye de girmeyen baslik orta ilgili sayilir, yazma.",
        "",
        "Yalnizca su JSON nesnesini dondur:",
        '{"yuksek": [{"no": 1, "etkilenen": ["KOD"], "ozet": "..."}], '
        '"alakasiz": [2, 5]}',
        "",
        liste,
    ]
    return SATIR.join(kurallar)


def _yuksek_kaydi(kayit) -> tuple[int, Degerlendirme] | None:
    """Tek "yuksek" kaydini cevirir. Bozuk kayit ATLANIR, tumunu dusurmez."""
    if not isinstance(kayit, dict):
        return None
    try:
        no = int(kayit.get("no"))
    except (TypeError, ValueError):
        return None
    ham = kayit.get("etkilenen")
    etkilenen = (tuple(str(e).strip() for e in ham if str(e).strip())
                 if isinstance(ham, list) else ())
    return no, Degerlendirme(ilgi=YUKSEK, etkilenen=etkilenen,
                             ozet=str(kayit.get("ozet", "")).strip())


def cevabi_coz(ham: str, adet: int) -> dict[int, Degerlendirme]:
    """Model cevabini {baslik_no: Degerlendirme} sozlugune cevirir.

    Aralik disi numara atilir: model uydurdugu 40. basligi listeye
    sokamamali. Listelenmeyen baslik hata degil - DUSUK sayilir ve ham
    haliyle, ozetsiz gosterilir.
    """
    veri = json_coz(ham)
    if not isinstance(veri, dict):
        raise LLMHatasi("model cevabi nesne degil")
    sonuc: dict[int, Degerlendirme] = {}
    # Kota istemde SORULUR, burada UYGULANIR: istem bir ricadir, kirpma bir
    # garantidir. Modelin kendi sirasi korunur - ilk yazdigi, en onemli
    # gordugudur.
    for kayit in (veri.get("yuksek") or [])[:AZAMI_YUKSEK]:
        cozulen = _yuksek_kaydi(kayit)
        if cozulen and 1 <= cozulen[0] <= adet:
            sonuc[cozulen[0]] = cozulen[1]
    for ham_no in veri.get("alakasiz") or []:
        try:
            no = int(ham_no)
        except (TypeError, ValueError):
            continue
        # YUKSEK kazanir: model bir basligi iki listeye birden koyarsa
        # sessizce sona atmak, ozeti yazilmis bir basligi gorunmez yapardi.
        if 1 <= no <= adet and no not in sonuc:
            sonuc[no] = Degerlendirme(ilgi=ALAKASIZ)
    return sonuc


def haberleri_degerlendir(haberler: list, varlik_adlari: dict[str, str],
                          ayarlar: LLMAyarlari, env: dict[str, str],
                          gonder=None) -> tuple[list, dict, str]:
    """Doner: (siralanmis haberler, {baslik: Degerlendirme}, uyari metni).

    Uyari BOS ise analiz calisti. Doluysa haberler DEGISMEDEN doner ve
    cagiran uyariyi ciktiya yazar - sessizce ham listeye dusmek, okuyana
    "bunlar en ilgili basliklar" izlenimi verirdi.

    ALAKASIZ basliklar elenmez, sona atilir. Elemek modelin yanilgisini
    gorunmez yapardi; sona atmak yalnizca sirayi degistirir.
    """
    if not haberler:
        return haberler, {}, ""
    kirpilan = haberler[:AZAMI_BASLIK]
    istem = istem_uret([h.baslik for h in kirpilan], varlik_adlari)
    try:
        ham = sor(istem, ayarlar, env, gonder or http_llm)
        degerlendirmeler = cevabi_coz(ham, len(kirpilan))
    except LLMHatasi as hata:
        return haberler, {}, f"haber analizi yapilamadi: {hata}"
    if not degerlendirmeler:
        return haberler, {}, "haber analizi bos dondu, basliklar ham sirada"

    esleme = {kirpilan[no - 1].baslik: d
              for no, d in degerlendirmeler.items()}
    # Kararli siralama: ayni ilgi duzeyinde ozgun sira korunur, boylece iki
    # kosu ayni girdide ayni ciktiyi verir.
    sirali = sorted(
        haberler,
        key=lambda h: esleme[h.baslik].sira if h.baslik in esleme
        else ILGI_SIRASI[DUSUK])
    return sirali, esleme, ""
