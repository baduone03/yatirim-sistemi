# Yatirim Sistemi Tuzaklari

Fiyat cekme, risk olcumu, maliyet modeli, sinyal uretimi ve bot. Yalnizca bu
klasorde calisirken gecerli B kategorisi maddeler - birden fazla klasoru baglayan
A maddeleri kok `CLAUDE.md`'dedir ve buraya YAZILMAZ.

## Gotchas (B)

- **yatirim carpani**: `carpan` (ons->gram) YALNIZCA `fetch.py:_tl_bazina_cevir` icinde
  uygulanir. `portfolio.py` fiyatlari zaten cevrilmis alir - orada tekrar carparsan deger 31 kat
  kucuk cikar.
- **TL cevrimi**: fiyat gecmisi indirilirken `USDTRY=X` de cekilir; kur verisi gelmezse script
  hata verir, sessizce USD birakmaz.
- **BIST sembolleri**: Yahoo'da `.IS` soneki gerekir (`THYAO.IS`). Veri boslugu olabilir, rapor
  "Veri uyarilari" bolumunde isaretler.
- **iki farkli maliyet tabani**: `portfoy.yaml` maliyeti varligin KENDI para biriminde tutar
  (guncel kurla cevrilir). `simulasyon/islemler.yaml` ise islem anindaki TL fiyatini tutar
  (cevrim yok). Bu yuzden iki ayri fonksiyon var: `portfoyu_hesapla` ve
  `portfoyu_ledgerdan_hesapla`. Karistirma.
- **Telegram**: `python-telegram-bot` KULLANILMIYOR - `requests` ile dogrudan Bot API. Async
  yok, MarkdownV2 kacisi yok, `Bot.close()` tuzagi yok. HTML parse modunda yalnizca `& < >`
  kacirilir.
- **BIST evreni ana rapora girmez**: 59 hisse `izleme: true` yapilirsa korelasyon matrisi 59x59
  olur, rapor okunmaz. `bist-evreni.yaml` yalnizca `tarama.py` icindir.
- **Yahoo'da delist BIST tickerlari**: ISATR, KOZAL, SODA, KOZAA, SELGD - evrenden cikarildi.
  Yeni delist cikarsa tarama uyari basar, calismaya devam eder.
- **kisma kurali = katki VE beta**: ham risk katkisi TEK BASINA yanlis olcut. 6 pozisyonda
  ortalama katki %16.7'dir, birilerinin tavani asmasi zorunludur; ayrica pozisyonu kucultmek
  katkiyi dusurur ama BETAYI DEGISTIRMEZ (beta varligin ozelligi). Yalniz katkiya bakan kural,
  parasindan az risk tasiyan verimli varliklari (QQQ beta 0.83) sattirir. `Esikler.kisilmali()`
  iki kosulu birden arar.
- **karisik takvim / volatilite tuzagi (ONEMLI)**: BIST hafta sonu kapali, kripto acik.
  `ffill().pct_change()` kapali gunleri sifir getiri yapar -> volatilite %20-25 DUSUK cikar.
  `ffill` olmadan `pct_change()` ise NaN'den sonraki gunu de siler -> her Pazartesi BIST
  getirisi kaybolur, veri %30 azalir. Dogru yol `risk.ortak_getiriler()`: once tum varliklarin
  islem gordugu ortak takvime `reindex`, sonra `pct_change`. Yeni getiri hesabi yazarken bu
  fonksiyonu kullan.
- **yillicklastirma carpani sabit degil**: `risk.yillik_periyot_sayisi()` carpani gozlem
  yogunlugundan turetir (~241), `islem_gunu_yil: 252` yalnizca fallback. Ortak takvim kesisim
  oldugu icin 252 varsaymak volatiliteyi ~%3 sisirir.
- **bayat fiyat**: `son_fiyatlar` ffill yapar, delist/veri kesintisi sessizce eski fiyatla
  degerleme yapardi. `FiyatVerisi.bayat_semboller()` 7 gunden eski veriyi raporda ve Telegram'da
  isaretler. Degerlemeyi bozmaz, yalnizca gorunur kilar.
- **kurumsal olay maliyet kurali (EN KRITIK)**: bedelsiz/split'te `adet *= oran` ama **TOPLAM
  MALIYET DEGISMEZ**. Cebinden para cikmadi. Toplam maliyeti orana BOLMEK, olmayan kar uydurur:
  1000 TL'lik 10 lot, 2.0 bedelsizden sonra 20 lottur ve maliyeti hala 1000 TL'dir; 500'e
  dusurursen %100 sahte kar cikar. Birim maliyet `toplam/adet`ten turetilir ve zaten dogru
  sekilde yariya iner.
- **kurumsal olay zaman cizgisi**: olaylar islemlerle TARIH SIRASINDA harmanlanir
  (`ledger._zaman_cizgisi`), topluca uygulanmaz. Toplu carpim, olaydan SONRA alinan lotlari da
  carpar - 4:1 split'ten sonra alinan 10 lot 40 gorunur. Ayni tarihte olay islemden ONCE gelir
  (ex-tarih mantigi).
- **supheli sembol RISK hesabina da girmez**: kurumsal olay suphesi hem degerlemeyi durdurur hem
  sembolu getiri matrisinden cikarir (`risk._risk_gecmisi`). Fiyata guvenmeyip o fiyattan
  turetilen volatiliteye guvenmek tutarsiz. Tum semboller supheliyse risk hesabi sebebini yazan
  hatayla durur, bos matrisle devam etmez.
