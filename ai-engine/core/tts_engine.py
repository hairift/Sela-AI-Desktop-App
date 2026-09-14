"""
SELA AI Desktop - Mesin TTS Tunggal (Singleton) berbasis Piper
==============================================================
Satu-satunya jalur sintesis suara di aplikasi. Piper ONNX dimuat SEKALI saat
startup lalu dipakai ulang untuk semua permintaan (pola singleton).

Karakter suara:
- id : id_ID-ucic-sela-medium.onnx (custom hasil cloning) bila tersedia,
       jika tidak ada otomatis memakai id_ID-news_tts-medium.onnx.
- en : en_US-amy-medium.onnx.

Sesuai aturan proyek: TIDAK ADA berkas sementara di disk. Seluruh audio
dirangkai di memori memakai io.BytesIO + modul `wave`.

Pemakaian:
    from core import dapatkan_tts
    tts = dapatkan_tts()
    wav_bytes = tts.sintesis_wav_bytes("Halo, saya SELA.")
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import threading
import wave
from typing import Any, Dict, List, Optional

# Nama berkas model Piper yang didukung.
MODEL_ID_CUSTOM = "id_ID-ucic-sela-medium.onnx"
MODEL_ID_DEFAULT = "id_ID-news_tts-medium.onnx"
MODEL_EN_DEFAULT = "en_US-amy-medium.onnx"

_MAKS_KARAKTER_KALIMAT = 220


def normalisasi_bahasa(bahasa: Optional[str]) -> str:
    """Petakan 'id-ID', 'ID', 'jawa', 'EN' menjadi 'id' atau 'en'."""
    kode = (bahasa or "id").strip().lower().replace("_", "-").split("-")[0]
    if kode.startswith("en"):
        return "en"
    # Jawa dialihkan ke Indonesia karena fonetik serumpun.
    return "id"


def bersihkan_teks_tts(teks: str) -> str:
    """Buang markdown, tautan, dan emoji agar diucapkan natural (bukan dieja)."""
    if not teks:
        return ""
    bersih = teks.strip()
    bersih = re.sub(r"https?://\S+", "tautannya ada di layar ya", bersih)
    bersih = re.sub(r"\*\*(.+?)\*\*", r"\1", bersih)
    bersih = re.sub(r"\*(.+?)\*", r"\1", bersih)
    bersih = re.sub(r"^#{1,6}\s+", "", bersih, flags=re.MULTILINE)
    bersih = re.sub(r"^[>\-\*•]\s?", "", bersih, flags=re.MULTILINE)
    bersih = re.sub(r"\[([^\]\n]*)\]", "", bersih)
    bersih = re.sub(r"[😀-🙏🌀-🗿🚀-🛿☀-➿]+", "", bersih)
    bersih = re.sub(r"\s+", " ", bersih).strip()
    return bersih


def pecah_kalimat(teks: str, batas: int = _MAKS_KARAKTER_KALIMAT) -> List[str]:
    """Pecah teks panjang menjadi potongan pendek agar sintesis cepat mengalir."""
    if not teks:
        return []
    if len(teks) <= batas:
        return [teks]
    bagian = re.split(r"(?<=[.!?])\s+", teks)
    hasil: List[str] = []
    penampung = ""
    for kalimat in bagian:
        kandidat = (penampung + " " + kalimat).strip()
        if len(kandidat) <= batas:
            penampung = kandidat
        else:
            if penampung:
                hasil.append(penampung)
            if len(kalimat) <= batas:
                penampung = kalimat
            else:
                for i in range(0, len(kalimat), batas):
                    hasil.append(kalimat[i : i + batas])
                penampung = ""
    if penampung:
        hasil.append(penampung)
    return hasil or [teks]


class TtsEngine:
    """Pembungkus tunggal PiperVoice untuk sintesis suara SELA."""

    _instance: Optional["TtsEngine"] = None
    _kunci_singleton = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "TtsEngine":
        if cls._instance is None:
            with cls._kunci_singleton:
                if cls._instance is None:
                    instansi = super().__new__(cls)
                    instansi._sudah_disiapkan = False
                    cls._instance = instansi
        return cls._instance

    def __init__(self, direktori_model: Optional[str] = None) -> None:
        if getattr(self, "_sudah_disiapkan", False):
            return
        self._sudah_disiapkan = True

        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        if direktori_model is None:
            direktori_model = os.path.abspath(
                os.path.join(self.direktori_induk, "..", "models", "tts_piper")
            )
        self.direktori_model = direktori_model

        self._voices: Dict[str, Any] = {}
        self._kunci_sintesis = threading.Lock()
        self.apakah_siap = False
        self.pesan_status = "belum dimuat"
        self.nama_model_aktif: Dict[str, str] = {}

        self._muat_voices()

    # ── Pemuatan model ────────────────────────────────────────────────────────
    def _pilih_berkas(self, kandidat: List[str]) -> Optional[str]:
        for nama in kandidat:
            jalur = os.path.join(self.direktori_model, nama)
            if os.path.exists(jalur):
                return jalur
        return None

    def _muat_voices(self) -> None:
        try:
            from piper import PiperVoice
        except Exception as galat:  # pragma: no cover
            self.apakah_siap = False
            self.pesan_status = f"piper-tts belum terpasang: {galat}"
            print("[TTS] piper-tts belum terpasang. Jalankan: pip install piper-tts")
            return

        rencana = {
            "id": [MODEL_ID_CUSTOM, MODEL_ID_DEFAULT],
            "en": [MODEL_EN_DEFAULT],
        }
        for bahasa, kandidat in rencana.items():
            jalur = self._pilih_berkas(kandidat)
            if not jalur:
                print(f"[TTS] Model Piper '{bahasa}' tidak ditemukan di {self.direktori_model}")
                continue
            try:
                self._voices[bahasa] = PiperVoice.load(jalur)
                self.nama_model_aktif[bahasa] = os.path.basename(jalur)
                print(f"[TTS] Piper '{bahasa}' siap: {os.path.basename(jalur)}")
            except Exception as galat:
                print(f"[TTS] Gagal memuat Piper '{bahasa}': {galat}")

        self.apakah_siap = bool(self._voices)
        if self.apakah_siap:
            self.pesan_status = "Piper siap: " + ", ".join(
                f"{b}={n}" for b, n in self.nama_model_aktif.items()
            )
        else:
            self.pesan_status = "tidak ada model Piper yang berhasil dimuat"

    # ── Sintesis (in-memory, tanpa berkas tmp) ────────────────────────────────
    def sintesis_wav_bytes(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """Sintesis satu potongan teks menjadi byte WAV di memori."""
        teks_bersih = bersihkan_teks_tts(teks)
        if not teks_bersih:
            return None
        kode = normalisasi_bahasa(bahasa)
        voice = self._voices.get(kode) or self._voices.get("id")
        if voice is None:
            return None
        buffer = io.BytesIO()
        try:
            with self._kunci_sintesis:
                with wave.open(buffer, "wb") as wav:
                    voice.synthesize_wav(teks_bersih, wav)
            data = buffer.getvalue()
            return data or None
        except Exception as galat:
            print(f"[TTS] Sintesis gagal: {galat}")
            return None
        finally:
            buffer.close()

    async def sintesis_base64_async(self, teks: str, bahasa: str = "id") -> Dict[str, Any]:
        """API asinkron utama: hasilkan audio WAV base64 untuk frontend."""
        kode = normalisasi_bahasa(bahasa)
        if not self.apakah_siap:
            return {
                "audio_base64": "",
                "format": "audio/wav",
                "engine": "piper-unavailable",
                "bahasa": kode,
                "sukses": False,
            }

        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, self.sintesis_wav_bytes, teks, kode)
        if not wav_bytes:
            return {
                "audio_base64": "",
                "format": "audio/wav",
                "engine": "piper-empty",
                "bahasa": kode,
                "sukses": False,
            }
        return {
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "format": "audio/wav",
            "engine": "piper",
            "bahasa": kode,
            "sukses": True,
        }

    def sintesis_base64(self, teks: str, bahasa: str = "id") -> Dict[str, Any]:
        """Versi sinkron dari sintesis_base64_async."""
        try:
            return asyncio.run(self.sintesis_base64_async(teks, bahasa))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.sintesis_base64_async(teks, bahasa))

    def status_engine(self) -> Dict[str, Any]:
        """Status engine untuk endpoint /api/status-tts."""
        return {
            "piper_siap": self.apakah_siap,
            "engine_aktif": "piper" if self.apakah_siap else "piper-unavailable",
            "model_aktif": self.nama_model_aktif,
            "pesan_status": self.pesan_status,
        }


def dapatkan_tts() -> TtsEngine:
    """Ambil instansi tunggal TtsEngine."""
    return TtsEngine()


if __name__ == "__main__":
    mesin = dapatkan_tts()
    print("Status TTS:", mesin.status_engine())
    if mesin.apakah_siap:
        data = mesin.sintesis_wav_bytes("Halo, saya SELA dari UCIC Cirebon.", "id")
        print("Ukuran WAV:", len(data) if data else 0, "bytes")
