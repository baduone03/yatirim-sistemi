"""Telegram bildirimi.

Telegram Bot API'ye dogrudan HTTPS POST atar - python-telegram-bot'a gerek yok:
tek mesaj gonderiyoruz, async dongu ve MarkdownV2 kacis derdi gereksiz.
HTML parse modu kullanilir, kacilacak yalnizca 3 karakter var.

Kimlik bilgileri vault kokundeki .env dosyasindan okunur.
Token asla koda veya rapora yazilmaz.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import requests

from config import PROJE_DIZINI, Esikler
from maliyet import donem_orani
from portfolio import Portfoy, SinifSapmasi

VARSAYILAN_ESIKLER = Esikler(rebalancing_sapma=0.05, risk_katkisi_ust=0.25)

ENV_DOSYASI = PROJE_DIZINI.parents[1] / ".env"
API_KOKU = "https://api.telegram.org"
ZAMAN_ASIMI = 15


class TelegramHatasi(RuntimeError):
    pass


def _kacis(metin: str) -> str:
    """Telegram HTML parse modu icin: yalnizca bu uc karakter kacirilir."""
    return metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


ORTAM_ANAHTARLARI = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")


def env_oku(dosya: Path = ENV_DOSYASI) -> dict[str, str]:
    """Kimlik bilgilerini okur: once .env dosyasi, sonra ortam degiskenleri.

    Ortam degiskeni dosyayi EZER. Sebep: GitHub Actions'ta .env dosyasi yok,
    degerler repository secrets'tan ortama enjekte edilir. Lokalde ise .env
    kullanilir. Ayni kod iki ortamda da calisir.

    python-dotenv bagimliligi eklemeye degmez - format zaten bu kadar basit.
    """
    degerler: dict[str, str] = {}

    if dosya.exists():
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            anahtar, deger = satir.split("=", 1)
            degerler[anahtar.strip()] = deger.strip().strip('"').strip("'")

    for anahtar in ORTAM_ANAHTARLARI:
        ortam_degeri = os.environ.get(anahtar)
        if ortam_degeri:
            degerler[anahtar] = ortam_degeri.strip()

    return degerler


def mesaj_gonder(metin: str, env: dict[str, str] | None = None) -> None:
    """Telegram'a mesaj gonderir. Basarisizlikta TelegramHatasi firlatir."""
    env = env if env is not None else env_oku()
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        if not ENV_DOSYASI.exists():
            raise TelegramHatasi(
                f"{ENV_DOSYASI} yok ve TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID "
                "ortam degiskeni de tanimli degil.\n"
                "Lokal: .env.example dosyasini .env olarak kopyala.\n"
                "GitHub Actions: repository secrets tanimli mi kontrol et."
            )
        if not env:
            # En sik hata: degerler '#' ile baslayan yorum satirina yazilmis.
            raise TelegramHatasi(
                f"{ENV_DOSYASI} okundu ama hicbir ANAHTAR=deger satiri bulunamadi. "
                "Degerler '#' ile baslayan yorum satirina yazilmis olabilir."
            )
        eksik = [ad for ad, deger in
                 (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id))
                 if not deger]
        raise TelegramHatasi(f"{ENV_DOSYASI} icinde eksik/bos: {', '.join(eksik)}")

    try:
        yanit = requests.post(
            f"{API_KOKU}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": metin, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=ZAMAN_ASIMI,
        )
    except requests.RequestException as hata:
        # KRITIK: token URL yolunda. urllib3'un ConnectionError mesaji istek
        # URL'sini icerir; ham hatayi yukari birakmak token'i loga sizdirir.
        # Hata TURUNU aktar, metnini ASLA.
        raise TelegramHatasi(
            f"Telegram'a ulasilamadi ({type(hata).__name__})"
        ) from None

    if not yanit.ok:
        try:
            aciklama = yanit.json().get("description", "bilinmeyen hata")
        except ValueError:
            # Proxy/gateway HTML donebilir - JSON bekleyip patlamayalim.
            aciklama = "yanit JSON degil"
        raise TelegramHatasi(f"Telegram reddetti (HTTP {yanit.status_code}): {aciklama}")


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
            f"{simge}  <b>{_kacis(islem.sembol)}</b>  {islem.adet:g} adet"
        )
        satirlar.append(
            f"     {_tl(islem.fiyat_try)} x {islem.adet:g} = {_tl(islem.tutar_try)}"
        )
        if islem.gerekce:
            satirlar.append(f"     <i>{_kacis(islem.gerekce)}</i>")
    return satirlar


