---
title: 20k TL Simulasyonu
date_created: 2026-08-13
tags: [yatirim, simulasyon, portfoy, karar-gunlugu]
status: active
related: ["[[00-sistem]]", "[[risk-butcesi]]", "[[korelasyon]]", "[[rebalancing]]"]
---

# 20k TL Simulasyonu

Kagit uzerinde 20.000 TL. Gercek para yok. Alim/satim kararlarini Claude verir,
her karar gerekcesiyle birlikte buraya yazilir. Amac stratejiyi gercek fiyatlarla
test etmek.

## Kurallar

| Kural | Deger |
|---|---|
| Baslangic sermayesi | 20.000 TL |
| Komisyon | islem basina %0.15 |
| BIST | tam lot zorunlu |
| ABD hisse/ETF, kripto, gram maden | kesirli serbest |
| Kaldirac / acik pozisyon | yok |
| Ek para girisi | yok - sadece baslangic sermayesi |
| Rebalancing esigi | hedeften **3 puan** sapma (agresif) |
| Kisma kurali | risk katkisi > **%20** VE beta > **1,50** |

Defter `islemler.yaml` append-only. Gecmis islem silinmez; hata varsa
ters islemle kapatilir.

## Calistirma

```
python scripts/yatirim/main.py --sim          # gunluk rapor
python scripts/yatirim/karar_takip.py         # karar sonuclarini olc
```

Cikti: `simulasyon/raporlar/YYYY-AA-GG.md`

## Karar sonuc takibi

Gerekce yazmak yetmez; gerekcenin **tutup tutmadigini olcmek** gerek.
Her karar `kararlar.yaml` icine olculebilir bir **beklenti** ile yazilir ve
**5/10/15/20/25/30.** gunlerde olculur.

Kural: **esik tetiklensin veya tetiklenmesin fiyat kaydedilir.** Eski Yildiz
Pazar botu vadesi dolan 377 sinyalin `outcome_price` alanini NULL biraktigi
icin verisinin %88'i olcum icin kullanilamaz hale gelmisti.

Sonuclar: [[00-karar-sonuclari]] · Ham olcum: `kararlar-olcum.yaml`

Olcum gecmis fiyat serisinden yapilir, "bugun" fiyatindan degil - sistem
birkac gun kapali kalsa bile kacan kontrol gunleri geriye donuk dolar.

---

## Karar gunlugu

### 2026-08-13 — Acilis tahsisi

**Kullanilan sermaye:** 16.883 TL alim + 25 TL komisyon. Nakit kalan 3.091 TL (%15,5).

| Sinif | Tutar | Agirlik | Ne alindi |
|---|---:|---:|---|
| BIST | 5.889 TL | 29,5% | ASELS 6, THYAO 7, GARAN 13 lot |
| Nasdaq | 4.997 TL | 25,0% | QQQ 0,1446 |
| Maden | 3.999 TL | 20,0% | Gram altin 0,583 |
| Kripto | 1.998 TL | 10,0% | BTC 0,00066 |
| Nakit | 3.091 TL | 15,5% | - |

**Neyi almadim ve neden:**

- **NVDA, AAPL** — ikisi de zaten QQQ icinde. Ustune tek tek almak cesitlendirme
  degil, ayni bahse ikinci kez girmek. QQQ-NVDA korelasyonu 0,68.
  20.000 TL'de tek sirket riski tasiyacak yer yok.
- **ETH** — BTC ile korelasyon 0,89. Ayni pozisyonun iki parcasi. Bolmek
  cesitlendirme uretmez, sadece ikinci komisyon uretir. Bkz. [[korelasyon]]
- **Gumus** — altinla 0,82 korele, volatilitesi altinin iki kati (%54,6 vs %23,6).
  20.000 TL'de acilabilecek pozisyon ~500 TL olurdu: ne koruma ne getiri,
  sadece kalabalik.

