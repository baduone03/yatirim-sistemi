# Haftalik vault saglik denetimi (Katman 0 yedek + Katman 1 tespit).
#
# Yatirim tarafindaki isle KARISTIRMA:
#   scripts/yatirim/gunluk.ps1        -> portfoy raporu, Telegram'a mesaj atar
#   scripts/vault/haftalik.ps1        -> deterministik vault denetimi (python)
#   scripts/haftalik-denetim.ps1      -> BU DOSYA, Claude ile anlamsal denetim
# Bu betik Telegram'a mesaj ATMAZ, cakisma yok. Zamanlanmis gorev adi:
# `vault-haftalik-denetim` (Pazar 03:00 onerilir - piyasalar kapali).
#
# Terfi (Katman 3) su an KAPALI - dosyanin sonundaki bloga bak.

$ErrorActionPreference = 'Stop'

$vault = "C:\Users\Dodo\ikinci-beyin"
$yedek = "C:\Users\Dodo\ikinci-beyin-yedek"
$tarih = Get-Date -Format "yyyy-MM-dd"

# --- KATMAN 0: YEDEK ---
# Denetimden ONCE calisir. Yedek alinamazsa denetim hic baslamaz: bu klasorler
# .gitignore beyaz listesi disinda, yani GitHub'da kopyalari YOK. Tek koruma bu.
$hedef = Join-Path $yedek $tarih
New-Item -ItemType Directory -Path $hedef -Force | Out-Null
foreach ($k in @("01-inbox", "02-sources", "03-wiki", "05-daily", "06-archive",
                 "07-dogrulanmis", "memory.md", ".claude")) {
    $kaynak = Join-Path $vault $k
    if (Test-Path $kaynak) { Copy-Item $kaynak $hedef -Recurse -Force }
}
Write-Host "Yedek alindi: $hedef"

# Son 4 yedegi tut, eskileri sil. Ad formati yyyy-MM-dd oldugu icin
# ada gore ters siralama = tarihe gore ters siralama.
Get-ChildItem $yedek -Directory | Sort-Object Name -Descending |
    Select-Object -Skip 4 | Remove-Item -Recurse -Force

# --- KATMAN 1: TESPIT ---
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "claude CLI bulunamadi - denetim calistirilamadi. Yedek alindi."
}

Set-Location $vault

# Arac kisiti en onemli guvenlik katmani: `Bash` listede YOK. Bash olmadan
# Claude dosya silemez, `rm` calistiramaz, git komutu veremez.
# Not: onceki oturum varsa "resume?" diyalogu headless calismayi kilitler,
# echo "1" ile onu geciyoruz.
echo "1" | claude -p "/audit" `
    --allowedTools "Read,Glob,Grep,Edit,Write" `
    --max-turns 40 `
    --output-format text | Tee-Object -FilePath "$hedef\denetim-cikti.txt"

Write-Host "Denetim bitti. Rapor: 05-daily/audit-$tarih.md"

# --- KATMAN 3: TERFI PUSH --- (ILK AY KAPALI)
#
# Ilk ay terfi ELLE yapilacak: rapordaki "terfiye uygun" notlara Dodo bakar,
# uygun bulduklarini elle 07-dogrulanmis/ altina tasir. Kapinin dogru
# calistigi gorulunce asagidaki blok acilacak.
#
# Acmadan once: /audit icindeki Bolum C de acilmali, yoksa 07-dogrulanmis/
# hicbir zaman dolmaz ve bu blok her hafta "terfi edecek not yok" der.
#
# git pull --rebase
# git add 07-dogrulanmis/
# $degisiklik = git diff --cached --name-only
# if ($degisiklik) {
#     git commit -m "terfi: dogrulanmis notlar $tarih"
#     git push
#     Write-Host "GitHub'a terfi edildi."
# } else {
#     Write-Host "Terfi edecek yeni not yok."
# }