- **`risk_modu: disla | duzelt`** (`varliklar.yaml -> kurumsal_olay`): `disla` varsayilan.
  `duzelt` defterdeki TUM olaylari geri-duzeltme olarak uygular (`_seriyi_duzelt`: ex-tarihten
  ONCEKI fiyatlar orana BOLUNUR), sonra hala supheli olani dislar. Supheli sembol tam da olay
  defterde OLMADIGI icin supheli sayilir, yani ona uygulanacak oran yoktur - `duzelt` modunun
  asil isi, deftere YAZILMIS olayin seride biraktigi sicramayi temizlemek.
- **fiyat serisi duzeltmesi ile adet/maliyet muhasebesi AYRI**: `ledger` tarafinda toplam
  maliyet DEGISMEZ; `risk._seriyi_duzelt` ise olcek birligi icin fiyati boler. Ikisini ayni
  kural sanip maliyeti de bolmek sahte kar uydurur.
- **gozlem dususu GUN degil HUCRE sayar**: ortak takvim bir KESISIM oldugu icin sembol cikarmak
  gun sayisini dusurmez, ARTIRIR. Kaybedilen sey kapsam; olcu gun x sembol
  (`risk._gozlem_dususu`). Esik `kurumsal_olay.gozlem_dusus_esigi`.
- **tahmin `null` DEGILDIR**: `null` "hicbir sey soyleyemem" demek ve sinyali tamamen kapatir;
  uc senaryolu `tahmin` blogu "olcmedim ama sinirlarini biliyorum" demek. Blokta `tahmin: true`
  ZORUNLU - olmadan sozluk reddedilir, yoksa yanlislikla yazilmis bir blok olculmus sayi gibi
  davranirdi.
- **dayaniklilik != islem yap**: karar uc senaryoda da AYNI cikabilir ama o ortak karar "maliyet
  sapmayi yutuyor" olabilir. `VarlikDuyarliligi.dayanikli` kararin GUVENILIR oldugunu,
  `sinyal_acik` YAPILMASI gerektigini soyler. Yalnizca dayanikliliga bakan kapi, maliyeti
  kesinlikle sapmadan buyuk olan varlikta islem onerir.
- **duyarlilik karar olcutu**: gidis-donus maliyeti < `esikler.rebalancing_sapma`. Ikisi de
  portfoy orani cinsinden, dogrudan karsilastirilabilir. Maliyet sinirin ustundeyse islem
  duzelttigi sapmadan fazlasini goturur.
- **sabit komisyon kucuk pozisyonu bogar**: 2 x 1.5 USD x 41 TL / 3.000 TL = %4.1. ABD
  varliklari referans pozisyonda esigi ASAR ve "maliyet yutuyor" cikar; 12.000 TL'de
  `kur_spread_tek_yon` belirleyici parametre olur. Yani duyarlilik sonucu POZISYON BUYUKLUGUNE
  bagli - `maliyet.duyarlilik. referans_pozisyon_try` degistirilirse sonuc degisir.
- **ham `Tahmin` ARITMETIGE GIRMEZ**: `Tahmin > 0` ve `Tahmin * float` TypeError verir.
  `eksik_kalemler` icin `_pozitif_olabilir` (KOTUMSER senaryoya bakar - iyimserde 0 olan verim
  kotumserde varsa stopaj sorusu DUSMEZ), aritmetik icin `senaryoyla(TEMEL)`.
  `GercekYapilandirmaTesti` bunun icin var - sentetik sozlukler gercek YAML'daki girinti
  hatasini yakalamaz.
- **rapor kalemi tahmine dayaniyorsa ISARETLENIR**: `maliyet_kalemleri` `[TAHMIN: temel
  senaryo]` notu ekler. Olculmus gibi gorunen bir tahmin, modelin kapatmaya calistigi hatanin ta
  kendisi.
- **`maliyet.sembol_spreadi` profili EZER**: tek global spread, likiditesi cok farkli hisseleri
  ayni kefeye koyar (BIST30 dar, kucuk hisse genis) ve buyuklerde maliyeti abartip gereksiz
  "ekonomik degil" karari uretir. Listede olmayan sembol profilin varsayilanini alir; tanimsiz
  sembol `config` dogrulamasinda patlar.
- **referans pozisyon SABIT DEGIL, portfoyden turetilir** (`duyarlilik.referans_pozisyonlar`):
  tutulan varlikta gercek deger, tutulmayanda hedef dagilimda alacagi deger (sinif hedefi / o
  siniftaki sembol sayisi), portfoy bossa YAML yedegi. Sabit referans varsaymak sonucu OLCMEK
  yerine SECMEK olur - ayni varlik 1.700 TL'de "pozisyon cok kucuk", 12.000 TL'de "su
  parametreyi olc" cikiyor.
- **"ekonomik degil" ile "parametre belirsizligi" AYRI bolumler**: ilkinde eksik olan PARA,
  ikincisinde bir SAYI. Cozumleri de farkli - biri buyutulur veya varliktan cikilir, digeri
  olculur. Ayni listede gosterilirse cozumu para olan sorun "sonra olcerim" kutusunda kalir.
- **minimum ekonomik pozisyon**: `2*komisyon_usd*usdtry / (esik - taban)`. `taban` = pozisyondan
  BAGIMSIZ kisim (oransal komisyon + 2*kur spread + kambiyo vergisi + 2*menkul spread). Taban
  esigi asiyorsa `math.inf` doner - hicbir buyukluk yetmez, o varliktan cikmaktan baska secenek
  yok.
- **duyarlilik IKI BOYUTLU**: (1) islem maliyeti - `gidis_donus` sapma esigini asiyor mu; (2)
  tasima - beyan edilen beklenti GEREKEN getiriyi karsiliyor mu. Ikisi de gecmeden sinyal
  acilmaz.
