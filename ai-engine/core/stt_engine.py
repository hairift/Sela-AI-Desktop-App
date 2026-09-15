"""
SELA AI Desktop - Mesin STT Tunggal berbasis sherpa-onnx (STREAMING)
=====================================================================
Mengubah audio menjadi teks secara REAL-TIME: kata muncul saat pengguna masih
berbicara, bukan menunggu rekaman selesai. Ini yang membuat SELA terasa seperti
bercakap dengan manusia.

Model: `sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10`
(zipformer transducer streaming, 8 bahasa termasuk Indonesia). Empat berkas
model disimpan di `ai-engine/models/sherpa-streaming-zipformer/`.

Menggantikan faster-whisper sepenuhnya. Whisper bersifat "batch" (harus menunggu
seluruh rekaman) sehingga tidak bisa memenuhi kebutuhan real-time.

Dua jalur pemakaian:
1. STREAMING (utama, real-time) — dipakai `/ws/asr-stream`:
       sesi = stt.buat_sesi()
       stt.terima_pcm(sesi, pcm_int16_bytes)      # dipanggil terus-menerus
       stt.hasil_terkini(sesi)                    # teks sementara (kata per kata)
       stt.apakah_akhir_ucapan(sesi)              # deteksi pengguna berhenti
       stt.akhirkan(sesi)                         # teks final
2. BATCH (cadangan, kompatibel) — dipakai `/api/transcribe`:
       stt.transkripsikan_bytes(byte_audio, bahasa="id")

Seluruh audio diproses di memori. TIDAK ADA berkas sementara di disk.

Pemakaian:
    from core import dapatkan_stt
    stt = dapatkan_stt()
    print(stt.transkripsikan_bytes(wav_bytes, "id"))
"""

from __future__ import annotations

import io
import os
import re
import threading
from typing import Any, Dict, List, Optional

# Nama berkas model di ai-engine/models/sherpa-streaming-zipformer/.
BERKAS_ENCODER = "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx"
BERKAS_DECODER = "decoder-epoch-75-avg-11-chunk-16-left-128.onnx"
BERKAS_JOINER = "joiner-epoch-75-avg-11-chunk-16-left-128.int8.onnx"
BERKAS_TOKENS = "tokens.txt"

SAMPLE_RATE = 16000
AMBANG_RMS_HENING = 0.0015
DURASI_MIN_DETIK = 0.2

# Deteksi akhir ucapan (endpoint) agar SELA bisa langsung menjawab begitu
# pengguna berhenti bicara. Nilai kecil = respons lebih cepat, tetapi berisiko
# memotong jeda berpikir yang wajar. 1,2 detik hening setelah ada kata adalah
# keseimbangan yang dipakai asisten suara umum; sebelum ada kata sama sekali
# dipakai 2 detik supaya pengguna sempat mulai.
HENING_AKHIR_TANPA_TEKS = float(os.environ.get("SELA_ASR_HENING1", "2.0"))
HENING_AKHIR_SETELAH_TEKS = float(os.environ.get("SELA_ASR_HENING2", "1.2"))
MAKS_PANJANG_UCAPAN = float(os.environ.get("SELA_ASR_MAKS_UCAPAN", "20"))