**Kucuk sermayenin zorladigi taviz:** BIST bacagi 3 hisseden ibaret cunku
izleme listesinde BIST endeks fonu yok (XU100.IS satin alinabilir bir arac degil).
Uc hisse, endeksin tasidigi sektor cesitliligini vermez - bu bilincli kabul
edilmis bir konsantrasyon riski. Cozum: izleme listesine bir BIST endeks fonu
eklemek.

**Ilk risk okumasi:**

| Varlik | Agirlik | Risk katkisi | Yorum |
|---|---:|---:|---|
| Altin | 20,0% | 23,2% | agirliginin biraz uzerinde |
| QQQ | 25,0% | 21,5% | agirliginin altinda - iyi |
| **Aselsan** | **10,7%** | **18,1%** | **paranin 1/10'u, riskin 1/5'i** |
| Bitcoin | 10,0% | 15,1% | beklenen, kripto boyle |
| THYAO | 10,5% | 11,4% | dengeli |
| Garanti | 8,2% | 10,7% | dengeli |

Portfoy volatilitesi **%12,4** — en dusuk volatiliteli tekil varliktan (QQQ %16,3)
bile dusuk. Cesitlendirme calisiyor demektir. Bkz. [[risk-butcesi]]

**Izlenecek:** ASELS'in volatilitesi %39,3 ve risk katkisi agirliginin
1,7 kati. Pozisyon buyutulmeyecek; risk katkisi %22'yi asarsa kisilacak.

### 2026-08-13 (2) — BIST bacagi takasi: GARAN -> TUPRS

Eski Yildiz Pazar botundan alinan 59 hisselik evren tarandi. Acilista
"3 hisse tahmini" olarak isaretledigim zayiflik giderildi.

**Islem:** GARAN 13 lot satildi (1.644 TL), TUPRS 5 lot alindi (1.682 TL).
Komisyon 5 TL. Gerceklesen: -2 TL.

**Gerekce — GARAN neden gitti:** THYAO ile korelasyonu 0,61. Ikisi ayni
bahsin iki kopyasi (TL faiz + ic talep dongusu). Portfoyde iki pozisyon
gorunuyordu, risk tarafinda tek pozisyondu.

**Gerekce — TUPRS neden geldi:** mevcut BIST hisselerine ortalama
korelasyon 0,17, evrendeki en dusugu. Rafineri marji + ihracat geliri,
banka ve havacilikla farkli sok kaynagi.

**Olculen sonuc:**

| Olcut | Once | Sonra |
|---|---:|---:|
| BIST bacagi volatilitesi | 29,2% | **26,9%** |
| Portfoy volatilitesi | 15,6% | **14,7%** |
| BIST bacaginin risk katkisi | 40,2% | 36,2% |

Dikkat: TUPRS'un **tek basina volatilitesi daha yuksek** (36,9% vs GARAN
37,1% — neredeyse esit), buna ragmen bacak volatilitesi dustu. Duseren sey
volatilite degil korelasyon. [[korelasyon]] ve [[risk-butcesi]] tam olarak
bunu anlatiyor.

**ASELS'i neden takas etmedim:** ASELS->TUPRS takasi bacak volatilitesini
daha da dusururdu (26,0%). Ama bu yalnizca ASELS'in yuksek volatilitesinden
kaynaklanir; ASELS diger BIST hisselerine 0,17-0,20 korele, yani asil
cesitlendirici o. Dusuk korelasyonlu varligi volatilite icin atmak yanlis islem.

**Durust uyari:** TUPRS'un 1 yillik getirisi +197%. Bunu momentum icin
almadim, korelasyon icin aldim. Boyle bir ralliden sonra girmek drawdown
riski tasir. Ayrica rafineri = regulasyon ve petrol fiyati maruziyeti.

**Ayni gun ikinci islem yapmanin gerekcesi:** kural "piyasa hareketi
tetiklemeden islem yok" diyor. Bu islemi tetikleyen piyasa degil, acilista
eksik olan bilginin tamamlanmasiydi. Bu istisna tekrarlanmamali.

### 2026-08-13 (3) — Gun sonu: ISLEM YOK

