"""
SELA AI Desktop - Mesin STT Tunggal berbasis faster-whisper
============================================================
Mengubah audio (WebM/Opus/WAV/MP3/PCM dari mikrofon) menjadi teks, 100%
di memori. TIDAK ADA berkas sementara: audio di-decode langsung dari
io.BytesIO memakai PyAV bawaan faster-whisper, dengan fallback soundfile.

Lapisan anti-halusinasi Whisper:
1. Gerbang energi (RMS) + durasi minimum sebelum inferensi.
2. VAD Silero bawaan faster-whisper dengan padding.
3. beam size 5, no_speech_threshold, repetition_penalty, compression ratio.
4. Filter kata/suku-kata berulang.
5. Koreksi ASR ringan (koreksi_asr) untuk istilah kampus UCIC.

Pemakaian:
    from core import dapatkan_stt
    stt = dapatkan_stt()
    hasil = stt.transkripsikan_bytes(byte_audio, bahasa="id")
"""

from __future__ import annotations

import io
import os
import re
import threading
from typing import Any, Dict, Optional

# Urutan model dari paling akurat ke paling ringan (semua di models/whisper).
MODEL_PILIHAN = ("small", "medium", "base", "tiny")
AMBANG_RMS_HENING = 0.0015
DURASI_MIN_DETIK = 0.2


