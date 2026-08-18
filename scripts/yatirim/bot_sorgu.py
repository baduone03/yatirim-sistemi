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

import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bicim import oran, tl, yuzde  # noqa: E402
from bildirim import bol  # noqa: E402
from config import PROJE_DIZINI, TR_OFSET, yapilandirmayi_oku  # noqa: E402
from duyarlilik import duyarliligi_olc  # noqa: E402
from fetch import fiyatlari_getir, maliyet_modelini_coz  # noqa: E402
from kurumsal_olay import bilinen_olay_anahtarlari, olaylari_oku  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from mesaj import kacis  # noqa: E402
from notify import API_KOKU, ZAMAN_ASIMI, env_oku  # noqa: E402
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

BASLIK = "SIMULASYON"
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
        {p.sembol: p.deger_try for p in portfoy.pozisyonlar}, fiyatlar.usdtry)
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
    return [f"<b>{BASLIK}</b> - veri gunu {kacis(veri.veri_zamani)}", ""]


def _belirsizlik_uyarisi(veri: Veri) -> list[str]:
    belirsizler = veri.duyarlilik.belirsizler
    if not belirsizler:
        return []
    parametreler = sorted({p for v in belirsizler.values()
                           for p in v.belirsiz_parametreler})
    return ["", "UYARI - parametre belirsizligi: "
            + kacis(", ".join(parametreler))
            + f" ({len(belirsizler)} varlikta sinyal bastirildi)."]


