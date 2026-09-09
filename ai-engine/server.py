"""
SELA AI Desktop - Server Backend AI Lokal & Full-Duplex WebSocket
Menyediakan antarmuka komunikasi ultra-low latency antara aplikasi desktop dan modul AI offline:
RAG Anti-Halusinasi, Pemroses LLM GGUF, Whisper ASR, dan Sintesis Suara Voice Cloning.
"""

import os
import sys
import json
import re
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
from pencari_web import PencariWeb
from pengenal_user import PengenalUser
from klien_mcp import KlienMcp

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
pencari_web = PencariWeb()
pengenal_user = PengenalUser()
klien_mcp = KlienMcp()
print("[Server AI] Seluruh modul AI lokal siap!")

# Mulai koneksi MCP di background (komunikasi antar robot kampus)
klien_mcp.mulai()
print("[Server AI] MCP client dimulai untuk komunikasi antar robot kampus.")


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
        "model_llm_aktif": "Qwen 3.5 4B (llama.cpp Vulkan GPU)" if pemroses_llm.apakah_siap else None,
        "model_whisper_tersedia": pengenal_suara.apakah_siap,
        "model_whisper_aktif": getattr(pengenal_suara, "nama_model_aktif", ""),
        "tts_siap": sintesis_suara.apakah_siap,
        "tts_engine": "OmniVoice (k2-fsa) Voice Design Female",
        "sampel_suara_kloning": len(sintesis_suara.daftar_sampel_audio),
    }


