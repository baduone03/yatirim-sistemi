# Ikinci Beyin Kurallari

## Vault Sahibi
- Ad: Dodo
- Ilgi alanlari: Dijital girisimler, sistem kurma, otomasyon, kripto, blockchain, yapay zeka, dijital gelir modelleri
- Baglam: Teknoloji ve AI ile dijitalden para kazanmaya calisan genc girisimci. Vibecoder.
- Dil: Turkce yaz. Terim adlari (blockchain, DeFi, API, prompt, smart contract vb.) Ingilizce kalabilir ama teknik kavramlari ve surecleri Turkce acikla. "Liquidity pool'a stake et" degil, "Likidite havuzuna tokenlarini kilitleyerek faiz kazanirsin (buna staking deniyor)" yaz. Ilk gectigi yerde her terimi bir cumleyle acikla, sonraki kullanimlarda aciklama gerekmez.

## Vault Yapisi
- 01-inbox/: Ham, islenmemis girdiler. Her zaman buradan basla.
- 02-sources/: Islenmis kaynak materyaller.
- 03-wiki/: Sentetik bilgi - kavramlar, kisiler, konular.
  - concepts/: Kavram sayfalari (or: smart-contract.md, defi.md)
  - people/: Kisi sayfalari (or: vitalik-buterin.md)
  - topics/: Konu sayfalari (or: pasif-gelir-modelleri.md)
- 04-projects/: Aktif projeler.
- 05-daily/: Gunluk notlar.
- 06-archive/: Tamamlanmis materyaller.

## YAML Frontmatter Sablonu
Her notun basinda bu olmali:
```yaml
---
title: "Not Basligi"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
tags: []
status: inbox | processed | evergreen | needs-review
related: []
source: ""
money_angle: ""
---
```

## Not Yazma Kurallari
1. Atomik not: Bir dosya = bir fikir. "Blockchain ve Yapay Zeka" diye tek not yazma, ikisini ayir.
2. Baslik = icerigin ozeti. "Notlar" veya "Arastirma" gibi belirsiz isimler yasak.
3. Ilk paragraf = notun ana iddiasi. Okuyucu ilk 2 cumlede ne hakkinda oldugunu anlamali.
4. Somut ol. "Ilginc bir proje" degil, "Kullanicilarin AI ile otomatik NFT uretmesini saglayan proje, aylik 50K kullanici, ucretsiz katmani var" yaz.
5. Kaynak varsa mutlaka URL ekle.

## Baglanti Kurallari
- Wiki baglantisini yalnizca gercek iliski varsa kur.
- Zayif baglanti YASAK: "ikisi de teknoloji" yeterli degil.
- Guclu baglanti ornekleri:
  - Neden-sonuc: `[[DeFi]] protokolleri [[akilli sozlesme]] uzerine insa edilir`
  - Karsitlik: `[[CEX]] merkeziyetci, [[DEX]] merkeziyetsiz`
  - Bagimlilik: `[[yield-farming]] yapmak icin [[likidite havuzu]] anlamak sart`
- Bir kavram 2+ farkli DIS kaynakta gecmedikce bagimsiz wiki sayfasi olusturma.
  Ayni kaynagin iki yerde tekrarlanmasi iki kaynak sayilmaz.
- Bu dosyadaki ornek baglantilar backtick icinde yazilir. Ciplak yazilirsa
  Obsidian'da tiklanabilir olur ve tiklanan her ornek kok dizine bos bir not
  yaratir (`DEX.md` boyle olustu).

## Isleme Hatti (Ingest)
01-inbox/ icindeki status: inbox dosyalarini su sirayla isle:
1. Dosyayi oku, ana fikri tek cumlede belirle.
2. Anahtar kavramlari cikar (maksimum 5).
3. 02-sources/ altina yapilandirilmis ozet yaz:
   - Baslik
   - Tek cumle ozet
   - Ana noktalar (en fazla 5 madde)
   - Kaynak URL
   - money_angle degerlendirmesi
4. Ilgili wiki sayfalarini kontrol et:
   - Sayfa varsa: yeni bilgiyi ekle, celiski varsa belirt.
   - Sayfa yoksa ve kavram 2+ kaynakta geciyorsa: yeni sayfa olustur.
