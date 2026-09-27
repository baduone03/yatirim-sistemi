"""Karar sonuc takibi: her karari 5/10/15/20/25/30. gunde olcer.

Tasarim ilkesi (eski Yildiz Pazar botunun hatasindan): kontrol gununde
esik tetiklensin veya tetiklenmesin FIYAT VE PORTFOY DEGERI KAYDEDILIR.
O bot vadesi dolan 377 sinyalin outcome_price'ini NULL biraktigi icin
verisinin %88'i olcum icin kullanilamaz hale gelmisti.

Olcumler gecmis fiyat serisinden yapilir, "bugun" fiyatindan degil.
Boylece sistem birkac gun kapali kalsa bile kacan kontrol gunleri
geriye donuk doldurulur.

Kullanim:
    python scripts/yatirim/karar_takip.py            # olcum + rapor
    python scripts/yatirim/karar_takip.py --rapor    # yalnizca rapor
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PROJE_DIZINI, yapilandirmayi_oku  # noqa: E402
from fetch import fiyatlari_getir  # noqa: E402
from ledger import durumu_hesapla, islemleri_oku  # noqa: E402
from fetch import FiyatVerisi  # noqa: E402
from portfolio import Portfoy, PozisyonDegeri, portfoyu_ledgerdan_hesapla  # noqa: E402
from risk import riski_hesapla  # noqa: E402

SIM_DIZINI = PROJE_DIZINI / "simulasyon"
KARARLAR_DOSYASI = SIM_DIZINI / "kararlar.yaml"
OLCUMLER_DOSYASI = SIM_DIZINI / "kararlar-olcum.yaml"
RAPOR_DOSYASI = SIM_DIZINI / "00-karar-sonuclari.md"
DEFTER_DOSYASI = SIM_DIZINI / "islemler.yaml"

KONTROL_GUNLERI = (5, 10, 15, 20, 25, 30)

# Bu tarihten itibaren her karar `bozan_kosul` tasimak ZORUNDA. Oncekiler
# muaf: kosulu sonucu gordukten sonra yazmak tezi sonradan uydurmaktir.
BOZAN_KOSUL_ZORUNLU = date(2026, 9, 28)

PORTFOY_GETIRISI = "portfoy_getirisi"
TAKAS_FARKI = "takas_farki"
SEMBOL_GETIRISI = "getiri:"          # getiri:TUPRS.IS
VOLATILITE = "volatilite:"           # volatilite:portfoy | :bist | :TUPRS.IS
RISK_KATKISI = "risk_katkisi:"       # risk_katkisi:ASELS.IS
RISK_OLCUTLERI = (VOLATILITE, RISK_KATKISI)
PORTFOY = "portfoy"
ALTI, USTU = "alti", "ustu"


@dataclass(frozen=True)
class BozanKosul:
    """Karari YANLIS cikaracak olculebilir durum. Karar ANINDA yazilir.

    Beklenti "ne olmali" der; bozan kosul "ne olursa yanildim" der. Beklenti
    serbest metindir ve tutup tutmadigina okuyan karar verir - bu yuzden her
    sonuc beklentiyi "aslinda tuttu" diye okumaya musaittir. Bozan kosul
    makine tarafindan her kontrol gununde denetlenir; yoruma yer birakmaz.
    """

    olcut: str
    yon: str
    esik: float
    aciklama: str = ""

    @property
    def risk_mi(self) -> bool:
        """Risk olcutu gecmis fiyattan TURETILEMEZ, olcum aninda hesaplanip
        `Olcum.kosul_degeri` olarak saklanir."""
        return self.olcut.startswith(RISK_OLCUTLERI)

    @property
    def hedef(self) -> str:
        return self.olcut.split(":", 1)[1] if ":" in self.olcut else ""

    def deger(self, karar: "Karar", olcum: "Olcum") -> float | None:
        """Olcutun o olcumdeki degeri. Veri yoksa None - 'tutuyor' SAYILMAZ."""
        if self.risk_mi:
            return olcum.kosul_degeri
        if self.olcut == PORTFOY_GETIRISI:
            return olcum.portfoy_getirisi
        if self.olcut == TAKAS_FARKI:
            semboller = [*karar.alinan, *karar.satilan]
            if not all(s in olcum.getiriler for s in semboller):
                return None
            return takas_farki(karar, olcum)
        return olcum.getiriler.get(self.hedef)

    def tetiklendi(self, deger: float) -> bool:
        return deger < self.esik if self.yon == ALTI else deger > self.esik

    @property
    def ad(self) -> str:
        """Okunur ad: 'volatilite:bist' degil 'BIST bacaginin volatilitesi'."""
        hedef = self.hedef
        if self.olcut == PORTFOY_GETIRISI:
            return "Portfoy getirisi"
        if self.olcut == TAKAS_FARKI:
            return "Takas farki (alinan - satilan)"
        if self.olcut.startswith(SEMBOL_GETIRISI):
            return f"{hedef} getirisi"
        if self.olcut.startswith(RISK_KATKISI):
            return f"{hedef} risk katkisi"
        if hedef == PORTFOY:
            return "Portfoy volatilitesi"
        if hedef.islower():
            return f"{hedef.upper()} bacaginin volatilitesi"
        return f"{hedef} volatilitesi"

    def bicim(self, deger: float) -> str:
        """Getiri isaretli (+4.2%), seviye (volatilite, katki) isaretsiz (26.5%)."""
        return f"{deger * 100:.1f}%" if self.risk_mi else f"{deger * 100:+.1f}%"

    def metin(self) -> str:
        yon = "altina inerse" if self.yon == ALTI else "ustune cikarsa"
        return (f"{self.ad} {self.bicim(self.esik)} {yon} tez bozulur"
                + (f" - {self.aciklama}" if self.aciklama else ""))


def _bozan_kosulu_ayristir(ham: dict | None, karar_id: str, alinan: list[str],
                           satilan: list[str],
                           siniflar: set[str] | None = None) -> BozanKosul | None:
    if ham is None:
        return None
    kosul = BozanKosul(
        olcut=str(ham.get("olcut", "")), yon=str(ham.get("yon", "")),
        esik=float(ham["esik"]) if "esik" in ham else float("nan"),
        aciklama=" ".join(str(ham.get("aciklama", "")).split()))
    # Yazim hatasi okuma aninda patlar: sessizce "olculemedi" kalan bir kosul
    # 30 gun boyunca hicbir seyi denetlemez ve kimse fark etmez.
    if kosul.yon not in (ALTI, USTU):
        raise ValueError(f"{karar_id}: bozan_kosul.yon 'alti' veya 'ustu' olmali")
    if kosul.esik != kosul.esik:
        raise ValueError(f"{karar_id}: bozan_kosul.esik eksik (kesir: -0.05 = %-5)")
    if abs(kosul.esik) >= 1:
        raise ValueError(f"{karar_id}: bozan_kosul.esik KESIR olmali, {kosul.esik} geldi "
                         "(-5 degil -0.05, %28 degil 0.28)")
    if kosul.risk_mi and kosul.esik <= 0:
        raise ValueError(f"{karar_id}: {kosul.olcut} bir seviyedir, esik pozitif olmali")
    hedef = kosul.hedef
    sembol_mu = hedef in (*alinan, *satilan)
    if kosul.olcut == TAKAS_FARKI and not (alinan and satilan):
        raise ValueError(f"{karar_id}: takas_farki icin alinan VE satilan dolu olmali")
    if kosul.olcut.startswith((SEMBOL_GETIRISI, RISK_KATKISI)) and not sembol_mu:
        raise ValueError(f"{karar_id}: {kosul.olcut} - sembol alinan/satilan "
                         "listesinde olmali, yoksa fiyati olculmez")
    if kosul.olcut.startswith(VOLATILITE):
        # Sinif adi kucuk harf (bist), sembol buyuk (TUPRS.IS). siniflar
        # verilmediyse (test) yalnizca bu ayrima bakilir.
        sinif_mi = hedef.islower() and (siniflar is None or hedef in siniflar)
        if not (hedef == PORTFOY or sinif_mi or sembol_mu):
            raise ValueError(
                f"{karar_id}: {kosul.olcut} - hedef 'portfoy', bir varlik sinifi "
                f"({', '.join(sorted(siniflar or []))}) veya alinan/satilan "
                "icindeki bir sembol olmali")
    elif not kosul.olcut.startswith((SEMBOL_GETIRISI, RISK_KATKISI)) and \
            kosul.olcut not in (PORTFOY_GETIRISI, TAKAS_FARKI):
        raise ValueError(
            f"{karar_id}: bozan_kosul.olcut gecersiz: '{kosul.olcut}'. Gecerli: "
            f"{PORTFOY_GETIRISI}, {TAKAS_FARKI}, {SEMBOL_GETIRISI}<SEMBOL>, "
            f"{VOLATILITE}<portfoy|sinif|SEMBOL>, {RISK_KATKISI}<SEMBOL>")
    return kosul


@dataclass(frozen=True)
class Karar:
    id: str
    tarih: str
    tip: str
    ozet: str
    beklenti: str
    satilan: list[str]
    alinan: list[str]
    bozan_kosul: BozanKosul | None = None

    @property
    def tarih_gun(self) -> date:
        return datetime.strptime(self.tarih, "%Y-%m-%d").date()


@dataclass(frozen=True)
class Olcum:
    karar_id: str
    gun: int                      # kacinci kontrol gunu (5, 10, ...)
    olcum_tarihi: str
    portfoy_degeri: float
    portfoy_getirisi: float       # karar gununden bu yana
    fiyatlar: dict[str, float]    # ilgili sembollerin o gunku TL fiyati
    getiriler: dict[str, float]   # karar gununden bu yana sembol getirileri
    # Risk tipi bozan kosulun o gunku degeri. Gecmis fiyattan geri turetmek
    # riski_hesapla'yi yeniden kosturmak demek; --rapor modu fiyat cekmez.
    kosul_degeri: float | None = None


def kararlari_oku(dosya: Path = KARARLAR_DOSYASI,
                  siniflar: set[str] | None = None) -> list[Karar]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    kararlar = []
    for k in ham.get("kararlar") or []:
        karar_id = str(k["id"])
        satilan = list(k.get("satilan") or [])
        alinan = list(k.get("alinan") or [])
        karar = Karar(
            id=karar_id,
            tarih=str(k["tarih"]),
            tip=str(k.get("tip", "")),
            ozet=str(k.get("ozet", "")),
            beklenti=" ".join(str(k.get("beklenti", "")).split()),
            satilan=satilan,
            alinan=alinan,
            bozan_kosul=_bozan_kosulu_ayristir(k.get("bozan_kosul"), karar_id,
                                               alinan, satilan, siniflar),
        )
        if karar.bozan_kosul is None and karar.tarih_gun >= BOZAN_KOSUL_ZORUNLU:
            raise ValueError(
                f"{karar_id}: bozan_kosul zorunlu ({BOZAN_KOSUL_ZORUNLU} sonrasi "
                "kararlar). 'Ne olursa yanildim' sorusu karar ANINDA cevaplanir.")
        kararlar.append(karar)
    return kararlar


def takas_farki(karar: Karar, olcum: "Olcum") -> float:
    """Alinanin getirisi - satilanin getirisi. Rapor ve bozan kosul AYNI formul."""
    alinan = sum(olcum.getiriler.get(s, 0.0) for s in karar.alinan)
    satilan = sum(olcum.getiriler.get(s, 0.0) for s in karar.satilan)
    return alinan - satilan


def kosul_durumu(karar: Karar, olcumler: list["Olcum"]) -> str:
    """Bozan kosulun hukmu, tek cumle. Ilk tetiklenme KALICIDIR: sonradan
    toparlanmak tezi geri getirmez - yanildigin an kayitlidir."""
    kosul = karar.bozan_kosul
    if kosul is None or not olcumler:
        return ""
    sirali = sorted(olcumler, key=lambda o: o.gun)
    esik = kosul.bicim(kosul.esik)
    taban = next((o for o in sirali if o.gun == 0), None)
    taban_deger = kosul.deger(karar, taban) if taban else None
    if taban_deger is not None and kosul.tetiklendi(taban_deger):
        # Karar gunu zaten saglanan kosul hicbir seyi test etmez.
        return (f"⚠️ **Kosul anlamsiz:** karar gunu {kosul.ad} zaten "
                f"{kosul.bicim(taban_deger)} idi, sinir {esik}. Yeni karar "
                "yazarken siniri karar gunundeki degerin otesine koy.")

    kontroller = [o for o in sirali if o.gun > 0]
    olculen = []
    for olcum in kontroller:
        deger = kosul.deger(karar, olcum)
        if deger is None:
            continue
        if kosul.tetiklendi(deger):
            return (f"❌ **TEZ BOZULDU** - {olcum.gun}. gunde ({olcum.olcum_tarihi}) "
                    f"{kosul.ad} {kosul.bicim(deger)} oldu, sinir {esik} idi.")
        olculen.append((olcum, deger))
    if not olculen:
        if not kontroller:
            return ""
        return "❔ **Olculemedi** - veri yok. Tutuyor SAYILMAZ."
    son, deger = olculen[-1]
    bas = (f"karar gunu {kosul.bicim(taban_deger)} → "
           if taban_deger is not None else "")
    eksik = [o.gun for o in kontroller if kosul.deger(karar, o) is None]
    ek = f" Olculemeyen gun: {', '.join(map(str, eksik))}." if eksik else ""
    return (f"✅ **Tez tutuyor** - {kosul.ad}: {bas}{son.gun}. gun "
            f"{kosul.bicim(deger)}. Sinir {esik}, araya "
            f"{abs(deger - kosul.esik) * 100:.1f} puan var.{ek}")


def olcumleri_oku(dosya: Path = OLCUMLER_DOSYASI) -> list[Olcum]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    return [
        Olcum(
            karar_id=o["karar_id"], gun=int(o["gun"]), olcum_tarihi=o["olcum_tarihi"],
            portfoy_degeri=float(o["portfoy_degeri"]),
            portfoy_getirisi=float(o["portfoy_getirisi"]),
            fiyatlar={k: float(v) for k, v in (o.get("fiyatlar") or {}).items()},
            getiriler={k: float(v) for k, v in (o.get("getiriler") or {}).items()},
            kosul_degeri=(float(o["kosul_degeri"])
                          if o.get("kosul_degeri") is not None else None),
        )
        for o in (ham.get("olcumler") or [])
    ]


def olcumleri_yaz(olcumler: list[Olcum], dosya: Path = OLCUMLER_DOSYASI) -> None:
    """Olcumleri diske yazar. Makine uretimi - elle duzenlenmez."""
    icerik = {
        "olcumler": [
            {
                "karar_id": o.karar_id, "gun": o.gun, "olcum_tarihi": o.olcum_tarihi,
                "portfoy_degeri": round(o.portfoy_degeri, 2),
                "portfoy_getirisi": round(o.portfoy_getirisi, 6),
                "fiyatlar": {k: round(v, 4) for k, v in o.fiyatlar.items()},
                "getiriler": {k: round(v, 6) for k, v in o.getiriler.items()},
                **({"kosul_degeri": round(o.kosul_degeri, 6)}
                   if o.kosul_degeri is not None else {}),
            }
            for o in sorted(olcumler, key=lambda x: (x.karar_id, x.gun))
        ]
    }
    baslik = (
        "# MAKINE URETIMI - elle duzenleme.\n"
        "# karar_takip.py tarafindan yazilir. Kararlar icin kararlar.yaml'a bak.\n\n"
    )
    dosya.write_text(
        baslik + yaml.safe_dump(icerik, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _fiyat_o_gun(seri: pd.Series, gun: date) -> float | None:
    """Verilen tarihteki son bilinen fiyat. Piyasa kapaliysa onceki gun."""
    gecerli = seri.dropna()
    gecerli = gecerli[gecerli.index.date <= gun]
    return float(gecerli.iloc[-1]) if len(gecerli) else None


def _portfoy_degeri(yapilandirma, fiyatlar, islemler, komisyon: float,
                    baslangic_nakit: float, gun: date) -> float | None:
    """Portfoyun o tarihteki degeri: defteri o gune kadar oynatip degerle."""
    o_gune_kadar = [i for i in islemler if datetime.strptime(i.tarih, "%Y-%m-%d").date() <= gun]
    if not o_gune_kadar:
        return None
    durum = durumu_hesapla(o_gune_kadar, baslangic_nakit, komisyon)

    toplam = durum.nakit_try
    for sembol, pozisyon in durum.pozisyonlar.items():
        if sembol not in fiyatlar.try_gecmis:
            return None
        fiyat = _fiyat_o_gun(fiyatlar.try_gecmis[sembol], gun)
        if fiyat is None:
            return None
        toplam += fiyat * pozisyon.adet
    return toplam


def _risk_olcumu(kosul: BozanKosul, yapilandirma, fiyatlar, islemler,
                 komisyon: float, baslangic_nakit: float, gun: date) -> float | None:
    """Risk olcutunun `gun` tarihindeki degeri - raporla AYNI yontem.

    O gunku pozisyonlar (defter o gune kadar oynatilir) x o gune kadarki
    `gecmis_gun` penceresi -> riski_hesapla. Beklentideki "%29,2'den
    %26,9'a" sayilari da gunluk raporda boyle uretildi; farkli yontemle
    olcmek tezi baska bir sayiyla sinamak olurdu.
    """
    o_gune_kadar = [i for i in islemler
                    if datetime.strptime(i.tarih, "%Y-%m-%d").date() <= gun]
    if not o_gune_kadar:
        return None
    durum = durumu_hesapla(o_gune_kadar, baslangic_nakit, komisyon)
    pozisyonlar = []
    for sembol, pozisyon in durum.pozisyonlar.items():
        varlik = yapilandirma.varliklar.get(sembol)
        fiyat = (_fiyat_o_gun(fiyatlar.try_gecmis[sembol], gun)
                 if sembol in fiyatlar.try_gecmis else None)
        if varlik is None or fiyat is None:
            return None
        pozisyonlar.append(PozisyonDegeri(
            sembol=sembol, ad=varlik.ad, sinif=varlik.sinif, adet=pozisyon.adet,
            maliyet_try=pozisyon.maliyet_try, deger_try=fiyat * pozisyon.adet))

    hedef = kosul.hedef
    nakit = durum.nakit_try
    if kosul.olcut.startswith(VOLATILITE) and hedef != PORTFOY and hedef.islower():
        # Sinif bacagi: yalnizca o sinifin pozisyonlari, nakitsiz.
        pozisyonlar = [p for p in pozisyonlar if p.sinif == hedef]
        nakit = 0.0
        if not pozisyonlar:
            return None

    tarihler = fiyatlar.try_gecmis.index.date
    pencere = ((tarihler <= gun)
               & (tarihler > gun - timedelta(days=yapilandirma.ayarlar.gecmis_gun)))
    kesik = FiyatVerisi(
        try_gecmis=fiyatlar.try_gecmis[pencere], usdtry=fiyatlar.usdtry,
        eksik_semboller=[], kurumsal_olay_supheleri=fiyatlar.kurumsal_olay_supheleri)
    try:
        rapor = riski_hesapla(yapilandirma, kesik,
                              Portfoy(pozisyonlar=pozisyonlar, nakit_try=nakit,
                                      fiyatlanamayan=[]))
    except RuntimeError:
        return None

    if kosul.olcut.startswith(VOLATILITE) and (hedef == PORTFOY or hedef.islower()):
        return float(rapor.portfoy_volatilitesi)   # np.float64 YAML'a yazilamaz
    varlik = next((r for r in rapor.varlik_riskleri if r.sembol == hedef), None)
    if varlik is None:
        return None       # dislandi (kurumsal olay suphesi) veya yetersiz veri
    return float(varlik.yillik_volatilite if kosul.olcut.startswith(VOLATILITE)
                 else varlik.risk_katkisi)


def olcum_yap(karar: Karar, gun_sayisi: int, yapilandirma, fiyatlar,
              islemler, komisyon: float, baslangic_nakit: float) -> Olcum | None:
    olcum_gunu = karar.tarih_gun + timedelta(days=gun_sayisi)

    taban_deger = _portfoy_degeri(yapilandirma, fiyatlar, islemler, komisyon,
                                  baslangic_nakit, karar.tarih_gun)
    simdiki_deger = _portfoy_degeri(yapilandirma, fiyatlar, islemler, komisyon,
                                    baslangic_nakit, olcum_gunu)
    if taban_deger is None or simdiki_deger is None or taban_deger == 0:
        return None

    semboller = sorted(set(karar.satilan) | set(karar.alinan))
    fiyat_kaydi: dict[str, float] = {}
    getiri_kaydi: dict[str, float] = {}
    for sembol in semboller:
        if sembol not in fiyatlar.try_gecmis:
            continue
        taban = _fiyat_o_gun(fiyatlar.try_gecmis[sembol], karar.tarih_gun)
        simdi = _fiyat_o_gun(fiyatlar.try_gecmis[sembol], olcum_gunu)
        if taban is None or simdi is None or taban == 0:
            continue
        fiyat_kaydi[sembol] = simdi
        getiri_kaydi[sembol] = simdi / taban - 1.0

    kosul = karar.bozan_kosul
    kosul_degeri = (_risk_olcumu(kosul, yapilandirma, fiyatlar, islemler, komisyon,
                                 baslangic_nakit, olcum_gunu)
                    if kosul is not None and kosul.risk_mi else None)

    return Olcum(
        karar_id=karar.id, gun=gun_sayisi, olcum_tarihi=olcum_gunu.isoformat(),
        portfoy_degeri=simdiki_deger,
        portfoy_getirisi=simdiki_deger / taban_deger - 1.0,
        fiyatlar=fiyat_kaydi, getiriler=getiri_kaydi,
        kosul_degeri=kosul_degeri,
    )


def eksik_olcumleri_tamamla(kararlar: list[Karar], mevcut: list[Olcum],
                            yapilandirma, fiyatlar, islemler,
                            komisyon: float, baslangic_nakit: float) -> list[Olcum]:
    """Vadesi gelmis ama henuz olculmemis kontrol gunlerini doldurur."""
    yapilmis = {(o.karar_id, o.gun) for o in mevcut}
    bugun = date.today()
    yeni: list[Olcum] = []

    for karar in kararlar:
        # Bozan kosullu kararlarda 0. gun (karar gunu) de olculur: "karar
        # gunu 29.2% -> 20. gun 26.5%" okumasi bu satirdan gelir ve karar
        # gunu zaten saglanan (hicbir seyi test etmeyen) kosul yakalanir.
        gunler = ((0, *KONTROL_GUNLERI) if karar.bozan_kosul is not None
                  else KONTROL_GUNLERI)
        for gun_sayisi in gunler:
            if (karar.id, gun_sayisi) in yapilmis:
                continue
            if karar.tarih_gun + timedelta(days=gun_sayisi) > bugun:
                continue          # vadesi gelmemis
            olcum = olcum_yap(karar, gun_sayisi, yapilandirma, fiyatlar,
                              islemler, komisyon, baslangic_nakit)
            if olcum:
                yeni.append(olcum)
    return yeni


def _yuzde(oran: float) -> str:
    return f"{oran * 100:+.2f}%"


def rapor_olustur(kararlar: list[Karar], olcumler: list[Olcum]) -> str:
    bugun = date.today()
    satirlar = [
        "---",
        "title: Karar Sonuclari",
        f"date_created: {bugun.isoformat()}",
        "tags: [yatirim, karar, olcum, geribildirim]",
        "status: active",
        'related: ["[[00-simulasyon]]", "[[00-sistem]]"]',
        "---",
        "",
        "# Karar Sonuclari",
        "",
        "Her karar **5/10/15/20/25/30.** gunlerde olculur. Esik tetiklensin veya "
        "tetiklenmesin fiyat ve portfoy degeri kaydedilir - eski Yildiz Pazar botu "
        "vadesi dolan sinyallerin fiyatini kaydetmedigi icin verisinin %88'ini "
        "kullanilamaz hale getirmisti.",
        "",
        "> Bu tablo **veri** sunar, hukum vermez. Risk icin verilmis bir karar "
        "getiri olarak kaybettirebilir ve yine de dogru olabilir; beklenti "
        "satirini okumadan sonuca bakma.",
        "",
    ]

    gruplu: dict[str, list[Olcum]] = {}
    for olcum in olcumler:
        gruplu.setdefault(olcum.karar_id, []).append(olcum)

    for karar in kararlar:
        gecen = (bugun - karar.tarih_gun).days
        kosul = karar.bozan_kosul
        kendi = sorted(gruplu.get(karar.id, []), key=lambda o: o.gun)
        # Hukum EN USTTE: okuyan once "tez tuttu mu"yu gormeli, gerekceyi
        # merak ederse asagi insin.
        hukum = kosul_durumu(karar, kendi)
        satirlar += [
            f"## {karar.id}",
            "",
            f"**{karar.tip}** — {karar.ozet}",
            "",
            *([hukum, ""] if hukum else []),
            f"*Beklenti:* {karar.beklenti}",
            "",
            *([f"*Bozan kosul:* {kosul.metin()}", ""] if kosul else []),
            f"Karar tarihi {karar.tarih} ({gecen} gun once).",
            "",
        ]

        if not kendi:
            sonraki = min(
                (g for g in KONTROL_GUNLERI if karar.tarih_gun + timedelta(days=g) > bugun),
                default=None,
            )
            satirlar += [
                "Henuz olcum yok."
                + (f" Ilk kontrol {sonraki}. gunde." if sonraki else ""),
                "",
            ]
            continue

        takas = bool(karar.satilan and karar.alinan)
        basliklar = ["Gun", "Tarih", "Portfoy", "Portfoy getirisi"]
        if takas:
            basliklar += ["Satilan", "Alinan", "Takas farki"]
        if kosul:
            basliklar.append(kosul.ad)
        satirlar += [
            "| " + " | ".join(basliklar) + " |",
            "|" + "---|" * len(basliklar),
        ]

        for olcum in kendi:
            hucreler = [
                "0 (karar)" if olcum.gun == 0 else str(olcum.gun), olcum.olcum_tarihi,
                f"{olcum.portfoy_degeri:,.0f} TL".replace(",", "."),
                _yuzde(olcum.portfoy_getirisi),
            ]
            if takas:
                satilan_getiri = sum(olcum.getiriler.get(s, 0.0) for s in karar.satilan)
                alinan_getiri = sum(olcum.getiriler.get(s, 0.0) for s in karar.alinan)
                hucreler += [
                    _yuzde(satilan_getiri), _yuzde(alinan_getiri),
                    f"**{_yuzde(takas_farki(karar, olcum))}**",
                ]
            if kosul:
                deger = kosul.deger(karar, olcum)
                hucreler.append(
                    "-" if deger is None else
                    kosul.bicim(deger) + (" ❌" if kosul.tetiklendi(deger) else ""))
            satirlar.append("| " + " | ".join(hucreler) + " |")

        satirlar.append("")
        if takas:
            satirlar += [
                "*Takas farki* = alinanin getirisi − satilanin getirisi. "
                "Pozitif ise takas getiri olarak kazandirdi. Karar risk icin "
                "verildiyse bu satir tek basina yeterli degil.",
                "",
            ]

        kalan = [g for g in KONTROL_GUNLERI if g > kendi[-1].gun]
        if kalan:
            satirlar += [f"Kalan kontrol gunleri: {', '.join(map(str, kalan))}.", ""]
        else:
            satirlar += ["**Takip tamamlandi** (30 gun doldu).", ""]

    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Karar sonuclarini olcer")
    ayristirici.add_argument("--rapor", action="store_true",
                             help="yeni olcum yapma, yalnizca raporu yeniden uret")
    argumanlar = ayristirici.parse_args()

    yapilandirma = yapilandirmayi_oku()
    kararlar = kararlari_oku(
        siniflar={v.sinif for v in yapilandirma.varliklar.values()})
    if not kararlar:
        print(f"Karar yok: {KARARLAR_DOSYASI}")
        return 0

    olcumler = olcumleri_oku()

    if not argumanlar.rapor:
        islemler, baslangic_nakit, komisyon, _ = islemleri_oku(DEFTER_DOSYASI)
        print(f"{len(kararlar)} karar icin olcum kontrol ediliyor...")
        fiyatlar = fiyatlari_getir(yapilandirma)

        yeni = eksik_olcumleri_tamamla(kararlar, olcumler, yapilandirma, fiyatlar,
                                       islemler, komisyon, baslangic_nakit)
        if yeni:
            olcumler += yeni
            olcumleri_yaz(olcumler)
            for olcum in yeni:
                print(f"  olculdu: {olcum.karar_id} gun {olcum.gun} "
                      f"-> portfoy {_yuzde(olcum.portfoy_getirisi)}")
        else:
            print("  vadesi gelmis yeni kontrol gunu yok")

    RAPOR_DOSYASI.write_text(rapor_olustur(kararlar, olcumler), encoding="utf-8")
    print(f"Rapor: {RAPOR_DOSYASI}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