@aplikasi_server.post("/api/chat")
async def proses_obrolan_rest(data_mentah: dict):
    """
    Endpoint pemrosesan obrolan berbasis RAG Anti-Halusinasi dan format kompatibel.
    Frontend sudah membangun system prompt + konteks RAG (Fuse.js) yang lengkap.
    Backend menghormati system prompt dari frontend dan MENAMBAH grounding RAG
    backend (BM25) sebagai lapisan verifikasi tambahan, bukan menggantikan.
    Ini mencegah double grounding dan duplikasi teks.
    """
    kueri = data_mentah.get("userQuery") or data_mentah.get("pesan_pengguna") or ""
    messages = data_mentah.get("messages", [])
    if not kueri and messages:
        pesan_terakhir = messages[-1]
        kueri = pesan_terakhir.get("content", "")

    riwayat = data_mentah.get("riwayat_obrolan") or messages or []

    # 1. Bangun grounding RAG backend (untuk verifikasi & dokumen rujukan)
    konteks_grounding, dokumen_rujukan, ditemukan = mesin_rag.bangun_konteks_grounding(kueri, riwayat)

    # 2. Tentukan prompt utama: gunakan system prompt dari frontend jika ada
    #    (frontend sudah menggabungkan RAG Fuse.js + web search + memory user)
    prompt_sistem_frontend = None
    if messages:
        for pesan in messages:
            if pesan.get("role") == "system":
                prompt_sistem_frontend = pesan.get("content", "")
                break

    if prompt_sistem_frontend:
        # Frontend sudah menyusun prompt lengkap - gunakan itu dan tambahkan grounding backend
        prompt_instruksi = _bangun_prompt_gabungan(
            prompt_sistem_frontend, kueri, riwayat,
            konteks_grounding, dokumen_rujukan, ditemukan
        )
    else:
        # Fallback: tidak ada system prompt dari frontend, bangun prompt sendiri
        prompt_instruksi = mesin_rag.buat_prompt_instruksi_dari_konteks(
            kueri, riwayat, konteks_grounding, dokumen_rujukan, ditemukan
        )

    # 3. Cek apakah pertanyaan membutuhkan web search real-time (hanya jika frontend belum melakukannya)
    konteks_web = ""
    if pencari_web.apakah_perlu_web_search(kueri) and "KONTEKS WEB SEARCH" not in (prompt_sistem_frontend or ""):
        try:
            hasil_web = await run_in_threadpool(pencari_web.cari, kueri, "id")
            if hasil_web.get("ditemukan"):
                konteks_web = hasil_web.get("konteks", "")
                # Sisipkan konteks web ke prompt
                if "<|im_start|>assistant\n" in prompt_instruksi:
                    prompt_instruksi = prompt_instruksi.replace(
                        "<|im_start|>assistant\n",
                        f"[KONTEKS WEB SEARCH TAMBAHAN]\n{konteks_web}\n\n<|im_start|>assistant\n",
                    )
        except Exception as galat_web:
            print(f"[Server AI] Web search gagal: {galat_web}")

    # 4. Jika user belum dikenal dan ini sapaan, tambahkan instruksi tanya nama
    #    (hanya jika frontend belum menambahkannya)
    konteks_user = pengenal_user.dapatkan_konteks_user()
    if (not pengenal_user.apakah_dikenal() and
        pengenal_user.deteksi_kebutuhan_nama(kueri) and
        "INSTRUKSI: User belum mengenalkan dirinya" not in (prompt_sistem_frontend or "")):
        konteks_user += (
            "\n\nINSTRUKSI: User belum mengenalkan dirinya. "
            "Setelah menjawab, tanyakan namanya dengan ramah dan natural, "
            "misal: 'Ngomong-ngomong, boleh kenalan? Nama kamu siapa?'"
        )

    # 5. Cek apakah user menyebutkan namanya
    nama_diekstrak = pengenal_user.ekstrak_nama_dari_pesan(kueri)
    if nama_diekstrak:
        pengenal_user.simpan_nama(nama_diekstrak)
        konteks_user = pengenal_user.dapatkan_konteks_user()

    # 6. Sisipkan konteks user ke prompt jika ada dan belum ada
    if konteks_user and "<|im_start|>assistant\n" in prompt_instruksi:
        if "[KONTEKS USER]" not in prompt_instruksi and "[MEMORI USER]" not in prompt_instruksi:
            prompt_instruksi = prompt_instruksi.replace(
                "<|im_start|>assistant\n",
                f"[KONTEKS USER]\n{konteks_user}\n\n<|im_start|>assistant\n",
            )

    # 7. Cek pesan masuk dari MCP (robot kampus lain)
    pesan_mcp = klien_mcp.ambil_pesan_masuk()
    if pesan_mcp:
        ringkasan_mcp = "; ".join(
            f"{p.get('pengirim', 'unknown')}: {p.get('konten', '')[:100]}"
            for p in pesan_mcp[:3]
        )
        if "[INFO DARI ROBOT KAMPUS LAIN]" not in prompt_instruksi:
            prompt_instruksi = prompt_instruksi.replace(
                "<|im_start|>assistant\n",
                f"[INFO DARI ROBOT KAMPUS LAIN]\n{ringkasan_mcp}\n\n<|im_start|>assistant\n",
            )

    # 8. Hasilkan jawaban melalui LLM
    # Tanpa model GGUF, ekstraksi lama membaca beberapa dokumen sekaligus dan
    # dapat menjawab topik yang salah. Gunakan jalur deterministik berbasis
    # kueri + dokumen ranking pertama; ini tetap RAG dan tidak berhalusinasi.
    if not pemroses_llm.apakah_siap:
        jawaban_lengkap = _jawab_tanpa_llm(
            kueri, dokumen_rujukan, konteks_grounding, konteks_web
        )
    else:
        def _generasikan_llm():
            kumpulan = []
            for token in pemroses_llm.hasilkan_jawaban_streaming(prompt_instruksi):
                kumpulan.append(token)
            return "".join(kumpulan).strip()

        jawaban_lengkap = await run_in_threadpool(_generasikan_llm)

    # 9. Bersihkan jawaban dari duplikasi teks
    jawaban_lengkap = _bersihkan_duplikasi_teks(jawaban_lengkap)

    return {
        "text": jawaban_lengkap,
        "teks": jawaban_lengkap,
        "apakah_ditemukan": ditemukan,
        "dokumen_rujukan": [
            {"judul": d["judul"], "kategori": d["kategori"]} for d in dokumen_rujukan
        ],
        "web_search_digunakan": bool(konteks_web),
        "user_dikenal": pengenal_user.apakah_dikenal(),
        "nama_user": pengenal_user.nama_user,
    }


