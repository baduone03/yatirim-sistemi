Vault saglik denetimi yap. SALT OKUNUR.

## AKTIF KAPSAM

**Yalnizca BOLUM A calisir.** Asagidaki "PASIF" basligi altindaki Bolum B, C
ve D bu ay devre disidir - onlari okuma, uygulama, ozetleme. Hicbir dosyayi
degistirme, tasima, silme, birlestirme. Tek yazma islemi denetim raporudur.

Gerekce: denetimin ne buldugunu gormeden ona yazma yetkisi vermek,
halusinasyona karsi kurulan sistemin kendisini halusinasyona acar. Dort hafta
rapor okunacak, prompt kalibre edilecek, sonra yazma yetkisi verilecek.

## KAPSAM DISI (dokunma, okuma bile gereksiz)

`04-projects/yatirim-sistemi/`, `.env`, `.git/`

`CLAUDE.md` dosyalarinin ICERIGI kapsam disi - okuma, degistirme, ozetleme.
Tek istisna asagidaki 8 numarali kontrol: yalnizca BOYUT ve kategori etiketi
olculur, icerik degerlendirilmez.

## BOLUM A: TESPIT (hicbir sey degistirme)

1. **Celiski:** `03-wiki/` icinde birbiriyle celisen iddialari bul.
2. **Kaynaksiz:** `kaynak_zinciri` bos olan wiki sayfalarini listele.
3. **Suresi dolmus:** `gecerlilik` tarihi gecmis notlar.
4. **Yetim:** hicbir baglantisi olmayan notlar.
5. **Tek kaynak:** tum iddialari tek dis kaynaktan gelen sayfalar.
6. **Yanki ihlali:** kanit olarak baska bir wiki sayfasini gosteren notlar.
7. **Tahmin vadesi:** `04-projects/vault-sistemi/tahminler.md` icinde kontrol
   tarihi gelmis olanlar.
8. **CLAUDE.md sismesi:** her `CLAUDE.md` dosyasinin boyutunu olc (bayt / 4 =
   kabaca token). Sinirlar: kok `CLAUDE.md` 5k token, alt klasor 8k token.
   Uc kontrol, ucu de UYARI - hicbiri hata degil, hicbiri isi durdurmaz:
   - Sinirini asan dosya: "N token, sinir M" diye bildir.
   - Sinirini %20'den fazla asan dosya (kok > 6k, alt klasor > 9.6k):
     "KISALTMA TURU GEREKLI" diye bildir. Testi olan maddeler tek satira
     inebilir, olay anlatilari arsive tasinabilir. Duzeltmeyi SEN yapma.
   - Alt klasor `CLAUDE.md`'lerinde `(A,` kategori etiketi tasiyan madde ara.
     Alt klasorde A kategorisi madde OLAMAZ - bulunan her madde koke tasinmak
     uzere listelenir.

2 ve 4 numarali kontroller `scripts/vault/gozden_gecir.py` tarafindan zaten
deterministik olarak yapiliyor. Ayni bulguyu tekrar uretme; betigin urettigi
son raporu (`05-daily/YYYY-AA-GG-gozden-gecirme.md`) oku ve farkli bir sey
buldiysan onu yaz. Asil deger 1, 5, 6 ve 7'de - bunlari regex bulamaz.

## CIKTI

`05-daily/audit-YYYY-AA-GG.md`
Maksimum 400 kelime. Sorun yoksa "temiz" yaz, uzun rapor uretme.

---

# PASIF - BU AY CALISTIRMA

Asagidakiler ilk ay kapali. Egitim tekerlekleri cikinca bu basligi ve
yukaridaki "AKTIF KAPSAM" uyarisini kaldir.

<!--
=== BOLUM B: GUVENLI DUZELTME ===
Sadece sunlari yap:
- Suresi dolmus notlarin status'unu needs-review yap
- Kaynaksiz iddialara [DOGRULANMAMIS] isareti ekle
- Arsiv kuralina uyan notlari 06-archive/ altina tasi

Icerik iddiasi DEGISTIRME. Not SILME. Not BIRLESTIRME.

DEVRE KESICI: 20'den fazla notta degisiklik gerekiyorsa hicbir sey yapma,
"DEVRE KESICI ACILDI: N not etkilenecekti" yaz ve dur.

=== BOLUM C: TERFI DEGERLENDIRMESI ===
03-wiki/ icindeki her notu 7 kontrolden gecir:
1. kaynak_zinciri dolu mu
2. Tum iddialar [OLGU]/[CIKARIM]/[TAHMIN] etiketli mi
3. Yanki ihlali yok mu
4. gecerlilik dolmamis mi
5. Celiski taramasindan temiz mi
6. Son degisiklikten bu yana 14 gun gecmis mi
7. Hassas veri (token, anahtar, kisisel bilgi, gercek pozisyon) yok mu

Yedisini de gecen notu 07-dogrulanmis/ altina kopyala.
Gecemeyeni 05-daily/terfi-red-YYYY-AA-GG.md dosyasina gerekcesiyle yaz.

=== BOLUM D: ONAY BEKLEYENLER ===
Silme, birlestirme, celiski cozumu ve iddia duzeltmesi onerilerini
05-daily/onay-bekleyen-YYYY-AA-GG.md dosyasina yaz. UYGULAMA.
-->
