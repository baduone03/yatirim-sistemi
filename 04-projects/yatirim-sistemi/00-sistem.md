---
title: Yatirim Sistemi
date_created: 2026-08-12
tags: [proje, yatirim, risk, portfoy]
status: active
related: ["[[varlik-dagilimi]]", "[[volatilite]]", "[[max-drawdown]]", "[[korelasyon]]", "[[rebalancing]]", "[[risk-butcesi]]"]
---

# Yatirim Sistemi

Sinirli sermayeyi BIST, Nasdaq, kripto ve madenler arasinda dagitip
riski olcerek yoneten karar destek sistemi. Emir vermez, tahmin yapmaz:
**olcer ve sapma oldugunda uyarir.**

## Guncel durum

<!-- OZET:BASLANGIC -->
**Gercek portfoy yok** - `portfoy.yaml` sablon durumunda, rapor uretilmiyor.

Aktif calisan: **20.000 TL simulasyon** -> [[00-simulasyon]]
<!-- OZET:BITIS -->

## Temel ilkeler

1. **Once risk, sonra getiri.** Pozisyon buyuklugu beklenen getiriye gore degil,
   portfoy volatilitesine katkisina gore belirlenir. Bkz. [[risk-butcesi]]
2. **Cesitlendirme korelasyonla olculur, sayiyla degil.** On tane birbirine %0.9
   korele varlik tek pozisyondur. Bkz. [[korelasyon]]
3. **Hedef dagilim onceden yazilir.** Piyasa hareket ettikce agirliklar kayar;
   kural piyasa aninda degil sakinken kurulur. Bkz. [[varlik-dagilimi]]
4. **Sapma esigi 5 puan.** Bir varlik sinifi hedefinden 5 puan sapinca
   rebalancing uyarisi cikar. Bkz. [[rebalancing]]
5. **Kur bir risktir, muhasebe detayi degil.** Tum metrikler TL bazinda
   hesaplanir, USD varliklarin kur riski volatiliteye dahildir.
6. **Kayip toleransi onceden bilinir.** Max drawdown gecmiste ne kadar
   dusus yasandigini gosterir. Bkz. [[max-drawdown]]

## Dosyalar

| Dosya | Ne icin |
|---|---|
| `varliklar.yaml` | Izlenen semboller, varlik siniflari, hedef dagilim |
| `portfoy.yaml` | Pozisyonlar, maliyetler, nakit |
| `bist-evreni.yaml` | BIST Yildiz Pazar aday havuzu (tarama icin, ana rapora girmez) |
| `simulasyon/` | 20k TL kagit portfoy - bkz. [[00-simulasyon]] |
| `raporlar/` | Tarihli rapor ciktilari |

Sembol eklemek/cikarmak, hedef agirlik degistirmek icin **yalnizca YAML
dosyalarini** duzenle. Kod tarafinda degisiklik gerekmez.

## Calistirma

```
python scripts/yatirim/main.py --sim            # simulasyon raporu  <- AKTIF
python scripts/yatirim/main.py --sim --telegram # + Telegram ozeti
python scripts/yatirim/tarama.py --sim          # BIST evren taramasi
python scripts/yatirim/main.py                  # gercek portfoy (sablon iken durur)
```

`raporlar/YYYY-AA-GG.md` yazar ve yukaridaki ozet blogunu gunceller.

## Sablon korumasi

`portfoy.yaml` icinde `sablon: true` oldugu surece **gercek portfoy raporu
uretilmez** - script net bir hatayla durur. Sebep: doldurulmamis ornek veriyle
uretilen rapor gercek gibi gorunur ve Telegram'a gercek gibi duser.

Gercek parayla baslarken: pozisyonlari yaz, `sablon: true` satirini sil.

## Otomatik calistirma

Windows Task Scheduler gorevi: **`IkinciBeyin-YatirimRaporu`**
Hafta ici her gun 19:00'da `scripts/yatirim/gunluk.ps1` calisir
(simulasyon raporu + Telegram ozeti). Log: `scripts/yatirim/loglar/gunluk.log`

```powershell
Get-ScheduledTask -TaskName IkinciBeyin-YatirimRaporu        # durum
Start-ScheduledTask -TaskName IkinciBeyin-YatirimRaporu      # elle tetikle
Unregister-ScheduledTask -TaskName IkinciBeyin-YatirimRaporu # kaldir
```

## Testler

```
python -m unittest discover -s scripts/yatirim -p "test_*.py"
```

23 test, tamami cevrimdisi (sentetik veri, Yahoo'ya gitmez). Kodu
degistirdikten sonra calistir.

## Telegram bildirimi

Vault kokune `.env` koy (`.env.example`'i kopyala):

```
TELEGRAM_BOT_TOKEN=...   # @BotFather -> /newbot
TELEGRAM_CHAT_ID=...     # @userinfobot
```

Bota Telegram'dan once **Start** demen gerekir, aksi halde `chat not found`.
`.env` `.gitignore`'da - asla paylasilmaz.

Mesaj yalnizca **esik asilinca** anlam tasir: rebalancing sapmasi veya
risk katkisi %25 ustu. Esik asilmadiysa "islem gerekmiyor" yazar.

## BIST evren taramasi

`tarama.py` 59 hisselik Yildiz Pazar evrenini mevcut portfoyunle
**korelasyona gore** siralar. Amaci "hangi hisse yukselir" degil -
"hangi hisse portfoyume en az benzeyen riski getirir".

Cikti: `raporlar/tarama-YYYY-AA-GG.md`

## Veri kaynagi

Yahoo Finance (`yfinance`). Tek bagimlilik, API anahtari yok.

| Sinif | Sembol ornegi |
|---|---|
| BIST | `THYAO.IS`, `XU100.IS` |
| Nasdaq | `QQQ`, `NVDA` |
| Kripto | `BTC-USD`, `ETH-USD` |
| Maden | `GC=F` (altin ons), `SI=F` (gumus ons) |
| Kur | `USDTRY=X` |

Ons -> gram cevrimi `carpan: 0.0321507` alaniyla yapilir.

## Bilinen sinirlar

- Yahoo verisi gecikmeli; BIST sembollerinde bosluk olabilir. Script eksik
  veriyi raporda isaretler, uydurmaz.
- Risk metrikleri **ortak islem takvimi** uzerinden hesaplanir: yalnizca tum
  varliklarin acik oldugu gunler. Yilda ~238 gun kalir. Kriptonun hafta sonu
  hareketi Pazartesi getirisine katilir.
- Gecmis volatilite gelecegi garanti etmez.
- Maliyetin TL cevrimi guncel kurla yapilir; kur farki K/Z'ye ayrisik yansimaz.
- Sistem yatirim tavsiyesi vermez.

## Sonraki adimlar

- [ ] Ornek `portfoy.yaml` verisini gercek pozisyonlarla degistir
- [ ] Hedef dagilimi kendi risk istahina gore ayarla
- [ ] Haftalik otomatik calistirma (Windows Task Scheduler)
