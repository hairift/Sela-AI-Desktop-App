"""
SELA AI Desktop - Chunker Berbasis Jendela Kalimat (Sentence Window)
====================================================================
Memecah dokumen panjang menjadi potongan berukuran tetap dengan tumpang
tindih, memakai batas kalimat sebagai pemisah agar tidak memotong di tengah
gagasan. Perilaku ini meniru SentenceWindowNodeParser milik llama-index
(chunk_size = 512 token, overlap = 80 token) namun diimplementasikan mandiri
agar RAG tetap berjalan tanpa dependensi llama-index.

Token dihitung per kata (whitespace). Ukuran default 512/80 sesuai target
arsitektur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_POLA_KALIMAT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class Chunk:
    """Satu potongan teks siap di-embed dan dicari."""

    teks: str
    id: str = ""
    judul: str = ""
    kategori: str = ""
    kata_kunci: List[str] = field(default_factory=list)
    indeks: int = 0

    def ke_metadata(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "judul": self.judul,
            "kategori": self.kategori,
            "kata_kunci": self.kata_kunci,
            "indeks": self.indeks,
            "teks": self.teks,
        }


class SentenceWindowChunker:
    """Pemecah teks berbasis jendela kalimat dengan tumpang tindih."""

    def __init__(self, chunk_size: int = 512, overlap: int = 80) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap harus lebih kecil dari chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    @staticmethod
    def _pecah_kalimat(teks: str) -> List[str]:
        bagian = [k.strip() for k in _POLA_KALIMAT.split(teks) if k and k.strip()]
        return bagian or ([teks.strip()] if teks.strip() else [])

    def potong(self, teks: str) -> List[str]:
        """Pecah teks menjadi beberapa potongan dengan tumpang tindih token."""
        kalimat = self._pecah_kalimat(teks)
        if not kalimat:
            return []

        potongan: List[str] = []
        jendela: List[str] = []
        panjang = 0

        for kalimat_i in kalimat:
            n_kata = len(kalimat_i.split())
            # Kalimat tunggal yang lebih panjang dari chunk_size dipecah paksa.
            if n_kata > self.chunk_size:
                if jendela:
                    potongan.append(" ".join(jendela))
                    jendela, panjang = [], 0
                kata = kalimat_i.split()
                for i in range(0, len(kata), self.chunk_size - self.overlap):
                    potongan.append(" ".join(kata[i : i + self.chunk_size]))
                continue

            if panjang + n_kata > self.chunk_size and jendela:
                potongan.append(" ".join(jendela))
                # Tumpang tindih: pertahankan ekor jendela sebelumnya.
                ekor: List[str] = []
                total = 0
                for k in reversed(jendela):
                    total += len(k.split())
                    if total > self.overlap:
                        break
                    ekor.insert(0, k)
                jendela = ekor
                panjang = sum(len(k.split()) for k in jendela)

            jendela.append(kalimat_i)
            panjang += n_kata

        if jendela:
            potongan.append(" ".join(jendela))
        return [p.strip() for p in potongan if p.strip()]

    def bangun_chunk(self, dokumen: Dict[str, Any]) -> List[Chunk]:
        """Ubah satu dokumen dataset menjadi daftar Chunk."""
        konten = (dokumen.get("content") or dokumen.get("konten") or "").strip()
        judul = dokumen.get("title") or dokumen.get("judul") or ""
        kategori = dokumen.get("category") or dokumen.get("kategori") or ""
        kata_kunci = dokumen.get("keywords") or dokumen.get("kata_kunci") or []
        id_dok = str(dokumen.get("id") or judul or "")

        # Judul + kata kunci disisipkan ke awal potongan agar konteks ikut terbawa.
        awalan = judul
        if kata_kunci:
            awalan = f"{judul} ({', '.join(str(k) for k in kata_kunci)})"

        hasil: List[Chunk] = []
        for i, potongan in enumerate(self.potong(konten)):
            teks = f"{awalan}. {potongan}".strip()
            hasil.append(
                Chunk(
                    teks=teks,
                    id=id_dok,
                    judul=judul,
                    kategori=kategori,
                    kata_kunci=[str(k) for k in kata_kunci],
                    indeks=i,
                )
            )
        return hasil


def potong_teks(teks: str, chunk_size: int = 512, overlap: int = 80) -> List[str]:
    """Fungsi bantu cepat untuk memotong satu teks."""
    return SentenceWindowChunker(chunk_size=chunk_size, overlap=overlap).potong(teks)


if __name__ == "__main__":
    chunker = SentenceWindowChunker(chunk_size=512, overlap=80)
    contoh = "UCIC berdiri sejak lama. " * 200
    hasil = chunker.potong(contoh)
    print(f"Jumlah potongan: {len(hasil)}")
    print("Panjang potongan (kata):", [len(p.split()) for p in hasil][:5])