def ucgenleme_durdurma_mesaji(durduranlar, baslik: str) -> str:
    """Rapor URETILMEDIGINDE gonderilen mesaj.

    Rapor yoksa sessiz kalmak en kotu secenek: kimse bir seyin durdugunu
    bilmez ve bayat raporu guncel sanir.
    """
    satirlar = [f"<b>🛑 {_kacis(baslik)} - RAPOR URETILMEDI</b>", ""]
    for sonuc in sorted(durduranlar, key=lambda u: u.sembol):
        satirlar.append(f"• {_kacis(sonuc.sembol)}: {_kacis(sonuc.gerekce)}")
        if sonuc.tl_fiyat is not None and sonuc.beklenen_tl is not None:
            satirlar.append(
                f"  BTCTurk {sonuc.tl_fiyat:,.0f} TL / beklenen "
                f"{sonuc.beklenen_tl:,.0f} TL (kur: {_kacis(sonuc.kur_kaynagi)})")
    satirlar += [
        "",
        "Uc kaynak da taze ama birbirini tutmuyor. Once kaynaklari kontrol et; "
        "gercek bir kopukluksa esigi degil pozisyonu gozden gecir.",
    ]
    return "\n".join(satirlar)


def _asiri_getiri_satiri(getiri: float, durum, maliyet) -> list[str]:
    """Risksiz getiriye gore fazla/eksik.

    Brut getiriyi tek basina gostermek yaniltir: %1 kazanan bir portfoy, ayni
    donemde mevduat %0.5 verdiyse iyi, %2 verdiyse kotudur.
    """
    if maliyet is None or durum is None or not durum.baslangic_tarihi:
        return []
    if maliyet.tl_risksiz_yillik is None:
        return []
    try:
        gun = (date.today() - date.fromisoformat(durum.baslangic_tarihi)).days
    except ValueError:
        return []
    if gun <= 0:
        return []
    risksiz = donem_orani(maliyet.tl_risksiz_yillik, gun)
    isaret = "🟢" if getiri >= risksiz else "🔴"
    return [f"{isaret} Asiri getiri {(getiri - risksiz) * 100:+.2f}% "
            f"(risksiz {risksiz * 100:.2f}%, {gun} gun)"]


def hurdle_eksik_mesaji(baslik: str, seri: str) -> str:
    """Hurdle rate yoksa rapor uretilmez - sessiz kalmak en kotu secenek."""
    return "\n".join([
        f"<b>🛑 {_kacis(baslik)} - RAPOR URETILMEDI</b>",
        "",
        "TL risksiz getiri (hurdle rate) yok.",
        f"Canli seri: {_kacis(seri) or '(tanimsiz)'}",
        "Yedek: varliklar.yaml -> maliyet.firsat.tl_risksiz_yillik",
        "",
        "Bu deger olmadan getiri sifira gore olculur ve risksiz getirinin "
        "altinda kalan her portfoy 'basarili' gorunur.",
    ])


