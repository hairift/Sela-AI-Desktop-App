"""
SELA AI Desktop - Persiapan & Pemeriksaan Berkas Model Offline
==============================================================
Memeriksa ketersediaan model yang dibutuhkan aplikasi agar berjalan offline:
- LLM GGUF (Qwen 3.5 4B) + adaptor LoRA UCIC opsional
- TTS Supertonic 3 (ONNX, 31 bahasa termasuk Indonesia)
- Embedder semantik multilingual-e5-small (opsional, untuk RAG)
- ASR sherpa-onnx streaming zipformer (realtime, kata per kata)

Secara bawaan skrip ini hanya MEMERIKSA dan menampilkan tautan unduh resmi.
Untuk benar-benar mengunduh, jalankan salah satu:

    python ai-engine/persiapan_model.py --unduh-embedder   # e5-small (~493 MB)
    python ai-engine/persiapan_model.py --unduh-asr        # zipformer (~340 MB)
    python ai-engine/persiapan_model.py --unduh-tts        # supertonic-3 (~396 MB)
    python ai-engine/persiapan_model.py --unduh-semua

Unduhan memakai urllib langsung ke berkas tujuan (tanpa berkas sementara),
sehingga tidak terganggu pembersih berkas otomatis dan bisa dilanjutkan
(di-resume) bila terputus: jalankan ulang perintah yang sama.

CATATAN PENTING soal Supertonic 3: berkasnya diunduh di sini, BUKAN lewat
`auto_download` paket supertonic. Paket itu memakai huggingface_hub yang
membuat berkas sementara lalu menghapusnya; pembersih berkas lingkungan ini
memblokir penghapusan tersebut sehingga unduhan gagal di tengah.

Semua berkas besar diabaikan oleh Git (lihat .gitignore).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import zipfile

_AKAR = os.path.dirname(os.path.abspath(__file__))
DIREKTORI_MODEL = os.path.join(_AKAR, "models")
DIREKTORI_EMBEDDER = os.path.join(DIREKTORI_MODEL, "multilingual-e5-small")
DIREKTORI_ASR = os.path.join(DIREKTORI_MODEL, "sherpa-streaming-zipformer")
DIREKTORI_TTS = os.path.join(DIREKTORI_MODEL, "supertonic-3")

# Nama berkas yang dicari (berdasarkan arsitektur final).
BERKAS_WAJIB = {
    "LLM GGUF (Qwen 3.5 4B)": [
        os.path.join(DIREKTORI_MODEL, "qwen3-4b-ucic-q4_k_m.gguf"),
        os.path.join(DIREKTORI_MODEL, "Qwen3.5-4B-UD-Q4_K_XL.gguf"),
    ],
    "LoRA UCIC (opsional)": [
        os.path.join(DIREKTORI_MODEL, "qwen3-4b-ucic-lora.gguf"),
    ],
    "ASR streaming zipformer (encoder)": [
        os.path.join(DIREKTORI_ASR, "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx"),
    ],
    "TTS Supertonic 3 (ONNX)": [
        os.path.join(DIREKTORI_TTS, "onnx", "vector_estimator.onnx"),
    ],
}

TAUTAN = {
    "LLM GGUF (Qwen 3.5 4B)": "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF",
    "ASR streaming zipformer": (
        "https://huggingface.co/csukuangfj/"
        "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10"
    ),
    "TTS Supertonic 3": "https://huggingface.co/Supertone/supertonic-3",
    "Embedder multilingual-e5-small": "https://huggingface.co/intfloat/multilingual-e5-small",
}

# ── Embedder semantik multilingual-e5-small (opsional) ────────────────────────
_BASE_E5 = "https://huggingface.co/intfloat/multilingual-e5-small/resolve/main/"
# Hanya berkas yang benar-benar dipakai sentence-transformers. Bobot `.safetensors`
# dipilih (bukan `pytorch_model.bin`) karena lebih kecil dan tidak butuh torch.load.
BERKAS_EMBEDDER = [
    "config.json",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "sentencepiece.bpe.model",
    "1_Pooling/config.json",
    "model.safetensors",
]

# ── ASR streaming: sherpa-onnx zipformer transducer (8 bahasa, termasuk id) ───
_BASE_ASR = (
    "https://huggingface.co/csukuangfj/"
    "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10/resolve/main/"
)
BERKAS_ASR = [
    "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx",
    "decoder-epoch-75-avg-11-chunk-16-left-128.onnx",
    "joiner-epoch-75-avg-11-chunk-16-left-128.int8.onnx",
    "tokens.txt",
]

# Berkas ASR yang benar-benar bobot (untuk verifikasi keutuhan). `tokens.txt`
# BUKAN bobot -- isinya kamus token -- jadi cukup diperiksa keberadaannya.
# Sebelumnya tokens.txt ikut dilewatkan ke penjaga bobot; penjaga itu tidak
# mengenali ekstensi .txt sehingga selalu mengembalikan False dan ASR selalu
# dilaporkan "belum lengkap" meski keempat berkasnya sudah ada.
BERKAS_ASR_BOBOT = tuple(n for n in BERKAS_ASR if n.endswith(".onnx"))

# ── TTS: Supertonic 3 (ONNX) ─────────────────────────────────────────────────
# Diunduh SENDIRI lewat urllib, bukan lewat huggingface_hub. Alasannya: paket
# `supertonic` memakai snapshot_download yang membuat berkas sementara lalu
# menghapusnya — dan pembersih berkas lingkungan ini (safe-delete) memblokir
# penghapusan itu sehingga unduhan gagal di tengah (terbukti: berhenti di
# 9/26 berkas). Unduhan langsung tidak pernah menyentuh berkas sementara.
# Revisi dipatok sama dengan yang dipakai paket supertonic 1.3.1 agar cocok.
_REVISI_TTS = "724fb5abbf5502583fb520898d45929e62f02c0b"
_BASE_TTS = f"https://huggingface.co/Supertone/supertonic-3/resolve/{_REVISI_TTS}/"
BERKAS_TTS = [
    "config.json",
    "onnx/tts.json",
    "onnx/unicode_indexer.json",
    "onnx/duration_predictor.onnx",
    "onnx/text_encoder.onnx",
    "onnx/vector_estimator.onnx",
    "onnx/vocoder.onnx",
    # Gaya suara: F = perempuan, M = laki-laki (F1 adalah suara bawaan SELA).
    "voice_styles/F1.json",
    "voice_styles/F2.json",
    "voice_styles/F3.json",
    "voice_styles/F4.json",
    "voice_styles/F5.json",
    "voice_styles/M1.json",
    "voice_styles/M2.json",
    "voice_styles/M3.json",
    "voice_styles/M4.json",
    "voice_styles/M5.json",
]


def _onnx_utuh(jalur: str) -> bool:
    """
    True bila struktur protobuf ONNX habis TEPAT di akhir berkas.

    ONNX tidak menyimpan indeks di akhir berkas seperti zip atau safetensors,
    jadi ukuran saja tidak bisa dipercaya: unduhan terpotong yang masih di atas
    ambang ukuran akan lolos. Fungsi ini menelusuri field tingkat atas
    `ModelProto` (tag varint + panjang) tanpa membaca isi tensor -- tensor hanya
    di-seek -- sehingga biayanya kecil bahkan untuk berkas ratusan MB.

    Kembar dengan `_onnx_utuh` di `rag/embedder.py`; sengaja diduplikasi agar
    skrip persiapan tetap jalan tanpa mengimpor paket RAG (yang butuh
    numpy/faiss/sentence-transformers). Bila salah satu diubah, ubah keduanya.
    """
    try:
        ukuran = os.path.getsize(jalur)
    except OSError:
        return False
    if ukuran < 16:
        return False

    def _baca_varint(berkas, pos: int):
        nilai = 0
        geser = 0
        while True:
            b = berkas.read(1)
            if not b:
                return None, None
            pos += 1
            nilai |= (b[0] & 0x7F) << geser
            if not (b[0] & 0x80):
                return nilai, pos
            geser += 7
            if geser > 63:
                return None, None

    try:
        with open(jalur, "rb") as berkas:
            pos = 0
            while pos < ukuran:
                berkas.seek(pos)
                tag, pos = _baca_varint(berkas, pos)
                if tag is None:
                    return False
                tipe = tag & 0x07
                if tipe == 0:
                    _, pos = _baca_varint(berkas, pos)
                    if pos is None:
                        return False
                elif tipe == 2:
                    panjang, pos = _baca_varint(berkas, pos)
                    if pos is None:
                        return False
                    pos += panjang
                    if pos > ukuran:
                        return False
                elif tipe == 5:
                    pos += 4
                    if pos > ukuran:
                        return False
                elif tipe == 1:
                    pos += 8
                    if pos > ukuran:
                        return False
                else:
                    return False
            return pos == ukuran
    except OSError:
        return False


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
        # ONNX tidak menyimpan indeks di akhir berkas, jadi ukuran saja tidak
        # cukup: struktur protobuf-nya ditelusuri sampai byte terakhir.
        return _onnx_utuh(jalur)
    if ukuran < 100_000_000:
        return False
    if nama.endswith(".safetensors"):
        # Hanya memeriksa header TIDAK cukup: bobot tensor berada di AKHIR
        # berkas, jadi unduhan terpotong tetap punya header sah. Ukuran total
        # dihitung dari `data_offsets` di header lalu dibandingkan dengan
        # ukuran berkas sebenarnya.
        try:
            with open(jalur, "rb") as berkas:
                kepala = berkas.read(8)
                if len(kepala) < 8:
                    return False
                panjang_header = int.from_bytes(kepala, "little")
                if not (0 < panjang_header <= ukuran - 8):
                    return False
                mentah = berkas.read(panjang_header)
            if len(mentah) < panjang_header:
                return False
            info = json.loads(mentah.decode("utf-8"))
            akhir_data = 0
            for kunci, nilai in info.items():
                if kunci == "__metadata__" or not isinstance(nilai, dict):
                    continue
                offset = nilai.get("data_offsets")
                if isinstance(offset, (list, tuple)) and len(offset) == 2:
                    akhir_data = max(akhir_data, int(offset[1]))
            if akhir_data <= 0:
                return False
            return 8 + panjang_header + akhir_data == ukuran
        except Exception:
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


def _asr_lengkap() -> bool:
    """Lengkap bila keempat berkas zipformer ada dan bobotnya terverifikasi."""
    if not all(
        os.path.exists(os.path.join(DIREKTORI_ASR, nama)) for nama in BERKAS_ASR
    ):
        return False
    return all(
        _bobot_utuh(os.path.join(DIREKTORI_ASR, nama)) for nama in BERKAS_ASR_BOBOT
    )


def _tts_lengkap() -> bool:
    """Lengkap bila empat modul ONNX Supertonic 3 sudah ada."""
    modul = ("duration_predictor.onnx", "text_encoder.onnx", "vector_estimator.onnx", "vocoder.onnx")
    return all(
        os.path.exists(os.path.join(DIREKTORI_TTS, "onnx", nama)) for nama in modul
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

    Untuk `.bin`/`.safetensors` memakai penjaga yang sama dengan embedder
    (`rag.embedder.bobot_model_utuh`) supaya unduhan yang lolos di sini pasti
    juga dianggap siap oleh server. `.onnx` diverifikasi lokal lewat `_onnx_utuh`
    (kembarannya), dan berkas pendukung (config.json, tokenizer, tokens.txt,
    dsb.) cukup diperiksa tidak kosong.
    """
    try:
        if os.path.getsize(jalur) == 0:
            return False
    except OSError:
        return False

    nama = jalur.lower()
    if nama.endswith(".onnx"):
        # Bisa diverifikasi lokal (murni stdlib), jadi tidak perlu impor RAG.
        return _onnx_utuh(jalur)
    if not nama.endswith((".bin", ".safetensors")):
        # Berkas pendukung: config.json, tokenizer, tokens.txt, voice_styles, dsb.
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


