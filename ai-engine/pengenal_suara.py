"""
SELA AI Desktop - Pengenal Suara Offline Full-Duplex (Whisper ASR)
==================================================================
Menerima streaming audio dari mikrofon dan mengubahnya menjadi teks
Bahasa Indonesia / Inggris / Jawa secara offline.

Perbaikan stabilitas "kadang bisa kadang tidak":
1. Model default `small` (jauh lebih akurat dari `tiny` untuk Bahasa
   Indonesia) dengan fallback otomatis small -> base -> tiny.
2. Decoding eksplisit via PyAV (`faster_whisper.audio.decode_audio`)
   sehingga WebM/Opus dari browser SELALU bisa dibaca (sebelumnya
   kadang gagal diam-diam dan menghasilkan teks kosong).
3. Gerbang energi (energy gate) + durasi minimum SEBELUM inferensi:
   audio hening/sangat pendek langsung dikembalikan kosong tanpa
   memicu halusinasi Whisper.
4. Parameter anti-halusinasi: beam 5, no_speech 0.6, VAD Silero dengan
   padding, repetition penalty, dan filter kata/suku-kata berulang.
5. Dukungan language: "id" (default), "en", "jv" (Jawa memakai model
   Indonesia karena fonetik serumpun), "auto" (deteksi otomatis).

Mode full-duplex: modul ini stateless per panggilan sehingga aman
dipanggil paralel dari REST maupun WebSocket streaming (/ws/asr-stream
di server.py) sambil TTS sedang berbunyi (barge-in).
"""

import os
import io
import re
from typing import Optional, Dict, Any


# Urutan model dari paling akurat ke paling ringan.
MODEL_PILIHAN = ("small", "base", "tiny")

# Ambang gerbang energi (RMS sinyal 16kHz float32 [-1, 1]).
AMBANG_RMS_HENING = 0.008
DURASI_MIN_DETIK = 0.4