def _bangun_prompt_gabungan(
    prompt_sistem: str, kueri: str, riwayat: list,
    konteks_grounding: str, dokumen_rujukan: list, ditemukan: bool
) -> str:
    """
    Membangun prompt gabungan yang menghormati system prompt dari frontend
    dan menambahkan grounding RAG backend sebagai verifikasi tambahan.
    Menghindari duplikasi konteks.
    """
    # Jika frontend sudah punya konteks, jangan tambahkan lagi
    sudah_ada_konteks = "KONTEKS KAMPUS" in prompt_sistem or "DOKUMEN RESMI" in prompt_sistem

    prompt_lengkap = f"<|im_start|>system\n{prompt_sistem}\n"

    # Tambahkan grounding backend hanya jika belum ada konteks di frontend
    if not sudah_ada_konteks and ditemukan and not konteks_grounding.startswith("INTENT_PERCAKAPAN:"):
        prompt_lengkap += f"\n[GROUNDING TAMBAHAN DARI RAG BACKEND]\n{konteks_grounding}\n"

    prompt_lengkap += "<|im_end|>\n"

    # Tambahkan riwayat obrolan.  Klien lama kadang sudah memasukkan kueri
    # terakhir ke dalam ``riwayat``; jangan menaruh pesan user yang sama dua
    # kali karena model akan menganggapnya sebagai dua pertanyaan berbeda.
    riwayat_bersih = []
    kueri_norm = " ".join(kueri.lower().split())
    for pesan in riwayat or []:
        peran = pesan.get("role", "user")
        teks = (pesan.get("text", "") or pesan.get("content", "")).strip()
        if not teks or peran == "system":
            continue
        teks_norm = " ".join(teks.lower().split())
        if peran == "user" and teks_norm == kueri_norm:
            continue
        # Hindari duplikasi yang sama persis di riwayat berurutan pula.
        if riwayat_bersih and riwayat_bersih[-1][0] == peran and riwayat_bersih[-1][1] == teks_norm:
            continue
        riwayat_bersih.append((peran, teks_norm, teks))

    # Tambahkan maksimal empat giliran terdahulu, bukan system prompt.
    if riwayat_bersih:
        for peran, _teks_norm, teks in riwayat_bersih[-4:]:
            nama_peran = "assistant" if peran == "assistant" else "user"
            prompt_lengkap += f"<|im_start|>{nama_peran}\n{teks}\n<|im_end|>\n"

    prompt_lengkap += f"<|im_start|>user\n{kueri}\n<|im_end|>\n<|im_start|>assistant\n"
    return prompt_lengkap


from starlette.concurrency import run_in_threadpool


def _ringkas_konten_rag(konten: str, batas_karakter: int = 1250) -> str:
    """Pertahankan paragraf/baris penting dari satu dokumen RAG saja."""
    import re as _re
    bagian = [baris.strip() for baris in konten.splitlines() if baris.strip()]
    hasil = []
    panjang = 0
    for baris in bagian:
        if baris.lower().startswith(("alur pindah", "catatan tambahan", "informasi tambahan")):
            break
        kandidat = len(baris) + (1 if hasil else 0)
        if hasil and panjang + kandidat > batas_karakter:
            break
        hasil.append(baris)
        panjang += kandidat
    return "\n".join(hasil).strip()


def _jawab_tanpa_llm(kueri: str, dokumen: list, konteks: str, konteks_web: str) -> str:
    """Jawaban aman saat model generatif lokal belum tersedia."""
    q = kueri.lower()
    if konteks_web:
        # Ambil satu hasil web teratas; jangan mencampurnya dengan RAG kampus.
        blok = konteks_web.split("\n\n")[0]
        baris = [b.strip() for b in blok.splitlines() if b.strip() and not b.startswith("Sumber:")]
        isi = " ".join(baris[1:] if len(baris) > 1 else baris)
        # Artikel ensiklopedis yang hanya menjelaskan jabatan tidak menjawab
        # pertanyaan "siapa ... sekarang". Lebih baik jujur meminta ulang
        # daripada mengirim informasi umum yang tampak meyakinkan tetapi salah.
        jika_tanya_tokoh = any(k in q for k in ("siapa presiden", "walikota", "wali kota"))
        jawaban_jabatan_generik = (
            isi.lower().startswith("presiden republik indonesia")
            and "prabowo" not in isi.lower()
        )
        if jika_tanya_tokoh and (jawaban_jabatan_generik or not any(
            penanda in isi.lower()
            for penanda in ("adalah", "menjabat", "dipimpin", "prabowo", "wali kota")
        )):
            return "Maaf, sumber real-time yang tersedia belum menampilkan nama pejabatnya dengan jelas. Coba kirim pertanyaannya sekali lagi ya."
        return _ringkas_konten_rag(isi, 520) or "Maaf, hasil pencarian real-time belum bisa diringkas."

    if konteks.startswith("INTENT_PERCAKAPAN:"):
        return konteks.split(":", 2)[-1].strip()

    realtime = any(k in q for k in ("presiden", "walikota", "berita", "terkini", "sekarang", "hari ini", "cuaca"))
    if realtime:
        return "Maaf, pencarian informasi terkini sedang tidak tersedia. Coba kirim pertanyaannya sekali lagi ya."

    if dokumen:
        return _ringkas_konten_rag(dokumen[0].get("konten", ""))

    return (
        "Aku bisa membantu menjawab pertanyaan umum atau informasi UCIC. "
        "Kalau ingin info kampus, silakan tanyakan saja tentang pendaftaran, jurusan, biaya, atau beasiswa."
    )


