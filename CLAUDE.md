# Ikinci Beyin Kurallari

## Kim Icin
Bu vault, Dodo'nun kisisel bilgi tabanidir.
Ilgi alanlari: Dijital girisimler, sistem kurma, otomasyon
Profesyonel baglam: Vibecoder

## Vault Yapisi
- 01-inbox/: Ham, islenmemis girdiler. Her zaman buradan basla.
- 02-sources/: Islenmis kaynak materyaller.
- 03-wiki/: Sentetik bilgi - kavramlar, kisiler, konular.
- 04-projects/: Aktif projeler.
- 05-daily/: Gunluk notlar.
- 06-archive/: Tamamlanmis materyaller.

## Not Yazma Kurallari
1. Her not atomik olmali - tek bir fikir, tek bir dosya.
2. Her notun YAML frontmatter'i olmali (title, date_created, tags, status, related).
3. [[Wiki baglantilari]] ile notlar arasi iliskiler kur.
4. Baglantilari YALNIZCA gercek iliski varsa kur.
5. Turkce yaz, teknik terimler Ingilizce kalabilir.

## Baglanti Kurallari
- Bir kavram en az 2 farkli kaynakta gecmedikce wiki sayfasi olusturma.
- Zayif baglantilardan kacin.
- Guclu baglanti: somut mekanizma, neden-sonuc, karsitlik.

## Isleme Hatti
1. 01-inbox/ dosyalarini oku.
2. Icerigi analiz et, anahtar kavramlari cikar.
3. 02-sources/ altina ozet olustur.
4. 03-wiki/ altinda sayfalari guncelle veya olustur.
5. [[baglantilar]] ile mevcut notlara bagla.
6. status'u processed olarak guncelle.

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
- **testler**: `python -m unittest discover -s scripts/yatirim -p "test_*.py"` (23 test, pytest YOK, stdlib unittest). Tamami cevrimdisi/sentetik - Yahoo'ya gitmez, piyasa saatinden bagimsiz. Kod degisikligi sonrasi calistir.
- **calistirma GitHub Actions'ta**: repo `baduone03/yatirim-sistemi` (private), workflow hafta ici 16:00 UTC = 19:00 TR. Yerel Task Scheduler gorevi KALDIRILDI - ikisi ayni anda calisirsa Telegram'a gunde iki mesaj duser. `gunluk.ps1` yerel yedek olarak duruyor ama zamanlanmis degil.
- **`gh secret set` PowerShell pipe ile BOZULUR**: `$deger | gh secret set AD` satir sonu ekleyip token'i gecersiz kilar (Telegram HTTP 404 verir). Daima `--body $deger` kullan.
- **vault = git repo, beyaz liste**: `.gitignore` once `/*` ile her seyi dislar, sonra yalnizca `scripts/`, `04-projects/yatirim-sistemi/`, `CLAUDE.md`, `README.md`, `.github/` eklenir. Yeni not klasoru varsayilan olarak GitHub'a GITMEZ. Kara listeye cevirme.
- **Actions raporu repoya commit eder**: calismaya baslamadan ONCE `git pull` yap. Yoksa ayni tarihli rapor dosyasinda rebase catismasi cikar (hem Actions hem sen ayni dosyayi uretirsiniz). Cozum: rapor turetilmis veri, `git checkout --theirs` ile kendi surumunu al, sonra yeniden uret.
- **kisma kurali = katki VE beta**: ham risk katkisi TEK BASINA yanlis olcut. 6 pozisyonda ortalama katki %16.7'dir, birilerinin tavani asmasi zorunludur; ayrica pozisyonu kucultmek katkiyi dusurur ama BETAYI DEGISTIRMEZ (beta varligin ozelligi). Yalniz katkiya bakan kural, parasindan az risk tasiyan verimli varliklari (QQQ beta 0.83) sattirir. `Esikler.kisilmali()` iki kosulu birden arar.
- **karar esikleri YAML'da**: `varliklar.yaml` -> `esikler`. Kodda sabit tutma. Simulasyonda agresif (3 puan / %20), gercek parada gevsek (5 puan / %25) olmali - komisyon %0.15, gidis-donus %0.30.
- **karisik takvim / volatilite tuzagi (ONEMLI)**: BIST hafta sonu kapali, kripto acik. `ffill().pct_change()` kapali gunleri sifir getiri yapar -> volatilite %20-25 DUSUK cikar. `ffill` olmadan `pct_change()` ise NaN'den sonraki gunu de siler -> her Pazartesi BIST getirisi kaybolur, veri %30 azalir. Dogru yol `risk.ortak_getiriler()`: once tum varliklarin islem gordugu ortak takvime `reindex`, sonra `pct_change`. Yeni getiri hesabi yazarken bu fonksiyonu kullan.
- **yillicklastirma carpani sabit degil**: `risk.yillik_periyot_sayisi()` carpani gozlem yogunlugundan turetir (~241), `islem_gunu_yil: 252` yalnizca fallback. Ortak takvim kesisim oldugu icin 252 varsaymak volatiliteyi ~%3 sisirir.
- **bayat fiyat**: `son_fiyatlar` ffill yapar, delist/veri kesintisi sessizce eski fiyatla degerleme yapardi. `FiyatVerisi.bayat_semboller()` 7 gunden eski veriyi raporda ve Telegram'da isaretler. Degerlemeyi bozmaz, yalnizca gorunur kilar.
- **sqlite3 cursor tuzagi**: dis dongude `cur.execute(...)` uzerinde iterasyon yaparken ic ic ayni cursor'a `execute` cagirmak dis iterasyonu sessizce keser. Ayri cursor kullan veya once `.fetchall()`.

## memory.md Kullanimi
- Oturumlar arasi bilgileri memory.md'ye yaz.
- Format: Tarih + kisa madde.
