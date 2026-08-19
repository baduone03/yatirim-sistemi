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

```bash
cd altyapi/telegram-webhook

wrangler secret put TELEGRAM_BOT_TOKEN       # mevcut bot token'ın
wrangler secret put TELEGRAM_WEBHOOK_SECRET  # 2. adımdaki dize
wrangler secret put GITHUB_PAT               # 3. adımdaki token
wrangler secret put IZINLI_CHAT_ID           # senin chat id'in
```

Her komut değeri **sorarak** alır; hiçbiri dosyaya yazılmaz, komut
geçmişine düşmez.

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

- Worker'da **hiçbir anahtar yazılı değil**; hepsi Cloudflare secret'ı.
  `worker.js` ve `wrangler.toml` git'te izleniyor, ikisi de temiz.
- Üç katmanlı doğrulama: Telegram secret header → chat id beyaz listesi →
  yalnızca `/` ile başlayan komutlar. İlk iki katman olmasaydı Worker
  URL'ini bulan biri sınırsız Actions dakikası yakabilirdi.
- Bot workflow'u chat id'yi **tekrar** kontrol eder. Sebep: repo'ya yazma
  yetkisi olan biri Worker'ı atlayıp doğrudan `repository_dispatch`
  atabilir; yetki kontrolü tek katmana bırakılamaz.
- Worker Telegram hatalarını yutar ve loglamaz — hata gövdesi istek URL'ini,
  yani bot token'ını taşıyabilir.

## Kota frenleri

`worker.js` içindeki `AYAR` bloğunda:

| ayar | değer | ne yapar |
|---|---|---|
| `ASGARI_ARALIK_SN` | 90 | Bu süreden sık tetiklenmez; "N dakika sonra tekrar sor" der. |
| `UYARI_ORANI` | 0.80 | %80 kullanımda haber verir, çalışmaya devam eder. |
| `TAVAN_ORANI` | 0.92 | %92'de sorgu botunu durdurur. Günlük rapor korunur — öncelik onda. |

Kullanım GitHub API'sinden ölçülüyor (ay başından bu yana koşu sayısı × 1 dk).
Ölçüm başarısız olursa fren **açılır**, sistem kilitlenmez.
