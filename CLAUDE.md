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
- **supheli sembol RISK hesabina da girmez**: kurumsal olay suphesi hem
  degerlemeyi durdurur hem sembolu getiri matrisinden cikarir
  (`risk._risk_gecmisi`). Fiyata guvenmeyip o fiyattan turetilen volatiliteye
  guvenmek tutarsiz. Tum semboller supheliyse risk hesabi sebebini yazan
  hatayla durur, bos matrisle devam etmez.
- **`risk_modu: disla | duzelt`** (`varliklar.yaml -> kurumsal_olay`): `disla`
  varsayilan. `duzelt` defterdeki TUM olaylari geri-duzeltme olarak uygular
  (`_seriyi_duzelt`: ex-tarihten ONCEKI fiyatlar orana BOLUNUR), sonra hala
  supheli olani dislar. Supheli sembol tam da olay defterde OLMADIGI icin
  supheli sayilir, yani ona uygulanacak oran yoktur - `duzelt` modunun asil
  isi, deftere YAZILMIS olayin seride biraktigi sicramayi temizlemek.
- **fiyat serisi duzeltmesi ile adet/maliyet muhasebesi AYRI**: `ledger`
  tarafinda toplam maliyet DEGISMEZ; `risk._seriyi_duzelt` ise olcek birligi
  icin fiyati boler. Ikisini ayni kural sanip maliyeti de bolmek sahte kar
  uydurur.
- **gozlem dususu GUN degil HUCRE sayar**: ortak takvim bir KESISIM oldugu
  icin sembol cikarmak gun sayisini dusurmez, ARTIRIR. Kaybedilen sey kapsam;
  olcu gun x sembol (`risk._gozlem_dususu`). Esik `kurumsal_olay.gozlem_dusus_esigi`.
- **tahmin `null` DEGILDIR**: `null` "hicbir sey soyleyemem" demek ve sinyali
  tamamen kapatir; uc senaryolu `tahmin` blogu "olcmedim ama sinirlarini
  biliyorum" demek. Blokta `tahmin: true` ZORUNLU - olmadan sozluk reddedilir,
  yoksa yanlislikla yazilmis bir blok olculmus sayi gibi davranirdi.
- **dayaniklilik != islem yap**: karar uc senaryoda da AYNI cikabilir ama o
  ortak karar "maliyet sapmayi yutuyor" olabilir. `VarlikDuyarliligi.dayanikli`
  kararin GUVENILIR oldugunu, `sinyal_acik` YAPILMASI gerektigini soyler.
  Yalnizca dayanikliliga bakan kapi, maliyeti kesinlikle sapmadan buyuk olan
  varlikta islem onerir.
- **duyarlilik karar olcutu**: gidis-donus maliyeti < `esikler.rebalancing_sapma`.
  Ikisi de portfoy orani cinsinden, dogrudan karsilastirilabilir. Maliyet
  sinirin ustundeyse islem duzelttigi sapmadan fazlasini goturur.
- **sabit komisyon kucuk pozisyonu bogar**: 2 x 1.5 USD x 41 TL / 3.000 TL =
  %4.1. ABD varliklari referans pozisyonda esigi ASAR ve "maliyet yutuyor"
  cikar; 12.000 TL'de `kur_spread_tek_yon` belirleyici parametre olur. Yani
  duyarlilik sonucu POZISYON BUYUKLUGUNE bagli - `maliyet.duyarlilik.
  referans_pozisyon_try` degistirilirse sonuc degisir.
- **ham `Tahmin` ARITMETIGE GIRMEZ**: `Tahmin > 0` ve `Tahmin * float`
  TypeError verir. `eksik_kalemler` icin `_pozitif_olabilir` (KOTUMSER
  senaryoya bakar - iyimserde 0 olan verim kotumserde varsa stopaj sorusu
  DUSMEZ), aritmetik icin `senaryoyla(TEMEL)`. Bu kural bir kez ihlal edildi
  ve gercek yapilandirmayla main.py coktu; `GercekYapilandirmaTesti` bunun
  icin var - sentetik sozlukler gercek YAML'daki girinti hatasini yakalamaz.
- **rapor kalemi tahmine dayaniyorsa ISARETLENIR**: `maliyet_kalemleri`
  `[TAHMIN: temel senaryo]` notu ekler. Olculmus gibi gorunen bir tahmin,
  modelin kapatmaya calistigi hatanin ta kendisi.