- **sistem beklenen getiri URETMEZ, GEREKENI hesaplar**: `gereken = tl_risksiz + yillik_tasima +
  gidis_donus / planlanan_yil`. Her girdisi olculebilir. Basabas formulunun cebirsel tersi ama
  onemli farkla: basabas beklenen getiriyi PAYDADA istiyordu ve o sayi sistemin uretemeyecegi
  bir tahmindi. Islem maliyeti planlanan sureye YAYILIR - kisa plan ayni maliyeti daha agir
  kilar.
- **`beklenen_getiri_yillik` VARSAYILANI YOK**: `null` ise gereken getiri hesaplanir ve
  GOSTERILIR ama sinyal URETILMEZ. Bir sayi girilirse o KULLANICI BEYANIDIR (`kaynak:
  kullanici-beyani`), modelin tahmini degil. Beyan gerekenin altindaysa sinyal bastirilir.
  Sistemin bu alani kendi doldurmasi, uretmedigi bir fiyat tahminini uretiyormus gibi yapmak
  olurdu.
- **maliyet payi = (tasima + gidis_donus/planlanan) / gereken**. Ozdeslik: `maliyet_payi +
  risksiz/gereken = 1`. Pay `HURDLE_HAKIMIYET_ESIGI`nin (%10) altindaysa baglayici kisit maliyet
  DEGIL, TL risksiz getiridir - komisyonu sifirlasan bile gereken getiri neredeyse ayni kalir.
  Su an 12 varligin HEPSI bu durumda: %48 risksiz oran her seyi domine ediyor.
- **hurdle bayatliginda IKI esik var**: `firsat.bayatlik_gun` (7) ve `firsat.durdurma_gun` (30).
  Arada kalan bant ISARETLENIR, rapor URETILIR (`uyarilari_topla` -> "Hurdle rate N GUNLUK");
  yalnizca durdurma esigi asilinca rapor durur. Kapi `main.hurdle_engeli` ->
  `risksiz_durduruyor_mu`, `risksiz_taze_mi` DEGIL - ikincisi artik sadece isaretleme sorusudur.
  Olculen sey politika faizine bagli mevduat orani - 12 gunde onda birkac puan oynar, %48'lik
  hurdle'da gurultudur. 30 gun keyfi degil: PPK ~6 haftada bir toplaniyor, 30 gunu asan oran
  arada faiz karari gecmis OLABILECEGI anlamina gelir (gecikmis degil, YANLIS).
- **canli TCMB orani DURDURMA esigiyle kabul edilir, taze esigiyle degil**
  (`fetch.maliyet_modelini_coz`): canli deger reddedilirse yerine elle yazilmis YAML yedegi
  geciyor ve o yedek DAHA ESKI olabilir. Taze esigiyle eleseydik 12 gunluk canli sayiyi atip 60
  gunluk yedegi kullanabilirdik - tam tersi. Enflasyon satiri bu kuralin disinda: onun durdurma
  katmani yok.
- **tarihsiz yedek TAZE SAYILMAZ**: `firsat.tl_risksiz_tarih` bos birakilirsa sistem hicbir
  zaman rapor uretmez. Bilincli: elle yazilmis bir sayinin ne zamandan kaldigi bilinmiyorsa
  guncel olduguna guvenilemez. Tarih serinin YAYIM tarihidir, dosyaya yazildigi gun degil.
- **`tcmb_yuzde_orani` UC deger doner** `(oran, kaynak, tarih)`: tarih modele kadar gelmezse
  bayatlik hic olculemez.
- **KAPSAM KURALI, kodla zorlanir**: bloke edebilen (yani `null` birakilinca sinyali kapatan)
  her alan bir duyarlilik boyutu tarafindan kapsanmak ZORUNDA. `duyarlilik.kapsam_denetimi()`
  ihlalleri dondurur ve `test_bloke_eden_parametre_duyarlilikta_kapsaniyor` bos olmasini sart
  kosar. Sebep: tahminle doldurulan bir alan sinyali ACABILIR; acilisi saglayan sayinin
  SINANMAMIS olmasi `null` disiplinini tumuyle bosa dusurur. Tek istisna `YAPISAL_ALANLAR`
  (`kur_cevrimi`) - bool, uc senaryosu olamaz, yani tahminle doldurulamaz.
- **kosulmamis boyut GECMIS SAYILMAZ**: `tutma_dayanikli`, `tutma_kararlari` bossa False doner.
  `maliyet.tutma` eksikse basabas boyutu kosmaz, tasima tahminleri KAPSAM DISI kalir ve varlik
  "DOGRULANMAMIS ACILIM" isaretlenir.
- **temettu ISARETI**: maliyet terimi `verim * stopaj`, verimin KENDISI degil. Seri
  `auto_adjust=True` ile cekiliyor, yani BRUT temettu fiyatta ZATEN var; net eline gecen
  `verim*(1-stopaj)`, aradaki fark tam olarak stopaj. Verimi maliyet yazmak temettuyu IKI KEZ
  duser, geliri ayrica eklemek IKI KEZ sayar. `auto_adjust` kapatilirsa formul sessizce
  yanlislasir - `test_temettu_isaret_dogru` o baglantiyi kilitliyor.
- **`maliyet.tutma.beklenen_getiri_yillik` TAHMIN DEGIL BEYAN**: sistem fiyat tahmini uretmez.
  Basabas paydasi ASIRI getiridir (`beklenen - tasima - risksiz`); TL risksiz %48 civarinda
  oldugu icin beklenen getiri bunun altindaysa payda negatif olur ve basabas SONSUZ cikar. Bu
  hata degil, dogru cevap - mevduattan az kazandiran varlik islem maliyetini hic geri odemez.