5. Baglantilari kur.
6. Orijinal dosyanin status'unu "processed" yap ve dosyayi 06-archive/ altina
   tasi. 01-inbox/ yalnizca bekleyen isi gosterir; islenmis girdi orada
   kalirsa klasor anlamini yitirir. Wikilink'ler dosya adiyla cozuldugu icin
   tasima baglantilari bozmaz.
7. memory.md'ye tek satir ozet ekle.

Kaynak olmayan girdi 02-sources/ altina KONMAZ. Kendi tasarim notun, sartname
veya retrospektif ise yeri 04-projects/. Sebep: 02-sources dis kanit
klasorudur; kendi ciktini oraya koyup sonra ona atif yapmak yanki odasi
yaratir.

## Para Acisi (Money Angle)
Her kaynagi islerken su kategorileri tara:

### Dogrudan Gelir
- Bu bilgiyle bir dijital urun satilabilir mi? (E-kitap, sablon, kurs, preset, prompt paketi)
- SaaS veya mikro-servis kurulabilir mi? (API, bot, otomasyon araci)
- Freelance hizmet olarak sunulabilir mi? (Danismanlik, kurulum, yonetim)

### Otomasyon Firsati
- Manuel yapilan bir isi otomatiklestirebilir miyiz? (AI ile, script ile, no-code ile)
- Baskalarinin bu otomasyona ihtiyaci var mi?
- Ucretsiz araclarla (n8n, Make, Zapier free tier) kurulabilir mi?

### Arbitraj
- Bir yerde ucretsiz/ucuz olan bilgi veya hizmet, baska bir yerde degerli mi?
- Dil arbitraji: Ingilizce icerigi Turkce pazara tasimak mumkun mu?
- Platform arbitraji: Bir platformdaki icerik/hizmet baska platformda eksik mi?

### Kripto ve DeFi
- Airdrop firsati var mi? (Yeni proje, testnet, erken kullanici avantaji)
- Yield/getiri firsati var mi? (Staking, likidite saglama, lending)
- Yeni bir protokol veya zincir mi? Erken girmenin avantaji ne?

### Icerik ve Topluluk
- Bu konuda icerik uretilebilir mi? (YouTube, blog, Twitter thread, newsletter)
- Affiliate/referans programi var mi?
- Topluluk kurulabilir mi? (Discord, Telegram grubu)

### Degerlendirme Kurallari
- Cevap varsa money_angle alanina kategori + tek cumle yaz. Ornek: "Otomasyon: Bu API'yi kullanarak otomatik fiyat karsilastirma botu kurulabilir, ucretsiz tier yeterli."
- Zorla firsat uydurma. Her notta para acisi olmak zorunda degil.
- Gercekci ol. "Milyonluk firsat" degil, "ayda 500TL getirebilecek yan gelir" gibi somut tahminler yap.

## Bilgi Guncelleme
- Yeni kaynak mevcut wiki sayfasiyla celisiyorsa:
  1. Celiskiyi acikca belirt.
  2. Tarih ve guvenilirlik karsilastir.
  3. Sayfayi guncelle, eski bilgiyi "Tarihsel not:" altinda koru.
- 6 aydan eski guncellenmeyen notlara needs-review etiketi ekle.

## Davranis Kurallari
- Proaktif ol: Bir firsat, kisayol veya ucretsiz alternatif gordugunde beklemeden soyle.
- "Burada soyle bir sey var" formatiyla tuyo ver.
- Teoriyi 2-3 cumleyle gec, uygulamayi detaylandir.
- Maliyet-sifir cozumleri her zaman once oner.
- Karsilastirmali sun: "X var ama Y de var, farki su" formatinda.
- Belirsiz sifatlar kullanma: "ilginc", "guzel", "faydali" yasak. Neyin ilginc oldugunu somutla.
- Gereksiz tekrar yapma. Ama Dodo'nun soylediginde yanlislik, risk veya eksiklik varsa duzeltmeye devam et — "bunu zaten soyledim" deyip susma, dogruyu kabul edene kadar acikla.

## Token Optimizasyonu
Bu vault'ta her token para. Ciktilari su kurallara gore uret:

