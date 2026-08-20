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

## Gotchas (A - DEGISMEZ)

Birden fazla klasoru/araci birden baglayan kurallar. Klasore ozgu tuzaklar
ilgili alt klasorun `CLAUDE.md`'sindedir:

- `scripts/yatirim/CLAUDE.md` - fiyat, risk, maliyet modeli, sinyal, bot
- `scripts/vault/CLAUDE.md` - Web Clipper, frontmatter, vault denetimi
- `altyapi/telegram-webhook/CLAUDE.md` - Cloudflare Worker, kota, yetki
- `06-archive/gotcha-gecmisi.md` - duzeltilmis olay kayitlari (baglama girmez)

### Kimlik ve guvenlik

- **SIMULASYONDAYIZ**: gercek para yok. `portfoy.yaml` `sablon: true` -> gercek portfoy raporu
  uretilmez, script durur. Aktif olan tek sey `simulasyon/islemler.yaml` uzerinden calisan
  20.000 TL kagit portfoy. Rapor/Telegram ciktisini gercek portfoy gibi sunma.
- **vault = git repo, beyaz liste**: `.gitignore` once `/*` ile her seyi dislar, sonra yalnizca
  `scripts/`, `04-projects/yatirim-sistemi/`, `CLAUDE.md`, `README.md`, `.github/` eklenir. Yeni
  not klasoru varsayilan olarak GitHub'a GITMEZ. Kara listeye cevirme.
- **`.env` vault kokunde**, `.gitignore`'da. Token asla rapora/koda yazilmaz; Telegram hata
  mesajinda sadece API aciklamasi gosterilir.
- **`.env` yorum satiri tuzagi**: degerler `#` ile baslayan satira yazilirsa parser atlar ve
  "token yok" der. `notify.py` artik bu durumu ayirt eden hata mesaji veriyor. Sablonda ornek
  degeri yorum icinde `ANAHTAR : deger` diye gostermek bu hataya davet cikariyor - gosterme.
- **EVDS anahtari yoksa sistem CALISIR**: Yahoo'ya duser ve raporda bunu yazar. Anahtar `.env`
  -> `EVDS_API_ANAHTARI`, header ile gonderilir (URL'ye KOYMA - loglara ve hata mesajlarina
  sizar).
- **`TELEGRAM_IZINLI_CHAT_ID` bos = bot SUSAR**: "ayar yoksa herkese acik" degil. Ayrica
  anahtarin `notify.ORTAM_ANAHTARLARI` icinde olmasi SART - Actions'ta .env yok, secret ortamdan
  okunur; listede olmayan anahtar orada sessizce bos kalir ve bot hicbir mesaja cevap vermez.
- **chat id IKI yerde suzuluyor** (Worker + `tek_komutu_cevapla`): repo'ya yazma yetkisi olan
  biri Worker'i atlayip dogrudan `repository_dispatch` atabilir. Yetki kontrolu tek katmana
  birakilamaz.
- **yetki kontrolu WORKER'da, Actions'ta degil**: Telegram botlari herkese aciktir. Suzme
  Actions'ta kalsaydi her yabanci mesaj bir kosu baslatir ve 1 dakika kota yakardi - botun adini
  bilen biri kotayi tuketebilirdi. Actions tarafindaki kontrol (`tek_komutu_cevapla`) KALDI ama
  ikincil: repo'ya yazma yetkisi olan biri Worker'i atlayip dogrudan dispatch atabilir.
- **komut metni workflow'da `${{ }}` ile GOMULMEZ**: kullanici yazdigi metin dogrudan `run:`
  icine gomulseydi kabuk enjeksiyonu olurdu. Ortam degiskeni (`KOMUT`) uzerinden gecer, tirnak
  icinde okunur.

### Kod ve yapilandirma siniri

- **sembol / hedef / esik degisikligi YALNIZCA YAML'da**: `04-projects/yatirim-sistemi/*.yaml`
  icinde yapilir, kodda degil. Karar esikleri `varliklar.yaml -> esikler` altinda; kodda sabit
  tutma. Simulasyonda agresif (3 puan / %20), gercek parada gevsek (5 puan / %25) olmali -
  komisyon %0.15, gidis-donus %0.30.
- **simulasyon defteri append-only**: gecmis islem duzeltilmez, ters islemle kapatilir. Maliyet
  agirlikli ortalama.
- **`03-wiki` ciktidir, kaynak degil**: her wiki sayfasi `kaynak_zinciri` beyan etmeli. Kaynagi
  model bilgisiyse `kaynak_zinciri: ["model-bilgisi"]` yaz - sayfa yasak degil, beyansiz olmasi
  yasak. Beyansiz sayfa zamanla "vault boyle diyor" diye kendine atif yapilan iddiaya doner.