def _bersihkan_duplikasi_teks(teks: str) -> str:
    """
    Bersihkan jawaban AI dari duplikasi teks, baris ganda, dan pengulangan.
    Menangani: kalimat berulang, frasa berulang, baris duplikat, spasi ganda,
    tag template yang bocor, dan pengulangan kata.
    """
    if not teks:
        return teks
    import re as _re

    # 0. Hapus tag template yang bocor dari LLM
    teks = _re.sub(r"<\|im_start\|>.*?<\|im_end\|>", "", teks, flags=_re.DOTALL)
    teks = _re.sub(r"<\|im_start\|>.*?", "", teks)
    teks = _re.sub(r"<\|im_end\|>", "", teks)

    # 1. Hapus baris yang sama persis berurutan
    baris = teks.split("\n")
    baris_bersih = []
    for b in baris:
        if b.strip() and (not baris_bersih or b.strip() != baris_bersih[-1].strip()):
            baris_bersih.append(b)
    teks = "\n".join(baris_bersih)

    # 2. Pisah teks menjadi kalimat utuh (dengan tanda akhirnya)
    kalimat_utuh = _re.findall(r"[^.!?]*[.!?]\s*", teks)
    if not kalimat_utuh:
        kalimat_utuh = [teks]
    sisa = teks[len("".join(kalimat_utuh)):]
    if sisa.strip():
        kalimat_utuh.append(sisa)

    # 3. Hapus kalimat yang sama, termasuk pengulangan non-berurutan yang
    # sering muncul setelah model menerima konteks ganda.
    hasil_kalimat = []
    kalimat_terlihat = set()
    for k in kalimat_utuh:
        k_bersih = k.strip()
        if not k_bersih:
            continue
        k_norm = _re.sub(r"[^\w]+", " ", k_bersih.lower()).strip()
        if k_norm in kalimat_terlihat:
            continue
        # Cek apakah kalimat ini sama dengan kalimat sebelumnya
        if hasil_kalimat and k_bersih == hasil_kalimat[-1].strip():
            continue
        # Cek apakah kalimat ini adalah duplikasi parsial (misal: "UCIC" setelah "UCIC adalah kampus")
        if hasil_kalimat:
            prev = hasil_kalimat[-1].strip().rstrip(".!?")
            # Jika kalimat sebelumnya sudah mengandung kalimat ini secara lengkap, lewati
            if len(k_bersih) < 20 and k_bersih.rstrip(".!?") in prev:
                continue
        hasil_kalimat.append(k)
        kalimat_terlihat.add(k_norm)
    teks = "".join(hasil_kalimat)

    # 4. Hapus frasa berulang dalam satu kalimat (misal: "biaya kuliah biaya kuliah")
    teks = _re.sub(r"\b(\w+(?:\s+\w+)?)\s+\1\b", r"\1", teks, flags=_re.IGNORECASE)

    # 5. Hapus spasi ganda dan baris kosong berlebihan
    teks = _re.sub(r" {2,}", " ", teks)
    teks = _re.sub(r"\n{3,}", "\n\n", teks)
    return teks.strip()


