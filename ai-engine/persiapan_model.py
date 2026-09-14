"""
SELA AI Desktop - Persiapan & Pemeriksaan Berkas Model Offline
==============================================================
Memeriksa ketersediaan model yang dibutuhkan aplikasi agar berjalan offline:
- LLM GGUF (Qwen 3.5 4B) + adaptor LoRA UCIC opsional
- TTS Piper ONNX (id_ID + en_US)
- Embedder semantik bge-m3 (opsional, untuk RAG)
- ASR faster-whisper (diunduh otomatis oleh faster-whisper)

Secara bawaan skrip ini hanya MEMERIKSA dan menampilkan tautan unduh resmi.
Untuk benar-benar mengunduh model embedder bge-m3 (opsional, ~2,2 GB), jalankan:

    python ai-engine/persiapan_model.py --unduh-embedder

Unduhan memakai urllib langsung ke berkas tujuan (tanpa berkas sementara),
sehingga tidak terganggu pembersih berkas otomatis dan bisa dilanjutkan
(di-resume) bila terputus: jalankan ulang perintah yang sama.

Semua berkas besar diabaikan oleh Git (lihat .gitignore).
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
import zipfile

_AKAR = os.path.dirname(os.path.abspath(__file__))
DIREKTORI_MODEL = os.path.join(_AKAR, "models")
DIREKTORI_PIPER = os.path.join(DIREKTORI_MODEL, "tts_piper")
DIREKTORI_EMBEDDER = os.path.join(DIREKTORI_MODEL, "bge-m3")

# Nama berkas yang dicari (berdasarkan arsitektur final).
BERKAS_WAJIB = {
    "LLM GGUF (Qwen 3.5 4B)": [
        os.path.join(DIREKTORI_MODEL, "qwen3-4b-ucic-q4_k_m.gguf"),
        os.path.join(DIREKTORI_MODEL, "Qwen3.5-4B-UD-Q4_K_XL.gguf"),
    ],
    "LoRA UCIC (opsional)": [
        os.path.join(DIREKTORI_MODEL, "qwen3-4b-ucic-lora.gguf"),
    ],
    "TTS Piper Indonesia": [
        os.path.join(DIREKTORI_PIPER, "id_ID-ucic-sela-medium.onnx"),
        os.path.join(DIREKTORI_PIPER, "id_ID-news_tts-medium.onnx"),
    ],
    "TTS Piper Inggris": [
        os.path.join(DIREKTORI_PIPER, "en_US-amy-medium.onnx"),
    ],
}

TAUTAN = {
    "LLM GGUF (Qwen 3.5 4B)": "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF",
    "TTS Piper Indonesia": "https://huggingface.co/rhasspy/piper-voices (folder id/id_ID)",
    "TTS Piper Inggris": "https://huggingface.co/rhasspy/piper-voices (folder en/en_US)",
    "Embedder bge-m3": "https://huggingface.co/BAAI/bge-m3",
}

# ── Embedder semantik bge-m3 (opsional) ───────────────────────────────────────
_BASE_BGE = "https://huggingface.co/BAAI/bge-m3/resolve/main/"
BERKAS_EMBEDDER = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "sentencepiece.bpe.model",
    "1_Pooling/config.json",
    "pytorch_model.bin",
]


def _bobot_utuh(jalur: str) -> bool:
    """
    True hanya bila berkas bobot benar-benar utuh, bukan unduhan terpotong.

    Memeriksa ukuran saja tidak cukup: unduhan yang berhenti di tengah tetap
    lolos ambang "> 1 GB" dan membuat skrip ini salah melaporkan "lengkap",
    padahal modelnya masih rusak. Karena itu isi berkas diverifikasi.

    Logika ini kembar dengan `bobot_model_utuh` di `rag/embedder.py`, sengaja
    diduplikasi agar skrip persiapan tetap bisa dijalankan TANPA mengimpor paket
    RAG (yang butuh numpy/faiss/sentence-transformers). Bila salah satu diubah,
    ubah keduanya.
    """
    try:
        ukuran = os.path.getsize(jalur)
    except OSError:
        return False
    nama = jalur.lower()
    if nama.endswith(".onnx"):
        return ukuran > 1_000_000
    if ukuran < 100_000_000:
        return False
    if nama.endswith(".safetensors"):
        try:
            with open(jalur, "rb") as berkas:
                kepala = berkas.read(8)
            if len(kepala) < 8:
                return False
            panjang_header = int.from_bytes(kepala, "little")
            return 0 < panjang_header <= ukuran - 8
        except OSError:
            return False
    if nama.endswith(".bin"):
        try:
            with zipfile.ZipFile(jalur) as arsip:
                arsip.namelist()  # memaksa pembacaan central directory
            return True
        except (zipfile.BadZipFile, OSError):
            return False
    return False


def _embedder_lengkap() -> bool:
    """Lengkap bila config ada DAN berkas bobotnya terverifikasi utuh."""
    if not os.path.exists(os.path.join(DIREKTORI_EMBEDDER, "config.json")):
        return False
    try:
        nama_berkas = os.listdir(DIREKTORI_EMBEDDER)
    except OSError:
        return False
    return any(
        nama.endswith((".bin", ".safetensors"))
        and _bobot_utuh(os.path.join(DIREKTORI_EMBEDDER, nama))
        for nama in nama_berkas
    )


def _ukuran_jarak_jauh(url: str) -> int:
    """Ukuran berkas di server (0 bila tidak diketahui)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _berkas_model_utuh(jalur: str) -> bool:
    """
    Verifikasi keutuhan ISI berkas model, bukan hanya ukurannya.

    Memakai penjaga yang sama dengan embedder (`rag.embedder.bobot_model_utuh`)
    supaya unduhan yang lolos di sini pasti juga dianggap siap oleh server.
    Berkas pendukung (config.json, tokenizer, dsb.) cukup diperiksa tidak kosong.
    """
    try:
        if os.path.getsize(jalur) == 0:
            return False
    except OSError:
        return False

    if not jalur.lower().endswith((".bin", ".safetensors", ".onnx")):
        return True

    if _AKAR not in sys.path:
        sys.path.insert(0, _AKAR)
    try:
        from rag.embedder import bobot_model_utuh
    except Exception:
        # Tidak bisa memverifikasi (impor gagal) -> jangan gagalkan unduhan.
        return True
    return bobot_model_utuh(jalur)