def komut_portfoy(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    portfoy, durum = veri.portfoy, veri.durum
    baslangic = durum.baslangic_nakit_try
    net = portfoy.toplam_deger_try - baslangic
    # Saf FIYAT etkisi: pozisyonlar sabit tutulup fiyatlar geri alinir.
    gunluk = degisim_24s(portfoy, veri.fiyatlar)

    satirlar = _basliklar(veri) + ["<b>Pozisyonlar</b>"]
    for pozisyon in sorted(portfoy.pozisyonlar, key=lambda p: -p.deger_try):
        satirlar.append(
            f"{kacis(pozisyon.sembol)}: {tl(pozisyon.deger_try)} "
            f"({yuzde(pozisyon.kar_zarar_yuzde)})")
    if portfoy.fiyatlanamayan:
        satirlar.append("Fiyatlanamayan: "
                        + kacis(", ".join(portfoy.fiyatlanamayan)))

    satirlar += [
        "",
        f"Toplam: {tl(portfoy.toplam_deger_try)}",
        f"Nakit: {tl(portfoy.nakit_try)}",
        f"24 saat: {yuzde(gunluk) if gunluk is not None else 'veri yok'}",
        f"Baslangictan: {tl(net)} ({yuzde(net / baslangic if baslangic else 0.0)})",
        f"Kur maruziyeti: {oran(kur_maruziyeti(portfoy, veri.yapilandirma.varliklar))}",
    ]
    return "\n".join(satirlar + _belirsizlik_uyarisi(veri))


def komut_risk(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    risk = veri.risk
    satirlar = _basliklar(veri) + [
        f"Portfoy volatilitesi: {oran(risk.portfoy_volatilitesi)}",
        f"Max drawdown: {oran(risk.portfoy_max_drawdown)}",
        f"Pencere: {risk.gozlem_sayisi} islem gunu",
        "",
        "<b>Risk katkisi / beta</b>",
    ]
    for varlik in risk.varlik_riskleri:
        satirlar.append(
            f"{kacis(varlik.sembol)}: katki {oran(varlik.risk_katkisi)}, "
            f"beta {varlik.beta:.2f}")

    ihlaller = [s for s in veri.karar.sonuclar.values()
                if s.tur == SEMBOL and s.yon and not s.acik]
    acik = veri.karar.sinyaller(SEMBOL)
    satirlar.append("")
    if acik:
        satirlar.append("Esik ihlali (SINYAL ACIK): "
                        + kacis(", ".join(s.ad for s in acik)))
    if ihlaller:
        satirlar.append("Esik asildi ama bastirildi:")
        satirlar += [f"  {kacis(s.ad)} - {kacis(s.etiket)}" for s in ihlaller]
    if not acik and not ihlaller:
        satirlar.append("Esik ihlali yok.")
    if risk.dislanan:
        satirlar.append("Risk hesabi disi: " + kacis(", ".join(sorted(risk.dislanan))))
    return "\n".join(satirlar + _belirsizlik_uyarisi(veri))


def komut_durum(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    bayatlar = veri.fiyatlar.bayat_semboller(veri.yapilandirma.bayatlik)
    karar = veri.karar
    satirlar = _basliklar(veri) + [
        f"Fiyat verisi gunu: {kacis(veri.fiyatlar.son_tarih)}",
        f"Bayat sembol: "
        + (kacis(", ".join(f"{s} ({g} islem gunu)"
                           for s, g in sorted(bayatlar.items())))
           if bayatlar else "yok"),
        f"Fiyat gelmeyen: "
        + (kacis(", ".join(veri.fiyatlar.eksik_semboller))
           if veri.fiyatlar.eksik_semboller else "yok"),
        "",
        f"Devre kesici: {'KESILDI' if karar.devre_kesildi else 'acik'} "
        f"({karar.gunluk_sayi}/{karar.gunluk_maks} sinyal)",
        f"Acik sinyal: {len(karar.sinyaller())}",
    ]
    if veri.risk.gozlem_guvenilirligi_dustu:
        satirlar.append(
            f"UYARI - volatilite tahmini guvenilirligi dustu "
            f"(veri kaybi {oran(veri.risk.gozlem_dususu)}).")
    engellenen = veri.maliyet.engellenenler
    if engellenen:
        satirlar.append(f"Eksik maliyet: {len(engellenen)} varlikta sinyal yok.")
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
        return ("Bilinmeyen sembol. Tanimli semboller:\n"
                + kacis(", ".join(sorted(veri.yapilandirma.varliklar))))

    sembol = bilinen[istenen]
    fiyat = veri.fiyatlar.son_fiyatlar.get(sembol)
    bayatlar = veri.fiyatlar.bayat_semboller(veri.yapilandirma.bayatlik)
    # Kaynak adi ucgenlemeden turetilir: kripto degerlemesi BTCTurk'ten
    # geliyorsa "yahoo" yazmak, hangi fiyata bakildigini yanlis gosterir.
    ucgen_fiyatlari = veri.fiyatlar.ucgenleme.degerleme_fiyatlari()
    kaynak = "btcturk" if sembol in ucgen_fiyatlari else "yahoo"

    satirlar = _basliklar(veri) + [f"<b>{kacis(sembol)}</b>"]
    if fiyat is None:
        satirlar.append("Fiyat YOK - degerleme durduruldu veya veri gelmedi.")
        gerekce = veri.fiyatlar.kurumsal_olay_supheleri.get(sembol)
        if gerekce:
            satirlar.append("Sebep: kurumsal olay suphesi - " + kacis(gerekce))
        return "\n".join(satirlar)

    satirlar += [
        f"Fiyat: {tl(fiyat)}",
        f"Veri zamani: {kacis(veri.veri_zamani)}",
        f"Kaynak: {kacis(kaynak)}",
        f"Bayat: {'EVET - ' + str(bayatlar[sembol]) + ' islem gunu' if sembol in bayatlar else 'hayir'}",
    ]
    if not veri.duyarlilik.sinyal_acik_mi(sembol):
        satirlar.append("Sinyal kapali: " + kacis(veri.duyarlilik.etiket(sembol)))
    return "\n".join(satirlar)


def komut_son(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    islemler = veri.durum.islemler[-SON_ISLEM_SAYISI:]
    if not islemler:
        return "\n".join(_basliklar(veri) + ["Henuz islem yok."])

    satirlar = _basliklar(veri) + [f"<b>Son {len(islemler)} simule islem</b>"]
    for islem in reversed(islemler):
        tetik = islem.gerekce or "kayitli tetikleyici yok"
        satirlar.append(
            f"{kacis(islem.tarih)} {kacis(islem.yon)} {kacis(islem.sembol)} "
            f"{tl(islem.tutar_try)} - {kacis(tetik)}")
    return "\n".join(satirlar)


def komut_param(baglam: Baglam, arguman: str) -> str:
    veri = baglam.veri
    gerekenler = veri.duyarlilik.olculmesi_gerekenler
    satirlar = _basliklar(veri) + ["<b>Olculmesi gereken parametreler</b>"]
    if not gerekenler:
        satirlar.append("Yok - tahminli kalemlerin hicbiri karari cevirmiyor.")
    else:
        for sira, (parametre, semboller) in enumerate(gerekenler, start=1):
            satirlar.append(
                f"{sira}. {kacis(parametre)} - {len(semboller)} varlik "
                f"({kacis(', '.join(semboller))})")
    yutanlar = veri.duyarlilik.maliyet_yutanlar
    if yutanlar:
        satirlar += ["", "Maliyet sapmayi yutuyor (olculecek sey yok): "
                     + kacis(", ".join(sorted(yutanlar)))]
    engellenen = veri.maliyet.eksik_kalem_ozeti
    if engellenen:
        satirlar += ["", "<b>Hic tahmini olmayan (bloklu) kalemler</b>"]
        satirlar += [f"- {kacis(kalem)}: {len(semboller)} varlik"
                     for kalem, semboller in engellenen.items()]
    return "\n".join(satirlar)


def komut_yardim(baglam: Baglam, arguman: str) -> str:
    return "\n".join([
        f"<b>{BASLIK} sorgu botu</b> - salt okunur, islem acmaz.",
        "",
        "/portfoy - pozisyonlar, deger, K/Z, nakit, kur maruziyeti",
        "/risk - beta, risk katkisi, esik ihlalleri",
        "/durum - veri tazeligi, uyarilar, devre kesici",
        "/fiyat SEMBOL - fiyat, veri zamani, kaynak, bayatlik",
        "/son - son 5 simule islem",
        "/param - olculmesi gereken parametreler",
        "/yardim - bu liste",
    ])


KOMUTLAR = {
    "/portfoy": komut_portfoy,
    "/risk": komut_risk,
    "/durum": komut_durum,
    "/fiyat": komut_fiyat,
    "/son": komut_son,
    "/param": komut_param,
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

def guncellemeleri_getir(token: str, offset: int) -> list[dict]:
    yanit = requests.get(
        f"{API_KOKU}/bot{token}/getUpdates",
        params={"offset": offset + 1, "timeout": 0, "allowed_updates": '["message"]'},
        timeout=ZAMAN_ASIMI,
    )
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


def calistir(env: dict[str, str] | None = None, getir=None, gonder=None,
             offset_dosyasi: Path = OFFSET_DOSYASI, yukleyici=None,
             ayarlar: BotAyarlari | None = None, simdi=None) -> int:
    """Bir kosu. Doner: surec cikis kodu.

    Ag katmani enjekte edilir (`kaynaklar.py` ile ayni kalip) - testler sahte
    getir/gonder gecirir ve paket tamamen cevrimdisi kalir.
    """
    ayarlar = ayarlar if ayarlar is not None else bot_ayarlarini_oku()
    if not ayarlar.kosulacak_mi(simdi or simdi_utc()):
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
    return calistir()


if __name__ == "__main__":
    raise SystemExit(main())
