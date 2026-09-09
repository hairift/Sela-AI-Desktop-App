"""
SELA AI Desktop - Skrip Persiapan & Pemeriksaan Model GGUF Offline
Memeriksa ketersediaan model Qwen 2.5 GGUF dan menyediakan tautan unduh model resmi HuggingFace.
"""

import os
import sys

DIREKTORI_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(DIREKTORI_MODEL, exist_ok=True)

MODEL_REKOMENDASI = {
    "qwen3.5-4b": {
        "nama_berkas": "Qwen3.5-4B-UD-Q4_K_XL.gguf",
        "ukuran": "~2.99 GB",
        "url": "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF",
        "deskripsi": "Model resmi Qwen 3.5 4B Parameter ultra-cerdas, optimal untuk RTX 3050 (35 layer GPU offload via llama.cpp Vulkan)."
    }
}

def periksa_status_model():
    print("=" * 60)
    print(" [SELA AI Desktop] Pemeriksaan Model GGUF Offline")
    print("=" * 60)
    print(f"Direktori Model: {DIREKTORI_MODEL}\n")

    berkas_ditemukan = []
    for berkas in os.listdir(DIREKTORI_MODEL):
        if berkas.endswith(".gguf"):
            jalur = os.path.join(DIREKTORI_MODEL, berkas)
            ukuran_mb = os.path.getsize(jalur) / (1024 * 1024)
            berkas_ditemukan.append((berkas, ukuran_mb))

    if berkas_ditemukan:
        print("Model GGUF yang terdeteksi di sistem:")
        for nama, ukuran in berkas_ditemukan:
            print(f"  [V] {nama} ({ukuran:.1f} MB)")
    else:
        print("Belum ada file .gguf di folder models/.")
        print("\nSistem saat ini otomatis menggunakan Mesin RAG Ekstraksi Fakta Langsung.")
        print("Untuk mengaktifkan model GGUF native, silakan unduh model rekomendasi berikut:")
        for kunci, info in MODEL_REKOMENDASI.items():
            print(f"\n* Pilihan: {info['nama_berkas']} ({info['ukuran']})")
            print(f"  Deskripsi: {info['deskripsi']}")
            print(f"  Tautan: {info['url']}")
            print(f"  Simpan ke: {os.path.join(DIREKTORI_MODEL, info['nama_berkas'])}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    periksa_status_model()
