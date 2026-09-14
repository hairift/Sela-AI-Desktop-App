# SELA AI Desktop Launcher (PowerShell)
$ErrorActionPreference = "SilentlyContinue"
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $PSScriptRoot

$env:PATH = "C:\Program Files\nodejs;" + "$PSScriptRoot\node_modules\.bin;" + $env:PATH

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   SELA AI RECEPTIONIST - APLIKASI DESKTOP (OFFLINE DAN FULL DUPLEX)" -ForegroundColor Green
Write-Host "   Universitas Catur Insan Cendekia (UCIC) Cirebon" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Hentikan sisa proses Electron lama jika ada
Stop-Process -Name "electron" -Force -ErrorAction SilentlyContinue

# 2. Pilih interpreter Python yang benar-benar punya dependensi SELA (fastapi + uvicorn)
#    Catatan: `python` di PATH bisa menunjuk versi lain tanpa paket, sehingga server gagal jalan.
$PYEXE = "python"
$PYARGS = @()
try {
    & py -3.12 -c "import fastapi, uvicorn" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $PYEXE = "py"; $PYARGS = @("-3.12") }
} catch { }
Write-Host "[SELA Desktop] Interpreter Python: $PYEXE $($PYARGS -join ' ')" -ForegroundColor Cyan

# 3. Periksa apakah server AI aktif di port 8008
$aiStatus = $null
try { $aiStatus = Invoke-WebRequest -Uri "http://127.0.0.1:8008/kesehatan" -UseBasicParsing -TimeoutSec 1 2>$null } catch { }
if (-not $aiStatus -or $aiStatus.StatusCode -ne 200) {
    Write-Host "[SELA Desktop] Menjalankan server AI di latar belakang (Port 8008)..." -ForegroundColor Yellow
    $argServer = @($PYARGS) + @("ai-engine/server.py")
    Start-Process -FilePath $PYEXE -ArgumentList $argServer -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "[SELA Desktop] Server AI offline aktif dan siap di port 8008." -ForegroundColor Green
}

# 4. Jalankan Aplikasi Desktop Electron
Write-Host "[SELA Desktop] Membuka jendela aplikasi desktop SELA AI..." -ForegroundColor Green
$env:NODE_ENV = "production"
& "$PSScriptRoot\node_modules\.bin\electron.cmd" .

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SELA AI Desktop ditutup." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
