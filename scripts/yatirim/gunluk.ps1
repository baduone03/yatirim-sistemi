# Gunluk simulasyon raporu + Telegram ozeti.
# Windows Task Scheduler tarafindan calistirilir (bkz. gorev-kur.ps1).
#
# Python'un tam yolu gomulu: zamanlanmis gorev farkli PATH ile calisir,
# 'python' komutu orada bulunamayabilir.

$ErrorActionPreference = 'Stop'

$Python  = 'C:\Users\Dodo\AppData\Local\Programs\Python\Python312\python.exe'
$Betik   = Join-Path $PSScriptRoot 'main.py'
$LogDizi = Join-Path $PSScriptRoot 'loglar'
$Log     = Join-Path $LogDizi 'gunluk.log'

if (-not (Test-Path $LogDizi)) { New-Item -ItemType Directory -Path $LogDizi | Out-Null }

function Yaz($mesaj) {
    $satir = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mesaj
    Add-Content -Path $Log -Value $satir -Encoding utf8
}

Yaz '--- calisma basladi ---'

if (-not (Test-Path $Python)) {
    Yaz "HATA: python bulunamadi: $Python"
    exit 1
}

# stderr'i de yakala: yfinance uyarilari ve Python hatalari oraya gider.
$cikti = & $Python $Betik --sim --telegram 2>&1
$kod = $LASTEXITCODE

foreach ($satir in $cikti) { Yaz "  $satir" }

if ($kod -eq 0) {
    Yaz 'sonuc: BASARILI'
} else {
    Yaz "sonuc: HATA (exit=$kod)"
}

# Log dosyasi sinirsiz buyumesin: 2000 satiri gecerse son 1000'i tut.
$satirlar = @(Get-Content $Log)
if ($satirlar.Count -gt 2000) {
    $satirlar[-1000..-1] | Set-Content -Path $Log -Encoding utf8
}

exit $kod