class PengenalSuaraOffline:
    """
    Engine Pengenal Suara (Speech-to-Text / ASR) Berbasis Faster-Whisper.
    Disesuaikan untuk bahasa Indonesia percakapan kampus UCIC.
    """

    def __init__(self, ukuran_model: str = "small", upgrade_background: bool = True):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.join(self.direktori_induk, "models", "whisper")
        os.makedirs(self.direktori_model, exist_ok=True)

        self.ukuran_model = ukuran_model
        self.upgrade_background = upgrade_background
        self.model_whisper = None
        self.perangkat_aktif = ""
        self.nama_model_aktif = ""
        self.apakah_siap = False

        # Kosakata pembantu kampus untuk meningkatkan akurasi transkripsi
        self.prompt_konteks_kampus = (
            "SELA, UCIC, Universitas Catur Insan Cendekia, Cirebon, kampus, mahasiswa, prodi, "
            "fakultas, FTI, FEB, FPS, Teknik Informatika, Sistem Informasi, DKV, Manajemen, "
            "Akuntansi, Bisnis Digital, pendaftaran, PMB, beasiswa, UKT, biaya kuliah, KRS, wisuda."
        )

        self.inisialisasi_whisper()

    # ── Inisialisasi ──────────────────────────────────────────
    def _apakah_model_lengkap(self, nama_model: str) -> bool:
        """Cek snapshot lokal sudah berisi model.bin utuh (hemat startup offline)."""
        akar = os.path.join(self.direktori_model, f"models--Systran--faster-whisper-{nama_model}")
        dir_snapshot = os.path.join(akar, "snapshots")
        if not os.path.isdir(dir_snapshot):
            return False
        try:
            for snap in os.listdir(dir_snapshot):
                bin_model = os.path.join(dir_snapshot, snap, "model.bin")
                if os.path.exists(bin_model) and os.path.getsize(bin_model) > 10 * 1024 * 1024:
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _buat_wav_uji(modus: str = "nada") -> io.BytesIO:
        """
        Bangun WAV uji valid untuk probe CUDA/cuBLAS.
        - "nada": 2 detik sinus 440 Hz + VAD aktif (memaksa komputasi matriks
          penuhmirip ucapan asli sehingga cuBLAS yang hilang langsung ketahuan
          saat load, bukan saat user bicara).
        - "hening": 0.5 detik hening.
        """
        import wave
        import struct
        import math
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            if modus == "nada":
                bingkai = [int(12000 * math.sin(2 * math.pi * 440 * i / 16000))
                           for i in range(32000)]
            else:
                bingkai = [0] * 8000
            wav.writeframes(struct.pack("<" + "h" * len(bingkai), *bingkai))
        buf.seek(0)
        return buf

    def _params_transkripsi(self, kode_bahasa):
        """Parameter identik untuk probe load-time dan transkripsi real (harus sama!)."""
        return dict(
            language=kode_bahasa,
            initial_prompt=self.prompt_konteks_kampus,
            beam_size=5,
            best_of=5,
            patience=1.0,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=400,
                speech_pad_ms=200,
                threshold=0.5,
            ),
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            repetition_penalty=1.2,
        )

    def _muat_model_varian(self, nama_model: str):
        """Coba muat satu varian model (CUDA dulu, lalu CPU). Kembalikan model atau None."""
        import importlib
        modul_fw = importlib.import_module("faster_whisper")
        WhisperModel = getattr(modul_fw, "WhisperModel")
        for perangkat, tipe_komputasi in (("cuda", "float16"), ("cpu", "int8")):
            try:
                model = WhisperModel(
                    nama_model,
                    device=perangkat,
                    compute_type=tipe_komputasi,
                    download_root=self.direktori_model,
                )
                # Probe VAD+beam penuh + ITERASI: cuBLAS rusak langsung ketahuan di sini.
                # Pakai parameter IDENTIK dengan real agar hasil probe valid.
                list(model.transcribe(
                    self._buat_wav_uji("nada"),
                    **self._params_transkripsi("id"),
                )[0])
                print(f"[Pengenal Suara] Model Whisper '{nama_model}' siap pada: {perangkat}!")
                return model, perangkat
            except Exception as galat:
                print(f"[Pengenal Suara] '{nama_model}'/{perangkat} gagal ({galat}).")
        return None, ""

    def _upgrade_model_background(self, nama_model_docel: str):
        """Unduh model docel di background lalu hot-swap bila berhasil."""
        try:
            print(f"[Pengenal Suara] [BG] Mengunduh model '{nama_model_docel}' untuk akurasi lebih baik...")
            model, perangkat = self._muat_model_varian(nama_model_docel)
            if model is not None:
                self.model_whisper = model
                self.perangkat_aktif = perangkat
                self.nama_model_aktif = nama_model_docel
                print(f"[Pengenal Suara] [BG] Upgrade ke '{nama_model_docel}' berhasil!")
        except Exception as galat:
            print(f"[Pengenal Suara] [BG] Upgrade model gagal: {galat}")

    def inisialisasi_whisper(self):
        """Memuat model Whisper: pakai cache lokal dulu (instant), upgrade di background."""
        try:
            import importlib
            importlib.import_module("faster_whisper")
        except Exception:
            self._inisialisasi_whisper_standar()
            return

        # 1. Model yang diminta bila sudah lengkap di disk.
        if self._apakah_model_lengkap(self.ukuran_model):
            model, perangkat = self._muat_model_varian(self.ukuran_model)
            if model is not None:
                self.model_whisper = model
                self.perangkat_aktif = perangkat
                self.nama_model_aktif = self.ukuran_model
                self.apakah_siap = True
                return

        # 2. Fallback instant: cache lokal tercepat dulu (startup tidak boleh lama);
        #    model yang diminta (small) menyusul via upgrade background.
        for cadangan in ("tiny", "base", "medium"):
            if cadangan == self.ukuran_model:
                continue
            if self._apakah_model_lengkap(cadangan):
                model, perangkat = self._muat_model_varian(cadangan)
                if model is not None:
                    self.model_whisper = model
                    self.perangkat_aktif = perangkat
                    self.nama_model_aktif = cadangan
                    self.apakah_siap = True
                    break

        # 3. Upgrade ke model yang diminta di background (tidak blokir startup).
        if self.upgrade_background and (
            (not self.apakah_siap) or (self.nama_model_aktif != self.ukuran_model)
        ):
            import threading
            threading.Thread(target=self._upgrade_model_background,
                             args=(self.ukuran_model,), daemon=True).start()

        if not self.apakah_siap:
            print("[Pengenal Suara] Semua varian cache gagal, coba unduh langsung...")
            model, perangkat = self._muat_model_varian(self.ukuran_model)
            if model is not None:
                self.model_whisper = model
                self.perangkat_aktif = perangkat
                self.nama_model_aktif = self.ukuran_model
                self.apakah_siap = True
                return
            self._inisialisasi_whisper_standar()

    def _turunkan_ke_cpu(self) -> bool:
        """Muat ulang model aktif di CPU bila CUDA ternyata rusak (cublas hilang)."""
        if self.perangkat_aktif != "cuda" or not self.nama_model_aktif:
            return False
        try:
            print("[Pengenal Suara] CUDA rusak saat inferensi, turun ke CPU...")
            model, _ = self._muat_model_varian_cpu_saja(self.nama_model_aktif)
            if model is None:
                return False
            self.model_whisper = model
            self.perangkat_aktif = "cpu"
            print(f"[Pengenal Suara] Model '{self.nama_model_aktif}' kini berjalan di CPU.")
            return True
        except Exception as galat:
            print(f"[Pengenal Suara] Gagal turun ke CPU: {galat}")
            return False

    def _muat_model_varian_cpu_saja(self, nama_model: str):
        import importlib
        modul_fw = importlib.import_module("faster_whisper")
        WhisperModel = getattr(modul_fw, "WhisperModel")
        try:
            model = WhisperModel(nama_model, device="cpu", compute_type="int8",
                                 download_root=self.direktori_model)
            list(model.transcribe(self._buat_wav_uji("nada"), language="id",
                                  beam_size=5, vad_filter=True)[0])
            return model, "cpu"
        except Exception as galat:
            print(f"[Pengenal Suara] Muat CPU '{nama_model}' gagal: {galat}")
            return None, ""

    def _inisialisasi_whisper_standar(self):
        try:
            import importlib
            modul_w = importlib.import_module("whisper")
            print(f"[Pengenal Suara] Menggunakan pustaka Whisper standar ({self.ukuran_model})...")
            self.model_whisper = modul_w.load_model(self.ukuran_model, download_root=self.direktori_model)
            self.nama_model_aktif = self.ukuran_model + "-standar"
            self.apakah_siap = True
        except Exception:
            print("[Pengenal Suara] Pustaka Whisper belum terinstal.")
            print("[Pengenal Suara] Pasang dengan: pip install faster-whisper")
            self.apakah_siap = False

    # ── Decoding + gerbang energi ─────────────────────────────
    def _decode_ke_pcm16k(self, data_audio_bytes: bytes):
        """
        Decode WebM/WAV/MP3/PCM apa pun menjadi float32 mono 16kHz.
        Mengembalikan None bila berkas rusak/tak dikenali.
        """
        try:
            from faster_whisper.audio import decode_audio
            pcm = decode_audio(io.BytesIO(data_audio_bytes), sampling_rate=16000)
            if pcm is None or len(pcm) == 0:
                return None
            return pcm
        except Exception as galat:
            print(f"[Pengenal Suara] Decode audio gagal: {galat}")
            return None

    @staticmethod
    def _rms(pcm) -> float:
        try:
            import numpy as np
            return float(np.sqrt(np.mean(np.asarray(pcm, dtype=np.float64) ** 2)))
        except Exception:
            return 0.0

    def _normalisasi_bahasa(self, bahasa: Optional[str]) -> Optional[str]:
        """'id-ID'->'id', 'EN'->'en', 'jawa'/'jv'->'id', 'auto'->None (deteksi)."""
        kode = (bahasa or "id").strip().lower().replace("_", "-").split("-")[0]
        if kode == "auto":
            return None
        if kode in ("jv", "jw", "jawa"):
            return "id"
        if kode.startswith("en"):
            return "en"
        return "id"

    # ── Transkripsi utama ─────────────────────────────────────
    @staticmethod
    def _apakah_galat_cuda(galat: Exception) -> bool:
        pesan = str(galat).lower()
        return ("cublas" in pesan or "cuda" in pesan or "cudnn" in pesan
                or "nvrtc" in pesan or "cudart" in pesan)

    def _jalankan_transkripsi_penuh(self, pcm, kode_bahasa):
        """
        Satu putaran transkripsi penuh (termasuk iterasi generator lazy
        faster-whisper). Mengembalikan (teks_gabungan, bahasa_terdeteksi).
        """
        segmen_hasil, info = self.model_whisper.transcribe(
            pcm, **self._params_transkripsi(kode_bahasa)
        )
        daftar_teks = []
        for seg in segmen_hasil:  # di sinilah komputasi CUDA berat terjadi
            if getattr(seg, "no_speech_prob", 0) > 0.6:
                continue
            teks_seg = seg.text.strip()
            if not teks_seg:
                continue
            # Tangkal halusinasi: kata berulang ("halo halo halo halo")
            if re.search(r"(\b\w+\b)(?:\s*[,.]?\s*\1){2,}", teks_seg, re.IGNORECASE):
                print(f"[Pengenal Suara] Abaikan halusinasi (kata berulang): {teks_seg}")
                continue
            # Tangkal halusinasi: suku kata berulang ("kakakakak...")
            if re.search(r"(\w{2,3})\1{3,}", teks_seg, re.IGNORECASE):
                print(f"[Pengenal Suara] Abaikan halusinasi (suku berulang): {teks_seg}")
                continue
            daftar_teks.append(teks_seg)
        return " ".join(daftar_teks).strip(), getattr(info, "language", kode_bahasa or "id")

    def _transkripsi_dengan_fallback_cpu(self, pcm, kode_bahasa):
        """Transkripsi penuh; bila CUDA rusak (cublas hilang) turun ke CPU lalu ulangi."""
        try:
            return self._jalankan_transkripsi_penuh(pcm, kode_bahasa)
        except Exception as galat:
            if self._apakah_galat_cuda(galat) and self._turunkan_ke_cpu():
                return self._jalankan_transkripsi_penuh(pcm, kode_bahasa)
            raise

    def transkripsikan_audio_bytes(
        self, data_audio_bytes: bytes, bahasa: str = "id"
    ) -> Dict[str, Any]:
        """
        Mengonversi data biner audio (WebM/WAV/MP3/PCM) menjadi teks.
        Dilengkapi gerbang energi, VAD Silero, dan pencegah halusinasi.
        Selalu mengembalikan dict {teks, sukses, ...} — tidak pernah raise.
        """
        if not data_audio_bytes or len(data_audio_bytes) < 1000:
            return {"teks": "", "pesan": "Audio terlalu pendek", "sukses": True}

        if not (self.apakah_siap and self.model_whisper is not None):
            return {
                "teks": "",
                "pesan": "Model Whisper sedang diinisialisasi",
                "sukses": False,
            }

        pcm = self._decode_ke_pcm16k(data_audio_bytes)
        if pcm is None:
            return {"teks": "", "pesan": "Format audio tidak dikenali", "sukses": True}

        durasi = len(pcm) / 16000.0
        energi = self._rms(pcm)
        if durasi < DURASI_MIN_DETIK:
            return {"teks": "", "pesan": "Audio terlalu pendek", "sukses": True}
        if energi < AMBANG_RMS_HENING:
            return {"teks": "", "pesan": "Hening (tidak ada suara)", "sukses": True,
                    "durasi": round(durasi, 2), "energi": round(energi, 4)}

        kode_bahasa = self._normalisasi_bahasa(bahasa)

        # Model whisper standar (openai-whisper) punya API berbeda.
        if self.nama_model_aktif.endswith("-standar"):
            return self._transkripsi_whisper_standar(pcm, kode_bahasa, durasi, energi)

        try:
            teks_gabungan, bahasa_terdeteksi = self._transkripsi_dengan_fallback_cpu(
                pcm, kode_bahasa
            )
            return {"teks": teks_gabungan, "sukses": True,
                    "bahasa": bahasa_terdeteksi,
                    "durasi": round(durasi, 2), "energi": round(energi, 4)}
        except Exception as galat:
            print(f"[Pengenal Suara] Galat transkripsi: {galat}")
            return {"teks": "", "pesan": f"Galat transkripsi: {galat}", "sukses": False}

    def _transkripsi_whisper_standar(self, pcm, kode_bahasa, durasi, energi) -> Dict[str, Any]:
        try:
            import numpy as np
            opsi = dict(language=kode_bahasa or "id", fp16=False,
                        initial_prompt=self.prompt_konteks_kampus,
                        condition_on_previous_text=False, no_speech_threshold=0.6)
            hasil = self.model_whisper.transcribe(np.asarray(pcm, dtype=np.float32), **opsi)
            teks = (hasil.get("text") or "").strip()
            return {"teks": teks, "sukses": True, "bahasa": kode_bahasa or "id",
                    "durasi": round(durasi, 2), "energi": round(energi, 4)}
        except Exception as galat:
            print(f"[Pengenal Suara] Galat whisper standar: {galat}")
            return {"teks": "", "pesan": str(galat), "sukses": False}


if __name__ == "__main__":
    pengenal = PengenalSuaraOffline()
    print(f"Status Pengenal Suara Whisper: {'Siap' if pengenal.apakah_siap else 'Menunggu instalasi package'}")
    print(f"Model aktif: {pengenal.nama_model_aktif or '-'}")