### Yapma
- Ayni seyi farkli kelimelerle tekrar soyleme.
- "Simdi sunu yapacagim", "Ilk olarak", "Son olarak" gibi adim anlatma cumleleri yazma — direkt yap.
- Yaptigin isi ozetleme. Sadece beklenmedik bir sey olduysa soyle.
- Giris ve kapanis cumleleri ekleme. "Tabii ki!", "Iste sonuc:", "Umarim faydali olmustur" yasak.
- Bos satir, dekoratif ayrac (---), gereksiz baslik hiyerarsisi kullanma.
- Bir dosyayi okuduktan sonra icerigini bana geri anlatma — ben zaten vault'un sahibiyim.

### Yap
- Tek cumleyle cevaplanacak soruya tek cumle yaz.
- Not olustururken: baslik + 1 paragraf ozet + maddeler. Uzun nesir yazma.
- Wiki sayfasi guncellerken: yalnizca yeni bilgiyi ekle, mevcut icerigi tekrar yazma.
- Birden fazla dosya islerken: her dosya icin ayri ayri rapor verme, toplu ozet ver.
- Hata yoksa "basarili" deme, sessizce devam et.
- Maksimum cikti uzunlugu: Tek not ozeti <= 150 kelime. Wiki sayfasi <= 300 kelime. Gunluk brifing <= 200 kelime. Reflect analizi <= 400 kelime.

### Toplu Islem Kurali
5+ dosya islerken:
1. Once tum dosyalari sessizce oku.
2. Sonra toplu isle.
3. En sonda tek bir ozet ver: "X dosya islendi. Y yeni wiki sayfasi olusturuldu. Z baglanti kuruldu."

## Ton
- Kisa, oz, somut.
- Turkce, teknik terimler Ingilizce.
- Gereksiz kibar cumleler yok. Direkt ise gir.

---

