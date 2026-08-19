# Telegram webhook kurulumu

Amaç: Telegram'a yazdığın komut **anında** GitHub Actions koşusu tetiklesin.
Cevap 30 dakika yerine ~40 saniyede gelir, aylık Actions kullanımı %75'ten
%35'e düşer.

**Bu adımları sen yapacaksın** — token ve hesap işlemlerine ben dokunmuyorum.
Her adım tek komut; toplam ~10 dakika.

## Önce bil: geri dönüş tek satır

Bir şey ters giderse botu eski haline döndüren komut:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook"
```

Webhook silinince `getUpdates` tekrar çalışır. Sonra `bot-sorgu.yml` içindeki
cron bloğunu geri koyarız.

## 1. Cloudflare hesabı ve wrangler

```bash
npm install -g wrangler
wrangler login
```

Ücretsiz katman yeterli: günde 100.000 istek. Kredi kartı istemiyor.

## 2. Webhook secret'ı üret

Telegram'ın gönderdiği her isteğe koyacağı parola. Bunu sen üretiyorsun,
kimseye vermiyorsun:

```bash
openssl rand -hex 32
```

Çıkan dizeyi bir yere kopyala — 4. ve 5. adımda lazım.

## 3. GitHub PAT üret

github.com → Settings → Developer settings → **Fine-grained tokens** → Generate

- Repository access: **Only select repositories** → `baduone03/yatirim-sistemi`
- Permissions → Repository permissions → **Contents: Read and write**
- Başka hiçbir izin verme. Süre: 1 yıl.

`Contents: Read and write` gerekli çünkü `repository_dispatch` bu izni
istiyor. Classic token kullanma — kapsamı tüm hesabı kapsar.

## 4. Secret'ları Cloudflare'e gir

Dört secret + bir değişken. `IZINLI_CHAT_ID` **secret olarak** giriliyor,
`wrangler.toml`'a yazılmıyor: `vars` bölümü Cloudflare panelinde açık metin
görünür ve bu dosya git'te izleniyor.

```bash
cd altyapi/telegram-webhook

wrangler secret put TELEGRAM_BOT_TOKEN       # mevcut bot token'ın
wrangler secret put TELEGRAM_WEBHOOK_SECRET  # 2. adımdaki dize
wrangler secret put GITHUB_PAT               # 3. adımdaki token
wrangler secret put IZINLI_CHAT_ID           # senin chat id'in (virgülle çoklu)
```

Her komut değeri **sorarak** alır; hiçbiri dosyaya yazılmaz, komut
geçmişine düşmez.

`GITHUB_REPO` gizli değil (PAT'in kapsamında zaten belli) — `wrangler.toml`
içindeki `vars` bölümünde duruyor.

**Chat id'ini bilmiyorsan:** Telegram'da `@userinfobot`'a yaz, sana söyler.

`IZINLI_CHAT_ID` boş bırakılırsa **kimse** geçemez — "ayar yoksa herkese
açık" değil, "kimseye kapalı". Bot tarafındaki
`TELEGRAM_IZINLI_CHAT_ID` secret'ıyla aynı mantık.

## 5. Deploy et ve webhook'u bağla

```bash
wrangler deploy
```

Çıktıdaki URL'i (`https://yatirim-telegram-webhook.<hesap>.workers.dev`) al ve:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://yatirim-telegram-webhook.<hesap>.workers.dev" \
  -d "secret_token=<2. ADIMDAKI DIZE>" \
  -d "allowed_updates=[\"message\"]"
```

`{"ok":true,"result":true}` görmen lazım.

## 6. Test

Telegram'a `/durum` yaz. ~40 saniye içinde cevap gelmeli.

Gelmezse sırayla bak:

```bash
# Telegram webhook'u ne durumda gördüğünü söyler
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"

# Worker logları (canlı)
wrangler tail
```

`getWebhookInfo` içinde `last_error_message` doluysa sorun Worker'da,
`pending_update_count` yüksekse Worker cevap vermiyor demektir.

## Güvenlik notları

Yetki kontrolü **Worker'da** yapılıyor, Actions'ta değil. Telegram botları
herkese açıktır: bot adını bilen herkes mesaj yazabilir. Süzme Actions
tarafında kalsaydı her yabancı mesaj bir koşu başlatır ve 1 dakika kota
yakardı — yani botun adını bilen biri kotayı tüketebilirdi.

Sıra (her adım bir öncekini geçmeden çalışmaz):

| # | kontrol | geçmezse |
|---|---|---|
| 1 | `secret_token` başlığı | **401**, dispatch yok |
| 2 | chat id beyaz listesi | 200 sessiz, dispatch yok, **cevap da yok** |
| 3 | `/` ile başlayan komut | 200, dispatch yok |
| 4 | 90 sn soğuma | "N dakika sonra tekrar sor" |
| 5 | aylık kota tavanı | "kota doldu" |
| 6 | `repository_dispatch` | — |

- **401 neden güvenli:** Telegram'ın kendi istekleri her zaman doğru başlığı
  taşır, yani 401 alan istek zaten sahtedir. Ayrıca `setWebhook`'ta
  `secret_token` unutulmuşsa bu Telegram tarafında görünür hata olarak
  birikir; sessizce 200 dönmek yanlış kurulumu her mesajın kaybolması
  şeklinde gizlerdi.
- **Yetkisiz chat'e cevap dönmez.** "Yetkin yok" demek bile botun orada
  olduğunu doğrular.
- Worker'da **hiçbir anahtar yazılı değil**; hepsi Cloudflare secret'ı.
  `worker.js`, `wrangler.toml` ve `package.json` git'te izleniyor, üçü de temiz.
- Bot workflow'u chat id'yi **tekrar** kontrol eder — ikinci savunma. Repo'ya
  yazma yetkisi olan biri Worker'ı atlayıp doğrudan `repository_dispatch`
  atabilir; yetki kontrolü tek katmana bırakılamaz.
- Worker Telegram hatalarını yutar ve loglamaz — hata gövdesi istek URL'ini,
  yani bot token'ını taşıyabilir.

## Kota frenleri

`worker.js` içindeki `AYAR` bloğunda:

| ayar | değer | ne yapar |
|---|---|---|
| `ASGARI_ARALIK_SN` | 90 | Bu süreden sık tetiklenmez; "N dakika sonra tekrar sor" der. |
| `TAVAN_ORANI` | 0.92 | %92'de sorgu botunu durdurur. Günlük rapor korunur — öncelik onda. |

Kullanım **gerçek koşu sürelerinden** hesaplanıyor, "koşu başına 1 dakika"
varsayılmıyor. GitHub yukarı yuvarlar: 39 saniyelik koşu 1 dakika, 61
saniyelik koşu **2 dakika**. Sabit 1 dk varsaymak, koşular yavaşladığında
kotayı gerçeğin yarısı gösterir ve fren hiç devreye girmez.

Ölçüm başarısız olursa fren **açılır**, sistem kilitlenmez — GitHub API'sinin
bir hıçkırığı botu tümden susturmamalı.

Ayrıca Actions tarafında `kosu_suresi.py` son 10 koşunun ortalamasını izliyor;
50 saniyeyi aşarsa günde bir kez Telegram'a uyarı düşüyor.

## Testler

```bash
node --test altyapi/telegram-webhook/worker.test.js
```

Bağımlılık yok — Node'un yerleşik koşucusu. Ağa çıkmaz, `fetch` sahteyle
değiştirilir. Günlük rapor workflow'u da bu testleri koşuyor: kırık bir fren
sessizce kota tüketir.
