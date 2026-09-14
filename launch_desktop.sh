#!/bin/bash
# ================================================================
# SELA AI RECEPTIONIST - APLIKASI DESKTOP (LINUX & MACOS)
# ================================================================

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "================================================================"
echo "   SELA AI RECEPTIONIST - APLIKASI DESKTOP (OFFLINE & FULL DUPLEX)"
echo "   Universitas Catur Insan Cendekia (UCIC)"
echo "================================================================"

# 1. Instalasi dependensi jika belum ada
if [ ! -d "node_modules" ]; then
    echo "[SELA Desktop] Menginstal dependensi antarmuka..."
    npm install
fi

# 2. Pilih interpreter Python yang benar-benar punya dependensi SELA (fastapi + uvicorn)
if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    PYEXE=python3
elif python -c "import fastapi, uvicorn" 2>/dev/null; then
    PYEXE=python
else
    PYEXE=python3
    echo "[SELA Desktop] PERINGATAN: fastapi/uvicorn belum terpasang."
    echo "                Jalankan: pip install -r ai-engine/requirements.txt"
fi
echo "[SELA Desktop] Interpreter Python: $PYEXE"

# 3. Jalankan Mesin AI Offline
echo "[SELA Desktop] Menjalankan Mesin AI Offline (Port 8008)..."
"$PYEXE" ai-engine/server.py &
PID_AI=$!

cleanup() {
    echo "[SELA Desktop] Menghentikan server AI..."
    kill "$PID_AI" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 3

# 3. Jalankan Aplikasi Desktop
echo "[SELA Desktop] Meluncurkan aplikasi desktop..."
npm run dev -- --open
