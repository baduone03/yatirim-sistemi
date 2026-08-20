# Telegram Webhook Worker Tuzaklari

Cloudflare Worker'in kendi davranisi: yanit kodlari, sira, kota freni. Yalnizca
bu klasorde calisirken gecerli B kategorisi maddeler - A maddeleri kok
`CLAUDE.md`'dedir ve buraya YAZILMAZ.

## Gotchas (B)

- **Worker HER ZAMAN HTTP 200 doner**: 401/500 donerse Telegram webhook'u devre disi birakabilir
  veya sonsuz yeniden deneme baslatir. Yetkisiz istek sessizce yutulur - reddedildigi belli
  EDILMEZ.
- **webhook maliyeti KULLANIMA bagli**: yoklama sabit ~1095 dk/ay yakiyordu, webhook ~10
  mesaj/gunde ~300 dk. Ama gunde 40 komut ~1200 dk eder. `worker.js -> AYAR` iki fren tutuyor:
  `ASGARI_ARALIK_SN` (90 sn) ve `TAVAN_ORANI` (0.92). Tavanda sorgu botu durur, gunluk rapor
  DURMAZ - oncelik onda.
- **Worker sirasi sabit**: secret_token (401) -> chat id (200 sessiz) -> komut bicimi -> sogutma
  -> kota tavani -> dispatch. Sogutma tavandan ONCE: sogutma ANLIK korumadir (pes pese mesaj),
  tavan AYLIK. Sirasi tersine cevrilirse hizli yazan biri "kota %40" hesabina takilmaz ve 20
  kosu acar.
- **`secret_token` yoksa 401, 200 DEGIL**: Telegram'in kendi istekleri her zaman dogru basligi
  tasir, yani 401 alan istek sahtedir. Ayrica setWebhook'ta secret unutulmussa 401 Telegram
  tarafinda GORUNUR hata olarak birikir; sessiz 200 bu yanlis kurulumu "her mesaj kayboluyor"
  seklinde gizlerdi.
- **yetkisiz chat'e CEVAP DONMEZ**: "yetkin yok" demek bile botun orada oldugunu dogrular.
- **kota GERCEK kosu suresinden hesaplanir**: `kotaOzeti` sureyi olcup `ceil(sn/60)` uygular.
  "Kosu basina 1 dk" varsaymak, kosular yavasladiginda kotayi gercegin YARISI gosterir ve fren
  hic devreye girmez. 39 sn = 1 dk, 61 sn = 2 dk.
- **kota olcumu basarisizsa fren ACILIR**: `frenKontrol` null doner, istek gecer. Olcememeyi
  "kota dolmus" saymak, GitHub API hikkirigini botun tumden susmasina cevirirdi. Ayni felsefe
  `kosu_suresi.kosulari_cek`'te: hicbir sekilde yukari patlamaz, `[]` doner.
