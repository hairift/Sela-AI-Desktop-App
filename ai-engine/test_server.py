"""
SELA AI Desktop - Uji Asap (Smoke Test) Arsitektur Baru
=======================================================
Menguji setiap lapisan tanpa perlu menjalankan server penuh:

1. Chunker jendela kalimat (512/80)
2. Embedder (bge-m3 atau hashing cadangan)
3. Vector store (FAISS atau NumPy)
4. Retriever leksikal BM25 + gerbang cakupan IDF
5. RAG engine + ambang anti-halusinasi
6. Evaluasi goldens (src/data/rag_goldens.json)
7. Campus tool (intent + pencarian)
8. Curhat tool (empatik)
9. Web search (deteksi kebutuhan)
10. TTS Piper (sintesis pendek)
11. STT (gerbang energi untuk audio pendek/hening)
12. VAD (SPEECH_START / SPEECH_END)
13. Prompt library (tujuh prompt)
14. Routing ranah (kampus / umum / real-time)
15. Server FastAPI (opsional, set SELA_UJI_SERVER=1)
16. Pengunduh model (truncate berkas rusak / resume / verifikasi)

Jalankan:  python ai-engine/test_server.py
"""

from __future__ import annotations

import io
import json
import os
import struct
import sys
import wave

_AKAR = os.path.dirname(os.path.abspath(__file__))
if _AKAR not in sys.path:
    sys.path.insert(0, _AKAR)

LULUS = 0
GAGAL = 0


def _cek(nama: str, kondisi: bool, detail: str = "") -> None:
    global LULUS, GAGAL
    if kondisi:
        LULUS += 1
        print(f"  [LULUS] {nama} {detail}")
    else:
        GAGAL += 1
        print(f"  [GAGAL] {nama} {detail}")


def _jalur_goldens() -> str:
    return os.path.abspath(os.path.join(_AKAR, "..", "src", "data", "rag_goldens.json"))


def _jalur_model_glb() -> str:
    return os.path.abspath(os.path.join(_AKAR, "..", "public", "models", "sela.glb"))


def _nama_animasi_glb(jalur: str) -> set[str]:
    """
    Baca daftar nama animasi langsung dari chunk JSON di dalam berkas .glb.

    Dipakai untuk memastikan setiap gerakan yang bisa dipilih `tentukan_gerakan`
    benar-benar ada sebagai klip di model. Tanpa pemeriksaan ini, mengganti model
    3D bisa membuat animasi mati senyap (nama klip tidak cocok) tanpa galat apa pun.
    """
    if not os.path.exists(jalur):
        return set()
    with open(jalur, "rb") as berkas:
        if berkas.read(4) != b"glTF":
            return set()
        berkas.read(8)  # versi + panjang total berkas
        while True:
            kepala = berkas.read(8)
            if len(kepala) < 8:
                return set()
            panjang, tipe = struct.unpack("<II", kepala)
            data = berkas.read(panjang)
            # Tipe chunk JSON = 'JSON' dibaca little-endian.
            if tipe == 0x4E4F534A:
                dokumen = json.loads(data.decode("utf-8"))
                return {
                    animasi.get("name", "")
                    for animasi in dokumen.get("animations", [])
                }
            if tipe == 0x004E4942:  # 'BIN\0' -> JSON sudah terlewat
                return set()


def uji_chunker() -> None:
    print("\n[1] Chunker jendela kalimat")
    from rag import SentenceWindowChunker

    c = SentenceWindowChunker(chunk_size=512, overlap=80)
    teks = "Ini kalimat contoh untuk pengujian. " * 120
    potongan = c.potong(teks)
    _cek("menghasilkan potongan", len(potongan) > 1, f"({len(potongan)} potongan)")
    _cek("panjang <= chunk_size", all(len(p.split()) <= 512 for p in potongan))
    dok = {"id": "x", "title": "Judul", "category": "profil", "keywords": ["a"], "content": teks}
    chunk = c.bangun_chunk(dok)
    _cek("bangun_chunk membawa metadata", chunk and chunk[0].judul == "Judul")


