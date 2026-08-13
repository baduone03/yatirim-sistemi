# Yatirim Sistemi

BIST, Nasdaq, kripto ve madenler arasinda dagitilmis bir portfoyu **olcen ve
sapma oldugunda uyaran** karar destek sistemi. Emir vermez, fiyat tahmini yapmaz.

> Su an calisan tek sey **20.000 TL'lik kagit portfoy simulasyonu**.
> Gercek para yok. `portfoy.yaml` sablon durumunda ve gercek portfoy raporu
> uretmeyi reddeder.

Bu repo bir Obsidian vault'un icinden yalnizca yatirim sistemini yayinlar.
Kisisel notlar (`01-inbox`, `03-wiki`, `05-daily` ...) `.gitignore` beyaz
listesi ile disarida tutulur.

## Ne yapiyor

1. Yahoo Finance'ten fiyat ceker, hepsini TL bazina cevirir
2. Pozisyon degeri, maliyet ve kar/zarari hesaplar
3. Risk olcer: yillik volatilite, korelasyon matrisi, max drawdown,
   Euler risk katkisi
4. Hedef dagilimdan sapmayi bulur, esik asilinca rebalancing uyarisi verir
5. Markdown rapor yazar, Telegram'a ozet gonderir

## Calistirma

```bash
pip install -r scripts/yatirim/requirements.txt

python scripts/yatirim/main.py --sim              # simulasyon raporu
python scripts/yatirim/main.py --sim --telegram   # + Telegram ozeti
python scripts/yatirim/tarama.py --sim            # BIST evren taramasi
python -m unittest discover -s scripts/yatirim -p "test_*.py"
```

## Otomatik calistirma

`.github/workflows/gunluk-rapor.yml` hafta ici 16:00 UTC (19:00 TR) calisir:
testleri kosar, raporu uretir, Telegram'a yollar, sonucu repoya commit eder.
Hata olursa Telegram'a uyari duser.

Gerekli repository secrets:

| Secret | Nereden |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram'da @BotFather -> `/newbot` |
| `TELEGRAM_CHAT_ID` | Telegram'da @userinfobot |

Bota Telegram'dan once **Start** demen gerekir, aksi halde `chat not found`.

## Yapilandirma

Sembol, hedef agirlik ve pozisyon degisiklikleri **yalnizca YAML** dosyalarinda
yapilir, kod degismez.

| Dosya | Ne icin |
|---|---|
| `04-projects/yatirim-sistemi/varliklar.yaml` | Semboller, varlik siniflari, hedef dagilim |
| `04-projects/yatirim-sistemi/portfoy.yaml` | Gercek portfoy (su an sablon) |
| `04-projects/yatirim-sistemi/bist-evreni.yaml` | BIST tarama aday havuzu |
| `04-projects/yatirim-sistemi/simulasyon/islemler.yaml` | Simulasyon islem defteri (append-only) |

## Onemli teknik not

Risk metrikleri **ortak islem takvimi** uzerinden hesaplanir - yalnizca tum
varliklarin acik oldugu gunler. BIST hafta sonu kapali, kripto acik: kapali
gunleri doldurmak volatiliteyi %20-25 dusuk gosterir, doldurmamak da her
Pazartesi'yi siler. Detay `scripts/yatirim/risk.py` -> `ortak_getiriler`.

## Limitler

- Yahoo Finance verisi gecikmeli olabilir; eksik veri raporda isaretlenir, uydurulmaz
- Gecmis volatilite ve korelasyon gelecek riski garanti etmez
- Korelasyon sakin donemde olculur, kriz aninda 1'e kosar
- **Yatirim tavsiyesi degildir.**