def ozet_mesaji(portfoy: Portfoy, sapmalar: list[SinifSapmasi], risk,
                durum=None, baslik: str = "Yatirim", fiyatlar=None,
                esikler: Esikler = VARSAYILAN_ESIKLER, bayatlik=None,
                maliyet=None) -> str:
    """Rapordan kisa Telegram ozeti uretir - detay markdown raporda kalir."""
    if durum:
        taban = durum.baslangic_nakit_try
        net = portfoy.toplam_deger_try - taban
    else:
        taban = portfoy.toplam_maliyet_try
        net = portfoy.toplam_deger_try - taban
    getiri = net / taban if taban else 0.0
    isaret = "🟢" if net >= 0 else "🔴"

    satirlar = [
        f"<b>{_kacis(baslik)}</b>",
        f"{isaret} {_tl(portfoy.toplam_deger_try)}  ({getiri * 100:+.1f}%)",
        f"Net: {_tl(net)} | Nakit: {_tl(portfoy.nakit_try)}",
        "",
        f"Volatilite {risk.portfoy_volatilitesi * 100:.1f}%"
        f" | Drawdown {risk.portfoy_max_drawdown * 100:.1f}%",
    ]
    satirlar += _asiri_getiri_satiri(getiri, durum, maliyet)

    if durum:
        satirlar += _islem_satirlari(durum, date.today().isoformat())

    ucgenleme = fiyatlar.ucgenleme if fiyatlar is not None else None
    if ucgenleme is not None and ucgenleme.primliler:
        satirlar += ["", "<b>TR primi</b>"]
        for sonuc in sorted(ucgenleme.primliler, key=lambda u: u.sembol):
            satirlar.append(
                f"• {_kacis(sonuc.sembol)}: {sonuc.tr_primi * 100:+.2f}% "
                f"(kur: {_kacis(sonuc.kur_kaynagi)})")
    if ucgenleme is not None and ucgenleme.dogrulanmayanlar:
        satirlar += ["", "<b>⚠️ Dogrulanmamis kripto fiyati</b>"]
        for sonuc in sorted(ucgenleme.dogrulanmayanlar, key=lambda u: u.sembol):
            satirlar.append(f"• {_kacis(sonuc.sembol)}: {_kacis(sonuc.gerekce)}")

    # Kurumsal olay suphesi en agir uyari: rakamlar yanlis olabilir ve sebebi
    # veri eksikligi degil, kayitli olmayan bir bedelsiz/split olabilir.
    supheliler = fiyatlar.kurumsal_olay_supheleri if fiyatlar is not None else {}
    if supheliler:
        satirlar += ["", "<b>🛑 Olasi kurumsal olay</b>"]
        for sembol, gerekce in sorted(supheliler.items()):
            satirlar.append(f"• {_kacis(sembol)}: {_kacis(gerekce)}")
        satirlar.append("Degerleme durduruldu. Bedelsiz/split ise olay defterine yaz.")

    # Fiyatlanamayan pozisyon varsa sapma hesabi eksik veri uzerinden yapilmis
    # demektir; tavsiyeyi guvenilir gibi gondermek yanlis islem yaptirir.
    if portfoy.fiyatlanamayan:
        satirlar += [
            "",
            "<b>⚠️ Eksik veri</b>",
            f"Fiyatlanamayan pozisyon: {_kacis(', '.join(portfoy.fiyatlanamayan))}",
            "Rebalancing tavsiyesi bu yuzden guvenilmez.",
        ]

    # Eksik maliyet kalemi olan varlik icin sinyal URETILMEZ. Bastirmayi
    # Telegram'da da uygulamak sart: rapor bastiriyor ama mesaj bastirmiyorsa
    # Dodo mesaja bakip islem yapar ve tum kural bosa duser.
    engellenenler = maliyet.engellenenler if maliyet is not None else {}
    if engellenenler:
        satirlar += [
            "",
            f"<b>🛑 Eksik maliyet kalemi — {len(engellenenler)} varlikta "
            "sinyal yok</b>",
        ]
        for kalem, semboller in maliyet.eksik_kalem_ozeti.items():
            satirlar.append(
                f"• <code>{_kacis(kalem)}</code> — {len(semboller)} varlik")
        satirlar.append("Degerler: varliklar.yaml -> maliyet")

    sapanlar = [s for s in sapmalar
                if abs(s.sapma) >= esikler.rebalancing_sapma
                and (maliyet is None or maliyet.sinif_sinyali_acik(s.sinif))]
    if sapanlar:
        satirlar += ["", "<b>Rebalancing uyarisi</b>"]
        for sapma in sapanlar:
            yon = "fazla" if sapma.sapma > 0 else "eksik"
            satirlar.append(
                f"• {_kacis(sapma.sinif)}: {sapma.guncel_agirlik * 100:.1f}%"
                f" (hedef {sapma.hedef_agirlik * 100:.0f}%) — "
                f"{abs(sapma.sapma) * 100:.1f} puan {yon}"
            )

    yogun = [r for r in risk.varlik_riskleri if esikler.kisilmali(r)
             and (maliyet is None or maliyet.sinyal_acik(r.sembol))]
    if yogun:
        satirlar += ["", "<b>Kisilmali</b>"]
        for varlik_riski in yogun:
            satirlar.append(
                f"• {_kacis(varlik_riski.sembol)}: katki "
                f"{varlik_riski.risk_katkisi * 100:.1f}%, "
                f"beta {varlik_riski.beta:.2f}"
            )

    if not sapanlar and not yogun and not engellenenler:
        satirlar += ["", "Esik asilmadi — islem gerekmiyor."]

    # Veri sorunu sessiz kalmamali: bayat fiyat yanlis degerleme demek.
    bayatlar = fiyatlar.bayat_semboller(bayatlik) if fiyatlar is not None else {}
    if bayatlar:
        satirlar += ["", "<b>⚠️ Bayat fiyat verisi</b>"]
        for sembol, gecikme in sorted(bayatlar.items()):
            satirlar.append(f"• {_kacis(sembol)}: {gecikme} gundur guncellenmedi")

    return "\n".join(satirlar)
