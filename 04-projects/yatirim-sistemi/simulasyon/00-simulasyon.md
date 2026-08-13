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
| Rebalancing esigi | hedeften 5 puan sapma |

Defter `islemler.yaml` append-only. Gecmis islem silinmez; hata varsa
ters islemle kapatilir.

## Calistirma

```
python scripts/yatirim/main.py --sim
```

Cikti: `simulasyon/raporlar/YYYY-AA-GG.md`

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

---

## Sonraki karar icin tetikleyiciler

- Bir varlik sinifi hedeften 5 puan saparsa -> rebalancing degerlendir
- Tek varligin risk katkisi %25'i asarsa -> pozisyonu kis
- Portfoy max drawdown -%20'yi asarsa -> dagilimi bastan gozden gecir
- Aksi halde islem yok. **Islem yapmamak da bir karardir.**
