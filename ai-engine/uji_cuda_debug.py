import io
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
from pengenal_suara import PengenalSuaraOffline

m = WhisperModel("tiny", device="cuda", compute_type="float16",
                 download_root="models/whisper")
print("model loaded cuda", flush=True)

# 1. probe-file 2s nada
try:
    segs, _ = m.transcribe(PengenalSuaraOffline._buat_wav_uji("nada"),
                           language="id", beam_size=5, vad_filter=True)
    print("probe file ok:", [s.text for s in segs], flush=True)
except Exception as e:
    print("probe file GAGAL:", e, flush=True)

# 2. wav piper real sebagai file
import base64
from sintesis_suara import SintesisSuaraOffline
tts = SintesisSuaraOffline()
h = tts.sintesis_teks_ke_audio_base64(
    "Halo, bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?", "id")
wav = base64.b64decode(h["audio_base64"])
open("_uji_real.wav", "wb").write(wav)
try:
    segs, _ = m.transcribe(io.BytesIO(wav), language="id", beam_size=5,
                           vad_filter=True)
    print("real file ok:", [s.text for s in segs], flush=True)
except Exception as e:
    print("real file GAGAL:", e, flush=True)

# 3. wav real sebagai numpy pcm
try:
    pcm = decode_audio(io.BytesIO(wav), sampling_rate=16000)
    print("pcm len:", len(pcm), flush=True)
    segs, _ = m.transcribe(pcm, language="id", beam_size=5, vad_filter=True)
    print("real numpy ok:", [s.text for s in segs], flush=True)
except Exception as e:
    print("real numpy GAGAL:", e, flush=True)