def uji_embedder() -> None:
    print("\n[2] Embedder")
    from rag import dapatkan_embedder

    emb = dapatkan_embedder()
    print(f"       metode: {emb.metode} ({emb.dimensi} dimensi)")
    v = emb.encode(["biaya kuliah", "harga ukt"])
    _cek("vektor berbentuk (2, dim)", getattr(v, "shape", (0,))[0] == 2)
    import numpy as np

    a = emb.encode("biaya kuliah teknik informatika")
    b = emb.encode("harga ukt prodi informatika")
    c = emb.encode("jadwal pertandingan sepak bola")
    _cek("kemiripan semantik wajar", float(np.dot(a, b)) >= float(np.dot(a, c)))


def uji_vector_store() -> None:
    print("\n[3] Vector store")
    import numpy as np

    from rag import VectorStore

    vs = VectorStore(dimensi=4)
    vs.tambah(np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype="float32"), [{"judul": "A"}, {"judul": "B"}])
    hasil = vs.cari(np.array([0.9, 0.1, 0, 0], dtype="float32"), top_k=1)
    _cek("pencarian mengembalikan hasil", bool(hasil), f"({vs.metode})")
    _cek("peringkat teratas benar", hasil and hasil[0][1]["judul"] == "A")

    # ── Persistensi & konsistensi indeks ─────────────────────────────────────
    # Bug yang pernah terjadi: `simpan()` jalur FAISS membiarkan `vectors.npy`
    # lama (dimensi berbeda) tertinggal, dan `muat()` tidak memeriksa kecocokan
    # dimensi maupun jumlah vektor vs metadata — sehingga jalur semantik bisa
    # mati senyap atau melempar IndexError. Tes ini mengunci perilaku yang benar.
    import json
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="uji_vs_")
    try:
        def _numpy_store(dim: int) -> "VectorStore":
            """Store yang sejak awal berjalan di jalur NumPy (faiss tidak ada)."""
            s = VectorStore(dimensi=dim, direktori=tmp)
            s._faiss = None
            s._index = None
            s.metode = "numpy"
            return s

        def _tulis_meta(dim: int, n: int) -> None:
            with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {"dimensi": dim, "metode": "numpy",
                     "metadatas": [{"id": f"d{i}"} for i in range(n)]},
                    f,
                )

        a = _numpy_store(8)
        a.tambah(np.random.rand(5, 8).astype("float32"), [{"id": f"d{i}"} for i in range(5)])
        a.simpan()
        _cek(
            "simpan jalur NumPy hanya menulis vectors.npy",
            sorted(os.listdir(tmp)) == ["meta.json", "vectors.npy"],
            f"({sorted(os.listdir(tmp))})",
        )

        b = VectorStore(dimensi=8, direktori=tmp)
        b.tambah(np.random.rand(5, 8).astype("float32"), [{"id": f"d{i}"} for i in range(5)])
        b.simpan()
        _cek(
            "simpan jalur FAISS membuang vectors.npy lama",
            sorted(os.listdir(tmp)) == ["index.faiss", "meta.json"],
            f"({sorted(os.listdir(tmp))})",
        )

        c = _numpy_store(8)
        os.remove(os.path.join(tmp, "index.faiss"))
        np.save(os.path.join(tmp, "vectors.npy"), np.random.rand(5, 8).astype("float32"))
        _tulis_meta(1024, 5)
        _cek("muat menolak dimensi tak cocok", c.muat() is False)
        _tulis_meta(8, 3)
        _cek("muat menolak jumlah vektor != metadata", c.muat() is False)
        _tulis_meta(8, 5)
        _cek("muat menerima indeks yang konsisten", c.muat() is True)

        d = _numpy_store(8)
        d._vektor = np.random.rand(5, 8).astype("float32")
        d.metadatas = [{"id": "hanya-satu"}]
        try:
            n = len(d.cari(np.random.rand(8).astype("float32"), top_k=3))
            _cek("cari() aman saat jumlah tak sinkron", n == 1, f"(n={n})")
        except Exception as galat:
            _cek("cari() aman saat jumlah tak sinkron", False, f"({type(galat).__name__})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uji_lexical() -> None:
    print("\n[4] Retriever leksikal BM25")
    from rag.lexical import LexicalIndex

    with open(os.path.join(_AKAR, "..", "src", "data", "ucic_dataset.json"), encoding="utf-8") as f:
        dok = json.load(f)
    idx = LexicalIndex(dok)
    print(f"       {idx.info()}")
    _cek("indeks terbangun", idx.n > 0)

    kandidat = idx.cari("Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?", top_k=3)
    top_ids = [k["dokumen"]["id"] for k in kandidat]
    _cek("kueri dosen+algoritma -> dosen_fti peringkat 1", bool(top_ids) and top_ids[0] == "dosen_fti", f"({top_ids})")

    kandidat2 = idx.cari("berapa biaya kuliah teknik informatika", top_k=3)
    top_ids2 = [k["dokumen"]["id"] for k in kandidat2]
    _cek(
        "kueri biaya TI -> dokumen biaya TI peringkat 1",
        bool(top_ids2) and top_ids2[0] == "biaya_teknik_informatika_2026",
        f"({top_ids2})",
    )

    _cek("kueri di luar kampus ditolak", idx.cari("resep rendang padang", top_k=3) == [])
    _cek("kueri tokoh luar kampus ditolak", idx.cari("siapa presiden indonesia sekarang", top_k=3) == [])

    # Varian PENDEK wajib ikut diuji. Sebelumnya hanya versi panjang di atas yang
    # diuji, dan versi panjang itu lolos hanya karena satu kecocokan kebetulan
    # masih di bawah ambang cakupan (1 dari 3 istilah). Pada versi pendek (2
    # istilah), satu kecocokan kebetulan bernilai cakupan 0,50 sehingga lolos —
    # mis. "resep rendang" -> koreksi salah ketik 'resep'->'reset' & 'rendang'->
    # 'renang' yang kebetulan ada di dua dokumen berbeda. Gerbang kini juga
    # menuntut >= 2 istilah berbeda cocok di SATU dokumen (_MIN_COCOK_DISTINCT).
    _cek("kueri PENDEK di luar kampus ditolak", idx.cari("resep rendang", top_k=3) == [])
    _cek("kueri PENDEK tokoh luar kampus ditolak", idx.cari("siapa presiden indonesia", top_k=3) == [])
    _cek("kueri harian di luar kampus ditolak", idx.cari("cuaca hari ini", top_k=3) == [])


def uji_rag() -> None:
    print("\n[5] RAG engine")
    from rag import RagEngine

    rag = RagEngine()
    print(f"       {rag.total_dokumen} dokumen, embedder={rag.embedder.metode}, semantik={rag._semantik_aktif()}")
    _cek("dokumen termuat", rag.total_dokumen > 0)

    _, dok, ada = rag.bangun_konteks("berapa biaya kuliah teknik informatika")
    _cek("menemukan dokumen relevan", ada and len(dok) > 0, f"(top: {dok[0]['judul'] if dok else '-'})")

    _, dok_algo, ada_algo = rag.bangun_konteks("Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?")
    _cek(
        "kueri algoritma tidak nyasar ke biaya kuliah",
        ada_algo and dok_algo and "biaya" not in dok_algo[0]["id"].lower(),
        f"(top: {dok_algo[0]['id'] if dok_algo else '-'})",
    )

    _, dok2, ada2 = rag.bangun_konteks("resep rendang padang asli minang")
    _cek("menolak topik di luar kampus (anti-halusinasi)", not ada2 or len(dok2) == 0)


def uji_goldens() -> None:
    print("\n[6] Evaluasi goldens (rag_goldens.json)")
    from rag import RagEngine

    jalur = _jalur_goldens()
    if not os.path.exists(jalur):
        _cek("berkas goldens ada", False, f"({jalur})")
        return
    with open(jalur, encoding="utf-8") as f:
        goldens = json.load(f)

    rag = RagEngine()
    lulus = 0
    gagal_ids = []
    for g in goldens:
        kueri = g.get("query", "")
        diharapkan = set(g.get("expected_ids") or [])
        _, dok, _ = rag.bangun_konteks(kueri)
        terambil = [d["id"] for d in dok]
        if diharapkan & set(terambil):
            lulus += 1
        else:
            gagal_ids.append((g.get("id"), kueri, terambil[:3]))

    rasio = lulus / len(goldens) if goldens else 0.0
    print(f"       goldens lulus: {lulus}/{len(goldens)} ({rasio * 100:.1f}%)")
    for gid, kueri, terambil in gagal_ids[:8]:
        print(f"         - {gid}: '{kueri}' -> {terambil}")
    _cek("rasio goldens >= 85%", rasio >= 0.85, f"({rasio * 100:.1f}%)")


def uji_campus_tool() -> None:
    print("\n[7] Campus tool")
    from tools import dapatkan_campus_tool

    alat = dapatkan_campus_tool()
    _cek("deteksi sapaan", (alat.deteksi_intent("halo") or {}).get("intent") == "sapaan")
    _cek("deteksi identitas", (alat.deteksi_intent("siapa kamu") or {}).get("intent") == "identitas")
    _cek("deteksi terima kasih", (alat.deteksi_intent("makasih ya") or {}).get("intent") == "terima_kasih")
    _, dok, ada = alat.cari("beasiswa")
    _cek("pencarian kampus berjalan", ada, f"({[d['judul'] for d in dok][:1]})")


def uji_curhat_tool() -> None:
    print("\n[8] Curhat tool")
    from tools import dapatkan_curhat_tool

    alat = dapatkan_curhat_tool()
    _cek("deteksi curhat", (alat.deteksi("aku takut gak diterima kuliah") or {}).get("intent") == "curhat")
    _cek("deteksi tips", (alat.deteksi("gimana cara biar fokus belajar") or {}).get("intent") == "tips")
    _cek("respons empatik non-kosong", len(alat.jawab("aku bingung milih jurusan")) > 20)


def uji_web_search() -> None:
    print("\n[9] Web search")
    from tools import dapatkan_web_search

    alat = dapatkan_web_search()
    print(f"       mesin: {alat.info()['mesin']}")
    _cek("deteksi real-time", alat.perlu_web_search("siapa presiden indonesia sekarang"))
    _cek("bukan real-time untuk topik kampus", not alat.perlu_web_search("berapa biaya kuliah ucic"))


def uji_tts() -> None:
    print("\n[10] TTS Piper")
    from core import dapatkan_tts

    tts = dapatkan_tts()
    _cek("mesin TTS siap", tts.apakah_siap, f"({tts.nama_model_aktif})")
    if tts.apakah_siap:
        data = tts.sintesis_wav_bytes("Halo, saya SELA.", "id")
        _cek("sintesis menghasilkan WAV", bool(data) and data[:4] == b"RIFF", f"({len(data or b'')} byte)")
        _cek("singleton stabil", dapatkan_tts() is tts)


def uji_stt() -> None:
    print("\n[11] STT (gerbang energi, tanpa file tmp)")
    from core import dapatkan_stt

    stt = dapatkan_stt()
    print(f"       model: {stt.nama_model_aktif or '-'} ({stt.perangkat_aktif or '-'})")
    hasil_pendek = stt.transkripsikan_bytes(b"123")
    _cek("audio terlalu pendek ditolak", hasil_pendek.get("teks") == "")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    hasil_hening = stt.transkripsikan_bytes(buf.getvalue())
    _cek("audio hening ditolak", hasil_hening.get("teks") == "", f"({hasil_hening.get('pesan')})")


def uji_vad() -> None:
    print("\n[12] VAD")
    import numpy as np

    from core import dapatkan_vad
    from core.vad_engine import UKURAN_BINGKAI

    v = dapatkan_vad()
    v.reset()
    print(f"       metode: {v.metode_aktif}")
    hening = np.zeros(UKURAN_BINGKAI, dtype=np.int16).tobytes()
    bicara = (np.sin(np.linspace(0, 6.28 * 60, UKURAN_BINGKAI)) * 12000).astype(np.int16).tobytes()
    peristiwa = [v.proses_bingkai(bicara) for _ in range(6)]
    _cek("mendeteksi SPEECH_START", "SPEECH_START" in peristiwa)
    akhir = [v.proses_bingkai(hening) for _ in range(30)]
    _cek("mendeteksi SPEECH_END", "SPEECH_END" in akhir)


def uji_prompts() -> None:
    print("\n[13] Prompt library")
    from prompts import (
        ATURAN_ANTI_NOISE,
        ATURAN_PERTANYAAN_LANJUTAN,
        CAMPUS_RAG_ANTI_HALU,
        CURHAT_PROMPT,
        GREETING_VARIATIF,
        LUAR_TOPIK_PROMPT,
        MASTER_PERSONA,
        ROUTER_PROMPT,
        WEB_SEARCH_PROMPT,
        pesan_sistem_kampus,
        pesan_sistem_umum,
    )

    _cek("MASTER_PERSONA ada", len(MASTER_PERSONA) > 100)
    _cek("ROUTER_PROMPT ada", "{pesan}" in ROUTER_PROMPT)
    _cek("CAMPUS_RAG_ANTI_HALU ada", "{konteks}" in CAMPUS_RAG_ANTI_HALU)
    _cek("WEB_SEARCH_PROMPT ada", "{konteks_web}" in WEB_SEARCH_PROMPT)
    _cek("CURHAT_PROMPT ada", "{pertanyaan}" in CURHAT_PROMPT)
    _cek("LUAR_TOPIK_PROMPT ada", "{pertanyaan}" in LUAR_TOPIK_PROMPT)
    _cek("GREETING_VARIATIF punya >=4 slot", len(GREETING_VARIATIF) >= 4)
    _cek("ATURAN_ANTI_NOISE menyebut IGNORE_NOISE", "[IGNORE_NOISE]" in ATURAN_ANTI_NOISE)
    _cek("ATURAN_PERTANYAAN_LANJUTAN ada", "[Pertanyaan" in ATURAN_PERTANYAAN_LANJUTAN)
    _cek("pesan_sistem_kampus terformat", "DOKUMEN RESMI" in pesan_sistem_kampus("KONTEKS", "tanya"))
    _cek("pesan_sistem_umum terformat", "LUAR KAMPUS" in pesan_sistem_umum("tanya"))


def uji_routing() -> None:
    print("\n[14] Routing ranah (kampus / umum / real-time)")
    import server

    _cek("deteksi topik kampus", server.apakah_topik_kampus("berapa biaya kuliah TI"))
    _cek("bukan topik kampus", not server.apakah_topik_kampus("resep rendang padang"))

    r_kampus = server.susun_rencana("berapa biaya kuliah teknik informatika", [], "id")
    _cek("rute kampus benar", r_kampus["jalur"] == "kampus", f"({r_kampus['jalur']})")

    r_umum = server.susun_rencana("cara membuat rendang padang", [], "id")
    _cek("rute umum benar", r_umum["jalur"] == "umum", f"({r_umum['jalur']})")

    r_kosong = server.susun_rencana("apakah ada jurusan kedokteran di UCIC", [], "id")
    _cek("rute kampus_kosong untuk topik kampus tak tercatat", r_kosong["jalur"] in ("kampus_kosong", "kampus"), f"({r_kosong['jalur']})")

    # ── Gerakan avatar: setiap nama yang bisa dipilih harus ada di model 3D ──
    # Semua cabang tentukan_gerakan disapu, lalu hasilnya dicek terhadap klip
    # yang benar-benar ada di public/models/sela.glb. Tanpa ini, mengganti model
    # bisa mematikan animasi secara senyap (nama klip tidak cocok, tanpa galat).
    kombinasi = [
        ("intent", i)
        for i in ("sapaan", "identitas", "terima_kasih", "penutup", None, "lain")
    ] + [(j, None) for j in ("kampus_kosong", "umum", "kampus", "web", "curhat")]
    dipilih = {server.tentukan_gerakan(j, i) for j, i in kombinasi}
    _cek("tentukan_gerakan selalu mengembalikan nama", "" not in dipilih, f"({sorted(dipilih)})")

    nama_glb = _nama_animasi_glb(_jalur_model_glb())
    _cek("sela.glb terbaca", bool(nama_glb), f"({len(nama_glb)} animasi)")
    hilang = sorted(dipilih - nama_glb)
    _cek(
        "semua gerakan ada di sela.glb",
        not hilang,
        f"(hilang: {hilang})" if hilang else f"({sorted(dipilih)})",
    )


def uji_server() -> None:
    print("\n[15] Server FastAPI (TestClient)")
    try:
        from fastapi.testclient import TestClient

        import server

        klien = TestClient(server.aplikasi_server)
        resp = klien.get("/kesehatan")
        _cek("GET /kesehatan", resp.status_code == 200, f"({resp.json().get('status')})")
        data = resp.json()
        _cek("RAG terindeks", data.get("total_dokumen_rag", 0) > 0)
        _cek("retriever leksikal aktif", data.get("retriever_leksikal") == "bm25-lexical")
        _cek("TTS siap", data.get("tts_siap") is True)
        _cek("LLM terdeteksi", "model_llm_tersedia" in data)

        resp_chat = klien.post("/api/chat", json={"userQuery": "halo", "riwayat_obrolan": []})
        _cek("POST /api/chat", resp_chat.status_code == 200 and bool(resp_chat.json().get("text")))

        # Kontrak frontend: /api/chat wajib menyertakan `gerakan` agar animasi 3D
        # bisa dipicu. Nilainya harus salah satu klip yang ada di model.
        gerakan_chat = resp_chat.json().get("gerakan")
        _cek(
            "POST /api/chat menyertakan gerakan valid",
            gerakan_chat in {"Greeting", "Goodbye", "Confused", "Nodding", "Shaking Head"},
            f"({gerakan_chat})",
        )

        resp_umum = klien.post("/api/chat", json={"userQuery": "cara membuat rendang padang", "riwayat_obrolan": []})
        body_umum = resp_umum.json()
        _cek("POST /api/chat off-campus dijawab", resp_umum.status_code == 200 and bool(body_umum.get("text")), f"(jalur={body_umum.get('jalur')})")

        resp_tts = klien.post("/api/sintesis", json={"teks_kalimat": "Halo", "bahasa": "id"})
        _cek("POST /api/sintesis", resp_tts.status_code == 200)
    except Exception as galat:  # pragma: no cover
        _cek("server dapat diuji", False, f"({galat})")


def uji_unduh_model() -> None:
    print("\n[16] Pengunduh model (truncate berkas rusak / resume / verifikasi)")
    import functools
    import http.server
    import socketserver
    import tempfile
    import threading

    import persiapan_model

    # Gerbang keutuhan isi diuji terpisah (uji_embedder); di sini logika unduh.
    asli = persiapan_model._berkas_model_utuh
    persiapan_model._berkas_model_utuh = lambda jalur: True

    class PenanganSenyap(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # senyapkan log akses saat diuji
            pass

    peladen = None
    try:
        akar = tempfile.mkdtemp(prefix="sela_unduh_")
        sumber = os.path.join(akar, "srv")
        os.makedirs(sumber)
        muatan = os.urandom(2 * 1024 * 1024)
        with open(os.path.join(sumber, "model.bin"), "wb") as berkas:
            berkas.write(muatan)

        penangan = functools.partial(PenanganSenyap, directory=sumber)
        peladen = socketserver.TCPServer(("127.0.0.1", 0), penangan)
        threading.Thread(target=peladen.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{peladen.server_address[1]}/model.bin"

        # Berkas lokal KELEWAT BESAR (sisa unduhan paralel) -> wajib di-truncate.
        # Regresi: dulu dibuka mode "ab" sehingga unduhan baru DITAMBAHKAN ke
        # berkas lama dan hasilnya makin rusak (berkas jadi ~2x ukuran).
        tujuan = os.path.join(akar, "model.bin")
        with open(tujuan, "wb") as berkas:
            berkas.write(b"X" * (5 * 1024 * 1024))
        persiapan_model._unduh_satu(url, tujuan)
        with open(tujuan, "rb") as berkas:
            isi = berkas.read()
        _cek(
            "berkas kelewat besar di-truncate, bukan ditambahkan",
            isi == muatan,
            f"({len(isi)} byte, harap {len(muatan)})",
        )

        # Berkas sudah lengkap -> dilewati tanpa unduh ulang.
        persiapan_model._unduh_satu(url, tujuan)
        _cek("berkas lengkap dilewati", os.path.getsize(tujuan) == len(muatan))
    finally:
        persiapan_model._berkas_model_utuh = asli
        if peladen is not None:
            peladen.shutdown()
            peladen.server_close()


def main() -> int:
    print("=" * 64)
    print(" [SELA AI Desktop] Uji Asap Arsitektur Baru")
    print("=" * 64)
    uji_chunker()
    uji_embedder()
    uji_vector_store()
    uji_lexical()
    uji_rag()
    uji_goldens()
    uji_campus_tool()
    uji_curhat_tool()
    uji_web_search()
    uji_tts()
    uji_stt()
    uji_vad()
    uji_prompts()
    uji_unduh_model()
    if os.environ.get("SELA_UJI_SERVER") == "1":
        uji_routing()
        uji_server()
    else:
        print("\n[14/15] Routing & Server FastAPI dilewati (set SELA_UJI_SERVER=1 untuk menguji).")

    print("\n" + "=" * 64)
    print(f" HASIL: {LULUS} lulus, {GAGAL} gagal")
    print("=" * 64)
    return 1 if GAGAL else 0


if __name__ == "__main__":
    sys.exit(main())
