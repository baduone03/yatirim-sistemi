"""Telegram sorgu botu testleri - tamami CEVRIMDISI.

Ag katmani (`getir` / `gonder`) ve veri yukleyici enjekte edilir; hicbir test
Telegram'a veya Yahoo'ya cikmaz. Guvenlik kurallari burada dogrulanir cunku
bir sorgu botunun en pahali hatasi sessiz olanidir: yanlis kisiye cevap
vermek, hata metninde yol sizdirmak, ayni komutu iki kez isletmek.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bot_sorgu  # noqa: E402
from bot_sorgu import (  # noqa: E402
    KOMUTLAR,
    Baglam,
    BotAyarlari,
    cevabi_uret,
    guncellemeleri_isle,
    izinli_kimlikler,
    offset_oku,
    offset_yaz,
)
from mesaj import kacis  # noqa: E402

import numpy as np
import pandas as pd

from config import (  # noqa: E402
    Ayarlar,
    Bekleme,
    DevreKesici,
    Esikler,
    Varlik,
    Yapilandirma,
)
from duyarlilik import duyarliligi_olc  # noqa: E402
from fetch import FiyatVerisi  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from maliyet import modeli_kur  # noqa: E402
from portfolio import portfoyu_ledgerdan_hesapla, sinif_sapmalari  # noqa: E402
from risk import riski_hesapla  # noqa: E402
from sinyal import SinyalGecmisi, kararlari_uret  # noqa: E402


def defter_durumu(islemler: str, nakit: float = 10000.0):
    """islemler.yaml govdesinden LedgerDurumu - test_yatirim ile ayni kalip."""
    dosya = Path(tempfile.mkdtemp()) / "islemler.yaml"
    dosya.write_text(
        f"baslangic_nakit_try: {nakit}\nkomisyon_orani: 0.0\n"
        f"baslangic_tarihi: 2026-06-01\nislemler:\n{islemler}",
        encoding="utf-8")
    return durumu_hesapla(*islemleri_oku(dosya)[:3], [],
                          baslangic_tarihi="2026-06-01", bugun="2026-08-19")



IZINLI = "123456"
YABANCI = "999999"
ENV = {"TELEGRAM_BOT_TOKEN": "gizli-token",
       "TELEGRAM_IZINLI_CHAT_ID": IZINLI}
AYARLAR_ACIK = BotAyarlari(aralik_dakika=30, baslangic_saat=0, bitis_saat=0)
AN = datetime(2026, 8, 19, 12, 3, tzinfo=timezone.utc)


def gecici_dosya(ad: str = "bot_offset.txt") -> Path:
    return Path(tempfile.mkdtemp()) / ad


def guncelleme(update_id: int, chat_id: str, metin: str) -> dict:
    return {"update_id": update_id,
            "message": {"chat": {"id": int(chat_id)}, "text": metin}}


class SahteGonderici:
    def __init__(self):
        self.gonderilenler: list[tuple[str, str]] = []

    def __call__(self, chat_id: str, metin: str) -> None:
        self.gonderilenler.append((chat_id, metin))


class IzinTesti(unittest.TestCase):
    """Yalnizca izinli chat id cevap alir."""

    def test_bot_izinsiz_chat_id_reddediliyor(self):
        gonderici = SahteGonderici()
        son_id, cevaplanan = guncellemeleri_isle(
            [guncelleme(11, YABANCI, "/portfoy"),
             guncelleme(12, YABANCI, "/yardim")],
            izinli_kimlikler(ENV), Baglam(env=ENV), gonderici)

        # Hicbir cevap gitmedi - sessiz kalmak botun varligini dogrulamamak.
        self.assertEqual(gonderici.gonderilenler, [])
        self.assertEqual(cevaplanan, 0)
        # Offset YINE de ilerledi: ilerlemezse tek yabanci mesaj kuyrugu tikar
        # ve sahibinin komutlari hic islenmez.
        self.assertEqual(son_id, 12)

    def test_izinli_chat_cevap_alir(self):
        gonderici = SahteGonderici()
        guncellemeleri_isle([guncelleme(5, IZINLI, "/yardim")],
                            izinli_kimlikler(ENV), Baglam(env=ENV), gonderici)
        self.assertEqual(len(gonderici.gonderilenler), 1)
        self.assertEqual(gonderici.gonderilenler[0][0], IZINLI)

    def test_izinli_liste_bos_ise_hicbir_cevap_yok(self):
        """Ayar yoksa "herkese acik" degil, "kimseye kapali"."""
        self.assertEqual(izinli_kimlikler({}), set())
        gonderici = SahteGonderici()
        guncellemeleri_isle([guncelleme(1, IZINLI, "/yardim")],
                            izinli_kimlikler({}), Baglam(), gonderici)
        self.assertEqual(gonderici.gonderilenler, [])

    def test_birden_fazla_izinli_kimlik(self):
        self.assertEqual(izinli_kimlikler({"TELEGRAM_IZINLI_CHAT_ID": "1, 2 ,3"}),
                         {"1", "2", "3"})


class OffsetTesti(unittest.TestCase):
    """getUpdates ayni guncellemeyi offset ilerleyene kadar tekrar verir."""

    def test_bot_offset_mukerrer_islemiyor(self):
        dosya = gecici_dosya()
        gonderici = SahteGonderici()
        cagrilan_offsetler: list[int] = []

        def getir(offset):
            cagrilan_offsetler.append(offset)
            # Ilk kosuda iki mesaj, ikinci kosuda (offset ilerledi) hicbiri.
            return [guncelleme(41, IZINLI, "/yardim"),
                    guncelleme(42, IZINLI, "/yardim")] if offset == 0 else []

        ilk = bot_sorgu.calistir(env=ENV, getir=getir, gonder=gonderici,
                                 offset_dosyasi=dosya, ayarlar=AYARLAR_ACIK,
                                 simdi=AN)
        ikinci = bot_sorgu.calistir(env=ENV, getir=getir, gonder=gonderici,
                                    offset_dosyasi=dosya, ayarlar=AYARLAR_ACIK,
                                    simdi=AN)

        self.assertEqual((ilk, ikinci), (0, 0))
        self.assertEqual(cagrilan_offsetler, [0, 42])
        # Iki mesaj bir kez cevaplandi, ikinci kosuda tekrar YOK.
        self.assertEqual(len(gonderici.gonderilenler), 2)
        self.assertEqual(offset_oku(dosya), 42)

    def test_bot_offset_degismediyse_commit_yok(self):
        """offset_yaz -> False ise workflow commit atmamali.

        Her kosuda yazip commit etmek yarim saatte bir bos commit demek;
        repo gecmisi okunmaz olur ve gercek degisiklikler arada kaybolur.
        """
        dosya = gecici_dosya()
        self.assertTrue(offset_yaz(7, dosya))       # ilk yazim - degisti
        self.assertFalse(offset_yaz(7, dosya))      # ayni deger - degismedi
        self.assertTrue(offset_yaz(8, dosya))       # ilerledi - degisti
        self.assertEqual(offset_oku(dosya), 8)

    def test_mesaj_yoksa_offset_dosyasina_dokunulmaz(self):
        dosya = gecici_dosya()
        sonuc = bot_sorgu.calistir(env=ENV, getir=lambda ofs: [],
                                   gonder=SahteGonderici(), offset_dosyasi=dosya,
                                   ayarlar=AYARLAR_ACIK, simdi=AN)
        self.assertEqual(sonuc, 0)
        self.assertFalse(dosya.exists())

    def test_bozuk_offset_sifirdan_baslar(self):
        """Ileri bir tahmin yapmak mesajlari KALICI olarak dusururdu."""
        dosya = gecici_dosya()
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text("bozuk", encoding="utf-8")
        self.assertEqual(offset_oku(dosya), 0)


class KomutTesti(unittest.TestCase):
    """Kullanici metni SABIT sozlukte aranir, asla calistirilmaz."""

    def test_bot_taninmayan_komut_bilgi_sizdirmiyor(self):
        cevap = cevabi_uret("/silsupurge", Baglam(env=ENV))
        self.assertIn("Taninmayan komut", cevap)
        self.assertIn("/yardim", cevap)
        for sizinti in ("Traceback", "gizli-token", "ikinci-beyin",
                        "C:\\", "/home/", ".env", "bot_sorgu.py"):
            self.assertNotIn(sizinti, cevap)

    def test_komut_hatasi_detay_sizdirmiyor(self):
        """Istisna metni sembol adi ve dosya yolu tasiyabilir - mesaja girmemeli."""
        def patlayan(env):
            raise RuntimeError(
                "/home/runner/ikinci-beyin/.env okunamadi: token=gizli-token")

        cevap = cevabi_uret("/portfoy", Baglam(env=ENV, yukleyici=patlayan))
        self.assertEqual(cevap,
                         "Veri su an okunamadi. Bir sonraki kosuda tekrar dene.")
        self.assertNotIn("gizli-token", cevap)
        self.assertNotIn(".env", cevap)

    def test_bot_yazma_islemi_yok(self):
        """Hicbir komut yazma/calistirma cagrisi icermemeli.

        Kaynak metnini taramak kaba ama etkili: yeni bir komut eklerken
        yanlislikla `subprocess` veya `write_text` cagirmak, bu testi kirar.
        """
        kaynak = Path(bot_sorgu.__file__).read_text(encoding="utf-8")
        komut_bolumu = kaynak[kaynak.index("# Komutlar"):kaynak.index("KOMUTLAR = {")]
        for yasak in ("eval(", "exec(", "subprocess", "os.system", "__import__",
                      "write_text", "open(", "unlink", "rmtree", "requests."):
            self.assertNotIn(yasak, komut_bolumu, f"komut bolumunde {yasak} var")

        # Modulde yazma yalnizca offset defterinde olmali.
        self.assertEqual(kaynak.count("write_text"), 1)
        self.assertIn("dosya.write_text", kaynak)

    def test_komut_sozlugu_beklenen_kumeyi_icerir(self):
        self.assertEqual(
            set(KOMUTLAR),
            {"/portfoy", "/risk", "/durum", "/fiyat", "/son", "/param", "/yardim"})

    def test_bot_adi_soneki_temizlenir(self):
        """Grupta /risk@InvestmentTR_bot diye gelir."""
        cevap = cevabi_uret("/yardim@InvestmentTR_bot", Baglam(env=ENV))
        self.assertNotIn("Taninmayan komut", cevap)

    def test_bos_metin_taninmayan_komut(self):
        self.assertIn("Taninmayan komut", cevabi_uret("   ", Baglam(env=ENV)))


class MesajBicimiTesti(unittest.TestCase):
    def test_bot_html_kacis_ampersand(self):
        """Sira onemli: `&` ilk sirada olmali.

        Once `<` kacirilsaydi `&lt;` icindeki `&` sonra yeniden kacirilir ve
        okuyucu `&amp;lt;` gorurdu.
        """
        self.assertEqual(kacis("A & B < C > D"), "A &amp; B &lt; C &gt; D")
        self.assertEqual(kacis("<b>"), "&lt;b&gt;")
        # Yalnizca bu uc karakter - tirnak ve kesme isareti DOKUNULMAZ.
        self.assertEqual(kacis("Tupras'in %5'i"), "Tupras'in %5'i")

    def test_bot_4096_bolme(self):
        uzun = "\n".join(f"satir {i} " + "x" * 80 for i in range(200))
        self.assertGreater(len(uzun), 4096)

        parcalar = bot_sorgu.bol(uzun)
        self.assertGreater(len(parcalar), 1)
        for parca in parcalar:
            self.assertLessEqual(len(parca), 4096)
        # Bolme satir sinirinda - hicbir satir ortadan kesilmemeli.
        birlesik = "".join(p.split("\n\n<i>(")[0] for p in parcalar)
        self.assertEqual(birlesik.replace("\n", ""), uzun.replace("\n", ""))

    def test_kisa_mesaj_bolunmez(self):
        self.assertEqual(bot_sorgu.bol("kisa"), ["kisa"])


class KosuPenceresiTesti(unittest.TestCase):
    """Gece bosuna Actions dakikasi yakilmasin."""

    AYARLAR = BotAyarlari(aralik_dakika=30, baslangic_saat=7, bitis_saat=1)

    def _an(self, tr_saat: int, dakika: int = 3):
        return datetime(2026, 8, 19, (tr_saat - 3) % 24, dakika, tzinfo=timezone.utc)

    def test_pencere_disinda_kosmaz(self):
        for tr_saat in (1, 3, 6):
            self.assertFalse(self.AYARLAR.kosulacak_mi(self._an(tr_saat)), tr_saat)

    def test_pencere_icinde_kosar(self):
        for tr_saat in (7, 12, 23, 0):
            self.assertTrue(self.AYARLAR.kosulacak_mi(self._an(tr_saat)), tr_saat)

    def test_genis_aralik_ara_kosuyu_atlar(self):
        """aralik_dakika: 60 -> cron 30 dk'da tetiklese de yarisi atlanir."""
        saatlik = BotAyarlari(aralik_dakika=60, baslangic_saat=7, bitis_saat=1)
        self.assertTrue(saatlik.kosulacak_mi(self._an(12, dakika=3)))
        self.assertFalse(saatlik.kosulacak_mi(self._an(12, dakika=33)))

    def test_pencere_disinda_ag_cagrisi_yapilmaz(self):
        cagrildi = []
        sonuc = bot_sorgu.calistir(
            env=ENV, getir=lambda ofs: cagrildi.append(ofs) or [],
            gonder=SahteGonderici(), offset_dosyasi=gecici_dosya(),
            ayarlar=self.AYARLAR, simdi=self._an(4))
        self.assertEqual(sonuc, 0)
        self.assertEqual(cagrildi, [])


