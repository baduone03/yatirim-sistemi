"""Haber beslemeleri: RSS/Atom cekme, ayristirma ve tazelik suzmesi.

Bu modul SAYI URETMEZ, metin tasir. Sistemin geri kalani fiyat ve oran
olcerken burasi baglam saglar - ve baglamin karar uretmedigi her yerde
oldugu gibi, tazeligi acikca isaretlenir.

TASARIM: `getir` enjekte edilir (kaynaklar.py'deki ayni kalip). Testler
sahte bir getirici gecirir, ag'a hic cikilmaz. Yeni besleme eklerken bu
kalibi bozma - yoksa test paketi ag'a bagimli hale gelir.

BIR BESLEMENIN DUSMESI RAPORU DURDURMAZ. Uc kaynaktan biri cevap vermezse
o kaynak "okunamadi" diye isaretlenir ve digerleri yazilir. `OLCULEMEDI !=
DURDUR` ayriminin haber tarafindaki karsiligi: bizim korlugumuz, dunyanin
sessizligi degil.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

import requests

ZAMAN_ASIMI = 15
# Tarayici gibi gorunmek gerekiyor: bazi haber sunuculari varsayilan
# python-requests basligina 403 doner.
BASLIKLAR = {"User-Agent": "Mozilla/5.0 (compatible; yatirim-sistemi/1.0)"}

# Atom ve RSS ayni agacta farkli isim alanlari kullanir.
ATOM = "{http://www.w3.org/2005/Atom}"


class HaberHatasi(RuntimeError):
    """Besleme okunamadi veya ayristirilamadi."""


@dataclass(frozen=True)
class Haber:
    baslik: str
    baglanti: str
    kaynak: str
    kategori: str
    tarih: date | None = None       # None = besleme tarih vermedi

    @property
    def tarihsiz(self) -> bool:
        return self.tarih is None


def http_metin(url: str, getir=None) -> str:
    """Beslemeyi ham metin olarak indirir.

    `http_json`den ayri: RSS XML'dir, JSON degil. Ayni dogrulamayi JSON
    uzerinden yapmaya calismak her beslemede "JSON degil" hatasi uretirdi.
    """
    try:
        cevap = requests.get(url, headers=BASLIKLAR, timeout=ZAMAN_ASIMI)
    except requests.RequestException as hata:
        raise HaberHatasi(f"{url} okunamadi: {type(hata).__name__}") from None
    if not cevap.ok:
        raise HaberHatasi(f"{url} HTTP {cevap.status_code} dondurdu")
    # requests, HTTP basliginda charset yoksa ISO-8859-1 VARSAYAR (RFC 2616).
    # Haber beslemeleri neredeyse daima UTF-8 ve kodlamayi XML bildiriminde
    # tasir; varsayilana birakmak Turkce ve tipografik karakterleri bozar
    # ("Here's" -> "Here�s"). Govdeden tahmin etmek dogru olani secer.
    if not cevap.encoding or "charset" not in cevap.headers.get(
            "content-type", "").lower():
        cevap.encoding = cevap.apparent_encoding or "utf-8"
    return cevap.text


def _metin(dugum, *adlar: str) -> str:
    """Ilk dolu alt dugumun metni. RSS ve Atom farkli adlar kullanir."""
    for ad in adlar:
        bulunan = dugum.find(ad)
        if bulunan is not None:
            if bulunan.text and bulunan.text.strip():
                return bulunan.text.strip()
            # Atom'da baglanti metinde degil href niteligindedir.
            href = bulunan.get("href")
            if href:
                return href.strip()
    return ""


def _tarihi_coz(ham: str) -> date | None:
    """RSS (RFC822) ve Atom (ISO8601) tarihlerini cozer.

    Cozulemeyen tarih None doner, BUGUN SAYILMAZ. Tarihsiz bir basligi
    guncel varsaymak, haber tarafinda tam olarak `bayat fiyat` tuzagidir:
    eski bir haber taze gorunur ve karari yanlis yone iter.
    """
    if not ham:
        return None
    try:
        return parsedate_to_datetime(ham).date()
    except (TypeError, ValueError):
        pass
    try:
        temiz = ham.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(temiz).date()
    except ValueError:
        return None


def beslemeyi_coz(xml_metin: str, kaynak: str, kategori: str) -> list[Haber]:
    """RSS 2.0 veya Atom beslemesini Haber listesine cevirir."""
    try:
        kok = ET.fromstring(xml_metin.strip())
    except ET.ParseError as hata:
        raise HaberHatasi(f"{kaynak}: XML ayristirilamadi ({hata})") from None

    ogeler = kok.iter("item")
    haberler = [
        Haber(baslik=_metin(oge, "title"), baglanti=_metin(oge, "link"),
              kaynak=kaynak, kategori=kategori,
              tarih=_tarihi_coz(_metin(oge, "pubDate", "date")))
        for oge in ogeler
    ]
    if haberler:
        return [h for h in haberler if h.baslik]

    haberler = [
        Haber(baslik=_metin(oge, f"{ATOM}title"),
              baglanti=_metin(oge, f"{ATOM}link"),
              kaynak=kaynak, kategori=kategori,
              tarih=_tarihi_coz(_metin(oge, f"{ATOM}updated",
                                       f"{ATOM}published")))
        for oge in kok.iter(f"{ATOM}entry")
    ]
    return [h for h in haberler if h.baslik]


def haberleri_topla(beslemeler: list[dict], getir=http_metin,
                    bugun: date | None = None, azami_gun: int = 2,
                    besleme_basina: int = 6
                    ) -> tuple[list[Haber], list[str]]:
    """Tum beslemeleri toplar, tazelik suzer. Doner: (haberler, uyarilar).

    Besleme basina tavan var: tek bir yuksek hacimli kaynak (kripto
    beslemeleri gunde 50+ baslik uretir) ozeti tek basina ele gecirmemeli.

    Tarihsiz haberler ELENMEZ ama isaretlenir - besleme tarih vermiyor diye
    haberi atmak, olcemedigimiz seyi yok saymak olurdu.
    """
    bugun = bugun or datetime.now(timezone.utc).date()
    haberler: list[Haber] = []
    uyarilar: list[str] = []

    for besleme in beslemeler:
        ad = str(besleme.get("ad") or besleme.get("url", "?"))
        url = str(besleme.get("url", ""))
        kategori = str(besleme.get("kategori", "genel"))
        if not url:
            uyarilar.append(f"{ad}: url tanimsiz, atlandi")
            continue
        try:
            ham = getir(url)
            cozulen = beslemeyi_coz(ham, ad, kategori)
        except HaberHatasi as hata:
            uyarilar.append(f"{ad} okunamadi: {hata}")
            continue

        taze = [h for h in cozulen
                if h.tarih is None or (bugun - h.tarih).days <= azami_gun]
        if cozulen and not taze:
            uyarilar.append(
                f"{ad}: {len(cozulen)} baslik var ama hepsi {azami_gun} "
                "gunden eski")
        haberler += taze[:besleme_basina]

    return haberler, uyarilar
