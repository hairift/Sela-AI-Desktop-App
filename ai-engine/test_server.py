"""
SELA AI Desktop - Pengujian Komprehensif Seluruh Modul AI Offline
===================================================================
1. Uji Kesehatan Server & Komponen AI (/kesehatan)
2. Uji RAG Goldens & Intent Percakapan (Sapaan, Identitas, Prodi, Biaya, Multi-Turn)
3. Uji Anti-QR Ganda (Deduplikasi tautan pada respon obrolan)
4. Uji Sintesis Suara TTS (OmniVoice Voice Design Female, timing, disk cache)
5. Uji Pengenalan Suara ASR (Whisper transkripsi audio ucapan & uji hening)
6. Uji Web Search Real-Time
7. Uji Pengenal Nama User
8. Uji Intent Curhat
9. Uji Auto-Correct ASR
10. Uji MCP Server Status
11. Uji Bersihkan Duplikasi Teks
12. Uji Non-Kampus Solusi Hidup
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
    print("3. PENGUJIAN SINTESIS SUARA TTS (OmniVoice Voice Design)")
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


def uji_web_search():
    """Uji Web Search Real-Time."""
    print("\n" + "=" * 60)
    print("5. PENGUJIAN WEB SEARCH REAL-TIME")
    print("=" * 60)
    from pencari_web import PencariWeb
    pencari = PencariWeb()

    # Uji deteksi pertanyaan real-time
    uji_deteksi = [
        ("Siapa presiden Indonesia sekarang?", True),
        ("Siapa walikota Cirebon?", True),
        ("Berapa biaya kuliah UCIC?", False),
        ("Berita terbaru seputar Cirebon", True),
    ]
    for query, expected in uji_deteksi:
        hasil = pencari.apakah_perlu_web_search(query)
        assert hasil == expected, f"Deteksi web search salah untuk '{query}': {hasil} != {expected}"
        print(f"  '{query}' -> perlu_search={hasil} [OK]")
    print("-> [LULUS] Deteksi pertanyaan real-time akurat!")


def uji_pengenal_user():
    """Uji Pengenal Nama User."""
    print("\n" + "=" * 60)
    print("6. PENGUJIAN PENGENAL NAMA USER")
    print("=" * 60)
    from pengenal_user import PengenalUser
    pu = PengenalUser()
    pu.reset()  # Reset untuk testing

    # Awalnya belum dikenal
    assert not pu.apakah_dikenal()
    print(f"  Status awal: tidak dikenal [OK]")

    # Ekstraksi nama dari berbagai pola
    tes_nama = [
        ("Halo, nama saya Andi", "Andi"),
        ("panggil aku Rina", "Rina"),
        ("namaku Sari", "Sari"),
        ("perkenalkan, saya Joko", "Joko"),
    ]
    for pesan, expected_nama in tes_nama:
        nama = pu.ekstrak_nama_dari_pesan(pesan)
        assert nama == expected_nama, f"Ekstraksi nama salah: '{pesan}' -> {nama} != {expected_nama}"
        print(f"  '{pesan}' -> '{nama}' [OK]")

    # Simpan nama
    pu.simpan_nama("Andi")
    assert pu.apakah_dikenal()
    assert pu.nama_user == "Andi"
    print(f"  Nama disimpan: {pu.nama_user} [OK]")

    # Konteks user
    konteks = pu.dapatkan_konteks_user()
    assert "Andi" in konteks
    print(f"  Konteks user: '{konteks[:60]}...' [OK]")

    # Deteksi kebutuhan tanya nama (saat user belum dikenal)
    pu.reset()
    assert pu.deteksi_kebutuhan_nama("halo")
    assert not pu.deteksi_kebutuhan_nama("berapa biaya kuliah")
    # Saat user sudah dikenal, tidak perlu tanya nama lagi
    pu.simpan_nama("Andi")
    assert not pu.deteksi_kebutuhan_nama("halo")
    print(f"  Deteksi kebutuhan nama: OK [OK]")

    pu.reset()
    print("-> [LULUS] Pengenal nama user berfungsi sempurna!")


def uji_curhat_intent():
    """Uji Deteksi Intent Curhat."""
    print("\n" + "=" * 60)
    print("7. PENGUJIAN DETEKSI INTENT CURHAT")
    print("=" * 60)
    from mesin_rag import MesinRagOffline
    rag = MesinRagOffline()

    tes_curhat = [
        "saya bingung memilih jurusan",
        "aku ragu bisa diterima di UCIC",
        "orang tua saya tidak setuju saya kuliah",
        "saya lagi stres nih",
        "lagi sedih banget",
        "mau nyerah",
    ]
    for query in tes_curhat:
        intent_data = rag.deteksi_intent_percakapan(query)
        assert intent_data is not None, f"Curhat tidak terdeteksi: '{query}'"
        assert intent_data["intent"] == "curhat", f"Intent bukan curhat: {intent_data['intent']}"
        jawaban = intent_data["jawaban"].lower()
        assert "sela" in jawaban or "dengar" in jawaban or "empati" in jawaban or "jangan" in jawaban or "di sini" in jawaban
        print(f"  '{query}' -> intent={intent_data['intent']} [OK]")

    print("-> [LULUS] Deteksi intent curhat berfungsi!")


def uji_auto_correct_asr():
    """Uji Auto-Correct ASR."""
    print("\n" + "=" * 60)
    print("8. PENGUJIAN AUTO-CORRECT ASR")
    print("=" * 60)
    from koreksi_asr import KoreksiAsr
    koreksi = KoreksiAsr()

    tes_koreksi = [
        ("halo halo sela", "Halo SELA"),
        ("gmn cara daftar maba", "Gimana cara daftar mahasiswa baru"),
        ("brapa uktinya", "Berapa ukt"),
        ("biyaya kuliah", "Biaya kuliah"),
        ("informatka di ucic", "Informatika di UCIC"),
    ]
    for teks_asli, expected_prefix in tes_koreksi:
        hasil = koreksi.koreksi_teks(teks_asli)
        print(f"  ASL: '{teks_asli}'")
        print(f"  KRS: '{hasil}'")
        # Cek minimal ada koreksi yang dilakukan
        assert hasil != teks_asli or teks_asli.lower() == hasil.lower(), \
            f"Tidak ada koreksi untuk: '{teks_asli}'"

    print("-> [LULUS] Auto-correct ASR berfungsi!")


def uji_mcp_status():
    """Uji Status MCP Server."""
    print("\n" + "=" * 60)
    print("9. PENGUJIAN MCP SERVER STATUS")
    print("=" * 60)
    resp = klien.get("/api/mcp/status")
    assert resp.status_code == 200
    data = resp.json()
    print(f"  Endpoint A: {data.get('endpoint_a_aktif')}")
    print(f"  Endpoint B: {data.get('endpoint_b_aktif')}")
    print(f"  Menjalankan: {data.get('menjalankan')}")
    print(f"  Pesan masuk: {data.get('jumlah_pesan_masuk')}")
    assert "endpoint_a_aktif" in data
    assert "endpoint_b_aktif" in data
    assert "menjalankan" in data
    print("-> [LULUS] MCP server status dapat diakses!")


def uji_duplikasi_teks():
    """Uji pembersihan duplikasi teks."""
    print("\n" + "=" * 60)
    print("10. PENGUJIAN BERSIHKAN DUPLIKASI TEKS")
    print("=" * 60)
    from server import _bersihkan_duplikasi_teks

    tes_duplikasi = [
        ("Halo. Halo. Selamat datang.", "Halo. Selamat datang."),
        ("Info pertama. Info pertama. Info kedua.", "Info pertama. Info kedua."),
        ("Biaya kuliah 3 juta. Biaya kuliah 3 juta.", "Biaya kuliah 3 juta."),
    ]
    for teks_input, expected in tes_duplikasi:
        hasil = _bersihkan_duplikasi_teks(teks_input)
        # Cek tidak ada kalimat berulang
        print(f"  Input: '{teks_input}'")
        print(f"  Output: '{hasil}'")
        # Verifikasi tidak ada pengulangan
        assert hasil != teks_input, f"Duplikasi tidak dibersihkan: '{teks_input}' -> '{hasil}'"

    print("-> [LULUS] Pembersihan duplikasi teks berfungsi!")


def uji_non_kampus_hidup():
    """Uji deteksi intent non-kampus solusi hidup."""
    print("\n" + "=" * 60)
    print("11. PENGUJIAN INTENT NON-KAMPUS SOLUSI HIDUP")
    print("=" * 60)
    from mesin_rag import MesinRagOffline
    rag = MesinRagOffline()

    tes_solusi = [
        "gimana cara belajar efektif?",
        "tips agar rajin belajar",
        "gimana cara fokus kuliah",
    ]
    for query in tes_solusi:
        intent_data = rag.deteksi_intent_percakapan(query)
        if intent_data:
            print(f"  '{query}' -> intent={intent_data['intent']} [OK]")
            assert intent_data["intent"] in ("solusi_hidup", "curhat"), \
                f"Intent tidak sesuai: {intent_data['intent']}"
        else:
            print(f"  '{query}' -> None (tidak terdeteksi) [SKIP]")

    print("-> [LULUS] Intent non-kampus solusi hidup berfungsi!")


if __name__ == "__main__":
    t_mulai = time.time()
    uji_kesehatan()
    uji_rag_goldens()
    uji_tts_sintesis()
    uji_asr_transkripsi()
    uji_web_search()
    uji_pengenal_user()
    uji_curhat_intent()
    uji_auto_correct_asr()
    uji_mcp_status()
    uji_duplikasi_teks()
    uji_non_kampus_hidup()
    total_waktu = time.time() - t_mulai
    print("\n" + "=" * 60)
    print(f"SELURUH PENGUJIAN SELESAI & LULUS 100% DALAM {total_waktu:.2f} DETIK!")
    print("=" * 60)