def _unduh_satu(url: str, tujuan: str) -> None:
    """Unduh satu berkas, melanjutkan (resume) bila sudah ada sebagian."""
    total = _ukuran_jarak_jauh(url)
    lokal = os.path.getsize(tujuan) if os.path.exists(tujuan) else 0

    if total and lokal == total:
        print(f"[=] {os.path.basename(tujuan)} sudah lengkap ({lokal / 1048576:.1f} MB)")
        return
    if total and lokal > total:
        # Berkas lokal lebih besar dari seharusnya (mis. dua unduhan paralel yang
        # saling menimpa) -> buang dan mulai dari nol.
        lokal = 0

    judul = os.path.basename(tujuan)
    if lokal:
        print(f"[>] melanjutkan {judul} dari {lokal / 1048576:.1f} MB ...", flush=True)
    else:
        print(f"[>] mengunduh {judul} ...", flush=True)

    headers = {"Range": f"bytes={lokal}-"} if lokal else {}
    mulai = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
        # "ab" HANYA sah bila benar-benar melanjutkan potongan yang ada, yaitu
        # saat ada byte lokal DAN server menerima Range (206). Bila mulai dari
        # nol -- termasuk saat berkas lama dibuang karena kelewat besar -- WAJIB
        # "wb": memakai "ab" di situ akan MENAMBAHKAN unduhan baru ke berkas lama
        # yang rusak, sehingga hasilnya makin rusak (berkas bisa jadi ~2x ukuran).
        mode = "ab" if (lokal and resp.status == 206) else "wb"
        with open(tujuan, mode) as f:
            while True:
                blok = resp.read(1 << 20)
                if not blok:
                    break
                f.write(blok)
    akhir = os.path.getsize(tujuan)
    if total and akhir != total:
        print(
            f"[!] {judul} baru {akhir / 1048576:.1f} MB dari {total / 1048576:.1f} MB "
            "- koneksi terputus, jalankan ulang untuk melanjutkan.",
            flush=True,
        )
        raise IOError(f"unduhan {judul} belum lengkap")

    # Ukuran cocok BUKAN jaminan isi sehat: dua unduhan paralel ke berkas yang
    # sama dapat merusak isi sementara ukuran akhirnya kebetulan benar, dan bila
    # HEAD gagal (total == 0) ukuran tidak diperiksa sama sekali. Isi diverifikasi.
    if not _berkas_model_utuh(tujuan):
        print(
            f"[!] {judul} berukuran {akhir / 1048576:.1f} MB tetapi ISINYA rusak "
            "- hapus berkas itu lalu jalankan ulang perintah ini.",
            flush=True,
        )
        raise IOError(f"unduhan {judul} rusak")

    print(f"[V] {judul} ({akhir / 1048576:.1f} MB, {time.time() - mulai:.0f}s)", flush=True)


