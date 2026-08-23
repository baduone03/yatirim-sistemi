"""Ongoru defteri: yanlislanabilir piyasa ongorulerini kaydeder ve olcer.

NEDEN AYRI BIR MODUL: bu dosya SINYAL URETMEZ ve karar yoluna baglanmaz.
Ongoru, sistemin kendi akil yurutmesini yanlislanabilir kilmak icindir -
islem tetiklemek icin degil. Bir ongoruye dayanarak pozisyon acmak, henuz
kalibre olmadigi kanitlanmamis bir modele para baglamaktir. `main.py` bu
modulu import ETMEZ; TahminIzolasyonTesti bunu her kosuda dogrular.

OLCEK UYARISI: %50 sansi %55 beceriden istatistiksel olarak ayirmak kabaca
1000 gozlem ister. 30 gozlem "egilim", 100 gozlem "isaret", hukum degil.
Karne bu esikleri acikca yazar; altindaysa "hukum yok" der.

KOSUL DILI - iki tip, ikisi de makine tarafindan kontrol edilebilir:

    tip: esik_asar    # sembolun ufuk sonundaki getirisi esigi asacak mi
      sembol: ASELS.IS
      esik: 0.03      # 0.0 yazilirsa "yukselecek mi" demektir

    tip: gecer        # sembol, kiyasi gecebilecek mi (goreli)
      sembol: ASELS.IS
      kiyas: XU100.IS

Serbest metin ongoru KABUL EDILMEZ. "Piyasa iyi olacak" olculemez;
olculemeyen ongoru geri bildirim uretmez ve defteri kirletir.

Kullanim:
    python scripts/yatirim/tahmin.py            # olcum + karne
    python scripts/yatirim/tahmin.py --rapor    # yalnizca karne
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

SIM_DIZINI = PROJE_DIZINI / "simulasyon"
TAHMINLER_DOSYASI = SIM_DIZINI / "tahminler.yaml"
SONUCLAR_DOSYASI = SIM_DIZINI / "tahmin-sonuclari.yaml"
KARNE_DOSYASI = SIM_DIZINI / "00-tahmin-karnesi.md"

GECERLI_TIPLER = ("esik_asar", "gecer")

# Karnenin hangi esikten sonra ne diyecegi. Sayilar kesin degil ama
# buyukluk mertebesi dogru: ayirt etme gucu gozlem sayisinin karekokuyle
# buyur, yani 4 kat kesinlik icin 16 kat gozlem gerekir.
EGILIM_N = 30
ISARET_N = 100
HUKUM_N = 1000


class TahminHatasi(ValueError):
    """Defterdeki bir kayit olculebilir degil."""


@dataclass(frozen=True)
class Tahmin:
    id: str
    tarih: str
    ufuk_gun: int
    olasilik: float          # 0.0 - 1.0, ongorunun tutacagina dair guven
    tip: str
    sembol: str
    esik: float              # tip == esik_asar
    kiyas: str               # tip == gecer
    gerekce: str
    dayanak: str             # hangi haber/veri; bos olabilir

    @property
    def tarih_gun(self) -> date:
        return datetime.strptime(self.tarih, "%Y-%m-%d").date()

    @property
    def vade_gunu(self) -> date:
        return self.tarih_gun + timedelta(days=self.ufuk_gun)

    @property
    def ifade(self) -> str:
        """Insan okunur, kosulun birebir karsiligi."""
        if self.tip == "gecer":
            return f"{self.sembol}, {self.kiyas} kiyasini gecer"
        if self.esik == 0.0:
            return f"{self.sembol} yukselir"
        return f"{self.sembol} getirisi %{self.esik * 100:.1f} esigini asar"


@dataclass(frozen=True)
class Sonuc:
    tahmin_id: str
    olcum_tarihi: str
    tuttu: bool
    getiri: float                 # sembolun ufuk boyunca getirisi
    kiyas_getirisi: float | None  # tip == gecer ise kiyasin getirisi


def _kaydi_dogrula(ham: dict) -> None:
    """Olculemeyen kayit defterin girisinde reddedilir.

    Sessizce atlamak, defteri sessizce kirletirdi: karne 'N=40' der ama
    aslinda 12'si hic olculmemistir. Yuksek sesle patlamak dogrusu.
    """
    tip = str(ham.get("tip", ""))
    if tip not in GECERLI_TIPLER:
        raise TahminHatasi(
            f"{ham.get('id')}: tip '{tip}' gecersiz. "
            f"Gecerli tipler: {', '.join(GECERLI_TIPLER)}")
    if not ham.get("sembol"):
        raise TahminHatasi(f"{ham.get('id')}: sembol zorunlu")
    if tip == "gecer" and not ham.get("kiyas"):
        raise TahminHatasi(f"{ham.get('id')}: tip 'gecer' icin kiyas zorunlu")
    if tip == "esik_asar" and ham.get("esik") is None:
        raise TahminHatasi(
            f"{ham.get('id')}: tip 'esik_asar' icin esik zorunlu "
            f"(yukselecek demek icin 0.0 yaz)")

    olasilik = ham.get("olasilik")
    if olasilik is None or not 0.0 <= float(olasilik) <= 1.0:
        raise TahminHatasi(f"{ham.get('id')}: olasilik 0.0-1.0 arasinda olmali")
    if float(olasilik) in (0.0, 1.0):
        raise TahminHatasi(
            f"{ham.get('id')}: olasilik 0 veya 1 olamaz - kesinlik iddiasi "
            f"olculemez ve Brier skorunu bozar")
    if int(ham.get("ufuk_gun", 0)) < 1:
        raise TahminHatasi(f"{ham.get('id')}: ufuk_gun en az 1 olmali")


def tahminleri_oku(dosya: Path = TAHMINLER_DOSYASI) -> list[Tahmin]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    tahminler = []
    for kayit in (ham.get("tahminler") or []):
        _kaydi_dogrula(kayit)
        tahminler.append(Tahmin(
            id=str(kayit["id"]),
            tarih=str(kayit["tarih"]),
            ufuk_gun=int(kayit["ufuk_gun"]),
            olasilik=float(kayit["olasilik"]),
            tip=str(kayit["tip"]),
            sembol=str(kayit["sembol"]),
            esik=float(kayit.get("esik") or 0.0),
            kiyas=str(kayit.get("kiyas") or ""),
            gerekce=" ".join(str(kayit.get("gerekce", "")).split()),
            dayanak=" ".join(str(kayit.get("dayanak", "")).split()),
        ))
    kimlikler = [t.id for t in tahminler]
    tekrar = {k for k in kimlikler if kimlikler.count(k) > 1}
    if tekrar:
        raise TahminHatasi(f"tekrarlanan tahmin id: {sorted(tekrar)}")
    return tahminler


def sonuclari_oku(dosya: Path = SONUCLAR_DOSYASI) -> list[Sonuc]:
    if not dosya.exists():
        return []
    ham = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    return [
        Sonuc(
            tahmin_id=s["tahmin_id"], olcum_tarihi=s["olcum_tarihi"],
            tuttu=bool(s["tuttu"]), getiri=float(s["getiri"]),
            kiyas_getirisi=(None if s.get("kiyas_getirisi") is None
                            else float(s["kiyas_getirisi"])),
        )
        for s in (ham.get("sonuclar") or [])
    ]


def sonuclari_yaz(sonuclar: list[Sonuc], dosya: Path = SONUCLAR_DOSYASI) -> None:
    icerik = {
        "sonuclar": [
            {
                "tahmin_id": s.tahmin_id, "olcum_tarihi": s.olcum_tarihi,
                "tuttu": s.tuttu, "getiri": round(s.getiri, 6),
                "kiyas_getirisi": (None if s.kiyas_getirisi is None
                                   else round(s.kiyas_getirisi, 6)),
            }
            for s in sorted(sonuclar, key=lambda x: x.tahmin_id)
        ]
    }
    baslik = (
        "# MAKINE URETIR - elle duzenleme.\n"
        "# tahmin.py yazar. Ongoruler icin tahminler.yaml'a bak.\n"
        "# Bir sonuc yazildiktan sonra DEGISTIRILMEZ: sonradan duzeltilen\n"
        "# sonuc, karneyi olcum aracindan ovunme aracina cevirir.\n\n"
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


def _getiri(gecmis, sembol: str, baslangic: date, bitis: date) -> float | None:
    if sembol not in gecmis:
        return None
    taban = _fiyat_o_gun(gecmis[sembol], baslangic)
    son = _fiyat_o_gun(gecmis[sembol], bitis)
    if taban is None or son is None or taban == 0:
        return None
    return son / taban - 1.0


def olc(tahmin: Tahmin, gecmis) -> Sonuc | None:
    """Vadesi dolmus bir ongoruyu olcer. Fiyat yoksa None - kayit yazilmaz.

    Fiyat gelmediginde 'yanlis' yazmak veriyi bozar: bizim korlugumuz
    ongorunun tutmadigi anlamina gelmez. Olculemeyen ongoru bekler.
    """
    getiri = _getiri(gecmis, tahmin.sembol, tahmin.tarih_gun, tahmin.vade_gunu)
    if getiri is None:
        return None

    kiyas_getirisi = None
    if tahmin.tip == "gecer":
        kiyas_getirisi = _getiri(gecmis, tahmin.kiyas,
                                 tahmin.tarih_gun, tahmin.vade_gunu)
        if kiyas_getirisi is None:
            return None
        tuttu = getiri > kiyas_getirisi
    else:
        tuttu = getiri >= tahmin.esik

    return Sonuc(
        tahmin_id=tahmin.id, olcum_tarihi=tahmin.vade_gunu.isoformat(),
        tuttu=tuttu, getiri=getiri, kiyas_getirisi=kiyas_getirisi,
    )


def vadesi_dolanlari_olc(tahminler: list[Tahmin], mevcut: list[Sonuc],
                         gecmis, bugun: date) -> list[Sonuc]:
    olculmus = {s.tahmin_id for s in mevcut}
    yeni = []
    for tahmin in tahminler:
        if tahmin.id in olculmus or tahmin.vade_gunu > bugun:
            continue
        sonuc = olc(tahmin, gecmis)
        if sonuc:
            yeni.append(sonuc)
    return yeni


@dataclass(frozen=True)
class Karne:
    n: int
    isabet: int
    isabet_orani: float
    brier: float             # dusuk = iyi. Hep %50 demek 0.25 verir.
    brier_referans: float    # hep taban orani demenin skoru
    taban_oran: float        # gerceklesen olaylarin orani


def karne_hesapla(tahminler: list[Tahmin], sonuclar: list[Sonuc]) -> Karne | None:
    """Isabet orani + Brier skoru.

    Brier tek basina aldatir: nadir olaylara hep 'olmaz' demek dusuk Brier
    verir. Bu yuzden taban orani da hesaplanir - model onu gecemiyorsa
    hicbir bilgi katmiyor demektir.
    """
    haritali = {t.id: t for t in tahminler}
    ciftler = [(haritali[s.tahmin_id], s) for s in sonuclar if s.tahmin_id in haritali]
    if not ciftler:
        return None

    n = len(ciftler)
    isabet = sum(1 for _, s in ciftler if s.tuttu)
    taban_oran = isabet / n
    brier = sum((t.olasilik - (1.0 if s.tuttu else 0.0)) ** 2 for t, s in ciftler) / n
    brier_referans = sum((taban_oran - (1.0 if s.tuttu else 0.0)) ** 2
                         for _, s in ciftler) / n
    return Karne(n=n, isabet=isabet, isabet_orani=isabet / n, brier=brier,
                 brier_referans=brier_referans, taban_oran=taban_oran)


def kalibrasyon(tahminler: list[Tahmin], sonuclar: list[Sonuc],
                kova_sayisi: int = 5) -> list[tuple[str, int, float, float]]:
    """Olasilik kovasi -> (etiket, n, ortalama_iddia, gerceklesen_oran).

    Kalibrasyon, isabet oranindan farkli bir sey olcer: %70 dedigin
    seylerin gercekten %70'i oluyor mu? Iyi kalibre bir model az isabetli
    olabilir; kotu kalibre bir model cok isabetli gorunup guvenilmez olur.
    """
    haritali = {t.id: t for t in tahminler}
    ciftler = [(haritali[s.tahmin_id], s) for s in sonuclar if s.tahmin_id in haritali]
    satirlar = []
    for i in range(kova_sayisi):
        alt, ust = i / kova_sayisi, (i + 1) / kova_sayisi
        kova = [(t, s) for t, s in ciftler
                if alt <= t.olasilik < ust or (i == kova_sayisi - 1 and t.olasilik == ust)]
        if not kova:
            continue
        satirlar.append((
            f"%{alt * 100:.0f}-{ust * 100:.0f}",
            len(kova),
            sum(t.olasilik for t, _ in kova) / len(kova),
            sum(1 for _, s in kova if s.tuttu) / len(kova),
        ))
    return satirlar


def _yuzde(oran: float) -> str:
    return f"{oran * 100:+.2f}%"


def _hukum(karne: Karne) -> list[str]:
    """Gozlem sayisi neye yetiyor - ve neye yetmiyor."""
    if karne.n < EGILIM_N:
        return [f"**Hukum yok.** {karne.n} gozlem var, egilim okumak icin bile "
                f"en az {EGILIM_N} gerekiyor. Bu sayilar simdilik yalnizca "
                f"defterin calistigini gosterir."]
    if karne.n < ISARET_N:
        satir = [f"**Egilim** ({karne.n} gozlem). Isaret icin {ISARET_N}, "
                 f"beceriyi sanstan ayirmak icin ~{HUKUM_N} gozlem gerekir."]
    elif karne.n < HUKUM_N:
        satir = [f"**Isaret** ({karne.n} gozlem). Beceriyi sanstan istatistiksel "
                 f"olarak ayirmak icin ~{HUKUM_N} gozlem gerekir."]
    else:
        satir = [f"**Olculebilir** ({karne.n} gozlem)."]

    if karne.brier < karne.brier_referans:
        satir.append(f"Brier {karne.brier:.4f}, taban oran referansinin "
                     f"({karne.brier_referans:.4f}) ALTINDA - olasilik "
                     f"iddialari bilgi katiyor.")
    else:
        satir.append(f"Brier {karne.brier:.4f}, taban oran referansini "
                     f"({karne.brier_referans:.4f}) GECEMIYOR - su ana kadar "
                     f"olasilik iddialari hicbir bilgi katmadi.")
    return satir


def karne_raporu(tahminler: list[Tahmin], sonuclar: list[Sonuc],
                 bugun: date) -> str:
    satirlar = [
        "---",
        "title: Tahmin Karnesi",
        f"date_created: {bugun.isoformat()}",
        "tags: [yatirim, tahmin, olcum, kalibrasyon]",
        "status: active",
        'related: ["[[00-simulasyon]]", "[[00-karar-sonuclari]]"]',
        "---",
        "",
        "# Tahmin Karnesi",
        "",
        "Ongoruler **islem tetiklemez**. Bu defterin isi, sistemin akil "
        "yurutmesini yanlislanabilir kilmak - pozisyon acmak degil.",
        "",
    ]

    karne = karne_hesapla(tahminler, sonuclar)
    if karne is None:
        satirlar += ["Henuz vadesi dolmus ongoru yok.", ""]
    else:
        satirlar += [
            "## Ozet", "",
            f"- Olculen ongoru: **{karne.n}**",
            f"- Isabet: **{karne.isabet}/{karne.n}** (%{karne.isabet_orani * 100:.1f})",
            f"- Brier skoru: **{karne.brier:.4f}** (dusuk = iyi; hep %50 demek 0.2500 verir)",
            f"- Taban oran: %{karne.taban_oran * 100:.1f} "
            f"(ongorulerin gerceklesme sikligi)",
            "",
        ] + _hukum(karne) + [""]

        kova_satirlari = kalibrasyon(tahminler, sonuclar)
        if kova_satirlari:
            satirlar += [
                "## Kalibrasyon", "",
                "%70 dedigin seylerin gercekten %70'i oldu mu? Isabetten "
                "farkli bir soru: az isabetli ama iyi kalibre bir model "
                "guvenilir, tersi degil.",
                "",
                "| Olasilik araligi | n | Ortalama iddia | Gerceklesen |",
                "|---|---|---|---|",
            ]
            for etiket, n, iddia, gercek in kova_satirlari:
                satirlar.append(
                    f"| {etiket} | {n} | %{iddia * 100:.0f} | %{gercek * 100:.0f} |")
            satirlar.append("")

    olculmus = {s.tahmin_id: s for s in sonuclar}
    bekleyen = [t for t in tahminler if t.id not in olculmus]

    if olculmus:
        satirlar += ["## Olculen ongoruler", "",
                     "| Tarih | Ongoru | Ufuk | Iddia | Sonuc | Getiri |",
                     "|---|---|---|---|---|---|"]
        for tahmin in sorted(tahminler, key=lambda t: t.tarih, reverse=True):
            sonuc = olculmus.get(tahmin.id)
            if not sonuc:
                continue
            isaret = "DOGRU" if sonuc.tuttu else "YANLIS"
            getiri = _yuzde(sonuc.getiri)
            if sonuc.kiyas_getirisi is not None:
                getiri += f" / kiyas {_yuzde(sonuc.kiyas_getirisi)}"
            satirlar.append(
                f"| {tahmin.tarih} | {tahmin.ifade} | {tahmin.ufuk_gun}g "
                f"| %{tahmin.olasilik * 100:.0f} | **{isaret}** | {getiri} |")
        satirlar.append("")

    if bekleyen:
        satirlar += ["## Bekleyen ongoruler", "",
                     "| Vade | Ongoru | Ufuk | Iddia | Dayanak |",
                     "|---|---|---|---|---|"]
        for tahmin in sorted(bekleyen, key=lambda t: t.vade_gunu):
            kalan = (tahmin.vade_gunu - bugun).days
            vade = f"{tahmin.vade_gunu.isoformat()} ({kalan}g)" if kalan > 0 \
                else f"{tahmin.vade_gunu.isoformat()} (olculmedi)"
            satirlar.append(
                f"| {vade} | {tahmin.ifade} | {tahmin.ufuk_gun}g "
                f"| %{tahmin.olasilik * 100:.0f} | {tahmin.dayanak or '-'} |")
        satirlar.append("")

    return "\n".join(satirlar)


def _karneyi_yaz(icerik: str, dosya: Path) -> None:
    """Icerik degismediyse dosyaya DOKUNMAZ.

    Bu betik tarama gridinde de kosuyor. Kosulsuz yazmak gunde 12 anlamsiz
    commit uretirdi - raporun yalnizca gun sonu yazilmasinin sebebiyle ayni
    sebep. Degisiklik yoksa git de bir sey gormez.
    """
    if dosya.exists() and dosya.read_text(encoding="utf-8") == icerik:
        print(f"Karne degismedi: {dosya}")
        return
    dosya.write_text(icerik, encoding="utf-8")
    print(f"Karne guncellendi: {dosya}")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Ongoruleri olcer")
    ayristirici.add_argument("--rapor", action="store_true",
                             help="yeni olcum yapma, yalnizca karneyi uret")
    argumanlar = ayristirici.parse_args()

    # Sabitler ACIKCA geciliyor: varsayilan arguman `def` aninda baglanir,
    # yani modul sabitini degistirmek fonksiyonu etkilemez ve modul uctan
    # uca test edilemez hale gelir.
    tahminler = tahminleri_oku(TAHMINLER_DOSYASI)
    if not tahminler:
        print(f"Ongoru yok: {TAHMINLER_DOSYASI}")
        return 0

    sonuclar = sonuclari_oku(SONUCLAR_DOSYASI)
    bugun = date.today()

    if not argumanlar.rapor:
        vadesi_dolan = [t for t in tahminler
                        if t.vade_gunu <= bugun and t.id not in {s.tahmin_id for s in sonuclar}]
        if vadesi_dolan:
            print(f"{len(vadesi_dolan)} ongorunun vadesi doldu, olculuyor...")
            yapilandirma = yapilandirmayi_oku()
            fiyatlar = fiyatlari_getir(yapilandirma)
            yeni = vadesi_dolanlari_olc(tahminler, sonuclar, fiyatlar.try_gecmis, bugun)
            if yeni:
                sonuclar += yeni
                sonuclari_yaz(sonuclar, SONUCLAR_DOSYASI)
                for sonuc in yeni:
                    print(f"  {sonuc.tahmin_id}: "
                          f"{'DOGRU' if sonuc.tuttu else 'YANLIS'} "
                          f"({_yuzde(sonuc.getiri)})")
            else:
                print("  fiyat gelmedi, olcum ertelendi")
        else:
            print("  vadesi dolmus yeni ongoru yok")

    _karneyi_yaz(karne_raporu(tahminler, sonuclar, bugun), KARNE_DOSYASI)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (TahminHatasi, ValueError, FileNotFoundError, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(1)
