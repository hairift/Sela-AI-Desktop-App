# Sela-AI-Desktop-App

SELA AI Desktop - AI Receptionist and Campus Customer Service UCIC.

## Tampilan

![Tampilan antarmuka SELA AI Desktop](docs/tangkapan-layar.png)

## Struktur
- `src/` - Frontend React + Vite
- `electron/` - Electron main process
- `ai-engine/` - Python backend (ASR streaming, LLM, TTS, RAG)
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

## Mesin AI
| Bagian | Mesin | Keterangan |
| --- | --- | --- |
| Otak bahasa | Qwen3.5-4B (GGUF) | Offline, `enable_thinking: false` agar menjawab langsung |
| Suara (TTS) | **Supertonic 3** (ONNX) | 31 bahasa termasuk Indonesia, 10 tag ekspresi |
| Pendengaran (ASR) | **sherpa-onnx streaming zipformer** | Ucapan jadi teks **kata per kata** saat berbicara |
| Pencarian fakta | BM25 + gerbang cakupan IDF | Mesin utama RAG anti-halusinasi |
| Penguat makna | **multilingual-e5-small** (384 dim) | Opsional, memperkuat pencocokan parafrase |

## Model AI
Folder model (`models/`, `ai-engine/models/`) sengaja tidak di-push ke GitHub karena ukurannya besar.

Jalankan skrip persiapan model untuk mengunduh ulang:

```bash
py -3.12 ai-engine/persiapan_model.py --unduh-semua   # embedder + ASR + TTS
py -3.12 ai-engine/persiapan_model.py                 # cek kelengkapan saja
```

| Model | Ukuran | Perintah |
| --- | --- | --- |
| LLM Qwen3.5-4B GGUF | 2,8 GB | taruh manual di `ai-engine/models/` |
| TTS Supertonic 3 | 396 MB | `--unduh-tts` |
| ASR streaming zipformer | 340 MB | `--unduh-asr` |
| Embedder multilingual-e5-small | 493 MB | `--unduh-embedder` |
