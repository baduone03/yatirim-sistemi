"""Telegram bildirimi.

Telegram Bot API'ye dogrudan HTTPS POST atar - python-telegram-bot'a gerek yok:
tek mesaj gonderiyoruz, async dongu ve MarkdownV2 kacis derdi gereksiz.
HTML parse modu kullanilir, kacilacak yalnizca 3 karakter var.

Kimlik bilgileri vault kokundeki .env dosyasindan okunur.
Token asla koda veya rapora yazilmaz.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import requests

from bildirim import (
    ATLANDI,
    BIRIKTIRILDI,
    GONDERILDI,
    KUYRUK_DOSYASI,
    Bildirim,
    BildirimAyarlari,
    GonderimSonucu,
    birlestir,
    bol,
    kuyrugu_oku,
    kuyrugu_yaz,
    son_saatteki_gonderim,
)
from config import PROJE_DIZINI, TR_OFSET
from mesaj import (
    Etki,
    GunSonuOzeti,
    IslemOnerisi,
    Tetikleyici,
    gun_sonu_mesaji,
    islem_karari_mesaji,
    uyari_mesaji,
)
from sinyal import (
    GONDERILEN_LOG,
    gonderildi_yaz,
    gonderilen_anahtarlar,
    islem_anahtari,
    simdi_utc,
)

ENV_DOSYASI = PROJE_DIZINI.parents[1] / ".env"
API_KOKU = "https://api.telegram.org"
ZAMAN_ASIMI = 15


class TelegramHatasi(RuntimeError):
    pass


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


def idempotent_gonder(metin: str, anahtar: str, ek_anahtarlar: list[str] | None = None,
                      env: dict[str, str] | None = None,
                      log: Path = GONDERILEN_LOG,
                      simdi: datetime | None = None) -> bool:
    """Ayni anahtar daha once gonderildiyse GONDERMEZ.

    Doner: True = gonderildi, False = zaten gonderilmisti.

    `anahtar` tekillik anahtaridir (gunluk ozette `ozet:{tarih}`).
    `ek_anahtarlar` yalnizca kayda gecer; mesajin icerdigi tekil islem
    sinyallerini isaretler ki ileride sinyal bazli gonderim eklendiginde ayni
    sinyal ikinci kez gitmesin.

    Log SONRA yazilir: once yazip sonra gonderirsek basarisiz bir gonderim
    "gonderildi" isaretlenir ve mesaj bir daha asla denenmez.
    """
    if anahtar in gonderilen_anahtarlar(log):
        return False
    simdi = simdi or simdi_utc()
    for parca in bol(metin):
        mesaj_gonder(parca, env)
    gonderildi_yaz([anahtar, *(ek_anahtarlar or [])], simdi, log)
    return True


# --- Bildirim kanali: hiz siniri + sessiz saatler ---------------------------
#
# Her gonderim buradan gecer. Dogrudan `mesaj_gonder` cagirmak frenleri atlar;
# tek istisna rapor URETILEMEDIGINDE giden hata mesajlaridir (main.py) - onlar
# hiz sinirina takilmamali, cunku sessiz kalmak en kotu secenek.


def _kuyrugu_gonder(bekleyenler: list[Bildirim], baslik: str, ayarlar,
                    env, log: Path, kuyruk: Path,
                    simdi: datetime) -> GonderimSonucu:
    """Biriken bildirimleri TEK mesajda gonderir."""
    if not bekleyenler:
        return GonderimSonucu(ATLANDI)
    anahtar = f"toplu:{simdi.date().isoformat()}:{simdi.strftime('%H%M')}"
    idempotent_gonder(birlestir(bekleyenler, baslik),
                      anahtar, [b.anahtar for b in bekleyenler], env, log, simdi)
    kuyrugu_yaz([], kuyruk)
    return GonderimSonucu(GONDERILDI, len(bekleyenler))


def kuyrugu_bosalt(ayarlar: BildirimAyarlari, env: dict | None = None,
                   log: Path = GONDERILEN_LOG, kuyruk: Path = KUYRUK_DOSYASI,
                   simdi: datetime | None = None) -> GonderimSonucu:
    """Sessiz saat bittiyse veya hiz siniri bosaldiysa kuyrugu gonderir.

    Her kosunun BASINDA cagrilir. Cagrilmazsa gece biriken bildirimler diskte
    kalir ve hicbir zaman gonderilmez - sessizce kaybolan uyari, hic uretilmemis
    uyaridan kotudur cunku sistem calisiyor sanilir.
    """
    simdi = simdi or simdi_utc()
    bekleyenler = kuyrugu_oku(kuyruk)
    if not bekleyenler or ayarlar.sessiz_mi(simdi):
        return GonderimSonucu(ATLANDI, kuyruk=bekleyenler)
    return _kuyrugu_gonder(bekleyenler, "🔔 Biriken bildirimler", ayarlar,
                           env, log, kuyruk, simdi)


def kanaldan_gonder(bildirim: Bildirim, ayarlar: BildirimAyarlari,
                    env: dict | None = None, log: Path = GONDERILEN_LOG,
                    kuyruk: Path = KUYRUK_DOSYASI,
                    simdi: datetime | None = None) -> GonderimSonucu:
    """Tek gonderim kapisi: idempotency -> sessiz saat -> hiz siniri -> gonder.

    Sira onemli. Idempotency ilk sirada cunku zaten gonderilmis bir mesaji
    kuyruga almak onu ikinci kez gonderir. Sessiz saat hiz sinirindan once
    cunku gece hicbir sey gitmeyecekse sayaci mesgul etmenin anlami yok.

    Sessiz saat kapisi TIPE BAKAR (`biriktirilir_mi`): islem karari gece de
    gider, ozet ve uyari birikir.
    """
    simdi = simdi or simdi_utc()
    if bildirim.anahtar in gonderilen_anahtarlar(log):
        return GonderimSonucu(ATLANDI)

    bekleyenler = kuyrugu_oku(kuyruk)
    if bildirim.anahtar in {b.anahtar for b in bekleyenler}:
        return GonderimSonucu(ATLANDI, kuyruk=bekleyenler)

    damgali = bildirim if bildirim.olusma else Bildirim(
        bildirim.tip, bildirim.anahtar, bildirim.metin,
        simdi.isoformat(timespec="seconds"))

    if ayarlar.biriktirilir_mi(damgali.tip, simdi):
        yeni = [*bekleyenler, damgali]
        kuyrugu_yaz(yeni, kuyruk)
        return GonderimSonucu(BIRIKTIRILDI, kuyruk=yeni)

    # Sessiz saatte istisna tip: hiz siniri BIRLESTIRMESI atlanir. Birlestirme
    # bekleyen kuyrugu da yollar; gece 01:05'te gelen bir islem sinyali, saat
    # 00:55'te dolan hiz sinirine takilip tum gece kuyrugunu bosaltirdi.
    if not (ayarlar.sessiz_mi(simdi)
            and damgali.tip in ayarlar.sessiz_istisna_tipler) \
            and son_saatteki_gonderim(simdi, log) >= ayarlar.saatlik_maks_mesaj:
        # Hiz siniri asildi: mesaji ayri gondermek yerine biriktir ve
        # bekleyenlerle BIRLIKTE tek mesaj olarak yolla. Tek tek gondermek
        # sinirin varlik sebebini ortadan kaldirirdi.
        return _kuyrugu_gonder([*bekleyenler, damgali], "🔔 Hiz siniri - toplu ozet",
                               ayarlar, env, log, kuyruk, simdi)

    idempotent_gonder(damgali.metin, damgali.anahtar, None, env, log, simdi)
    return GonderimSonucu(GONDERILDI, 1)


# --- 5.1: gonderim giris noktalari -----------------------------------------
#
# Uc fonksiyon, uc mesaj turu. Hepsi kanaldan gecer; sablon uretimi mesaj.py'da.


def gonder_islem_karari(islem: IslemOnerisi, tetikleyen: list[Tetikleyici],
                        etki: list[Etki], gidis_donus: float | None,
                        komisyon_try: float | None,
                        uyarilar: list[str] | None = None,
                        ayarlar: BildirimAyarlari | None = None,
                        env: dict | None = None,
                        simdi: datetime | None = None) -> GonderimSonucu:
    """Tek islem karari bildirimi.

    Idempotency anahtari SAAT icerir: siklik artinca ayni gun ayni sembolde
    iki farkli karar cikabilir, ama ayni saat icinde ayni karar iki kez
    gitmemeli.
    """
    simdi = simdi or simdi_utc()
    return kanaldan_gonder(
        Bildirim(
            tip="islem",
            anahtar=islem_anahtari(islem.sembol, islem.yon.lower(), simdi),
            metin=islem_karari_mesaji(islem, tetikleyen, etki, gidis_donus,
                                      komisyon_try, uyarilar),
        ),
        ayarlar or BildirimAyarlari(), env, simdi=simdi)


def gonder_gun_sonu(ozet: GunSonuOzeti, ayarlar: BildirimAyarlari | None = None,
                    env: dict | None = None, simdi: datetime | None = None,
                    gun: str = "") -> GonderimSonucu:
    """Gunluk kapanis ozeti veya acilis brifingi. Her biri gunde bir tane.

    `gun` TR gunudur ve disaridan gelir: UTC gunune baglansaydi TR 00:00-03:00
    arasindaki kosu bir onceki gunun anahtarini kullanir ve ozet atlanirdi.
    """
    simdi = simdi or simdi_utc()
    gun = gun or (simdi + TR_OFSET).date().isoformat()
    tur = "brifing" if "brifing" in ozet.baslik.lower() else "gunsonu"
    return kanaldan_gonder(
        Bildirim(tip=tur, anahtar=f"{tur}:{gun}", metin=gun_sonu_mesaji(ozet)),
        ayarlar or BildirimAyarlari(), env, simdi=simdi)


def gonder_uyari(tip: str, mesaj: str, ayarlar: BildirimAyarlari | None = None,
                 env: dict | None = None,
                 simdi: datetime | None = None) -> GonderimSonucu:
    """Veri/sistem uyarisi.

    Anahtar SAAT bazli: ayni uyari saatte bir tekrarlanabilir ama saat icinde
    tekrarlanmaz. Tarih bazli olsaydi sabah cozulen bir sorun aksam yeniden
    ortaya ciktiginda haber verilmezdi.
    """
    simdi = simdi or simdi_utc()
    ozet = mesaj[:60].replace(" ", "-").replace(":", "")
    return kanaldan_gonder(
        Bildirim(tip=tip,
                 anahtar=f"uyari:{tip}:{simdi.date().isoformat()}:"
                         f"{simdi.hour:02d}:{ozet}",
                 metin=uyari_mesaji(tip, mesaj)),
        ayarlar or BildirimAyarlari(), env, simdi=simdi)
