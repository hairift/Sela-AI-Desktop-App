print("start", flush=True)
from pengenal_suara import PengenalSuaraOffline
print("import ok", flush=True)
asr = PengenalSuaraOffline(ukuran_model="tiny")
print("ASR siap:", asr.apakah_siap, "| model:", asr.nama_model_aktif, flush=True)