- **sebep KODLA tasinir, metinle degil**: `duyarlilik` sebep kodu dondurur,
  `sinyal.SEBEP_ETIKETLERI` etikete cevirir.
- **`null` kalem KALMADI, hepsi tahmin**: 12 varligin tamami olculebilir.
  `TumVarliklarOlculebilirTesti` bunu kilitliyor - yeni varlik eklenip maliyet kalemi
  doldurulmazsa test patlar. Sessizce bloklu kalan varlik raporda tek satir olur ve aylarca fark
  edilmez.
- **`emtia_bilinmiyor.kur_cevrimi: false` bir VARSAYIM**: gram altin TL ile TR platformundan
  alinir kabul edildi, kur marji saticinin TL fiyatina gomulu ve `menkul_spread` araligi
  (0.0010-0.0080) bunu kapsiyor. USD hesaptan ABD altin ETF'i alinacaksa `true` yapilmali VE
  `kur_spread_tek_yon` + `kambiyo_vergisi` doldurulmali. Bool oldugu icin aralik alamaz - olcum
  degil yapisal secim.
- **sorgu botu SALT OKUNUR**: `bot_sorgu.py` `gecmisi_yaz` CAGIRMAZ. Cagirsaydi soru sormak
  latch'i ilerletir ve kimse islem yapmadan bekleme suresi baslardi. Yazdigi tek dosya
  `simulasyon/bot_offset.txt`.
- **bot offset izinsiz mesajda DA ilerler**: ilerlemeseydi tek bir yabanci mesaj `getUpdates`
  kuyrugunu kalici olarak tikar ve sahibinin komutlari hic islenmezdi. Cevap gitmez, offset
  gecer.
- **bot araligi YAML'da, cron SABIT**: Actions zamanlamasi YAML okuyamaz. `bot-sorgu.yml` 30
  dakikada bir tetikler, `bildirim.yaml -> bot.aralik_dakika` fazladan kosuyu erken keser.
  Butce: 30 dk x 18 saat = ~1095 dk/ay, rapor workflow'unun ~400 dk'si ustune toplam ~%75.
  Sikismada ilk dugme `aralik_dakika: 60`.
- **kurumsal olay ledger'a yazilmaz**: `islemler.yaml` yalnizca SENIN islemlerini tutar,
  append-only. Bedelsiz sirketin isidir, nakit akisi yoktur. Ayri defter:
  `simulasyon/kurumsal-olaylar.yaml`.
- **bayatlik = kacirilan ISLEM GUNU, takvim gunu DEGIL**: BIST Cuma'dan Pazartesi'ye 3 takvim
  gunu gecirir, 1 islem gunu. Sartnamedeki "bist: 1 gun" takvim gunu olarak kodlansaydi her
  Pazartesi tum BIST hisseleri bayat cikardi. `FiyatVerisi._sinif_takvimi()` referans takvimi
  sinifin kendi verisinden turetir. Esigi 1'in ALTINDA olan siniflar (kripto) surekli piyasadir,
  onlarda referans tum takvimdir.
- **gunluk barda dakika esigi yok**: fiyat verisi `interval="1d"`. "kripto 15 dakika" gunluk
  barda tek bir seye karsilik gelir: esik 0 = en son barda veri olmali. Intraday veriye
  gecilmeden dakika/saat esigi anlamsizdir.
- **hacim dogrulanamazsa sembol supheli KALIR**: `_hacim_dogruluyor` hacim verisi yoksa False
  doner. Bilincli: dogrulanamayan sicramayi "gercek" saymak yanlis degeri dogruymus gibi
  raporlamaktir.
- **`kapanislari_indir` artik `(kapanis, hacim)` tuple doner**: hacim kurumsal olay tespiti icin
  sart. Tek deger bekleyen cagri sessizce DataFrame yerine tuple alir.
- **yfinance paralel indirmede "database is locked"** (B, 2026-08-26): 7 sembolun HEPSI birden
  `OperationalError('database is locked')` ile duserse sebep Yahoo degil, yfinance'in kendi
  SQLite onbelleginde is parcaciklarinin kilitlenmesi. `kapanislari_indir` bu yuzden 3 kez
  dener ve ILK denemeden sonrasini `threads=False` ile yapar - sirali indirme kendisiyle
  yarisamaz. Bkz. IndirmeYenidenDenemeTesti.
- **yfinance toplu indirmede gecici rate limit**: 13 sembolun HEPSI birden "possibly delisted"
  derse bu delist degil, rate limit. Kod "ag baglantisini kontrol et" der ama tek sembol ayri
  denendiginde calisiyorsa sebep budur; birkac dakika bekle. `period='365d'` gecerlidir, sorun o
  degil.
- **BTCTurk gecmis VERMEZ**: `/api/v2/ticker` anlik kotasyondur. Bu yuzden yalnizca DEGERLEME
  fiyatini ezer; volatilite, korelasyon ve beta hala Yahoo'nun 365 gunluk serisinden gelir. Yani
  kriptonun degeri BTCTurk'ten, getirisi Yahoo'dan. Rapor bunu yaziyor - kaldirma.
- **BTCTurk `timestamp` MILISANIYE**: saniye sanip cevirirsen tarih 1970 cikar ve her fiyat
  bayat sayilir, kripto degerlemesi sessizce Yahoo'ya doner.
- **TL ciftini dogrudan al**: BTCTRY yerine BTC/USD x USD/TRY carpimi kullanmak cift cevrim
  hatasidir. Ustelik TR primini o carpimla olcersen prim daima 0 cikar - kendi kendini
  dogrulayan hesap.
- **CoinGecko degerlemeye ASLA girmez**: rolu yalnizca ucgenleme referansi. Girseydi kripto
  fiyati bazen BTCTurk bazen CoinGecko olur, portfoy degeri kaynaga gore ziplardi.
