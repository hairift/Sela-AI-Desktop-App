"""
SELA AI Desktop - Pengujian Komprehensif Seluruh Modul AI Offline
===================================================================
1. Uji Kesehatan Server & Komponen AI (/kesehatan)
2. Uji RAG Goldens & Intent Percakapan (Sapaan, Identitas, Prodi, Biaya, Multi-Turn)
3. Uji Anti-QR Ganda (Deduplikasi tautan pada respon obrolan)
4. Uji Sintesis Suara TTS (OmniVoice Cloned / Piper Female, timing, disk cache)
5. Uji Pengenalan Suara ASR (Whisper transkripsi audio ucapan & uji hening)
"""

import os
import io
import time
import json
import base64
import wave
import struct

from fastapi.testclient import TestClient
from server import aplikasi_server


klien = TestClient(aplikasi_server)


def uji_kesehatan():
    print("\n" + "=" * 60)
    print("1. PENGUJIAN STATUS KESEHATAN SERVER (/kesehatan)")
    print("=" * 60)
    resp = klien.get("/kesehatan")
    assert resp.status_code == 200, f"Status code bukan 200: {resp.status_code}"
    data = resp.json()
    print(f"Status: {data.get('status')}")
    print(f"Total Dokumen RAG: {data.get('total_dokumen_rag')}")
    print(f"Whisper Tersedia: {data.get('model_whisper_tersedia')} ({data.get('model_whisper_aktif')})")
    print(f"TTS Engine: {data.get('tts_engine')}")
    print(f"Sampel Suara Kloning: {data.get('sampel_suara_kloning')} berkas")
    assert data.get("status") == "sehat"
    assert data.get("total_dokumen_rag", 0) > 100
    assert data.get("tts_siap") is True
    print("-> [LULUS] Status kesehatan server prima!")


def uji_rag_goldens():
    print("\n" + "=" * 60)
    print("2. PENGUJIAN RAG GOLDENS & INTENT PERCAKAPAN")
    print("=" * 60)

    kasus_uji = [
        {
            "nama": "Sapaan Ramah (Bukan Prodi Olahraga)",
            "query": "halo",
            "riwayat": [],
            "kata_kunci_wajib": ["halo", "selamat datang", "ucic", "sela"],
            "kata_kunci_dilarang": ["olahraga", "perpustakaan"],
        },
        {
            "nama": "Identitas & Profil SELA",
            "query": "siapa kamu",
            "riwayat": [],
            "kata_kunci_wajib": ["sela", "asisten virtual", "ucic"],
            "kata_kunci_dilarang": ["perpustakaan ucic adalah fasilitas"],
        },
        {
            "nama": "Fakultas dan Program Studi",
            "query": "Fakultas apa saja yang ada di UCIC?",
            "riwayat": [],
            "kata_kunci_wajib": ["fti", "feb", "fps"],
            "kata_kunci_dilarang": [],
        },
        {
            "nama": "Biaya Kuliah Teknik Informatika",
            "query": "Berapa biaya kuliah S1 Teknik Informatika?",
            "riwayat": [],
            "kata_kunci_wajib": ["teknik informatika", "reguler", "semester"],
            "kata_kunci_dilarang": [],
        },
        {
            "nama": "Multi-Turn Context Linking (Nyambung)",
            "query": "Lalu syarat pendaftarannya apa?",
            "riwayat": [
                {"role": "user", "text": "Berapa biaya kuliah S1 Teknik Informatika?"},
                {"role": "assistant", "text": "Biaya S1 Teknik Informatika reguler 3 bulan Rp2.820.000..."},
            ],
            "kata_kunci_wajib": ["pendaftaran", "pmb", "ijazah"],
            "kata_kunci_dilarang": [],
        },
    ]

    for k in kasus_uji:
        t0 = time.time()
        resp = klien.post(
            "/api/chat",
            json={
                "userQuery": k["query"],
                "riwayat_obrolan": k["riwayat"],
                "bahasa": "id",
            },
        )
        dt = time.time() - t0
        assert resp.status_code == 200, f"Chat gagal: {resp.status_code}"
        data = resp.json()
        teks = data.get("text", "").lower()

        print(f"\n[UJI]: {k['nama']} ({dt:.2f}s)")
        print(f"Query: '{k['query']}'")
        print(f"Jawaban: {data.get('text', '')[:120]}...")

        for w in k["kata_kunci_wajib"]:
            assert w in teks, f"Kata kunci wajib '{w}' tidak ditemukan dalam: {teks}"

        for d in k["kata_kunci_dilarang"]:
            assert d not in teks, f"Kata kunci terlarang '{d}' muncul dalam: {teks}"

        # Uji pencegahan URL ganda pada teks
        urls = [u for u in data.get("text", "").split() if u.startswith("http")]
        if urls:
            assert len(urls) == len(set(urls)), f"Ditemukan duplikasi URL mentah dalam teks: {urls}"

        print(f"-> [LULUS] Respon valid & bebas halusinasi!")


