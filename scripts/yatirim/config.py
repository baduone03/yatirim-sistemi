"""YAML yapilandirmasini okur ve dogrular."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from maliyet import MaliyetModeli, modeli_kur

# Turkiye kalici UTC+3, yaz saati uygulamasi yok. Zaman damgalari UTC tutulur
# ama "hafta sonu" ve "sessiz saat" YEREL kavramlardir: UTC uzerinden
# hesaplanirsa Cumartesi TR 02:00 hala Cuma sayilir.
TR_OFSET = timedelta(hours=3)

PROJE_DIZINI = Path(__file__).resolve().parents[2] / "04-projects" / "yatirim-sistemi"


def simdi_utc() -> datetime:
    """Tum zaman damgalari UTC.

    Actions UTC'de, yerel kosu TR saatinde calisir. Naive `datetime.now()`
    kullanilsaydi yerel kosu 20:00 yazar, ardindan gelen Actions kosusu 16:00
    yazardi - gecen sure NEGATIF cikar ve bekleme suresi anlamini yitirirdi.
    """
    return datetime.now(timezone.utc)


def hafta_sonu_mu(an: datetime) -> bool:
    """UTC damgadan TR takvimine gore hafta sonu mu."""
    return (an + TR_OFSET).weekday() >= 5


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
class Esikler:
    """Karar esikleri - kodda sabit degil, varliklar.yaml'dan gelir.

    Her esik bir BANT: sinyal `_ust` degerinde acilir, `_geri_donus` degerine
    inmeden kapanmaz. Tek esikli kural, deger esigin etrafinda salinirken her
    kosuda ters sinyal uretir - komisyon oder, pozisyon degismez.

    `acik` parametresi latch durumudur ve cagirandan gelir; Esikler durum
    tutmaz, yalnizca sayi karsilastirir.
    """

    rebalancing_sapma: float
    risk_katkisi_ust: float
    risk_beta_ust: float = 1.50
    rebalancing_geri_donus: float = 0.0
    risk_katkisi_geri_donus: float = 0.0
    hafta_sonu_carpani: float = 1.0

    def _carpan(self, hafta_sonu: bool) -> float:
        return self.hafta_sonu_carpani if hafta_sonu else 1.0

    def sapma_asildi(self, sapma: float, acik: bool = False,
                     hafta_sonu: bool = False) -> bool:
        """Rebalancing sapmasi bandi. Esige esitken latch ACIK kalir."""
        taban = self.rebalancing_geri_donus if acik else self.rebalancing_sapma
        return abs(sapma) >= taban * self._carpan(hafta_sonu)

    def kisilmali(self, varlik_riski, acik: bool = False,
                  hafta_sonu: bool = False) -> bool:
        """Kisma karari: katki VE beta birlikte tavani asmali.

        Bant yalnizca katkiya uygulanir - beta = katki/agirlik oldugu icin
        katki bandi betanin salinimini da buyuk olcude sonumler.
        """
        taban = self.risk_katkisi_geri_donus if acik else self.risk_katkisi_ust
        return (varlik_riski.risk_katkisi > taban * self._carpan(hafta_sonu)
                and varlik_riski.beta > self.risk_beta_ust)


@dataclass(frozen=True)
class Bekleme:
    """Ayni sembolde iki sinyal arasindaki asgari sure.

    Sure, son URETILEN sinyalden olculur (`sinyal-durumu.yaml`), islem
    defterinden degil: defter yalnizca TARIH tutar, "24 saat" gun cozunurlugunde
    tanimsizdir.
    """

    ayni_sembol_saat: float = 0.0


@dataclass(frozen=True)
class DevreKesici:
    """Gunluk sinyal tavani. Asilirsa o gun HICBIR sinyal uretilmez."""

    gunluk_maks_islem: int = 6


@dataclass(frozen=True)
class BayatlikEsikleri:
    """Varlik sinifi basina bayatlik esigi, KACIRILAN ISLEM GUNU cinsinden.

    Takvim gunu degil: BIST Cuma'dan Pazartesi'ye 3 takvim gunu gecirir ama
    1 islem gunu. Takvim gunu sayan bir esik her Pazartesi yanlis alarm verir.
    """

    varsayilan: float = 7.0
    sinif_bazli: dict[str, float] = field(default_factory=dict)

    def gun(self, sinif: str) -> float:
        return self.sinif_bazli.get(sinif, self.varsayilan)


@dataclass(frozen=True)
class KurumsalOlayAyarlari:
    """Kayitli olmayan bedelsiz/split suphesinin tespit parametreleri."""

    getiri_esigi: float = 0.25
    hacim_carpani: float = 1.5
    hacim_penceresi: int = 20
    tarama_gunu: int = 5


@dataclass(frozen=True)
class VeriKaynaklari:
    """Dis kaynak uc noktalari ve ucgenleme esikleri.

    Bos birakilirsa (URL yok) o kaynak devre disidir ve sistem tamamen
    Yahoo uzerinden calisir - FAZ 2 oncesi davranis.
    """

    btcturk_url: str = ""
    btcturk_ciftleri: dict[str, str] = field(default_factory=dict)
    coingecko_url: str = ""
    coingecko_kimlikleri: dict[str, str] = field(default_factory=dict)
    tcmb_url: str = ""
    tcmb_seri: str = "TP.DK.USD.A.EF.YTL"
    tcmb_bayatlik_gun: int = 1
    btcturk_bayatlik_dakika: float = 15.0
    prim_esigi: float = 0.03
    durdurma_esigi: float = 0.08

    @property
    def btcturk_acik(self) -> bool:
        return bool(self.btcturk_url and self.btcturk_ciftleri)


@dataclass(frozen=True)
class Yapilandirma:
    ayarlar: Ayarlar
    esikler: Esikler
    hedef_dagilim: dict[str, float]
    varliklar: dict[str, Varlik]
    nakit_try: float
    pozisyonlar: list[Pozisyon] = field(default_factory=list)
    sablon: bool = False          # portfoy.yaml doldurulmamis ornek veri mi
    bayatlik: BayatlikEsikleri = field(default_factory=BayatlikEsikleri)
    kurumsal_olay: KurumsalOlayAyarlari = field(default_factory=KurumsalOlayAyarlari)
    kaynaklar: VeriKaynaklari = field(default_factory=VeriKaynaklari)
    maliyet: MaliyetModeli = field(default_factory=MaliyetModeli)
    bekleme: Bekleme = field(default_factory=Bekleme)
    devre_kesici: DevreKesici = field(default_factory=DevreKesici)

    @property
    def fiyat_sembolleri(self) -> list[str]:
        return sorted({*self.varliklar, self.ayarlar.kur_sembolu})

    @property
    def sinif_haritasi(self) -> dict[str, str]:
        return {sembol: varlik.sinif for sembol, varlik in self.varliklar.items()}


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

    sayim: dict[str, int] = {}
    for pozisyon in pozisyonlar:
        sayim[pozisyon.sembol] = sayim.get(pozisyon.sembol, 0) + 1
    mukerrer = sorted(s for s, n in sayim.items() if n > 1)
    if mukerrer:
        raise ValueError(
            f"portfoy.yaml'da ayni sembol birden fazla satirda: {mukerrer}. "
            "Lotlari tek satirda birlestir (adet topla, maliyeti agirlikli ortala)."
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
    esik_ham = varlik_ham.get("esikler") or {}
    esikler = Esikler(
        rebalancing_sapma=float(esik_ham.get("rebalancing_sapma", 0.05)),
        risk_katkisi_ust=float(esik_ham.get("risk_katkisi_ust", 0.25)),
        risk_beta_ust=float(esik_ham.get("risk_beta_ust", 1.50)),
        # Varsayilanlar tetiklerle (0.05 / 0.25) ayni sekle sahip: sapma bandi
        # yarilanir, katki bandi 3 puan iner. Tetigi ozellestirip geri donusu
        # unutan yapilandirma asagidaki dogrulamada patlar - sessizce uyumsuz
        # bir bant olusmaz.
        rebalancing_geri_donus=float(esik_ham.get("rebalancing_geri_donus", 0.025)),
        risk_katkisi_geri_donus=float(esik_ham.get("risk_katkisi_geri_donus", 0.22)),
        hafta_sonu_carpani=float(esik_ham.get("hafta_sonu_carpani", 1.0)),
    )
    if esikler.hafta_sonu_carpani < 1:
        raise ValueError(
            "esikler.hafta_sonu_carpani 1'den kucuk olamaz, "
            f"{esikler.hafta_sonu_carpani} geldi. 1'in altinda hafta sonu esigi "
            "DARALIR - ince likiditede tam ters davranis.")
    for ad, deger in (("rebalancing_sapma", esikler.rebalancing_sapma),
                      ("risk_katkisi_ust", esikler.risk_katkisi_ust)):
        if not 0 < deger < 1:
            raise ValueError(f"esikler.{ad} 0 ile 1 arasinda olmali, {deger} geldi")
    if esikler.risk_beta_ust <= 1:
        raise ValueError(
            f"esikler.risk_beta_ust 1'den buyuk olmali, {esikler.risk_beta_ust} geldi "
            "(beta 1 = varlik parasi kadar risk tasiyor)"
        )
    # Geri donus esigi tetigin ALTINDA olmali. Esit veya ustunde olsaydi
    # histerezis bandi ters doner: latch acildigi anda kapanir (bant yok) ya da
    # bir daha hic kapanmaz. Ikisi de sessizce yanlis calisir.
    for tetik_ad, tetik, donus_ad, donus in (
            ("rebalancing_sapma", esikler.rebalancing_sapma,
             "rebalancing_geri_donus", esikler.rebalancing_geri_donus),
            ("risk_katkisi_ust", esikler.risk_katkisi_ust,
             "risk_katkisi_geri_donus", esikler.risk_katkisi_geri_donus)):
        if not 0 < donus < tetik:
            raise ValueError(
                f"esikler.{donus_ad} 0 ile esikler.{tetik_ad} ({tetik}) arasinda "
                f"olmali, {donus} geldi. Histerezis bandi bu iki sayidan olusur; "
                "geri donus tetigin altinda degilse bant yoktur.")

    bekleme_ham = varlik_ham.get("bekleme") or {}
    bekleme = Bekleme(ayni_sembol_saat=float(bekleme_ham.get("ayni_sembol_saat", 0.0)))
    if bekleme.ayni_sembol_saat < 0:
        raise ValueError(
            f"bekleme.ayni_sembol_saat negatif olamaz, {bekleme.ayni_sembol_saat} geldi")

    kesici_ham = varlik_ham.get("devre_kesici") or {}
    devre_kesici = DevreKesici(
        gunluk_maks_islem=int(kesici_ham.get("gunluk_maks_islem", 6)))
    if devre_kesici.gunluk_maks_islem < 1:
        raise ValueError(
            "devre_kesici.gunluk_maks_islem en az 1 olmali, "
            f"{devre_kesici.gunluk_maks_islem} geldi (0 = sistem hic sinyal uretmez)")

    bayat_ham = varlik_ham.get("bayatlik_esikleri") or {}
    bayatlik = BayatlikEsikleri(
        varsayilan=float(bayat_ham.get("varsayilan", 7.0)),
        sinif_bazli={ad: float(d) for ad, d in bayat_ham.items() if ad != "varsayilan"},
    )
    # Yazim hatasi sessizce varsayilana dusmesin: `kripo: 0` yazilsaydi kripto
    # 7 gunluk esikle olculur ve kimse fark etmezdi.
    tanimsiz = sorted(set(bayatlik.sinif_bazli) - {v.sinif for v in varliklar.values()})
    if tanimsiz:
        raise ValueError(
            f"bayatlik_esikleri'nde tanimsiz varlik sinifi: {tanimsiz}. "
            f"Gecerli siniflar: {sorted({v.sinif for v in varliklar.values()})}"
        )
    for ad, deger in bayatlik.sinif_bazli.items():
        if deger < 0:
            raise ValueError(f"bayatlik_esikleri.{ad} negatif olamaz, {deger} geldi")

    olay_ham = varlik_ham.get("kurumsal_olay") or {}
    kurumsal_olay = KurumsalOlayAyarlari(
        getiri_esigi=float(olay_ham.get("getiri_esigi", 0.25)),
        hacim_carpani=float(olay_ham.get("hacim_carpani", 1.5)),
        hacim_penceresi=int(olay_ham.get("hacim_penceresi", 20)),
        tarama_gunu=int(olay_ham.get("tarama_gunu", 5)),
    )
    if not 0 < kurumsal_olay.getiri_esigi < 1:
        raise ValueError(
            "kurumsal_olay.getiri_esigi 0 ile 1 arasinda olmali, "
            f"{kurumsal_olay.getiri_esigi} geldi"
        )
    if kurumsal_olay.hacim_carpani < 1:
        raise ValueError(
            "kurumsal_olay.hacim_carpani 1'den kucuk olamaz "
            "(1 = medyan hacim, altini 'artis' saymak anlamsiz)"
        )

    kaynak_ham = varlik_ham.get("veri_kaynaklari") or {}
    ucgen_ham = kaynak_ham.get("ucgenleme") or {}
    kaynaklar = VeriKaynaklari(
        btcturk_url=str((kaynak_ham.get("btcturk") or {}).get("url", "")),
        btcturk_ciftleri=dict((kaynak_ham.get("btcturk") or {}).get("ciftler") or {}),
        coingecko_url=str((kaynak_ham.get("coingecko") or {}).get("url", "")),
        coingecko_kimlikleri=dict(
            (kaynak_ham.get("coingecko") or {}).get("kimlikler") or {}),
        tcmb_url=str((kaynak_ham.get("tcmb") or {}).get("url", "")),
        tcmb_seri=str(
            (kaynak_ham.get("tcmb") or {}).get("seri", "TP.DK.USD.A.EF.YTL")),
        tcmb_bayatlik_gun=int((kaynak_ham.get("tcmb") or {}).get("bayatlik_gun", 1)),
        btcturk_bayatlik_dakika=float(
            ucgen_ham.get("btcturk_bayatlik_dakika", 15.0)),
        prim_esigi=float(ucgen_ham.get("prim_esigi", 0.03)),
        durdurma_esigi=float(ucgen_ham.get("durdurma_esigi", 0.08)),
    )
    if not 0 < kaynaklar.prim_esigi < kaynaklar.durdurma_esigi < 1:
        raise ValueError(
            "ucgenleme esikleri 0 < prim_esigi < durdurma_esigi < 1 olmali; "
            f"prim={kaynaklar.prim_esigi}, durdurma={kaynaklar.durdurma_esigi}"
        )
    # Sembol yazim hatasi sessizce kaynagi devre disi birakmasin.
    for ad, harita in (("btcturk.ciftler", kaynaklar.btcturk_ciftleri),
                       ("coingecko.kimlikler", kaynaklar.coingecko_kimlikleri)):
        tanimsiz = sorted(set(harita) - set(varliklar))
        if tanimsiz:
            raise ValueError(
                f"veri_kaynaklari.{ad} icinde varliklar.yaml'da olmayan "
                f"sembol var: {tanimsiz}")

    sinif_haritasi = {s: v.sinif for s, v in varliklar.items()}
    maliyet = modeli_kur(varlik_ham, sinif_haritasi)
    _maliyeti_dogrula(varlik_ham, varliklar)

    return Yapilandirma(
        ayarlar=Ayarlar(
            kur_sembolu=ayar_ham["kur_sembolu"],
            gecmis_gun=int(ayar_ham["gecmis_gun"]),
            islem_gunu_yil=int(ayar_ham["islem_gunu_yil"]),
        ),
        esikler=esikler,
        hedef_dagilim=hedef_dagilim,
        varliklar=varliklar,
        nakit_try=float(portfoy_ham.get("nakit_try", 0.0)),
        pozisyonlar=pozisyonlar,
        sablon=bool(portfoy_ham.get("sablon", False)),
        bayatlik=bayatlik,
        kurumsal_olay=kurumsal_olay,
        kaynaklar=kaynaklar,
        maliyet=maliyet,
        bekleme=bekleme,
        devre_kesici=devre_kesici,
    )


def _maliyeti_dogrula(varlik_ham: dict, varliklar: dict[str, Varlik]) -> None:
    """Maliyet blogundaki yazim hatalarini yakalar.

    Yazim hatasi burada sessizce "eksik kalem"e donusurse sinyal bastirilir ve
    sebep hicbir zaman anlasilmaz: rapor "profil tanimsiz" der, YAML'da profil
    gorunur durur. Hatayi okuma aninda patlatmak tek dogru davranis.
    """
    maliyet_ham = varlik_ham.get("maliyet") or {}
    profil_haritasi = maliyet_ham.get("sinif_profili") or {}
    tanimli_profiller = set(maliyet_ham.get("islem") or {})
    siniflar = {v.sinif for v in varliklar.values()}

    tanimsiz_sinif = sorted(set(profil_haritasi) - siniflar)
    if tanimsiz_sinif:
        raise ValueError(
            f"maliyet.sinif_profili'nde tanimsiz varlik sinifi: {tanimsiz_sinif}. "
            f"Gecerli siniflar: {sorted(siniflar)}")

    eksik_profil = sorted(set(profil_haritasi.values()) - tanimli_profiller)
    if eksik_profil:
        raise ValueError(
            f"maliyet.sinif_profili tanimsiz profile isaret ediyor: {eksik_profil}. "
            f"maliyet.islem altinda tanimli olanlar: {sorted(tanimli_profiller)}")

    tanimsiz_sembol = sorted(set(maliyet_ham.get("tasima") or {}) - set(varliklar))
    if tanimsiz_sembol:
        raise ValueError(
            f"maliyet.tasima'da varliklar.yaml'da olmayan sembol: {tanimsiz_sembol}")

    nakit_ham = varlik_ham.get("nakit") or {}
    kaynak = nakit_ham.get("getiri_kaynagi")
    if kaynak not in (None, "tl_risksiz"):
        raise ValueError(
            f"nakit.getiri_kaynagi yalnizca 'tl_risksiz' olabilir, '{kaynak}' geldi")


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
