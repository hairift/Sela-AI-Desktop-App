"""
SELA AI Desktop - Skrip Persiapan & Pemeriksaan Model GGUF Offline
Memeriksa ketersediaan model Qwen 2.5 GGUF dan menyediakan tautan unduh model resmi HuggingFace.
"""

import os
import sys

DIREKTORI_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(DIREKTORI_MODEL, exist_ok=True)

MODEL_REKOMENDASI = {
    "qwen2.5-7b": {
        "nama_berkas": "qwen2.5-7b-instruct-q4_k_m.gguf",
        "ukuran": "~4.68 GB",
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        "deskripsi": "Model utama akurasi tinggi, pas untuk VRAM 6GB RTX 3050."
    },
    "qwen2.5-3b": {
        "nama_berkas": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "ukuran": "~2.1 GB",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "deskripsi": "Model super cepat, latency rendah (<50ms), hemat VRAM (hanya butuh 2.5GB)."
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
