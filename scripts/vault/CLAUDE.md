# Vault Bakim Tuzaklari

Web Clipper girdileri, frontmatter isleme ve haftalik denetim. Yalnizca bu
klasorde calisirken gecerli B kategorisi maddeler - A maddeleri kok
`CLAUDE.md`'dedir ve buraya YAZILMAZ.

## Gotchas (B)

- **Web Clipper `status` alani yazmaz**: kupurler vault sablonunu degil clipper'in kendi
  sablonunu kullanir. Hedef klasor uzanti ayarindadir, `status` alanini ise hicbir ayar
  yazdirmaz. Iki savunma var: `girdileri_topla.py` kupuru `01-inbox`'a tasir ve `status: inbox`
  damgalar; `gozden_gecir.py` girdi klasorlerinde (`01-inbox`, `Clippings`) `status` alani HIC
  olmayan notu bekleyen sayar. Klasor ayari duzelse bile damgalama gerekli kalir.
- **`haftalik-denetim.ps1` sirasi**: once `girdileri_topla.py`, sonra `gozden_gecir.py
  --telegram`. Ters cevirme - denetim Telegram'a ozet gonderiyor, once normalize edilmezse zaten
  kendiliginden duzelecek bir durumu bildirir.
- **mevcut `status` degeri asla ezilmez**: `girdileri_topla.py` alani yalnizca HIC yoksa ekler.
  Aksi halde her calisma islenmis notlari yeniden inbox'a acar.
- **BOM bosluk sayilmaz**: `metin.lstrip().startswith("---")` UTF-8-BOM ile yazilmis dosyada
  FALSE doner (PowerShell `Set-Content -Encoding utf8` BOM yazar). Frontmatter kontrolu icin
  daima `_frontmatter_blok()` kullan, elle string kontrolu yazma.
- **frontmatter alani govdede aranmaz**: `_frontmatter_alani` yalnizca `--- ... ---` blogunu
  tarar. Tum metni tarasaydi boru hattini anlatan bir not govdesindeki ornek `status: inbox`
  satiri o notu islenmemis girdi yapardi.
