"""
SELA AI Desktop - Server Backend AI Lokal & Full-Duplex WebSocket
Menyediakan antarmuka komunikasi ultra-low latency antara aplikasi desktop dan modul AI offline:
RAG Anti-Halusinasi, Pemroses LLM GGUF, Whisper ASR, dan Sintesis Suara Voice Cloning.
"""

import os
import sys
import json
import asyncio
import base64
import mimetypes
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Impor modul AI lokal yang telah dibuat
from mesin_rag import MesinRagOffline
from pemroses_llm import PemrosesLlmOffline
from pengenal_suara import PengenalSuaraOffline
from sintesis_suara import SintesisSuaraOffline

# Inisialisasi Aplikasi FastAPI
aplikasi_server = FastAPI(
    title="SELA AI Desktop Engine",
    description="Backend AI Mandiri Offline Universitas Catur Insan Cendekia (UCIC)",
    version="1.0.0",
)

# Konfigurasi CORS agar dapat diakses oleh Vite dev server dan Electron
aplikasi_server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inisialisasi komponen-komponen AI offline
print("[Server AI] Memuat komponen-komponen AI offline lokal...")
mesin_rag = MesinRagOffline()
pemroses_llm = PemrosesLlmOffline()
pengenal_suara = PengenalSuaraOffline(ukuran_model="small")
sintesis_suara = SintesisSuaraOffline()
print("[Server AI] Seluruh modul AI lokal siap!")


# ── Model Skema Data REST API ──────────────────────────────────────────────────

class PermintaanObrolan(BaseModel):
    pesan_pengguna: str
    riwayat_obrolan: Optional[List[Dict[str, str]]] = []
    bahasa: Optional[str] = "id"


class PermintaanSintesis(BaseModel):
    teks_kalimat: str
    bahasa: Optional[str] = "id"


# ── Endpoint REST API ─────────────────────────────────────────────────────────

@aplikasi_server.get("/kesehatan")
async def cek_kesehatan_server():
    """Endpoint pemantauan kesehatan server untuk Electron pengelola proses."""
    return {
        "status": "sehat",
        "mesin_rag": True,
        "total_dokumen_rag": mesin_rag.total_dokumen,
        "model_llm_tersedia": pemroses_llm.apakah_siap,
        "model_whisper_tersedia": pengenal_suara.apakah_siap,
        "model_whisper_aktif": getattr(pengenal_suara, "nama_model_aktif", ""),
        "tts_siap": sintesis_suara.apakah_siap,
        "tts_engine": "piper-female-natural + higgs-tts2-feminine (voice cloning dihapus)",
        "sampel_suara_kloning": len(sintesis_suara.daftar_sampel_audio),
    }


@aplikasi_server.post("/api/chat")
async def proses_obrolan_rest(data_mentah: dict):
    """
    Endpoint pemrosesan obrolan berbasis RAG Anti-Halusinasi dan format kompatibel.
    """
    kueri = data_mentah.get("userQuery") or data_mentah.get("pesan_pengguna") or ""
    if not kueri and "messages" in data_mentah and len(data_mentah["messages"]) > 0:
        pesan_terakhir = data_mentah["messages"][-1]
        kueri = pesan_terakhir.get("content", "")

    riwayat = data_mentah.get("riwayat_obrolan") or data_mentah.get("messages") or []

    # 1. Bangun prompt berpagar fakta ketat dari RAG
    prompt_instruksi = mesin_rag.buat_prompt_instruksi_ketat(kueri, riwayat)
    _, dokumen_rujukan, ditemukan = mesin_rag.bangun_konteks_grounding(kueri)

    # 2. Hasilkan jawaban melalui LLM
    kumpulan_token = []
    for token in pemroses_llm.hasilkan_jawaban_streaming(prompt_instruksi):
        kumpulan_token.append(token)

    jawaban_lengkap = "".join(kumpulan_token).strip()

    return {
        "text": jawaban_lengkap,
        "teks": jawaban_lengkap,
        "apakah_ditemukan": ditemukan,
        "dokumen_rujukan": [
            {"judul": d["judul"], "kategori": d["kategori"]} for d in dokumen_rujukan
        ],
    }


