"""
SELA AI Desktop - Sintesis Suara Offline 100% OmniVoice Voice Design
====================================================================
Mesin suara perempuan alami kampus UCIC berbasis k2-fsa/OmniVoice Voice Design:
1. Jalur Suara Tunggal & Murni (OmniVoice Voice Design):
   - Karakter suara perempuan muda, ceria, imut, dan ramah (female, young adult, high pitch).
   - Mendukung penuh Bahasa Indonesia (ind) dan Bahasa Inggris (eng).
   - Seluruh dependensi Piper telah dihapus 100%.
2. Inisialisasi Instan (Eager Loading):
   - Memuat model k2-fsa/OmniVoice secara langsung dari cache Hugging Face lokal (~2 detik saat server start).
   - Siap seketika sejak awal aplikasi dibuka tanpa delay background thread.
3. Disk & Memory Audio Caching (Latensi 0ms):
   - Seluruh jawaban dan kalimat populer disimpan di direktori cache_audio/omnivoice/.
   - Pemanggilan berulang atau pertanyaan umum langsung diputar dengan latensi 0 ms.
"""

import os
import io
import re
import wave
import asyncio
import base64
import hashlib
import threading
from typing import Optional, Dict, Any, List

import numpy as np


OMNIVOICE_MODEL_ID = "k2-fsa/OmniVoice"

# Kode bahasa untuk OmniVoice.generate(language=...)
OMNIVOICE_KODE_BAHASA = {
    "id": "id",   # Indonesian
    "jv": "id",   # Javanese -> dialihkan ke Indonesian
    "jw": "id",
    "jawa": "id",
    "en": "en",   # English
}


def _normalisasi_kode_bahasa(bahasa: Optional[str]) -> str:
    """Petakan 'id-ID', 'ID', 'jawa', 'EN' dsb. menjadi 'id' / 'en' / 'jv'."""
    kode = (bahasa or "id").strip().lower().replace("_", "-")
    kode_utama = kode.split("-")[0]
    if kode_utama in ("jv", "jw", "jawa"):
        return "jv"
    if kode_utama.startswith("en"):
        return "en"
    return "id"


def _bersihkan_teks_untuk_tts(teks: str) -> str:
    """Buang markdown/URL/emoji agar diucapkan natural, bukan dieja simbol."""
    if not teks:
        return ""
    bersih = teks.strip()
    # URL tidak dieja huruf per huruf; pembaca tetap mendapat arahan yang jelas.
    bersih = re.sub(r"https?://\S+", "Linknya bisa kamu akses di sini.", bersih)
    # Markdown formatting
    bersih = re.sub(r"\*\*(.+?)\*\*", r"\1", bersih)
    bersih = re.sub(r"^#{1,3}\s+", "", bersih, flags=re.MULTILINE)
    bersih = re.sub(r"^>\s?", "", bersih, flags=re.MULTILINE)
    # Follow-up tag dan emoji
    bersih = re.sub(r"\[[^\]\n]*\]", "", bersih)
    bersih = re.sub(r"[😀-🙏🌀-🗿🚀-🛿☀-➿]+", "", bersih)
    bersih = re.sub(r"\s+", " ", bersih).strip()
    return bersih


def _pecah_kalimat(teks: str, batas: int = 220) -> List[str]:
    """Pecah teks panjang menjadi potongan < batas karakter per sintesis."""
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
                    hasil.append(kalimat[i:i + batas])
                penampung = ""
    if penampung:
        hasil.append(penampung)
    return hasil or [teks]


