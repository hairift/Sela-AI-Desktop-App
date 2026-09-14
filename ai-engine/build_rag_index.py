"""
SELA AI Desktop - Pembangun Indeks RAG Vektor
=============================================
Membaca dataset resmi UCIC (src/data/ucic_dataset.json atau ai-engine/data/*.json),
memotongnya dengan chunker jendela kalimat (512 token, overlap 80), meng-embed
dengan bge-m3, lalu menyimpan indeks FAISS ke:

    ai-engine/rag/vector_store/faiss_index/

Jalankan sekali (atau setiap kali dataset berubah):
    python ai-engine/build_rag_index.py
"""

from __future__ import annotations

import os
import sys
import time

_AKAR = os.path.dirname(os.path.abspath(__file__))
if _AKAR not in sys.path:
    sys.path.insert(0, _AKAR)

from rag import RagEngine  # noqa: E402


def main() -> None:
    print("=" * 64)
    print(" [SELA] Membangun indeks RAG vektor (FAISS + bge-m3)")
    print("=" * 64)
    mulai = time.time()
    rag = RagEngine()
    print(f"Sumber dataset : {rag.jalur_dataset}")
    print(f"Embedder       : {rag.embedder.metode}")
    rag.bangun_indeks()
    print(f"Total dokumen  : {rag.total_dokumen}")
    print(f"Total chunk    : {rag.total_chunk}")
    print(f"Vector store   : {rag.store.metode if rag.store else '-'}")
    print(f"Direktori      : {rag.direktori_indeks}")
    print(f"Selesai dalam  : {time.time() - mulai:.1f} detik")

    # Uji cepat pencarian.
    for q in ["biaya kuliah teknik informatika", "beasiswa", "lokasi kampus"]:
        _, dok, ada = rag.bangun_konteks(q)
        top = dok[0]["judul"] if dok else "-"
        print(f"  uji '{q}' -> ditemukan={ada} top='{top}'")


if __name__ == "__main__":
    main()
