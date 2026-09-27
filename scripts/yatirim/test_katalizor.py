"""Katalizor takvimi: dogrulama, pencere, bayatlik uyarisi, mesaj ve rapor."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from config import yapilandirmayi_oku
from katalizor import Katalizor, Takvim, takvimi_oku
from mesaj import GunSonuOzeti, gun_sonu_mesaji, uyarilari_topla
from portfolio import Portfoy, PozisyonDegeri
from report import katalizor_bolumu

BUGUN = date(2026, 10, 1)       # Persembe


def _yaml(govde: str) -> Path:
    dosya = Path(tempfile.mkdtemp()) / "k.yaml"
    dosya.write_text(govde, encoding="utf-8")
    return dosya


def _k(tarih, olay="PPK", kapsam="makro", etki="yuksek", saat="") -> Katalizor:
    return Katalizor(tarih=tarih, olay=olay, kapsam=kapsam, etki=etki, saat=saat)


def _portfoy(*pozisyonlar) -> Portfoy:
    return Portfoy(pozisyonlar=[PozisyonDegeri(s, s, sinif, 1, 1, 1)
                                for s, sinif in pozisyonlar],
                   nakit_try=0.0, fiyatlanamayan=[])


class OkumaTesti(unittest.TestCase):
    OKU = staticmethod(lambda d: takvimi_oku(d, {"THYAO.IS"}, {"bist", "nasdaq"}))

    def test_dosya_yoksa_bos(self):
        self.assertEqual(self.OKU(Path("/yok/k.yaml")).olaylar, [])

    def test_gecerli_olay(self):
        takvim = self.OKU(_yaml(
            "olaylar:\n  - {tarih: 2026-10-22, saat: '14:00', olay: PPK, "
            "kapsam: makro, etki: yuksek}\n"))
        self.assertEqual(takvim.olaylar[0].saat, "14:00")

    def test_tanimsiz_kapsam_reddedilir(self):
        # Yanlis yazilmis sembol sessizce "pozisyonuna dokunmuyor" olurdu.
        with self.assertRaisesRegex(ValueError, "kapsam"):
            self.OKU(_yaml("olaylar:\n  - {tarih: 2026-10-22, olay: X, "
                           "kapsam: THYAO, etki: yuksek}\n"))

    def test_gecersiz_etki_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "etki"):
            self.OKU(_yaml("olaylar:\n  - {tarih: 2026-10-22, olay: X, "
                           "kapsam: makro, etki: kritik}\n"))

    def test_tarih_metin_reddedilir(self):
        with self.assertRaisesRegex(ValueError, "tarih"):
            self.OKU(_yaml("olaylar:\n  - {tarih: '22 Ekim', olay: X, "
                           "kapsam: makro, etki: yuksek}\n"))

    def test_gercek_takvim_okunuyor(self):
        from main import KATALIZOR_DOSYASI
        y = yapilandirmayi_oku()
        takvim = takvimi_oku(KATALIZOR_DOSYASI, set(y.varliklar),
                             {v.sinif for v in y.varliklar.values()})
        self.assertTrue(takvim.olaylar)


class PencereTesti(unittest.TestCase):
    def test_yalnizca_pencere_ici_sirali(self):
        takvim = Takvim([_k(date(2026, 10, 9)), _k(date(2026, 10, 2)),
                         _k(date(2026, 9, 30)), _k(date(2026, 10, 1))], pencere_gun=7)
        self.assertEqual([k.tarih.day for k in takvim.yaklasanlar(BUGUN)], [1, 2])

    def test_kapsama_uyarisi(self):
        takvim = Takvim([_k(date(2026, 10, 10))], kapsama_uyari_gun=21)
        self.assertIn("2026-10-10 sonrasini kapsamiyor", takvim.kapsama_uyarisi(BUGUN))
        self.assertIsNone(Takvim([_k(date(2026, 11, 1))]).kapsama_uyarisi(BUGUN))

    def test_uyari_telegram_listesine_girer(self):
        self.assertEqual(uyarilari_topla(None, None, None, None, None,
                                         takvim_uyarisi="guncelle"), ["guncelle"])


class MesajTesti(unittest.TestCase):
    def _mesaj(self, katalizorler, tutulanlar=frozenset()):
        return gun_sonu_mesaji(GunSonuOzeti(
            portfoy=_portfoy(), risk=None, veri_zamani="2026-10-01",
            katalizorler=katalizorler, tutulanlar=tutulanlar))

    def test_satir_bicimi_ve_isaret(self):
        mesaj = self._mesaj(
            [_k(date(2026, 10, 5), "TUFE", saat="10:00"),
             _k(date(2026, 10, 6), "THYAO bilanco", kapsam="THYAO.IS")],
            frozenset({"THYAO.IS", "bist"}))
        self.assertIn("📅 Yaklasan: Pzt 5 Ekim 10:00 TUFE · 👉 Sal 6 Ekim THYAO bilanco",
                      mesaj)

    def test_fazlasi_rapora(self):
        mesaj = self._mesaj([_k(date(2026, 10, d)) for d in range(2, 7)])
        self.assertIn("(+2 raporda)", mesaj)

    def test_olay_yoksa_satir_duser(self):
        self.assertNotIn("📅", self._mesaj([]))


class RaporTesti(unittest.TestCase):
    def test_bolum(self):
        takvim = Takvim([_k(date(2026, 10, 5), "TUFE"),
                         _k(date(2026, 10, 6), "BIST olay", kapsam="bist"),
                         _k(date(2026, 10, 7), "Nasdaq olay", kapsam="nasdaq")])
        metin = "\n".join(katalizor_bolumu(takvim, _portfoy(("GARAN.IS", "bist")), BUGUN))
        self.assertIn("| Pzt 5 Eki | - | TUFE | yuksek | genel (makro) |", metin)
        self.assertIn("| BIST olay | yuksek | 👉 evet |", metin)
        self.assertIn("| Nasdaq olay | yuksek | hayir |", metin)
        self.assertIn("kapsamiyor", metin)     # son olay 7 Ekim < 1 Ekim + 21

    def test_bos_aralik_acikca_yazilir(self):
        takvim = Takvim([_k(date(2026, 12, 1))])
        self.assertIn("Takvimde bu aralikta olay yok.",
                      katalizor_bolumu(takvim, _portfoy(), BUGUN))

    def test_takvim_yoksa_bolum_yok(self):
        self.assertEqual(katalizor_bolumu(Takvim(), _portfoy(), BUGUN), [])


if __name__ == "__main__":
    unittest.main()