Portfoy **20.317 TL** (+%1,6). Hicbir tetikleyici calismadi:

| Sinif | Sapma | Esik |
|---|---:|---:|
| bist | +0,7 puan | 5 |
| maden | -0,5 puan | 5 |
| nasdaq | -0,1 puan | 5 |
| kripto | -0,1 puan | 5 |
| nakit | +0,0 puan | 5 |

**Izlemede:** ASELS risk katkisi %23,2, agirligi %11,6 — paranin sekizde biri,
riskin dortte biri. Bugun +%10 yaptigi icin agirligi buyudu. Kisma esigi %25;
henuz asilmadi, dokunulmadi.

**Neden gunluk islem yapmiyorum:** komisyon %0,15, gidis-donus %0,30.
20.000 TL'de her tur ~60 TL. Gunde bir tur = ayda ~1.200 TL = sermayenin %6'si.
Bu maliyeti asacak gunluk kenar iddiasi icin kanit yok; aksine eski Yildiz
Pazar botunun 427 sinyalinin %88'i TP/SL'e degmeden sondu.

Kurali sikisinca esnetmek, kurali hic koymamakla ayni sey.

### 2026-08-13 (4) — Esikler agresiflestirildi + ASELS kisildi

Simulasyon oldugu icin esikler siki tutuldu: rebalancing 5 -> **3 puan**,
risk katkisi tavani %25 -> **%20**. Esikler artik kodda sabit degil,
`varliklar.yaml` icindeki `esikler` blogunda.

**Yeni esikle uc varlik tetikledi ama ikisi YANLIS alarmdi:**

| Varlik | Katki | Agirlik | Beta | Karar |
|---|---:|---:|---:|---|
| ASELS | %23,2 | %11,6 | **2,00** | **kisildi** |
| Altin | %23,2 | %19,5 | 1,19 | dokunulmadi |
| QQQ | %20,6 | %24,9 | **0,83** | dokunulmadi |

QQQ tavani asiyordu ama parasindan **az** risk tasiyor - portfoydeki en verimli
tasiyici. Altinin katkisi agirligindan geliyor, betasindan degil; ustelik tek
cesitlendirici (herkese 0,15-0,26 korele), kismak volatiliteyi **artirirdi**.

**Kural duzeltildi.** Ham katki tek basina yanlis olcut: 6 pozisyonda ortalama
katki %16,7'dir, birilerinin %20'yi asmasi matematiksel zorunluluk. Ayrica
pozisyonu kucultmek katkiyi dusurur ama **betayi degistirmez** - beta varligin
ozelligidir. Yeni kural iki kosulu birden ister: `katki > %20` **ve** `beta > 1,50`.

**Islem:** ASELS 1 lot satildi (392,50 TL), geliriyle TUPRS 1 lot alindi (346,75 TL).
Komisyon 1,11 TL. Nakde park edilmedi - risk 2,00 betadan 0,79 betaya kaydirildi,
BIST agirligi korundu.

**Sonuc:**

| Olcut | Once | Sonra |
|---|---:|---:|
| ASELS risk katkisi | %23,2 | **%18,5** |
| Portfoy volatilitesi | %14,6 | **%14,3** |
| Tetikleyen pozisyon | 3 | **0** |

Not: ASELS bugun +%10,2 yaptigi icin agirligi buyudu. Kazanandan satmak
his olarak yanlis gelir - [[rebalancing]] tam olarak bunu anlatiyor.

---

## Sonraki karar icin tetikleyiciler

- Bir varlik sinifi hedeften **3 puan** saparsa -> rebalancing degerlendir
- Bir varligin katkisi **%20**'yi VE betasi **1,50**'yi birlikte asarsa -> kis
- Portfoy max drawdown -%20'yi asarsa -> dagilimi bastan gozden gecir
- Aksi halde islem yok. **Islem yapmamak da bir karardir.**

Esikler `varliklar.yaml` -> `esikler` blogunda. Gercek parayla calisirken
komisyon maliyeti nedeniyle gevsetilmeli (5 puan / %25).