class SttEngine:
    """Pembungkus tunggal faster-whisper untuk transkripsi ucapan SELA."""

    _instance: Optional["SttEngine"] = None
    _kunci_singleton = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "SttEngine":
        if cls._instance is None:
            with cls._kunci_singleton:
                if cls._instance is None:
                    instansi = super().__new__(cls)
                    instansi._sudah_disiapkan = False
                    cls._instance = instansi
        return cls._instance

    def __init__(self, ukuran_model: str = "small") -> None:
        if getattr(self, "_sudah_disiapkan", False):
            return
        self._sudah_disiapkan = True

        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.abspath(
            os.path.join(self.direktori_induk, "..", "models", "whisper")
        )
        os.makedirs(self.direktori_model, exist_ok=True)

        self.ukuran_model = ukuran_model
        self.model = None
        self.apakah_siap = False
        self.nama_model_aktif = ""
        self.perangkat_aktif = ""

        # Kosakata pembantu kampus untuk menaikkan akurasi transkripsi.
        self.prompt_konteks = (
            "SELA, UCIC, Universitas Catur Insan Cendekia, Cirebon, kampus, mahasiswa, prodi, "
            "fakultas, FTI, FEB, FPS, Teknik Informatika, Sistem Informasi, DKV, Manajemen, "
            "Akuntansi, Bisnis Digital, pendaftaran, PMB, beasiswa, UKT, biaya kuliah, KRS, wisuda."
        )

        try:
            from koreksi_asr import KoreksiAsr  # modul lama tetap dipakai

            self.koreksi = KoreksiAsr()
        except Exception:
            self.koreksi = None

        self._muat_model()

    # ── Pemuatan model ────────────────────────────────────────────────────────
    def _apakah_lengkap(self, nama: str) -> bool:
        akar = os.path.join(self.direktori_model, f"models--Systran--faster-whisper-{nama}")
        snap = os.path.join(akar, "snapshots")
        if not os.path.isdir(snap):
            return False
        try:
            for folder in os.listdir(snap):
                berkas = os.path.join(snap, folder, "model.bin")
                if os.path.exists(berkas) and os.path.getsize(berkas) > 10 * 1024 * 1024:
                    return True
        except Exception:
            pass
        return False

    def _coba_muat(self, nama: str):
        from faster_whisper import WhisperModel

        kandidat = []
        try:
            import torch

            if torch.cuda.is_available():
                kandidat.append(("cuda", "float16"))
        except Exception:
            pass
        kandidat.append(("cpu", "int8"))

        for perangkat, tipe in kandidat:
            try:
                model = WhisperModel(
                    nama, device=perangkat, compute_type=tipe, download_root=self.direktori_model
                )
                # Probe ringan untuk memastikan backend benar-benar berfungsi.
                list(model.transcribe(io.BytesIO(self._wav_uji()), language="id", beam_size=5)[0])
                return model, perangkat
            except Exception as galat:
                print(f"[STT] '{nama}' pada {perangkat} gagal: {galat}")
        return None, ""

    @staticmethod
    def _wav_uji() -> bytes:
        """WAV hening 0,5 detik untuk probe backend (di memori)."""
        import math
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            bingkai = [int(9000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(8000)]
            wav.writeframes(struct.pack("<" + "h" * len(bingkai), *bingkai))
        return buf.getvalue()

    def _muat_model(self) -> None:
        try:
            import faster_whisper  # noqa: F401
        except Exception:
            self.apakah_siap = False
            print("[STT] faster-whisper belum terpasang. Jalankan: pip install faster-whisper")
            return

        urutan = [self.ukuran_model] + [m for m in MODEL_PILIHAN if m != self.ukuran_model]
        for nama in urutan:
            if not self._apakah_lengkap(nama) and nama != self.ukuran_model:
                continue
            model, perangkat = self._coba_muat(nama)
            if model is not None:
                self.model = model
                self.nama_model_aktif = nama
                self.perangkat_aktif = perangkat
                self.apakah_siap = True
                print(f"[STT] Whisper '{nama}' siap pada {perangkat}.")
                return
        self.apakah_siap = False
        print("[STT] Tidak ada model Whisper yang bisa dimuat.")

    # ── Decoding (100% memori) ────────────────────────────────────────────────
    def _decode_pcm16k(self, data_audio: bytes):
        """Decode audio apa pun menjadi float32 mono 16 kHz tanpa menyentuh disk."""
        try:
            from faster_whisper.audio import decode_audio

            pcm = decode_audio(io.BytesIO(data_audio), sampling_rate=16000)
            if pcm is not None and len(pcm) > 0:
                return pcm
        except Exception as galat:
            print(f"[STT] Decode PyAV/BytesIO gagal ({galat}); coba soundfile.")

        try:
            import numpy as np
            import soundfile as sf

            with sf.SoundFile(io.BytesIO(data_audio)) as berkas:
                data = berkas.read(dtype="float32", always_2d=False)
                sr = berkas.samplerate
            if data is None or len(data) == 0:
                return None
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != 16000:
                # Resampling linier sederhana (cukup untuk gate energi + ASR).
                import math

                n_target = int(len(data) * 16000 / sr)
                idx = np.linspace(0, len(data) - 1, n_target)
                data = np.interp(idx, np.arange(len(data)), data).astype(np.float32)
            return data
        except Exception as galat2:
            print(f"[STT] Fallback soundfile gagal: {galat2}")
        return None

    @staticmethod
    def _rms(pcm) -> float:
        try:
            import numpy as np

            return float(np.sqrt(np.mean(np.asarray(pcm, dtype=np.float64) ** 2)))
        except Exception:
            return 0.0

    @staticmethod
    def _normalisasi_bahasa(bahasa: Optional[str]) -> Optional[str]:
        kode = (bahasa or "id").strip().lower().replace("_", "-").split("-")[0]
        if kode == "auto":
            return None
        if kode in ("jv", "jw", "jawa"):
            return "id"
        if kode.startswith("en"):
            return "en"
        return "id"

    def _params(self, kode_bahasa) -> Dict[str, Any]:
        return dict(
            language=kode_bahasa,
            initial_prompt=self.prompt_konteks,
            beam_size=5,
            best_of=5,
            patience=1.0,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=300, threshold=0.35),
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            repetition_penalty=1.2,
        )

    # ── Transkripsi utama ─────────────────────────────────────────────────────
    def transkripsikan_bytes(self, data_audio: bytes, bahasa: str = "id") -> Dict[str, Any]:
        """Ubah byte audio menjadi teks. Selalu mengembalikan dict, tidak pernah raise."""
        if not data_audio or len(data_audio) < 1000:
            return {"teks": "", "pesan": "Audio terlalu pendek", "sukses": True}
        if not (self.apakah_siap and self.model is not None):
            return {"teks": "", "pesan": "Model Whisper belum siap", "sukses": False}

        pcm = self._decode_pcm16k(data_audio)
        if pcm is None:
            return {"teks": "", "pesan": "Format audio tidak dikenali", "sukses": True}

        durasi = len(pcm) / 16000.0
        energi = self._rms(pcm)
        if durasi < DURASI_MIN_DETIK:
            return {"teks": "", "pesan": "Audio terlalu pendek", "sukses": True}
        if energi < AMBANG_RMS_HENING:
            return {
                "teks": "",
                "pesan": "Hening (tidak ada suara)",
                "sukses": True,
                "durasi": round(durasi, 2),
                "energi": round(energi, 4),
            }

        kode = self._normalisasi_bahasa(bahasa)
        try:
            segmen, info = self.model.transcribe(pcm, **self._params(kode))
            potongan = []
            for seg in segmen:
                if getattr(seg, "no_speech_prob", 0) > 0.6:
                    continue
                teks_seg = seg.text.strip()
                if not teks_seg:
                    continue
                if re.search(r"(\b\w+\b)(?:\s*[,.]?\s*\1){2,}", teks_seg, re.IGNORECASE):
                    print(f"[STT] Abaikan halusinasi (kata berulang): {teks_seg}")
                    continue
                if re.search(r"(\w{2,3})\1{3,}", teks_seg, re.IGNORECASE):
                    print(f"[STT] Abaikan halusinasi (suku berulang): {teks_seg}")
                    continue
                potongan.append(teks_seg)

            teks = " ".join(potongan).strip()
            if teks and self.koreksi is not None:
                teks_terkoreksi = self.koreksi.koreksi_teks(teks)
                if teks_terkoreksi != teks:
                    print(f"[STT] Auto-correct: '{teks}' -> '{teks_terkoreksi}'")
                    teks = teks_terkoreksi

            return {
                "teks": teks,
                "sukses": True,
                "bahasa": getattr(info, "language", kode or "id"),
                "durasi": round(durasi, 2),
                "energi": round(energi, 4),
            }
        except Exception as galat:
            print(f"[STT] Galat transkripsi: {galat}")
            return {"teks": "", "pesan": f"Galat transkripsi: {galat}", "sukses": False}

    def info(self) -> Dict[str, Any]:
        return {
            "apakah_siap": self.apakah_siap,
            "model": self.nama_model_aktif,
            "perangkat": self.perangkat_aktif,
        }


def dapatkan_stt() -> SttEngine:
    """Ambil instansi tunggal SttEngine."""
    return SttEngine()


if __name__ == "__main__":
    mesin = dapatkan_stt()
    print("Status STT:", mesin.info())
