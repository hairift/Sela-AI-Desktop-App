"""
SELA AI Desktop - Embedder Teks
===============================
Jalur utama: BAAI/bge-m3 via sentence-transformers (multibahasa, 1024 dimensi),
vektor dinormalisasi L2 sehingga kemiripan kosinus = dot product.

Urutan sumber model:
1. Folder lokal proyek `ai-engine/models/bge-m3/` (paling andal, tanpa jaringan).
2. Id HuggingFace "BAAI/bge-m3" (diunduh sekali lalu di-cache).

Jalur cadangan: embedder hashing mandiri (tanpa unduhan model) yang tetap
menghasilkan vektor bermakna secara leksikal, sehingga pencarian vektor tetap
berjalan meski bge-m3 belum tersedia. Saat cadangan aktif, RAG tetap presisi
karena retriever leksikal BM25 (rag/lexical.py) yang memimpin pencarian.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
import zipfile
from typing import Any, List, Optional

NAMA_MODEL_EMBED = "BAAI/bge-m3"
_DIM_CADANGAN = 512
# Folder model lokal dalam proyek (diunduh oleh persiapan model / skrip unduh).
_DIR_LOKAL = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "bge-m3")
)
# Ukuran minimum agar sebuah berkas wajar disebut bobot model penuh (byte).
_AMBANG_BOBOT_MIN = 100_000_000


def bobot_model_utuh(jalur: str) -> bool:
    """
    True hanya bila berkas bobot model benar-benar UTUH, bukan unduhan terpotong.

    Memeriksa ukuran saja tidak cukup: unduhan bge-m3 yang berhenti di tengah
    (mis. 1,25 GB dari 2,27 GB) tetap lolos ambang "> 1 GB", lalu gagal dimuat
    dengan galat `PytorchStreamReader ... checkpoint file is corrupted`.
    Karena itu ISI berkas diverifikasi, bukan hanya ukurannya:

    - `.safetensors`: 8 byte pertama (little-endian) = panjang header metadata.
      Utuh bila 8 + panjang header tidak melewati ukuran berkas.
    - `.bin`        : arsip zip PyTorch (`torch.save`). Central directory saja
      TIDAK cukup — lihat catatan di cabang `.bin` di bawah; isi entri kunci
      ikut dibaca utuh.
    - `.onnx`       : protobuf tanpa indeks di akhir, jadi cukup ambang ukuran.
    """
    try:
        ukuran = os.path.getsize(jalur)
    except OSError:
        return False

    nama = jalur.lower()
    if nama.endswith(".onnx"):
        return ukuran > 1_000_000
    if ukuran < _AMBANG_BOBOT_MIN:
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
        # Membaca central directory saja TIDAK cukup. Dua penulis paralel (mis.
        # dua unduhan berjalan bersamaan ke berkas yang sama) dapat merusak ISI
        # berkas sementara central directory di akhir tetap terbaca -- penjaga
        # lalu meloloskan berkas rusak, dan server membuang waktu memuat
        # checkpoint yang pasti gagal. Karena itu entri kecil yang wajib ada
        # (pickle struktur) dibaca UTUH sebagai bukti isi benar-benar sehat.
        try:
            with zipfile.ZipFile(jalur) as arsip:
                nama_entri = arsip.namelist()
                if not nama_entri:
                    return False
                sasaran = [n for n in nama_entri if n.endswith("data.pkl")]
                if not sasaran:
                    sasaran = [n for n in nama_entri if n.endswith(".pkl")]
                for entri in sasaran:
                    with arsip.open(entri) as berkas_entri:
                        while berkas_entri.read(1 << 20):
                            pass
            return True
        except Exception:
            # BadZipFile (termasuk CRC-32 tidak cocok), galat zlib, EOF di
            # tengah entri, dsb. Semuanya berarti "tidak utuh" -> jangan dipakai.
            return False
    return False


class Embedder:
    """Pembungkus embedder dengan jalur bge-m3 dan cadangan hashing."""

    _instance: Optional["Embedder"] = None
    _kunci_singleton = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "Embedder":
        if cls._instance is None:
            with cls._kunci_singleton:
                if cls._instance is None:
                    instansi = super().__new__(cls)
                    instansi._sudah_disiapkan = False
                    cls._instance = instansi
        return cls._instance

    def __init__(self, nama_model: str = NAMA_MODEL_EMBED, perangkat: str = "cpu") -> None:
        if getattr(self, "_sudah_disiapkan", False):
            return
        self._sudah_disiapkan = True

        self.nama_model = nama_model
        self.perangkat = perangkat
        self._model = None
        self.metode = "hashing"
        self.dimensi = _DIM_CADANGAN
        self._muat()

    def _muat(self) -> None:
        galat_terakhir: Optional[Exception] = None
        kandidat = self._kandidat_sumber()
        if not kandidat:
            galat_terakhir = RuntimeError(
                "bobot bge-m3 lokal belum lengkap/terverifikasi, dan unduhan "
                "HuggingFace tidak diaktifkan (SELA_EMBEDDER_HF != 1)"
            )
        for sumber, batas in kandidat:
            model, galat = self._muat_dengan_batas(sumber, batas)
            if model is not None:
                self._model = model
                self.dimensi = int(model.get_sentence_embedding_dimension())
                label = "lokal" if os.path.isdir(sumber) else "HuggingFace"
                self.metode = f"sentence-transformers:{self.nama_model} ({label})"
                print(f"[Embedder] {self.nama_model} siap ({self.dimensi} dimensi, {label}).")
                return
            galat_terakhir = galat

        self._model = None
        self.dimensi = _DIM_CADANGAN
        self.metode = "hashing-cadangan"
        print(
            f"[Embedder] bge-m3 tidak tersedia ({galat_terakhir}). "
            "Memakai embedder hashing cadangan; retriever leksikal BM25 tetap memimpin."
        )

    def _muat_dengan_batas(self, sumber: str, batas_detik: int) -> tuple:
        """
        Muat model di thread terpisah dengan batas waktu, agar proses startup
        tidak pernah menggantung saat unduhan jaringan macet.
        """
        hasil: dict = {}

        def _kerja() -> None:
            try:
                from sentence_transformers import SentenceTransformer

                hasil["model"] = SentenceTransformer(sumber, device=self.perangkat)
            except Exception as galat:  # pragma: no cover - bergantung paket opsional
                hasil["galat"] = galat

        pekerja = threading.Thread(target=_kerja, daemon=True)
        pekerja.start()
        pekerja.join(batas_detik)
        if pekerja.is_alive():
            return None, TimeoutError(f"memuat '{sumber}' melebihi {batas_detik} detik")
        return hasil.get("model"), hasil.get("galat")

    @staticmethod
    def _bobot_lokal_utuh(direktori: str) -> bool:
        """
        True bila folder memuat berkas bobot model yang lolos verifikasi keutuhan.

        Delegasi ke `bobot_model_utuh`, sehingga unduhan yang belum tuntas tidak
        pernah dianggap siap dan tidak memicu galat 'checkpoint is corrupted'.
        """
        try:
            nama_berkas = os.listdir(direktori)
        except OSError:
            return False
        return any(
            nama.endswith((".bin", ".safetensors", ".onnx"))
            and bobot_model_utuh(os.path.join(direktori, nama))
            for nama in nama_berkas
        )

    @classmethod
    def _kandidat_sumber(cls) -> List[tuple]:
        """
        (sumber, batas_detik) berurutan: folder lokal lebih dulu (tanpa jaringan).

        Unduhan langsung dari HuggingFace hanya dicoba bila diminta eksplisit
        lewat SELA_EMBEDDER_HF=1, supaya startup server tidak pernah menggantung
        di jaringan. Untuk mengunduh model, jalankan skrip persiapan model.
        """
        kandidat: List[tuple] = []
        if os.path.exists(os.path.join(_DIR_LOKAL, "config.json")) and cls._bobot_lokal_utuh(_DIR_LOKAL):
            kandidat.append((_DIR_LOKAL, 180))
        if os.environ.get("SELA_EMBEDDER_HF") == "1":
            kandidat.append((NAMA_MODEL_EMBED, 600))
        return kandidat

    # ── Cadangan hashing ──────────────────────────────────────────────────────
    @staticmethod
    def _tokenisasi(teks: str) -> List[str]:
        teks = teks.lower()
        kata = re.findall(r"[a-z0-9]+", teks)
        # Tambahkan trigram karakter untuk menangkap variasi morfologi.
        gram = [teks[i : i + 3] for i in range(len(teks) - 2)]
        return kata + gram

    def _encode_hashing(self, teks_list: List[str]) -> "Any":
        import numpy as np

        matriks = np.zeros((len(teks_list), self.dimensi), dtype="float32")
        for baris, teks in enumerate(teks_list):
            token = self._tokenisasi(teks or "")
            if not token:
                continue
            freq: dict[str, int] = {}
            for t in token:
                freq[t] = freq.get(t, 0) + 1
            for t, c in freq.items():
                h = int(hashlib.blake2b(t.encode("utf-8"), digest_size=8).hexdigest(), 16)
                idx = h % self.dimensi
                tanda = 1.0 if (h >> 61) & 1 else -1.0
                matriks[baris, idx] += tanda * (1.0 + math.log(c))
            norma = float(np.linalg.norm(matriks[baris]))
            if norma > 0:
                matriks[baris] /= norma
        return matriks

    # ── API publik ────────────────────────────────────────────────────────────
    def encode(self, teks: "Any", normalisasi: bool = True) -> "Any":
        """Ubah teks (str atau list[str]) menjadi matriks vektor float32."""
        import numpy as np

        if isinstance(teks, str):
            teks_list = [teks]
            satu = True
        else:
            teks_list = list(teks)
            satu = False

        if not teks_list:
            return np.zeros((0, self.dimensi), dtype="float32")

        if self._model is not None:
            vektor = self._model.encode(
                teks_list, normalize_embeddings=normalisasi, convert_to_numpy=True
            ).astype("float32")
        else:
            vektor = self._encode_hashing(teks_list)
        return vektor[0] if satu else vektor

    def info(self) -> dict:
        return {"metode": self.metode, "dimensi": self.dimensi, "nama_model": self.nama_model}


def dapatkan_embedder() -> Embedder:
    """Ambil instansi tunggal Embedder."""
    return Embedder()


if __name__ == "__main__":
    emb = dapatkan_embedder()
    print("Status Embedder:", emb.info())
    v = emb.encode(["biaya kuliah teknik informatika", "harga ukt prodi informatika"])
    print("Bentuk vektor:", getattr(v, "shape", None))
