"""Yatirim raporu uretir.

Kullanim:
    python scripts/yatirim/main.py           # gercek portfoy (portfoy.yaml)
    python scripts/yatirim/main.py --sim     # simulasyon defteri (islemler.yaml)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bildirim import ayarlari_oku  # noqa: E402
from config import (  # noqa: E402
    PROJE_DIZINI,
    RAPOR_DIZINI,
    TR_OFSET,
    sablonu_reddet,
    yapilandirmayi_oku,
)
from fetch import fiyatlari_getir, maliyet_modelini_coz  # noqa: E402
from kurumsal_olay import bilinen_olay_anahtarlari, olaylari_oku  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from maliyet import donem_orani  # noqa: E402
from mesaj import (  # noqa: E402
    Etki,
    GunSonuOzeti,
    IslemOnerisi,
    Tetikleyici,
    hurdle_eksik_mesaji,
    ucgenleme_durdurma_mesaji,
    uyarilari_topla,
)
from notify import (  # noqa: E402
    TelegramHatasi,
    env_oku,
    gonder_gun_sonu,
    gonder_islem_karari,
    gonder_uyari,
    kuyrugu_bosalt,
    mesaj_gonder,
)
from piyasa import BRIFING, TARAMA  # noqa: E402
from portfolio import (  # noqa: E402
    degisim_24s,
    kur_ayristir,
    kur_maruziyeti,
    portfoyu_hesapla,
    portfoyu_ledgerdan_hesapla,
    sinif_sapmalari,
)
from duyarlilik import duyarliligi_olc, referans_pozisyonlar  # noqa: E402
from report import (  # noqa: E402
    OZET_BASLANGIC,
    OZET_BITIS,
    donem_gunu,
    rapor_olustur,
    sistem_ozeti,
)
from risk import riski_hesapla  # noqa: E402
from sinyal import (  # noqa: E402
    SEMBOL,
    gecmisi_oku,
    gecmisi_yaz,
    kararlari_uret,
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


@dataclass(frozen=True)
class HurdleEngeli:
    gerekce: str
    mesaj: str


def hurdle_engeli(maliyet, baslik: str, bugun: date | None = None
                  ) -> HurdleEngeli | None:
    """Hurdle rate rapor uretmeye YETERLI mi? Degilse engeli doner.

    Iki ayri kusur, tek sonuc: yok da olmaz, BAYAT da olmaz. Bayatlik daha
    sinsi - rapor uretilir, sayilar makul gorunur, kararlar sessizce yanlis
    cikar. Bu sayi gereken getiriyi, asiri getiriyi, nakit getirisini ve
    sinyal kapisini birden belirliyor.

    Ayri fonksiyon olmasinin sebebi test edilebilirlik: kapinin kendisi
    sinanabilmeli, "main.py'de bir yerde bir if var" yeterli degil.
    """
    if maliyet.risksiz_taze_mi(bugun):
        return None
    bayat = maliyet.tl_risksiz_yillik is not None
    return HurdleEngeli(
        gerekce=("TL risksiz getiri (hurdle rate) BAYAT" if bayat
                 else "TL risksiz getiri (hurdle rate) yok"),
        mesaj=hurdle_eksik_mesaji(
            baslik, maliyet.risksiz_serisi,
            maliyet.risksiz_tarih if bayat else "",
            maliyet.risksiz_bayatlik_gun),
    )


def _durumu_yukle(sim: bool, olaylar, nakit_getirisi_yillik: float | None,
                  bugun: str):
    if not sim:
        return None
    islemler, baslangic_nakit, komisyon, baslangic = islemleri_oku(SIM_DEFTERI)
    return durumu_hesapla(islemler, baslangic_nakit, komisyon, olaylar,
                          nakit_getirisi_yillik=nakit_getirisi_yillik,
                          baslangic_tarihi=baslangic, bugun=bugun)


def _islem_onerileri(karar, fiyatlar, portfoy, risk, yapilandirma, maliyet,
                     ayarlar, ortam, simdi) -> int:
    """Acik her sinyal icin ayri islem karari bildirimi. Doner: giden sayisi.

    Sinyal yoksa HICBIR mesaj gitmez - "bugun islem yok" demek gurultudur,
    gun sonu ozeti zaten portfoyun durumunu soyluyor.
    """
    son_fiyatlar = fiyatlar.son_fiyatlar
    agirliklar = {p.sembol: p.deger_try / portfoy.toplam_deger_try
                  for p in portfoy.pozisyonlar} if portfoy.toplam_deger_try else {}
    riskler = {r.sembol: r for r in risk.varlik_riskleri}
    giden = 0
    for sonuc in karar.sinyaller(SEMBOL):
        fiyat = son_fiyatlar.get(sonuc.ad)
        varlik_riski = riskler.get(sonuc.ad)
        if fiyat is None or varlik_riski is None:
            continue
        # Kisma miktari: agirligi hedef katkiya indirecek tutar. Kaba ama
        # somut - "azalt" demek ne kadar azaltacagini soylemiyorsa emir degil.
        hedef_agirlik = (yapilandirma.esikler.risk_katkisi_ust
                         / varlik_riski.beta if varlik_riski.beta else 0.0)
        azalt_try = max(
            (agirliklar.get(sonuc.ad, 0.0) - hedef_agirlik)
            * portfoy.toplam_deger_try, 0.0)
        islem = IslemOnerisi(
            sembol=sonuc.ad, yon="SAT", adet=azalt_try / fiyat,
            fiyat_try=fiyat, veri_zamani=fiyatlar.son_tarih,
            veri_kaynagi=_veri_kaynagi(fiyatlar, sonuc.ad))
        gidis_donus = maliyet.gidis_donus(sonuc.ad, azalt_try, fiyatlar.usdtry)
        sonuc_gonderim = gonder_islem_karari(
            islem,
            [Tetikleyici("Risk katkisi", varlik_riski.risk_katkisi,
                         yapilandirma.esikler.risk_katkisi_ust),
             Tetikleyici("Beta", varlik_riski.beta,
                         yapilandirma.esikler.risk_beta_ust, "sayi")],
            [Etki("Agirlik", agirliklar.get(sonuc.ad, 0.0), hedef_agirlik),
             Etki("Risk katkisi", varlik_riski.risk_katkisi,
                  yapilandirma.esikler.risk_katkisi_ust)],
            gidis_donus,
            azalt_try * gidis_donus / 2 if gidis_donus is not None else None,
            ayarlar=ayarlar, env=ortam, simdi=simdi)
        print(f"  islem karari {sonuc.ad}: {sonuc_gonderim.durum}")
        giden += 1
    return giden


def _veri_kaynagi(fiyatlar, sembol: str) -> str:
    """Fiyatin nereden geldigi. Kripto BTCTurk'ten ezilmis olabilir."""
    if sembol in {s.sembol for s in fiyatlar.ucgenleme.sonuclar}:
        return "btcturk/yahoo (ucgenlenmis)"
    return "yahoo (gunluk kapanis)"


