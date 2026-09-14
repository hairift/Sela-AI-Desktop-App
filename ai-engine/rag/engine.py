"""
SELA AI Desktop - Mesin RAG Anti-Halusinasi (Leksikal BM25 + Vektor opsional)
=============================================================================
Menggabungkan chunker jendela kalimat, retriever leksikal BM25, dan (bila
tersedia) embedder semantik bge-m3 + vector store menjadi satu mesin
pencarian yang membumi pada data resmi UCIC.

Anti-halusinasi berlapis:
1. Gerbang cakupan IDF (rag/lexical.py). Dokumen hanya lolos bila cukup banyak
   istilah penting pertanyaan benar-benar tertulis di dokumen. Pertanyaan di
   luar kampus ("resep rendang", "siapa presiden") gagal di sini.
2. Ambang relatif terhadap kandidat teratas, agar dokumen yang jauh lebih lemah
   tidak ikut menjadi konteks.
3. Bila embedder bge-m3 aktif, ambang kosinus absolut 0,72 tetap diberlakukan
   sebagai lapisan tambahan pada jalur semantik.

Sumber data: src/data/ucic_dataset.json (atau ai-engine/data/*.json).
Indeks vektor (opsional): ai-engine/rag/vector_store/faiss_index/.
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .chunker import SentenceWindowChunker
from .embedder import dapatkan_embedder
from .lexical import LexicalIndex
from .vector_store import VectorStore

AMBANG_KOSINUS = 0.72
# Ambang relatif: dokumen dengan skor < 55% skor teratas dianggap tidak relevan.
RASIO_RELATIF = 0.55
# Bobot penggabungan saat embedder semantik aktif (hibrida).
BOBOT_SEMANTIK = 0.5
BOBOT_LEKSIKAL = 0.5

# Topik kampus untuk penautan konteks antar-giliran percakapan.
TOPIK_KAMPUS = [
    "teknik informatika", "sistem informasi", "desain komunikasi visual", "dkv",
    "manajemen", "akuntansi", "bisnis digital", "pendidikan kepelatihan olahraga",
    "manajemen informatika", "manajemen bisnis", "beasiswa", "kip kuliah",
    "biaya kuliah", "biaya pendaftaran", "kelas karyawan", "kelas sore",
    "perpustakaan", "fasilitas", "alumni", "asrama", "syarat pendaftaran",
    "jadwal pendaftaran", "lokasi kampus", "kontak pmb", "rektor", "akreditasi",
    "dosen", "kurikulum", "program studi", "jurusan", "pendaftaran",
]

_INDIKATOR_LANJUTAN = (
    "biaya", "biayanya", "syarat", "syaratnya", "cara", "caranya", "jadwal",
    "jadwalnya", "kelas sore", "kelas karyawan", "akreditasi", "lulusan",
    "prospek", "gelombang", "pembayaran", "gedung", "dimana", "kapan", "berapa",
    "gimana", "bagaimana", "kalau", "terus", "lalu", "itu",
)


class RagEngine:
    """Mesin RAG anti-halusinasi untuk basis pengetahuan UCIC."""

    def __init__(
        self,
        jalur_dataset: Optional[str] = None,
        direktori_indeks: Optional[str] = None,
        ambang: float = AMBANG_KOSINUS,
    ) -> None:
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.akar_ai = os.path.abspath(os.path.join(self.direktori_induk, ".."))

        self.jalur_dataset = jalur_dataset or self._temukan_dataset()
        if direktori_indeks is None:
            direktori_indeks = os.path.join(self.direktori_induk, "vector_store", "faiss_index")
        self.direktori_indeks = direktori_indeks

        self.ambang = ambang
        self.chunker = SentenceWindowChunker(chunk_size=512, overlap=80)
        self.embedder = dapatkan_embedder()
        self.store: Optional[VectorStore] = None

        self.total_dokumen = 0
        self.total_chunk = 0
        self.pesan_status = "belum dibangun"

        # Retriever leksikal dibangun dari dokumen penuh (bukan chunk) agar
        # judul & kata kunci tetap utuh dan bobot medannya bekerja.
        self.dokumen: List[Dict[str, Any]] = self._muat_dokumen()
        self.total_dokumen = len(self.dokumen)
        self.lexical = LexicalIndex(self.dokumen)

        self.muat_atau_bangun()

    # ── Sumber data ───────────────────────────────────────────────────────────
    def _temukan_dataset(self) -> str:
        kandidat = [
            os.path.join(self.akar_ai, "..", "src", "data", "ucic_dataset.json"),
            os.path.join(self.akar_ai, "data", "ucic_dataset.json"),
        ]
        kandidat += sorted(glob.glob(os.path.join(self.akar_ai, "data", "*.json")))
        for jalur in kandidat:
            jalur_abs = os.path.abspath(jalur)
            if os.path.exists(jalur_abs):
                return jalur_abs
        return os.path.abspath(kandidat[0])

    def _muat_dokumen(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.jalur_dataset):
            print(f"[RAG] Dataset tidak ditemukan di {self.jalur_dataset}")
            return []
        with open(self.jalur_dataset, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("data") or data.get("items") or []
        # Lewati dokumen gabungan raksasa (bukan chunk per topik).
        return [
            d for d in data
            if str(d.get("id", "")) not in {"data_lengkap_ucic", "data_lengkap"}
        ]

    # ── Indeks vektor (opsional, hanya bila embedder semantik tersedia) ───────
    def _semantik_aktif(self) -> bool:
        return (
            self.embedder.metode.startswith("sentence-transformers")
            and self.store is not None
            and self.store.ukuran > 0
        )

    def bangun_indeks(self) -> None:
        """Bangun ulang indeks vektor dari dokumen lalu simpan ke disk."""
        chunk_semua = []
        for dok in self.dokumen:
            chunk_semua.extend(self.chunker.bangun_chunk(dok))
        self.total_chunk = len(chunk_semua)

        if not chunk_semua:
            self.pesan_status = "tidak ada chunk yang dibangun"
            self.store = VectorStore(dimensi=self.embedder.dimensi, direktori=self.direktori_indeks)
            return

        vektor = self.embedder.encode([c.teks for c in chunk_semua])
        self.store = VectorStore(dimensi=self.embedder.dimensi, direktori=self.direktori_indeks)
        self.store.tambah(vektor, [c.ke_metadata() for c in chunk_semua])
        self.store.simpan()
        self.pesan_status = (
            f"indeks vektor dibangun: {self.total_chunk} chunk dari {self.total_dokumen} dokumen "
            f"({self.embedder.metode})"
        )
        print(f"[RAG] {self.pesan_status}")

    def muat_atau_bangun(self) -> None:
        """Muat indeks vektor bila embedder semantik siap; jika tidak, lewati."""
        self.store = VectorStore(dimensi=self.embedder.dimensi, direktori=self.direktori_indeks)
        if not self.embedder.metode.startswith("sentence-transformers"):
            # Tanpa bge-m3, jalur vektor tidak dipakai; retriever leksikal BM25
            # yang menangani seluruh pencarian. Indeks lama tidak perlu dibangun.
            self.pesan_status = (
                f"retriever leksikal BM25 siap: {self.total_dokumen} dokumen "
                "(embedder semantik belum aktif)"
            )
            print(f"[RAG] {self.pesan_status}")
            return
        if self.store.muat() and self.store.ukuran > 0:
            if self.store.dimensi != self.embedder.dimensi:
                print(
                    f"[RAG] Dimensi indeks tersimpan ({self.store.dimensi}) tidak cocok dengan "
                    f"embedder aktif ({self.embedder.dimensi}); membangun ulang indeks."
                )
                self.bangun_indeks()
                return
            self.total_chunk = self.store.ukuran
            self.pesan_status = f"indeks vektor dimuat: {self.total_chunk} chunk ({self.store.metode})"
            print(f"[RAG] {self.pesan_status}")
            return
        self.bangun_indeks()

    # ── Penautan konteks multi-giliran ────────────────────────────────────────
    @staticmethod
    def _norm(teks: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(teks).lower())).strip()

    def perkaya_kueri(self, kueri: str, riwayat: Optional[List[Dict[str, str]]]) -> str:
        q = self._norm(kueri)
        if any(topik in q for topik in TOPIK_KAMPUS):
            return kueri
        if not any(ind in q for ind in _INDIKATOR_LANJUTAN):
            return kueri
        for pesan in reversed((riwayat or [])[-4:]):
            teks = self._norm(pesan.get("text", "") or pesan.get("content", ""))
            for topik in TOPIK_KAMPUS:
                if topik in teks:
                    return f"{topik} {kueri}"
        return kueri

    # ── Pencarian ─────────────────────────────────────────────────────────────
    def cari(self, kueri: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Cari dokumen paling relevan dan saring dengan gerbang anti-halusinasi."""
        kandidat = self.lexical.cari(kueri, top_k=max(top_k * 4, 12))
        if not kandidat:
            return []

        if self._semantik_aktif():
            kandidat = self._gabung_semantik(kueri, kandidat)

        kandidat.sort(key=lambda k: (-k["skor"], -k["cakupan"]))
        skor_teratas = kandidat[0]["skor"]
        batas = skor_teratas * RASIO_RELATIF

        hasil: List[Dict[str, Any]] = []
        for k in kandidat:
            if k["skor"] < batas:
                continue
            dok = k["dokumen"]
            hasil.append(
                {
                    "id": dok.get("id", ""),
                    "judul": dok.get("title", ""),
                    "kategori": dok.get("category", ""),
                    "kata_kunci": dok.get("keywords", []),
                    "teks": dok.get("content", ""),
                    "skor": round(float(k["skor"]), 4),
                    "cakupan": round(float(k.get("cakupan", 0.0)), 4),
                }
            )
            if len(hasil) >= top_k:
                break
        return hasil

    def _gabung_semantik(
        self, kueri: str, kandidat: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Gabungkan skor BM25 ternormalisasi dengan kemiripan kosinus bge-m3."""
        try:
            vektor_kueri = self.embedder.encode(kueri)
            pasangan = self.store.cari(vektor_kueri, top_k=max(len(self.dokumen), 8))
        except Exception as galat:  # pragma: no cover - bergantung paket opsional
            print(f"[RAG] Jalur semantik dilewati: {galat}")
            return kandidat

        kosinus_per_dok: Dict[str, float] = {}
        for skor, meta in pasangan:
            id_dok = meta.get("id", "")
            if id_dok and float(skor) > kosinus_per_dok.get(id_dok, -1.0):
                kosinus_per_dok[id_dok] = float(skor)

        if not kosinus_per_dok:
            return kandidat

        skor_leks_max = max((k["skor"] for k in kandidat), default=1.0) or 1.0
        for k in kandidat:
            id_dok = k["dokumen"].get("id", "")
            kos = kosinus_per_dok.get(id_dok, 0.0)
            # Ambang kosinus absolut tetap berlaku bila embedder benar-benar bge-m3.
            if self.embedder.metode.startswith("sentence-transformers") and kos < self.ambang:
                kos = 0.0
            leks_norm = k["skor"] / skor_leks_max
            k["skor"] = (
                BOBOT_SEMANTIK * kos * 100.0 + BOBOT_LEKSIKAL * leks_norm * 100.0
            )
        return kandidat

    def bangun_konteks(
        self, kueri: str, riwayat: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """Bangun teks konteks grounding + daftar dokumen + status ditemukan."""
        kueri_efektif = self.perkaya_kueri(kueri, riwayat)
        dokumen = self.cari(kueri_efektif, top_k=3)
        if not dokumen:
            return "INFORMASI_TIDAK_TERSEDIA_DI_DATASET", [], False
        bagian = [
            f"[DOKUMEN {i}] {d['judul']} (Kategori: {d['kategori']})\n{d['teks']}"
            for i, d in enumerate(dokumen, 1)
        ]
        return "\n\n".join(bagian), dokumen, True

    # ── Info ──────────────────────────────────────────────────────────────────
    def info(self) -> Dict[str, Any]:
        return {
            "total_dokumen": self.total_dokumen,
            "total_chunk": self.total_chunk,
            "embedder": self.embedder.info(),
            "retriever_leksikal": self.lexical.info(),
            "vector_store": self.store.info() if self.store else None,
            "semantik_aktif": self._semantik_aktif(),
            "ambang_kosinus": self.ambang,
            "rasio_relatif": RASIO_RELATIF,
            "pesan": self.pesan_status,
        }


if __name__ == "__main__":
    rag = RagEngine()
    print("Info RAG:", rag.info())
    for q in [
        "Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?",
        "berapa biaya kuliah teknik informatika",
        "fasilitas kampus",
        "resep rendang",
    ]:
        konteks, docs, ada = rag.bangun_konteks(q)
        print(f"\n[{q}] ditemukan={ada}")
        for d in docs:
            print(f"   - {d['judul']} (skor {d['skor']} | cakupan {d['cakupan']})")
