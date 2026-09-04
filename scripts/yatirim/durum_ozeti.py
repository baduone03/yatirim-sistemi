"""Gun sonu / brifing mesajinin basina gelen uc cumlelik okuma.

SORUN: mesaj dogru ama uzun. Portfoy durumu, hareket anlatisi, islem
bolumu, uyarilar - hepsi gerekli, ama telefonda ilk bakista "bugun onemli
bir sey oldu mu" sorusunun cevabi gorunmuyor.

COZUM: modele SISTEMIN KENDI URETTIGI mesaj verilir ve ondan yalnizca o
metindeki olgulari kullanan uc cumle istenir.

NEDEN GIRDI OLARAK HAM SAYI DEGIL, HAZIR METIN: modele ayri bir olgu listesi
hazirlansaydi o liste zamanla mesajdan SAPARDI - mesaja yeni bir bolum
eklenir, olgu listesi guncellenmez ve ozet artik mesajda yazmayan bir sey
soyler. Girdi mesajin kendisi oldugu surece ozet mesajdan ileri gidemez.

RAPOR DOSYASINA YAZILMAZ, YALNIZCA TELEGRAM'A: rapor `.md` Actions
tarafindan repoya commit ediliyor. Model ciktisi kosudan kosuya kelime
duzeyinde degisir; commit edilseydi her gun anlamsiz bir diff uretirdi.
"""

from __future__ import annotations

import re

from llm import LLMAyarlari, LLMHatasi, http_llm, sor

AZAMI_CUMLE = 3
# Modele giden metin tavani: mesaj uzasa da istem sisip gecikmeyi buyutmesin.
AZAMI_KARAKTER = 4000

ISTEM_BASI = (
    "Asagida bir yatirim takip sisteminin urettigi gunluk ozet mesaji var.\n\n"
    f"Bu metni okuyan biri icin EN FAZLA {AZAMI_CUMLE} cumlelik Turkce bir "
    "giris yaz.\n\n"
    "Kurallar:\n"
    "- YALNIZCA metinde yazan olgulari kullan. Metinde olmayan hicbir sayi, "
    "isim veya olay ekleme.\n"
    "- Tahmin yapma, tavsiye verme, 'alinabilir/satilabilir' deme.\n"
    "- En onemli degisimi ve varsa uyariyi one cikar.\n"
    "- Baslik, madde isareti, emoji veya HTML etiketi kullanma. Duz cumle yaz.\n"
    "- Giris veya kapanis cumlesi ekleme, dogrudan ozete basla.\n\n"
    "METIN:\n"
)

_ETIKET = re.compile(r"<[^>]+>")


def _sadelestir(metin: str) -> str:
    """HTML etiketlerini atar. Model etiketi olgu sanmasin, ciktiya kopyalamasin."""
    return _ETIKET.sub("", metin).strip()[:AZAMI_KARAKTER]


def kirp(ham: str) -> str:
    """Cikti disiplini: etiket temizligi + cumle tavani.

    Model uc cumle istendiginde bes yazabiliyor. Tavani istemde BIRAKMAK
    yetmez - istem bir ricadir, kirpma bir garantidir.
    """
    temiz = " ".join(_ETIKET.sub("", ham).split())
    if not temiz:
        return ""
    cumleler = re.findall(r"[^.!?]+[.!?]", temiz) or [temiz]
    return " ".join(c.strip() for c in cumleler[:AZAMI_CUMLE]).strip()


def ozet_uret(mesaj_metni: str, ayarlar: LLMAyarlari, env: dict[str, str],
              gonder=None) -> tuple[str, str]:
    """Doner: (ozet, uyari). Uyari doluysa ozet bostur ve sebebi yazar.

    Hicbir kosulda mesaji DUSURMEZ: ozet uretilemezse mesaj eskisi gibi,
    onsozsuz gider. Kolaylik katmani, asil ciktinin onune gecemez.
    """
    govde = _sadelestir(mesaj_metni)
    if not govde:
        return "", ""
    try:
        ham = sor(ISTEM_BASI + govde, ayarlar, env, gonder or http_llm)
    except LLMHatasi as hata:
        return "", f"durum ozeti uretilemedi: {hata}"
    ozet = kirp(ham)
    return (ozet, "") if ozet else ("", "durum ozeti bos dondu")
