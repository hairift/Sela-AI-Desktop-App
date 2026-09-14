# Sela-AI-Desktop-App

SELA AI Desktop - AI Receptionist and Campus Customer Service UCIC.

## Tampilan

![Tampilan antarmuka SELA AI Desktop](docs/tangkapan-layar.png)

## Struktur
- `src/` - Frontend React + Vite
- `electron/` - Electron main process
- `ai-engine/` - Python backend (Whisper ASR, LLM, Piper TTS, RAG)
- `public/` - Aset statis
- `assets/3d-source/` - Sumber model 3D editable (tidak ikut bundel Vite)
- `docs/` - Tangkapan layar dan dokumentasi

## Cara jalan
```bat
launch_desktop.bat
```
atau
```powershell
.\launch_desktop.ps1
```

## Model AI
Folder model (`models/`, `ai-engine/models/`) sengaja tidak di-push ke GitHub karena ukurannya besar (2.8GB+).
Jalankan script persiapan model di `ai-engine/persiapan_model.py` untuk mengunduh ulang model yang dibutuhkan
(faster-whisper, Piper TTS id_ID & en_US).
