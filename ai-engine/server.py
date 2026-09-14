"""
SELA AI Desktop - Server Backend AI Lokal (FastAPI + WebSocket Full-Duplex)
===========================================================================
Satu-satunya titik masuk backend. Merangkai seluruh mesin SELA:

- core.llm_engine  : LLM tunggal (llama-cpp-python, GGUF langsung, singleton)
- core.stt_engine  : STT tunggal (faster-whisper, 100% memori, tanpa file tmp)
- core.tts_engine  : TTS tunggal (Piper, singleton, audio di memori)
- core.vad_engine  : VAD untuk barge-in (FastRTC Silero atau cadangan energi)
- rag             : RAG anti-halusinasi (retriever leksikal BM25 + gerbang
                    cakupan IDF; diperkuat bge-m3/FAISS bila tersedia)
- tools           : campus_tool (RAG UCIC), web_search_tool, curhat_tool
- prompts         : seluruh system prompt terpusat

Backend adalah OTAK TUNGGAL: seluruh retrieval, routing niat, web search, dan
penyusunan prompt terjadi di sini. Frontend hanya mengirim pertanyaan + riwayat.

Kontrak antarmuka dengan frontend (React) DIPERTAHANKAN:
  POST /api/chat, /api/transcribe, /api/transkripsi, /api/sintesis,
       /api/web-search, /api/status-asr, /api/status-tts
  GET  /kesehatan, /api/user/*, /api/mcp/*
  WS   /ws/asr-stream, /ws/dupleks   (barge-in via VAD)

Jalankan:  python ai-engine/server.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import sys
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import uvicorn

# Pastikan folder ai-engine ada di path agar impor paket lokal selalu berhasil.
_AKAR_AI = os.path.dirname(os.path.abspath(__file__))
if _AKAR_AI not in sys.path:
    sys.path.insert(0, _AKAR_AI)

from core import dapatkan_llm, dapatkan_stt, dapatkan_tts, dapatkan_vad  # noqa: E402
from prompts import (  # noqa: E402
    MASTER_PERSONA,
    instruksi_tanya_nama,
    pesan_sistem_curhat,
    pesan_sistem_kampus,
    pesan_sistem_umum,
    pesan_sistem_web,
    sapaan_variatif,
)
from tools import (  # noqa: E402
    dapatkan_campus_tool,
    dapatkan_curhat_tool,
    dapatkan_web_search,
)
from pengenal_user import PengenalUser  # noqa: E402
from klien_mcp import KlienMcp  # noqa: E402

# ── Inisialisasi aplikasi ─────────────────────────────────────────────────────
aplikasi_server = FastAPI(
    title="SELA AI Desktop Engine",
    description="Backend AI mandiri offline Universitas Catur Insan Cendekia (UCIC)",
    version="2.0.0",
)
aplikasi_server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("[Server AI] Memuat mesin AI offline...")
llm = dapatkan_llm()
stt = dapatkan_stt()
tts = dapatkan_tts()
vad = dapatkan_vad()
alat_kampus = dapatkan_campus_tool()
alat_web = dapatkan_web_search()
alat_curhat = dapatkan_curhat_tool()
pengenal_user = PengenalUser()
klien_mcp = KlienMcp()
# Ringkasan RAG untuk log: tanpa bge-m3 jalur vektor memang dilewati (total_chunk
# tetap 0), jadi yang dilaporkan adalah jumlah dokumen leksikal yang benar-benar siap.
_ringkasan_rag = (
    f"{alat_kampus.total_dokumen} dokumen + {alat_kampus.total_chunk} chunk"
    if alat_kampus.total_chunk
    else f"{alat_kampus.total_dokumen} dokumen (leksikal BM25)"
)
print(f"[Server AI] Siap. LLM={'ok' if llm.apakah_siap else 'off'} "
      f"STT={'ok' if stt.apakah_siap else 'off'} TTS={'ok' if tts.apakah_siap else 'off'} "
      f"RAG={_ringkasan_rag} VAD={vad.metode_aktif}")
klien_mcp.mulai()


# ── Skema REST ────────────────────────────────────────────────────────────────
class PermintaanObrolan(BaseModel):
    pesan_pengguna: Optional[str] = None
    riwayat_obrolan: Optional[List[Dict[str, str]]] = []
    bahasa: Optional[str] = "id"


class PermintaanSintesis(BaseModel):
    teks_kalimat: str
    bahasa: Optional[str] = "id"


class PermintaanWebSearch(BaseModel):
    query: str


class PermintaanUser(BaseModel):
    nama: Optional[str] = None


# ── Orkestrasi: pilih jalur & susun pesan untuk LLM ───────────────────────────
def _riwayat_bersih(riwayat: Optional[List[Dict[str, str]]], kueri: str) -> List[Dict[str, str]]:
    """Ambil maksimal empat giliran terakhir, tanpa duplikasi & tanpa system."""
    hasil: List[Dict[str, str]] = []
    kueri_norm = " ".join((kueri or "").lower().split())
    for pesan in riwayat or []:
        peran = pesan.get("role", "user")
        teks = (pesan.get("text") or pesan.get("content") or "").strip()
        if not teks or peran == "system":
            continue
        if peran == "user" and " ".join(teks.lower().split()) == kueri_norm:
            continue
        if hasil and hasil[-1]["role"] == peran and hasil[-1]["content"] == teks:
            continue
        hasil.append({"role": "assistant" if peran == "assistant" else "user", "content": teks})
    return hasil[-4:]


# Kata kunci penanda topik kampus. Dipakai untuk memutuskan apakah pertanyaan
# yang tidak ditemukan di dataset harus dijawab jujur sebagai "belum ada data"
# (topik kampus) atau dijawab sebagai pertanyaan umum lalu diarahkan ke UCIC.
_KATA_KAMPUS = re.compile(
    r"\b(ucic|cic|kampus|kuliah|mahasiswa|pendaftaran|mendaftar|daftar|biaya|"
    r"ukt|spp|beasiswa|kip|jurusan|prodi|program\s+studi|dosen|kurikulum|"
    r"fakultas|fti|feb|fps|dkv|informatika|manajemen|akuntansi|bisnis|"
    r"perpustakaan|lab|laboratorium|kelas|semester|akreditasi|rektor|alumni|"
    r"asrama|syarat|jadwal|pmb|gedung|fasilitas|krs|skripsi|yudisium|wisuda|"
    r"karier|prospek|lulusan|mata\s+kuliah)\b",
    re.IGNORECASE,
)


def apakah_topik_kampus(kueri: str) -> bool:
    """True bila pertanyaan jelas menyangkut kampus UCIC."""
    return bool(_KATA_KAMPUS.search(kueri or ""))


# ── Gerakan animasi 3D ────────────────────────────────────────────────────────
# Nama gerakan HARUS sama persis dengan nama animasi di public/models/sela.glb:
# Confused, Goodbye, Greeting, Idle, Nodding, Shaking Head, Talking, Thinking.
def tentukan_gerakan(jalur: str, intent: Optional[str] = None) -> str:
    """
    Pilih gerakan avatar yang cocok dengan sifat jawaban.

    Gerakan ini diputar SEKALI di awal jawaban oleh frontend, lalu dilanjutkan
    animasi latar (Talking saat berbicara, Thinking saat memproses, Idle saat diam).
    """
    if jalur == "intent":
        return {
            "sapaan": "Greeting",
            "identitas": "Greeting",
            "terima_kasih": "Nodding",
            "penutup": "Goodbye",
        }.get(intent or "", "Nodding")
    if jalur == "kampus_kosong":
        # Data resmi tidak memuat jawabannya -> geleng kepala (jujur, bukan mengarang).
        return "Shaking Head"
    if jalur == "umum":
        # Pertanyaan di luar kampus -> ekspresi bingung lalu diarahkan ke UCIC.
        return "Confused"
    # kampus / web / curhat: mengangguk sambil menyampaikan informasi.
    return "Nodding"



def susun_rencana(kueri: str, riwayat: Optional[List[Dict[str, str]]], bahasa: str) -> Dict[str, Any]:
    """
    Tentukan jalur jawaban (intent / curhat / web / kampus) lalu susun daftar
    pesan siap dikirim ke LLM. Mengembalikan dict rencana.
    """
    kueri = (kueri or "").strip()
    riwayat_bersih = _riwayat_bersih(riwayat, kueri)

    # 0. Simpan nama pengguna bila disebutkan.
    nama = pengenal_user.ekstrak_nama_dari_pesan(kueri)
    if nama:
        pengenal_user.simpan_nama(nama)

    konteks_user = pengenal_user.dapatkan_konteks_user()

    # 1. Niat percakapan cepat (sapaan / identitas / terima kasih / penutup).
    intent = alat_kampus.deteksi_intent(kueri)
    if intent is not None:
        jawaban = intent["jawaban"]
        if intent["intent"] == "sapaan":
            jawaban = sapaan_variatif(bahasa)
            if not pengenal_user.apakah_dikenal():
                jawaban += " Sebelum lanjut, boleh kenalan dulu? Nama kamu siapa?"
        return {
            "jalur": "intent",
            "intent": intent["intent"],
            "jawaban_langsung": jawaban,
            "pesan": [],
            "dokumen": [],
            "ditemukan": True,
        }

    # 2. Mode curhat (empatik).
    curhat = alat_curhat.deteksi(kueri)
    if curhat is not None:
        catatan = curhat.get("catatan", "")
        if pengenal_user.nama_user:
            catatan = f"Pengguna bernama {pengenal_user.nama_user}. {catatan}"
        sistem = pesan_sistem_curhat(catatan, kueri)
        return {
            "jalur": "curhat",
            "jawaban_langsung": alat_curhat.jawab(kueri, pengenal_user.nama_user),
            "pesan": [{"role": "system", "content": sistem}] + riwayat_bersih
                     + [{"role": "user", "content": kueri}],
            "dokumen": [],
            "ditemukan": True,
        }

    # 3. RAG kampus (anti-halusinasi) — didahulukan agar pertanyaan kampus
    #    selalu dijawab dari data resmi, bukan dari tebakan.
    konteks, dokumen, ditemukan = alat_kampus.cari(kueri, riwayat)
    if ditemukan:
        sistem = pesan_sistem_kampus(konteks, kueri)
        if konteks_user:
            sistem += f"\n\nKONTEKS PENGGUNA:\n{konteks_user}"
        if not pengenal_user.apakah_dikenal() and pengenal_user.deteksi_kebutuhan_nama(kueri):
            sistem += f"\n\n{instruksi_tanya_nama()}"
        return {
            "jalur": "kampus",
            "jawaban_langsung": None,
            "pesan": [{"role": "system", "content": sistem}] + riwayat_bersih
                     + [{"role": "user", "content": kueri}],
            "dokumen": dokumen,
            "ditemukan": True,
        }

    # 4. Informasi real-time di luar data kampus -> web search.
    if alat_web.perlu_web_search(kueri):
        hasil_web = alat_web.cari(kueri, bahasa)
        if hasil_web.get("ditemukan"):
            sistem = pesan_sistem_web(hasil_web["konteks"], kueri)
            return {
                "jalur": "web",
                "jawaban_langsung": None,
                "pesan": [{"role": "system", "content": sistem}] + riwayat_bersih
                         + [{"role": "user", "content": kueri}],
                "dokumen": [],
                "ditemukan": True,
            }

    # 5. Topik kampus tetapi belum tercatat di data resmi -> jawab jujur.
    if apakah_topik_kampus(kueri):
        sistem = pesan_sistem_kampus("INFORMASI_TIDAK_TERSEDIA_DI_DATASET", kueri)
        if konteks_user:
            sistem += f"\n\nKONTEKS PENGGUNA:\n{konteks_user}"
        return {
            "jalur": "kampus_kosong",
            "jawaban_langsung": None,
            "pesan": [{"role": "system", "content": sistem}] + riwayat_bersih
                     + [{"role": "user", "content": kueri}],
            "dokumen": [],
            "ditemukan": False,
        }

    # 6. Pertanyaan umum di luar kampus -> jawab singkat lalu arahkan ke UCIC.
    sistem = pesan_sistem_umum(kueri)
    if konteks_user:
        sistem += f"\n\nKONTEKS PENGGUNA:\n{konteks_user}"
    return {
        "jalur": "umum",
        "jawaban_langsung": None,
        "pesan": [{"role": "system", "content": sistem}] + riwayat_bersih
                 + [{"role": "user", "content": kueri}],
        "dokumen": [],
        "ditemukan": False,
    }


def _bersihkan_teks(teks: str) -> str:
    """Buang tag template bocor, baris/kalimat duplikat, dan spasi ganda."""
    if not teks:
        return teks
    teks = re.sub(r"<\|im_start\|>.*?<\|im_end\|>", "", teks, flags=re.DOTALL)
    teks = re.sub(r"<\|im_(start|end)\|>", "", teks)
    baris_bersih: List[str] = []
    for b in teks.split("\n"):
        if b.strip() and (not baris_bersih or b.strip() != baris_bersih[-1].strip()):
            baris_bersih.append(b)
    teks = "\n".join(baris_bersih)
    kalimat = re.findall(r"[^.!?]*[.!?]\s*", teks) or [teks]
    sisa = teks[len("".join(kalimat)):]
    if sisa.strip():
        kalimat.append(sisa)
    hasil: List[str] = []
    terlihat = set()
    for k in kalimat:
        k_bersih = k.strip()
        if not k_bersih:
            continue
        k_norm = re.sub(r"[^\w]+", " ", k_bersih.lower()).strip()
        if k_norm in terlihat:
            continue
        terlihat.add(k_norm)
        hasil.append(k)
    teks = "".join(hasil)
    teks = re.sub(r" {2,}", " ", teks)
    teks = re.sub(r"\n{3,}", "\n\n", teks)
    return teks.strip()


def _jawab_langsung(rencana: Dict[str, Any], kueri: str) -> str:
    """Jawaban cadangan deterministik bila LLM belum siap."""
    if rencana.get("jawaban_langsung"):
        return rencana["jawaban_langsung"]
    dokumen = rencana.get("dokumen") or []
    if rencana["jalur"] == "web":
        return (
            "Maaf, hasil pencarian real-time belum bisa diringkas saat ini. "
            "Coba kirim pertanyaannya sekali lagi ya."
        )
    if dokumen:
        return dokumen[0].get("teks", "")[:1200]
    return (
        "Untuk pertanyaan itu, informasinya belum tercatat di basis data resmi kami. "
        "Silakan hubungi Admin PMB UCIC melalui WhatsApp 0812 1670 0519 "
        "atau kunjungi pmb.cic.ac.id ya."
    )


def _kumpulkan_jawaban(pesan: List[Dict[str, str]]) -> str:
    """Jalankan LLM tanpa streaming, kumpulkan menjadi satu teks."""
    return "".join(llm.chat_stream(pesan)).strip()


# ── Endpoint kesehatan ────────────────────────────────────────────────────────
@aplikasi_server.get("/kesehatan")
async def cek_kesehatan():
    info_rag = alat_kampus.info()
    return {
        "status": "sehat",
        "mesin_rag": True,
        "total_dokumen_rag": alat_kampus.total_dokumen,
        "total_chunk_rag": alat_kampus.total_chunk,
        "retriever_leksikal": info_rag.get("retriever_leksikal", {}).get("metode"),
        "embedder": alat_kampus.rag.embedder.metode,
        "semantik_aktif": info_rag.get("semantik_aktif", False),
        "vector_store": alat_kampus.rag.store.metode if alat_kampus.rag.store else None,
        "model_llm_tersedia": llm.apakah_siap,
        "model_llm_aktif": llm.info().get("model"),
        "model_whisper_tersedia": stt.apakah_siap,
        "model_whisper_aktif": stt.nama_model_aktif,
        "tts_siap": tts.apakah_siap,
        "tts_engine": "Piper ONNX (singleton)",
        "vad_metode": vad.metode_aktif,
    }


# ── Obrolan REST ──────────────────────────────────────────────────────────────
@aplikasi_server.post("/api/chat")
async def proses_obrolan_rest(data_mentah: dict):
    """
    Obrolan REST. Backend adalah OTAK TUNGGAL: seluruh RAG, routing niat,
    web search, dan penyusunan prompt dilakukan di sini.

    System prompt yang mungkin masih dikirim frontend DIABAIKAN dengan sengaja.
    Sebelumnya frontend membangun konteks RAG sendiri (Fuse.js) dan menandainya
    dengan "[KONTEKS KAMPUS]", sehingga backend melewati RAG-nya dan jawaban
    ditentukan oleh dua mesin sekaligus. Kini hanya satu sumber kebenaran.
    """
    kueri = (data_mentah.get("userQuery") or data_mentah.get("pesan_pengguna") or "").strip()
    riwayat = data_mentah.get("riwayat_obrolan") or data_mentah.get("messages") or []
    bahasa = data_mentah.get("bahasa") or data_mentah.get("lang") or "id"

    if not kueri:
        for pesan in reversed(riwayat):
            if pesan.get("role") == "user":
                kueri = (pesan.get("content") or "").strip()
                break

    rencana = await run_in_threadpool(susun_rencana, kueri, riwayat, bahasa)

    if rencana["jalur"] == "intent" and rencana.get("jawaban_langsung"):
        jawaban = rencana["jawaban_langsung"]
    elif llm.apakah_siap and rencana.get("pesan"):
        jawaban = await run_in_threadpool(_kumpulkan_jawaban, rencana["pesan"])
    else:
        jawaban = _jawab_langsung(rencana, kueri)

    jawaban = _bersihkan_teks(jawaban)
    dokumen = rencana.get("dokumen") or []
    jalur = rencana.get("jalur")
    return {
        "text": jawaban,
        "teks": jawaban,
        "apakah_ditemukan": bool(rencana.get("ditemukan")),
        "jalur": jalur,
        "gerakan": tentukan_gerakan(jalur, rencana.get("intent")),
        "dokumen_rujukan": [
            {"judul": d.get("judul", ""), "kategori": d.get("kategori", "")} for d in dokumen
        ],
        "web_search_digunakan": jalur == "web",
        "user_dikenal": pengenal_user.apakah_dikenal(),
        "nama_user": pengenal_user.nama_user,
    }


# ── Transkripsi (STT) ─────────────────────────────────────────────────────────
@aplikasi_server.post("/api/transcribe")
async def transkripsi_rest(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    bahasa_efektif = lang or bahasa or "id"
    konten = await file.read()
    hasil = await run_in_threadpool(stt.transkripsikan_bytes, konten, bahasa_efektif)
    teks = hasil.get("teks", "")
    return {
        "text": teks,
        "teks": teks,
        "sukses": hasil.get("sukses", True),
        "durasi": hasil.get("durasi", 0),
        "bahasa": hasil.get("bahasa", bahasa_efektif),
    }


@aplikasi_server.post("/api/transkripsi")
async def transkripsi_rest_alias(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    return await transkripsi_rest(file=file, lang=lang, bahasa=bahasa)


@aplikasi_server.get("/api/status-asr")
async def status_asr():
    return {
        "apakah_siap": stt.apakah_siap,
        "nama_model": stt.nama_model_aktif,
        "perangkat": stt.perangkat_aktif,
    }


# ── Sintesis (TTS) ────────────────────────────────────────────────────────────
@aplikasi_server.post("/api/sintesis")
async def sintesis_rest(data: PermintaanSintesis):
    return await tts.sintesis_base64_async(data.teks_kalimat, data.bahasa or "id")


@aplikasi_server.get("/api/status-tts")
async def status_tts():
    return tts.status_engine()


# ── Web search ────────────────────────────────────────────────────────────────
@aplikasi_server.post("/api/web-search")
async def web_search_rest(data: PermintaanWebSearch):
    return await run_in_threadpool(alat_web.cari, data.query, "id")


# ── MCP ───────────────────────────────────────────────────────────────────────
@aplikasi_server.get("/api/mcp/status")
async def status_mcp():
    return klien_mcp.status()


@aplikasi_server.post("/api/mcp/kirim")
async def kirim_mcp(data: dict):
    return {"terkirim": klien_mcp.kirim_pesan(data.get("pesan", ""), data.get("target", "broadcast"))}


@aplikasi_server.get("/api/mcp/pesan-masuk")
async def pesan_masuk_mcp():
    pesan = klien_mcp.ambil_pesan_masuk()
    return {"pesan": pesan, "jumlah": len(pesan)}


# ── Memori pengguna ───────────────────────────────────────────────────────────
@aplikasi_server.get("/api/user/status")
async def status_user():
    return {"dikenal": pengenal_user.apakah_dikenal(), "nama": pengenal_user.nama_user}


@aplikasi_server.post("/api/user/simpan-nama")
async def simpan_nama(data: PermintaanUser):
    if data.nama:
        pengenal_user.simpan_nama(data.nama)
    return {"sukses": True, "nama": pengenal_user.nama_user}


@aplikasi_server.get("/api/user/konteks")
async def konteks_user():
    return {"konteks": pengenal_user.dapatkan_konteks_user()}


# ── WebSocket ASR streaming ───────────────────────────────────────────────────
@aplikasi_server.websocket("/ws/asr-stream")
async def ws_asr_streaming(koneksi: WebSocket):
    """Streaming audio ke teks. Buffer hanya di memori, tanpa file tmp."""
    await koneksi.accept()
    print("[WS ASR] Klien terhubung.")
    penyangga = bytearray()
    bahasa_aktif = "id"
    batas = 8 * 1024 * 1024
    try:
        while True:
            pesan = await koneksi.receive()
            if pesan.get("bytes"):
                if len(penyangga) < batas:
                    penyangga.extend(pesan["bytes"])
                await koneksi.send_json({"tipe": "parsial", "ukuran_bytes": len(penyangga)})
                continue
            if not pesan.get("text"):
                continue
            try:
                paket = json.loads(pesan["text"])
            except Exception:
                continue
            tipe = paket.get("tipe", "")
            bahasa_aktif = paket.get("bahasa") or paket.get("lang") or bahasa_aktif
            if tipe == "batal":
                penyangga.clear()
                await koneksi.send_json({"tipe": "dibatalkan"})
            elif tipe == "selesai":
                if len(penyangga) < 1000:
                    await koneksi.send_json({"tipe": "hasil", "teks": "", "sukses": True})
                else:
                    loop = asyncio.get_running_loop()
                    hasil = await loop.run_in_executor(
                        None, stt.transkripsikan_bytes, bytes(penyangga), bahasa_aktif
                    )
                    await koneksi.send_json(
                        {
                            "tipe": "hasil",
                            "teks": hasil.get("teks", ""),
                            "sukses": hasil.get("sukses", True),
                            "bahasa": hasil.get("bahasa", bahasa_aktif),
                        }
                    )
                penyangga.clear()
    except WebSocketDisconnect:
        print("[WS ASR] Klien memutuskan koneksi.")
    except Exception as galat:
        print(f"[WS ASR] Kendala: {galat}")


# ── WebSocket Full-Duplex + Barge-In VAD ──────────────────────────────────────
@aplikasi_server.websocket("/ws/dupleks")
async def ws_dupleks(koneksi: WebSocket):
    """
    Koneksi full-duplex:
    - Klien mengirim {"tipe":"tanya","kueri","riwayat","bahasa"}.
    - Server mengalirkan {"tipe":"potongan_teks"} dan {"tipe":"potongan_audio"}
      per kalimat, lalu {"tipe":"selesai"}.
    - Barge-in: klien boleh mengirim {"tipe":"interupsi"}, atau mengirim bingkai
      audio {"tipe":"audio_frame","pcm_base64"} sehingga VAD mendeteksi
      SPEECH_START saat TTS berbunyi dan server membatalkan tugas LLM & TTS.
    """
    await koneksi.accept()
    print("[WS Dupleks] Klien terhubung.")

    tugas_generasi: Optional[asyncio.Task] = None
    tugas_tts: Optional[asyncio.Task] = None
    dibatalkan = asyncio.Event()
    vad.reset()

    async def batalkan_semua(alasan: str):
        nonlocal tugas_generasi, tugas_tts
        dibatalkan.set()
        for nama, tugas in (("llm", tugas_generasi), ("tts", tugas_tts)):
            if tugas and not tugas.done():
                tugas.cancel()
                print(f"[WS Dupleks] Tugas {nama} dibatalkan ({alasan}).")
        tugas_generasi = None
        tugas_tts = None

    async def alirkan(kueri: str, riwayat: list, bahasa: str):
        nonlocal tugas_tts
        try:
            rencana = await run_in_threadpool(susun_rencana, kueri, riwayat, bahasa)
            await koneksi.send_json(
                {
                    "tipe": "mulai_menjawab",
                    "kueri": kueri,
                    "jalur": rencana["jalur"],
                    "dokumen_rujukan": [
                        {"judul": d["judul"], "kategori": d["kategori"]}
                        for d in rencana.get("dokumen", [])
                    ],
                }
            )

            # Jalur niat cepat: langsung kirim jawaban + audio.
            if rencana["jalur"] == "intent" and rencana.get("jawaban_langsung"):
                kalimat_list = [
                    {"teks": s}
                    for s in re.split(r"(?<=[.!?])\s+", rencana["jawaban_langsung"]) if s.strip()
                ]
            elif llm.apakah_siap and rencana.get("pesan"):
                kalimat_list = []
                loop = asyncio.get_running_loop()
                antrean: asyncio.Queue = asyncio.Queue()

                def _produksi():
                    for item in llm.stream_per_kalimat(rencana["pesan"]):
                        loop.call_soon_threadsafe(antrean.put_nowait, item)
                    loop.call_soon_threadsafe(antrean.put_nowait, None)

                threading.Thread(target=_produksi, daemon=True).start()
                while True:
                    item = await antrean.get()
                    if item is None:
                        break
                    kalimat_list.append(item)
            else:
                jawaban = _jawab_langsung(rencana, kueri)
                kalimat_list = [
                    {"teks": s} for s in re.split(r"(?<=[.!?])\s+", jawaban) if s.strip()
                ]

            teks_terkumpul: List[str] = []
            for item in kalimat_list:
                if dibatalkan.is_set():
                    print("[WS Dupleks] Aliran dihentikan oleh barge-in.")
                    return
                kalimat = item["teks"]
                teks_terkumpul.append(kalimat)
                await koneksi.send_json({"tipe": "potongan_teks", "kalimat": kalimat})

                tugas_tts = asyncio.create_task(tts.sintesis_base64_async(kalimat, bahasa))
                try:
                    hasil_audio = await tugas_tts
                except asyncio.CancelledError:
                    print("[WS Dupleks] TTS dibatalkan saat barge-in.")
                    return
                finally:
                    tugas_tts = None

                if dibatalkan.is_set():
                    return
                if hasil_audio and hasil_audio.get("audio_base64"):
                    await koneksi.send_json(
                        {
                            "tipe": "potongan_audio",
                            "kalimat": kalimat,
                            "audio_base64": hasil_audio["audio_base64"],
                            "format": hasil_audio.get("format", "audio/wav"),
                            "engine": hasil_audio.get("engine"),
                            "bahasa": hasil_audio.get("bahasa", "id"),
                        }
                    )
                else:
                    await koneksi.send_json(
                        {"tipe": "status_tts_gagal", "kalimat": kalimat, "engine": "piper-unavailable"}
                    )
                await asyncio.sleep(0.01)

            if not dibatalkan.is_set():
                await koneksi.send_json(
                    {
                        "tipe": "selesai",
                        "teks_penuh": _bersihkan_teks(" ".join(teks_terkumpul)),
                        "dokumen_rujukan": [
                            {"judul": d["judul"], "kategori": d["kategori"]}
                            for d in rencana.get("dokumen", [])
                        ],
                    }
                )
        except asyncio.CancelledError:
            print("[WS Dupleks] Tugas generasi dibatalkan.")
            raise

    try:
        while True:
            mentah = await koneksi.receive_text()
            try:
                paket = json.loads(mentah)
            except Exception:
                continue
            tipe = paket.get("tipe", "")

            if tipe == "interupsi":
                await batalkan_semua("sinyal interupsi klien")
                await koneksi.send_json({"tipe": "interupsi_berhasil"})
                continue

            if tipe == "audio_frame":
                # Barge-in berbasis VAD: hanya jika sedang ada generasi berjalan.
                try:
                    pcm = base64.b64decode(paket.get("pcm_base64", ""))
                except Exception:
                    pcm = b""
                peristiwa = vad.proses_bingkai(pcm) if pcm else None
                if peristiwa == "SPEECH_START" and (tugas_generasi or tugas_tts):
                    await batalkan_semua("VAD mendeteksi SPEECH_START")
                    await koneksi.send_json({"tipe": "barge_in", "alasan": "speech_start"})
                continue

            if tipe == "tanya":
                kueri = (paket.get("kueri") or "").strip()
                if not kueri:
                    continue
                await batalkan_semua("pertanyaan baru")
                dibatalkan = asyncio.Event()
                vad.reset()
                tugas_generasi = asyncio.create_task(
                    alirkan(kueri, paket.get("riwayat", []), paket.get("bahasa", "id"))
                )
                continue

    except WebSocketDisconnect:
        print("[WS Dupleks] Klien memutuskan koneksi.")
    except Exception as galat:
        print(f"[WS Dupleks] Kendala: {galat}")
    finally:
        await batalkan_semua("koneksi ditutup")


# ── (Opsional) FastRTC Stream ─────────────────────────────────────────────────
def _coba_pasang_fastrtc(app: FastAPI) -> None:
    """Pasang FastRTC Stream bila paketnya tersedia. Gagal dengan aman bila tidak."""
    try:
        import fastrtc  # noqa: F401
    except Exception:
        print("[Server AI] FastRTC tidak terpasang; streaming memakai WebSocket /ws/dupleks.")
        return
    try:
        from fastrtc import Stream  # type: ignore

        def _penangan(audio):
            return audio

        aliran = Stream(handler=_penangan, modality="audio", mode="send-receive")
        aliran.mount(app)
        print("[Server AI] FastRTC Stream berhasil dipasang.")
    except Exception as galat:
        print(f"[Server AI] FastRTC ada tetapi gagal dipasang ({galat}); memakai /ws/dupleks.")


_coba_pasang_fastrtc(aplikasi_server)


# ── Berkas statis frontend ────────────────────────────────────────────────────
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")

jalur_dist = os.path.abspath(os.path.join(_AKAR_AI, "..", "dist"))
if os.path.exists(jalur_dist):
    print(f"[Server AI] Memasang antarmuka dari: {jalur_dist}")
    aplikasi_server.mount("/", StaticFiles(directory=jalur_dist, html=True), name="antarmuka")
else:
    print(f"[Server AI] Folder antarmuka belum ada di {jalur_dist}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT_SELA_AI", 8008))
    print(f"[Server AI] Menjalankan FastAPI di http://127.0.0.1:{port}")
    uvicorn.run(aplikasi_server, host="127.0.0.1", port=port, log_level="info")
