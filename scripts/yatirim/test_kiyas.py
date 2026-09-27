"""Alternatif kiyasi: tek seferlik alim, baslangic fiyati, mevduat satiri."""

import unittest

import pandas as pd

from config import yapilandirmayi_oku
from fetch import FiyatVerisi
from kiyas import KiyasSatiri, baslangic_fiyati, kiyaslari_hesapla
from ledger import durumu_hesapla
from mesaj import GunSonuOzeti, gun_sonu_mesaji
from portfolio import Portfoy
from report import _kiyas_bolumu


class KiyasTesti(unittest.TestCase):
    def _gecmis(self):
        gunler = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14",
                                 "2026-08-17", "2026-09-26"])
        return pd.DataFrame({
            "XU100.IS": [90.0, 100.0, 101.0, None, 120.0],
            # Hafta sonu baslangic: 08-15 Cumartesi, ilk acik gun 08-17.
            "GC=F": [None, None, None, 50.0, 55.0],
        }, index=gunler)

    def test_baslangictan_onceki_fiyat_kullanilmaz(self):
        # 08-12'deki 90 o gun alinabilecek bir fiyat degil.
        self.assertEqual(baslangic_fiyati(self._gecmis()["XU100.IS"], "2026-08-13"), 100.0)

    def test_kapali_gunde_ilk_acik_gun(self):
        self.assertEqual(baslangic_fiyati(self._gecmis()["GC=F"], "2026-08-15"), 50.0)

    def test_veri_yoksa_none(self):
        self.assertIsNone(baslangic_fiyati(self._gecmis()["XU100.IS"], "2026-10-01"))

    def test_siralama_komisyon_ve_mevduat(self):
        satirlar = kiyaslari_hesapla(
            sermaye=20_000, baslangic="2026-08-13", portfoy_degeri=21_000,
            semboller=["XU100.IS", "QQQ"], adlar={"XU100.IS": "BIST 100"},
            # 999: BTCTurk'un ezdigi fiyat; kiyas seriyle tutarli kalmali.
            try_gecmis=self._gecmis(), son_fiyatlar={"XU100.IS": 999.0},
            komisyon_orani=0.0015, risksiz_yillik=0.48, gun=45)
        adlar = [s.ad for s in satirlar]
        # BIST %20 > portfoy %5 > mevduat; olculemeyen en sonda.
        self.assertEqual(adlar, ["BIST 100", "Bu portfoy", "Mevduat", "QQQ"])
        self.assertAlmostEqual(satirlar[0].deger_try, 20_000 * 0.9985 * 1.2)
        self.assertTrue(satirlar[1].portfoy)
        self.assertAlmostEqual(satirlar[2].getiri, 1.48 ** (45 / 365) - 1)
        self.assertIsNone(satirlar[3].deger_try)
        self.assertIn("baslangic", satirlar[3].not_)

    def test_risksiz_yoksa_mevduat_olculemedi(self):
        satirlar = kiyaslari_hesapla(20_000, "2026-08-13", 20_000, [], {},
                                     self._gecmis(), {}, 0.0, None, 45)
        self.assertIsNone(satirlar[-1].deger_try)


class KiyasBolumuTesti(unittest.TestCase):
    """Gercek varliklar.yaml ile rapor bolumu uctan uca render ediliyor mu."""

    def test_bolum_render(self):
        yapilandirma = yapilandirmayi_oku()
        self.assertTrue(yapilandirma.kiyas)
        gunler = pd.to_datetime(["2026-08-13", "2026-09-26"])
        gecmis = pd.DataFrame({s: [100.0, 110.0] for s in yapilandirma.kiyas},
                              index=gunler)
        fiyatlar = FiyatVerisi(try_gecmis=gecmis, usdtry=40.0, eksik_semboller=[])
        durum = durumu_hesapla([], 20_000, 0.0015, baslangic_tarihi="2026-08-13")
        portfoy = Portfoy(pozisyonlar=[], nakit_try=20_500.0, fiyatlanamayan=[])
        metin = "\n".join(_kiyas_bolumu(yapilandirma, fiyatlar, portfoy, durum,
                                        yapilandirma.maliyet, 44))
        self.assertIn("## Alternatif kiyasi", metin)
        self.assertIn("**Bu portfoy**", metin)
        self.assertIn("Mevduat", metin)
        self.assertIn("BIST 100", metin)


class KiyasMesajTesti(unittest.TestCase):
    """Telegram gun sonu: lider + portfoyun sirasi, tek satir."""

    def _mesaj(self, kiyaslar):
        portfoy = Portfoy(pozisyonlar=[], nakit_try=20_500.0, fiyatlanamayan=[])
        return gun_sonu_mesaji(GunSonuOzeti(
            portfoy=portfoy, risk=None, veri_zamani="2026-09-26",
            baslangic_try=20_000.0, kiyaslar=kiyaslar))

    def test_portfoy_geride(self):
        mesaj = self._mesaj([
            KiyasSatiri("BIST 100", 22_000, 0.10),
            KiyasSatiri("Bu portfoy", 20_500, 0.025, portfoy=True),
            KiyasSatiri("Mevduat", 20_400, 0.02),
            KiyasSatiri("QQQ", None, None, "veri yok"),
        ])
        # Olculemeyen secenek paydaya girmez: 2./3, 2./4 degil.
        self.assertIn("Portfoy 2./3: en iyisi BIST 100 +10.0%", mesaj)

    def test_portfoy_onde(self):
        mesaj = self._mesaj([
            KiyasSatiri("Bu portfoy", 20_500, 0.025, portfoy=True),
            KiyasSatiri("Altin (gram)", 20_300, 0.015),
        ])
        self.assertIn("Alternatiflerin ONUNDE: portfoy 1./2, ikinci Altin (gram) +1.5%", mesaj)

    def test_kiyas_yoksa_satir_duser(self):
        self.assertNotIn("🏁", self._mesaj([]))


if __name__ == "__main__":
    unittest.main()
