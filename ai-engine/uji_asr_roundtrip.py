import asyncio
import base64
from sintesis_suara import SintesisSuaraOffline
from pengenal_suara import PengenalSuaraOffline

print("== Init ASR ==", flush=True)
asr = PengenalSuaraOffline(ukuran_model="small", upgrade_background=False)
print("ASR siap:", asr.apakah_siap, "| model:", asr.nama_model_aktif, flush=True)

print("== Sintesis kalimat uji ==", flush=True)
tts = SintesisSuaraOffline()
h = tts.sintesis_teks_ke_audio_base64(
    "Halo, bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?", "id")
wav = base64.b64decode(h["audio_base64"])
print("TTS engine:", h.get("engine"), "| wav bytes:", len(wav), flush=True)

print("== Transkripsi kembali ==", flush=True)
hasil = asr.transkripsikan_audio_bytes(wav, bahasa="id")
print("TEKS:", repr(hasil.get("teks")), flush=True)
print("SUKSES:", hasil.get("sukses"), "| durasi:", hasil.get("durasi"),
      "| energi:", hasil.get("energi"), flush=True)

print("== Uji hening (harus kosong, sukses) ==", flush=True)
import wave as wv
import struct
hening = wv.open("hening_uji.wav", "wb")
hening.setnchannels(1)
hening.setsampwidth(2)
hening.setframerate(16000)
hening.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
hening.close()
with open("hening_uji.wav", "rb") as f:
    rh = asr.transkripsikan_audio_bytes(f.read(), bahasa="id")
print("HENING:", repr(rh.get("teks")), rh.get("pesan"), rh.get("sukses"), flush=True)
import os
os.remove("hening_uji.wav")
print("== SELESAI ==", flush=True)
