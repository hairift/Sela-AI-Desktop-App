"""
SELA AI Desktop - Mesin TTS Tunggal (Singleton) berbasis Supertonic 3
=====================================================================
Satu-satunya jalur sintesis suara di aplikasi. Model Supertonic 3 (ONNX,
~99 juta parameter, 31 bahasa termasuk Indonesia) dimuat SEKALI saat startup
lalu dipakai ulang untuk semua permintaan (pola singleton).

Menggantikan Piper sepenuhnya. Hanya ada SATU mesin suara di aplikasi agar
tidak pernah ada dua engine yang berebut / bertabrakan.

Model diambil oleh paket `supertonic` sendiri ke folder proyek
`ai-engine/models/supertonic-3/` (diatur lewat SUPERTONIC_CACHE_DIR), bukan ke
cache pengguna, supaya aplikasi tetap mandiri dan bisa dikemas offline.

TAG EKSPRESI (10 tag resmi Supertonic 3)
----------------------------------------
<angry> <sad> <laugh> <scream> <sigh> <surprise> <breath> <cough> <yawn>
<throatclear>

Catatan jujur soal Bahasa Indonesia (hasil riset komunitas):
- Tag paling konsisten pada bahasa Inggris, Jepang, dan Korea. Pada bahasa lain
  (termasuk Indonesia) model kadang MENGABAIKAN tag, dan kadang membacanya
  sebagai teks biasa.
- Tag <scream> dan <angry> dikenal paling tidak stabil.
- Trik yang dipakai komunitas: ULANG tag 2-3 kali di awal kalimat.

Karena itu perilaku bawaan (`SELA_TTS_EMOSI=auto`) hanya menyalakan tag untuk
bahasa yang stabil, agar SELA tidak pernah mengucapkan kata "angry angry angry".
Nilai yang didukung:
    auto  -> tag hanya untuk en / ja / ko  (bawaan, paling aman)
    on    -> tag selalu dipasang (termasuk Indonesia, memakai trik ulang 3x)
    off   -> tag tidak pernah dipasang
Ganti suara dengan `SELA_TTS_SUARA` (F1..F5, M1..M5; bawaan F1).

Sesuai aturan proyek: TIDAK ADA berkas sementara di disk. Seluruh audio
dirangkai di memori memakai io.BytesIO + modul `wave`.

Pemakaian:
    from core import dapatkan_tts
    tts = dapatkan_tts()
    wav_bytes = tts.sintesis_wav_bytes("Halo, saya SELA.", bahasa="id")
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

# Nama model Supertonic yang dipakai.
NAMA_MODEL_TTS = "supertonic-3"
# Suara bawaan (F = perempuan, M = laki-laki; angka 1-5 = varian).
SUARA_BAWAAN = "F1"

# Tag ekspresi resmi Supertonic 3.
TAG_RESMI = (
    "angry",
    "sad",
    "laugh",
    "scream",
    "sigh",
    "surprise",
    "breath",
    "cough",
    "yawn",
    "throatclear",
)
_HIMPUNAN_TAG = set(TAG_RESMI)

# Padanan nama emosi (Indonesia / Inggris bebas) -> tag resmi.
_ALIAS_EMOSI = {
    "marah": "angry",
    "kesal": "angry",
    "agresif": "angry",
    "sedih": "sad",
    "duka": "sad",
    "ketawa": "laugh",
    "tertawa": "laugh",
    "tawa": "laugh",
    "teriak": "scream",
    "menjerit": "scream",
    "menghela": "sigh",
    "hela": "sigh",
    "napas": "sigh",
    "kaget": "surprise",
    "terkejut": "surprise",
    "heran": "surprise",
    "nafas": "breath",
    "tarik_napas": "breath",
    "batuk": "cough",
    "menguap": "yawn",
    "kantu": "throatclear",
    "berdeham": "throatclear",
}

# Bahasa yang tag ekspresinya benar-benar stabil (hasil riset komunitas).
_BAHASA_TAG_STABIL = {"en", "ja", "ko"}

# Berapa kali tag diulang. 3 adalah angka yang dipakai komunitas untuk
# menaikkan peluang tag benar-benar dipatuhi model.
_ULANG_TAG = 3

# Batas panjang teks per panggilan sintesis (Supertonic memotong sendiri per
# 300 karakter, jadi ini hanya jaring pengaman agar tidak ada teks raksasa).
_MAKS_KARAKTER_KALIMAT = 900


def normalisasi_bahasa(bahasa: Optional[str]) -> str:
    """
    Petakan kode bahasa apa pun menjadi kode Supertonic 3 yang sah.

    Bahasa yang tidak didukung (mis. Jawa) dialihkan ke 'id' karena fonetiknya
    serumpun, sehingga model tetap bersuara wajar.
    """
    kode = (bahasa or "id").strip().lower().replace("_", "-").split("-")[0]
    if not kode or kode in ("auto", "na", "unknown"):
        return "id"
    if kode in ("jv", "jw", "jawa", "su", "sunda"):
        return "id"
    try:
        from supertonic import SUPPORTED_LANGUAGES
    except Exception:
        SUPPORTED_LANGUAGES = ("en", "id", "ja", "ko")  # pragma: no cover
    return kode if kode in SUPPORTED_LANGUAGES else "id"


def mode_emosi() -> str:
    """Baca saklar tag emosi dari lingkungan: auto | on | off."""
    nilai = (os.environ.get("SELA_TTS_EMOSI") or "auto").strip().lower()
    return nilai if nilai in ("auto", "on", "off") else "auto"


# ── Setelan kecepatan sintesis ───────────────────────────────────────────────
# Angka bawaan dipilih dari pengukuran nyata, bukan tebakan (lihat
# CLEANUP_REPORT.md §27). `total_steps` = jumlah langkah difusi model: semakin
# sedikit langkah semakin cepat, TETAPI amplitudo puncak ikut naik dan bisa
# melewati skala penuh sehingga audio terpotong (distorsi).
# Hasil ukur 4 kalimat Indonesia, rata-rata:
#   steps=8 -> 1.223 ms, puncak 0,41   (bawaan lama)
#   steps=6 ->   923 ms, puncak 0,49   (bawaan sekarang, 25% lebih cepat)
#   steps=5 ->   785 ms, puncak 0,56   (aman, 36% lebih cepat)
#   steps=4 ->   665 ms, puncak 0,89   DAN pernah 1,26 di kalimat lain -> TIDAK AMAN
# Jadi bawaan 6 (aman, jelas lebih cepat); 5 sudah terukur aman dan bisa dipilih
# lewat SELA_TTS_STEPS bila kecepatan lebih penting daripada kehalusan suara.
STEPS_BAWAAN = 6
KECEPATAN_BAWAAN = 1.15
JEDA_BAWAAN = 0.15


def _angka_lingkungan(nama: str, bawaan: float) -> float:
    """Baca angka dari variabel lingkungan; kembalikan bawaan bila tidak sah."""
    mentah = (os.environ.get(nama) or "").strip()
    if not mentah:
        return bawaan
    try:
        return float(mentah)
    except ValueError:
        return bawaan


def jumlah_langkah() -> int:
    """Jumlah langkah difusi dari SELA_TTS_STEPS (4-16, bawaan 6)."""
    nilai = int(_angka_lingkungan("SELA_TTS_STEPS", STEPS_BAWAAN))
    return nilai if 4 <= nilai <= 16 else STEPS_BAWAAN


def kecepatan_bicara() -> float:
    """Pengali kecepatan bicara dari SELA_TTS_SPEED (0,5-2,0, bawaan 1,15)."""
    nilai = _angka_lingkungan("SELA_TTS_SPEED", KECEPATAN_BAWAAN)
    return nilai if 0.5 <= nilai <= 2.0 else KECEPATAN_BAWAAN


def jeda_antar_potongan() -> float:
    """
    Jeda antar potongan teks (detik) dari SELA_TTS_JEDA (0-1, bawaan 0,15).

    Supertonic menyisipkan jeda ini di antara potongan panjang (teks > 300
    karakter). Bawaan paketnya 0,3 detik -- terlalu panjang untuk percakapan
    karena terasa menggantung di tengah jawaban.
    """
    nilai = _angka_lingkungan("SELA_TTS_JEDA", JEDA_BAWAAN)
    return nilai if 0.0 <= nilai <= 1.0 else JEDA_BAWAAN


def normalisasi_emosi(emosi: Optional[str]) -> Optional[str]:
    """Ubah nama emosi bebas menjadi salah satu dari 10 tag resmi (atau None)."""
    if not emosi:
        return None
    kunci = re.sub(r"[^a-z]+", "_", emosi.strip().lower()).strip("_")
    if kunci in _HIMPUNAN_TAG:
        return kunci
    return _ALIAS_EMOSI.get(kunci)


def apakah_tag_dipakai(bahasa: str) -> bool:
    """True bila tag emosi boleh dipasang untuk bahasa ini."""
    mode = mode_emosi()
    if mode == "off":
        return False
    if mode == "on":
        return True
    return bahasa in _BAHASA_TAG_STABIL


def bersihkan_tag_emosi(teks: str) -> str:
    """
    Buang SEMUA tag ekspresi dari teks.

    Dipakai untuk memastikan tag tidak pernah muncul di balon obrolan maupun
    diucapkan sebagai kata biasa ketika model mengabaikannya.
    """
    if not teks:
        return teks
    pola = r"<\s*(?:" + "|".join(TAG_RESMI) + r")\s*>"
    return re.sub(pola, " ", teks, flags=re.IGNORECASE)


def pasang_tag_emosi(teks: str, emosi: Optional[str]) -> str:
    """
    Pasang tag ekspresi di awal teks, diulang beberapa kali (trik komunitas).

    Pengulangan menaikkan peluang model mematuhi tag, terutama pada bahasa di
    luar en/ja/ko. Tag yang tidak dikenal diabaikan (teks dikembalikan apa
    adanya) sehingga tidak pernah ada tag sampah yang ikut diucapkan.
    """
    tag = normalisasi_emosi(emosi)
    if not tag or not teks.strip():
        return teks
    return (f"<{tag}> " * _ULANG_TAG) + teks.strip()


def bersihkan_teks_tts(teks: str) -> str:
    """Buang markdown, tautan, emoji, dan tag ekspresi agar diucapkan natural."""
    if not teks:
        return ""
    bersih = teks.strip()
    bersih = bersihkan_tag_emosi(bersih)
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
    """
    Pecah teks panjang menjadi potongan aman untuk sekali sintesis.

    Hanya dipakai sebagai jaring pengaman; Supertonic sudah memotong sendiri
    per 300 karakter. Kalimat TIDAK dipecah pada titik yang diapit angka,
    supaya "Rp170.000" tidak berubah menjadi "Rp170. 000".
    """
    if not teks:
        return []
    if len(teks) <= batas:
        return [teks]
    bagian = [k for k in re.split(r"(?<=[.!?])\s+", teks) if k.strip()]
    hasil: List[str] = []
    penampung = ""
    for kalimat in bagian:
        kandidat = (penampung + " " + kalimat).strip()
        if len(kandidat) <= batas:
            penampung = kandidat
            continue
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
    """Pembungkus tunggal Supertonic 3 untuk sintesis suara SELA."""

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
                os.path.join(self.direktori_induk, "..", "models", "supertonic-3")
            )
        self.direktori_model = direktori_model
        # Arahkan unduhan paket supertonic ke folder proyek (bukan cache pengguna).
        os.environ.setdefault("SUPERTONIC_CACHE_DIR", self.direktori_model)

        self._tts: Any = None
        self._gaya: Dict[str, Any] = {}
        self._kunci_sintesis = threading.Lock()
        self.apakah_siap = False
        self.pesan_status = "belum dimuat"
        self.nama_suara = (os.environ.get("SELA_TTS_SUARA") or SUARA_BAWAAN).strip().upper()
        self.sample_rate = 44100
        self.nama_model_aktif: Dict[str, str] = {}

        self._muat()

    # ── Pemuatan model ────────────────────────────────────────────────────────
    def _muat(self) -> None:
        try:
            from supertonic import TTS
        except Exception as galat:  # pragma: no cover
            self.apakah_siap = False
            self.pesan_status = f"paket supertonic belum terpasang: {galat}"
            print("[TTS] Paket `supertonic` belum terpasang. Jalankan: pip install supertonic")
            return

        # Unduh otomatis hanya bila diminta. Saat aplikasi sudah dikemas offline,
        # set SELA_TTS_UNDUH=0 agar tidak ada percobaan jaringan saat startup.
        unduh_otomatis = (os.environ.get("SELA_TTS_UNDUH") or "1").strip() != "0"
        try:
            os.makedirs(self.direktori_model, exist_ok=True)
        except OSError:
            pass

        try:
            self._tts = TTS(
                model=NAMA_MODEL_TTS,
                model_dir=self.direktori_model,
                auto_download=unduh_otomatis,
            )
        except Exception as galat:
            self.apakah_siap = False
            self.pesan_status = f"model {NAMA_MODEL_TTS} tidak bisa dimuat: {galat}"
            print(f"[TTS] Gagal memuat Supertonic 3: {galat}")
            return

        self.sample_rate = int(getattr(self._tts, "sample_rate", 44100) or 44100)
        # Panaskan suara bawaan supaya permintaan pertama tidak terasa lambat.
        if self._ambil_gaya(self.nama_suara) is None:
            self.apakah_siap = False
            self.pesan_status = f"gaya suara '{self.nama_suara}' tidak tersedia"
            print(f"[TTS] Gaya suara '{self.nama_suara}' tidak ditemukan di model.")
            return

        self.apakah_siap = True
        self.pesan_status = (
            f"Supertonic 3 siap (suara {self.nama_suara}, {self.sample_rate} Hz, "
            f"tag emosi={mode_emosi()})"
        )
        print(f"[TTS] Supertonic 3 siap: suara {self.nama_suara}, {self.sample_rate} Hz.")

    def _ambil_gaya(self, nama_suara: str) -> Any:
        """Ambil (dan cache) objek gaya suara dari model."""
        if self._tts is None:
            return None
        nama = (nama_suara or SUARA_BAWAAN).strip().upper()
        if nama in self._gaya:
            return self._gaya[nama]
        try:
            gaya = self._tts.get_voice_style(voice_name=nama)
        except Exception as galat:
            print(f"[TTS] Gaya suara '{nama}' gagal diambil: {galat}")
            return None
        self._gaya[nama] = gaya
        self.nama_model_aktif["default"] = f"{NAMA_MODEL_TTS}/{nama}"
        return gaya

    # ── Sintesis (in-memory, tanpa berkas tmp) ────────────────────────────────
    def _ke_wav_bytes(self, gelombang: Any) -> Optional[bytes]:
        """Ubah gelombang float32 Supertonic menjadi byte WAV 16-bit di memori."""
        try:
            import numpy as np
        except Exception:  # pragma: no cover
            return None
        data = np.asarray(gelombang, dtype="float32").reshape(-1)
        if data.size == 0:
            return None
        # Model dengan langkah difusi sedikit dapat menghasilkan amplitudo puncak
        # DI ATAS skala penuh (terukur 1,26 pada steps=4). Memotongnya keras akan
        # menimbulkan distorsi; mengecilkan seluruh gelombang secara proporsional
        # jauh lebih halus dan hanya sedikit menurunkan volume.
        puncak = float(np.max(np.abs(data)))
        if puncak > 1.0:
            data = data / puncak
        data = np.clip(data, -1.0, 1.0)
        pcm = (data * 32767.0).astype("<i2").tobytes()
        buffer = io.BytesIO()
        try:
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(pcm)
            return buffer.getvalue() or None
        finally:
            buffer.close()

    def sintesis_wav_bytes(
        self, teks: str, bahasa: str = "id", emosi: Optional[str] = None
    ) -> Optional[bytes]:
        """Sintesis satu potongan teks menjadi byte WAV di memori."""
        teks_bersih = bersihkan_teks_tts(teks)
        if not teks_bersih:
            return None
        if not (self.apakah_siap and self._tts is not None):
            return None
        kode = normalisasi_bahasa(bahasa)
        gaya = self._ambil_gaya(self.nama_suara)
        if gaya is None:
            return None
        if apakah_tag_dipakai(kode):
            teks_bersih = pasang_tag_emosi(teks_bersih, emosi)

        potongan: List[bytes] = []
        for bagian in pecah_kalimat(teks_bersih):
            try:
                with self._kunci_sintesis:
                    gelombang, _ = self._tts.synthesize(
                        bagian,
                        voice_style=gaya,
                        total_steps=jumlah_langkah(),
                        speed=kecepatan_bicara(),
                        silence_duration=jeda_antar_potongan(),
                        lang=kode,
                    )
            except Exception as galat:
                print(f"[TTS] Sintesis gagal: {galat}")
                return None
            data = self._ke_wav_bytes(gelombang)
            if not data:
                return None
            potongan.append(data)
        if not potongan:
            return None
        if len(potongan) == 1:
            return potongan[0]
        return self._gabung_wav(potongan)

    def _gabung_wav(self, daftar_wav: List[bytes]) -> Optional[bytes]:
        """Gabungkan beberapa WAV (format identik) menjadi satu WAV di memori."""
        try:
            bingkai: List[bytes] = []
            for data in daftar_wav:
                with wave.open(io.BytesIO(data), "rb") as wav:
                    bingkai.append(wav.readframes(wav.getnframes()))
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as keluar:
                keluar.setnchannels(1)
                keluar.setsampwidth(2)
                keluar.setframerate(self.sample_rate)
                keluar.writeframes(b"".join(bingkai))
            return buffer.getvalue() or None
        except Exception as galat:
            print(f"[TTS] Gagal menggabungkan potongan audio: {galat}")
            return None

    async def sintesis_base64_async(
        self, teks: str, bahasa: str = "id", emosi: Optional[str] = None
    ) -> Dict[str, Any]:
        """API asinkron utama: hasilkan audio WAV base64 untuk frontend."""
        kode = normalisasi_bahasa(bahasa)
        if not self.apakah_siap:
            return {
                "audio_base64": "",
                "format": "audio/wav",
                "engine": "supertonic-unavailable",
                "bahasa": kode,
                "sukses": False,
            }

        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(
            None, self.sintesis_wav_bytes, teks, kode, emosi
        )
        if not wav_bytes:
            return {
                "audio_base64": "",
                "format": "audio/wav",
                "engine": "supertonic-empty",
                "bahasa": kode,
                "sukses": False,
            }
        return {
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "format": "audio/wav",
            "engine": "supertonic-3",
            "bahasa": kode,
            "sukses": True,
        }

    def sintesis_base64(
        self, teks: str, bahasa: str = "id", emosi: Optional[str] = None
    ) -> Dict[str, Any]:
        """Versi sinkron dari sintesis_base64_async."""
        try:
            return asyncio.run(self.sintesis_base64_async(teks, bahasa, emosi))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.sintesis_base64_async(teks, bahasa, emosi))

    def status_engine(self) -> Dict[str, Any]:
        """Status engine untuk endpoint /api/status-tts."""
        return {
            "tts_siap": self.apakah_siap,
            "engine_aktif": "supertonic-3" if self.apakah_siap else "supertonic-unavailable",
            "model_aktif": f"{NAMA_MODEL_TTS}/{self.nama_suara}",
            "suara": self.nama_suara,
            "sample_rate": self.sample_rate,
            "mode_emosi": mode_emosi(),
            "tag_tersedia": list(TAG_RESMI),
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
