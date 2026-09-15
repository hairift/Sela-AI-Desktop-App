"""
SELA AI Desktop - Embedder Teks
===============================
Jalur utama: intfloat/multilingual-e5-small via sentence-transformers
(multibahasa, 384 dimensi), vektor dinormalisasi L2 sehingga kemiripan
kosinus = dot product.

Model ini menggantikan bge-m3 (1024 dimensi, ~2,2 GB). Tugasnya hanya
MEMPERKUAT RAG: mesin pencari utama tetap retriever leksikal BM25 di
rag/lexical.py, sehingga ukuran model yang jauh lebih kecil (470 MB) tidak
menurunkan presisi jawaban secara berarti.

KONVENSI E5 (wajib): model e5 dilatih dengan prefiks tugas. Kueri diberi
awalan "query: " dan dokumen diberi awalan "passage: ". Tanpa prefiks ini
kualitas pencocokan makna turun nyata. Prefiks HANYA ditambahkan pada jalur
model sungguhan (bukan pada embedder hashing cadangan).

Urutan sumber model:
1. Folder lokal proyek `ai-engine/models/multilingual-e5-small/`
   (paling andal, tanpa jaringan).
2. Id HuggingFace "intfloat/multilingual-e5-small" (unduh sekali lalu di-cache).

Jalur cadangan: embedder hashing mandiri (tanpa unduhan model) yang tetap
menghasilkan vektor bermakna secara leksikal, sehingga pencarian vektor tetap
berjalan meski e5-small belum tersedia. Saat cadangan aktif, RAG tetap presisi
karena retriever leksikal BM25 (rag/lexical.py) yang memimpin pencarian.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import zipfile
from typing import Any, List, Optional

NAMA_MODEL_EMBED = "intfloat/multilingual-e5-small"
_DIM_CADANGAN = 384
# Folder model lokal dalam proyek (diunduh oleh persiapan model / skrip unduh).
_DIR_LOKAL = os.path.abspath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "models", "multilingual-e5-small"
    )
)
# Ukuran minimum agar sebuah berkas wajar disebut bobot model penuh (byte).
_AMBANG_BOBOT_MIN = 100_000_000

# Prefiks tugas E5. Wajib untuk model keluarga e5.
PREFIKS_KUERI = "query: "
PREFIKS_DOKUMEN = "passage: "


def _onnx_utuh(jalur: str) -> bool:
    """
    True bila struktur protobuf ONNX habis TEPAT di akhir berkas.

    ONNX tidak menyimpan indeks di akhir berkas seperti zip atau safetensors,
    jadi ukuran saja tidak bisa dipercaya: unduhan yang terpotong tetapi masih
    di atas ambang ukuran akan lolos dan baru ketahuan saat model dimuat.

    Fungsi ini menelusuri field tingkat atas `ModelProto` (tag varint + panjang)
    tanpa pernah membaca isi tensor -- tensor hanya di-seek -- sehingga biayanya
    tetap kecil bahkan untuk berkas ratusan MB. Bila ada panjang field yang
    melewati akhir berkas, berarti berkas terpotong.
    """
    try:
        ukuran = os.path.getsize(jalur)
    except OSError:
        return False
    if ukuran < 16:
        return False

    def _baca_varint(berkas, pos: int):
        """Kembalikan (nilai, pos_baru) atau (None, None) bila berkas habis."""
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
                if tipe == 0:  # varint
                    _, pos = _baca_varint(berkas, pos)
                    if pos is None:
                        return False
                elif tipe == 2:  # length-delimited
                    panjang, pos = _baca_varint(berkas, pos)
                    if pos is None:
                        return False
                    pos += panjang
                    if pos > ukuran:
                        return False
                elif tipe == 5:  # 32-bit
                    pos += 4
                    if pos > ukuran:
                        return False
                elif tipe == 1:  # 64-bit
                    pos += 8
                    if pos > ukuran:
                        return False
                else:
                    # Tipe 3/4 (start/end group) tidak dipakai protobuf modern.
                    return False
            return pos == ukuran
    except OSError:
        return False


def bobot_model_utuh(jalur: str) -> bool:
    """
    True hanya bila berkas bobot model benar-benar UTUH, bukan unduhan terpotong.

    Memeriksa ukuran saja tidak cukup: unduhan yang berhenti di tengah
    (mis. 1,25 GB dari 2,27 GB pada era bge-m3) tetap lolos ambang "> 1 GB",
    lalu gagal dimuat dengan galat `PytorchStreamReader ... checkpoint file is
    corrupted`. Karena itu ISI berkas diverifikasi, bukan hanya ukurannya:

    - `.safetensors`: 8 byte pertama (little-endian) = panjang header metadata.
      Hanya memeriksa header TIDAK cukup: bobot tensor berada DI AKHIR berkas,
      jadi unduhan yang terpotong tetap punya header yang sah. Karena itu
      ukuran total yang diharapkan dihitung dari `data_offsets` di header
      (8 + panjang header + offset data terbesar) lalu dibandingkan dengan
      ukuran berkas sebenarnya.
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
        return _onnx_utuh(jalur)
    if ukuran < _AMBANG_BOBOT_MIN:
        return False
    if nama.endswith(".safetensors"):
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
            # JSON rusak, header tidak konsisten, atau berkas terpotong.
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
    """Pembungkus embedder dengan jalur multilingual-e5-small dan cadangan hashing."""

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
                "bobot multilingual-e5-small lokal belum lengkap/terverifikasi, dan unduhan "
                "HuggingFace tidak diaktifkan (SELA_EMBEDDER_HF != 1)"
            )
        for sumber, batas in kandidat:
            model, galat = self._muat_dengan_batas(sumber, batas)
            if model is not None:
                self._model = model
                # sentence-transformers 6.x mengganti nama metode ini; dukung
                # keduanya agar tidak memicu FutureWarning di versi baru.
                pengukur = getattr(model, "get_embedding_dimension", None) or getattr(
                    model, "get_sentence_embedding_dimension"
                )
                self.dimensi = int(pengukur())
                label = "lokal" if os.path.isdir(sumber) else "HuggingFace"
                self.metode = f"sentence-transformers:{self.nama_model} ({label})"
                print(f"[Embedder] {self.nama_model} siap ({self.dimensi} dimensi, {label}).")
                return
            galat_terakhir = galat

        self._model = None
        self.dimensi = _DIM_CADANGAN
        self.metode = "hashing-cadangan"
        print(
            f"[Embedder] multilingual-e5-small tidak tersedia ({galat_terakhir}). "
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
    def _beri_prefiks(self, teks_list: List[str], jenis: str) -> List[str]:
        """
        Tambahkan prefiks tugas E5 ("query: " / "passage: ") bila belum ada.

        Model keluarga e5 dilatih dengan prefiks ini; menghilangkannya membuat
        pencocokan makna menurun. Prefiks hanya relevan untuk model sungguhan,
        jadi pemanggil cadangan hashing tidak melewati jalur ini.
        """
        prefiks = PREFIKS_KUERI if jenis == "query" else PREFIKS_DOKUMEN
        hasil: List[str] = []
        for teks in teks_list:
            bersih = (teks or "").lstrip()
            # Buang prefiks apa pun yang sudah ada -- benar maupun salah peran --
            # lalu pasang prefiks yang sesuai. Prefiks menandai PERAN teks, jadi
            # prefiks peran yang keliru harus ditimpa, bukan dibiarkan; menumpuknya
            # ("query: passage: x") justru memberi penanda ganda yang membingungkan
            # model. Teks tanpa prefiks tetap mendapat prefiks yang benar.
            for p in (PREFIKS_KUERI, PREFIKS_DOKUMEN):
                if bersih.startswith(p):
                    bersih = bersih[len(p):].lstrip()
                    break
            hasil.append(prefiks + bersih)
        return hasil

    def encode(self, teks: "Any", normalisasi: bool = True, jenis: str = "passage") -> "Any":
        """
        Ubah teks (str atau list[str]) menjadi matriks vektor float32.

        ``jenis`` menentukan prefiks tugas E5: "query" untuk pertanyaan pengguna,
        "passage" (bawaan) untuk dokumen/chunk yang diindeks. Nilai lain
        diperlakukan sebagai "passage".
        """
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
                self._beri_prefiks(teks_list, jenis),
                normalize_embeddings=normalisasi,
                convert_to_numpy=True,
            ).astype("float32")
        else:
            vektor = self._encode_hashing(teks_list)
        return vektor[0] if satu else vektor

    def encode_kueri(self, teks: "Any", normalisasi: bool = True) -> "Any":
        """Pintasan `encode(..., jenis="query")` untuk kueri pengguna."""
        return self.encode(teks, normalisasi=normalisasi, jenis="query")

    def encode_dokumen(self, teks: "Any", normalisasi: bool = True) -> "Any":
        """Pintasan `encode(..., jenis="passage")` untuk dokumen yang diindeks."""
        return self.encode(teks, normalisasi=normalisasi, jenis="passage")

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