- **TCMB yalnizca IS GUNU kur yayimlar** (~15:30). Hafta sonu/tatilde yeni kur yok. Bayat TCMB
  kuruyla ucgenleme yapmak "TR primi" adi altinda kurun bayatligini olcer - kripto 7/24 hareket
  ederken kur donmus kalir. `bayatlik_gun` asilirsa Yahoo'ya duser ve raporda `yahoo (tcmb
  bayat)` yazar.
- **OLCULEMEDI != DURDUR**: OLCULEMEDI kaynaklardan biri yok/bayat demek - bizim korlugumuz,
  rapor URETILIR. DURDUR uc kaynak da tazeyken gercek kopukluk demek - rapor URETILMEZ. Ayrimi
  kaldirirsan CoinGecko'nun bir dakikalik hikkirigi BIST ve altin dahil tum gunun raporunu
  sildirir.
- **`kaynaklar.py` ag katmani enjekte edilir**: her fonksiyon `getir=http_json` parametresi
  alir. Testler sahte `getir` gecirir, ag'a cikilmaz. Yeni kaynak eklerken bu kalibi bozma -
  yoksa test paketi ag'a bagimli hale gelir.
- **`null` != `0.0` (maliyet modelinin bel kemigi)**: `varliklar.yaml -> maliyet` altinda `null`
  "bilmiyorum", `0.0` "olctum, sifir cikti" demektir. Bilinmeyeni sifir yazmak sessiz
  basarisizligin en tehlikeli turu: hata cikmaz, yalnizca karsiz islem karli gorunur. Eksik
  kalemi olan varlik icin sinyal `report.py` VE `notify.py` ikisinde de bastirilir - yalnizca
  birinde bastirmak kurali bosa dusurur, Dodo Telegram'a bakip islem yapar.
- **"kapsam disi" ile "bilinmiyor" ayri bayraklar**: `kur_cevrimi: false` -> kur spread'i ve
  kambiyo vergisi SORULMAZ (TL hesaptan TL hisse alirken cevrim yoktur). `temettu_verimi: 0.0`
  -> stopaj sorusu duser. Bu bayraklar olmasa altin ve kripto sonsuza kadar "temettu stopaji
  bilinmiyor" diye bloklu kalirdi.
- **maliyet dagiliminda kismi olcum YAPILMAZ**: bir sembolun gider orani bilinmiyorsa "Gider
  orani" kalemi tumuyle OLCULEMEDI sayilir. Bilinenleri toplayip kalemi olculmus gibi gostermek
  maliyeti oldugundan dusuk raporlar. Bu yuzden net getiri "UST SINIR" etiketiyle yazilir.
- **reel getiri CARPIMSAL**: `(1+n)/(1+e)-1`. Toplamsal `n-e` %25-50 enflasyon bandinda ciddi
  sapar: %40 nominal / %25 enflasyonda toplamsal %15 der, dogrusu %12.0.
- **yillik oran doneme BILESIK indirgenir**: `maliyet.donem_orani(yillik, gun) =
  (1+yillik)^(gun/365)-1`. Yillik %48'i 4 gunluk getiriyle dogrudan kiyaslamak elma-armut. Yeni
  getiri karsilastirmasi yazarken bu fonksiyonu kullan.
- **nakit sifir getiriyle DURMAZ**: `durumu_hesapla(..., nakit_getirisi_yillik=...)` verilirse
  her islem araliginda bakiyeye faiz isler. Faiz islem SONRASI bakiyeye uygulanir, tum sermayeye
  degil. Getiri BRUT'tur - mevduat stopaji bilinmiyor, yani gercek net getiri raporda yazandan
  DUSUK. Sim ozdesligi bu yuzden `net = gerceklesmemis + gerceklesen + nakit_getirisi -
  alis_komisyonu`.
- **`islemleri_oku` 4 deger doner**: `(islemler, baslangic_nakit, komisyon_orani,
  baslangic_tarihi)`. `durumu_hesapla(*islemleri_oku(...))` YAZMA - dorduncu deger `olaylar`
  parametresine duser.
- **TCMB seri arsivi WAF arkasinda**: `POST /igmevdsms-dis/fe` form-encoded gonderilince HTTP
  200 + TCMB'nin "Sayfa Goruntulenemedi" HTML'i doner, JSON gonderilince 400. Yani anahtarla
  bile tam EVDS serisi (gerceklesen TUFE dahil) cekilemez. Anahtarsiz `sk-seriler` ucunda
  yalnizca ~10 seri var: USD, EUR, mevduat faizi (`TP.TRY.MT02`), TUFE BEKLENTISI
  (`TP.PKAUO.S01.E.U`). `http_json` HTML govdeyi zaten yakalar.
- **`TP.FE.OKTG01` ARSIVLENMIS**: sartnamede gecen enflasyon serisi hem arsiv (son guncelleme
  09-02-2026) hem de ozel kapsamli (cekirdek) TUFE, manset degil. Guncel manset
  `TP.TUKFIY2025.GENEL` ama yukaridaki WAF yuzunden erisilemiyor.
- **TCMB oran serileri YUZDE cinsinden**: `47.91` = %47.91. `tcmb_yuzde_orani` 100'e boler.
  Bolmezsen hurdle rate 4791 kat getiri olur ve her portfoy "basarisiz" cikar.
- **TCMB aylik seride tarih "AGUSTOS 2026"**, gunluk seride "07-08-2026". `_tcmb_tarihi` ikisini
  de cozer ve aylik seride ayin ILK gununu alir - aylik veriyi taze gostermek bayat enflasyonu
  guncel sanmak demektir.
- **`bicim.py` neden var**: `tl/yuzde/oran` bicimlendiricileri `report.py` ve `rapor_maliyet.py`
  arasinda kopyalanirsa biri 1 digeri 2 basamak gosterir, ayni rakam iki tabloda farkli okunur.
- **esik testi TEK yerde**: `sinyal.kararlari_uret()` disinda hicbir yerde esik karsilastirmasi
  yazma. `report.py` ve `notify.py` artik yalnizca `Karar` nesnesini render eder.
- **ters yon geri donus esigini KULLANMAZ**: bant yalnizca AYNI yondeki sinyali ayakta tutar.
  `+2 puan -> -2 puan` gecisinde geri donus esigi (1.5) uygulansaydi, tetigi (3 puan) hic
  asmamis bir ters islem onerisi mesrulasirdi. `sinyal._sinif_sonucu` bu yuzden `onceki.yon ==
  yon` sartini arar.
- **bekleme suresi 24 DEGIL 20 saat**: Actions gunde bir calisiyor, iki kosu arasi tam 24.0 saat
  ve cron 5-30 dakika kayabiliyor. Esik 24 olsaydi gunlerin yaklasik yarisinda TUM sembol
  sinyalleri sessizce dusurulurdu. 20 saat gunluk kadansta no-op, kadans saatlige cikinca
  devreye girer. Kadansi artirirken `bekleme.ayni_sembol_saat`'i de 24'e cikar.
- **bastirilan sinyal saati ILERLETMEZ**: `son_sinyal` yalnizca sinyal gercekten uretildiginde
  guncellenir. Bastirilan sinyal saati ilerletseydi bekleme suresi kendi kendini uzatir ve
  sembol bir daha asla sinyal uretmezdi.
- **devre kesildiginde gunluk sayac ilerlemez**: kesilen kosuda sinyal URETILMEDIGI icin sayac
  sabit kalir. Ilerleseydi devre bir daha asla kapanmaz, tek bir yogun gun sistemi kalici olarak
  susturmus olurdu.
- **latch, esigi asma durumunu izler; bastirma sebeplerinden BAGIMSIZ**: eksik maliyet / bekleme
  / devre kesici sinyali bastirir ama latch'i degistirmez. Latch piyasa kosulunu tutar, bizim
  gonderim kararimizi degil.
- **`gonderilen.log` once GONDER sonra YAZ**: log gonderimden once yazilirsa basarisiz bir
  gonderim "gonderildi" isaretlenir ve mesaj bir daha asla denenmez. `#` ile baslayan satirlar
  anahtar sayilmaz (dosya basligi icin).
