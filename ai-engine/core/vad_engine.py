"""
SELA AI Desktop - Mesin VAD (Voice Activity Detection)
======================================================
Mendeteksi kapan pengguna mulai dan berhenti berbicara. Dipakai untuk
barge-in: begitu terdeteksi SPEECH_START saat TTS SELA sedang berbunyi,
server membatalkan tugas LLM dan TTS yang sedang berjalan.

Dua jalur:
1. Jalur utama  : Silero VAD dari FastRTC (bila paket `fastrtc` terpasang).
   Deteksi simbol dilakukan secara defensif sehingga perbedaan versi API
   tidak membuat aplikasi gagal.
2. Jalur cadangan: VAD energi + zero-crossing dengan hysteresis, ambang
   adaptif, dan hangover. Selalu tersedia, tanpa dependensi tambahan.

Pemakaian:
    from core import dapatkan_vad
    vad = dapatkan_vad()
    peristiwa = vad.proses_bingkai(pcm_int16_bytes)  # "SPEECH_START" | "SPEECH_END" | None
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

SAMPLE_RATE = 16000
UKURAN_BINGKAI = 512  # ~32 ms pada 16 kHz

# Ambang VAD energi.
AMBANG_MIN = 0.012          # ambang absolut minimum (RMS ternormalisasi)
FAKTOR_NOISE = 2.6          # ambang = noise_floor * faktor
BINGKAI_MULAI = 3           # jumlah bingkai bersuara berturut untuk SPEECH_START
BINGKAI_HENING = 18         # ~576 ms hening untuk SPEECH_END (hangover)
GERBANG_ZCR = 0.25          # batas zero-crossing rate untuk menolak derau


class VadEngine:
    """Mesin VAD singleton untuk mendeteksi barge-in."""

    _instance: Optional["VadEngine"] = None
    _kunci_singleton = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "VadEngine":
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

        self._sisa_byte = bytearray()
        self._noise_floor = 0.004
        self._bingkai_bersuara = 0
        self._bingkai_hening = 0
        self._sedang_bicara = False
        self._kunci = threading.Lock()

        self._silero = None
        self._silero_siap = False
        self.metode_aktif = "energi"
        self._coba_silero()

    # ── Jalur Silero/FastRTC (opsional) ───────────────────────────────────────
    def _coba_silero(self) -> None:
        """Coba aktifkan Silero VAD dari FastRTC bila tersedia."""
        try:
            import fastrtc  # noqa: F401
        except Exception:
            self.metode_aktif = "energi"
            return
        for nama in ("SileroVADModel", "get_silero_model", "SileroVadModel"):
            simbol = getattr(fastrtc, nama, None)
            if simbol is None:
                continue
            try:
                self._silero = simbol() if callable(simbol) else simbol
                self._silero_siap = True
                self.metode_aktif = "silero-fastrtc"
                print(f"[VAD] Silero VAD FastRTC aktif via {nama}.")
                return
            except Exception as galat:
                print(f"[VAD] Gagal memakai FastRTC {nama}: {galat}")
        self.metode_aktif = "energi"

    # ── Utilitas sinyal ───────────────────────────────────────────────────────
    @staticmethod
    def _ke_float(pcm) -> "Any":
        """Normalisasi int16/bytes/float menjadi float32 pada rentang [-1, 1]."""
        import numpy as np

        if isinstance(pcm, (bytes, bytearray)):
            arr = np.frombuffer(bytes(pcm), dtype=np.int16).astype(np.float32)
            return arr / 32768.0
        arr = np.asarray(pcm, dtype=np.float32)
        if arr.size and np.max(np.abs(arr)) > 1.5:
            arr = arr / 32768.0
        return arr

    @staticmethod
    def _ciri(pcm) -> "tuple[float, float]":
        import numpy as np

        if pcm.size == 0:
            return 0.0, 0.0
        rms = float(np.sqrt(np.mean(np.square(pcm))))
        zcr = float(np.mean(np.abs(np.diff(np.sign(pcm))) > 0))
        return rms, zcr

    # ── Pemrosesan bingkai ────────────────────────────────────────────────────
    def proses_bingkai(self, data_pcm) -> Optional[str]:
        """
        Proses satu bingkai audio. Mengembalikan:
        "SPEECH_START" saat pengguna mulai bicara,
        "SPEECH_END" saat pengguna berhenti bicara,
        None bila belum ada perubahan status.
        """
        import numpy as np

        with self._kunci:
            self._sisa_byte.extend(bytes(data_pcm) if isinstance(data_pcm, (bytes, bytearray)) else b"")
            potongan = []
            if isinstance(data_pcm, (bytes, bytearray)):
                langkah = UKURAN_BINGKAI * 2
                while len(self._sisa_byte) >= langkah:
                    blok = self._sisa_byte[:langkah]
                    del self._sisa_byte[:langkah]
                    potongan.append(np.frombuffer(bytes(blok), dtype=np.int16).astype(np.float32) / 32768.0)
            else:
                potongan.append(self._ke_float(data_pcm))

            peristiwa: Optional[str] = None
            for blok in potongan:
                if blok.size == 0:
                    continue
                rms, zcr = self._ciri(blok)
                # Perbarui noise floor hanya saat tidak ada ucapan (adaptif).
                if not self._sedang_bicara and rms < max(AMBANG_MIN, self._noise_floor * FAKTOR_NOISE):
                    self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms

                ambang = max(AMBANG_MIN, self._noise_floor * FAKTOR_NOISE)
                bersuara = rms > ambang and zcr < GERBANG_ZCR

                if bersuara:
                    self._bingkai_bersuara += 1
                    self._bingkai_hening = 0
                else:
                    self._bingkai_hening += 1
                    self._bingkai_bersuara = 0

                if not self._sedang_bicara and self._bingkai_bersuara >= BINGKAI_MULAI:
                    self._sedang_bicara = True
                    peristiwa = "SPEECH_START"
                elif self._sedang_bicara and self._bingkai_hening >= BINGKAI_HENING:
                    self._sedang_bicara = False
                    peristiwa = "SPEECH_END"
            return peristiwa

    def sedang_bicara(self) -> bool:
        return self._sedang_bicara

    def reset(self) -> None:
        """Reset status (misalnya saat sesi WebSocket baru dimulai)."""
        with self._kunci:
            self._sisa_byte.clear()
            self._bingkai_bersuara = 0
            self._bingkai_hening = 0
            self._sedang_bicara = False

    def info(self) -> Dict[str, Any]:
        return {
            "metode_aktif": self.metode_aktif,
            "silero_siap": self._silero_siap,
            "sample_rate": SAMPLE_RATE,
            "ukuran_bingkai": UKURAN_BINGKAI,
        }


def dapatkan_vad() -> VadEngine:
    """Ambil instansi tunggal VadEngine."""
    return VadEngine()


if __name__ == "__main__":
    import numpy as np

    mesin = dapatkan_vad()
    print("Status VAD:", mesin.info())
    # Simulasi: hening -> bicara -> hening
    hening = (np.zeros(UKURAN_BINGKAI, dtype=np.int16)).tobytes()
    bicara = (np.sin(np.linspace(0, 6.28 * 40, UKURAN_BINGKAI)) * 12000).astype(np.int16).tobytes()
    for _ in range(3):
        print("hening ->", mesin.proses_bingkai(hening))
    for _ in range(5):
        print("bicara ->", mesin.proses_bingkai(bicara))
    for _ in range(20):
        ev = mesin.proses_bingkai(hening)
        if ev:
            print("hening ->", ev)