### Git ve GitHub Actions

- **calistirma GitHub Actions'ta**: repo `baduone03/yatirim-sistemi` (private), workflow hafta
  ici 16:00 UTC = 19:00 TR. Yerel Task Scheduler gorevi KALDIRILDI - ikisi ayni anda calisirsa
  Telegram'a gunde iki mesaj duser. `gunluk.ps1` yerel yedek olarak duruyor ama zamanlanmis
  degil.
- **Actions raporu repoya commit eder**: calismaya baslamadan ONCE `git pull` yap. Yoksa ayni
  tarihli rapor dosyasinda rebase catismasi cikar (hem Actions hem sen ayni dosyayi
  uretirsiniz). Cozum: rapor turetilmis veri, `git checkout --theirs` ile kendi surumunu al,
  sonra yeniden uret.
- **iki workflow ayni dizine commit ETMEZ**: `bot-sorgu.yml` yalnizca `bot_offset.txt` ekler.
  `git add 04-projects/yatirim-sistemi/` yazilsaydi bot kosusu rapor workflow'unun urettigi
  dosyalari da commit eder ve iki workflow surekli rebase catismasi yasardi.
- **`hata-durumu.yaml` COMMIT EDILMEK ZORUNDA** ve commit adimi `if: always()`: Actions temiz
  checkout aliyor, commit edilmezse her kosu "yeni hata" sanir. Basarisiz kosuda da yazilmali -
  hatanin oldugu kosu tam da kaydin guncellenmesi gereken kosudur.
- **histerezis latch'i DISKTE**: `sinyal-durumu.yaml` (+ `gonderilen.log`) makine uretimi KALICI
  DURUM, turetilmis veri degil. Actions `git add 04-projects/yatirim-sistemi/` ile commit eder;
  commit edilmezse her kosu latch'i kapali baslatir ve histerezis hicbir sey hatirlamaz. Yerel
  kosuyla Actions ayni dosyayi yazarsa catisma cikar - rapordan farkli olarak burada dogru surum
  **Actions'inki**.
- **`main.py` bilinen engelde `hata-kodu.txt` birakir**, workflow'un genel `failure()` adimi onu
  gorunce SUSAR. Yoksa ayni ariza icin iki mesaj gider ve - daha kotusu - iki farkli kod
  ("hurdle-bayat" / "rapor-basarisiz") her kosuda birbirini "yeni hata" yapip bastirmayi tumden
  etkisiz kilar.
- **tek workflow, gorevi script secer**: `piyasa.Takvim.gorev()` saate bakip TARAMA / GUN_SONU /
  BRIFING doner. Ayri workflow'lar her biri ayri checkout + pip install ederdi, Actions dakikasi
  ikiye katlanirdi. Seans saatleri `bildirim.yaml -> takvim` icinde, kodda DEGIL - BIST seans
  saatleri gecmiste degisti.
- **webhook aktifken `getUpdates` HTTP 409 doner**: Telegram ikisini ayni anda kullandirmaz. Bu
  yuzden webhook'a gecerken yoklama yolu fiilen kapandi ve `bot-sorgu.yml`den cron KALDIRILDI -
  zamanlanmis kosu bekleyen mesaji okuyamaz, sadece hata verip 1 dakika yakardi. Emniyet agi
  Telegram'in kendisinde: webhook 200 donmezse guncelleme kuyrukta kalir ve yeniden denenir.
  Geri donus tek satir: `deleteWebhook`.

### Butce ve zaman

- **Actions dakika butcesi**: private repo, GitHub Free = 2000 dk/ay, her kosu yukari
  yuvarlanir. 2 saatlik grid ~800 dk (%40), 1 saatlik ~1530 dk (%77), 30 dakikalik ~2980 dk
  (MUMKUN DEGIL). Sikligi artirmanin tek faydasi ilk hareketi ne kadar gec duydugundur - bekleme
  suresi zaten sembol basina gunde ~1 sinyalle siniriyor.
- **Actions kosusu ~35 SANIYE, faturasi 1 DAKIKA**: sure `gh run list --json
  createdAt,updatedAt` ile olculur. GitHub kosu basina yukari yuvarlar, yani 35 sn de 59 sn de 1
  dakikadir. Butceyi "kosu ~2 dk" diye tahmin etmek toplami iki katina cikarir - 2 saatlik grid
  %40 degil %20. Butce kararindan once OLC; tahmin, sirf sayi buyuk gorundugu icin gereksiz
  seyrekletme kararina goturur.