- **`maliyet.sembol_spreadi` profili EZER**: tek global spread, likiditesi
  cok farkli hisseleri ayni kefeye koyar (BIST30 dar, kucuk hisse genis) ve
  buyuklerde maliyeti abartip gereksiz "ekonomik degil" karari uretir.
  Listede olmayan sembol profilin varsayilanini alir; tanimsiz sembol
  `config` dogrulamasinda patlar.
- **referans pozisyon SABIT DEGIL, portfoyden turetilir**
  (`duyarlilik.referans_pozisyonlar`): tutulan varlikta gercek deger,
  tutulmayanda hedef dagilimda alacagi deger (sinif hedefi / o siniftaki
  sembol sayisi), portfoy bossa YAML yedegi. Sabit referans varsaymak sonucu
  OLCMEK yerine SECMEK olur - ayni varlik 1.700 TL'de "pozisyon cok kucuk",
  12.000 TL'de "su parametreyi olc" cikiyor.
- **"ekonomik degil" ile "parametre belirsizligi" AYRI bolumler**: ilkinde
  eksik olan PARA, ikincisinde bir SAYI. Cozumleri de farkli - biri buyutulur
  veya varliktan cikilir, digeri olculur. Ayni listede gosterilirse cozumu
  para olan sorun "sonra olcerim" kutusunda kalir.
- **minimum ekonomik pozisyon**: `2*komisyon_usd*usdtry / (esik - taban)`.
  `taban` = pozisyondan BAGIMSIZ kisim (oransal komisyon + 2*kur spread +
  kambiyo vergisi + 2*menkul spread). Taban esigi asiyorsa `math.inf` doner -
  hicbir buyukluk yetmez, o varliktan cikmaktan baska secenek yok.
- **duyarlilik IKI BOYUTLU**: (1) islem maliyeti - `gidis_donus` sapma
  esigini asiyor mu; (2) tasima - beyan edilen beklenti GEREKEN getiriyi
  karsiliyor mu. Ikisi de gecmeden sinyal acilmaz.
- **sistem beklenen getiri URETMEZ, GEREKENI hesaplar**:
  `gereken = tl_risksiz + yillik_tasima + gidis_donus / planlanan_yil`.
  Her girdisi olculebilir. Basabas formulunun cebirsel tersi ama onemli
  farkla: basabas beklenen getiriyi PAYDADA istiyordu ve o sayi sistemin
  uretemeyecegi bir tahmindi. Islem maliyeti planlanan sureye YAYILIR - kisa
  plan ayni maliyeti daha agir kilar.
- **`beklenen_getiri_yillik` VARSAYILANI YOK**: `null` ise gereken getiri
  hesaplanir ve GOSTERILIR ama sinyal URETILMEZ. Bir sayi girilirse o
  KULLANICI BEYANIDIR (`kaynak: kullanici-beyani`), modelin tahmini degil.
  Beyan gerekenin altindaysa sinyal bastirilir. Sistemin bu alani kendi
  doldurmasi, uretmedigi bir fiyat tahminini uretiyormus gibi yapmak olurdu -
  bir kez yapildi (0.65/0.55/0.80/0.55) ve silindi.
- **maliyet payi = (tasima + gidis_donus/planlanan) / gereken**. Ozdeslik:
  `maliyet_payi + risksiz/gereken = 1`. Pay `HURDLE_HAKIMIYET_ESIGI`nin (%10)
  altindaysa baglayici kisit maliyet DEGIL, TL risksiz getiridir - komisyonu
  sifirlasan bile gereken getiri neredeyse ayni kalir. Su an 12 varligin
  HEPSI bu durumda: %48 risksiz oran her seyi domine ediyor.
- **hurdle bayatliginda IKI esik var**: `firsat.bayatlik_gun` (7) ve
  `firsat.durdurma_gun` (30). Arada kalan bant ISARETLENIR, rapor URETILIR
  (`uyarilari_topla` -> "Hurdle rate N GUNLUK"); yalnizca durdurma esigi
  asilinca rapor durur. Kapi `main.hurdle_engeli` -> `risksiz_durduruyor_mu`,
  `risksiz_taze_mi` DEGIL - ikincisi artik sadece isaretleme sorusudur.
  Tek esikle basladi ve 2026-08-19'da patladi: TCMB `TP.TRY.MT02`'yi 12 gun
  yayimlamadi, sistem arka arkaya 6 kosuda coktu, o gunun tek ciktisi
  "BASARISIZ" alarmi oldu. Asil korkulan sey bayatligin GORUNMEMESIYDI;
  cozumu susmak degil isaretlemek. Olculen sey politika faizine bagli mevduat
  orani - 12 gunde onda birkac puan oynar, %48'lik hurdle'da gurultudur.
  30 gun keyfi degil: PPK ~6 haftada bir toplaniyor, 30 gunu asan oran arada
  faiz karari gecmis OLABILECEGI anlamina gelir (gecikmis degil, YANLIS).
