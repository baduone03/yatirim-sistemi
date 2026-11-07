"""Telegram sorgu botu - SALT OKUNUR.

GitHub Actions'ta calisir. Bekleyen mesajlari BIR KEZ ceker, cevaplar, cikar.
Long polling yok: Actions kosusu dakika basina faturalanir, acik tutulan bir
soket butcenin tamamini yakar.

GUVENLIK - bu modulun tamami bu dort kural etrafinda kurulu:

  1. IZINLI CHAT: yalnizca `TELEGRAM_IZINLI_CHAT_ID` listesindeki sohbetlere
     cevap verilir. Baska bir chat id'den gelen mesaj SESSIZCE yok sayilir -
     cevap vermek, botun varligini ve calisir oldugunu dogrular.
  2. SABIT KOMUT SOZLUGU: kullanici metni yalnizca `KOMUTLAR` sozlugunde
     ARANIR. Hicbir yerde shell, eval, exec, subprocess, import veya dosya
     yolu olusturmakta KULLANILMAZ. Argumanli tek komut `/fiyat`, argumani da
     yalnizca bilinen sembol listesiyle karsilastirilir.
  3. SIZINTI YOK: beklenmeyen hata kullaniciya tek cumleyle doner. Istisna
     metni, dosya yolu, stack trace ve token asla mesaja girmez - hepsi
     yalnizca Actions loguna yazilir.
  4. YAZMA YOK: hicbir komut islem acmaz, dosya degistirmez. Modulun yazdigi
     TEK dosya offset defteridir (`simulasyon/bot_offset.txt`) ve icerigi
     yalnizca son islenen update_id'dir.

MUKERRER KORUMASI: Telegram `getUpdates` ayni guncellemeyi offset ilerleyene
kadar tekrar verir. Son islenen `update_id` diske yazilir ve sonraki kosu
`offset = son + 1` ile cagirir. Dosya DEGISMEDIYSE commit edilmez - her yarim
saatte bir bos commit uretmek repo gecmisini okunmaz yapar.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bicim import oran, tl, yuzde  # noqa: E402
from bildirim import bol  # noqa: E402
from haber import haberleri_topla  # noqa: E402
from haber_analiz import haberleri_degerlendir  # noqa: E402
from config import PROJE_DIZINI, TR_OFSET, yapilandirmayi_oku  # noqa: E402
from duyarlilik import (  # noqa: E402
    GERCEK,
    HEDEF,
    YEDEK,
    duyarliligi_olc,
    referans_pozisyonlar,
)
from fetch import fiyatlari_getir, maliyet_modelini_coz  # noqa: E402
from kurumsal_olay import bilinen_olay_anahtarlari, olaylari_oku  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from maliyet import TEMEL  # noqa: E402
from mesaj import _gun_adi, _yuzde, haber_dosyasi, haber_mesaji, kacis  # noqa: E402
from notify import API_KOKU, ZAMAN_ASIMI, dosya_gonder, env_oku  # noqa: E402
from portfolio import (  # noqa: E402
    degisim_24s,
    kur_maruziyeti,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from risk import riski_hesapla  # noqa: E402
from sinyal import (  # noqa: E402
    SEMBOL,
    gecmisi_oku,
    kararlari_uret,
    simdi_utc,
)

SIM_DIZINI = PROJE_DIZINI / "simulasyon"
SIM_DEFTERI = SIM_DIZINI / "islemler.yaml"
SIM_OLAY_DEFTERI = SIM_DIZINI / "kurumsal-olaylar.yaml"
OFFSET_DOSYASI = SIM_DIZINI / "bot_offset.txt"
BILDIRIM_DOSYASI = PROJE_DIZINI / "bildirim.yaml"

# Workflow cron adimi. Kodda tek yerde: YAML dogrulamasi buna gore yapilir.
CRON_DAKIKA = 30

BASLIK = "Kağıt portföy"
SON_ISLEM_SAYISI = 5


# --------------------------------------------------------------------------
# Kosu penceresi (bildirim.yaml -> bot)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BotAyarlari:
    """Ne siklikta ve hangi saatlerde cevap verilecegi.

    Workflow cron'u SABIT 30 dakikadir; GitHub Actions zamanlamasi YAML
    okuyamaz. Aralik burada tanimlanir ve script fazladan kosuyu erken
    keser. Boylece sikligi degistirmek icin workflow'a dokunmak gerekmez -
    varliklar.yaml kuralinin ayni uygulamasi.
    """

    aralik_dakika: int = 30
    baslangic_saat: int = 7      # TR
    bitis_saat: int = 1          # TR, ertesi gun

    def calisma_saati_mi(self, an) -> bool:
        """TR saatiyle pencerede miyiz? Pencere gece yarisini asabilir."""
        saat = (an + TR_OFSET).hour
        if self.baslangic_saat == self.bitis_saat:
            return True                     # esitlik = 7/24, sifir uzunluk degil
        if self.baslangic_saat < self.bitis_saat:
            return self.baslangic_saat <= saat < self.bitis_saat
        return saat >= self.baslangic_saat or saat < self.bitis_saat

    def kosulacak_mi(self, an) -> bool:
        """Cron 30 dakikada bir tetikler; aralik daha genisse arayi atla.

        Ornek: aralik 60 -> yalnizca dakikasi 30'un altinda olan kosular
        calisir, digeri hicbir sey yapmadan cikar.
        """
        if not self.calisma_saati_mi(an):
            return False
        if self.aralik_dakika <= CRON_DAKIKA:
            return True
        yerel = an + TR_OFSET
        gecen = yerel.hour * 60 + yerel.minute
        # Cron adimina yuvarla: gercek tetikleme dakikasi 5-30 dk kayabilir.
        adim = round(gecen / CRON_DAKIKA) * CRON_DAKIKA
        return adim % self.aralik_dakika < CRON_DAKIKA


def bot_ayarlarini_oku(dosya: Path = BILDIRIM_DOSYASI) -> BotAyarlari:
    if not dosya.exists():
        return BotAyarlari()
    ham = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("bot") or {}
    ayarlar = BotAyarlari(
        aralik_dakika=int(ham.get("aralik_dakika", 30)),
        baslangic_saat=int(ham.get("baslangic_saat_tr", 7)),
        bitis_saat=int(ham.get("bitis_saat_tr", 1)),
    )
    if ayarlar.aralik_dakika < CRON_DAKIKA:
        raise ValueError(
            f"bildirim.yaml -> bot.aralik_dakika en az {CRON_DAKIKA} olmali "
            f"({ayarlar.aralik_dakika} geldi). Cron bundan daha sik "
            "tetiklenmiyor; daha kucuk bir deger sessizce etkisiz kalirdi.")
    for ad, saat in (("baslangic_saat_tr", ayarlar.baslangic_saat),
                     ("bitis_saat_tr", ayarlar.bitis_saat)):
        if not 0 <= saat <= 23:
            raise ValueError(f"bildirim.yaml -> bot.{ad} 0-23 arasinda olmali, "
                             f"{saat} geldi")
    return ayarlar


# --------------------------------------------------------------------------
# Veri (tembel yuklenir)
# --------------------------------------------------------------------------

@dataclass
class Baglam:
    """Komutlarin paylastigi veri kabi.

    TEMBEL: `/yardim` ve `/param` fiyat verisi istemez. Her kosuda Yahoo'ya
    gitmek, cogu kosuda hic mesaj olmamasina ragmen Actions dakikasi yakardi.
    Veri yalnizca gercekten soruldugunda cekilir ve bir kosuda BIR KEZ.
    """

    env: dict[str, str] = field(default_factory=dict)
    yukleyici: object = None
    _veri: object = None

    @property
    def veri(self):
        if self._veri is None:
            self._veri = (self.yukleyici or veriyi_yukle)(self.env)
        return self._veri


@dataclass(frozen=True)
class Veri:
    yapilandirma: object
    fiyatlar: object
    portfoy: object
    risk: object
    durum: object
    maliyet: object
    duyarlilik: object
    karar: object
    sapmalar: list

    @property
    def veri_zamani(self) -> str:
        """Fiyatlarin AIT OLDUGU gun. Mesajin gonderildigi an DEGIL.

        Ikisini karistirmak bayat veriyi taze gostermenin en kolay yolu:
        mesaj 14:30'da gidiyor diye fiyat 14:30'un fiyati olmuyor.
        """
        return self.fiyatlar.son_tarih


def veriyi_yukle(env: dict[str, str]) -> Veri:
    """Rapor hattinin SALT OKUNUR kopyasi. Hicbir durum dosyasi yazilmaz.

    `kararlari_uret` saf bir fonksiyondur - yeni gecmisi DONER, yazmaz.
    `gecmisi_yaz` burada bilincli olarak CAGRILMAZ: sorgu botunun latch'i
    ilerletmesi, kimse islem yapmadan bekleme suresini baslatirdi.
    """
    yapilandirma = yapilandirmayi_oku()
    olaylar = olaylari_oku(SIM_OLAY_DEFTERI)
    maliyet = maliyet_modelini_coz(yapilandirma)
    bugun = (simdi_utc() + TR_OFSET).date().isoformat()

    islemler, baslangic_nakit, komisyon, baslangic = islemleri_oku(SIM_DEFTERI)
    durum = durumu_hesapla(islemler, baslangic_nakit, komisyon, olaylar,
                           nakit_getirisi_yillik=maliyet.tl_risksiz_yillik,
                           baslangic_tarihi=baslangic, bugun=bugun)

    fiyatlar = fiyatlari_getir(yapilandirma, bilinen_olay_anahtarlari(olaylar), env)
    portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
    risk = riski_hesapla(yapilandirma, fiyatlar, portfoy, olaylar)
    sapmalar = sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)
    duyarlilik = duyarliligi_olc(
        maliyet, yapilandirma.esikler.rebalancing_sapma,
        referans_pozisyonlar(portfoy, yapilandirma.hedef_dagilim,
                             yapilandirma.sinif_haritasi,
                             maliyet.referans_pozisyon_try),
        fiyatlar.usdtry)
    karar = kararlari_uret(sapmalar, risk, yapilandirma.esikler,
                           yapilandirma.bekleme, yapilandirma.devre_kesici,
                           gecmisi_oku(), bugun, maliyet, None, duyarlilik)

    return Veri(yapilandirma=yapilandirma, fiyatlar=fiyatlar, portfoy=portfoy,
                risk=risk, durum=durum, maliyet=maliyet, duyarlilik=duyarlilik,
                karar=karar, sapmalar=sapmalar)


# --------------------------------------------------------------------------
# Komutlar - hepsi SALT OKUNUR
# --------------------------------------------------------------------------

def _basliklar(veri: Veri) -> list[str]:
    # Veri GUNU yazilir, mesaj zamani degil: mesaj 14:30'da gidiyor diye
    # fiyat 14:30'un fiyati olmuyor.
    return [f"<b>📊 {BASLIK} · {kacis(_gun_adi(veri.veri_zamani))} "
            "fiyatlarıyla</b>", ""]


def _ad(veri: Veri, sembol: str) -> str:
    """'GC=F' okuyana bir sey soylemez; adi yoksa sembol, uydurulmaz."""
    varlik = veri.yapilandirma.varliklar.get(sembol)
    return kacis(varlik.ad if varlik and varlik.ad else sembol)


def _belirsizlik_uyarisi(veri: Veri) -> list[str]:
    """Teknik ayrinti /param'da; burada yalnizca VAR oldugu soylenir."""
    belirsizler = veri.duyarlilik.belirsizler
    if not belirsizler:
        return []
    return ["", f"ℹ️ {len(belirsizler)} varlıkta maliyet tam ölçülmediği için "
            "öneri kapalı (parametre belirsizliği, ayrıntı /param)"]