- **`sinyal-durumu.yaml` bos kayit yazmaz**: kapali ve hic sinyal uretmemis kayit varsayilanla
  ayni. 12 sembol x 4 satir = okunmaz dosya. Kapali ama zaman damgasi olan kayit KALIR - bekleme
  latch kapandiktan sonra da isler.
- **geri donus esigi tetigin ALTINDA olmali**: `config._` dogrulamasi `0 < geri_donus < tetik`
  arar. Esit veya ustunde olsaydi bant ya hic olusmaz ya latch bir daha kapanmazdi; ikisi de
  sessizce yanlis calisir. Varsayilanlar (0.025 / 0.22) tetik varsayilanlariyla (0.05 / 0.25)
  ayni sekle sahip.
- **hafta sonu kur tuzagi** (B, 2026-08-20): hafta sonu USD/TRY DONMUS, kripto hareketli -
  aradaki fark TR primi DEGIL, kurun bayatligi. Gercek kopukluk sayilirsa DURDUR cikar ve o
  gun HIC rapor uretilmez. `kur_piyasasi_kapali=True` bunu OLCULEMEDI'ye cevirir; degerleme
  devam eder, yalnizca capraz kontrol duser. Bkz. HaftaSonuUcgenlemeTesti
- **rapor yalnizca gun sonu/brifing kosusunda yazilir**: tarama kosusu gunde 12 kez calisiyor ve
  rapor dosyasi tarihe gore adlandirildigi icin her kosu ayni dosyayi yeniden yazardi - 12
  anlamsiz commit, hepsi bir sonrakinin ustune. Taramanin isi sinyal tespiti.
  `sinyal-durumu.yaml` ise HER kosuda yazilir (latch ve bekleme saati taramada da ilerler).
- **piyasa takvimi TATIL BILMEZ**: bayram/resmi tatil `bildirim.yaml`'da tanimli degil, seans
  "acik" gorunur. Bilincli: sabit tatil listesi her yil elle guncellenmezse sessizce
  yanlislasir, bayatlik olcumu (`bayat_semboller`) ise kendini duzeltir ve zaten tatili yakalar.
- **`gonderilen.log` mesaj TURU basina anahtar**: `gunsonu:{tarih}`, `brifing:{tarih}`,
  `islem:{sembol}:{tarih}:{saat}:{yon}`, `uyari:{tip}:{tarih}:{saat}:{ozet}`,
  `toplu:{tarih}:{saatdk}`. Tek `ozet:{tarih}` anahtari 7/24'te yetmez - ayni gun hem brifing
  hem gun sonu var.
- **`islem:` anahtarlari hiz sinirina SAYILMAZ**: `son_saatteki_gonderim` onlari atlar. Islem
  kararlari zaten devre kesiciyle (gunde 6) sinirli; hiz siniri sayimina girselerdi 5 islem
  karari gun sonu ozetini bastirirdi.
- **hafta sonu sinyali bastirilmaz, SINIFI dusurulur**: normal esigi asip `hafta_sonu_carpani`
  ile genisletilmis esigi asmayan sinyal `HAFTA_SONU` sebebiyle islem onerisi olmaktan cikar ama
  `karar.hafta_sonu_uyarilari` icinde kalir ve gun sonu uyarilarina girer. Bilgi kesilmez, cita
  yukselir.