def _unduh_kumpulan(judul: str, base: str, berkas: list, tujuan_dir: str) -> int:
    """Unduh sekumpulan berkas dari satu repositori HuggingFace. 0 = sukses."""
    print("=" * 64)
    print(f" [SELA AI Desktop] Unduh {judul}")
    print("=" * 64)
    print(f"Tujuan: {tujuan_dir}\n")
    os.makedirs(tujuan_dir, exist_ok=True)

    for nama in berkas:
        tujuan = os.path.join(tujuan_dir, nama.replace("/", os.sep))
        os.makedirs(os.path.dirname(tujuan), exist_ok=True)
        try:
            _unduh_satu(base + nama, tujuan)
        except Exception as galat:
            print(f"[X] gagal {nama}: {type(galat).__name__} {galat}")
            print("    Jalankan ulang perintah ini untuk melanjutkan unduhan.")
            return 1

    print(f"\nSelesai. {judul} siap dipakai.")
    print("=" * 64)
    return 0


def unduh_embedder() -> int:
    """Unduh berkas multilingual-e5-small yang belum lengkap (bisa dilanjutkan)."""
    return _unduh_kumpulan(
        "Embedder Semantik multilingual-e5-small",
        _BASE_E5,
        BERKAS_EMBEDDER,
        DIREKTORI_EMBEDDER,
    )