class YapilandirmaTesti(unittest.TestCase):
    def test_aralik_cron_adiminin_altina_inemez(self):
        """Cron 30 dakikada bir tetikliyor; 15 yazmak sessizce etkisiz kalirdi."""
        dosya = gecici_dosya("bildirim.yaml")
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text("bot:\n  aralik_dakika: 15\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "aralik_dakika"):
            bot_sorgu.bot_ayarlarini_oku(dosya)

    def test_dosya_yoksa_varsayilan(self):
        ayarlar = bot_sorgu.bot_ayarlarini_oku(gecici_dosya("yok.yaml"))
        self.assertEqual(ayarlar.aralik_dakika, 30)
        self.assertEqual((ayarlar.baslangic_saat, ayarlar.bitis_saat), (7, 1))

    def test_gercek_bildirim_yaml_okunuyor(self):
        ayarlar = bot_sorgu.bot_ayarlarini_oku()
        self.assertGreaterEqual(ayarlar.aralik_dakika, 30)


class OrtamTesti(unittest.TestCase):
    def test_izinli_liste_ortam_degiskeninden_okunur(self):
        """Actions'ta .env YOK - secret ortama enjekte edilir.

        `ORTAM_ANAHTARLARI` listesinde olmayan anahtar orada sessizce bos
        kalir ve bot hicbir mesaja cevap vermez.
        """
        import os

        from notify import env_oku
        onceki = os.environ.get("TELEGRAM_IZINLI_CHAT_ID")
        os.environ["TELEGRAM_IZINLI_CHAT_ID"] = "424242"
        try:
            env = env_oku(Path(tempfile.mkdtemp()) / "yok.env")
            self.assertEqual(izinli_kimlikler(env), {"424242"})
        finally:
            if onceki is None:
                del os.environ["TELEGRAM_IZINLI_CHAT_ID"]
            else:
                os.environ["TELEGRAM_IZINLI_CHAT_ID"] = onceki


class TokenTesti(unittest.TestCase):
    def test_token_yoksa_hata_kodu(self):
        sonuc = bot_sorgu.calistir(
            env={"TELEGRAM_IZINLI_CHAT_ID": IZINLI}, getir=lambda ofs: [],
            gonder=SahteGonderici(), offset_dosyasi=gecici_dosya(),
            ayarlar=AYARLAR_ACIK, simdi=AN)
        self.assertEqual(sonuc, 1)

    def test_izinli_liste_yoksa_hata_kodu(self):
        """Bot cevap veremeyecekse sessizce basarili donmemeli."""
        sonuc = bot_sorgu.calistir(
            env={"TELEGRAM_BOT_TOKEN": "x"}, getir=lambda ofs: [],
            gonder=SahteGonderici(), offset_dosyasi=gecici_dosya(),
            ayarlar=AYARLAR_ACIK, simdi=AN)
        self.assertEqual(sonuc, 1)

    def test_getupdates_hatasi_kosuyu_dusurur(self):
        def patlayan(offset):
            raise RuntimeError("HTTP 401 bot1234:gizli-token")

        sonuc = bot_sorgu.calistir(env=ENV, getir=patlayan,
                                   gonder=SahteGonderici(),
                                   offset_dosyasi=gecici_dosya(),
                                   ayarlar=AYARLAR_ACIK, simdi=AN)
        self.assertEqual(sonuc, 1)



# --------------------------------------------------------------------------
# Komut govdeleri
# --------------------------------------------------------------------------

def _sentetik_veri():
    """Gercek siniflarla kurulmus, agsiz bir Veri.

    Neden gerekli: `cevabi_uret` her istisnayi yakalayip genel bir mesaja
    ceviriyor. Bu iyi bir guvenlik davranisi ama komut govdesindeki bir
    yazim hatasini da gizler - hata Telegram'da "veri okunamadi" diye
    gorunur ve kimse fark etmez. Bu test govdeleri gercekten calistirir.
    """
    gunler = pd.bdate_range("2026-06-01", periods=60)
    gecmis = pd.DataFrame(
        {"THYAO.IS": np.linspace(100, 120, 60),
         "BTC-USD": np.linspace(50, 60, 60),
         "GC=F": np.linspace(80, 85, 60)},
        index=gunler)
    fiyatlar = FiyatVerisi(
        try_gecmis=gecmis, usdtry=41.0, eksik_semboller=[],
        sinif_haritasi={"THYAO.IS": "bist", "BTC-USD": "kripto", "GC=F": "maden"},
        kurumsal_olay_supheleri={"GC=F": "2026-07-30: %-40.0 hareket"})

    yapilandirma = Yapilandirma(
        ayarlar=Ayarlar(kur_sembolu="USDTRY=X", gecmis_gun=365, islem_gunu_yil=252),
        esikler=Esikler(rebalancing_sapma=0.03, risk_katkisi_ust=0.20,
                        risk_beta_ust=1.30),
        hedef_dagilim={"bist": 0.6, "kripto": 0.4},
        varliklar={"THYAO.IS": Varlik("THYAO.IS", "THY", "bist", "TRY"),
                   "BTC-USD": Varlik("BTC-USD", "Bitcoin", "kripto", "USD"),
                   "GC=F": Varlik("GC=F", "Altin", "maden", "USD")},
        nakit_try=0.0, pozisyonlar=[])

    durum = defter_durumu(
        "  - {tarih: 2026-06-02, yon: AL, sembol: THYAO.IS, adet: 50, "
        "fiyat_try: 100, gerekce: acilis}\n"
        "  - {tarih: 2026-06-10, yon: AL, sembol: BTC-USD, adet: 10, "
        "fiyat_try: 2000, gerekce: sapma}\n",
        nakit=40000.0)
    portfoy = portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
    risk = riski_hesapla(yapilandirma, fiyatlar, portfoy)
    sapmalar = sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)

    maliyet = modeli_kur({
        "maliyet": {
            "sinif_profili": {"bist": "bist", "kripto": "kripto"},
            "islem": {
                "bist": {"komisyon_tip": "oransal", "komisyon_oran": 0.0015,
                         "kur_cevrimi": False, "menkul_spread": 0.001},
                "kripto": {"komisyon_tip": "oransal",
                           "komisyon_oran": {"tahmin": True, "iyimser": 0.001,
                                             "temel": 0.010, "kotumser": 0.030},
                           "kur_cevrimi": False, "menkul_spread": 0.0},
            },
            "tasima": {
                "THYAO.IS": {"gider_orani_yillik": 0.0, "temettu_verimi": 0.0},
                "BTC-USD": {"gider_orani_yillik": 0.0, "temettu_verimi": 0.0},
            },
            "firsat": {"tl_risksiz_yillik": 0.48},
        },
    }, yapilandirma.sinif_haritasi)
    duyarlilik = duyarliligi_olc(
        maliyet, yapilandirma.esikler.rebalancing_sapma,
        {p.sembol: p.deger_try for p in portfoy.pozisyonlar}, 41.0)
    karar = kararlari_uret(sapmalar, risk, yapilandirma.esikler,
                           Bekleme(ayni_sembol_saat=0.0),
                           DevreKesici(gunluk_maks_islem=6),
                           SinyalGecmisi(), "2026-08-19", maliyet, AN, duyarlilik)

    return bot_sorgu.Veri(
        yapilandirma=yapilandirma, fiyatlar=fiyatlar, portfoy=portfoy, risk=risk,
        durum=durum, maliyet=maliyet, duyarlilik=duyarlilik, karar=karar,
        sapmalar=sapmalar)