- **`uyarilari_topla` TEK uyari kaynagi**: eskiden uyari bloklari mesaj sablonuna dagilmisti ve
  yeni bir uyari turu rapora girip Telegram'a girmeyebiliyordu. Yeni uyari turu eklerken bu
  fonksiyona ekle, sablona degil.
- **`mesaj.py` sablon, `notify.py` tasima, `bildirim.py` politika**: sablon degistirmek icin
  tasima kodunu okumak gerekmiyor ve sablonlar agsiz test edilebiliyor. `mesaj_gonder`'i
  dogrudan cagirmak hiz siniri ve sessiz saat frenlerini ATLAR - tek istisna rapor
  uretilemediginde giden hata mesajlari (main.py), onlar sessiz kalmamali.
- **yerel seri geri BOLUNMEZ**: `fetch._serileri_hazirla` uc seri birden dondurur (TL, kendi
  para birimi, kur). `try_gecmis / kur` ile yerel seriyi turetmek yasak: kur serisi ffill'li,
  varlik serisi degil; bolme ffill artifaktini yerel seriye tasir ve `(1+yerel)(1+kur)-1` toplam
  TL getirisini tutmaz.
- **kur ayristirmasi CARPIMSAL**: `toplam_tl = (1+yerel)(1+kur)-1`. Toplamsal (%20 yerel + %25
  kur = %45) dogrusu %50'dir. Ayrim olmadan +%30 TL getirisi "iyi secim" gorunur; oysa kur %28
  arttiysa varlik dolar bazinda neredeyse hic kazandirmamistir.
- **sessiz saat TIPE bakar**: `biriktirilir_mi(tip, an)`, `sessiz_mi(an)` degil. 01:00-08:00
  arasi BIST de Nasdaq da kapali, yani o saatte sinyal uretebilen tek sey kripto - islem karari
  gece de GIDER, ozet ve uyari birikir. Biriken bir "AL" mesaji tavsiye degil, kacirilan
  firsatin tutanagidir. `bildirim.yaml -> sessiz_saatler.istisna_tipler`, bos birakilirsa gece
  tamamen susar.
- **sessiz saatte istisna tip hiz siniri BIRLESTIRMESINI atlar**: birlestirme bekleyen kuyrugu
  da yollar. Atlamasaydi 01:05'teki tek kripto sinyali, 00:55'te dolan saatlik sinir yuzunden
  tum gece kuyrugunu bosaltir ve sessiz saat kuralini fiilen kaldirirdi.
- **hata bildirimi kod bazinda 24 saatte bir** (`hata_takip.py`): iki saatlik gridde kalici bir
  ariza gunde 12 ayni mesaj uretiyordu. Yeni kod HEMEN, ayni kod 24 saat sonra "hala devam
  ediyor", cozulunce HEMEN.
- **bastirilan bildirim `son_bildirim`'i ILERLETMEZ**: ilerletseydi her kosu 24 saatlik sayaci
  sifirlar ve "hala devam ediyor" ozeti hicbir zaman gitmezdi. Sinyal bekleme latch'indeki ayni
  tuzak.
- **hata KODU karsilastirilir, MESAJ degil**: mesajda kosu URL'i ve tarih var, her kosuda
  degisir. Metne bakan karsilastirma her seferinde "yeni hata" gorur ve bastirma hic calismaz.
- **hurdle ZINCIR: mevduat birincil, politika faizi yedek** (`varliklar.yaml ->
  maliyet.firsat.kaynaklar`). Sira BILINCLI: hurdle'in tanimi "bu parayi nakitte tutsam ne
  kazanirdim" ve gercek alternatif MEVDUATTIR (%47.91). Politika faizi (%37.00) 11 puan dusuk;
  onu birincil yapmak citayi sessizce indirir ve her varlik hicbir sey degismeden daha iyi
  gorunur. Yedek olmasinin sebebi yapisal, degeri degil.
- **iki kaynak turu, IKI FARKLI TAZELIK SORUSU**: `tcmb_serisi` -> "kac gunluk?" (duzenli
  yayimlanan olcum). `ilan_edilmis` -> "hala yururlukte mi?" (PPK karari; kontrol
  `sonraki_gozden_gecirme` tarihidir). Politika faizi 23.01.2026'dan beri degismedi - gun sayan
  kural onu 208 gun bayat ilan eder ve saclamalar. `ilan_edilmis`in ara "isaretleme" bandi YOK:
  ya yururlukte ya degil; ara bant uydurmak, gecmis bir PPK karari ihtimalini "biraz bayat" diye
  yumusatmak olurdu.
- **`risksiz_durduruyor_mu` ZINCIR farkinda olmali**: duz alanlara bakan surum, yedege
  dusuldugunde politika faizini "208 gun bayat" ilan edip raporu durduruyordu - oysa o oran tam
  da bayatlayamadigi icin yedek secilmisti. Karar `risksiz_secilen.kullanilabilir_mi()`ye delege
  edilir.
- **`birincil_seri` KAZANAN kaynak degil, zincirdeki ILK seridir**: fetch bunu ceker. Kazanana
  bakilsaydi ilan edilmis oran one gectiginde canli seri hic yenilenmez, sonsuza kadar bayat
  kalir ve zincir bir daha asla birinciye donemezdi.
- **yedege dusus MUTLAKA uyari uretir** (`uyarilari_topla`): yedek oran citayi 11 puan
  dusuruyor. Sessizce gevsemis bir cita, gevsemis olduguna dair hicbir isaret tasimayan citadir.
