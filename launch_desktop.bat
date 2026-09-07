@echo off
setlocal
cd /d "%~dp0"

title SELA AI Desktop App - UCIC

echo ================================================================
echo    SELA AI RECEPTIONIST - APLIKASI DESKTOP
echo    Universitas Catur Insan Cendekia - UCIC Cirebon
echo ================================================================

:: 1. Atur PATH agar selalu mencakup Node.js dan biner lokal
set "PATH=C:\Program Files\nodejs;%~dp0node_modules\.bin;%PATH%"

:: 2. Hentikan sisa proses Electron lama jika ada yang tertahan
taskkill /F /IM electron.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: 3. Pastikan Mesin AI Offline aktif di port 8008
python -c "import requests; requests.get('http://127.0.0.1:8008/kesehatan', timeout=3)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [SELA Desktop] Memulai server AI di latar belakang port 8008...
    start "SELA Mesin AI" /min cmd /c "python ai-engine/server.py"
    echo [SELA Desktop] Menunggu server AI siap...
    timeout /t 6 /nobreak >nul
) else (
    echo [SELA Desktop] Server AI offline telah aktif di port 8008.
)

:: 4. Meluncurkan Jendela Aplikasi Desktop SELA
echo [SELA Desktop] Membuka jendela desktop SELA AI...
set "NODE_ENV=production"
call "%~dp0node_modules\.bin\electron.cmd" .

echo ================================================================
echo SELA AI Desktop ditutup.
echo ================================================================
pause