@aplikasi_server.post("/api/transcribe")
async def transkripsi_audio_rest(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    """Endpoint transkripsi suara menjadi teks via Whisper offline non-blocking (faster-whisper)."""
    bahasa_efektif = lang or bahasa or "id"
    konten_bytes = await file.read()
    hasil = await run_in_threadpool(
        pengenal_suara.transkripsikan_audio_bytes,
        konten_bytes,
        bahasa=bahasa_efektif
    )
    teks_hasil = hasil.get("teks", "")
    return {
        "text": teks_hasil,
        "teks": teks_hasil,
        "sukses": hasil.get("sukses", True),
        "durasi": hasil.get("durasi", 0),
        "bahasa": hasil.get("bahasa", bahasa_efektif),
    }


@aplikasi_server.post("/api/transkripsi")
async def transkripsi_audio_rest_alias(
    file: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    bahasa: Optional[str] = Form("id"),
):
    """Alias Bahasa Indonesia untuk /api/transcribe (kompatibilitas frontend lama)."""
    return await transkripsi_audio_rest(file=file, lang=lang, bahasa=bahasa)


@aplikasi_server.get("/api/status-asr")
async def status_mesin_asr():
    """Endpoint status kesiapan mesin Whisper ASR."""
    return {
        "apakah_siap": pengenal_suara.apakah_siap,
        "nama_model": pengenal_suara.nama_model_aktif,
        "perangkat": pengenal_suara.perangkat_aktif,
    }


@aplikasi_server.post("/api/sintesis")
async def sintesis_audio_rest(data_permintaan: PermintaanSintesis):
    """Endpoint sintesis suara Text-to-Speech offline natural (perempuan ID/EN/Jawa)."""
    hasil = await sintesis_suara.sintesis_teks_ke_audio_base64_async(
        data_permintaan.teks_kalimat, bahasa=data_permintaan.bahasa or "id"
    )
    return hasil


@aplikasi_server.get("/api/status-tts")
async def status_mesin_tts():
    """
    Endpoint monitoring status mesin TTS:
    - piper_siap: Piper ONNX sudah terload (fallback cepat)
    - omnivoice_siap: OmniVoice Voice Cloning sudah siap (kualitas tinggi)
    - omnivoice_gagal: Inisialisasi OmniVoice gagal (lihat log server)
    - engine_aktif: Engine yang saat ini digunakan ('omnivoice' atau 'piper')
    """
    return sintesis_suara.status_engine()


# ── Endpoint Web Search Real-Time ─────────────────────────────────────────────

class PermintaanWebSearch(BaseModel):
    query: str


@aplikasi_server.post("/api/web-search")
async def web_search_rest(data: PermintaanWebSearch):
    """Endpoint pencarian web real-time gratis (DuckDuckGo + Wikipedia)."""
    hasil = await run_in_threadpool(pencari_web.cari, data.query, "id")
    return hasil


# ── Endpoint MCP (Model Context Protocol) ─────────────────────────────────────

@aplikasi_server.get("/api/mcp/status")
async def status_mcp():
    """Status koneksi MCP ke jaringan robot kampus lainnya."""
    return klien_mcp.status()


@aplikasi_server.post("/api/mcp/kirim")
async def kirim_pesan_mcp(data: dict):
    """Kirim pesan ke robot kampus lain via MCP."""
    pesan = data.get("pesan", "")
    target = data.get("target", "broadcast")
    berhasil = klien_mcp.kirim_pesan(pesan, target)
    return {"terkirim": berhasil}


@aplikasi_server.get("/api/mcp/pesan-masuk")
async def ambil_pesan_mcp():
    """Ambil pesan masuk dari robot kampus lain."""
    pesan = klien_mcp.ambil_pesan_masuk()
    return {"pesan": pesan, "jumlah": len(pesan)}


# ── Endpoint Pengenal User (Memori Nama) ─────────────────────────────────────

class PermintaanUser(BaseModel):
    nama: Optional[str] = None


@aplikasi_server.get("/api/user/status")
async def status_user():
    """Cek apakah nama user sudah diketahui."""
    return {
        "dikenal": pengenal_user.apakah_dikenal(),
        "nama": pengenal_user.nama_user,
    }


@aplikasi_server.post("/api/user/simpan-nama")
async def simpan_nama_user(data: PermintaanUser):
    """Simpan nama user."""
    if data.nama:
        pengenal_user.simpan_nama(data.nama)
    return {"sukses": True, "nama": pengenal_user.nama_user}


@aplikasi_server.get("/api/user/konteks")
async def konteks_user():
    """Ambil konteks user untuk LLM."""
    return {"konteks": pengenal_user.dapatkan_konteks_user()}


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

                    # 1. Cek apakah user menyebutkan namanya
                    nama_diekstrak = pengenal_user.ekstrak_nama_dari_pesan(teks_tanya)
                    if nama_diekstrak:
                        pengenal_user.simpan_nama(nama_diekstrak)

                    # 2. Bangun prompt berbasis RAG (sekali eksekusi, hindari duplikasi)
                    konteks_grounding, dokumen_rujukan, ditemukan = mesin_rag.bangun_konteks_grounding(teks_tanya, riwayat_chat)
                    prompt_instruksi = mesin_rag.buat_prompt_instruksi_dari_konteks(
                        teks_tanya, riwayat_chat, konteks_grounding, dokumen_rujukan, ditemukan
                    )

                    # 3. Web search real-time jika diperlukan
                    konteks_web = ""
                    if pencari_web.apakah_perlu_web_search(teks_tanya):
                        try:
                            hasil_web = await run_in_threadpool(pencari_web.cari, teks_tanya, lang)
                            if hasil_web.get("ditemukan"):
                                konteks_web = hasil_web.get("konteks", "")
                                if "<|im_start|>assistant\n" in prompt_instruksi:
                                    prompt_instruksi = prompt_instruksi.replace(
                                        "<|im_start|>assistant\n",
                                        f"[KONTEKS WEB SEARCH]\n{konteks_web}\n\n<|im_start|>assistant\n",
                                    )
                        except Exception as galat_web:
                            print(f"[WebSocket Dupleks] Web search gagal: {galat_web}")

                    # 4. Sisipkan konteks user jika ada
                    konteks_user = pengenal_user.dapatkan_konteks_user()
                    if (konteks_user and "<|im_start|>assistant\n" in prompt_instruksi
                            and "[KONTEKS USER]" not in prompt_instruksi):
                        prompt_instruksi = prompt_instruksi.replace(
                            "<|im_start|>assistant\n",
                            f"[KONTEKS USER]\n{konteks_user}\n\n<|im_start|>assistant\n",
                        )

                    # Kirim notifikasi mulai generasi
                    await koneksi_ws.send_json({
                        "tipe": "mulai_menjawab",
                        "kueri": teks_tanya,
                        "dokumen_rujukan": [
                            {"judul": d["judul"], "kategori": d["kategori"]} for d in dokumen_rujukan
                        ],
                    })

                    teks_terkumpul = []

                    # Saat GGUF tidak terpasang, gunakan respons RAG/web yang
                    # sudah dirutekan, bukan ekstraksi prompt generik.
                    if pemroses_llm.apakah_siap:
                        aliran_kalimat = pemroses_llm.streaming_per_kalimat(prompt_instruksi)
                    else:
                        jawaban = _jawab_tanpa_llm(
                            teks_tanya, dokumen_rujukan, konteks_grounding, konteks_web
                        )
                        potongan = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", jawaban) if s.strip()]
                        aliran_kalimat = ({"tipe": "kalimat", "teks": s} for s in potongan)

                    # Alirkan per kalimat untuk disintesis suaranya secara paralel
                    for item_kalimat in aliran_kalimat:
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
                        try:
                            hasil_audio = await sintesis_suara.sintesis_teks_ke_audio_base64_async(kalimat, bahasa=lang)
                        except Exception as galat_tts:
                            print(f"[WebSocket Dupleks] TTS gagal untuk kalimat: {galat_tts}")
                            hasil_audio = None

                        if hasil_audio and hasil_audio.get("audio_base64"):
                            await koneksi_ws.send_json({
                                "tipe": "potongan_audio",
                                "kalimat": kalimat,
                                "audio_base64": hasil_audio.get("audio_base64"),
                                "format": hasil_audio.get("format", "audio/wav"),
                                "engine": hasil_audio.get("engine"),
                                "bahasa": hasil_audio.get("bahasa", "id-ID"),
                            })
                        elif hasil_audio and not hasil_audio.get("audio_base64"):
                            # Jangan mengganti karakter suara SELA dengan engine lain.
                            await koneksi_ws.send_json({
                                "tipe": "status_tts_gagal",
                                "kalimat": kalimat,
                                "engine": "omnivoice-unavailable",
                            })

                        # Beri jeda sangat singkat agar event loop dapat menangani interupsi
                        await asyncio.sleep(0.01)

                    if not apakah_dibatalkan:
                        teks_penuh = " ".join(teks_terkumpul)
                        # Bersihkan duplikasi
                        teks_penuh = _bersihkan_duplikasi_teks(teks_penuh)
                        await koneksi_ws.send_json({
                            "tipe": "selesai",
                            "teks_penuh": teks_penuh,
                            "dokumen_rujukan": [
                                {"judul": d["judul"], "kategori": d["kategori"]} for d in dokumen_rujukan
                            ],
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