def _bildirimleri_gonder(yapilandirma, fiyatlar, portfoy, risk, karar, durum,
                         maliyet, ayarlar, ortam, simdi, gorev, rapor_adi,
                         duyarlilik=None) -> None:
    """Gorev tipine gore bildirim gonderir.

    TARAMA: yalnizca islem kararlari. Her tarama kosusunda tam ozet gondermek
    gunde 12 ayni mesaj demek - okunmaz.
    GUN_SONU / BRIFING: portfoy durumu + tum uyarilar.
    """
    uyarilar = uyarilari_topla(fiyatlar, portfoy, karar, maliyet,
                              yapilandirma.bayatlik, risk, duyarlilik)
    giden = _islem_onerileri(karar, fiyatlar, portfoy, risk, yapilandirma,
                             maliyet, ayarlar, ortam, simdi)

    if gorev == TARAMA:
        # Uyarilar gun sonunda toplu gidiyor; tarama kosusunda yalnizca
        # ACIL olanlar (devre kesici) ayri mesaj hak eder.
        if karar.devre_kesildi:
            gonder_uyari("devre", uyarilar[0], ayarlar, ortam, simdi)
        print(f"Tarama: {giden} islem karari gonderildi.")
        return

    gun = donem_gunu(yapilandirma, durum)
    risksiz = (donem_orani(maliyet.tl_risksiz_yillik, gun)
               if maliyet.tl_risksiz_yillik is not None and gun > 0 else None)
    taban = durum.baslangic_nakit_try if durum else portfoy.toplam_maliyet_try
    getiri = (portfoy.toplam_deger_try - taban) / taban if taban else None
    ozet = GunSonuOzeti(
        portfoy=portfoy,
        risk=risk,
        veri_zamani=fiyatlar.son_tarih,
        degisim_24s=degisim_24s(portfoy, fiyatlar),
        asiri_getiri=(getiri - risksiz
                      if getiri is not None and risksiz is not None else None),
        risksiz=risksiz,
        donem_gun=gun,
        komisyon_try=durum.toplam_komisyon_try if durum else None,
        kur_maruziyeti=kur_maruziyeti(portfoy, yapilandirma.varliklar),
        ayrimlar=kur_ayristir(fiyatlar, yapilandirma.varliklar,
                              [p.sembol for p in portfoy.pozisyonlar], gun),
        uyarilar=uyarilar,
        baslik=("🌅 Pazartesi acilis brifingi" if gorev == BRIFING
                else "🌙 Gun sonu"),
    )
    sonuc = gonder_gun_sonu(ozet, ayarlar, ortam, simdi, gun=rapor_adi)
    print(f"{ozet.baslik}: {sonuc.durum} ({giden} islem karari da gonderildi)")


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

    # Bildirim politikasi ve takvim. Gorev tipi saate gore belirlenir: TEK
    # workflow calisir, ne yapacagini script secer.
    simdi = simdi_utc()
    # "Gun" TR gunudur, UTC gunu DEGIL. Actions UTC'de calisiyor; date.today()
    # kullanilsaydi TR 00:00-03:00 arasindaki kosular bir onceki gunun rapor
    # dosyasina yazar, gunluk sinyal sayaci TR 03:00'te sifirlanirdi. Ayrica
    # yerel makine TR saatinde, Actions UTC'de calistigi icin ayni gun iki
    # farkli isim uretirdi.
    rapor_adi = (simdi + TR_OFSET).date().isoformat()
    baslik = f"{'Simulasyon' if argumanlar.sim else 'Portfoy'} {rapor_adi}"
    bildirim_ayarlari = ayarlari_oku()
    gorev = bildirim_ayarlari.takvim.gorev(simdi)
    acik = bildirim_ayarlari.takvim.acik_seanslar(simdi)
    print(f"Gorev: {gorev} | acik seans: {', '.join(acik) or 'yok'}")

    # Sessiz saatte biriken bildirimler her kosunun BASINDA bosaltilir.
    # Bosaltilmazsa gece biriken uyarilar diskte kalir ve hic gonderilmez.
    if argumanlar.telegram:
        try:
            bosaltma = kuyrugu_bosalt(bildirim_ayarlari, ortam, simdi=simdi)
            if bosaltma.gonderilen:
                print(f"Biriken {bosaltma.gonderilen} bildirim gonderildi.")
        except TelegramHatasi as hata:
            print(f"UYARI - biriken bildirimler gonderilemedi: {hata}")

    # Hurdle rate ZORUNLU: yoksa getiri sifira gore olculur ve her pozitif
    # sonuc "basari" gorunur. Once canli TCMB, olmazsa varliklar.yaml yedegi.
    maliyet = maliyet_modelini_coz(yapilandirma)
    engel = hurdle_engeli(maliyet, baslik)
    if engel:
        print(f"HATA - {engel.gerekce}, rapor uretilmedi.", file=sys.stderr)
        print(f"  Canli seri: {maliyet.risksiz_serisi or '(tanimsiz)'}",
              file=sys.stderr)
        print("  Yedek: varliklar.yaml -> maliyet.firsat.tl_risksiz_yillik",
              file=sys.stderr)
        try:
            mesaj_gonder(engel.mesaj, ortam)
        except TelegramHatasi as hata:
            print(f"UYARI - Telegram uyarisi da gonderilemedi: {hata}",
                  file=sys.stderr)
        return 1
    for uyari in maliyet.uyarilar:
        print(f"UYARI - {uyari}")

    durum = _durumu_yukle(argumanlar.sim, olaylar,
                      maliyet.tl_risksiz_yillik, rapor_adi)

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
    risk = riski_hesapla(yapilandirma, fiyatlar, portfoy, olaylar)

    # Maliyet duyarliligi: tahminli kalemler karari ceviriyor mu?
    # Ceviriyorsa sinyal bastirilir ve raporda hangi parametrenin
    # olculmesi gerektigi yazar.
    duyarlilik = duyarliligi_olc(
        maliyet, yapilandirma.esikler.rebalancing_sapma,
        referans_pozisyonlar(portfoy, yapilandirma.hedef_dagilim,
                             yapilandirma.sinif_haritasi,
                             maliyet.referans_pozisyon_try),
        fiyatlar.usdtry)

    # Sinyal karari TEK noktada verilir; rapor ve Telegram yalnizca render eder.
    karar = kararlari_uret(sapmalar, risk, yapilandirma.esikler,
                           yapilandirma.bekleme, yapilandirma.devre_kesici,
                           gecmisi_oku(), rapor_adi, maliyet, simdi,
                           duyarlilik)
    for uyari in karar.uyarilar:
        print(f"UYARI - {uyari}")

    # Rapor YALNIZCA gun sonu/brifing kosusunda yazilir. Tarama kosusu gunde 12
    # kez calisiyor ve rapor dosyasi tarihe gore adlandirildigi icin her kosu
    # aynı dosyayi yeniden yazardi: 12 anlamsiz commit, hepsi bir sonrakinin
    # ustune. Taramanin isi sinyal tespiti, rapor uretimi degil.
    if gorev != TARAMA:
        rapor_dizini = SIM_RAPOR_DIZINI if durum else RAPOR_DIZINI
        rapor_dizini.mkdir(parents=True, exist_ok=True)
        rapor_dosyasi = rapor_dizini / f"{rapor_adi}.md"
        rapor_dosyasi.write_text(
            rapor_olustur(yapilandirma, fiyatlar, portfoy, sapmalar, risk, karar,
                          durum, maliyet, duyarlilik),
            encoding="utf-8",
        )
        if not durum:
            _sistem_ozetini_guncelle(sistem_ozeti(portfoy, risk, rapor_adi))
        print(f"Rapor yazildi: {rapor_dosyasi}")

    # Latch/bekleme/sayac hafizasi her kosuda kalicilasir - tarama kosusunda
    # rapor yazilmasa da sinyal uretildi ve bekleme saati islemeye basladi.
    gecmisi_yaz(karar.gecmis)
    if karar.devre_kesildi:
        print(f"UYARI - devre kesici: {karar.gunluk_sayi} sinyal olustu "
              f"(tavan {karar.gunluk_maks}), sinyal uretimi durduruldu.")
    if fiyatlar.eksik_semboller:
        print(f"UYARI - fiyat gelmeyen sembol: {', '.join(fiyatlar.eksik_semboller)}")
    for sembol, gerekce in sorted(fiyatlar.kurumsal_olay_supheleri.items()):
        print(f"UYARI - olasi kurumsal olay, degerleme durduruldu: {sembol} ({gerekce})")

    if argumanlar.telegram:
        try:
            _bildirimleri_gonder(yapilandirma, fiyatlar, portfoy, risk, karar,
                                 durum, maliyet, bildirim_ayarlari, ortam,
                                 simdi, gorev, rapor_adi, duyarlilik)
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