- **canli TCMB orani DURDURMA esigiyle kabul edilir, taze esigiyle degil**
  (`fetch.maliyet_modelini_coz`): canli deger reddedilirse yerine elle
  yazilmis YAML yedegi geciyor ve o yedek DAHA ESKI olabilir. Taze esigiyle
  eleseydik 12 gunluk canli sayiyi atip 60 gunluk yedegi kullanabilirdik -
  tam tersi. Enflasyon satiri bu kuralin disinda: onun durdurma katmani yok.
- **tarihsiz yedek TAZE SAYILMAZ**: `firsat.tl_risksiz_tarih` bos birakilirsa
  sistem hicbir zaman rapor uretmez. Bilincli: elle yazilmis bir sayinin ne
  zamandan kaldigi bilinmiyorsa guncel olduguna guvenilemez. Tarih serinin
  YAYIM tarihidir, dosyaya yazildigi gun degil.
- **`tcmb_yuzde_orani` UC deger doner** `(oran, kaynak, tarih)`: tarih modele
  kadar gelmezse bayatlik hic olculemez.
- **KAPSAM KURALI, kodla zorlanir**: bloke edebilen (yani `null` birakilinca
  sinyali kapatan) her alan bir duyarlilik boyutu tarafindan kapsanmak
  ZORUNDA. `duyarlilik.kapsam_denetimi()` ihlalleri dondurur ve
  `test_bloke_eden_parametre_duyarlilikta_kapsaniyor` bos olmasini sart kosar.
  Sebep: tahminle doldurulan bir alan sinyali ACABILIR; acilisi saglayan
  sayinin SINANMAMIS olmasi `null` disiplinini tumuyle bosa dusurur.
  Tek istisna `YAPISAL_ALANLAR` (`kur_cevrimi`) - bool, uc senaryosu olamaz,
  yani tahminle doldurulamaz.
- **kosulmamis boyut GECMIS SAYILMAZ**: `tutma_dayanikli`, `tutma_kararlari`
  bossa False doner. `maliyet.tutma` eksikse basabas boyutu kosmaz, tasima
  tahminleri KAPSAM DISI kalir ve varlik "DOGRULANMAMIS ACILIM" isaretlenir.
- **temettu ISARETI**: maliyet terimi `verim * stopaj`, verimin KENDISI degil.
  Seri `auto_adjust=True` ile cekiliyor, yani BRUT temettu fiyatta ZATEN var;
  net eline gecen `verim*(1-stopaj)`, aradaki fark tam olarak stopaj.
  Verimi maliyet yazmak temettuyu IKI KEZ duser, geliri ayrica eklemek IKI KEZ
  sayar. `auto_adjust` kapatilirsa formul sessizce yanlislasir -
  `test_temettu_isaret_dogru` o baglantiyi kilitliyor.
- **`maliyet.tutma.beklenen_getiri_yillik` TAHMIN DEGIL BEYAN**: sistem fiyat
  tahmini uretmez. Basabas paydasi ASIRI getiridir (`beklenen - tasima -
  risksiz`); TL risksiz %48 civarinda oldugu icin beklenen getiri bunun
  altindaysa payda negatif olur ve basabas SONSUZ cikar. Bu hata degil, dogru
  cevap - mevduattan az kazandiran varlik islem maliyetini hic geri odemez.
- **sebep KODLA tasinir, metinle degil**: `duyarlilik` sebep kodu dondurur,
  `sinyal.SEBEP_ETIKETLERI` etikete cevirir. Eskiden sebep, etiket metninde
  "belirsizligi" aranarak bulunuyordu; ucuncu sebep eklendiginde o eslestirme
  sessizce yanlis etiket uretti.
