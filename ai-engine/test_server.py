"""
Skrip pengujian TTS dan ASR endpoint server SELA AI.
Menguji kecepatan respons dan kualitas audio yang dihasilkan.
"""

import requests
import time
import base64
import wave
import struct
import io
import math

# Daftar kalimat yang akan diuji
kalimat_uji_id = [
    "Halo, selamat datang di UCIC!",
    "Baik, ada yang bisa saya bantu?",
    "Informasi ini belum tersedia di sistem kami.",
    "Silakan kunjungi website resmi kampus untuk informasi lebih lanjut.",
]

print("=" * 60)
print("TEST TTS - SELA AI DESKTOP")
print("=" * 60)

# 1. Test TTS per kalimat
for kalimat in kalimat_uji_id:
    t0 = time.time()
    try:
        resp = requests.post(
            "http://127.0.0.1:8008/api/sintesis",
            json={"teks_kalimat": kalimat, "bahasa": "id"},
            timeout=30,
        )
        data = resp.json()
        waktu = time.time() - t0
        engine = data.get("engine", "tidak diketahui")
        ukuran = len(data.get("audio_base64") or "")
        sukses = data.get("sukses", False)
        print(f"[{waktu:.2f}s] [{engine}] [{ukuran} bytes b64] - {kalimat[:45]}...")
    except Exception as e:
        print(f"[ERROR] {e} - {kalimat[:45]}...")

print()
print("=" * 60)
print("TEST ASR - SELA AI DESKTOP")
print("=" * 60)

# 2. Test ASR dengan audio sintetis (440Hz tone, 1 detik)
def buat_audio_tone(frekuensi=440, sr=16000, durasi=1.0):
    """Membuat audio sinyal tone untuk pengujian ASR."""
    sampel = [
        int(32767 * math.sin(2 * math.pi * frekuensi * i / sr))
        for i in range(int(sr * durasi))
    ]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack("<" + "h" * len(sampel), *sampel))
    buf.seek(0)
    return buf.read()

audio_test = buat_audio_tone()
t0 = time.time()
try:
    resp = requests.post(
        "http://127.0.0.1:8008/api/transcribe",
        files={"file": ("test.wav", io.BytesIO(audio_test), "audio/wav")},
        data={"lang": "id"},
        timeout=30,
    )
    data = resp.json()
    waktu = time.time() - t0
    print(f"[{waktu:.2f}s] ASR Tone Test -> teks: '{data.get('teks', '')}' | sukses: {data.get('sukses')}")
except Exception as e:
    print(f"[ERROR] ASR test gagal: {e}")

print()
print("=" * 60)
print("TEST SELESAI")
print("=" * 60)