class SesiAsr:
    """Satu sesi streaming: menyimpan stream sherpa + teks yang sudah terkumpul."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.teks_final: List[str] = []
        self.teks_terakhir = ""
        self.jumlah_bingkai = 0


class SttEngine:
    """Pembungkus tunggal OnlineRecognizer sherpa-onnx untuk ucapan SELA."""

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

    def __init__(self) -> None:
        if getattr(self, "_sudah_disiapkan", False):
            return
        self._sudah_disiapkan = True

        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.abspath(
            os.path.join(self.direktori_induk, "..", "models", "sherpa-streaming-zipformer")
        )

        self.recognizer: Any = None
        self.apakah_siap = False
        self.nama_model_aktif = ""
        self.perangkat_aktif = ""
        self.pesan_status = "belum dimuat"
        self._kunci = threading.Lock()

        try:
            from koreksi_asr import KoreksiAsr  # modul lama tetap dipakai

            self.koreksi = KoreksiAsr()
        except Exception:
            self.koreksi = None

        self._muat_model()

    # ── Pemuatan model ────────────────────────────────────────────────────────
    def _jalur(self, nama: str) -> str:
        return os.path.join(self.direktori_model, nama)

    def _semua_berkas_ada(self) -> bool:
        return all(
            os.path.exists(self._jalur(n))
            for n in (BERKAS_ENCODER, BERKAS_DECODER, BERKAS_JOINER, BERKAS_TOKENS)
        )

    def _muat_model(self) -> None:
        try:
            import sherpa_onnx
        except Exception:
            self.apakah_siap = False
            self.pesan_status = "paket sherpa-onnx belum terpasang"
            print("[STT] sherpa-onnx belum terpasang. Jalankan: pip install sherpa-onnx")
            return

        if not self._semua_berkas_ada():
            self.apakah_siap = False
            self.pesan_status = "berkas model zipformer belum lengkap"
            print(
                f"[STT] Model streaming belum lengkap di {self.direktori_model}. "
                "Jalankan: python ai-engine/persiapan_model.py --unduh-asr"
            )
            return

        try:
            self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=self._jalur(BERKAS_TOKENS),
                encoder=self._jalur(BERKAS_ENCODER),
                decoder=self._jalur(BERKAS_DECODER),
                joiner=self._jalur(BERKAS_JOINER),
                num_threads=int(os.environ.get("SELA_ASR_THREAD", "2")),
                sample_rate=SAMPLE_RATE,
                feature_dim=80,
                # greedy_search sudah cukup akurat untuk model kecil ini dan
                # paling cepat — penting untuk latensi real-time.
                decoding_method="greedy_search",
                # Deteksi akhir ucapan: pengguna berhenti -> SELA langsung menjawab.
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=HENING_AKHIR_TANPA_TEKS,
                rule2_min_trailing_silence=HENING_AKHIR_SETELAH_TEKS,
                rule3_min_utterance_length=MAKS_PANJANG_UCAPAN,
                provider="cpu",
            )
        except Exception as galat:
            self.apakah_siap = False
            self.pesan_status = f"gagal memuat model: {galat}"
            print(f"[STT] Gagal memuat model sherpa-onnx: {galat}")
            return

        self.apakah_siap = True
        self.nama_model_aktif = "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh"
        self.perangkat_aktif = "cpu"
        self.pesan_status = "sherpa-onnx streaming zipformer siap (realtime, kata per kata)"
        print(f"[STT] {self.nama_model_aktif} siap (streaming, cpu).")

    # ── Decoding audio ke PCM 16 kHz mono (100% memori) ───────────────────────
    @staticmethod
    def _ke_mono_16k(data_audio: bytes):
        """
        Decode audio apa pun (WebM/Opus/WAV/MP3/OGG) menjadi float32 mono 16 kHz.

        PyAV dipakai lebih dulu karena browser mengirim `audio/webm` (Opus) yang
        tidak bisa dibaca soundfile. soundfile tetap menjadi cadangan untuk
        WAV/FLAC/OGG.
        """
        try:
            import av  # PyAV
            import numpy as np

            with av.open(io.BytesIO(data_audio)) as wadah:
                aliran = wadah.streams.audio[0]
                potongan = []
                resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
                for bingkai in wadah.decode(aliran):
                    for hasil in resampler.resample(bingkai):
                        arr = hasil.to_ndarray()
                        potongan.append(np.asarray(arr, dtype="float32").reshape(-1))
                if potongan:
                    return np.concatenate(potongan).astype("float32") / 32768.0
        except Exception as galat:
            print(f"[STT] Decode PyAV gagal ({galat}); coba soundfile.")

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
            if sr != SAMPLE_RATE:
                # Resampling linier sederhana — cukup untuk ASR.
                n_target = int(len(data) * SAMPLE_RATE / sr)
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
    def _normalisasi_bahasa(bahasa: Optional[str]) -> str:
        kode = (bahasa or "id").strip().lower().replace("_", "-").split("-")[0]
        if kode in ("jv", "jw", "jawa", "su", "sunda"):
            return "id"
        return kode or "id"

    def _koreksi(self, teks: str) -> str:
        """Perbaiki istilah kampus UCIC yang sering salah dengar."""
        if teks and self.koreksi is not None:
            try:
                teks_terkoreksi = self.koreksi.koreksi_teks(teks)
                if teks_terkoreksi != teks:
                    print(f"[STT] Auto-correct: '{teks}' -> '{teks_terkoreksi}'")
                    return teks_terkoreksi
            except Exception:
                pass
        return teks

    @staticmethod
    def _buang_halusinasi(teks: str) -> bool:
        """True bila teks tampak seperti pengulangan halusinatif."""
        if re.search(r"(\b\w+\b)(?:\s*[,.]?\s*\1){2,}", teks, re.IGNORECASE):
            return True
        if re.search(r"(\w{2,3})\1{3,}", teks, re.IGNORECASE):
            return True
        return False

    # ── Jalur STREAMING (utama) ───────────────────────────────────────────────
    def buat_sesi(self) -> Optional[SesiAsr]:
        """Buat sesi streaming baru. None bila model belum siap."""
        if not (self.apakah_siap and self.recognizer is not None):
            return None
        try:
            return SesiAsr(self.recognizer.create_stream())
        except Exception as galat:
            print(f"[STT] Gagal membuat sesi streaming: {galat}")
            return None

    def terima_pcm(self, sesi: Optional[SesiAsr], data_pcm) -> Optional[str]:
        """
        Suapkan potongan audio ke sesi dan kembalikan teks terkini.

        `data_pcm` boleh berupa byte PCM 16-bit mono 16 kHz (dari browser) atau
        array float32. Setiap panggilan men-decode potongan yang sudah siap dan
        mengembalikan teks sementara (bisa bertambah kata demi kata).
        """
        if sesi is None or not self.recognizer:
            return None
        try:
            import numpy as np

            if isinstance(data_pcm, (bytes, bytearray)):
                if not data_pcm:
                    return sesi.teks_terakhir
                sampel = np.frombuffer(bytes(data_pcm), dtype=np.int16).astype("float32") / 32768.0
            else:
                sampel = np.asarray(data_pcm, dtype="float32").reshape(-1)
            if sampel.size == 0:
                return sesi.teks_terakhir

            with self._kunci:
                sesi.stream.accept_waveform(SAMPLE_RATE, sampel)
                sesi.jumlah_bingkai += 1
                while self.recognizer.is_ready(sesi.stream):
                    self.recognizer.decode_stream(sesi.stream)
                teks = self.recognizer.get_result(sesi.stream) or ""
            sesi.teks_terakhir = teks.strip()
            return sesi.teks_terakhir
        except Exception as galat:
            print(f"[STT] Kendala saat menerima audio: {galat}")
            return sesi.teks_terakhir

    def apakah_akhir_ucapan(self, sesi: Optional[SesiAsr]) -> bool:
        """True bila model mendeteksi pengguna sudah berhenti bicara."""
        if sesi is None or not self.recognizer:
            return False
        try:
            with self._kunci:
                return bool(self.recognizer.is_endpoint(sesi.stream))
        except Exception:
            return False

    def akhirkan(self, sesi: Optional[SesiAsr]) -> str:
        """Tutup sesi dan kembalikan teks final (setelah sisa audio di-decode)."""
        if sesi is None or not self.recognizer:
            return ""
        try:
            import numpy as np

            with self._kunci:
                # Ekor hening 0,1 detik agar sisa bingkai yang masih tertahan di
                # dalam stream ikut ter-decode sebelum hasil final dibaca.
                sesi.stream.accept_waveform(
                    SAMPLE_RATE, np.zeros(SAMPLE_RATE // 10, dtype="float32")
                )
                sesi.stream.input_finished()
                while self.recognizer.is_ready(sesi.stream):
                    self.recognizer.decode_stream(sesi.stream)
                teks = (self.recognizer.get_result(sesi.stream) or "").strip()
        except Exception as galat:
            print(f"[STT] Gagal menutup sesi: {galat}")
            teks = sesi.teks_terakhir
        if self._buang_halusinasi(teks):
            print(f"[STT] Abaikan halusinasi (kata berulang): {teks}")
            teks = ""
        return self._koreksi(teks)

    # ── Jalur BATCH (cadangan, kompatibel dengan /api/transcribe) ─────────────
    def transkripsikan_bytes(self, data_audio: bytes, bahasa: str = "id") -> Dict[str, Any]:
        """Ubah byte audio menjadi teks. Selalu mengembalikan dict, tidak pernah raise."""
        if not data_audio or len(data_audio) < 1000:
            return {"teks": "", "pesan": "Audio terlalu pendek", "sukses": True}
        if not (self.apakah_siap and self.recognizer is not None):
            return {"teks": "", "pesan": "Model ASR belum siap", "sukses": False}

        pcm = self._ke_mono_16k(data_audio)
        if pcm is None:
            return {"teks": "", "pesan": "Format audio tidak dikenali", "sukses": True}

        durasi = len(pcm) / float(SAMPLE_RATE)
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

        sesi = self.buat_sesi()
        if sesi is None:
            return {"teks": "", "pesan": "Sesi ASR gagal dibuat", "sukses": False}
        # Suapkan per 0,5 detik supaya jalur batch memakai mekanisme streaming
        # yang sama persis dengan jalur real-time.
        langkah = SAMPLE_RATE // 2
        for i in range(0, len(pcm), langkah):
            self.terima_pcm(sesi, pcm[i : i + langkah])
        teks = self.akhirkan(sesi)
        return {
            "teks": teks,
            "sukses": True,
            "bahasa": self._normalisasi_bahasa(bahasa),
            "durasi": round(durasi, 2),
            "energi": round(energi, 4),
        }

    def info(self) -> Dict[str, Any]:
        return {
            "apakah_siap": self.apakah_siap,
            "model": self.nama_model_aktif,
            "perangkat": self.perangkat_aktif,
            "streaming": True,
        }


def dapatkan_stt() -> SttEngine:
    """Ambil instansi tunggal SttEngine."""
    return SttEngine()


if __name__ == "__main__":
    mesin = dapatkan_stt()
    print("Status STT:", mesin.info())
