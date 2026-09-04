"""LLM istemcisi, haber analizi ve durum ozeti testleri. TAMAMEN CEVRIMDISI.

Ag katmani her testte enjekte ediliyor; paket calisirken NVIDIA'ya hicbir
istek gitmez ve anahtar gerekmez.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date

import durum_ozeti
import haber_analiz
from haber import Haber
from llm import ANAHTAR_ADI, LLMAyarlari, LLMHatasi, json_coz, sor
from mesaj import haber_mesaji

ACIK = LLMAyarlari(acik=True, model="test/model")
ORTAM = {ANAHTAR_ADI: "sahte-anahtar"}
ADLAR = {"BTC-USD": "Bitcoin", "GC=F": "Altin"}


def sabit(cevap: str):
    def gonder(istem, ayarlar, anahtar):
        return cevap
    return gonder


def patlayan(mesaj: str = "sunucu dustu"):
    def gonder(istem, ayarlar, anahtar):
        raise LLMHatasi(mesaj)
    return gonder


class KapiTesti(unittest.TestCase):
    """Anahtar ve `acik` bayragi olmadan hicbir cagri yapilmamali."""

    def test_kapaliysa_cagirmaz(self):
        with self.assertRaises(LLMHatasi):
            sor("x", LLMAyarlari(acik=False), ORTAM, sabit("olmaz"))

    def test_anahtarsiz_hata_verir(self):
        with self.assertRaises(LLMHatasi) as kap:
            sor("x", ACIK, {}, sabit("olmaz"))
        self.assertIn(ANAHTAR_ADI, str(kap.exception))

    def test_anahtar_hicbir_hataya_sizmaz(self):
        """Anahtar hata metnine girerse Actions loguna dusar."""
        with self.assertRaises(LLMHatasi) as kap:
            sor("x", ACIK, {ANAHTAR_ADI: "gizli-deger"}, patlayan("HTTP 401"))
        self.assertNotIn("gizli-deger", str(kap.exception))


class JsonCozmeTesti(unittest.TestCase):
    def test_cerceveli_cikti(self):
        self.assertEqual(json_coz('Iste:\n```json\n[{"a": 1}]\n```'), [{"a": 1}])

    def test_ciplak_dizi(self):
        self.assertEqual(json_coz('[1, 2]'), [1, 2])

    def test_nesne_icindeki_dizi_nesneyi_kacirmaz(self):
        """`{"yuksek": [...]}` dizi sanilirsa cevap tumden dusuyordu."""
        self.assertEqual({"yuksek": [1, 2]}, json_coz('{"yuksek": [1, 2]}'))

    def test_json_olmayan_cikti_hata(self):
        with self.assertRaises(LLMHatasi):
            json_coz("bugun hava guzel")


HABERLER = [
    Haber("TCMB faizi indirdi", "u1", "Bloomberg", "makro", date(2026, 9, 4)),
    Haber("Yeni MacBook tanitildi", "u2", "Verge", "piyasa", date(2026, 9, 4)),
    Haber("Bitcoin ETF girisi rekor", "u3", "CoinDesk", "kripto", date(2026, 9, 4)),
]
CEVAP = ('{"yuksek": ['
         '{"no": 1, "etkilenen": ["GC=F"], "ozet": "Faiz indi."},'
         ' {"no": 3, "etkilenen": ["BTC-USD"], "ozet": "Giris arti."}],'
         ' "alakasiz": [2]}')


class HaberAnaliziTesti(unittest.TestCase):
    def test_ilgiye_gore_siralanir(self):
        sirali, esleme, uyari = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(CEVAP))
        self.assertEqual("", uyari)
        self.assertEqual("Yeni MacBook tanitildi", sirali[-1].baslik)
        self.assertEqual(("BTC-USD",), esleme["Bitcoin ETF girisi rekor"].etkilenen)

    def test_yuksek_kotasi_uygulanir(self):
        """Istem kotasi bir rica; model asarsa kirpma garanti etmeli."""
        kayitlar = ", ".join(
            '{"no": %d, "ozet": "x"}' % n
            for n in range(1, haber_analiz.AZAMI_YUKSEK + 4))
        cozulen = haber_analiz.cevabi_coz(
            '{"yuksek": [%s]}' % kayitlar, haber_analiz.AZAMI_YUKSEK + 4)
        self.assertEqual(haber_analiz.AZAMI_YUKSEK, len(cozulen))

    def test_istem_yuksek_tavanini_yazar(self):
        istem = haber_analiz.istem_uret(["a"], ADLAR)
        self.assertIn(str(haber_analiz.AZAMI_YUKSEK), istem)

    def test_ozet_yalnizca_yuksek_ilgililerden_istenir(self):
        """Istem her basliga cumle yazdirmamali - olculdu: 30 baslik >25 sn."""
        istem = haber_analiz.istem_uret(["a", "b"], ADLAR)
        self.assertIn("alakasiz", istem)
        self.assertIn("yuksek", istem)

    def test_alakasiz_baslik_ELENMEZ(self):
        """Elemek modelin yanilgisini gorunmez yapardi; sona atmak yalnizca sira."""
        sirali, _, _ = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(CEVAP))
        self.assertEqual(len(HABERLER), len(sirali))

    def test_cagri_duserse_ham_sira_korunur(self):
        sirali, esleme, uyari = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, patlayan())
        self.assertEqual([h.baslik for h in HABERLER],
                         [h.baslik for h in sirali])
        self.assertEqual({}, esleme)
        self.assertTrue(uyari)

    def test_bozuk_cevap_haberi_dusurmez(self):
        sirali, _, uyari = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit("bugun hava guzel"))
        self.assertEqual(len(HABERLER), len(sirali))
        self.assertTrue(uyari)

    def test_aralik_disi_numara_atilir(self):
        """Model uydurdugu 9. basligi listeye sokamamali."""
        cevap = '{"yuksek": [{"no": 9, "ozet": "olmayan haber"}], "alakasiz": [42]}'
        _, esleme, _ = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(cevap))
        self.assertEqual({}, esleme)

    def test_listelenmeyen_baslik_dusuk_sayilir(self):
        """Modelin yazmadigi baslik kaybolmaz, ortada kalir."""
        cevap = '{"yuksek": [{"no": 3, "ozet": "x"}], "alakasiz": [2]}'
        sirali, esleme, _ = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(cevap))
        self.assertNotIn("TCMB faizi indirdi", esleme)
        self.assertEqual(["Bitcoin ETF girisi rekor", "TCMB faizi indirdi",
                          "Yeni MacBook tanitildi"],
                         [h.baslik for h in sirali])

    def test_iki_listede_birden_gecen_baslik_yuksek_kalir(self):
        cevap = '{"yuksek": [{"no": 1, "ozet": "x"}], "alakasiz": [1]}'
        _, esleme, _ = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(cevap))
        self.assertEqual(haber_analiz.YUKSEK, esleme["TCMB faizi indirdi"].ilgi)

    def test_istem_portfoy_sembollerini_tasir(self):
        istem = haber_analiz.istem_uret(["baslik"], ADLAR)
        self.assertIn("BTC-USD", istem)
        self.assertIn("Bitcoin", istem)


class HaberMesajiTesti(unittest.TestCase):
    def test_degerlendirmesiz_mesaj_degismedi(self):
        """Analiz kapaliyken mesaj eski bicimini korumali."""
        metin = haber_mesaji(HABERLER, [], date(2026, 9, 4))
        self.assertNotIn("model uretimi", metin)

    def test_yuksek_ilgi_ozeti_yazilir_dusuk_yazilmaz(self):
        _, esleme, _ = haber_analiz.haberleri_degerlendir(
            HABERLER, ADLAR, ACIK, ORTAM, sabit(CEVAP))
        metin = haber_mesaji(HABERLER, [], date(2026, 9, 4), esleme)
        self.assertIn("Faiz indi.", metin)
        self.assertNotIn("Urun tanitimi.", metin)
        self.assertIn("model uretimi", metin)


class JetonTavaniTesti(unittest.TestCase):
    """Yarim kalan cevap, bicim hatasi gibi degil KENDI adiyla raporlanmali."""

    def test_kesilen_cevap_tavani_soyler(self):
        import json
        import llm

        class SahteCevap:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({"choices": [{
                    "finish_reason": "length",
                    "message": {"content": '{"yuksek": [{"no": 1,'}}]}).encode()

        eski = llm.urllib.request.urlopen
        llm.urllib.request.urlopen = lambda istek, timeout=None: SahteCevap()
        try:
            with self.assertRaises(LLMHatasi) as kap:
                llm.http_llm("istem", ACIK, "anahtar")
        finally:
            llm.urllib.request.urlopen = eski
        self.assertIn("jeton tavanina", str(kap.exception))


class DurumOzetiTesti(unittest.TestCase):
    def test_cumle_tavani_uygulanir(self):
        ozet, uyari = durum_ozeti.ozet_uret(
            "<b>Gun sonu</b> Portfoy 20.000 TL.", ACIK, ORTAM,
            sabit("Bir. Iki. Uc. Dort. Bes."))
        self.assertEqual("", uyari)
        self.assertEqual("Bir. Iki. Uc.", ozet)

    def test_html_etiketi_ciktidan_atilir(self):
        ozet, _ = durum_ozeti.ozet_uret(
            "metin", ACIK, ORTAM, sabit("<b>Portfoy</b> arti."))
        self.assertEqual("Portfoy arti.", ozet)

    def test_cagri_duserse_ozet_bos_uyari_dolu(self):
        ozet, uyari = durum_ozeti.ozet_uret("metin", ACIK, ORTAM, patlayan())
        self.assertEqual("", ozet)
        self.assertTrue(uyari)

    def test_bos_cevap_uyari_uretir(self):
        ozet, uyari = durum_ozeti.ozet_uret("metin", ACIK, ORTAM, sabit("   "))
        self.assertEqual("", ozet)
        self.assertTrue(uyari)

    def test_girdi_mesajin_kendisi(self):
        """Ozet mesajda yazmayan bir sey soyleyemesin diye istem mesaji tasir."""
        gorulen = {}

        def casus(istem, ayarlar, anahtar):
            gorulen["istem"] = istem
            return "Ozet."

        durum_ozeti.ozet_uret("<b>Portfoy 20.000 TL</b>", ACIK, ORTAM, casus)
        self.assertIn("Portfoy 20.000 TL", gorulen["istem"])
        self.assertNotIn("<b>", gorulen["istem"])


if __name__ == "__main__":
    unittest.main()