def komut_portfoy(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    portfoy, durum = veri.portfoy, veri.durum
    baslangic = durum.baslangic_nakit_try
    net = portfoy.toplam_deger_try - baslangic
    # Saf FIYAT etkisi: pozisyonlar sabit tutulup fiyatlar geri alinir.
    gunluk = degisim_24s(portfoy, veri.fiyatlar)
    dolar = kur_maruziyeti(portfoy, veri.yapilandirma.varliklar)

    satirlar = _basliklar(veri) + [
        f"💰 Toplam: <b>{tl(portfoy.toplam_deger_try)}</b>",
        f"{'📈' if net >= 0 else '📉'} Başlangıçtan: "
        f"{'+' if net >= 0 else '-'}{tl(abs(net))}"
        + (f" ({_yuzde(net / baslangic)})" if baslangic else ""),
        "📊 Son 24 saat: " + (_yuzde(gunluk) if gunluk is not None
                             else "ölçülemedi"),
        f"💵 Nakit: {tl(portfoy.nakit_try)}",
        f"💱 Dolara bağlı kısım: {_yuzde(dolar, isaret=False)}",
        "",
        "<b>Pozisyonlar</b> (değer, kâr/zarar)",
    ]
    for pozisyon in sorted(portfoy.pozisyonlar, key=lambda p: -p.deger_try):
        satirlar.append(
            f"• {_ad(veri, pozisyon.sembol)}: {tl(pozisyon.deger_try)} "
            f"({_yuzde(pozisyon.kar_zarar_yuzde)})")
    if portfoy.fiyatlanamayan:
        satirlar.append("⚠️ Fiyatı alınamadı: " + ", ".join(
            _ad(veri, s) for s in portfoy.fiyatlanamayan))
    return "\n".join(satirlar + _belirsizlik_uyarisi(veri))


def komut_risk(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    risk = veri.risk
    satirlar = _basliklar(veri) + [
        f"📉 Yıllık oynaklık: {_yuzde(risk.portfoy_volatilitesi, isaret=False)}",
        f"⬇️ Kötü bir yılda olası düşüş: "
        f"{_yuzde(abs(risk.portfoy_max_drawdown), isaret=False)}",
        "",
        "<b>Para payı · risk payı</b>",
    ]
    # Beta yerine iki sayi yan yana: "paranin %20'si, riskin %37'si" betayi
    # (katki / agirlik) okuyana hesap yaptirmadan anlatir.
    for varlik in sorted(risk.varlik_riskleri, key=lambda v: -v.risk_katkisi):
        if not varlik.agirlik:
            continue
        satirlar.append(
            f"• {_ad(veri, varlik.sembol)}: para "
            f"{_yuzde(varlik.agirlik, isaret=False)} · risk "
            f"{_yuzde(varlik.risk_katkisi, isaret=False)}")

    acik = veri.karar.sinyaller(SEMBOL)
    bastirilan = [s for s in veri.karar.sonuclar.values()
                  if s.tur == SEMBOL and s.yon and not s.acik]
    satirlar.append("")
    if acik:
        satirlar.append("🔔 Risk sınırını aştı, azaltma önerisi: "
                        + ", ".join(_ad(veri, s.ad) for s in acik))
    for s in bastirilan:
        satirlar.append(f"⏸️ {_ad(veri, s.ad)} sınırı aştı ama öneri verilmedi "
                        f"({kacis(s.sebep.lower())})")
    if not acik and not bastirilan:
        satirlar.append("✅ Risk sınırını aşan varlık yok")
    if risk.dislanan:
        satirlar.append("ℹ️ Fiyatı şüpheli, hesaba katılmadı: "
                        + ", ".join(_ad(veri, s) for s in sorted(risk.dislanan)))
    return "\n".join(satirlar)


def komut_durum(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    bayatlar = veri.fiyatlar.bayat_semboller(veri.yapilandirma.bayatlik)
    karar = veri.karar
    satirlar = _basliklar(veri)
    if bayatlar:
        satirlar.append("⚠️ Gecikmeli fiyat: " + ", ".join(
            f"{_ad(veri, s)} ({g} iş günü)" for s, g in sorted(bayatlar.items())))
    else:
        satirlar.append("✅ Fiyatlar güncel")
    if veri.fiyatlar.eksik_semboller:
        satirlar.append("⚠️ Fiyatı gelmeyen: " + ", ".join(
            _ad(veri, s) for s in veri.fiyatlar.eksik_semboller))
    if karar.devre_kesildi:
        satirlar.append(f"🛑 Sistem kendini durdurdu: bugün {karar.gunluk_sayi} "
                        f"öneri çıktı (sınır {karar.gunluk_maks})")
    else:
        satirlar.append(f"⚙️ Sistem çalışıyor (bugün {karar.gunluk_sayi}/"
                        f"{karar.gunluk_maks} öneri)")
    satirlar.append(f"🔔 Açık öneri: {len(karar.sinyaller())}")

    if veri.risk.gozlem_guvenilirligi_dustu:
        satirlar.append(f"⚠️ Oynaklık tahmini zayıf (veri kaybı "
                        f"{_yuzde(veri.risk.gozlem_dususu, isaret=False)})")
    engellenen = veri.maliyet.engellenenler
    if engellenen:
        satirlar.append(f"⚠️ {len(engellenen)} varlıkta maliyet bilgisi eksik, "
                        "öneri yok")
    # Mevduat faizi (hurdle rate) bayatligi BURAYA DA yazilir: gun sonu
    # ozetinde gorunup burada gorunmemesi, iki ayri uyari yuzeyinin klasik
    # boslugu olurdu.
    if not veri.maliyet.risksiz_taze_mi():
        yas = veri.maliyet.risksiz_gun_yasi()
        satirlar.append(
            f"⚠️ Mevduat faizi verisi (hurdle rate) {yas} günlük "
            f"({kacis(veri.maliyet.risksiz_tarih)}); "
            f"{veri.maliyet.risksiz_bayatlik_gun} günden eskisi bayat"
            if yas is not None else
            "⚠️ Mevduat faizi verisinin (hurdle rate) tarihi bilinmiyor")
    return "\n".join(satirlar + _belirsizlik_uyarisi(veri))


def komut_fiyat(baglam: Baglam, arguman: str) -> str:
    """Tek sembol. Arguman SABIT sembol listesiyle karsilastirilir.

    Kullanici metni burada da yalnizca ARANIR: sozlukte yoksa liste doner,
    hicbir sekilde yol, sorgu veya komut olusturmakta kullanilmaz.
    """
    veri = baglam.veri
    istenen = arguman.strip().upper()
    bilinen = {s.upper(): s for s in veri.yapilandirma.varliklar}
    if istenen not in bilinen:
        return ("Bilinmeyen sembol. Şunlardan birini yaz (ör. /fiyat BTC-USD):\n"
                + kacis(", ".join(sorted(veri.yapilandirma.varliklar))))

    sembol = bilinen[istenen]
    fiyat = veri.fiyatlar.son_fiyatlar.get(sembol)
    bayatlar = veri.fiyatlar.bayat_semboller(veri.yapilandirma.bayatlik)
    # Kaynak adi ucgenlemeden turetilir: kripto degerlemesi BTCTurk'ten
    # geliyorsa "yahoo" yazmak, hangi fiyata bakildigini yanlis gosterir.
    ucgen_fiyatlari = veri.fiyatlar.ucgenleme.degerleme_fiyatlari()
    kaynak = "btcturk" if sembol in ucgen_fiyatlari else "yahoo"

    ad = _ad(veri, sembol)
    satirlar = _basliklar(veri) + [
        f"<b>{ad}</b>" + (f" ({kacis(sembol)})" if ad != kacis(sembol) else "")]
    if fiyat is None:
        satirlar.append("⚠️ Fiyat yok: değerleme durduruldu veya veri gelmedi.")
        gerekce = veri.fiyatlar.kurumsal_olay_supheleri.get(sembol)
        if gerekce:
            satirlar.append("Sebep: fiyatta açıklanamayan sıçrama "
                            f"(kurumsal olay şüphesi: {kacis(gerekce)})")
        return "\n".join(satirlar)

    satirlar += [
        f"💲 {tl(fiyat)}",
        f"🕒 {kacis(_gun_adi(veri.veri_zamani))} · kaynak: {kacis(kaynak)}",
    ]
    if sembol in bayatlar:
        satirlar.append(f"⚠️ Fiyat {bayatlar[sembol]} iş günü gecikmeli")
    if not veri.duyarlilik.sinyal_acik_mi(sembol):
        satirlar.append("ℹ️ Bu varlıkta alım önerisi şu an kapalı (ayrıntı /param)")
    return "\n".join(satirlar)


SON_GEREKCE_UZUNLUGU = 90


def komut_son(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    islemler = veri.durum.islemler[-SON_ISLEM_SAYISI:]
    if not islemler:
        return "\n".join(_basliklar(veri) + ["Henüz işlem yok."])

    satirlar = _basliklar(veri) + [f"<b>Son {len(islemler)} işlem</b>"]
    for islem in reversed(islemler):
        simge = "🟩 AL" if islem.yon == "AL" else "🟥 SAT"
        satirlar.append(
            f"• {kacis(_gun_adi(islem.tarih))} {simge} {_ad(veri, islem.sembol)}"
            f" — {tl(islem.tutar_try)}")
        gerekce = islem.gerekce or "kayıtlı gerekçe yok"
        if len(gerekce) > SON_GEREKCE_UZUNLUGU:
            gerekce = gerekce[:SON_GEREKCE_UZUNLUGU].rstrip() + "…"
        satirlar.append(f"  <i>{kacis(gerekce)}</i>")
    return "\n".join(satirlar)


POZISYON_KAYNAGI = {
    GERCEK: "gercek pozisyon",
    HEDEF: "hedef dagilimda alacagi deger",
    YEDEK: "YAML yedegi - portfoy bos",
}


def komut_param(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    duyarlilik = veri.duyarlilik
    satirlar = _basliklar(veri)

    # Referans buyukluk YAZILMAZSA liste hangi dunyayi anlattigini soylemiyor:
    # ayni varlik 1.700 TL'de "pozisyon cok kucuk", 12.000 TL'de "su parametreyi
    # olc" cikar. Sonuc buyukluge bagli, o yuzden buyukluk once gelir.
    satirlar += ["<b>Referans pozisyon buyuklukleri</b>"]
    for sembol, varlik in sorted(duyarlilik.varliklar.items()):
        satirlar.append(
            f"{kacis(sembol)}: {tl(varlik.pozisyon_try)} "
            f"({kacis(POZISYON_KAYNAGI.get(varlik.pozisyon_kaynagi, ''))})")

    # Gereken getiri: formulun her girdisi olculebilir, tahmin yok.
    # Beklenti beyan edilmediyse asil bilgi zaten bu sayidir.
    satirlar += ["", "<b>Gereken yillik getiri</b>",
                 "gereken = TL risksiz + tasima + gidis-donus / planlanan yil"]
    for sembol, varlik in sorted(duyarlilik.varliklar.items()):
        gereken = varlik.gereken_getiri.get(TEMEL)
        if gereken is None:
            continue
        pay = varlik.maliyet_paylari.get(TEMEL)
        beklenti = (oran(varlik.beklenti, 1) if varlik.beklenti_beyan_edildi
                    else "BEYAN YOK")
        satirlar.append(
            f"{kacis(sembol)}: {varlik.planlanan_yil:.0f} yil tutmak icin "
            f"{oran(gereken, 1)} | beklenti {kacis(beklenti)}"
            + (f" | maliyet payi {oran(pay, 1)}" if pay is not None else ""))

    hakimler = duyarlilik.hurdle_hakimler
    if hakimler:
        satirlar += [
            "",
            "Baglayici kisit MALIYET DEGIL, TL risksiz getiri: "
            + kacis(", ".join(hakimler))
            + ". Maliyet optimizasyonu bu varliklarda karari degistirmez."]

    bekleyenler = duyarlilik.beklenti_bekleyenler
    if bekleyenler:
        satirlar += [
            "",
            "BEKLENTI BEYAN EDILMEMIS - alim sinyali yok (azaltma etkilenmez): "
            + kacis(", ".join(bekleyenler))
            + ". varliklar.yaml -> maliyet.tutma icine kendi beklentini yaz."]

    satirlar += ["", "<b>Olculmesi gereken parametreler</b>"]
    gerekenler = duyarlilik.olculmesi_gerekenler
    if not gerekenler:
        satirlar.append("Yok - tahminli kalemlerin hicbiri karari cevirmiyor.")
    else:
        for sira, (parametre, semboller) in enumerate(gerekenler, start=1):
            satirlar.append(
                f"{sira}. {kacis(parametre)} - {len(semboller)} varlik "
                f"({kacis(', '.join(semboller))})")

    ekonomik_olmayanlar = duyarlilik.ekonomik_olmayanlar
    if ekonomik_olmayanlar:
        satirlar += ["", "<b>Ekonomik olmayan pozisyonlar</b>",
                     "Olculecek sey YOK - ya buyut ya cik:"]
        for sembol, varlik in ekonomik_olmayanlar.items():
            if varlik.buyutmek_ise_yarar:
                satirlar.append(
                    f"{kacis(sembol)}: {tl(varlik.pozisyon_try)} -> "
                    f"minimum {tl(varlik.minimum_pozisyon)}")
            else:
                satirlar.append(
                    f"{kacis(sembol)}: {tl(varlik.pozisyon_try)} - maliyet "
                    "tabani esigin ustunde, buyutmek ise yaramaz")

    tasima_belirsizleri = duyarlilik.tasima_belirsizleri
    if tasima_belirsizleri:
        satirlar += ["", "<b>Tasima maliyeti belirsizligi</b>",
                     "Basabas suresi bir senaryoda planlanani asiyor:"]
        satirlar += [f"- {kacis(parametre)}: {kacis(', '.join(semboller))}"
                     for parametre, semboller in sorted(tasima_belirsizleri.items())]

    # Varlik basina kapsam dokumu. "Karar dayanikli" satiri tek basina
    # hangi varsayimlarin SINANDIGINI gizler; sinanmamis bir tahminle acilan
    # sinyali goren tek yer bu liste.
    satirlar += ["", "<b>Tahmin kapsami (varlik basina)</b>"]
    for sembol, varlik in sorted(duyarlilik.varliklar.items()):
        if not varlik.blokaji_kaldiran:
            continue
        isaret = " DOGRULANMAMIS ACILIM" if varlik.dogrulanmamis_acilim else ""
        satirlar.append(
            f"{kacis(sembol)}:{isaret}"
            f"\n  blokaji kaldiran: {kacis(', '.join(varlik.blokaji_kaldiran))}"
            f"\n  sinandi: {kacis(', '.join(varlik.kapsam_ici_parametreler)) or '-'}"
            f"\n  SINANMADI: "
            f"{kacis(', '.join(varlik.kapsam_disi_parametreler)) or '-'}")

    if duyarlilik.dogrulanmamis_acilimlar:
        satirlar += [
            "",
            "UYARI - DOGRULANMAMIS ACILIM: bu varliklarin sinyalini hicbir "
            "duyarlilik boyutundan gecmemis bir tahmin aciyor. Ya parametreyi "
            "olc ya da onu kapsayan boyutu calistir."]

    engellenen = veri.maliyet.eksik_kalem_ozeti
    if engellenen:
        satirlar += ["", "<b>Hic tahmini olmayan (bloklu) kalemler</b>"]
        satirlar += [f"- {kacis(kalem)}: {len(semboller)} varlik"
                     for kalem, semboller in engellenen.items()]
    return "\n".join(satirlar)


def komut_yardim(baglam: Baglam, arguman: str) -> str:
    return "\n".join([
        f"<b>📊 {BASLIK} botu</b> — yalnızca bilgi verir, işlem yapmaz.",
        "",
        "/portfoy — toplam değer ve pozisyonlar",
        "/risk — risk hangi varlıkta toplanıyor",
        "/durum — veriler güncel mi, sistem çalışıyor mu",
        "/fiyat SEMBOL — tek varlığın fiyatı (ör. /fiyat BTC-USD)",
        "/son — son 5 işlem",
        "/haber — günün başlıkları",
        "/param — teknik: maliyet parametreleri",
        "/yardim — bu liste",
    ])


def _haberleri_sirala(haberler: list, yapilandirma, env: dict[str, str]):
    """Basliklari portfoye gore siralar. Doner: (haberler, degerlendirmeler, uyari).

    Model kapali veya cagri dusukse haberler DEGISMEDEN doner - besleme
    sirasi eskiden beri kullanilan sira, yani duserken kaybedilen sey
    siralamanin iyilesmesi, haberin kendisi degil.
    """
    if not yapilandirma.llm.kullanilabilir:
        return haberler, {}, ""
    adlar = {s: v.ad for s, v in yapilandirma.varliklar.items()}
    return haberleri_degerlendir(haberler, adlar, yapilandirma.llm, env)


def komut_haber(baglam: Baglam, arguman: str) -> str:
    """Guncel basliklar. Fiyat verisi CEKMEZ - haber fiyattan bagimsizdir.

    `baglam.veri` kasitli olarak kullanilmiyor: Yahoo'ya gitmek bu komut icin
    tamamen gereksiz Actions dakikasi yakardi. Yalnizca yapilandirma okunur.
    """
    yapilandirma = yapilandirmayi_oku()
    ayar = yapilandirma.haber
    if not ayar.beslemeler:
        return ("<b>📰 Haberler</b>\n\n"
                "Hic besleme tanimli degil. <code>varliklar.yaml -> "
                "veri_kaynaklari.haber.beslemeler</code> altina ekle.")

    bugun = (simdi_utc() + TR_OFSET).date()
    haberler, uyarilar = haberleri_topla(
        ayar.beslemeler, bugun=bugun, azami_gun=ayar.azami_gun,
        besleme_basina=ayar.besleme_basina)
    haberler, degerlendirmeler, uyari = _haberleri_sirala(
        haberler, yapilandirma, baglam.env)
    return haber_mesaji(haberler, uyarilar + ([uyari] if uyari else []),
                        bugun, degerlendirmeler)


KOMUTLAR = {
    "/portfoy": komut_portfoy,
    "/risk": komut_risk,
    "/durum": komut_durum,
    "/fiyat": komut_fiyat,
    "/son": komut_son,
    "/param": komut_param,
    "/haber": komut_haber,
    "/yardim": komut_yardim,
}


# --------------------------------------------------------------------------
# Yetki ve yonlendirme
# --------------------------------------------------------------------------

def izinli_kimlikler(env: dict[str, str]) -> set[str]:
    """Virgulle ayrilmis izinli chat id listesi.

    Tanimsizsa BOS KUME doner ve bot hicbir mesaja cevap vermez. Bilincli:
    "ayar yoksa herkese acik" bir bota, yanlis yapilandirmanin bedeli
    portfoyun yabancilara acilmasi olurdu.
    """
    ham = env.get("TELEGRAM_IZINLI_CHAT_ID", "")
    return {parca.strip() for parca in ham.split(",") if parca.strip()}


def _komutu_ayikla(metin: str) -> tuple[str, str]:
    """Ham metinden (komut, arguman). Bot adi soneki (/risk@bot) temizlenir."""
    parcalar = metin.strip().split(maxsplit=1)
    if not parcalar:
        return "", ""
    komut = parcalar[0].split("@", 1)[0].lower()
    return komut, (parcalar[1] if len(parcalar) > 1 else "")


def cevabi_uret(metin: str, baglam: Baglam) -> str:
    """Komutu SABIT sozlukte arar. Kullanici metni asla calistirilmaz.

    Beklenmeyen hata kullaniciya tek cumleyle doner: istisna metni dosya yolu
    ve sembol adi tasiyabilir, ikisi de mesaja girmemeli.
    """
    komut, arguman = _komutu_ayikla(metin)
    islev = KOMUTLAR.get(komut)
    if islev is None:
        return ("Taninmayan komut.\n\n" + komut_yardim(baglam, ""))
    try:
        return islev(baglam, arguman)
    except Exception as hata:                     # noqa: BLE001
        print(f"HATA - {komut}: {type(hata).__name__}", file=sys.stderr)
        return "Veri su an okunamadi. Bir sonraki kosuda tekrar dene."


# --------------------------------------------------------------------------
# Offset defteri
# --------------------------------------------------------------------------

def offset_oku(dosya: Path = OFFSET_DOSYASI) -> int:
    """Son islenen update_id. Dosya yoksa veya bozuksa 0.

    Bozuk dosyada 0 donmek guvenli taraf: en fazla Telegram'in elinde tuttugu
    guncellemeler bir kez daha islenir. Ters yonde bir tahmin yapmak
    (ornegin cok buyuk bir offset) mesajlari kalici olarak dusururdu.
    """
    if not dosya.exists():
        return 0
    try:
        return int(dosya.read_text(encoding="utf-8").strip() or 0)
    except ValueError:
        print("UYARI - offset dosyasi cozulemedi, sifirdan basliyor.",
              file=sys.stderr)
        return 0


def offset_yaz(deger: int, dosya: Path = OFFSET_DOSYASI) -> bool:
    """Doner: dosya DEGISTI mi. False ise workflow commit atmamali.

    Her kosuda yazip commit etmek yarim saatte bir bos commit demek - repo
    gecmisi okunmaz olur ve gercek degisiklikler arada kaybolur.
    """
    if offset_oku(dosya) == deger:
        return False
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(f"{deger}\n", encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# Telegram tasima
# --------------------------------------------------------------------------

class WebhookAktif(Exception):
    """getUpdates 409 dondu: webhook kurulu, yoklama yoluna gerek yok."""


def guncellemeleri_getir(token: str, offset: int) -> list[dict]:
    yanit = requests.get(
        f"{API_KOKU}/bot{token}/getUpdates",
        params={"offset": offset + 1, "timeout": 0, "allowed_updates": '["message"]'},
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code == 409:
        # Webhook aktif. Telegram getUpdates ile webhook'u ayni anda
        # kullandirmaz. Bu HATA DEGIL, dogru yapilandirmanin isareti:
        # mesajlar Worker uzerinden dispatch olarak geliyor demektir.
        raise WebhookAktif()
    if not yanit.ok:
        # Token URL yolunda - ham hata metnini yukari birakmak sizinti olur.
        raise RuntimeError(f"getUpdates reddedildi (HTTP {yanit.status_code})")
    return yanit.json().get("result") or []


def cevap_gonder(token: str, chat_id: str, metin: str) -> None:
    for parca in bol(metin):
        yanit = requests.post(
            f"{API_KOKU}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": parca, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=ZAMAN_ASIMI,
        )
        if not yanit.ok:
            raise RuntimeError(f"sendMessage reddedildi (HTTP {yanit.status_code})")


# --------------------------------------------------------------------------
# Kosu
# --------------------------------------------------------------------------

def guncellemeleri_isle(guncellemeler: list[dict], izinliler: set[str],
                        baglam: Baglam, gonder) -> tuple[int, int]:
    """Doner: (son update_id, cevaplanan mesaj sayisi).

    Offset izinsiz mesajlarda DA ilerler: ilerlemezse tek bir yabanci mesaj
    kuyrugu kalici olarak tikar ve sahibinin komutlari hic islenmez.
    """
    son_id = 0
    cevaplanan = 0
    for guncelleme in guncellemeler:
        son_id = max(son_id, int(guncelleme.get("update_id", 0)))
        mesaj = guncelleme.get("message") or {}
        chat_id = str((mesaj.get("chat") or {}).get("id", ""))
        metin = mesaj.get("text") or ""
        if not metin:
            continue
        if chat_id not in izinliler:
            # Cevap YOK - sessiz kalmak botun varligini dogrulamamak demektir.
            print(f"UYARI - izinsiz chat id reddedildi: {chat_id}", file=sys.stderr)
            continue
        gonder(chat_id, cevabi_uret(metin, baglam))
        cevaplanan += 1
    return son_id, cevaplanan


HABER_DIZINI = PROJE_DIZINI / "haberler"


def haber_ayrintisi_uret(env: dict[str, str] | None = None,
                         bugun=None) -> Path | None:
    """Haber ayrinti dosyasini diske yazar ve yolunu doner.

    KOMUT DEGIL, tasima yardimcisi. Komutlar saf kalmali - `komut_haber`
    yalnizca metin uretir. Bu ayrim `test_bot_yazma_islemi_yok` tarafindan
    korunuyor ve sebebi mimari: komut govdesi diske dokunmaya baslarsa
    "salt okunur bot" garantisi her yeni komutta yeniden tartisilir.
    """
    yapilandirma = yapilandirmayi_oku()
    ayar = yapilandirma.haber
    if not ayar.beslemeler:
        return None
    bugun = bugun or (simdi_utc() + TR_OFSET).date()
    haberler, uyarilar = haberleri_topla(
        ayar.beslemeler, bugun=bugun, azami_gun=ayar.azami_gun,
        besleme_basina=ayar.besleme_basina)
    haberler, degerlendirmeler, uyari = _haberleri_sirala(
        haberler, yapilandirma, env if env is not None else env_oku())
    HABER_DIZINI.mkdir(parents=True, exist_ok=True)
    dosya = HABER_DIZINI / f"{bugun}.md"
    dosya.write_text(
        haber_dosyasi(haberler, uyarilar + ([uyari] if uyari else []),
                      bugun, degerlendirmeler), encoding="utf-8")
    return dosya


def tek_komutu_cevapla(komut: str, chat_id: str,
                       env: dict[str, str] | None = None,
                       gonder=None, yukleyici=None) -> int:
    """Webhook yolu: komut Telegram'dan DEGIL, dispatch yukunden gelir.

    Neden ayri yol: Telegram'da webhook aktifken `getUpdates` HTTP 409 doner -
    ikisi ayni anda KULLANILAMAZ. Webhook'a gecince yoklama yolu fiilen
    kapaniyor, o yuzden komutun govdesi Worker tarafindan tasiniyor.

    Offset defteri bu yolda KULLANILMAZ ve gerekmez: her mesaj icin tam bir
    dispatch atiliyor, yani "hangi mesaji islemistim" sorusu yok. Tekrar
    gonderim riski de yok - Worker her zaman HTTP 200 doner, Telegram
    yeniden denemez.
    """
    env = env if env is not None else env_oku()
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_TOKEN")
    if not token:
        print("HATA - TELEGRAM_BOT_TOKEN yok.", file=sys.stderr)
        return 1

    # Worker de suzuyor ama burada TEKRAR suzuluyor: Worker atlanip dispatch
    # dogrudan atilabilir (repo yazma yetkisi olan herkes atabilir), yani
    # yetki kontrolu tek bir katmana birakilamaz.
    izinliler = izinli_kimlikler(env)
    if not izinliler:
        print("HATA - TELEGRAM_IZINLI_CHAT_ID tanimli degil, bot cevap vermez.",
              file=sys.stderr)
        return 1
    if str(chat_id) not in izinliler:
        print(f"UYARI - izinsiz chat id reddedildi: {chat_id}", file=sys.stderr)
        return 0

    gonder = gonder or (lambda hedef, metin: cevap_gonder(token, hedef, metin))
    try:
        gonder(str(chat_id), cevabi_uret(komut, Baglam(env=env, yukleyici=yukleyici)))
    except Exception as hata:                     # noqa: BLE001
        print(f"HATA - cevap gonderilemedi: {type(hata).__name__}", file=sys.stderr)
        return 1

    if komut.split()[0].split("@")[0] == "/haber":
        # Ayrinti dosyasi metin cevabindan SONRA gider ve basarisizligi
        # komutu dusurmez: ozet asil cikti, dosya kolaylik. Ikisini birbirine
        # baglamak, ek yuzunden haberi tumden kaybettirirdi.
        try:
            dosya = haber_ayrintisi_uret(env)
            if dosya is not None:
                dosya_gonder(dosya, f"Haber ayrintisi - {dosya.stem}", env)
        except Exception as hata:                 # noqa: BLE001
            print(f"UYARI - haber dosyasi eklenemedi: {type(hata).__name__}",
                  file=sys.stderr)
    print(f"Webhook komutu cevaplandi: {komut[:32]}")
    return 0


def calistir(env: dict[str, str] | None = None, getir=None, gonder=None,
             offset_dosyasi: Path = OFFSET_DOSYASI, yukleyici=None,
             ayarlar: BotAyarlari | None = None, simdi=None,
             pencereyi_atla: bool = False) -> int:
    """Bir kosu. Doner: surec cikis kodu.

    Ag katmani enjekte edilir (`kaynaklar.py` ile ayni kalip) - testler sahte
    getir/gonder gecirir ve paket tamamen cevrimdisi kalir.

    `pencereyi_atla`: kosu penceresi/aralik kapisini gec. Webhook ile gelen
    kosular icin ZORUNLU - o kosu zaten gelmis bir mesaj yuzunden basladi,
    "sirasi degil" diye kesmek mesaji cevapsiz birakirdi. Kapi yalnizca
    ZAMANLANMIS kosularin bosa dakika yakmasini engellemek icindir.
    """
    ayarlar = ayarlar if ayarlar is not None else bot_ayarlarini_oku()
    if not pencereyi_atla and not ayarlar.kosulacak_mi(simdi or simdi_utc()):
        print("Kosu penceresi disinda, cikiliyor.")
        return 0

    env = env if env is not None else env_oku()
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_TOKEN")
    if not token:
        print("HATA - TELEGRAM_BOT_TOKEN yok.", file=sys.stderr)
        return 1

    izinliler = izinli_kimlikler(env)
    if not izinliler:
        print("HATA - TELEGRAM_IZINLI_CHAT_ID tanimli degil, bot cevap vermez.",
              file=sys.stderr)
        return 1

    offset = offset_oku(offset_dosyasi)
    getir = getir or (lambda ofs: guncellemeleri_getir(token, ofs))
    gonder = gonder or (lambda chat_id, metin: cevap_gonder(token, chat_id, metin))

    try:
        guncellemeler = getir(offset)
    except WebhookAktif:
        # BASARI olarak cikilir. Bu kosu yalnizca emniyet agi croni; webhook
        # calisiyorsa yapacak isi yoktur. Hata sayilsaydi webhook kurulu olan
        # her sistemde gunluk kirmizi kosular birikirdi ve gercek bir ariza
        # o gurultunun icinde kaybolurdu.
        print("Webhook aktif - yoklamaya gerek yok, cikiliyor.")
        return 0
    except Exception as hata:                     # noqa: BLE001
        print(f"HATA - getUpdates: {type(hata).__name__}", file=sys.stderr)
        return 1

    if not guncellemeler:
        print("Bekleyen mesaj yok.")
        return 0

    baglam = Baglam(env=env, yukleyici=yukleyici)
    son_id, cevaplanan = guncellemeleri_isle(guncellemeler, izinliler, baglam, gonder)
    degisti = offset_yaz(son_id, offset_dosyasi) if son_id else False
    print(f"{len(guncellemeler)} guncelleme, {cevaplanan} cevap. "
          f"offset={'yazildi' if degisti else 'degismedi'}")
    return 0


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Telegram sorgu botu - salt okunur")
    ayristirici.add_argument(
        "--zorla", action="store_true",
        help="kosu penceresi/aralik kapisini atla (elle tetiklenen kosu)")
    ayristirici.add_argument(
        "--komut", default="",
        help="webhook yolu: cevaplanacak komut (getUpdates kullanilmaz)")
    ayristirici.add_argument(
        "--chat-id", default="", help="webhook yolu: cevabin gidecegi chat")
    argumanlar = ayristirici.parse_args()

    if argumanlar.komut:
        if not argumanlar.chat_id:
            print("HATA - --komut ile --chat-id zorunlu.", file=sys.stderr)
            return 1
        return tek_komutu_cevapla(argumanlar.komut, argumanlar.chat_id)
    return calistir(pencereyi_atla=argumanlar.zorla)


if __name__ == "__main__":
    raise SystemExit(main())
