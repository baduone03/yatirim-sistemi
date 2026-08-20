# Gotcha Gecmisi (C - GECMIS)

Duzeltilmis, tekrarlanamaz veya karsiligi kalmamis maddeler. Kural degil KAYIT:
her oturumda baglama girmesinler diye `CLAUDE.md`'den cikarildilar, silinmediler.
Tasima tarihi: 2026-08-20.

## Tumuyle cikarilan maddeler

- **[#127] kota olcumu basarisizsa fren ACILIR**: 133 numarali maddenin BIREBIR KOPYASIYDI.
  `CLAUDE.md`'de iki ayri `## Gotchas` basligi vardi ve ayni kural her ikisine de yazilmisti.
  Kural yasiyor: `altyapi/telegram-webhook/CLAUDE.md`.
  - Kaldirilan metin: kota olcumu basarisizsa fren ACILIR: `kosulariSay` null donunce istek
  gecer. Olcememeyi "kota dolmus" saymak, GitHub API'sinin bir hikkirigini botun tumden
  susmasina cevirirdi.

- **[#79] sqlite3 cursor tuzagi**: Repoda `sqlite3` HIC kullanilmiyor (`grep -rl sqlite3 scripts
  altyapi` bos doner). Karsiligi olmayan kural. sqlite'a gecilirse geri alinir.
  - Kaldirilan metin: sqlite3 cursor tuzagi: dis dongude `cur.execute(...)` uzerinde iterasyon
  yaparken ic ice ayni cursor'a `execute` cagirmak dis iterasyonu sessizce keser. Ayri cursor
  kullan veya once `.fetchall()`.

- **[#83] hurdle rate ZORUNLU, ama tek kaynakli DEGIL**: Yerini HurdleZinciriTesti ile gelen
  ZINCIR mantigi aldi (mevduat birincil, politika faizi yedek). "Once canli TCMB, olmazsa YAML
  yedegi" tarifi artik YANLIS - zincir ikiden fazla kaynak tasiyabiliyor ve yedege dusus uyari
  uretiyor. Guncel kural: `scripts/yatirim/CLAUDE.md` -> hurdle zinciri.
  - Kaldirilan metin: hurdle rate ZORUNLU, ama tek kaynakli DEGIL: `tl_risksiz_yillik` yoksa
  rapor URETILMEZ (sifira gore olculen her pozitif getiri "basari" gorunur). Once canli TCMB
  `TP.TRY.MT02`, olmazsa `varliklar.yaml` yedegi. USD/TRY'deki Yahoo yedegiyle ayni mantik:
  kaynagin bir gunluk kesintisi hurdle rate'i SIFIRLAMAMALI.

## Maddeden cikarilan olay anlatilari

Kurallarin kendisi yasiyor; yalnizca "bir kez soyle patladi" anlatilari
buraya alindi. Kural metnini kisaltir, olayi kaybetmez.

- **[#39] ham `Tahmin` ARITMETIGE GIRMEZ**: Bu kural bir kez ihlal edildi ve gercek
  yapilandirmayla main.py coktu;
- **[#47] `beklenen_getiri_yillik` VARSAYILANI YOK**: Sistemin bu alani kendi doldurmasi,
  uretmedigi bir fiyat tahminini uretiyormus gibi yapmak olurdu - bir kez yapildi
  (0.65/0.55/0.80/0.55) ve silindi.
- **[#49] hurdle bayatliginda IKI esik var**: Tek esikle basladi ve 2026-08-19'da patladi: TCMB
  `TP.TRY.MT02`'yi 12 gun yayimlamadi, sistem arka arkaya 6 kosuda coktu, o gunun tek ciktisi
  "BASARISIZ" alarmi oldu. Asil korkulan sey bayatligin GORUNMEMESIYDI; cozumu susmak degil
  isaretlemek.
- **[#57] sebep KODLA tasinir, metinle degil**: Eskiden sebep, etiket metninde "belirsizligi"
  aranarak bulunuyordu; ucuncu sebep eklendiginde o eslestirme sessizce yanlis etiket uretti.
- **[#93] esik testi TEK yerde**: FAZ 3'te ayni bastirma kurali iki modulde ayri yazildigi icin
  iki kez tutarsizlik cikti; tek karar noktasi bunun yapisal cozumu.
