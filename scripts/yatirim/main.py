"""Yatirim raporu uretir.

Kullanim:
    python scripts/yatirim/main.py           # gercek portfoy (portfoy.yaml)
    python scripts/yatirim/main.py --sim     # simulasyon defteri (islemler.yaml)
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    PROJE_DIZINI,
    RAPOR_DIZINI,
    sablonu_reddet,
    yapilandirmayi_oku,
)
from fetch import fiyatlari_getir  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from notify import TelegramHatasi, mesaj_gonder, ozet_mesaji  # noqa: E402
from portfolio import (  # noqa: E402
    portfoyu_hesapla,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from report import OZET_BASLANGIC, OZET_BITIS, rapor_olustur, sistem_ozeti  # noqa: E402
from risk import riski_hesapla  # noqa: E402

SISTEM_DOSYASI = PROJE_DIZINI / "00-sistem.md"
SIM_DIZINI = PROJE_DIZINI / "simulasyon"
SIM_DEFTERI = SIM_DIZINI / "islemler.yaml"
SIM_RAPOR_DIZINI = SIM_DIZINI / "raporlar"


def _sistem_ozetini_guncelle(ozet: str) -> None:
    """00-sistem.md icindeki ozet blogunu gunceller.

    Sessizce basarisiz OLMAZ: isaretci silinmisse bayat ozet aktif ozet gibi
    gorunmeye devam eder, bu da yanlis rakama bakmak demektir.
    """
    if not SISTEM_DOSYASI.exists():
        print(f"UYARI - {SISTEM_DOSYASI} yok, ozet guncellenmedi.")
        return
    icerik = SISTEM_DOSYASI.read_text(encoding="utf-8")
    desen = re.compile(f"{re.escape(OZET_BASLANGIC)}.*?{re.escape(OZET_BITIS)}", re.DOTALL)
    if not desen.search(icerik):
        print(
            f"UYARI - {SISTEM_DOSYASI} icinde {OZET_BASLANGIC} / {OZET_BITIS} "
            "isaretcileri bulunamadi. Ozet guncellenmedi; dosyadaki rakamlar BAYAT."
        )
        return
    SISTEM_DOSYASI.write_text(desen.sub(lambda _: ozet, icerik), encoding="utf-8")


def _durumu_yukle(sim: bool):
    if not sim:
        return None
    islemler, baslangic_nakit, komisyon = islemleri_oku(SIM_DEFTERI)
    return durumu_hesapla(islemler, baslangic_nakit, komisyon)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Yatirim/simulasyon raporu uretir")
    ayristirici.add_argument(
        "--sim", action="store_true", help="portfoy.yaml yerine simulasyon defterini kullan"
    )
    ayristirici.add_argument(
        "--telegram", action="store_true", help="ozeti Telegram'a gonder"
    )
    argumanlar = ayristirici.parse_args()

    yapilandirma = yapilandirmayi_oku()
    if not argumanlar.sim:
        sablonu_reddet(yapilandirma)
    durum = _durumu_yukle(argumanlar.sim)

    print(f"{len(yapilandirma.fiyat_sembolleri)} sembol icin fiyat cekiliyor...")
    fiyatlar = fiyatlari_getir(yapilandirma)

    portfoy = (
        portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
        if durum
        else portfoyu_hesapla(yapilandirma, fiyatlar)
    )
    sapmalar = sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)
    risk = riski_hesapla(yapilandirma, fiyatlar, portfoy)

    rapor_adi = date.today().isoformat()
    rapor_dizini = SIM_RAPOR_DIZINI if durum else RAPOR_DIZINI
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    rapor_dosyasi = rapor_dizini / f"{rapor_adi}.md"
    rapor_dosyasi.write_text(
        rapor_olustur(yapilandirma, fiyatlar, portfoy, sapmalar, risk, durum), encoding="utf-8"
    )

    if not durum:
        _sistem_ozetini_guncelle(sistem_ozeti(portfoy, risk, rapor_adi))

    print(f"Rapor yazildi: {rapor_dosyasi}")
    if fiyatlar.eksik_semboller:
        print(f"UYARI - fiyat gelmeyen sembol: {', '.join(fiyatlar.eksik_semboller)}")

    if argumanlar.telegram:
        baslik = f"{'Simulasyon' if durum else 'Portfoy'} {rapor_adi}"
        try:
            mesaj_gonder(ozet_mesaji(portfoy, sapmalar, risk, durum, baslik,
                                     fiyatlar, yapilandirma.esikler))
            print("Telegram ozeti gonderildi.")
        except TelegramHatasi as hata:
            # Rapor diske yazildi ve GECERLI - kaybolmadi.
            # Yine de exit 1 doneriyoruz: bu sistemin cikti kanali Telegram,
            # mesaj gitmediyse kimse rapordan haberdar olmaz. CI'in kosuyu
            # basarisiz isaretlemesi ve uyarmasi DOGRU davranis.
            print(f"UYARI - Telegram gonderilemedi: {hata}")
            print("Rapor diske yazildi, kaybolmadi.")
            return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as hata:
        # Beklenen yapilandirma/veri hatalari: traceback yerine net mesaj.
        # Beklenmeyen hatalar traceback ile yukselmeye devam eder.
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
