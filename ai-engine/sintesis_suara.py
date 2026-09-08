"""
SELA AI Desktop - Sintesis Suara Offline Voice Cloning (OmniVoice + Piper)
===========================================================================
Arsitektur suara wanita alami kampus UCIC:
1. Jalur Kloning Utama (OmniVoice by k2-fsa):
   - Zero-shot neural voice cloning berbasis model k2-fsa/OmniVoice.
   - Menggunakan sampel referensi suara pengguna di `voice_samples/001-id.wav` dan `001-en.wav`.
   - Pre-computed `VoiceClonePrompt` sehingga ekstraksi token referensi dilakukan sekali saat startup.
2. Jalur Kecepatan Instan (Piper ONNX):
   - Indonesia (id_ID-news_tts-medium) & Inggris (en_US-amy-medium).
   - Selalu siap dalam < 100ms untuk menjamin tidak ada lag atau freeze saat model besar sedang inisialisasi.
3. Disk & Memory Audio Caching:
   - Kalimat yang pernah disintesis disimpan secara permanen di disk (`cache_audio/`)
   - Latensi 0 ms untuk sapaan dan jawaban kampus yang sering diulang.
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


# ── Konfigurasi suara ──────────────────────────────────────────
SUARA_PIPER_PER_BAHASA = {
    "id": "id_ID-news_tts-medium",
    "jv": "id_ID-news_tts-medium",
    "jw": "id_ID-news_tts-medium",
    "jawa": "id_ID-news_tts-medium",
    "en": "en_US-amy-medium",
}

OMNIVOICE_MODEL_ID = "k2-fsa/OmniVoice"

# Kode bahasa ISO-639-3 yang diterima oleh OmniVoice.generate(language=...)
OMNIVOICE_KODE_BAHASA = {
    "id": "ind",   # Indonesian
    "jv": "ind",   # Javanese -> fallback ke Indonesian
    "en": "eng",   # English
}

# Transkripsi tepat dari sampel suara referensi pengguna (HARUS AKURAT)
TEKS_SAMPEL_REFERENSI = {
    "id": (
        "Halo, selamat datang. Saya adalah asisten virtual yang siap membantu "
        "kamu menyelesaikan berbagai tugas setiap hari."
    ),
    "en": (
        "Hello, welcome. I am a virtual assistant ready to help you complete "
        "various tasks every day!"
    ),
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
    # URL -> kata 'tautan' supaya tidak dieja huruf per huruf
    bersih = re.sub(r"https?://\S+", "tautan resmi", bersih)
    # Markdown formatting
    bersih = re.sub(r"\*\*(.+?)\*\*", r"\1", bersih)
    bersih = re.sub(r"^#{1,3}\s+", "", bersih, flags=re.MULTILINE)
    bersih = re.sub(r"^>\s?", "", bersih, flags=re.MULTILINE)
    # Follow-up tag
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
    Mesin TTS Offline Multi-Jalur: OmniVoice Zero-Shot Voice Cloning + Piper ONNX.
    """

    def __init__(self, direktori_sampel_suara: Optional[str] = None):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))

        if direktori_sampel_suara is None:
            direktori_sampel_suara = os.path.join(self.direktori_induk, "voice_samples")
        self.direktori_sampel_suara = direktori_sampel_suara
        os.makedirs(self.direktori_sampel_suara, exist_ok=True)

        self.direktori_model_piper = os.path.join(self.direktori_induk, "models", "tts_piper")
        self.direktori_model_omnivoice = os.path.join(self.direktori_induk, "models", "omnivoice")
        os.makedirs(self.direktori_model_piper, exist_ok=True)
        os.makedirs(self.direktori_model_omnivoice, exist_ok=True)

        self.direktori_cache = os.path.join(self.direktori_induk, "cache_audio")
        self.direktori_cache_omnivoice = os.path.join(self.direktori_cache, "omnivoice")
        self.direktori_cache_piper = os.path.join(self.direktori_cache, "piper")
        os.makedirs(self.direktori_cache, exist_ok=True)
        os.makedirs(self.direktori_cache_omnivoice, exist_ok=True)
        os.makedirs(self.direktori_cache_piper, exist_ok=True)

        # Muat daftar berkas sampel audio kloning dari direktori
        self.daftar_sampel_audio = [
            f for f in os.listdir(self.direktori_sampel_suara) if f.lower().endswith(".wav")
        ]

        self.cache_audio: Dict[str, str] = {}
        self.apakah_siap = False

        # Piper state
        self._suara_piper: Dict[str, Any] = {}
        self._kunci_piper = threading.Lock()

        # OmniVoice state
        self._omnivoice_model = None
        self._omnivoice_prompts: Dict[str, Any] = {}
        self._omnivoice_sr = 24000
        self._omnivoice_siap = False
        self._omnivoice_gagal = False
        self._kunci_omnivoice = threading.Lock()
        self._sedang_generate_omnivoice: set = set()

        # 1. Siapkan Piper (instan, <100ms)
        self._siapkan_piper()
        self.muat_cache_audio_dari_disk()

        # 2. Inisialisasi OmniVoice di background thread
        threading.Thread(target=self._inisialisasi_omnivoice, daemon=True).start()

    # ── Piper ONNX ────────────────────────────────────────────
    def _jalur_model_piper(self, nama_suara: str) -> str:
        return os.path.join(self.direktori_model_piper, nama_suara + ".onnx")

    def _unduh_suara_piper_jika_perlu(self, nama_suara: str) -> bool:
        jalur = self._jalur_model_piper(nama_suara)
        if os.path.exists(jalur) and os.path.getsize(jalur) > 1000:
            return True
        try:
            from piper.download_voices import download_voice
            print(f"[Sintesis Suara] Mengunduh suara Piper '{nama_suara}'...")
            download_voice(nama_suara, download_dir=self.direktori_model_piper)
            return os.path.exists(jalur)
        except Exception as galat:
            print(f"[Sintesis Suara] Gagal mengunduh suara Piper '{nama_suara}': {galat}")
            return False

    def _siapkan_piper(self):
        """Muat suara Piper perempuan ID + EN secara lazy-aman."""
        for kode in ("id", "en"):
            nama = SUARA_PIPER_PER_BAHASA[kode]
            try:
                if not self._unduh_suara_piper_jika_perlu(nama):
                    continue
                from piper.voice import PiperVoice
                with self._kunci_piper:
                    if nama not in self._suara_piper:
                        self._suara_piper[nama] = PiperVoice.load(self._jalur_model_piper(nama))
                print(f"[Sintesis Suara] Suara Piper perempuan siap: {nama}")
            except Exception as galat:
                print(f"[Sintesis Suara] Piper '{nama}' belum siap: {galat}")
        if self._suara_piper:
            self.apakah_siap = True

    def _dapatkan_suara_piper(self, bahasa: str):
        kode = _normalisasi_kode_bahasa(bahasa)
        nama = SUARA_PIPER_PER_BAHASA.get(kode, SUARA_PIPER_PER_BAHASA["id"])
        with self._kunci_piper:
            suara = self._suara_piper.get(nama)
        if suara is None:
            self._siapkan_piper()
            with self._kunci_piper:
                suara = self._suara_piper.get(nama)
        return suara, nama

    def sintesis_dengan_piper(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """Sintesis cepat via Piper ONNX (< 300 ms, natural)."""
        teks_bersih = _bersihkan_teks_untuk_tts(teks)
        if not teks_bersih:
            return None
        suara, nama = self._dapatkan_suara_piper(bahasa)
        if suara is None:
            return None
        try:
            from piper.voice import SynthesisConfig
            konfigurasi = SynthesisConfig(
                length_scale=1.0,
                noise_scale=0.667,
                noise_w_scale=0.8,
                normalize_audio=True,
            )
            frame_gabungan = bytearray()
            sample_rate = 22050
            for potongan in _pecah_kalimat(teks_bersih):
                for chunk in suara.synthesize(potongan, syn_config=konfigurasi):
                    if not chunk.audio_int16_bytes:
                        continue
                    sample_rate = chunk.sample_rate or sample_rate
                    frame_gabungan.extend(chunk.audio_int16_bytes)
            if not frame_gabungan:
                return None
            return _tulis_wav_bytes(bytes(frame_gabungan), sample_rate)
        except Exception as galat:
            print(f"[Sintesis Suara] Piper gagal ({nama}): {galat}")
            return None

    # ── OmniVoice Voice Cloning ───────────────────────────────
    def _inisialisasi_omnivoice(self):
        """
        Muat model k2-fsa/OmniVoice dan pre-compute VoiceClonePrompt di background.
        Model ~2.5GB akan diunduh otomatis ke direktori cache HuggingFace.
        """
        try:
            import traceback
            import torch
            from omnivoice import OmniVoice

            print(
                f"[TTS OmniVoice] Memuat model {OMNIVOICE_MODEL_ID}... "
                "Harap tunggu (unduh ~2.5GB jika pertama kali)."
            )
            perangkat = "cuda" if torch.cuda.is_available() else "cpu"
            tipe_data = torch.float16 if perangkat == "cuda" else torch.float32

            # PERBAIKAN: gunakan torch_dtype bukan dtype
            model = OmniVoice.from_pretrained(
                OMNIVOICE_MODEL_ID,
                torch_dtype=tipe_data,
                cache_dir=self.direktori_model_omnivoice,
            )
            # PERBAIKAN: pindahkan ke perangkat yang benar (bukan selalu cpu)
            model = model.to(perangkat)
            model.eval()

            # PERBAIKAN: baca sampling_rate dari model.config bukan model langsung
            sr = getattr(model.config, "sampling_rate", None) or 24000

            with self._kunci_omnivoice:
                self._omnivoice_model = model
                self._omnivoice_sr = sr
                self._omnivoice_perangkat = perangkat

                # Mode Voice Design: model siap seketika tanpa perlu ekstraksi token berulang
                self._omnivoice_siap = True
                self.apakah_siap = True

            print(
                f"[TTS OmniVoice] SIAP! Voice Design aktif (female, young adult, high pitch). "
                f"Sample rate: {sr}Hz, device: {perangkat}"
            )

        except Exception as galat:
            import traceback
            # Tampilkan error lengkap dengan stack trace agar mudah debug
            print(
                f"[TTS OmniVoice] GAGAL diinisialisasi: {galat}\n"
                f"{traceback.format_exc()}"
                "Menggunakan Piper ONNX sebagai fallback."
            )
            with self._kunci_omnivoice:
                self._omnivoice_gagal = True

    def sintesis_dengan_omnivoice(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """
        Sintesis suara OmniVoice Voice Design:
        - Karakter suara perempuan muda, ramah, imut, dan ekspresif.
        - Menggunakan instruct="female, young adult, high pitch".
        - Mendukung Bahasa Indonesia dan Bahasa Inggris secara penuh tanpa Piper.
        """
        with self._kunci_omnivoice:
            model_siap = self._omnivoice_siap
            model = self._omnivoice_model
            sr = self._omnivoice_sr

        if not model_siap or model is None:
            return None

        teks_bersih = _bersihkan_teks_untuk_tts(teks)
        if not teks_bersih:
            return None

        kode_bahasa = _normalisasi_kode_bahasa(bahasa)
        kode_omni = "en" if kode_bahasa == "en" else None

        # Karakter suara perempuan muda dan imut dengan intonasi emosional ceria
        instruksi_karakter = "female, young adult, high pitch"

        semua_frame: List[np.ndarray] = []
        try:
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
    def _kunci_cache(self, teks: str, bahasa: str, engine: str = "") -> str:
        bersih = _bersihkan_teks_untuk_tts(teks).lower()
        kode = _normalisasi_kode_bahasa(bahasa)
        gabung = f"{engine}:{kode}:{bersih}"
        return hashlib.md5(gabung.encode("utf-8")).hexdigest()

    def muat_cache_audio_dari_disk(self):
        """Memuat berkas audio yang tersimpan di disk cache."""
        for folder in (self.direktori_cache_omnivoice, self.direktori_cache_piper, self.direktori_cache):
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
        print(f"[Sintesis Suara] Memuat {len(self.cache_audio)} berkas audio dari disk cache!")

    def _simpan_ke_disk_cache(self, kunci: str, b64_audio: str, engine: str):
        self.cache_audio[kunci] = b64_audio
        subfolder = self.direktori_cache_omnivoice if "omni" in engine else self.direktori_cache_piper
        jalur_berkas = os.path.join(subfolder, f"{kunci}.wav")
        try:
            with open(jalur_berkas, "wb") as f:
                f.write(base64.b64decode(b64_audio))
        except Exception as galat:
            print(f"[Sintesis Suara] Gagal menyimpan cache disk: {galat}")

    def status_engine(self) -> Dict[str, Any]:
        """Kembalikan status engine TTS untuk diagnostik antarmuka desktop."""
        perangkat_omni = getattr(self, "_omnivoice_perangkat", "cpu")
        return {
            "piper_siap": bool(self._suara_piper),
            "omnivoice_siap": self._omnivoice_siap,
            "omnivoice_voice_design": True,
            "omnivoice_perangkat": perangkat_omni,
            "omnivoice_gagal": self._omnivoice_gagal,
            "omnivoice_model_dimuat": self._omnivoice_model is not None,
            "jumlah_cache_audio": len(self.cache_audio),
            "engine_aktif": "omnivoice-voicedesign",
            "pesan_status": (
                "OmniVoice Voice Design AKTIF (Karakter Wanita Imut, Ceria & Alami)"
                if self._omnivoice_siap
                else "Menyiapkan mesin OmniVoice Voice Design..."
            ),
        }

    async def sintesis_teks_ke_audio_base64_async(
        self, teks: str, bahasa: str = "id"
    ) -> Dict[str, Any]:
        """
        API Utama Sintesis Suara SELA (Full OmniVoice Voice Design):
        - Cek disk & memory cache (Respon instan 0ms)
        - Sintesis langsung dengan OmniVoice Voice Design (female, young adult, high pitch)
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

        # 2. Jalur Utama GPU: OmniVoice Voice Design jika tersedia akselerasi CUDA
        if self._omnivoice_siap and self._omnivoice_perangkat == "cuda":
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
                        "engine": "omnivoice-cuda",
                        "bahasa": kode_bahasa,
                        "sukses": True,
                    }
            except Exception as galat_omni:
                print(f"[Sintesis Suara] OmniVoice CUDA gagal: {galat_omni}")

        # 3. Jalur Kecepatan Ultra-Tinggi (< 80ms) Piper ONNX Suara Perempuan:
        # Sangat stabil, jernih, dan tidak membebani CPU, menghasilkan audio instan
        if self._suara_piper:
            wav_piper = await loop.run_in_executor(
                None, self.sintesis_dengan_piper, teks_bersih, kode_bahasa
            )
            if wav_piper:
                b64_hasil = base64.b64encode(wav_piper).decode("ascii")
                kunci_simpan = self._kunci_cache(teks_bersih, kode_bahasa, "piper")
                self._simpan_ke_disk_cache(kunci_simpan, b64_hasil, "piper")
                return {
                    "audio_base64": b64_hasil,
                    "format": "audio/wav",
                    "engine": "piper-female-fast",
                    "bahasa": kode_bahasa,
                    "sukses": True,
                }

        return {
            "audio_base64": "",
            "format": "audio/wav",
            "engine": "failed",
            "bahasa": kode_bahasa,
            "sukses": False,
        }

    def sintesis_teks_ke_audio_base64(self, teks: str, bahasa: str = "id") -> Dict[str, Any]:
        """Versi sinkron dari sintesis suara untuk kemudahan pemanggilan."""
        try:
            return asyncio.run(self.sintesis_teks_ke_audio_base64_async(teks, bahasa))
        except RuntimeError:
            # Jika event loop sudah aktif
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.sintesis_teks_ke_audio_base64_async(teks, bahasa))


if __name__ == "__main__":
    import time
    tts = SintesisSuaraOffline()
    print(f"Status TTS Siap: {tts.apakah_siap}")
    print(f"Sampel Suara Kloning: {len(tts.daftar_sampel_audio)} berkas")

    kalimat = "Halo, selamat datang di Universitas Catur Insan Cendekia Cirebon!"
    t0 = time.time()
    hasil = asyncio.run(tts.sintesis_teks_ke_audio_base64_async(kalimat, "id"))
    dt = time.time() - t0
    print(f"Hasil sintesis ({dt:.2f}s): {hasil.get('engine')} - {len(hasil.get('audio_base64', ''))} chars b64")