## Gotchas
- **yatirim carpani**: `carpan` (ons->gram) YALNIZCA `fetch.py:_tl_bazina_cevir` icinde uygulanir. `portfolio.py` fiyatlari zaten cevrilmis alir - orada tekrar carparsan deger 31 kat kucuk cikar.
- **TL cevrimi**: fiyat gecmisi indirilirken `USDTRY=X` de cekilir; kur verisi gelmezse script hata verir, sessizce USD birakmaz.
- **BIST sembolleri**: Yahoo'da `.IS` soneki gerekir (`THYAO.IS`). Veri boslugu olabilir, rapor "Veri uyarilari" bolumunde isaretler.
- **yatirim ayari**: sembol/hedef degisikligi sadece `04-projects/yatirim-sistemi/*.yaml` icinde yapilir, kodda degil.
- **iki farkli maliyet tabani**: `portfoy.yaml` maliyeti varligin KENDI para biriminde tutar (guncel kurla cevrilir). `simulasyon/islemler.yaml` ise islem anindaki TL fiyatini tutar (cevrim yok). Bu yuzden iki ayri fonksiyon var: `portfoyu_hesapla` ve `portfoyu_ledgerdan_hesapla`. Karistirma.
- **simulasyon defteri append-only**: gecmis islem duzeltilmez, ters islemle kapatilir. Maliyet agirlikli ortalama.
- **Telegram**: `python-telegram-bot` KULLANILMIYOR - `requests` ile dogrudan Bot API. Async yok, MarkdownV2 kacisi yok, `Bot.close()` tuzagi yok. HTML parse modunda yalnizca `& < >` kacirilir.
- **`.env` yorum satiri tuzagi**: degerler `#` ile baslayan satira yazilirsa parser atlar ve "token yok" der. `notify.py` artik bu durumu ayirt eden hata mesaji veriyor. Sablonda ornek degeri yorum icinde `ANAHTAR : deger` diye gostermek bu hataya davet cikariyor - gosterme.
- **`.env` vault kokunde**, `.gitignore`'da. Token asla rapora/koda yazilmaz; Telegram hata mesajinda sadece API aciklamasi gosterilir.
- **BIST evreni ana rapora girmez**: 59 hisse `izleme: true` yapilirsa korelasyon matrisi 59x59 olur, rapor okunmaz. `bist-evreni.yaml` yalnizca `tarama.py` icindir.
- **Yahoo'da delist BIST tickerlari**: ISATR, KOZAL, SODA, KOZAA, SELGD - evrenden cikarildi. Yeni delist cikarsa tarama uyari basar, calismaya devam eder.
- **SIMULASYONDAYIZ**: gercek para yok. `portfoy.yaml` `sablon: true` -> gercek portfoy raporu uretilmez, script durur. Aktif olan tek sey `simulasyon/islemler.yaml` uzerinden calisan 20.000 TL kagit portfoy. Rapor/Telegram ciktisini gercek portfoy gibi sunma.
- **testler, iki ayri paket**: `python -m unittest discover -s scripts/yatirim -p "test_*.py"` ve `python -m unittest discover -s scripts/vault -p "test_*.py"`. pytest YOK, stdlib unittest. Tamami cevrimdisi/sentetik - Yahoo'ya gitmez, piyasa saatinden bagimsiz. `discover` yalnizca verilen dizine bakar; yatirim testlerini calistirmak vault testlerini calistirmaz. Test sayisi buraya yazilmaz - bayatliyor.
- **Web Clipper `status` alani yazmaz**: kupurler vault sablonunu degil clipper'in kendi sablonunu kullanir. Hedef klasor uzanti ayarindadir, `status` alanini ise hicbir ayar yazdirmaz. Iki savunma var: `girdileri_topla.py` kupuru `01-inbox`'a tasir ve `status: inbox` damgalar; `gozden_gecir.py` girdi klasorlerinde (`01-inbox`, `Clippings`) `status` alani HIC olmayan notu bekleyen sayar. Klasor ayari duzelse bile damgalama gerekli kalir.
- **haftalik.ps1 sirasi**: once `girdileri_topla.py`, sonra `gozden_gecir.py --telegram`. Ters cevirme - denetim Telegram'a ozet gonderiyor, once normalize edilmezse zaten kendiliginden duzelecek bir durumu bildirir.
- **mevcut `status` degeri asla ezilmez**: `girdileri_topla.py` alani yalnizca HIC yoksa ekler. Aksi halde her calisma islenmis notlari yeniden inbox'a acar.
- **BOM bosluk sayilmaz**: `metin.lstrip().startswith("---")` UTF-8-BOM ile yazilmis dosyada FALSE doner (PowerShell `Set-Content -Encoding utf8` BOM yazar). Frontmatter kontrolu icin daima `_frontmatter_blok()` kullan, elle string kontrolu yazma.
- **`03-wiki` ciktidir, kaynak degil**: her wiki sayfasi `kaynak_zinciri` beyan etmeli. Kaynagi model bilgisiyse `kaynak_zinciri: ["model-bilgisi"]` yaz - sayfa yasak degil, beyansiz olmasi yasak. Beyansiz sayfa zamanla "vault boyle diyor" diye kendine atif yapilan iddiaya doner.
- **frontmatter alani govdede aranmaz**: `_frontmatter_alani` yalnizca `--- ... ---` blogunu tarar. Tum metni tarasaydi boru hattini anlatan bir not govdesindeki ornek `status: inbox` satiri o notu islenmemis girdi yapardi.
- **calistirma GitHub Actions'ta**: repo `baduone03/yatirim-sistemi` (private), workflow hafta ici 16:00 UTC = 19:00 TR. Yerel Task Scheduler gorevi KALDIRILDI - ikisi ayni anda calisirsa Telegram'a gunde iki mesaj duser. `gunluk.ps1` yerel yedek olarak duruyor ama zamanlanmis degil.
- **`gh secret set` PowerShell pipe ile BOZULUR**: `$deger | gh secret set AD` satir sonu ekleyip token'i gecersiz kilar (Telegram HTTP 404 verir). Daima `--body $deger` kullan.
- **vault = git repo, beyaz liste**: `.gitignore` once `/*` ile her seyi dislar, sonra yalnizca `scripts/`, `04-projects/yatirim-sistemi/`, `CLAUDE.md`, `README.md`, `.github/` eklenir. Yeni not klasoru varsayilan olarak GitHub'a GITMEZ. Kara listeye cevirme.
- **Actions raporu repoya commit eder**: calismaya baslamadan ONCE `git pull` yap. Yoksa ayni tarihli rapor dosyasinda rebase catismasi cikar (hem Actions hem sen ayni dosyayi uretirsiniz). Cozum: rapor turetilmis veri, `git checkout --theirs` ile kendi surumunu al, sonra yeniden uret.
- **kisma kurali = katki VE beta**: ham risk katkisi TEK BASINA yanlis olcut. 6 pozisyonda ortalama katki %16.7'dir, birilerinin tavani asmasi zorunludur; ayrica pozisyonu kucultmek katkiyi dusurur ama BETAYI DEGISTIRMEZ (beta varligin ozelligi). Yalniz katkiya bakan kural, parasindan az risk tasiyan verimli varliklari (QQQ beta 0.83) sattirir. `Esikler.kisilmali()` iki kosulu birden arar.
- **karar esikleri YAML'da**: `varliklar.yaml` -> `esikler`. Kodda sabit tutma. Simulasyonda agresif (3 puan / %20), gercek parada gevsek (5 puan / %25) olmali - komisyon %0.15, gidis-donus %0.30.
- **karisik takvim / volatilite tuzagi (ONEMLI)**: BIST hafta sonu kapali, kripto acik. `ffill().pct_change()` kapali gunleri sifir getiri yapar -> volatilite %20-25 DUSUK cikar. `ffill` olmadan `pct_change()` ise NaN'den sonraki gunu de siler -> her Pazartesi BIST getirisi kaybolur, veri %30 azalir. Dogru yol `risk.ortak_getiriler()`: once tum varliklarin islem gordugu ortak takvime `reindex`, sonra `pct_change`. Yeni getiri hesabi yazarken bu fonksiyonu kullan.
- **yillicklastirma carpani sabit degil**: `risk.yillik_periyot_sayisi()` carpani gozlem yogunlugundan turetir (~241), `islem_gunu_yil: 252` yalnizca fallback. Ortak takvim kesisim oldugu icin 252 varsaymak volatiliteyi ~%3 sisirir.
- **bayat fiyat**: `son_fiyatlar` ffill yapar, delist/veri kesintisi sessizce eski fiyatla degerleme yapardi. `FiyatVerisi.bayat_semboller()` 7 gunden eski veriyi raporda ve Telegram'da isaretler. Degerlemeyi bozmaz, yalnizca gorunur kilar.
- **kurumsal olay maliyet kurali (EN KRITIK)**: bedelsiz/split'te `adet *= oran` ama **TOPLAM MALIYET DEGISMEZ**. Cebinden para cikmadi. Toplam maliyeti orana BOLMEK, olmayan kar uydurur: 1000 TL'lik 10 lot, 2.0 bedelsizden sonra 20 lottur ve maliyeti hala 1000 TL'dir; 500'e dusurursen %100 sahte kar cikar. Birim maliyet `toplam/adet`ten turetilir ve zaten dogru sekilde yariya iner.
- **kurumsal olay zaman cizgisi**: olaylar islemlerle TARIH SIRASINDA harmanlanir (`ledger._zaman_cizgisi`), topluca uygulanmaz. Toplu carpim, olaydan SONRA alinan lotlari da carpar - 4:1 split'ten sonra alinan 10 lot 40 gorunur. Ayni tarihte olay islemden ONCE gelir (ex-tarih mantigi).
- **kurumsal olay ledger'a yazilmaz**: `islemler.yaml` yalnizca SENIN islemlerini tutar, append-only. Bedelsiz sirketin isidir, nakit akisi yoktur. Ayri defter: `simulasyon/kurumsal-olaylar.yaml`.
- **bayatlik = kacirilan ISLEM GUNU, takvim gunu DEGIL**: BIST Cuma'dan Pazartesi'ye 3 takvim gunu gecirir, 1 islem gunu. Sartnamedeki "bist: 1 gun" takvim gunu olarak kodlansaydi her Pazartesi tum BIST hisseleri bayat cikardi. `FiyatVerisi._sinif_takvimi()` referans takvimi sinifin kendi verisinden turetir. Esigi 1'in ALTINDA olan siniflar (kripto) surekli piyasadir, onlarda referans tum takvimdir.
- **gunluk barda dakika esigi yok**: fiyat verisi `interval="1d"`. "kripto 15 dakika" gunluk barda tek bir seye karsilik gelir: esik 0 = en son barda veri olmali. Intraday veriye gecilmeden dakika/saat esigi anlamsizdir.
- **hacim dogrulanamazsa sembol supheli KALIR**: `_hacim_dogruluyor` hacim verisi yoksa False doner. Bilincli: dogrulanamayan sicramayi "gercek" saymak yanlis degeri dogruymus gibi raporlamaktir.
- **`kapanislari_indir` artik `(kapanis, hacim)` tuple doner**: hacim kurumsal olay tespiti icin sart. Tek deger bekleyen cagri sessizce DataFrame yerine tuple alir.
- **yfinance toplu indirmede gecici rate limit**: 13 sembolun HEPSI birden "possibly delisted" derse bu delist degil, rate limit. Kod "ag baglantisini kontrol et" der ama tek sembol ayri denendiginde calisiyorsa sebep budur; birkac dakika bekle. `period='365d'` gecerlidir, sorun o degil.
- **BTCTurk gecmis VERMEZ**: `/api/v2/ticker` anlik kotasyondur. Bu yuzden yalnizca DEGERLEME fiyatini ezer; volatilite, korelasyon ve beta hala Yahoo'nun 365 gunluk serisinden gelir. Yani kriptonun degeri BTCTurk'ten, getirisi Yahoo'dan. Rapor bunu yaziyor - kaldirma.
- **BTCTurk `timestamp` MILISANIYE**: saniye sanip cevirirsen tarih 1970 cikar ve her fiyat bayat sayilir, kripto degerlemesi sessizce Yahoo'ya doner.
- **TL ciftini dogrudan al**: BTCTRY yerine BTC/USD x USD/TRY carpimi kullanmak cift cevrim hatasidir. Ustelik TR primini o carpimla olcersen prim daima 0 cikar - kendi kendini dogrulayan hesap.
- **CoinGecko degerlemeye ASLA girmez**: rolu yalnizca ucgenleme referansi. Girseydi kripto fiyati bazen BTCTurk bazen CoinGecko olur, portfoy degeri kaynaga gore ziplardi.
- **TCMB yalnizca IS GUNU kur yayimlar** (~15:30). Hafta sonu/tatilde yeni kur yok. Bayat TCMB kuruyla ucgenleme yapmak "TR primi" adi altinda kurun bayatligini olcer - kripto 7/24 hareket ederken kur donmus kalir. `bayatlik_gun` asilirsa Yahoo'ya duser ve raporda `yahoo (tcmb bayat)` yazar.
- **OLCULEMEDI != DURDUR**: OLCULEMEDI kaynaklardan biri yok/bayat demek - bizim korlugumuz, rapor URETILIR. DURDUR uc kaynak da tazeyken gercek kopukluk demek - rapor URETILMEZ. Ayrimi kaldirirsan CoinGecko'nun bir dakikalik hikkirigi BIST ve altin dahil tum gunun raporunu sildirir.
- **`kaynaklar.py` ag katmani enjekte edilir**: her fonksiyon `getir=http_json` parametresi alir. Testler sahte `getir` gecirir, ag'a cikilmaz. Yeni kaynak eklerken bu kalibi bozma - yoksa test paketi ag'a bagimli hale gelir.
- **EVDS anahtari yoksa sistem CALISIR**: Yahoo'ya duser ve raporda bunu yazar. Anahtar `.env` -> `EVDS_API_ANAHTARI`, header ile gonderilir (URL'ye KOYMA - loglara ve hata mesajlarina sizar).
- **sqlite3 cursor tuzagi**: dis dongude `cur.execute(...)` uzerinde iterasyon yaparken ic ice ayni cursor'a `execute` cagirmak dis iterasyonu sessizce keser. Ayri cursor kullan veya once `.fetchall()`.

## memory.md Kullanimi
- Oturumlar arasi bilgileri memory.md'ye yaz.
- Format: Tarih + kisa madde.