- **kosu suresi 60 saniyeyi asarsa fatura IKIYE katlanir**: 30 dakikalik grid bu yuzden riskli
  (%75 -> %149). Yeni bir ag cagrisi veya agir hesap eklerken kosu suresini yeniden olc; esik 60
  saniye.
- **cron dakikasi 0 DEGIL**: GitHub zamanlanmis kosulari best-effort calistirir ve saat basi
  kuyrugun en kalabalik ani. `0 */2` 10-40 dakika gecikebilir, `7 */2` gecikmez. Gun sonu croni
  (`30 20`) istisna: `gorev()` esigi tam 23:30 TR, kaydirilirsa gun sonu ozeti taramaya duser.
- **UTC zorunlu**: `sinyal.simdi_utc()` disinda `datetime.now()` kullanma. Actions UTC'de, yerel
  kosu TR saatinde calisir; naive damgalarla gecen sure NEGATIF cikar ve bekleme suresi anlamini
  yitirir. Tarih (`gun`, `ozet:{tarih}`) ise rapor adiyla AYNI olmali - o yerel `date.today()`.
- **"gun" TR gunudur, UTC gunu DEGIL**: `rapor_adi = (simdi_utc() + TR_OFSET).date()`.
  `date.today()` kullanilsaydi Actions (UTC) ile yerel makine (TR) ayni gun icin iki farkli isim
  uretir, TR 00:00-03:00 arasi kosular bir onceki gunun rapor dosyasina yazar ve gunluk sinyal
  sayaci TR 03:00'te sifirlanirdi. Rapor adi, `gunsonu:` anahtari, devre kesici sayaci ve nakit
  faizi hepsi ayni TR gununu kullanir.

### Calistirma

- **testler, UC ayri paket**: `python -m unittest discover -s scripts/yatirim -p "test_*.py"`,
  `python -m unittest discover -s scripts/vault -p "test_*.py"` ve Worker icin `node --test
  altyapi/telegram-webhook/worker.test.js`. pytest YOK, stdlib unittest; Worker tarafinda
  bagimlilik YOK, `npm install` gerekmiyor. Tamami cevrimdisi/sentetik - Yahoo'ya gitmez, piyasa
  saatinden bagimsiz. `discover` yalnizca verilen dizine bakar; bir paketi kosmak digerini
  kosmaz. `node --test`e dizin degil DOSYA yolu ver - dizin bicimi bu Node surumunde modul
  cozumleme hatasi veriyor. Test sayisi buraya yazilmaz - bayatliyor.
- **`gh secret set` PowerShell pipe ile BOZULUR**: `$deger | gh secret set AD` satir sonu
  ekleyip token'i gecersiz kilar (Telegram HTTP 404 verir). Daima `--body $deger` kullan.

## CLAUDE.md Bakimi

Bu dosya her oturumda otomatik yuklenir; alt klasorlerdeki `CLAUDE.md` ise
yalnizca o klasordeki dosyalara dokunuldugunda yuklenir. Kural bu ayrimi korumak
icindir.

- **Her `CLAUDE.md` en fazla 4k token** (~16 KB). Asan dosyada madde ya teste
  cevrilir ya arsive iner. Sinir asilmissa yeni madde EKLENMEZ, once yer acilir.
- **Kok dosyada yalnizca A kategorisi durur.** Alt klasor dosyalarinda A
  kategorisi madde OLAMAZ; bir madde A'ya terfi ediyorsa koke tasinir.
- **Kategori testi**: "Bu kurali cignemek bu klasorun DISINDA bir seyi bozar mi?"
  Evet -> A (kok). Hayir -> B (alt klasor). Duzeltilmis, tekrarlanamaz olay
  kaydi -> C (`06-archive/gotcha-gecmisi.md`).
  Emin olamadigin maddeyi A'ya koy - yanlis yere inen bir kural, gereksiz yere
  kokte duran kuraldan daha tehlikelidir.
- **Yeni gotcha eklerken kategori ve tarih yazilir**: `- **etiket** (A,
  2026-08-20): ...`
- **Testi yazilan madde tek satira iner** ve test adini tasir. Ornek:
  `- **simulasyon defteri append-only** (A, 2026-08-20). Bkz. LedgerTesti.`
- **`/audit` her `CLAUDE.md` boyutunu olcer**, 4k token'i asani ve alt
  klasorde duran A maddesini uyari olarak basar.

## memory.md Kullanimi
- Oturumlar arasi bilgileri memory.md'ye yaz.
- Format: Tarih + kisa madde.
