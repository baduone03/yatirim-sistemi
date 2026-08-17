"""Simulasyon islem defteri: alis/satislari okur, guncel pozisyon durumunu cikarir.

Defter append-only'dir - gecmis islem duzeltilmez, ters islemle kapatilir.
Maliyet agirlikli ortalama yontemiyle tutulur ve islem anindaki TL fiyati
uzerinden kaydedilir (yani kur farki maliyete dahildir).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from kurumsal_olay import KurumsalOlay
from maliyet import donem_orani

ALIS = "AL"
SATIS = "SAT"


@dataclass(frozen=True)
class Islem:
    tarih: str
    yon: str
    sembol: str
    adet: float
    fiyat_try: float
    gerekce: str

    @property
    def tutar_try(self) -> float:
        return self.adet * self.fiyat_try


@dataclass(frozen=True)
class LedgerPozisyonu:
    sembol: str
    adet: float
    maliyet_try: float           # kalan adetin toplam maliyeti


@dataclass(frozen=True)
class LedgerDurumu:
    pozisyonlar: dict[str, LedgerPozisyonu]
    nakit_try: float
    baslangic_nakit_try: float
    gerceklesen_kar_try: float
    toplam_komisyon_try: float
    islemler: list[Islem]
    komisyon_orani: float
    uygulanan_olaylar: list[KurumsalOlay] = field(default_factory=list)
    nakit_getirisi_try: float = 0.0
    nakit_getirisi_yillik: float | None = None
    baslangic_tarihi: str = ""


def islemleri_oku(dosya: Path) -> tuple[list[Islem], float, float, str]:
    """Defteri okur; (islemler, baslangic_nakit, komisyon_orani, baslangic_tarihi)."""
    if not dosya.exists():
        raise FileNotFoundError(f"Islem defteri yok: {dosya}")
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8"))

    islemler = [
        Islem(
            tarih=str(kayit["tarih"]),
            yon=kayit["yon"].upper(),
            sembol=kayit["sembol"],
            adet=float(kayit["adet"]),
            fiyat_try=float(kayit["fiyat_try"]),
            gerekce=kayit.get("gerekce", ""),
        )
        for kayit in ham.get("islemler") or []
    ]
    for islem in islemler:
        if islem.yon not in (ALIS, SATIS):
            raise ValueError(f"{islem.tarih} {islem.sembol}: yon AL veya SAT olmali")
        if islem.adet <= 0 or islem.fiyat_try <= 0:
            raise ValueError(f"{islem.tarih} {islem.sembol}: adet ve fiyat pozitif olmali")

    sirali = sorted(islemler, key=lambda i: i.tarih)
    # Sermayenin var oldugu tarih. Ilk islemden ONCE de nakit faiz isler;
    # ilk islem tarihini baslangic saymak o donemi kaybettirir.
    varsayilan_baslangic = sirali[0].tarih if sirali else ""
    return (
        sirali,
        float(ham["baslangic_nakit_try"]),
        float(ham.get("komisyon_orani", 0.0)),
        str(ham.get("baslangic_tarihi", varsayilan_baslangic)),
    )


def _alis_uygula(mevcut: LedgerPozisyonu | None, islem: Islem) -> LedgerPozisyonu:
    if mevcut is None:
        return LedgerPozisyonu(islem.sembol, islem.adet, islem.tutar_try)
    return LedgerPozisyonu(
        sembol=islem.sembol,
        adet=mevcut.adet + islem.adet,
        maliyet_try=mevcut.maliyet_try + islem.tutar_try,
    )


def _satis_uygula(mevcut: LedgerPozisyonu | None, islem: Islem) -> tuple[LedgerPozisyonu, float]:
    """Satisi uygular; (kalan pozisyon, gerceklesen kar) doner."""
    if mevcut is None or islem.adet > mevcut.adet + 1e-9:
        elde = 0.0 if mevcut is None else mevcut.adet
        raise ValueError(
            f"{islem.tarih} {islem.sembol}: {islem.adet:g} satilamaz, elde {elde:g} var"
        )
    birim_maliyet = mevcut.maliyet_try / mevcut.adet
    cikan_maliyet = birim_maliyet * islem.adet
    kalan = LedgerPozisyonu(
        sembol=islem.sembol,
        adet=mevcut.adet - islem.adet,
        maliyet_try=mevcut.maliyet_try - cikan_maliyet,
    )
    return kalan, islem.tutar_try - cikan_maliyet


def _olayi_uygula(mevcut: LedgerPozisyonu | None,
                  olay: KurumsalOlay) -> LedgerPozisyonu | None:
    """Bedelsiz/split uygular: adet oranla carpilir, TOPLAM MALIYET DEGISMEZ.

    Toplam maliyeti orana bolmek yaygin ve pahali bir hatadir. 1000 TL'ye
    alinan 10 lot, 2.0 oranli bedelsizden sonra 20 lottur ama maliyeti yine
    1000 TL'dir - cebinden para cikmadi. Maliyeti 500'e dusurmek, olmayan
    %100 kar uydurur. Birim maliyet zaten toplam/adet olarak turetilir ve
    dogru sekilde yariya iner.

    Elde pozisyon yoksa olay bu portfoyu ilgilendirmez (olay defteri tum
    piyasa icin tutulabilir).
    """
    if mevcut is None:
        return None
    return LedgerPozisyonu(
        sembol=mevcut.sembol,
        adet=mevcut.adet * olay.oran,
        maliyet_try=mevcut.maliyet_try,
    )


def _zaman_cizgisi(islemler: list[Islem],
                   olaylar: list[KurumsalOlay]) -> list[tuple[str, int, object]]:
    """Islem ve olaylari tarih sirasina dizer.

    Ayni tarihte olay islemden ONCE gelir (sira 0 vs 1): olayin tarihi
    ex-tarihtir, o gun piyasa zaten duzeltilmis fiyatla acilir, dolayisiyla
    ayni gun yapilan alim zaten yeni adet duzeninde yapilmistir.

    Sira onemli: olaylari sonradan topluca uygulamak, olaydan SONRA alinan
    lotlari da carpar. 4:1 split'ten sonra alinan 10 lot 40 lot gorunur.
    """
    return sorted(
        [(o.tarih, 0, o) for o in olaylar] + [(i.tarih, 1, i) for i in islemler],
        key=lambda k: (k[0], k[1]),
    )


def _faiz(bakiye: float, baslangic: str, bitis: str, yillik: float) -> float:
    """Iki tarih arasinda nakit bakiyesinin getirisi. Bilesik.

    Negatif veya sifir gun 0 doner: defterdeki ayni gunlu islemler arasinda
    faiz islememeli, ve baslangic tarihi ilk islemden sonraysa geriye dogru
    faiz uretilmemeli.
    """
    if bakiye <= 0 or not baslangic or not bitis:
        return 0.0
    gun = (date.fromisoformat(bitis) - date.fromisoformat(baslangic)).days
    return bakiye * donem_orani(yillik, gun) if gun > 0 else 0.0


def durumu_hesapla(islemler: list[Islem], baslangic_nakit: float,
                   komisyon_orani: float,
                   olaylar: list[KurumsalOlay] | None = None,
                   nakit_getirisi_yillik: float | None = None,
                   baslangic_tarihi: str = "",
                   bugun: str = "") -> LedgerDurumu:
    """Defteri yurutup guncel durumu cikarir.

    `nakit_getirisi_yillik` verilirse yatirilmamis TL bos durmaz: her islem
    araliginda bakiyeye faiz islenir. Nakti sifir getiriyle modellemek
    "nakitte beklemek maliyetsiz" yanilgisi uretir ve sistemi gereginden
    fazla islem onermeye iter. Verilmezse davranis degismez.
    """
    pozisyonlar: dict[str, LedgerPozisyonu] = {}
    nakit = baslangic_nakit
    gerceklesen = 0.0
    komisyon_toplami = 0.0
    uygulananlar: list[KurumsalOlay] = []
    nakit_getirisi = 0.0
    faiz_acik = nakit_getirisi_yillik is not None and bool(baslangic_tarihi)
    son_faiz_tarihi = baslangic_tarihi

    for tarih, tur, kayit in _zaman_cizgisi(islemler, olaylar or []):
        if faiz_acik:
            kazanc = _faiz(nakit, son_faiz_tarihi, tarih, nakit_getirisi_yillik)
            nakit += kazanc
            nakit_getirisi += kazanc
            son_faiz_tarihi = tarih
        if tur == 0:
            olay: KurumsalOlay = kayit
            yeni = _olayi_uygula(pozisyonlar.get(olay.sembol), olay)
            if yeni is not None:
                pozisyonlar[olay.sembol] = yeni
                uygulananlar.append(olay)
            continue

        islem: Islem = kayit
        komisyon = islem.tutar_try * komisyon_orani
        komisyon_toplami += komisyon
        mevcut = pozisyonlar.get(islem.sembol)

        if islem.yon == ALIS:
            nakit -= islem.tutar_try + komisyon
            pozisyonlar[islem.sembol] = _alis_uygula(mevcut, islem)
        else:
            nakit += islem.tutar_try - komisyon
            kalan, kar = _satis_uygula(mevcut, islem)
            gerceklesen += kar - komisyon
            pozisyonlar[islem.sembol] = kalan

        if nakit < -1e-6:
            raise ValueError(
                f"{islem.tarih} {islem.sembol}: nakit yetersiz ({nakit:,.2f} TL)"
            )

    # Son islemden bugune kadar kalan sure de faiz isler.
    if faiz_acik and bugun:
        kazanc = _faiz(nakit, son_faiz_tarihi, bugun, nakit_getirisi_yillik)
        nakit += kazanc
        nakit_getirisi += kazanc

    return LedgerDurumu(
        pozisyonlar={s: p for s, p in pozisyonlar.items() if p.adet > 1e-12},
        nakit_try=nakit,
        baslangic_nakit_try=baslangic_nakit,
        gerceklesen_kar_try=gerceklesen,
        toplam_komisyon_try=komisyon_toplami,
        islemler=islemler,
        komisyon_orani=komisyon_orani,
        uygulanan_olaylar=uygulananlar,
        nakit_getirisi_try=nakit_getirisi,
        nakit_getirisi_yillik=nakit_getirisi_yillik,
        baslangic_tarihi=baslangic_tarihi or (islemler[0].tarih if islemler else ""),
    )
