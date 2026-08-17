# Haftalik vault gozden gecirme.
# Windows Task Scheduler tarafindan calistirilir (IkinciBeyin-VaultDenetim).
#
# Neden GitHub Actions'ta DEGIL: CI checkout'u .gitignore beyaz listesi
# yuzunden eksik vault icerir (03-wiki, 02-sources, 05-daily repoda yok).
# Denetci orada calissaydi mevcut tum wikilink'leri "kirik" raporlardi.
# Tam vault yalnizca bu makinede var.

$ErrorActionPreference = 'Stop'

$Python    = 'C:\Users\Dodo\AppData\Local\Programs\Python\Python312\python.exe'
$Normalize = Join-Path $PSScriptRoot 'girdileri_topla.py'
$Betik     = Join-Path $PSScriptRoot 'gozden_gecir.py'
$LogDizi   = Join-Path $PSScriptRoot 'loglar'
$Log       = Join-Path $LogDizi 'haftalik.log'

if (-not (Test-Path $LogDizi)) { New-Item -ItemType Directory -Path $LogDizi | Out-Null }

function Yaz($mesaj) {
    $satir = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mesaj
    Add-Content -Path $Log -Value $satir -Encoding utf8
}

Yaz '--- vault denetimi basladi ---'

if (-not (Test-Path $Python)) {
    Yaz "HATA: python bulunamadi: $Python"
    exit 1
}

# Once normalizasyon, sonra denetim. Sira onemli: denetim Telegram'a ozet
# gonderiyor, once temizlenmezse zaten duzeltilebilir bir durumu bildirir.
# Normalizasyon coksa denetim yine calisir - denetim daha onemli olan is.
$ciktiN = & $Python $Normalize 2>&1
$kodN = $LASTEXITCODE

Yaz 'normalizasyon:'
foreach ($satir in $ciktiN) { Yaz "  $satir" }
if ($kodN -ne 0) { Yaz "  UYARI: normalizasyon basarisiz (exit=$kodN)" }

$cikti = & $Python $Betik --telegram 2>&1
$kod = $LASTEXITCODE

Yaz 'denetim:'
foreach ($satir in $cikti) { Yaz "  $satir" }

if ($kod -eq 0 -and $kodN -ne 0) { $kod = $kodN }
Yaz $(if ($kod -eq 0) { 'sonuc: BASARILI' } else { "sonuc: HATA (exit=$kod)" })

$satirlar = @(Get-Content $Log)
if ($satirlar.Count -gt 1000) {
    $satirlar[-500..-1] | Set-Content -Path $Log -Encoding utf8
}

exit $kod
