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
from fetch import fiyatlari_getir, maliyet_modelini_coz  # noqa: E402
from kurumsal_olay import bilinen_olay_anahtarlari, olaylari_oku  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from notify import (  # noqa: E402
    TelegramHatasi,
    env_oku,
    hurdle_eksik_mesaji,
    idempotent_gonder,
    mesaj_gonder,
    ozet_mesaji,
    ucgenleme_durdurma_mesaji,
)
from portfolio import (  # noqa: E402
    portfoyu_hesapla,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from report import OZET_BASLANGIC, OZET_BITIS, rapor_olustur, sistem_ozeti  # noqa: E402
from risk import riski_hesapla  # noqa: E402
from sinyal import (  # noqa: E402
    gecmisi_oku,
    gecmisi_yaz,
    karar_anahtarlari,
    kararlari_uret,
    ozet_anahtari,
    simdi_utc,
)

SISTEM_DOSYASI = PROJE_DIZINI / "00-sistem.md"
SIM_DIZINI = PROJE_DIZINI / "simulasyon"
SIM_DEFTERI = SIM_DIZINI / "islemler.yaml"
SIM_OLAY_DEFTERI = SIM_DIZINI / "kurumsal-olaylar.yaml"
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


def _durumu_yukle(sim: bool, olaylar, nakit_getirisi_yillik: float | None):
    if not sim:
        return None
    islemler, baslangic_nakit, komisyon, baslangic = islemleri_oku(SIM_DEFTERI)
    return durumu_hesapla(islemler, baslangic_nakit, komisyon, olaylar,
                          nakit_getirisi_yillik=nakit_getirisi_yillik,
                          baslangic_tarihi=baslangic,
                          bugun=date.today().isoformat())


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
    olaylar = olaylari_oku(SIM_OLAY_DEFTERI)
    ortam = env_oku()
    rapor_adi = date.today().isoformat()
    baslik = f"{'Simulasyon' if argumanlar.sim else 'Portfoy'} {rapor_adi}"

    # Hurdle rate ZORUNLU: yoksa getiri sifira gore olculur ve her pozitif
    # sonuc "basari" gorunur. Once canli TCMB, olmazsa varliklar.yaml yedegi.
    maliyet = maliyet_modelini_coz(yapilandirma)
    if maliyet.tl_risksiz_yillik is None:
        print("HATA - TL risksiz getiri (hurdle rate) yok, rapor uretilmedi.",
              file=sys.stderr)
        print(f"  Canli seri: {maliyet.risksiz_serisi or '(tanimsiz)'}",
              file=sys.stderr)
        print("  Yedek: varliklar.yaml -> maliyet.firsat.tl_risksiz_yillik",
              file=sys.stderr)
        try:
            mesaj_gonder(hurdle_eksik_mesaji(baslik, maliyet.risksiz_serisi), ortam)
        except TelegramHatasi as hata:
            print(f"UYARI - Telegram uyarisi da gonderilemedi: {hata}",
                  file=sys.stderr)
        return 1
    for uyari in maliyet.uyarilar:
        print(f"UYARI - {uyari}")

    durum = _durumu_yukle(argumanlar.sim, olaylar, maliyet.tl_risksiz_yillik)

    print(f"{len(yapilandirma.fiyat_sembolleri)} sembol icin fiyat cekiliyor...")
    # Deftere yazilmis olaylar otomatik tespiti tetiklemez - yoksa kayitli bir
    # bedelsizden sonra o sembolun degerlemesi sonsuza kadar durur.
    fiyatlar = fiyatlari_getir(yapilandirma, bilinen_olay_anahtarlari(olaylar), ortam)
    # Ucgenleme durdurdu: uc kaynak da taze ama birbirini tutmuyor. Rapor
    # URETILMEZ. Kaynaklardan biri eksik/bayat olsaydi durum OLCULEMEDI olur
    # ve rapor uretilirdi - CoinGecko'nun bir hikkirigi tum gunun raporunu
    # (BIST, altin, Nasdaq dahil) sildirmesin diye ayrim var.
    if fiyatlar.ucgenleme.durduranlar:
        mesaj = ucgenleme_durdurma_mesaji(fiyatlar.ucgenleme.durduranlar, baslik)
        print("HATA - ucgenleme durdurdu, rapor uretilmedi:", file=sys.stderr)
        for sonuc in fiyatlar.ucgenleme.durduranlar:
            print(f"  {sonuc.sembol}: {sonuc.gerekce}", file=sys.stderr)
        try:
            mesaj_gonder(mesaj, ortam)
            print("Telegram uyarisi gonderildi.")
        except TelegramHatasi as hata:
            print(f"UYARI - Telegram uyarisi da gonderilemedi: {hata}",
                  file=sys.stderr)
        return 1

    portfoy = (
        portfoyu_ledgerdan_hesapla(yapilandirma, fiyatlar, durum)
        if durum
        else portfoyu_hesapla(yapilandirma, fiyatlar)
    )
    sapmalar = sinif_sapmalari(portfoy, yapilandirma.hedef_dagilim)
    risk = riski_hesapla(yapilandirma, fiyatlar, portfoy)

    # Sinyal karari TEK noktada verilir; rapor ve Telegram yalnizca render eder.
    simdi = simdi_utc()
    karar = kararlari_uret(sapmalar, risk, yapilandirma.esikler,
                           yapilandirma.bekleme, yapilandirma.devre_kesici,
                           gecmisi_oku(), rapor_adi, maliyet, simdi)
    for uyari in karar.uyarilar:
        print(f"UYARI - {uyari}")

    rapor_dizini = SIM_RAPOR_DIZINI if durum else RAPOR_DIZINI
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    rapor_dosyasi = rapor_dizini / f"{rapor_adi}.md"
    rapor_dosyasi.write_text(
        rapor_olustur(yapilandirma, fiyatlar, portfoy, sapmalar, risk, karar,
                      durum, maliyet),
        encoding="utf-8",
    )
    # Latch/bekleme/sayac hafizasi rapor yazildiktan SONRA kalicilasir: rapor
    # uretilemezse sinyal "uretilmis" sayilmamali.
    gecmisi_yaz(karar.gecmis)

    if not durum:
        _sistem_ozetini_guncelle(sistem_ozeti(portfoy, risk, rapor_adi))

    print(f"Rapor yazildi: {rapor_dosyasi}")
    if karar.devre_kesildi:
        print(f"UYARI - devre kesici: {karar.gunluk_sayi} sinyal olustu "
              f"(tavan {karar.gunluk_maks}), sinyal uretimi durduruldu.")
    if fiyatlar.eksik_semboller:
        print(f"UYARI - fiyat gelmeyen sembol: {', '.join(fiyatlar.eksik_semboller)}")
    for sembol, gerekce in sorted(fiyatlar.kurumsal_olay_supheleri.items()):
        print(f"UYARI - olasi kurumsal olay, degerleme durduruldu: {sembol} ({gerekce})")

    if argumanlar.telegram:
        anahtar = ozet_anahtari(rapor_adi)
        try:
            gonderildi = idempotent_gonder(
                ozet_mesaji(portfoy, sapmalar, risk, karar, durum, baslik,
                            fiyatlar, yapilandirma.bayatlik, maliyet),
                anahtar, karar_anahtarlari(karar, simdi), ortam, simdi=simdi)
            if gonderildi:
                print("Telegram ozeti gonderildi.")
            else:
                # Sessizce atlamak yanlis olur: kosuyu elle tekrarlayan kisi
                # mesaji bekler ve gelmeyince sistemi bozuk sanir.
                print(f"Telegram ozeti ATLANDI - '{anahtar}' zaten gonderilmis.")
                print("  Yeniden gondermek icin bu satiri gonderilen.log'dan sil.")
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