- **`null` kalem KALMADI, hepsi tahmin**: 12 varligin tamami olculebilir.
  `TumVarliklarOlculebilirTesti` bunu kilitliyor - yeni varlik eklenip maliyet
  kalemi doldurulmazsa test patlar. Sessizce bloklu kalan varlik raporda tek
  satir olur ve aylarca fark edilmez.
- **`emtia_bilinmiyor.kur_cevrimi: false` bir VARSAYIM**: gram altin TL ile TR
  platformundan alinir kabul edildi, kur marji saticinin TL fiyatina gomulu ve
  `menkul_spread` araligi (0.0010-0.0080) bunu kapsiyor. USD hesaptan ABD
  altin ETF'i alinacaksa `true` yapilmali VE `kur_spread_tek_yon` +
  `kambiyo_vergisi` doldurulmali. Bool oldugu icin aralik alamaz - olcum degil
  yapisal secim.
- **sorgu botu SALT OKUNUR**: `bot_sorgu.py` `gecmisi_yaz` CAGIRMAZ. Cagirsaydi
  soru sormak latch'i ilerletir ve kimse islem yapmadan bekleme suresi baslardi.
  Yazdigi tek dosya `simulasyon/bot_offset.txt`.
- **`TELEGRAM_IZINLI_CHAT_ID` bos = bot SUSAR**: "ayar yoksa herkese acik"
  degil. Ayrica anahtarin `notify.ORTAM_ANAHTARLARI` icinde olmasi SART -
  Actions'ta .env yok, secret ortamdan okunur; listede olmayan anahtar orada
  sessizce bos kalir ve bot hicbir mesaja cevap vermez.
- **bot offset izinsiz mesajda DA ilerler**: ilerlemeseydi tek bir yabanci
  mesaj `getUpdates` kuyrugunu kalici olarak tikar ve sahibinin komutlari hic
  islenmezdi. Cevap gitmez, offset gecer.
- **bot araligi YAML'da, cron SABIT**: Actions zamanlamasi YAML okuyamaz.
  `bot-sorgu.yml` 30 dakikada bir tetikler, `bildirim.yaml -> bot.aralik_dakika`
  fazladan kosuyu erken keser. Butce: 30 dk x 18 saat = ~1095 dk/ay, rapor
  workflow'unun ~400 dk'si ustune toplam ~%75. Sikismada ilk dugme
  `aralik_dakika: 60`.