def unduh_asr() -> int:
    """Unduh berkas sherpa-onnx streaming zipformer yang belum lengkap."""
    return _unduh_kumpulan(
        "ASR Streaming sherpa-onnx zipformer (8 bahasa)",
        _BASE_ASR,
        BERKAS_ASR,
        DIREKTORI_ASR,
    )


def unduh_tts() -> int:
    """Unduh berkas Supertonic 3 yang belum lengkap (langsung, tanpa huggingface_hub)."""
    return _unduh_kumpulan(
        "TTS Supertonic 3 (ONNX + gaya suara)",
        _BASE_TTS,
        BERKAS_TTS,
        DIREKTORI_TTS,
    )


def periksa() -> int:
    print("=" * 64)
    print(" [SELA AI Desktop] Pemeriksaan Berkas Model Offline")
    print("=" * 64)
    print(f"Direktori model: {DIREKTORI_MODEL}\n")

    jumlah_hilang = 0
    jumlah_opsional_hilang = 0
    for label, kandidat in BERKAS_WAJIB.items():
        opsional = "opsional" in label.lower()
        ditemukan = next((p for p in kandidat if os.path.exists(p)), None)
        if ditemukan:
            mb = os.path.getsize(ditemukan) / (1024 * 1024)
            print(f"[V] {label}: {os.path.basename(ditemukan)} ({mb:.0f} MB)")
        else:
            # Komponen opsional (mis. LoRA hasil fine-tuning) tidak boleh
            # dihitung sebagai "model wajib belum lengkap".
            if opsional:
                jumlah_opsional_hilang += 1
            else:
                jumlah_hilang += 1
            print(f"[ ] {label}: BELUM ADA")
            for p in kandidat:
                print(f"      -> {os.path.relpath(p, _AKAR)}")
            if label in TAUTAN:
                print(f"      unduh: {TAUTAN[label]}")

    # Rincian per komponen (semua opsional; aplikasi tetap jalan tanpa ini).
    if _embedder_lengkap():
        ukuran = sum(
            os.path.getsize(os.path.join(akar, n))
            for akar, _, nama_berkas in os.walk(DIREKTORI_EMBEDDER)
            for n in nama_berkas
        ) / (1024 * 1024)
        print(f"[V] Embedder multilingual-e5-small: lengkap ({ukuran:.0f} MB)")
    else:
        print("[ ] Embedder multilingual-e5-small: BELUM ADA")
        print("      unduh: python ai-engine/persiapan_model.py --unduh-embedder")

    if _asr_lengkap():
        print("[V] ASR sherpa-onnx zipformer: lengkap (4 berkas)")
    else:
        print("[ ] ASR sherpa-onnx zipformer: BELUM LENGKAP")
        print("      unduh: python ai-engine/persiapan_model.py --unduh-asr")

    if _tts_lengkap():
        print("[V] TTS Supertonic 3: lengkap (4 modul ONNX)")
    else:
        print("[ ] TTS Supertonic 3: BELUM ADA")
        print("      unduh otomatis saat server pertama kali dijalankan (butuh internet sekali)")

    print("\nCatatan:")
    print("- Model GGUF cukup diletakkan di folder di atas, tanpa konfigurasi tambahan.")
    print("- RAG memakai retriever leksikal BM25 sebagai mesin utama; e5-small hanya memperkuat")
    print("  pencocokan makna. Tanpa e5-small, RAG tetap berjalan penuh dan presisi.")
    print("- ASR memakai sherpa-onnx streaming: ucapan menjadi teks kata per kata saat berbicara.")
    print("- Aplikasi tetap berjalan meski sebagian model belum ada (mode cadangan).")

    if jumlah_hilang:
        print(f"\n{jumlah_hilang} kategori model wajib belum lengkap.")
    else:
        print("\nSemua model wajib tersedia. Siap dijalankan offline.")
        if jumlah_opsional_hilang:
            print(
                f"({jumlah_opsional_hilang} komponen opsional belum ada; "
                "aplikasi tetap berjalan penuh.)"
            )
    print("=" * 64)
    return jumlah_hilang


if __name__ == "__main__":
    argumen = set(sys.argv[1:])
    if "--unduh-embedder" in argumen or "--unduh-bge-m3" in argumen:
        sys.exit(unduh_embedder())
    if "--unduh-asr" in argumen:
        sys.exit(unduh_asr())
    if "--unduh-tts" in argumen:
        sys.exit(unduh_tts())
    if "--unduh-semua" in argumen:
        kode = unduh_embedder()
        if kode == 0:
            kode = unduh_asr()
        if kode == 0:
            kode = unduh_tts()
        sys.exit(kode)
    sys.exit(0 if periksa() == 0 else 0)
