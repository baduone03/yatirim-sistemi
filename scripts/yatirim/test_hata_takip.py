"""Tekrarlayan hata bildirimi bastirma testleri. Ag'a CIKMAZ."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from hata_takip import (  # noqa: E402
    BASTIR,
    COZULDU,
    DEVAM,
    YENI,
    AktifHata,
    bildir,
    durumu_oku,
    durumu_yaz,
    karar_ver,
)

AN = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def gecici() -> Path:
    return Path(tempfile.mkdtemp()) / "hata-durumu.yaml"


class KararTesti(unittest.TestCase):
    def test_yeni_hata_hemen_bildirilir(self):
        karar = karar_ver("hurdle-bayat", None, AN)
        self.assertEqual(karar.durum, YENI)
        self.assertTrue(karar.bildirilecek)

    def test_ayni_hata_24_saatte_bir_bildiriliyor(self):
        """Iki saatlik gridde kalici bir ariza gunde 12 mesaj uretirdi."""
        ilk = AktifHata(kod="hurdle-bayat", ilk_gorulme=AN, son_bildirim=AN)

        # 2, 6, 12, 23 saat sonra: hepsi bastirilir.
        for saat in (2, 6, 12, 23):
            karar = karar_ver("hurdle-bayat", ilk, AN + timedelta(hours=saat))
            self.assertEqual(karar.durum, BASTIR, f"{saat}. saatte bildirim gitti")
            self.assertFalse(karar.bildirilecek)

        # 24. saatte "hala devam ediyor".
        karar = karar_ver("hurdle-bayat", ilk, AN + timedelta(hours=24))
        self.assertEqual(karar.durum, DEVAM)
        self.assertTrue(karar.bildirilecek)
        self.assertIn("HALA DEVAM", karar.onek)

    def test_bastirilan_bildirim_sayaci_ILERLETMEZ(self):
        """Ilerletseydi 24 saatlik sayac her kosuda sifirlanir ve
        'hala devam ediyor' ozeti hicbir zaman gonderilmezdi."""
        ilk = AktifHata(kod="x", ilk_gorulme=AN, son_bildirim=AN)
        bastirilan = karar_ver("x", ilk, AN + timedelta(hours=20))
        self.assertEqual(bastirilan.yeni_kayit.son_bildirim, AN)

        # 20. saatte bastirildi; 24. saatte yine de ozet gitmeli.
        karar = karar_ver("x", bastirilan.yeni_kayit, AN + timedelta(hours=24))
        self.assertEqual(karar.durum, DEVAM)

    def test_hata_degisirse_hemen_bildirilir(self):
        ilk = AktifHata(kod="hurdle-bayat", ilk_gorulme=AN, son_bildirim=AN)
        karar = karar_ver("kaynak-coktu", ilk, AN + timedelta(hours=1))
        self.assertEqual(karar.durum, YENI)
        self.assertEqual(karar.yeni_kayit.kod, "kaynak-coktu")

    def test_cozulunce_hemen_bildirilir_ve_kayit_silinir(self):
        ilk = AktifHata(kod="hurdle-bayat", ilk_gorulme=AN, son_bildirim=AN)
        karar = karar_ver("", ilk, AN + timedelta(hours=30))
        self.assertEqual(karar.durum, COZULDU)
        self.assertTrue(karar.bildirilecek)
        self.assertIsNone(karar.yeni_kayit)
        self.assertIn("30 saat", karar.onek)

    def test_hata_yokken_sessiz_kalinir(self):
        karar = karar_ver("", None, AN)
        self.assertEqual(karar.durum, BASTIR)
        self.assertFalse(karar.bildirilecek)

    def test_devam_ozeti_ilk_gorulmeyi_korur(self):
        ilk = AktifHata(kod="x", ilk_gorulme=AN, son_bildirim=AN)
        karar = karar_ver("x", ilk, AN + timedelta(hours=25))
        self.assertEqual(karar.yeni_kayit.ilk_gorulme, AN)
        self.assertEqual(karar.yeni_kayit.bildirim_sayisi, 2)


class DiskTesti(unittest.TestCase):
    def test_yazilan_durum_geri_okunur(self):
        dosya = gecici()
        kayit = AktifHata(kod="x", ilk_gorulme=AN, son_bildirim=AN,
                          bildirim_sayisi=3)
        durumu_yaz(kayit, dosya)
        geri = durumu_oku(dosya)
        self.assertEqual(geri, kayit)

    def test_dosya_yoksa_none(self):
        self.assertIsNone(durumu_oku(gecici()))

    def test_bozuk_kayit_hic_kayit_sayilir(self):
        """Bozuk dosya butun hata bildirimlerini kalici olarak susturmamali."""
        dosya = gecici()
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text("aktif: {kod: x, ilk_gorulme: bozuk}\n", encoding="utf-8")
        self.assertIsNone(durumu_oku(dosya))

    def test_bildir_akisi_uctan_uca(self):
        dosya = gecici()
        gidenler = []

        ilk = bildir("hurdle-bayat", "Rapor uretilmedi.", gidenler.append,
                     dosya, AN)
        self.assertEqual(ilk.durum, YENI)
        self.assertEqual(len(gidenler), 1)

        # 3 saat sonra ayni hata - sessiz.
        tekrar = bildir("hurdle-bayat", "Rapor uretilmedi.", gidenler.append,
                        dosya, AN + timedelta(hours=3))
        self.assertEqual(tekrar.durum, BASTIR)
        self.assertEqual(len(gidenler), 1, "bastirilan mesaj gonderildi")

        # 25 saat sonra - devam ozeti.
        devam = bildir("hurdle-bayat", "Rapor uretilmedi.", gidenler.append,
                       dosya, AN + timedelta(hours=25))
        self.assertEqual(devam.durum, DEVAM)
        self.assertEqual(len(gidenler), 2)
        self.assertIn("HALA DEVAM", gidenler[1])

        # Cozuldu.
        cozum = bildir("", "", gidenler.append, dosya, AN + timedelta(hours=26))
        self.assertEqual(cozum.durum, COZULDU)
        self.assertEqual(len(gidenler), 3)
        self.assertIsNone(durumu_oku(dosya))


class KosuSuresiTesti(unittest.TestCase):
    """60 saniye faturayi ikiye katlar; 50'de uyarmak tedbir icin zaman birakir."""

    def _kosu(self, saniye: float) -> dict:
        return {"created_at": "2026-08-19T10:00:00Z",
                "updated_at": (datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
                               + timedelta(seconds=saniye)).isoformat()}

    def test_ortalama_hesaplanir(self):
        from kosu_suresi import ortalama_saniye
        ortalama, ornek = ortalama_saniye([self._kosu(30), self._kosu(50)])
        self.assertEqual(ornek, 2)
        self.assertAlmostEqual(ortalama, 40.0)

    def test_bitmemis_ve_takilmis_kosu_disarida(self):
        from kosu_suresi import ortalama_saniye
        ortalama, ornek = ortalama_saniye([
            self._kosu(-100),        # bitmemis
            self._kosu(7200),        # takilmis
            self._kosu(40),
        ])
        self.assertEqual(ornek, 1)
        self.assertAlmostEqual(ortalama, 40.0)

    def test_ornek_yoksa_sifir(self):
        from kosu_suresi import ortalama_saniye
        self.assertEqual(ortalama_saniye([]), (0.0, 0))
        self.assertEqual(ortalama_saniye([{"created_at": "bozuk"}]), (0.0, 0))

    def test_uyari_metni_fatura_katini_soyler(self):
        from kosu_suresi import uyari_metni
        self.assertIn("2 dakika", uyari_metni(75.0, 10))
        self.assertIn("1 dakika", uyari_metni(55.0, 10))

    def test_olcum_coktugunde_bos_liste_doner(self):
        """Butce izleme yardimci islev; coktugunde raporu ETKILEMEMELI.

        Yukari patlasaydi tum rapor kosusu butce izleme yuzunden kirilirdi.
        """
        from kosu_suresi import kosulari_cek

        def patlat(_repo, _jeton):
            raise RuntimeError("ag yok")

        self.assertEqual(kosulari_cek("a/b", "j", getir=patlat), [])


if __name__ == "__main__":
    unittest.main()
