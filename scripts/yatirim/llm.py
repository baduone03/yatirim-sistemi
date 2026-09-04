"""NVIDIA NIM istemcisi: metinden metin, tek cagri.

NE ICIN VAR: bu sistemde sayilar OLCULUR, cumleler yazilmaz. Iki yerde
cumleye ihtiyac var - haber basliklarini portfoye gore siralamak ve gun sonu
mesajinin basina uc cumlelik bir okuma koymak. Ikisi de KARAR YOLUNUN
DISINDA; model ne derse desin hicbir sinyal, hicbir agirlik, hicbir esik
degismez.

NEDEN AYRI MODUL: cagri kalibi (anahtar okuma, zaman asimi, JSON govde,
hata cevirisi) iki cagiran arasinda ortak. Iki yerde ayri yazilsaydi biri
zaman asimini kisaltip digeri unuturdu.

TASARIM: `gonder` enjekte edilir (`kaynaklar.py` ile ayni kalip). Testler
sahte bir gonderici gecirir, ag'a hic cikilmaz.

ANAHTAR HICBIR YERDE BASILMAZ. Hata mesajinda yalnizca HTTP kodu ve API'nin
kendi aciklamasi gorunur - `kaynaklar.py`'deki ayni disiplin.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

UC_NOKTA = "https://integrate.api.nvidia.com/v1/chat/completions"
ANAHTAR_ADI = "NVIDIA_API_KEY"


class LLMHatasi(RuntimeError):
    """Model cagrilamadi. Cagiran, ozetsiz devam etmeye karar verir."""


@dataclass(frozen=True)
class LLMAyarlari:
    """`varliklar.yaml -> veri_kaynaklari.llm` karsiligi.

    Model adi KODDA SABIT DEGIL: NIM katalogu degisiyor ve bir modelin
    hesaba kapanmasi (HTTP 404) yalnizca YAML duzenlemesiyle cozulebilmeli.
    """

    model: str = "mistralai/mistral-nemotron"
    zaman_asimi: float = 25.0
    azami_jeton: int = 900
    acik: bool = False          # anahtar olsa bile YAML kapatabilir

    @property
    def kullanilabilir(self) -> bool:
        return self.acik and bool(self.model)


def _govde(istem: str, ayarlar: LLMAyarlari) -> bytes:
    return json.dumps({
        "model": ayarlar.model,
        "messages": [{"role": "user", "content": istem}],
        # Sicaklik 0: ayni girdi ayni ciktiyi versin. Ozet mesaja giriyor ve
        # her kosuda farkli kelimelerle ayni seyi soyleyen bir metin,
        # degisimin kendisini okunmaz yapar.
        "temperature": 0.0,
        "max_tokens": ayarlar.azami_jeton,
        # Nemotron ailesi dusunme metnini `content` icine sizdirabiliyor;
        # kapatilmazsa cikti "Here's a thinking process:" ile basliyor.
        "chat_template_kwargs": {"thinking": False},
    }).encode("utf-8")


def http_llm(istem: str, ayarlar: LLMAyarlari, anahtar: str) -> str:
    """Varsayilan ag katmani. Testlerde bunun YERINE sahte gecirilir."""
    istek = urllib.request.Request(
        UC_NOKTA, data=_govde(istem, ayarlar),
        headers={"Authorization": f"Bearer {anahtar}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=ayarlar.zaman_asimi) as cevap:
            veri = json.load(cevap)
    except urllib.error.HTTPError as hata:
        # API'nin kendi aciklamasi taniyi hizlandirir (404 = model hesaba
        # kapali, 401 = anahtar gecersiz). Anahtarin kendisi asla yazilmaz.
        aciklama = hata.read()[:200].decode("utf-8", "replace")
        raise LLMHatasi(
            f"{ayarlar.model}: HTTP {hata.code} - {aciklama}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        raise LLMHatasi(
            f"{ayarlar.model} cagrilamadi: {type(hata).__name__}") from None

    try:
        secim = veri["choices"][0]
        icerik = (secim["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise LLMHatasi(f"{ayarlar.model}: beklenen cevap bicimi gelmedi") from None

    # Jeton tavanina takilan cevap YARIM kalir ve JSON'u ortasindan kesilir.
    # Ayri hata olmasa tani "model cevabi JSON degil" olurdu ve saatlerce
    # istem bicimi aranirdi - oysa sorun istemde degil, tavanda.
    if secim.get("finish_reason") == "length":
        raise LLMHatasi(
            f"{ayarlar.model}: cikti {ayarlar.azami_jeton} jeton tavanina "
            "takildi, cevap yarim kaldi. Ya azami_jeton yukseltilmeli ya da "
            "modelden daha az sey istenmeli (varliklar.yaml -> "
            "veri_kaynaklari.llm).")
    return icerik


def sor(istem: str, ayarlar: LLMAyarlari, env: dict[str, str],
        gonder=http_llm) -> str:
    """Modeli cagirir, ham metni doner.

    Anahtar yoksa HATA firlatir, sessizce bos donmez: "ozet neden yok"
    sorusunun cevabi loglarda gorunmeli. Cagiran hatayi yakalayip ozetsiz
    devam etmeye karar verir - ozet bir kolayliktir, rapor degil.
    """
    if not ayarlar.kullanilabilir:
        raise LLMHatasi("llm.acik false veya model tanimsiz - ozet uretilmedi")
    anahtar = (env or {}).get(ANAHTAR_ADI, "").strip()
    if not anahtar:
        raise LLMHatasi(
            f"{ANAHTAR_ADI} tanimsiz. Yerelde .env dosyasina, GitHub "
            "Actions'ta repository secret olarak eklenir; ikisinde de "
            "eksikse ozet uretilmez ve sistem ham ciktiya duser.")
    return gonder(istem, ayarlar, anahtar)


def json_coz(ham: str):
    """Model ciktisindan JSON cikarir. ```json cercevesi ve on/arka metin toleransli.

    Modeller istenmese de cerceve ekliyor ve arada "Iste sonuc:" yaziyor.
    Ham metni dogrudan `json.loads`e vermek bu yuzden guvenilmez; ilk `[` veya
    `{` ile son kapanis arasi alinir.
    """
    metin = ham.strip()
    if metin.startswith("```"):
        metin = metin.split("```")[1] if "```" in metin[3:] else metin[3:]
        if metin.lstrip().lower().startswith("json"):
            metin = metin.lstrip()[4:]
    # Adaylar DISTAN ICE denenir: once metinde EN ONCE gelen acilis. Sabit
    # bir sira ("once dizi, sonra nesne") bir nesnenin ICINDEKI diziyi
    # yakalayip disindaki nesneyi kaciriyordu - `{"yuksek": [...]}` cevabi
    # dizi sanilip "nesne degil" hatasi uretiyordu.
    adaylar = sorted(
        ((metin.find(ac), ac, kapa) for ac, kapa in (("{", "}"), ("[", "]"))
         if metin.find(ac) >= 0))
    for bas, _, kapa in adaylar:
        son = metin.rfind(kapa)
        if bas < son:
            try:
                return json.loads(metin[bas:son + 1])
            except ValueError:
                continue
    raise LLMHatasi("model cevabi JSON degil")