- **iki workflow ayni dizine commit ETMEZ**: `bot-sorgu.yml` yalnizca
  `bot_offset.txt` ekler. `git add 04-projects/yatirim-sistemi/` yazilsaydi
  bot kosusu rapor workflow'unun urettigi dosyalari da commit eder ve iki
  workflow surekli rebase catismasi yasardi.
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
- **`null` != `0.0` (maliyet modelinin bel kemigi)**: `varliklar.yaml -> maliyet` altinda `null` "bilmiyorum", `0.0` "olctum, sifir cikti" demektir. Bilinmeyeni sifir yazmak sessiz basarisizligin en tehlikeli turu: hata cikmaz, yalnizca karsiz islem karli gorunur. Eksik kalemi olan varlik icin sinyal `report.py` VE `notify.py` ikisinde de bastirilir - yalnizca birinde bastirmak kurali bosa dusurur, Dodo Telegram'a bakip islem yapar.
- **"kapsam disi" ile "bilinmiyor" ayri bayraklar**: `kur_cevrimi: false` -> kur spread'i ve kambiyo vergisi SORULMAZ (TL hesaptan TL hisse alirken cevrim yoktur). `temettu_verimi: 0.0` -> stopaj sorusu duser. Bu bayraklar olmasa altin ve kripto sonsuza kadar "temettu stopaji bilinmiyor" diye bloklu kalirdi.
- **maliyet dagiliminda kismi olcum YAPILMAZ**: bir sembolun gider orani bilinmiyorsa "Gider orani" kalemi tumuyle OLCULEMEDI sayilir. Bilinenleri toplayip kalemi olculmus gibi gostermek maliyeti oldugundan dusuk raporlar. Bu yuzden net getiri "UST SINIR" etiketiyle yazilir.
- **hurdle rate ZORUNLU, ama tek kaynakli DEGIL**: `tl_risksiz_yillik` yoksa rapor URETILMEZ (sifira gore olculen her pozitif getiri "basari" gorunur). Once canli TCMB `TP.TRY.MT02`, olmazsa `varliklar.yaml` yedegi. USD/TRY'deki Yahoo yedegiyle ayni mantik: kaynagin bir gunluk kesintisi hurdle rate'i SIFIRLAMAMALI.
- **reel getiri CARPIMSAL**: `(1+n)/(1+e)-1`. Toplamsal `n-e` %25-50 enflasyon bandinda ciddi sapar: %40 nominal / %25 enflasyonda toplamsal %15 der, dogrusu %12.0.
- **yillik oran doneme BILESIK indirgenir**: `maliyet.donem_orani(yillik, gun) = (1+yillik)^(gun/365)-1`. Yillik %48'i 4 gunluk getiriyle dogrudan kiyaslamak elma-armut. Yeni getiri karsilastirmasi yazarken bu fonksiyonu kullan.
- **nakit sifir getiriyle DURMAZ**: `durumu_hesapla(..., nakit_getirisi_yillik=...)` verilirse her islem araliginda bakiyeye faiz isler. Faiz islem SONRASI bakiyeye uygulanir, tum sermayeye degil. Getiri BRUT'tur - mevduat stopaji bilinmiyor, yani gercek net getiri raporda yazandan DUSUK. Sim ozdesligi bu yuzden `net = gerceklesmemis + gerceklesen + nakit_getirisi - alis_komisyonu`.
- **`islemleri_oku` 4 deger doner**: `(islemler, baslangic_nakit, komisyon_orani, baslangic_tarihi)`. `durumu_hesapla(*islemleri_oku(...))` YAZMA - dorduncu deger `olaylar` parametresine duser.
- **TCMB seri arsivi WAF arkasinda**: `POST /igmevdsms-dis/fe` form-encoded gonderilince HTTP 200 + TCMB'nin "Sayfa Goruntulenemedi" HTML'i doner, JSON gonderilince 400. Yani anahtarla bile tam EVDS serisi (gerceklesen TUFE dahil) cekilemez. Anahtarsiz `sk-seriler` ucunda yalnizca ~10 seri var: USD, EUR, mevduat faizi (`TP.TRY.MT02`), TUFE BEKLENTISI (`TP.PKAUO.S01.E.U`). `http_json` HTML govdeyi zaten yakalar.
- **`TP.FE.OKTG01` ARSIVLENMIS**: sartnamede gecen enflasyon serisi hem arsiv (son guncelleme 09-02-2026) hem de ozel kapsamli (cekirdek) TUFE, manset degil. Guncel manset `TP.TUKFIY2025.GENEL` ama yukaridaki WAF yuzunden erisilemiyor.
- **TCMB oran serileri YUZDE cinsinden**: `47.91` = %47.91. `tcmb_yuzde_orani` 100'e boler. Bolmezsen hurdle rate 4791 kat getiri olur ve her portfoy "basarisiz" cikar.
- **TCMB aylik seride tarih "AGUSTOS 2026"**, gunluk seride "07-08-2026". `_tcmb_tarihi` ikisini de cozer ve aylik seride ayin ILK gununu alir - aylik veriyi taze gostermek bayat enflasyonu guncel sanmak demektir.
- **`bicim.py` neden var**: `tl/yuzde/oran` bicimlendiricileri `report.py` ve `rapor_maliyet.py` arasinda kopyalanirsa biri 1 digeri 2 basamak gosterir, ayni rakam iki tabloda farkli okunur.
- **esik testi TEK yerde**: `sinyal.kararlari_uret()` disinda hicbir yerde esik karsilastirmasi yazma. `report.py` ve `notify.py` artik yalnizca `Karar` nesnesini render eder. FAZ 3'te ayni bastirma kurali iki modulde ayri yazildigi icin iki kez tutarsizlik cikti; tek karar noktasi bunun yapisal cozumu.
- **histerezis latch'i DISKTE**: `sinyal-durumu.yaml` (+ `gonderilen.log`) makine uretimi KALICI DURUM, turetilmis veri degil. Actions `git add 04-projects/yatirim-sistemi/` ile commit eder; commit edilmezse her kosu latch'i kapali baslatir ve histerezis hicbir sey hatirlamaz. Yerel kosuyla Actions ayni dosyayi yazarsa catisma cikar - rapordan farkli olarak burada dogru surum **Actions'inki**.
- **ters yon geri donus esigini KULLANMAZ**: bant yalnizca AYNI yondeki sinyali ayakta tutar. `+2 puan -> -2 puan` gecisinde geri donus esigi (1.5) uygulansaydi, tetigi (3 puan) hic asmamis bir ters islem onerisi mesrulasirdi. `sinyal._sinif_sonucu` bu yuzden `onceki.yon == yon` sartini arar.
- **bekleme suresi 24 DEGIL 20 saat**: Actions gunde bir calisiyor, iki kosu arasi tam 24.0 saat ve cron 5-30 dakika kayabiliyor. Esik 24 olsaydi gunlerin yaklasik yarisinda TUM sembol sinyalleri sessizce dusurulurdu. 20 saat gunluk kadansta no-op, kadans saatlige cikinca devreye girer. Kadansi artirirken `bekleme.ayni_sembol_saat`'i de 24'e cikar.
- **bastirilan sinyal saati ILERLETMEZ**: `son_sinyal` yalnizca sinyal gercekten uretildiginde guncellenir. Bastirilan sinyal saati ilerletseydi bekleme suresi kendi kendini uzatir ve sembol bir daha asla sinyal uretmezdi.
- **devre kesildiginde gunluk sayac ilerlemez**: kesilen kosuda sinyal URETILMEDIGI icin sayac sabit kalir. Ilerleseydi devre bir daha asla kapanmaz, tek bir yogun gun sistemi kalici olarak susturmus olurdu.
- **latch, esigi asma durumunu izler; bastirma sebeplerinden BAGIMSIZ**: eksik maliyet / bekleme / devre kesici sinyali bastirir ama latch'i degistirmez. Latch piyasa kosulunu tutar, bizim gonderim kararimizi degil.
- **`gonderilen.log` once GONDER sonra YAZ**: log gonderimden once yazilirsa basarisiz bir gonderim "gonderildi" isaretlenir ve mesaj bir daha asla denenmez. `#` ile baslayan satirlar anahtar sayilmaz (dosya basligi icin).
- **UTC zorunlu**: `sinyal.simdi_utc()` disinda `datetime.now()` kullanma. Actions UTC'de, yerel kosu TR saatinde calisir; naive damgalarla gecen sure NEGATIF cikar ve bekleme suresi anlamini yitirir. Tarih (`gun`, `ozet:{tarih}`) ise rapor adiyla AYNI olmali - o yerel `date.today()`.
- **`sinyal-durumu.yaml` bos kayit yazmaz**: kapali ve hic sinyal uretmemis kayit varsayilanla ayni. 12 sembol x 4 satir = okunmaz dosya. Kapali ama zaman damgasi olan kayit KALIR - bekleme latch kapandiktan sonra da isler.
- **geri donus esigi tetigin ALTINDA olmali**: `config._` dogrulamasi `0 < geri_donus < tetik` arar. Esit veya ustunde olsaydi bant ya hic olusmaz ya latch bir daha kapanmazdi; ikisi de sessizce yanlis calisir. Varsayilanlar (0.025 / 0.22) tetik varsayilanlariyla (0.05 / 0.25) ayni sekle sahip.
- **HAFTA SONU KUR TUZAGI (7/24'un on kosulu)**: forex Cuma 22:00 - Pazar 22:00 UTC kapali, TCMB is gunu disinda kur yayimlamaz. Yani hafta sonu USD/TRY DONMUS, kripto hareketli. `beklenen_tl = coingecko_usd x donmus_kur` ile BTCTurk'un canli TL fiyati arasindaki fark TR primi DEGIL, kurun bayatligidir. `%8 durdurma esigi` asilirsa DURDUR cikar ve TUM raporun uretimi durur. `ucgenle(..., kur_piyasasi_kapali=True)` bunu OLCULEMEDI'ye cevirir - degerleme BTCTurk TL fiyatindan devam eder, yalnizca capraz kontrol yapilmaz. Hafta ici cron'da hic tetiklenmiyordu; 7/24'te her hafta sonu canli.
- **"gun" TR gunudur, UTC gunu DEGIL**: `rapor_adi = (simdi_utc() + TR_OFSET).date()`. `date.today()` kullanilsaydi Actions (UTC) ile yerel makine (TR) ayni gun icin iki farkli isim uretir, TR 00:00-03:00 arasi kosular bir onceki gunun rapor dosyasina yazar ve gunluk sinyal sayaci TR 03:00'te sifirlanirdi. Rapor adi, `gunsonu:` anahtari, devre kesici sayaci ve nakit faizi hepsi ayni TR gununu kullanir.
- **rapor yalnizca gun sonu/brifing kosusunda yazilir**: tarama kosusu gunde 12 kez calisiyor ve rapor dosyasi tarihe gore adlandirildigi icin her kosu ayni dosyayi yeniden yazardi - 12 anlamsiz commit, hepsi bir sonrakinin ustune. Taramanin isi sinyal tespiti. `sinyal-durumu.yaml` ise HER kosuda yazilir (latch ve bekleme saati taramada da ilerler).
- **tek workflow, gorevi script secer**: `piyasa.Takvim.gorev()` saate bakip TARAMA / GUN_SONU / BRIFING doner. Ayri workflow'lar her biri ayri checkout + pip install ederdi, Actions dakikasi ikiye katlanirdi. Seans saatleri `bildirim.yaml -> takvim` icinde, kodda DEGIL - BIST seans saatleri gecmiste degisti.
- **Actions dakika butcesi**: private repo, GitHub Free = 2000 dk/ay, her kosu yukari yuvarlanir. 2 saatlik grid ~800 dk (%40), 1 saatlik ~1530 dk (%77), 30 dakikalik ~2980 dk (MUMKUN DEGIL). Sikligi artirmanin tek faydasi ilk hareketi ne kadar gec duydugundur - bekleme suresi zaten sembol basina gunde ~1 sinyalle siniriyor.
- **piyasa takvimi TATIL BILMEZ**: bayram/resmi tatil `bildirim.yaml`'da tanimli degil, seans "acik" gorunur. Bilincli: sabit tatil listesi her yil elle guncellenmezse sessizce yanlislasir, bayatlik olcumu (`bayat_semboller`) ise kendini duzeltir ve zaten tatili yakalar.
- **`gonderilen.log` mesaj TURU basina anahtar**: `gunsonu:{tarih}`, `brifing:{tarih}`, `islem:{sembol}:{tarih}:{saat}:{yon}`, `uyari:{tip}:{tarih}:{saat}:{ozet}`, `toplu:{tarih}:{saatdk}`. Tek `ozet:{tarih}` anahtari 7/24'te yetmez - ayni gun hem brifing hem gun sonu var.
- **`islem:` anahtarlari hiz sinirina SAYILMAZ**: `son_saatteki_gonderim` onlari atlar. Islem kararlari zaten devre kesiciyle (gunde 6) sinirli; hiz siniri sayimina girselerdi 5 islem karari gun sonu ozetini bastirirdi.
- **hafta sonu sinyali bastirilmaz, SINIFI dusurulur**: normal esigi asip `hafta_sonu_carpani` ile genisletilmis esigi asmayan sinyal `HAFTA_SONU` sebebiyle islem onerisi olmaktan cikar ama `karar.hafta_sonu_uyarilari` icinde kalir ve gun sonu uyarilarina girer. Bilgi kesilmez, cita yukselir.
- **`uyarilari_topla` TEK uyari kaynagi**: eskiden uyari bloklari mesaj sablonuna dagilmisti ve yeni bir uyari turu rapora girip Telegram'a girmeyebiliyordu. Yeni uyari turu eklerken bu fonksiyona ekle, sablona degil.
- **`mesaj.py` sablon, `notify.py` tasima, `bildirim.py` politika**: sablon degistirmek icin tasima kodunu okumak gerekmiyor ve sablonlar agsiz test edilebiliyor. `mesaj_gonder`'i dogrudan cagirmak hiz siniri ve sessiz saat frenlerini ATLAR - tek istisna rapor uretilemediginde giden hata mesajlari (main.py), onlar sessiz kalmamali.
- **yerel seri geri BOLUNMEZ**: `fetch._serileri_hazirla` uc seri birden dondurur (TL, kendi para birimi, kur). `try_gecmis / kur` ile yerel seriyi turetmek yasak: kur serisi ffill'li, varlik serisi degil; bolme ffill artifaktini yerel seriye tasir ve `(1+yerel)(1+kur)-1` toplam TL getirisini tutmaz.
- **kur ayristirmasi CARPIMSAL**: `toplam_tl = (1+yerel)(1+kur)-1`. Toplamsal (%20 yerel + %25 kur = %45) dogrusu %50'dir. Ayrim olmadan +%30 TL getirisi "iyi secim" gorunur; oysa kur %28 arttiysa varlik dolar bazinda neredeyse hic kazandirmamistir.
- **Actions kosusu ~35 SANIYE, faturasi 1 DAKIKA**: sure `gh run list --json createdAt,updatedAt` ile olculur. GitHub kosu basina yukari yuvarlar, yani 35 sn de 59 sn de 1 dakikadir. Butceyi "kosu ~2 dk" diye tahmin etmek toplami iki katina cikarir - 2 saatlik grid %40 degil %20. Butce kararindan once OLC; tahmin, sirf sayi buyuk gorundugu icin gereksiz seyrekletme kararina goturur.
- **kosu suresi 60 saniyeyi asarsa fatura IKIYE katlanir**: 30 dakikalik grid bu yuzden riskli (%75 -> %149). Yeni bir ag cagrisi veya agir hesap eklerken kosu suresini yeniden olc; esik 60 saniye.
- **cron dakikasi 0 DEGIL**: GitHub zamanlanmis kosulari best-effort calistirir ve saat basi kuyrugun en kalabalik ani. `0 */2` 10-40 dakika gecikebilir, `7 */2` gecikmez. Gun sonu croni (`30 20`) istisna: `gorev()` esigi tam 23:30 TR, kaydirilirsa gun sonu ozeti taramaya duser.
- **sessiz saat TIPE bakar**: `biriktirilir_mi(tip, an)`, `sessiz_mi(an)` degil. 01:00-08:00 arasi BIST de Nasdaq da kapali, yani o saatte sinyal uretebilen tek sey kripto - islem karari gece de GIDER, ozet ve uyari birikir. Biriken bir "AL" mesaji tavsiye degil, kacirilan firsatin tutanagidir. `bildirim.yaml -> sessiz_saatler.istisna_tipler`, bos birakilirsa gece tamamen susar.
- **sessiz saatte istisna tip hiz siniri BIRLESTIRMESINI atlar**: birlestirme bekleyen kuyrugu da yollar. Atlamasaydi 01:05'teki tek kripto sinyali, 00:55'te dolan saatlik sinir yuzunden tum gece kuyrugunu bosaltir ve sessiz saat kuralini fiilen kaldirirdi.

- **webhook aktifken `getUpdates` HTTP 409 doner**: Telegram ikisini ayni
  anda kullandirmaz. Bu yuzden webhook'a gecerken yoklama yolu fiilen
  kapandi ve `bot-sorgu.yml`den cron KALDIRILDI - zamanlanmis kosu bekleyen
  mesaji okuyamaz, sadece hata verip 1 dakika yakardi. Emniyet agi
  Telegram'in kendisinde: webhook 200 donmezse guncelleme kuyrukta kalir ve
  yeniden denenir. Geri donus tek satir: `deleteWebhook`.
- **Worker HER ZAMAN HTTP 200 doner**: 401/500 donerse Telegram webhook'u
  devre disi birakabilir veya sonsuz yeniden deneme baslatir. Yetkisiz istek
  sessizce yutulur - reddedildigi belli EDILMEZ.
- **chat id IKI yerde suzuluyor** (Worker + `tek_komutu_cevapla`): repo'ya
  yazma yetkisi olan biri Worker'i atlayip dogrudan `repository_dispatch`
  atabilir. Yetki kontrolu tek katmana birakilamaz.
- **komut metni workflow'da `${{ }}` ile GOMULMEZ**: kullanici yazdigi metin
  dogrudan `run:` icine gomulseydi kabuk enjeksiyonu olurdu. Ortam
  degiskeni (`KOMUT`) uzerinden gecer, tirnak icinde okunur.
- **webhook maliyeti KULLANIMA bagli**: yoklama sabit ~1095 dk/ay yakiyordu,
  webhook ~10 mesaj/gunde ~300 dk. Ama gunde 40 komut ~1200 dk eder.
  `worker.js -> AYAR` iki fren tutuyor: `ASGARI_ARALIK_SN` (90 sn) ve
  `TAVAN_ORANI` (0.92). Tavanda sorgu botu durur, gunluk rapor DURMAZ -
  oncelik onda.
- **kota olcumu basarisizsa fren ACILIR**: `kosulariSay` null donunce istek
  gecer. Olcememeyi "kota dolmus" saymak, GitHub API'sinin bir hikkirigini
  botun tumden susmasina cevirirdi.

## memory.md Kullanimi
- Oturumlar arasi bilgileri memory.md'ye yaz.
- Format: Tarih + kisa madde.
