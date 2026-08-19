"""Actions kosu suresini izler ve yavaslamayi bildirir.

NEDEN: GitHub kosu basina YUKARI YUVARLAYARAK faturalar. 39 saniyelik kosu
1 dakika, 61 saniyelik kosu 2 DAKIKA yazilir. Yani kosu suresinin 60 saniyeyi
gecmesi butceyi bir anda IKIYE katlar - ve bu sessizce olur: hicbir sey
kirilmaz, hicbir hata cikmaz, ay sonunda kota bitmis olur.

Esik 50 saniye, 60 degil: sinirda uyarmak gec kalmaktir. 10 saniyelik pay,
yeni bir ag cagrisi eklendiginde durumu fark etmeye yeter.

Uyari gunde BIR kez gider - `gonderilen.log` uzerinden gunluk idempotency
anahtariyla (`uyari:kosu-suresi:{tarih}`). Her kosuda gonderilseydi uyarinin
kendisi gurultu olurdu.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

from bildirim import Bildirim, ayarlari_oku
from config import TR_OFSET, simdi_utc
from notify import env_oku, kanaldan_gonder

# 60 saniye faturayi ikiye katlar; 50'de uyar ki tedbir alacak zaman olsun.
ESIK_SANIYE = 50.0
ORNEK_KOSU = 10
ZAMAN_ASIMI = 20


def ortalama_saniye(kosular: list[dict]) -> tuple[float, int]:
    """Doner: (ortalama saniye, ornek sayisi).

    Bitmemis (negatif) ve takilmis (>1 saat) kosular DISARIDA: ikisi de
    ortalamayi anlamsiz kilar. Ornek yoksa (0.0, 0) doner.
    """
    sureler = []
    for kosu in kosular:
        try:
            basla = datetime.fromisoformat(str(kosu["created_at"]).replace("Z", "+00:00"))
            bitis = datetime.fromisoformat(str(kosu["updated_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        saniye = (bitis - basla).total_seconds()
        if 0 <= saniye < 3600:
            sureler.append(saniye)
    if not sureler:
        return 0.0, 0
    return sum(sureler) / len(sureler), len(sureler)


def uyari_metni(ortalama: float, ornek: int) -> str:
    fatura = 2 if ortalama > 60 else 1
    return (
        f"<b>Actions kosu suresi artti</b>\n"
        f"Son {ornek} kosunun ortalamasi <b>{ortalama:.0f} saniye</b> "
        f"(esik {ESIK_SANIYE:.0f}).\n\n"
        f"GitHub kosu basina yukari yuvarlar: 60 saniyeyi asan kosu "
        f"1 degil 2 dakika faturalanir. Su an kosu basina ~{fatura} dakika.\n\n"
        f"60'i asarsa aylik butce IKIYE katlanir. Yeni bir ag cagrisi veya "
        f"agir hesap eklendiyse geri al, yoksa tarama sikligini dusur."
    )


def kosulari_cek(repo: str, jeton: str, getir=None) -> list[dict]:
    """Son N kosu. Ag katmani enjekte edilebilir - testler ag'a cikmaz.

    HICBIR sekilde yukari patlamaz. Butce izleme yardimci bir islevdir;
    coktugunde tum rapor kosusunu kirmasi, cozmeye calistigi sorundan
    (sessiz butce tukenmesi) daha kotu olurdu. Bu yuzden `except Exception`
    ve bu yuzden enjekte edilen `getir` de ayni korumanin ICINDE.
    """
    try:
        if getir is not None:
            return getir(repo, jeton)
        url = f"https://api.github.com/repos/{repo}/actions/runs?per_page={ORNEK_KOSU}"
        istek = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {jeton}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "yatirim-sistemi",
        })
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            return json.loads(yanit.read()).get("workflow_runs") or []
    except Exception as hata:                     # noqa: BLE001
        print(f"UYARI - kosu suresi olculemedi: {type(hata).__name__}",
              file=sys.stderr)
        return []


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    jeton = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not jeton:
        print("Kosu suresi olculmedi: GITHUB_REPOSITORY/GITHUB_TOKEN yok.")
        return 0

    ortalama, ornek = ortalama_saniye(kosulari_cek(repo, jeton))
    if ornek == 0:
        print("Kosu suresi olculemedi (ornek yok).")
        return 0

    print(f"Son {ornek} kosu ortalamasi: {ortalama:.1f} sn (esik {ESIK_SANIYE}).")
    if ortalama <= ESIK_SANIYE:
        return 0

    simdi = simdi_utc()
    gun = (simdi + TR_OFSET).date().isoformat()
    sonuc = kanaldan_gonder(
        Bildirim(tip="uyari", anahtar=f"uyari:kosu-suresi:{gun}",
                 metin=uyari_metni(ortalama, ornek)),
        ayarlari_oku(), env_oku(), simdi=simdi)
    print(f"Kosu suresi uyarisi: {sonuc.durum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