- **zincirde en az bir `tcmb_serisi` ZORUNLU** (`_zinciri_coz` dogrulamasi): tumu elle girilmis
  olsaydi hurdle hicbir zaman canli dogrulanmaz, tamamen elle bakima kalirdi.
- **TLREF ve politika faizi CEKILEMIYOR** (2026-08 itibariyla): `evds2`
  `/service/evds/series=...` WAF'in HTML'ini doner (anahtarli da), `evds3` `/igmevdsms-dis/`
  altinda `sk-seriler` DISINDAKI tum yollar 403. `sk-seriler`teki 10 serinin icindeki tek faiz
  serisi `TP.TRY.MT02`. Bu yuzden politika faizi elle giriliyor; PPK takvimi yilda ~8 satir
  bakim.

- **bos sahte koleksiyon tip uyusmazligini GIZLER** (B, 2026-08-23): `RebalancingAlimTesti`
  sahtesi `"varliklar": []` tutuyordu; uretimde tip `dict[str, Varlik]`. Bos koleksiyon sifir kez
  dondugu icin `{v.sembol: ... for v in varliklar}` govdesi hic calismadi ve `AttributeError`
  uc cagri noktasinda birden uretime kadar gitti. Sahte veri uretimin **tipini** tasimali,
  yalnizca sekilini degil - bos liste/dict ile kurulan sahte, o kod yolunu HIC test etmez.
- **ongoru defteri karar yoluna BAGLANMAZ** (B, 2026-08-23): `tahmin.py` sinyal uretmez;
  `main.py`/`sinyal.py` onu import etmez ve Actions'ta AYRI adim olarak kosar. Sebep: bir
  ongoruye dayanarak pozisyon acmak, kalibre oldugu kanitlanmamis bir modele para baglamaktir.
  Bkz. `IzolasyonTesti`.
- **karne kosullu yazilir** (B, 2026-08-23): `tahmin.py` tarama gridinde de kosuyor; kosulsuz
  `write_text` gunde 12 anlamsiz commit uretirdi. Icerik aynysa dosyaya dokunulmaz.
- **varsayilan arguman `def` aninda baglanir** (B, 2026-08-23): `def oku(dosya=SABIT)` yazip
  sonra modul sabitini degistirmek fonksiyonu ETKILEMEZ - modul uctan uca test edilemez hale
  gelir. `main()` icinde sabitleri acikca gecir.
- **haber arsivi ozetten AYRI tavan kullanir** (B, 2026-08-23): Telegram ozeti besleme basina 6
  baslikla sinirli cunku okunabilir kalmali; arsiv `ARSIV_BESLEME_BASINA=40` kullanir. Ayni
  `haberleri_topla` iki farkli tavanla cagrilir - ozetin tavanini arsiv icin yukseltme, ozet
  okunmaz hale gelir. Bkz. `TavanTesti`.
- **arsivde anahtar BAGLANTI, baslik degil** (B, 2026-08-23): besleme ayni baglantiyi her kosuda
  tekrar verir; baslik anahtar olsaydi kucuk bir editoryal duzeltme kaydi coklardi. Gunluk dosya
  ~46 KB / ~135 baslik.
- **model listesi ERISIM BELGESI DEGIL** (B, 2026-09-05): `GET /v1/models` tum katalogu doner,
  hesabin cagirabildiklerini degil. `writer/palmyra-fin-70b-32k` ve
  `nvidia/nemotron-nano-3-30b-a3b` listede GORUNDUGU halde HTTP 404 veriyor
  ("Function ... not found for account"). Ne build.nvidia.com sayfasi ne de `/v1/models`
  kaynaktir - tek dogrulama gercek bir `chat/completions` cagrisi.
- **jeton tavani JSON'u ORTASINDAN keser** (B, 2026-09-05): `finish_reason=length` gelen cevap
  yarim kalir ve ayristirici "JSON degil" der - tani istem bicimine gider, oysa sorun tavanda.
  `llm.http_llm` bu durumu artik ayri hata olarak raporluyor. Bkz. `JetonTavaniTesti`.
- **kotasiz "ilgili" etiketi hicbir seyi siralamaz** (B, 2026-09-05): tavan konmadiginda model
  30 basligin 24'unu YUKSEK isaretledi; hem etiket bilgi tasimayi birakti hem cikti 900 jetonu
  asip cevabi yarida kesti. `AZAMI_YUKSEK=8` istemde SORULUR, `cevabi_coz` icinde UYGULANIR -
  istem bir rica, kirpma bir garantidir. Kotayla sure 26 sn'den 13.7 sn'ye dustu.
- **model secimi OLCULUR, okunmaz** (B, 2026-09-05): ayni haber gorevinde
  `mistralai/mistral-nemotron` 10 sn + gecerli JSON, `nvidia/nemotron-3-super-120b-a12b` 51 sn +
  tirnaksiz (bozuk) JSON, `nvidia/nemotron-3.5-lightning-30b-a3b` `chat_template_kwargs:
  {"thinking": false}` verilmesine ragmen dusunme metnini `content` icine sizdirdi. Parametre
  sayisi ve "reasoning" etiketi bu isin kalitesini soylemiyor.
- **NIM ucu KESINTIYE GIRIYOR** (B, 2026-09-05): ayni istem ayni gun once 10 sn'de dondu, sonra
  HTTP 500 ("Inference connection error") ve 25 sn zaman asimi verdi. Bu yuzden cagri
  BASARISIZLIGI normal yol sayilir: `haberleri_degerlendir` ve `ozet_uret` haberi/mesaji
  dusurmez, sebebi ciktiya yazip ham surume doner. Zaman asimini uzatarak "cozme" - kosu
  butcesi 60 saniye.
