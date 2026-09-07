"""
SELA AI Desktop - Sintesis Suara Offline Natural (Perempuan)
=============================================================
Arsitektur baru pengganti Voice Cloning + F5-TTS + sampel audio
(yang bersuara aneh/robotik) dengan dua jalur offline yang manusiawi:

1. Jalur Utama INSTAN - Piper ONNX (CPU, <300ms, natural, female):
   - Indonesia (termasuk teks Jawa, dilafalkan dengan suara Indonesia):
     `id_ID-news_tts-medium`  (perempuan)
   - Inggris: `en_US-amy-medium`  (perempuan)
   - 100% offline setelah model ONNX diunduh sekali ke models/tts_piper/.

2. Jalur KUALITAS - Higgs TTS v2 3B (Boson AI) via `transformers`:
   - Model: `bosonai/higgs-audio-v2-generation-3B-base`
   - Smart voice feminin (tanpa file referensi / tanpa voice cloning).
   - Dijalankan di background untuk meng-upgrade cache; tidak pernah
     memblokir respons utama karena inferensi LLM-audio berat.

3. Cadangan DARURAT - SAPI5/pyttsx3 suara perempuan (Windows bawaan).

API publik tetap sama seperti sebelumnya sehingga server.py dan
frontend tidak perlu diubah:
    SintesisSuaraOffline().sintesis_teks_ke_audio_base64_async(teks, bahasa)
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


# ── Konfigurasi suara ──────────────────────────────────────────
SUARA_PIPER_PER_BAHASA = {
    # Indonesia + Jawa (Jawa dilafalkan memakai suara Indonesia karena
    # belum ada model ONNX native Jawa yang berkualitas).
    "id": "id_ID-news_tts-medium",
    "jv": "id_ID-news_tts-medium",
    "jw": "id_ID-news_tts-medium",
    "jawa": "id_ID-news_tts-medium",
    # Inggris (perempuan).
    "en": "en_US-amy-medium",
}

HIGGS_MODEL_ID = "bosonai/higgs-audio-v2-generation-3B-base"

# Scene feminin untuk Higgs (smart voice, tanpa audio referensi).
_HIGGS_SCENE_FEMININ = (
    "Audio is recorded from a quiet room. "
    "SPEAKER0: feminine, young adult female voice, warm and friendly "
    "customer-service tone, clear Indonesian and English pronunciation."
)


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
    # URL -> kata "tautan" supaya tidak dieja "h t t p s ..."
    bersih = re.sub(r"https?://\S+", "tautan", bersih)
    # Markdown bold/heading/quote
    bersih = re.sub(r"\*\*(.+?)\*\*", r"\1", bersih)
    bersih = re.sub(r"^#{1,3}\s+", "", bersih, flags=re.MULTILINE)
    bersih = re.sub(r"^>\s?", "", bersih, flags=re.MULTILINE)
    # Follow-up "[...]" tidak perlu diucapkan
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
            else:  # kalimat tunggal sangat panjang -> potong keras
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
    Mesin TTS offline natural bersuara perempuan (ID/Jawa/EN).

    Prioritas respons:
      1. Cache in-memory (0 ms)
      2. Cache disk (0-2 ms)
      3. Piper ONNX feminin (< 300 ms, respons utama)
      4. Higgs TTS v2 feminin (background upgrade cache)
      5. SAPI5 perempuan (darurat bila 3 & 4 tak tersedia)
    """

    def __init__(self, direktori_sampel_suara: Optional[str] = None):
        # `direktori_sampel_suara` dipertahankan demi kompatibilitas
        # pemanggil lama; sistem voice cloning sudah DIHAPUS total.
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))

        self.direktori_model_piper = os.path.join(self.direktori_induk, "models", "tts_piper")
        self.direktori_model_higgs = os.path.join(self.direktori_induk, "models", "higgs")
        os.makedirs(self.direktori_model_piper, exist_ok=True)
        os.makedirs(self.direktori_model_higgs, exist_ok=True)

        self.direktori_cache = os.path.join(self.direktori_induk, "cache_audio")
        self.direktori_cache_higgs = os.path.join(self.direktori_cache, "higgs")
        os.makedirs(self.direktori_cache, exist_ok=True)
        os.makedirs(self.direktori_cache_higgs, exist_ok=True)

        # Kompatibilitas /kesehatan lama (voice cloning dihapus -> list kosong).
        self.daftar_sampel_audio: List[str] = []
        self.sampel_indonesia: List[str] = []
        self.sampel_inggris: List[str] = []

        self.cache_audio: Dict[str, str] = {}
        self.cache_higgs: Dict[str, str] = {}
        self.apakah_siap = False

        self._suara_piper: Dict[str, Any] = {}
        self._kunci_piper = threading.Lock()
        self._higgs_processor = None
        self._higgs_model = None
        self._higgs_gagal = False
        self._kunci_higgs = threading.Lock()
        self._sedang_generate_higgs: set = set()

        self._siapkan_piper()
        self.muat_cache_audio_dari_disk()
        # Higgs berat (LLM-audio 6B) -> inisialisasi di background,
        # tidak pernah memblokir startup server.
        threading.Thread(target=self._inisialisasi_higgs, daemon=True).start()

    # ── Piper ONNX ────────────────────────────────────────────
    def _jalur_model_piper(self, nama_suara: str) -> str:
        return os.path.join(self.direktori_model_piper, nama_suara + ".onnx")

    def _unduh_suara_piper_jika_perlu(self, nama_suara: str) -> bool:
        jalur = self._jalur_model_piper(nama_suara)
        if os.path.exists(jalur) and os.path.getsize(jalur) > 1000:
            return True
        try:
            from piper.download_voices import download_voice
            print(f"[Sintesis Suara] Mengunduh suara Piper '{nama_suara}' (sekali saja, lalu offline)...")
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
            # Coba muat ulang (mis. unduhan baru selesai di thread lain).
            self._siapkan_piper()
            with self._kunci_piper:
                suara = self._suara_piper.get(nama)
        return suara, nama

    def sintesis_dengan_piper(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """Jalur utama: Piper ONNX feminin, cepat & natural."""
        teks_bersih = _bersihkan_teks_untuk_tts(teks)
        if not teks_bersih:
            return None
        suara, nama = self._dapatkan_suara_piper(bahasa)
        if suara is None:
            return None
        try:
            from piper.voice import SynthesisConfig
            konfigurasi = SynthesisConfig(
                length_scale=1.0,   # kecepatan natural
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

    # ── Higgs TTS v2 (background quality) ─────────────────────
    def _inisialisasi_higgs(self):
        """Muat Higgs TTS v2 di background; gagal -> tetap jalan via Piper."""
        try:
            import torch
            from transformers import AutoProcessor, HiggsAudioV2ForConditionalGeneration
            print("[Sintesis Suara] Mengaktifkan Higgs TTS v2 (feminine smart voice) di background...")
            perangkat = "cuda" if torch.cuda.is_available() else "cpu"
            with self._kunci_higgs:
                self._higgs_processor = AutoProcessor.from_pretrained(
                    HIGGS_MODEL_ID, cache_dir=self.direktori_model_higgs, trust_remote_code=False
                )
                self._higgs_model = HiggsAudioV2ForConditionalGeneration.from_pretrained(
                    HIGGS_MODEL_ID, cache_dir=self.direktori_model_higgs,
                    device_map="auto" if perangkat == "cuda" else None,
                    torch_dtype="auto",
                )
                if perangkat == "cpu":
                    self._higgs_model = self._higgs_model.to("cpu")
                self._higgs_model.eval()
            print("[Sintesis Suara] Higgs TTS v2 siap (feminine, background quality).")
        except Exception as galat:
            print(f"[Sintesis Suara] Higgs TTS v2 tidak tersedia (tetap memakai Piper): {galat}")
            with self._kunci_higgs:
                self._higgs_gagal = True
                self._higgs_model = None

    def sintesis_dengan_higgs(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """Jalur kualitas: Higgs feminine smart voice (lambat, untuk cache)."""
        with self._kunci_higgs:
            if self._higgs_gagal or self._higgs_model is None or self._higgs_processor is None:
                return None
            processor = self._higgs_processor
            model = self._higgs_model
        teks_bersih = _bersihkan_teks_untuk_tts(teks)
        if not teks_bersih:
            return None
        try:
            import torch
            kode = _normalisasi_kode_bahasa(bahasa)
            label_bahasa = {"id": "Indonesian", "jv": "Javanese", "en": "English"}.get(kode, "Indonesian")
            percakapan = [
                {"role": "system",
                 "content": [{"type": "text", "text": "Generate audio following instruction."}]},
                {"role": "scene",
                 "content": [{"type": "text",
                              "text": f"{_HIGGS_SCENE_FEMININ} Language: {label_bahasa}."}]},
                {"role": "user",
                 "content": [{"type": "text", "text": teks_bersih[:400]}]},
            ]
            masukan = processor.apply_chat_template(
                percakapan, add_generation_prompt=True, tokenize=True,
                return_dict=True, return_tensors="pt", sampling_rate=24000,
            )
            perangkat_model = next(model.parameters()).device
            masukan = {k: (v.to(perangkat_model) if hasattr(v, "to") else v)
                       for k, v in masukan.items()}
            with torch.no_grad():
                keluaran = model.generate(**masukan, max_new_tokens=1024, do_sample=False)
            hasil_decode = processor.batch_decode(keluaran)
            # batch_decode mengembalikan audio (numpy) untuk HiggsAudioV2.
            audio = hasil_decode[0] if isinstance(hasil_decode, list) else hasil_decode
            import numpy as np
            if isinstance(audio, tuple):
                audio = audio[0]
            data = np.asarray(audio, dtype=np.float32).flatten()
            if data.size == 0:
                return None
            data = np.clip(data, -1.0, 1.0)
            pcm16 = (data * 32767).astype(np.int16).tobytes()
            return _tulis_wav_bytes(pcm16, 24000)
        except Exception as galat:
            print(f"[Sintesis Suara] Higgs gagal: {galat}")
            return None

    def _generate_higgs_background(self, teks_bersih: str, bahasa: str, kunci_hash: str):
        with self._kunci_higgs:
            if kunci_hash in self._sedang_generate_higgs:
                return
            self._sedang_generate_higgs.add(kunci_hash)
        try:
            audio_bytes = self.sintesis_dengan_higgs(teks_bersih, bahasa)
            if audio_bytes:
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                self.cache_higgs[kunci_hash] = b64_audio
                try:
                    with open(os.path.join(self.direktori_cache_higgs, f"{kunci_hash}.b64"),
                              "w", encoding="utf-8") as f:
                        f.write(b64_audio)
                except Exception:
                    pass
        except Exception as galat:
            print(f"[Sintesis Suara] [Higgs-BG] gagal: {galat}")
        finally:
            with self._kunci_higgs:
                self._sedang_generate_higgs.discard(kunci_hash)

    def _picu_higgs_background(self, teks_bersih: str, bahasa: str, kunci_hash: str):
        with self._kunci_higgs:
            model_siap = self._higgs_model is not None and not self._higgs_gagal
            sedang = kunci_hash in self._sedang_generate_higgs
        if model_siap and not sedang:
            threading.Thread(target=self._generate_higgs_background,
                             args=(teks_bersih, bahasa, kunci_hash), daemon=True).start()

    # ── Cadangan darurat SAPI5 perempuan ──────────────────────
    def sintesis_darurat_sapi5(self, teks: str, bahasa: str = "id") -> Optional[bytes]:
        """Fallback terakhir memakai suara Windows bila Piper+Higgs mati."""
        try:
            import pyttsx3
            import tempfile
            teks_bersih = _bersihkan_teks_untuk_tts(teks)
            if not teks_bersih:
                return None
            mesin = pyttsx3.init()
            mesin.setProperty("rate", 175)
            mesin.setProperty("volume", 0.95)
            kode = _normalisasi_kode_bahasa(bahasa)
            try:
                for suara in mesin.getProperty("voices"):
                    nama = suara.name.lower()
                    if kode == "en":
                        if any(k in nama for k in ["jenny", "zira", "eva", "female", "woman"]):
                            mesin.setProperty("voice", suara.id)
                            break
                    else:
                        if any(k in nama for k in ["female", "zira", "eva", "maria", "anna", "jenny"]):
                            mesin.setProperty("voice", suara.id)
                            break
            except Exception:
                pass
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                jalur_tmp = tmp.name
            try:
                mesin.save_to_file(teks_bersih[:400], jalur_tmp)
                mesin.runAndWait()
                if os.path.exists(jalur_tmp) and os.path.getsize(jalur_tmp) > 100:
                    with open(jalur_tmp, "rb") as f:
                        return f.read()
            finally:
                try:
                    if os.path.exists(jalur_tmp):
                        os.remove(jalur_tmp)
                except Exception:
                    pass
        except Exception as galat:
            print(f"[Sintesis Suara] SAPI5 darurat gagal: {galat}")
        return None

    # ── Cache ─────────────────────────────────────────────────
    def muat_cache_audio_dari_disk(self):
        total = 0
        try:
            for nama_berkas in os.listdir(self.direktori_cache):
                if nama_berkas.endswith(".b64"):
                    try:
                        with open(os.path.join(self.direktori_cache, nama_berkas),
                                  "r", encoding="utf-8") as f:
                            isi = f.read().strip()
                        if isi:
                            self.cache_audio[nama_berkas[:-4]] = isi
                            total += 1
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            for nama_berkas in os.listdir(self.direktori_cache_higgs):
                if nama_berkas.endswith(".b64"):
                    try:
                        with open(os.path.join(self.direktori_cache_higgs, nama_berkas),
                                  "r", encoding="utf-8") as f:
                            isi = f.read().strip()
                        if isi:
                            self.cache_higgs[nama_berkas[:-4]] = isi
                            total += 1
                    except Exception:
                        pass
        except Exception:
            pass
        if total > 0:
            print(f"[Sintesis Suara] Memuat {total} berkas audio dari disk cache!")

    # ── API utama ─────────────────────────────────────────────
    async def sintesis_teks_ke_audio_base64_async(
        self, teks_kalimat: str, bahasa: str = "id"
    ) -> Dict[str, Any]:
        """
        Prioritas: cache Higgs (0ms) -> cache Piper (0ms) -> Piper feminin
        (respons utama) + Higgs background -> SAPI5 darurat.
        """
        teks_bersih = _bersihkan_teks_untuk_tts(teks_kalimat)
        if not teks_bersih:
            return {"sukses": False, "pesan": "Teks kosong", "audio_base64": None}

        kode = _normalisasi_kode_bahasa(bahasa)
        kunci_cache = f"{kode}:{teks_bersih}"
        kunci_hash = hashlib.md5(kunci_cache.encode("utf-8")).hexdigest()

        if kunci_hash in self.cache_higgs:
            return {"sukses": True, "audio_base64": self.cache_higgs[kunci_hash],
                    "format": "audio/wav", "engine": "higgs-tts2-feminine",
                    "teks": teks_bersih, "bahasa": kode}
        jalur_higgs = os.path.join(self.direktori_cache_higgs, f"{kunci_hash}.b64")
        if os.path.exists(jalur_higgs):
            try:
                with open(jalur_higgs, "r", encoding="utf-8") as f:
                    data_b64 = f.read().strip()
                if data_b64:
                    self.cache_higgs[kunci_hash] = data_b64
                    return {"sukses": True, "audio_base64": data_b64,
                            "format": "audio/wav", "engine": "higgs-tts2-feminine",
                            "teks": teks_bersih, "bahasa": kode}
            except Exception:
                pass

        if kunci_hash in self.cache_audio:
            self._picu_higgs_background(teks_bersih, kode, kunci_hash)
            return {"sukses": True, "audio_base64": self.cache_audio[kunci_hash],
                    "format": "audio/wav", "engine": "piper-female-natural",
                    "teks": teks_bersih, "bahasa": kode}
        jalur_disk = os.path.join(self.direktori_cache, f"{kunci_hash}.b64")
        if os.path.exists(jalur_disk):
            try:
                with open(jalur_disk, "r", encoding="utf-8") as f:
                    data_b64 = f.read().strip()
                if data_b64:
                    self.cache_audio[kunci_hash] = data_b64
                    self._picu_higgs_background(teks_bersih, kode, kunci_hash)
                    return {"sukses": True, "audio_base64": data_b64,
                            "format": "audio/wav", "engine": "piper-female-natural",
                            "teks": teks_bersih, "bahasa": kode}
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        audio_bytes = await loop.run_in_executor(
            None, self.sintesis_dengan_piper, teks_bersih, kode
        )
        engine = "piper-female-natural"
        if not audio_bytes:
            # Higgs sinkron sebagai upaya kedua (jarang dipakai realtime).
            audio_bytes = await loop.run_in_executor(
                None, self.sintesis_dengan_higgs, teks_bersih, kode
            )
            engine = "higgs-tts2-feminine"
        if not audio_bytes:
            audio_bytes = await loop.run_in_executor(
                None, self.sintesis_darurat_sapi5, teks_bersih, kode
            )
            engine = "sapi5-female-fallback"

        if audio_bytes:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            self.cache_audio[kunci_hash] = b64_audio
            try:
                with open(jalur_disk, "w", encoding="utf-8") as f:
                    f.write(b64_audio)
            except Exception:
                pass
            self._picu_higgs_background(teks_bersih, kode, kunci_hash)
            self.apakah_siap = True
            return {"sukses": True, "audio_base64": b64_audio,
                    "format": "audio/wav", "engine": engine,
                    "teks": teks_bersih, "bahasa": kode}

        return {"sukses": False,
                "pesan": "Tidak dapat menyintesis audio offline.",
                "audio_base64": None, "teks": teks_bersih}

    def sintesis_teks_ke_audio_base64(
        self, teks_kalimat: str, bahasa: str = "id"
    ) -> Dict[str, Any]:
        """Wrapper synchronous untuk pengujian atau thread biasa."""
        try:
            return asyncio.run(self.sintesis_teks_ke_audio_base64_async(teks_kalimat, bahasa))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(
                self.sintesis_teks_ke_audio_base64_async(teks_kalimat, bahasa))


if __name__ == "__main__":
    tts = SintesisSuaraOffline()
    import time
    time.sleep(1)
    hasil = tts.sintesis_teks_ke_audio_base64(
        "Halo, selamat datang di Universitas CIC. Saya adalah asisten virtual SELA yang siap membantu Anda!"
    )
    print("Hasil Uji TTS:")
    print(f"  -> Sukses: {hasil.get('sukses')}")
    print(f"  -> Engine: {hasil.get('engine')}")
    print(f"  -> Format: {hasil.get('format')}")
    print(f"  -> Ukuran Base64: {len(hasil.get('audio_base64') or '')} karakter")
