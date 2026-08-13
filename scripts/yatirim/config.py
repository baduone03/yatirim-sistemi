"""YAML yapilandirmasini okur ve dogrular."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJE_DIZINI = Path(__file__).resolve().parents[2] / "04-projects" / "yatirim-sistemi"
VARLIKLAR_DOSYASI = PROJE_DIZINI / "varliklar.yaml"
PORTFOY_DOSYASI = PROJE_DIZINI / "portfoy.yaml"
RAPOR_DIZINI = PROJE_DIZINI / "raporlar"


@dataclass(frozen=True)
class Varlik:
    sembol: str
    ad: str
    sinif: str
    kur: str
    carpan: float = 1.0
    izleme: bool = False


@dataclass(frozen=True)
class Pozisyon:
    sembol: str
    adet: float
    maliyet: float
    tarih: str


@dataclass(frozen=True)
class Ayarlar:
    kur_sembolu: str
    gecmis_gun: int
    islem_gunu_yil: int


@dataclass(frozen=True)
class Yapilandirma:
    ayarlar: Ayarlar
    hedef_dagilim: dict[str, float]
    varliklar: dict[str, Varlik]
    nakit_try: float
    pozisyonlar: list[Pozisyon] = field(default_factory=list)
    sablon: bool = False          # portfoy.yaml doldurulmamis ornek veri mi

    @property
    def fiyat_sembolleri(self) -> list[str]:
        return sorted({*self.varliklar, self.ayarlar.kur_sembolu})


def _yukle(dosya: Path) -> dict:
    if not dosya.exists():
        raise FileNotFoundError(f"Yapilandirma dosyasi yok: {dosya}")
    return yaml.safe_load(dosya.read_text(encoding="utf-8"))


def _varliklari_ayristir(ham: list[dict]) -> dict[str, Varlik]:
    varliklar: dict[str, Varlik] = {}
    for kayit in ham:
        varlik = Varlik(
            sembol=kayit["sembol"],
            ad=kayit["ad"],
            sinif=kayit["sinif"],
            kur=kayit["kur"].upper(),
            carpan=float(kayit.get("carpan", 1.0)),
            izleme=bool(kayit.get("izleme", False)),
        )
        if varlik.kur not in ("TRY", "USD"):
            raise ValueError(f"{varlik.sembol}: kur TRY veya USD olmali, '{varlik.kur}' geldi")
        varliklar[varlik.sembol] = varlik
    return varliklar


def _dogrula(varliklar: dict[str, Varlik], pozisyonlar: list[Pozisyon],
             hedef_dagilim: dict[str, float]) -> None:
    bilinmeyen = {p.sembol for p in pozisyonlar} - set(varliklar)
    if bilinmeyen:
        raise ValueError(
            f"portfoy.yaml'da varliklar.yaml'da tanimsiz sembol var: {sorted(bilinmeyen)}"
        )

    siniflar = {v.sinif for v in varliklar.values() if not v.izleme}
    eksik = siniflar - set(hedef_dagilim)
    if eksik:
        raise ValueError(f"hedef_dagilim'da eksik varlik sinifi: {sorted(eksik)}")

    toplam = sum(hedef_dagilim.values())
    if abs(toplam - 1.0) > 0.001:
        raise ValueError(f"hedef_dagilim toplami 1.0 olmali, {toplam:.3f} geldi")


def yapilandirmayi_oku(varliklar_dosyasi: Path = VARLIKLAR_DOSYASI,
                       portfoy_dosyasi: Path = PORTFOY_DOSYASI) -> Yapilandirma:
    varlik_ham = _yukle(varliklar_dosyasi)
    portfoy_ham = _yukle(portfoy_dosyasi)

    varliklar = _varliklari_ayristir(varlik_ham["varliklar"])
    pozisyonlar = [
        Pozisyon(
            sembol=p["sembol"],
            adet=float(p["adet"]),
            maliyet=float(p["maliyet"]),
            tarih=str(p.get("tarih", "")),
        )
        for p in portfoy_ham.get("pozisyonlar") or []
    ]
    hedef_dagilim = {k: float(v) for k, v in varlik_ham["hedef_dagilim"].items()}
    _dogrula(varliklar, pozisyonlar, hedef_dagilim)

    ayar_ham = varlik_ham["ayarlar"]
    return Yapilandirma(
        ayarlar=Ayarlar(
            kur_sembolu=ayar_ham["kur_sembolu"],
            gecmis_gun=int(ayar_ham["gecmis_gun"]),
            islem_gunu_yil=int(ayar_ham["islem_gunu_yil"]),
        ),
        hedef_dagilim=hedef_dagilim,
        varliklar=varliklar,
        nakit_try=float(portfoy_ham.get("nakit_try", 0.0)),
        pozisyonlar=pozisyonlar,
        sablon=bool(portfoy_ham.get("sablon", False)),
    )


def sablonu_reddet(yapilandirma: Yapilandirma, dosya: Path = PORTFOY_DOSYASI) -> None:
    """Doldurulmamis ornek portfoyun gercek veri gibi raporlanmasini engeller.

    Simulasyon yolu bu kontrolden gecmez - orada pozisyonlar islem
    defterinden gelir, portfoy.yaml kullanilmaz.
    """
    if yapilandirma.sablon:
        raise ValueError(
            f"{dosya} sablon veri iceriyor (sablon: true) - gercek portfoy raporu "
            "uretilemez.\nSimulasyon icin --sim kullan; gercek portfoy icin "
            "dosyayi kendi pozisyonlarinla doldurup 'sablon' satirini sil."
        )
