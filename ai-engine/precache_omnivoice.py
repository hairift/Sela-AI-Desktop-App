"""
Pre-caching audio OmniVoice Voice Design untuk SELA AI Desktop
Menghasilkan berkas audio WAV untuk kalimat-kalimat populer kampus UCIC
sehingga saat user membuka aplikasi atau bertanya, respon suara instan 0ms!
"""

import os
import sys
import asyncio
import time

# Tambahkan direktori ai-engine ke path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from sintesis_suara import SintesisSuaraOffline, _bersihkan_teks_untuk_tts, _normalisasi_kode_bahasa

KALIMAT_POPULER = [
    # Sapaan awal & pergantian bahasa
    ("Halo! Selamat datang di Universitas Catur Insan Cendekia Cirebon. Ada yang bisa Sela bantu?", "id"),
    ("Halo! Selamat datang di UCIC. Saya SELA.", "id"),
    ("Mau bicara dalam Bahasa Indonesia atau Bahasa Inggris?", "id"),
    ("Hello! Welcome to UCIC. I'm SELA.", "en"),
    ("Would you like to speak in Indonesian or English?", "en"),
    ("Hello! Welcome to Catur Insan Cendekia University. How can Sela assist you today?", "en"),
    ("Sama-sama! Senang bisa membantu. Selamat datang kembali kapan saja ya!", "id"),
    ("You're welcome! Happy to help. Feel free to come back anytime!", "en"),

    # Ringkasan jawaban kampus yang paling sering terdengar.
    ("Pendaftaran mahasiswa baru di UCIC bisa dilakukan secara online melalui website resmi PMB.", "id"),
    ("Biaya kuliah di UCIC tersedia dengan pilihan cicilan dan beasiswa.", "id"),
    ("UCIC memiliki tiga fakultas dan beragam program studi.", "id"),
    ("Kampus utama UCIC beralamat di Jalan Kesambi Nomor 202, Cirebon.", "id"),

    # Pertanyaan Kampus Populer Lainnya
    ("Rektor Universitas Catur Insan Cendekia saat ini adalah Dr. Chandra Lukita, M.M.", "id"),
    ("UCIC menyediakan pilihan beasiswa seperti KIP Kuliah dan beasiswa yayasan.", "id"),
    ("Fasilitas kampus UCIC mencakup laboratorium komputer, perpustakaan digital, dan sarana olahraga.", "id"),
    ("Syarat pendaftaran mahasiswa baru meliputi ijazah atau SKL, KTP, dan pas foto.", "id"),
]

def jalankan_precache():
    print("[Pre-Cache OmniVoice] Menyiapkan mesin TTS...")
    tts = SintesisSuaraOffline()
    
    # Tunggu inisialisasi model
    for _ in range(30):
        if tts._omnivoice_siap or tts._omnivoice_gagal:
            break
        time.sleep(0.5)

    if not tts._omnivoice_siap:
        print("[Pre-Cache OmniVoice] Gagal: OmniVoice tidak siap.")
        return

    print(f"[Pre-Cache OmniVoice] Memulai pre-rendering untuk {len(KALIMAT_POPULER)} kalimat populer...")

    for idx, (kalimat, bahasa) in enumerate(KALIMAT_POPULER, 1):
        kode = _normalisasi_kode_bahasa(bahasa)
        teks_bersih = _bersihkan_teks_untuk_tts(kalimat)
        kunci = tts._kunci_cache(teks_bersih, kode, "omnivoice-vd")
        
        # Cek apakah sudah ada di disk
        jalur_wav = os.path.join(tts.direktori_cache_omnivoice, f"{kunci}.wav")
        if os.path.exists(jalur_wav) and os.path.getsize(jalur_wav) > 1000:
            print(f"[{idx}/{len(KALIMAT_POPULER)}] SUDAH ADA (Cache): {kalimat[:45]}...")
            continue

        print(f"[{idx}/{len(KALIMAT_POPULER)}] Mengenerate Voice Design: {kalimat[:45]}...")
        t0 = time.time()
        wav_bytes = tts.sintesis_dengan_omnivoice(teks_bersih, kode)
        dt = time.time() - t0
        if wav_bytes:
            with open(jalur_wav, "wb") as f:
                f.write(wav_bytes)
            print(f"    -> SUKSES disintesis dalam {dt:.2f}s ({len(wav_bytes)} bytes)")
        else:
            print("    -> GAGAL!")

    print("[Pre-Cache OmniVoice] Selesai!")

if __name__ == "__main__":
    jalankan_precache()