def _tulis_wav_bytes(frames_int16: bytes, sample_rate: int,
                     channels: int = 1, width: int = 2) -> bytes:
    """Rangkai frame PCM int16 menjadi berkas WAV (bytes) via stdlib."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(sample_rate)
        wav.writeframes(frames_int16)
    return buffer.getvalue()


class SintesisSuaraOffline:
    """
    Mesin TTS Offline 100% OmniVoice Voice Design (Tanpa Piper).
    """

    def __init__(self, direktori_sampel_suara: Optional[str] = None):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))

        if direktori_sampel_suara is None:
            direktori_sampel_suara = os.path.join(self.direktori_induk, "voice_samples")
        self.direktori_sampel_suara = direktori_sampel_suara
        os.makedirs(self.direktori_sampel_suara, exist_ok=True)

        self.direktori_cache = os.path.join(self.direktori_induk, "cache_audio")
        self.direktori_cache_omnivoice = os.path.join(self.direktori_cache, "omnivoice")
        os.makedirs(self.direktori_cache, exist_ok=True)
        os.makedirs(self.direktori_cache_omnivoice, exist_ok=True)

        # Muat daftar berkas sampel audio kloning dari direktori jika ada
        self.daftar_sampel_audio = [
            f for f in os.listdir(self.direktori_sampel_suara) if f.lower().endswith(".wav")
        ]

        self.cache_audio: Dict[str, str] = {}
        self.apakah_siap = False

        # OmniVoice state
        self._omnivoice_model = None
        self._omnivoice_sr = 24000
        self._omnivoice_perangkat = "cpu"
        self._omnivoice_siap = False
        self._omnivoice_gagal = False
        self._kunci_omnivoice = threading.Lock()

        # SELA memakai satu engine suara agar warna suara selalu konsisten.

        # 1. Muat cache audio disk terlebih dahulu (0ms respon untuk kalimat umum)
        self.muat_cache_audio_dari_disk()

        # 2. Inisialisasi Eager OmniVoice langsung saat startup (~2 detik dari cache lokal)
        self._inisialisasi_omnivoice()

    def _inisialisasi_omnivoice(self):
        """
        Muat model k2-fsa/OmniVoice secara langsung dari cache Hugging Face lokal.
        Model sudah terunduh di cache Hugging Face, sehingga pemuatan langsung siap dalam ~2 detik.
        """
        try:
            import torch
            from omnivoice import OmniVoice

            print(
                f"[TTS OmniVoice] Memuat model {OMNIVOICE_MODEL_ID} dari cache lokal..."
            )
            perangkat = "cuda" if torch.cuda.is_available() else "cpu"
            tipe_data = torch.float16 if perangkat == "cuda" else torch.float32

            model = OmniVoice.from_pretrained(
                OMNIVOICE_MODEL_ID,
                torch_dtype=tipe_data,
            )
            model = model.to(perangkat)
            model.eval()

            sr = getattr(model.config, "sampling_rate", None) or 24000

            with self._kunci_omnivoice:
                self._omnivoice_model = model
                self._omnivoice_sr = sr
                self._omnivoice_perangkat = perangkat
                self._omnivoice_siap = True
                self.apakah_siap = True

            print(
                f"[TTS OmniVoice] SIAP! 100% Full OmniVoice Voice Design aktif (female, young adult, high pitch). "
                f"Sample rate: {sr}Hz, device: {perangkat}"
            )

        except Exception as galat:
            import traceback
            print(
                f"[TTS OmniVoice] GAGAL diinisialisasi: {galat}\n"
                f"{traceback.format_exc()}"
            )
            with self._kunci_omnivoice:
                self._omnivoice_gagal = True

    def sintesis_dengan_omnivoice(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """
        Sintesis suara murni OmniVoice Voice Design:
        - Karakter suara perempuan muda, ramah, imut, dan ekspresif.
        - Menggunakan instruct="female, young adult, high pitch".
        - Mendukung Bahasa Indonesia dan Bahasa Inggris secara penuh tanpa Piper.
        """
        teks_bersih = _bersihkan_teks_untuk_tts(teks)
        if not teks_bersih:
            return None

        kode_bahasa = _normalisasi_kode_bahasa(bahasa)
        kode_omni = OMNIVOICE_KODE_BAHASA.get(kode_bahasa, "ind")

        # Karakter suara perempuan muda dan imut dengan intonasi ceria & berkarakter
        instruksi_karakter = "female, young adult, high pitch"

        semua_frame: List[np.ndarray] = []
        try:
            # Model generatif/GPU tidak aman dipakai paralel oleh endpoint
            # REST dan WebSocket. Satu antrean kecil jauh lebih stabil daripada
            # audio kosong atau proses CUDA yang saling bertabrakan.
            with self._kunci_omnivoice:
                model_siap = self._omnivoice_siap
                model = self._omnivoice_model
                sr = self._omnivoice_sr
                if not model_siap or model is None:
                    return None
                for potongan in _pecah_kalimat(teks_bersih):
                    hasil = model.generate(
                        text=potongan,
                        language=kode_omni,
                        instruct=instruksi_karakter,
                        speed=1.05,
                    )
                    if hasil and len(hasil) > 0:
                        semua_frame.append(hasil[0])

            if not semua_frame:
                print("[TTS OmniVoice] Generasi menghasilkan audio kosong.")
                return None

            # Gabungkan semua potongan audio
            audio_np = (
                np.concatenate(semua_frame) if len(semua_frame) > 1 else semua_frame[0]
            )
            # Normalisasi float array ke int16 WAV
            audio_int16 = (
                np.clip(audio_np, -1.0, 1.0) * 32767.0
            ).astype(np.int16).tobytes()
            return _tulis_wav_bytes(audio_int16, sample_rate=sr, channels=1, width=2)

        except Exception as galat:
            import traceback
            print(f"[TTS OmniVoice] Generasi Voice Design gagal: {galat}\n{traceback.format_exc()}")
            return None

    # ── Cache & Asinkron ──────────────────────────────────────
    def _kunci_cache(self, teks: str, bahasa: str, engine: str = "omnivoice-vd") -> str:
        bersih = _bersihkan_teks_untuk_tts(teks).lower()
        kode = _normalisasi_kode_bahasa(bahasa)
        gabung = f"{engine}:{kode}:{bersih}"
        return hashlib.md5(gabung.encode("utf-8")).hexdigest()

    def muat_cache_audio_dari_disk(self):
        """Memuat berkas audio OmniVoice yang tersimpan di disk cache."""
        for folder in (self.direktori_cache_omnivoice, self.direktori_cache):
            if not os.path.exists(folder):
                continue
            for berkas in os.listdir(folder):
                if berkas.endswith(".wav"):
                    kunci = berkas[:-4]
                    jalur = os.path.join(folder, berkas)
                    try:
                        with open(jalur, "rb") as f:
                            self.cache_audio[kunci] = base64.b64encode(f.read()).decode("ascii")
                    except Exception:
                        pass
        print(f"[Sintesis Suara] Memuat {len(self.cache_audio)} berkas audio OmniVoice dari disk cache!")

    def _simpan_ke_disk_cache(self, kunci: str, b64_audio: str, engine: str = "omnivoice"):
        self.cache_audio[kunci] = b64_audio
        jalur_berkas = os.path.join(self.direktori_cache_omnivoice, f"{kunci}.wav")
        try:
            with open(jalur_berkas, "wb") as f:
                f.write(base64.b64decode(b64_audio))
        except Exception as galat:
            print(f"[Sintesis Suara] Gagal menyimpan cache disk: {galat}")

    def status_engine(self) -> Dict[str, Any]:
        """Kembalikan status engine TTS untuk diagnostik antarmuka desktop."""
        perangkat_omni = getattr(self, "_omnivoice_perangkat", "cpu")
        return {
            "omnivoice_siap": self._omnivoice_siap,
            "omnivoice_voice_design": True,
            "omnivoice_perangkat": perangkat_omni,
            "omnivoice_gagal": self._omnivoice_gagal,
            "omnivoice_model_dimuat": self._omnivoice_model is not None,
            "jumlah_cache_audio": len(self.cache_audio),
            "engine_aktif": "omnivoice-voicedesign" if self._omnivoice_siap else "omnivoice-unavailable",
            "pesan_status": (
                "100% Full OmniVoice Voice Design AKTIF (Karakter Wanita Imut, Ceria & Alami)"
                if self._omnivoice_siap
                else "Menyiapkan mesin TTS..."
            ),
        }

    async def sintesis_teks_ke_audio_base64_async(
        self, teks: str, bahasa: str = "id"
    ) -> Dict[str, Any]:
        """
        API Utama Sintesis Suara SELA (100% Full OmniVoice Voice Design):
        - Cek disk & memory cache (Respon instan 0ms)
        - Sintesis langsung dengan OmniVoice Voice Design
        - Simpan hasil sintesis ke disk cache agar instan pada pemanggilan berikutnya.
        """
        kode_bahasa = _normalisasi_kode_bahasa(bahasa)
        teks_bersih = _bersihkan_teks_untuk_tts(teks)

        if not teks_bersih:
            return {"audio_base64": "", "format": "audio/wav", "engine": "none", "sukses": True}

        # 1. Cek cache OmniVoice (Respon instan 0ms)
        for prefiks in ("omnivoice-vd", "omnivoice", ""):
            kunci_omni = self._kunci_cache(teks_bersih, kode_bahasa, prefiks)
            if kunci_omni in self.cache_audio:
                return {
                    "audio_base64": self.cache_audio[kunci_omni],
                    "format": "audio/wav",
                    "engine": "omnivoice-voicedesign (cache)",
                    "bahasa": kode_bahasa,
                    "sukses": True,
                }
            # Cek berkas disk cache langsung
            jalur_disk = os.path.join(self.direktori_cache_omnivoice, f"{kunci_omni}.wav")
            if os.path.exists(jalur_disk) and os.path.getsize(jalur_disk) > 100:
                try:
                    with open(jalur_disk, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                        self.cache_audio[kunci_omni] = b64
                        return {
                            "audio_base64": b64,
                            "format": "audio/wav",
                            "engine": "omnivoice-voicedesign (cache-disk)",
                            "bahasa": kode_bahasa,
                            "sukses": True,
                        }
                except Exception:
                    pass

        loop = asyncio.get_running_loop()

        # 2. Sintesis Murni OmniVoice Voice Design
        if self._omnivoice_siap:
            try:
                wav_bytes = await loop.run_in_executor(
                    None, self.sintesis_dengan_omnivoice, teks_bersih, kode_bahasa
                )
                if wav_bytes:
                    b64_hasil = base64.b64encode(wav_bytes).decode("ascii")
                    kunci_simpan = self._kunci_cache(teks_bersih, kode_bahasa, "omnivoice-vd")
                    self._simpan_ke_disk_cache(kunci_simpan, b64_hasil, "omnivoice")
                    return {
                        "audio_base64": b64_hasil,
                        "format": "audio/wav",
                        "engine": "omnivoice-voicedesign",
                        "bahasa": kode_bahasa,
                        "sukses": True,
                    }
            except Exception as galat_omni:
                print(f"[Sintesis Suara] OmniVoice Voice Design gagal: {galat_omni}")

        # Engine utama belum siap atau gagal: jangan ganti karakter SELA dengan
        # engine lain. Frontend akan mempertahankan status error/retry, bukan
        # membunyikan suara yang tidak konsisten.
        print(f"[Sintesis Suara] OmniVoice belum dapat menyintesis: '{teks_bersih[:50]}...'")
        return {
            "audio_base64": "",
            "format": "audio/wav",
            "engine": "omnivoice-unavailable",
            "bahasa": kode_bahasa,
            "sukses": False,
            "teks_fallback": teks_bersih,
        }

    def sintesis_teks_ke_audio_base64(self, teks: str, bahasa: str = "id") -> Dict[str, Any]:
        """Versi sinkron dari sintesis suara untuk kemudahan pemanggilan."""
        try:
            return asyncio.run(self.sintesis_teks_ke_audio_base64_async(teks, bahasa))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.sintesis_teks_ke_audio_base64_async(teks, bahasa))