class KomutGovdesiTesti(unittest.TestCase):
    HATA = "Veri su an okunamadi. Bir sonraki kosuda tekrar dene."

    def setUp(self):
        veri = _sentetik_veri()
        self.baglam = Baglam(env=ENV, yukleyici=lambda env: veri)
        self.veri = veri

    def _cevap(self, metin: str) -> str:
        cevap = cevabi_uret(metin, self.baglam)
        self.assertNotEqual(cevap, self.HATA, f"{metin} patladi")
        return cevap

    def test_her_komut_calisiyor(self):
        for komut in ("/portfoy", "/risk", "/durum", "/son", "/param",
                      "/yardim", "/fiyat THYAO.IS"):
            cevap = self._cevap(komut)
            self.assertTrue(cevap.strip(), komut)

    def test_durum_bayat_hurdle_rate_i_bildirir(self):
        """Gun sonu ozetinde gorunen uyari /durum'da da gorunmeli.

        Iki ayri uyari yuzeyi var (mesaj.uyarilari_topla ve bot_sorgu); yeni
        bir uyari turunun birine girip digerine girmemesi bu sistemde daha
        once yasandi.
        """
        import dataclasses
        bayat = dataclasses.replace(self.veri.maliyet,
                                    risksiz_tarih="2026-08-07",
                                    risksiz_bayatlik_gun=7,
                                    risksiz_durdurma_gun=30)
        self.baglam = Baglam(env=ENV, yukleyici=lambda env: dataclasses.replace(
            self.veri, maliyet=bayat))
        cevap = self._cevap("/durum")
        self.assertIn("hurdle rate", cevap.lower())
        self.assertIn("2026-08-07", cevap)

    def test_veri_zamani_mesaj_zamani_degil(self):
        """Her fiyat/deger ciktisi VERI gununu tasimali.

        Mesaj 14:30'da gidiyor diye fiyat 14:30'un fiyati olmuyor; ikisini
        karistirmak bayat veriyi taze gostermenin en kolay yolu.
        """
        veri_gunu = self.veri.fiyatlar.son_tarih
        for komut in ("/portfoy", "/risk", "/durum", "/fiyat THYAO.IS", "/son"):
            self.assertIn(veri_gunu, self._cevap(komut), komut)

    def test_simulasyon_ibaresi(self):
        for komut in ("/portfoy", "/risk", "/durum", "/yardim"):
            self.assertIn("SIMULASYON", self._cevap(komut), komut)

    def test_belirsiz_parametre_uyarisi_ekleniyor(self):
        """Tahminli kalem karari ceviriyorsa mesajda uyari satiri olmali."""
        self.assertTrue(self.veri.duyarlilik.belirsizler, "fixture belirsizlik uretmeli")
        self.assertIn("parametre belirsizligi", self._cevap("/portfoy"))

    def test_fiyat_bilinmeyen_sembol_liste_doner(self):
        cevap = self._cevap("/fiyat ../../etc/passwd")
        self.assertIn("Bilinmeyen sembol", cevap)
        self.assertIn("THYAO.IS", cevap)
        self.assertNotIn("passwd", cevap)

    def test_fiyat_supheli_sembolde_sebep_yazar(self):
        cevap = self._cevap("/fiyat GC=F")
        self.assertIn("kurumsal olay suphesi", cevap)

    def test_fiyat_kaynak_ve_bayatlik_yazar(self):
        cevap = self._cevap("/fiyat THYAO.IS")
        for beklenen in ("Veri zamani:", "Kaynak:", "Bayat:"):
            self.assertIn(beklenen, cevap)

    def test_son_islem_tetikleyiciyi_yazar(self):
        cevap = self._cevap("/son")
        self.assertIn("THYAO.IS", cevap)
        self.assertIn("acilis", cevap)

    def test_risk_dislanan_sembolu_bildirir(self):
        self.assertIn("GC=F", self._cevap("/risk"))


    def test_param_referans_pozisyonu_yazar(self):
        """Buyukluk yazilmazsa liste hangi dunyayi anlattigini soylemiyor."""
        cevap = self._cevap("/param")
        self.assertIn("Referans pozisyon", cevap)
        for sembol in self.veri.duyarlilik.varliklar:
            self.assertIn(sembol, cevap)

    def test_param_ekonomik_olmayanlari_ayirir(self):
        cevap = self._cevap("/param")
        if self.veri.duyarlilik.ekonomik_olmayanlar:
            self.assertIn("Ekonomik olmayan pozisyonlar", cevap)
            self.assertIn("ya buyut ya cik", cevap)


    def test_param_kapsam_dokumunu_yazar(self):
        """"Karar dayanikli" tek basina hangi varsayimin sinandigini gizler."""
        cevap = self._cevap("/param")
        self.assertIn("Tahmin kapsami", cevap)
        self.assertIn("blokaji kaldiran", cevap)
        self.assertIn("SINANMADI", cevap)

    def test_veri_bir_kez_yuklenir(self):
        """Iki komut ayni kosuda gelirse Yahoo'ya iki kez gidilmemeli."""
        sayac = []
        veri = _sentetik_veri()

        def yukleyici(env):
            sayac.append(1)
            return veri

        baglam = Baglam(env=ENV, yukleyici=yukleyici)
        guncellemeleri_isle(
            [guncelleme(1, IZINLI, "/portfoy"), guncelleme(2, IZINLI, "/risk")],
            izinli_kimlikler(ENV), baglam, SahteGonderici())
        self.assertEqual(len(sayac), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