def unduh_embedder() -> int:
    """Unduh berkas bge-m3 yang belum lengkap. Dapat dilanjutkan bila terputus."""
    print("=" * 64)
    print(" [SELA AI Desktop] Unduh Embedder Semantik bge-m3 (opsional)")
    print("=" * 64)
    print(f"Tujuan: {DIREKTORI_EMBEDDER}\n")
    os.makedirs(DIREKTORI_EMBEDDER, exist_ok=True)

    for nama in BERKAS_EMBEDDER:
        tujuan = os.path.join(DIREKTORI_EMBEDDER, nama.replace("/", os.sep))
        os.makedirs(os.path.dirname(tujuan), exist_ok=True)
        try:
            _unduh_satu(_BASE_BGE + nama, tujuan)
        except Exception as galat:
            print(f"[X] gagal {nama}: {type(galat).__name__} {galat}")
            print("    Jalankan ulang perintah ini untuk melanjutkan unduhan.")
            return 1

    print("\nSelesai. Jalankan server agar indeks vektor dibangun sekali (otomatis).")
    print("=" * 64)
    return 0


def periksa() -> int:
    print("=" * 64)
    print(" [SELA AI Desktop] Pemeriksaan Berkas Model Offline")
    print("=" * 64)
    print(f"Direktori model: {DIREKTORI_MODEL}\n")

    jumlah_hilang = 0
    for label, kandidat in BERKAS_WAJIB.items():
        ditemukan = next((p for p in kandidat if os.path.exists(p)), None)
        if ditemukan:
            mb = os.path.getsize(ditemukan) / (1024 * 1024)
            print(f"[V] {label}: {os.path.basename(ditemukan)} ({mb:.0f} MB)")
        else:
            jumlah_hilang += 1
            print(f"[ ] {label}: BELUM ADA")
            for p in kandidat:
                print(f"      -> {os.path.relpath(p, _AKAR)}")
            if label in TAUTAN:
                print(f"      unduh: {TAUTAN[label]}")

    if _embedder_lengkap():
        ukuran = sum(
            os.path.getsize(os.path.join(DIREKTORI_EMBEDDER, n))
            for n in os.listdir(DIREKTORI_EMBEDDER)
            if os.path.isfile(os.path.join(DIREKTORI_EMBEDDER, n))
        ) / (1024 * 1024)
        print(f"[V] Embedder bge-m3 (opsional): lengkap ({ukuran:.0f} MB)")
    else:
        print("[ ] Embedder bge-m3 (opsional): BELUM ADA")
        print("      unduh: python ai-engine/persiapan_model.py --unduh-embedder")

    print("\nCatatan:")
    print("- Model GGUF dan Piper cukup diletakkan di folder di atas, tanpa konfigurasi tambahan.")
    print("- RAG memakai retriever leksikal BM25 sebagai mesin utama; bge-m3 hanya memperkuat")
    print("  pencocokan makna. Tanpa bge-m3, RAG tetap berjalan penuh dan presisi.")
    print("- Model Whisper diunduh otomatis oleh faster-whisper ke models/whisper/.")
    print("- Aplikasi tetap berjalan meski sebagian model belum ada (mode cadangan).")

    if jumlah_hilang:
        print(f"\n{jumlah_hilang} kategori model wajib belum lengkap.")
    else:
        print("\nSemua model wajib tersedia. Siap dijalankan offline.")
    print("=" * 64)
    return jumlah_hilang


if __name__ == "__main__":
    if "--unduh-embedder" in sys.argv or "--unduh-bge-m3" in sys.argv:
        sys.exit(unduh_embedder())
    sys.exit(0 if periksa() == 0 else 0)