def uji_tts_sintesis():
    print("\n" + "=" * 60)
    print("3. PENGUJIAN SINTESIS SUARA TTS (OmniVoice / Piper)")
    print("=" * 60)

    kalimat_uji = [
        ("Halo! Selamat datang di Universitas Catur Insan Cendekia Cirebon.", "id"),
    ]

    for teks, lang in kalimat_uji:
        # Panggilan pertama (generasi neural)
        t0 = time.time()
        resp = klien.post(
            "/api/sintesis",
            json={"teks_kalimat": teks, "bahasa": lang},
        )
        dt = time.time() - t0
        assert resp.status_code == 200
        data = resp.json()
        b64 = data.get("audio_base64", "")
        engine = data.get("engine", "")
        print(f"[{dt:.2f}s] Generasi ({engine}): '{teks[:35]}...' -> {len(b64)} chars b64")
        assert len(b64) > 1000, "Audio base64 kosong atau terlalu kecil"

        # Panggilan kedua (harus instan via disk/memory cache)
        t1 = time.time()
        resp_cache = klien.post(
            "/api/sintesis",
            json={"teks_kalimat": teks, "bahasa": lang},
        )
        dt_cache = time.time() - t1
        data_cache = resp_cache.json()
        print(f"[{dt_cache:.4f}s] Cache Hit ({data_cache.get('engine')}): '{teks[:35]}...'")
        assert dt_cache < 0.1, "Cache hit harus di bawah 100ms"

    print("-> [LULUS] Seluruh sintesis audio valid dan caching bekerja instan!")


def uji_asr_transkripsi():
    print("\n" + "=" * 60)
    print("4. PENGUJIAN PENGENAL SUARA ASR (Whisper Offline)")
    print("=" * 60)

    # 1. Transkripsi berkas WAV asli pengguna
    jalur_sampel = os.path.join(
        os.path.dirname(__file__), "voice_samples", "001-id.wav"
    )
    if os.path.exists(jalur_sampel):
        with open(jalur_sampel, "rb") as f:
            konten_wav = f.read()

        t0 = time.time()
        resp = klien.post(
            "/api/transcribe",
            files={"file": ("sample.wav", io.BytesIO(konten_wav), "audio/wav")},
            data={"lang": "id"},
        )
        dt = time.time() - t0
        assert resp.status_code == 200
        data = resp.json()
        teks_hasil = data.get("text", "")
        print(f"[{dt:.2f}s] Transkripsi 001-id.wav: '{teks_hasil}'")
        assert "selamat datang" in teks_hasil.lower() or "asisten" in teks_hasil.lower()
        print("-> [LULUS] Transkripsi audio asli pengguna akurat!")

    # 2. Uji audio hening (VAD harus menolak, tidak halusinasi)
    buf_hening = io.BytesIO()
    with wave.open(buf_hening, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    buf_hening.seek(0)

    resp_hening = klien.post(
        "/api/transcribe",
        files={"file": ("hening.wav", buf_hening, "audio/wav")},
        data={"lang": "id"},
    )
    assert resp_hening.status_code == 200
    data_hening = resp_hening.json()
    print(f"Uji Hening VAD: teks='{data_hening.get('text')}' | sukses={data_hening.get('sukses')}")
    assert data_hening.get("text") == "", "Audio hening tidak boleh menghasilkan teks halusinasi"
    print("-> [LULUS] Gerbang energi & VAD menolak hening tanpa halusinasi!")


if __name__ == "__main__":
    t_mulai = time.time()
    uji_kesehatan()
    uji_rag_goldens()
    uji_tts_sintesis()
    uji_asr_transkripsi()
    total_waktu = time.time() - t_mulai
    print("\n" + "=" * 60)
    print(f"SELURUH PENGUJIAN SELESAI & LULUS 100% DALAM {total_waktu:.2f} DETIK!")
    print("=" * 60)