@aplikasi_server.post("/api/transcribe")
async def transkripsi_audio_rest(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    """Endpoint transkripsi suara menjadi teks via Whisper offline."""
    bahasa_efektif = lang or bahasa or "id"
    konten_bytes = await file.read()
    hasil = pengenal_suara.transkripsikan_audio_bytes(konten_bytes, bahasa=bahasa_efektif)
    teks_hasil = hasil.get("teks", "")
    return {
        "text": teks_hasil,
        "teks": teks_hasil,
        "sukses": hasil.get("sukses", True),
    }


@aplikasi_server.post("/api/transkripsi")
async def transkripsi_audio_rest_alias(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    """Alias Bahasa Indonesia untuk /api/transcribe (kompatibilitas frontend lama)."""
    return await transkripsi_audio_rest(file=file, lang=lang, bahasa=bahasa)


@aplikasi_server.post("/api/sintesis")
async def sintesis_audio_rest(data_permintaan: PermintaanSintesis):
    """Endpoint sintesis suara Text-to-Speech offline natural (perempuan ID/EN/Jawa)."""
    hasil = await sintesis_suara.sintesis_teks_ke_audio_base64_async(
        data_permintaan.teks_kalimat, bahasa=data_permintaan.bahasa or "id"
    )
    return hasil


@aplikasi_server.websocket("/ws/asr-stream")
async def websocket_asr_streaming(koneksi_ws: WebSocket):
    """
    WebSocket ASR streaming full-duplex (real-time):
    - Klien mengirim potongan audio biner (WebM/PCM) kapan saja, bahkan saat
      TTS SELA sedang berbunyi (mendukung barge-in / interupsi alami).
    - Klien mengirim teks JSON {"tipe": "selesai", "bahasa": "id"} untuk
      meminta transkripsi seluruh buffer, atau {"tipe": "batal"} untuk
      membuang buffer.
    - Server menjawab {"tipe": "hasil", "teks": ..., "sukses": ...} atau
      {"tipe": "parsial", "ukuran_bytes": ...} sebagai ack tiap chunk.
    """
    await koneksi_ws.accept()
    print("[WebSocket ASR] Klien terhubung (full-duplex)!")
    penyangga_audio = bytearray()
    bahasa_aktif = "id"
    BATAS_PENYANGGA = 8 * 1024 * 1024  # 8 MB failsafe

    try:
        while True:
            pesan = await koneksi_ws.receive()
            if "bytes" in pesan and pesan["bytes"]:
                if len(penyangga_audio) < BATAS_PENYANGGA:
                    penyangga_audio.extend(pesan["bytes"])
                await koneksi_ws.send_json({
                    "tipe": "parsial",
                    "ukuran_bytes": len(penyangga_audio),
                })
                continue
            if "text" not in pesan or not pesan["text"]:
                continue
            try:
                data_paket = json.loads(pesan["text"])
            except Exception:
                continue
            tipe_paket = data_paket.get("tipe", "")
            if "bahasa" in data_paket or "lang" in data_paket:
                bahasa_aktif = data_paket.get("bahasa") or data_paket.get("lang") or bahasa_aktif

            if tipe_paket == "batal":
                penyangga_audio.clear()
                await koneksi_ws.send_json({"tipe": "dibatalkan"})
            elif tipe_paket == "selesai":
                if len(penyangga_audio) < 1000:
                    await koneksi_ws.send_json({"tipe": "hasil", "teks": "", "sukses": True})
                else:
                    loop = asyncio.get_running_loop()
                    hasil = await loop.run_in_executor(
                        None, pengenal_suara.transkripsikan_audio_bytes,
                        bytes(penyangga_audio), bahasa_aktif,
                    )
                    await koneksi_ws.send_json({
                        "tipe": "hasil",
                        "teks": hasil.get("teks", ""),
                        "sukses": hasil.get("sukses", True),
                        "bahasa": hasil.get("bahasa", bahasa_aktif),
                    })
                penyangga_audio.clear()
    except WebSocketDisconnect:
        print("[WebSocket ASR] Klien memutuskan koneksi.")
    except Exception as galat:
        print(f"[WebSocket ASR] Kendala koneksi: {galat}")


# ── WebSocket Full-Duplex (Interaksi Real-Time & Barge-In) ────────────────────

@aplikasi_server.websocket("/ws/dupleks")
async def websocket_full_dupleks(koneksi_ws: WebSocket):
    """
    Koneksi Full-Duplex Real-Time:
    - Mikrofon pengguna selalu aktif streaming.
    - Begitu pengguna berbicara saat audio SELA menyala, sinyal 'interupsi'
      langsung membatalkan generasi audio dan teks SELA secara instan (barge-in).
    - Streaming kalimat demi kalimat ke modul suara tanpa delay.
    """
    await koneksi_ws.accept()
    print("[WebSocket Dupleks] Klien terhubung!")

    # Variabel kontrol pembatalan jika terjadi interupsi (barge-in)
    tugas_generasi_aktif: Optional[asyncio.Task] = None
    apakah_dibatalkan = False

    try:
        while True:
            pesan_mentah = await koneksi_ws.receive_text()
            data_paket = json.loads(pesan_mentah)
            tipe_paket = data_paket.get("tipe", "")

            # 1. Tangani Sinyal Interupsi (Barge-in)
            if tipe_paket == "interupsi":
                apakah_dibatalkan = True
                if tugas_generasi_aktif and not tugas_generasi_aktif.done():
                    tugas_generasi_aktif.cancel()
                    print("[WebSocket Dupleks] Sinyal interupsi (barge-in) diterima! Pemutaran suara SELA dipotong.")
                await koneksi_ws.send_json({"tipe": "interupsi_berhasil"})
                continue

            # 2. Tangani Pertanyaan Teks atau Hasil ASR yang Siap Dijawab
            if tipe_paket == "tanya":
                pertanyaan = data_paket.get("kueri", "").strip()
                riwayat = data_paket.get("riwayat", [])
                bahasa = data_paket.get("bahasa", "id")

                if not pertanyaan:
                    continue

                # Batalkan generasi sebelumnya jika masih berjalan
                if tugas_generasi_aktif and not tugas_generasi_aktif.done():
                    tugas_generasi_aktif.cancel()

                apakah_dibatalkan = False

                # Fungsi asinkron untuk mengalirkan respon dan suara per kalimat
                async def alirkan_respon_dupleks(teks_tanya, riwayat_chat, lang):
                    nonlocal apakah_dibatalkan

                    # Bangun prompt berbasis RAG
                    prompt_instruksi = mesin_rag.buat_prompt_instruksi_ketat(teks_tanya, riwayat_chat)
                    _, dokumen_rujukan, ditemukan = mesin_rag.bangun_konteks_grounding(teks_tanya)

                    # Kirim notifikasi mulai generasi
                    await koneksi_ws.send_json({
                        "tipe": "mulai_menjawab",
                        "kueri": teks_tanya,
                        "dokumen_rujukan": [
                            {"judul": d["judul"], "kategori": d["kategori"]} for d in dokumen_rujukan
                        ],
                    })

                    teks_terkumpul = []

                    # Alirkan per kalimat untuk disintesis suaranya secara paralel
                    for item_kalimat in pemroses_llm.streaming_per_kalimat(prompt_instruksi):
                        if apakah_dibatalkan:
                            print("[WebSocket Dupleks] Generasi dihentikan oleh pengguna.")
                            break

                        kalimat = item_kalimat["teks"]
                        teks_terkumpul.append(kalimat)

                        # Kirim token/kalimat teks ke antarmuka
                        await koneksi_ws.send_json({
                            "tipe": "potongan_teks",
                            "kalimat": kalimat,
                        })

                        # Sintesis audio kalimat ini untuk langsung diputar (zero-latency streaming)
                        hasil_audio = await sintesis_suara.sintesis_teks_ke_audio_base64_async(kalimat, bahasa=lang)
                        await koneksi_ws.send_json({
                            "tipe": "potongan_audio",
                            "kalimat": kalimat,
                            "audio_base64": hasil_audio.get("audio_base64"),
                            "format": hasil_audio.get("format", "audio/mpeg"),
                            "engine": hasil_audio.get("engine"),
                            "bahasa": hasil_audio.get("bahasa", "id-ID"),
                        })

                        # Beri jeda sangat singkat agar event loop dapat menangani interupsi
                        await asyncio.sleep(0.01)

                    if not apakah_dibatalkan:
                        await koneksi_ws.send_json({
                            "tipe": "selesai",
                            "teks_penuh": " ".join(teks_terkumpul),
                        })

                # Jalankan tugas asinkron streaming
                tugas_generasi_aktif = asyncio.create_task(
                    alirkan_respon_dupleks(pertanyaan, riwayat, bahasa)
                )

    except WebSocketDisconnect:
        print("[WebSocket Dupleks] Klien memutuskan koneksi.")
    except Exception as galat:
        print(f"[WebSocket Dupleks] Kendala koneksi: {galat}")


# ── Pemasangan Berkas Statis Antarmuka Frontend Desktop ───────────────────────
# (mimetypes + StaticFiles sudah diimpor di bagian atas berkas)

# Daftarkan tipe MIME untuk model 3D GLTF / GLB agar dikenali browser & Three.js
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")

jalur_dist_frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
if os.path.exists(jalur_dist_frontend):
    print(f"[Server AI] Memasang antarmuka frontend desktop dari: {jalur_dist_frontend}")
    aplikasi_server.mount("/", StaticFiles(directory=jalur_dist_frontend, html=True), name="antarmuka")
else:
    print(f"[Server AI] Peringatan: Folder antarmuka produksi belum ditemukan di {jalur_dist_frontend}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT_SELA_AI", 8008))
    print(f"[Server AI] Memulai server FastAPI di http://127.0.0.1:{port}")
    uvicorn.run(aplikasi_server, host="127.0.0.1", port=port, log_level="info")

