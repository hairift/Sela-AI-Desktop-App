"""
SELA AI Desktop - Mesin LLM Tunggal (Singleton)
================================================
Satu-satunya jalur inferensi bahasa di seluruh aplikasi. Tidak ada Ollama,
tidak ada LM Studio. Satu model GGUF, satu mesin, satu pola singleton.

Dua backend di balik SATU antarmuka (dipilih otomatis saat start):

1. llama-cpp-python (utama, sesuai target arsitektur)
   `Llama(model_path=..., n_gpu_layers=-1, ...)` dimuat langsung ke proses
   Python. Sebelum dipakai, kemampuan pustaka ini diuji di SUBPROSES terpisah
   agar bila roda biner llama.cpp tidak cocok dengan CPU mesin ini (gejala:
   STATUS_ILLEGAL_INSTRUCTION / 0xc000001d), proses server utama tidak ikut
   mati. Hasil uji di-cache selama sesi.

2. llama-server.exe bawaan repo (cadangan)
   Bila uji di atas gagal, mesin memakai biner llama.cpp yang sudah ada di
   `ai-engine/llama_vulkan/llama-server.exe` (build Vulkan) melalui endpoint
   /v1/chat/completions. Ini bukan pustaka baru maupun layanan eksternal —
   binernya sudah ada di repo dan hanya dijalankan sebagai subprocess lokal.

Keduanya menyajikan model GGUF yang sama dan API Python yang identik, sehingga
seluruh kode di atasnya tidak perlu tahu backend mana yang aktif.

Pemakaian:
    from core import dapatkan_llm
    llm = dapatkan_llm()
    for kalimat in llm.stream_per_kalimat(messages):
        print(kalimat["teks"])
"""

from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Generator, List, Optional

# Nama model target (utamakan LoRA UCIC bila ada).
NAMA_MODEL_TARGET = "qwen3-4b-ucic-q4_k_m.gguf"
NAMA_LORA_TARGET = "qwen3-4b-ucic-lora.gguf"

# Kandidat nama berkas GGUF bila nama target belum ada di disk.
KANDIDAT_MODEL = (
    NAMA_MODEL_TARGET,
    "Qwen3.5-4B-UD-Q4_K_XL.gguf",
    "qwen3.5-4b",
    "qwen3-4b",
    "qwen2.5",
    "qwen",
)

_KONTEKS_TOKENS = 4096
_MAKS_TOKEN_DEFAULT = 512
_SUHU_DEFAULT = 0.6
_PORT_SERVER = int(os.environ.get("SELA_LLM_PORT", "8088"))


class LlmEngine:
    """Pembungkus tunggal mesin LLM SELA (singleton)."""

    _instance: Optional["LlmEngine"] = None
    _kunci_singleton = threading.Lock()
    # Hasil uji kemampuan llama-cpp-python, di-cache per proses.
    _hasil_probe_llama_cpp: Optional[bool] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "LlmEngine":
        if cls._instance is None:
            with cls._kunci_singleton:
                if cls._instance is None:
                    instansi = super().__new__(cls)
                    instansi._sudah_disiapkan = False
                    cls._instance = instansi
        return cls._instance

    def __init__(
        self,
        jalur_model: Optional[str] = None,
        lapisan_gpu: int = -1,
        konteks: int = _KONTEKS_TOKENS,
    ) -> None:
        if getattr(self, "_sudah_disiapkan", False):
            return
        self._sudah_disiapkan = True

        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.abspath(
            os.path.join(self.direktori_induk, "..", "models")
        )
        os.makedirs(self.direktori_model, exist_ok=True)

        self.lapisan_gpu = lapisan_gpu
        self.konteks = konteks
        self.jalur_model = jalur_model or self._temukan_model()
        self.jalur_lora = self._temukan_lora()

        self._llm: Any = None                    # backend llama-cpp-python
        self._server_proses: Optional[subprocess.Popen] = None  # backend llama-server
        self._url_server = f"http://127.0.0.1:{_PORT_SERVER}"
        self._kunci_inferensi = threading.Lock()
        self.apakah_siap = False
        self.backend = "belum"
        self.perangkat_aktif = "cpu"
        self.pesan_status = "belum dimuat"

        self._muat_model()
        atexit.register(self.tutup)

    # ── Penemuan berkas model ─────────────────────────────────────────────────
    def _temukan_model(self) -> str:
        """Pilih berkas GGUF terbaik yang tersedia di folder models/."""
        if not os.path.isdir(self.direktori_model):
            return os.path.join(self.direktori_model, NAMA_MODEL_TARGET)
        berkas = [f for f in os.listdir(self.direktori_model) if f.lower().endswith(".gguf")]
        if not berkas:
            return os.path.join(self.direktori_model, NAMA_MODEL_TARGET)

        def _skor(nama: str) -> int:
            n = nama.lower()
            if n == NAMA_MODEL_TARGET.lower():
                return 100
            if "ucic" in n:
                return 90
            if "qwen3.5" in n or "qwen-3.5" in n:
                return 80
            if "qwen3" in n:
                return 70
            if "qwen" in n:
                return 60
            return 10

        berkas.sort(key=_skor, reverse=True)
        return os.path.join(self.direktori_model, berkas[0])

    def _temukan_lora(self) -> Optional[str]:
        """Cari adaptor LoRA UCIC dalam format GGUF bila disediakan."""
        if not os.path.isdir(self.direktori_model):
            return None
        for nama in (NAMA_LORA_TARGET, "ucic-lora.gguf"):
            jalur = os.path.join(self.direktori_model, nama)
            if os.path.exists(jalur):
                return jalur
        for berkas in os.listdir(self.direktori_model):
            if "lora" in berkas.lower() and berkas.lower().endswith(".gguf"):
                return os.path.join(self.direktori_model, berkas)
        return None

    # ── Pemilihan backend ─────────────────────────────────────────────────────
    def _muat_model(self) -> None:
        if not os.path.exists(self.jalur_model):
            self.apakah_siap = False
            self.pesan_status = f"berkas GGUF tidak ditemukan: {self.jalur_model}"
            print(f"[LLM] Model GGUF belum ada di: {self.jalur_model}")
            print("[LLM] Jalankan `python ai-engine/persiapan_model.py` untuk panduan unduh.")
            return

        if self._uji_llama_cpp() and self._muat_llama_cpp():
            return
        if self._muat_llama_server():
            return

        self.apakah_siap = False
        self.pesan_status = "tidak ada backend LLM yang bisa dimuat"

    def _uji_llama_cpp(self) -> bool:
        """
        Uji llama-cpp-python di SUBPROSES. Bila biner llama.cpp tidak cocok
        dengan CPU (illegal instruction), subproses yang mati, bukan server.
        Hasil di-cache agar hanya dijalankan sekali per sesi.
        """
        if LlmEngine._hasil_probe_llama_cpp is not None:
            return LlmEngine._hasil_probe_llama_cpp

        kode = (
            "import sys\n"
            "from llama_cpp import Llama\n"
            f"m = Llama(model_path=r'{self.jalur_model}', n_gpu_layers=0, "
            "n_ctx=128, n_threads=2, verbose=False)\n"
            "m.create_completion('hi', max_tokens=1)\n"
            "print('PROBE_OK')\n"
        )
        try:
            hasil = subprocess.run(
                [sys.executable, "-c", kode],
                capture_output=True,
                text=True,
                timeout=180,
            )
            ok = hasil.returncode == 0 and "PROBE_OK" in (hasil.stdout or "")
            if not ok:
                print(
                    "[LLM] Uji llama-cpp-python gagal "
                    f"(exit={hasil.returncode}); memakai backend llama-server."
                )
        except Exception as galat:
            ok = False
            print(f"[LLM] Uji llama-cpp-python bermasalah ({galat}); memakai llama-server.")
        LlmEngine._hasil_probe_llama_cpp = ok
        return ok

    def _muat_llama_cpp(self) -> bool:
        """Muat model in-process memakai llama-cpp-python."""
        try:
            from llama_cpp import Llama
        except Exception as galat:
            print(f"[LLM] llama-cpp-python tidak dapat diimpor: {galat}")
            return False

        for lapisan, label in ((self.lapisan_gpu, "gpu"), (0, "cpu")):
            try:
                opsi: Dict[str, Any] = dict(
                    model_path=self.jalur_model,
                    n_gpu_layers=lapisan,
                    n_ctx=self.konteks,
                    n_threads=max(1, (os.cpu_count() or 4) - 1),
                    verbose=False,
                )
                if self.jalur_lora:
                    opsi["lora_path"] = self.jalur_lora
                self._llm = Llama(**opsi)
                self.backend = "llama-cpp-python"
                self.perangkat_aktif = label
                self.apakah_siap = True
                self.pesan_status = f"{os.path.basename(self.jalur_model)} siap via llama-cpp-python ({label})"
                print(f"[LLM] {self.pesan_status}")
                return True
            except Exception as galat:
                print(f"[LLM] llama-cpp-python gagal (n_gpu_layers={lapisan}): {galat}")
                self._llm = None
        return False

    def _temukan_llama_server(self) -> Optional[str]:
        for relatif in (("llama_vulkan", "llama-server.exe"), ("llama_bin", "llama-server.exe")):
            jalur = os.path.join(self.direktori_induk, "..", *relatif)
            jalur = os.path.abspath(jalur)
            if os.path.exists(jalur):
                return jalur
        return None

    def _cek_server(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._url_server}/health", headers={"User-Agent": "SELA"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _muat_llama_server(self) -> bool:
        """Jalankan llama-server.exe bawaan repo sebagai backend cadangan."""
        biner = self._temukan_llama_server()
        if not biner:
            print("[LLM] llama-server.exe tidak ditemukan di llama_vulkan/ atau llama_bin/.")
            return False

        # Pakai server yang sudah hidup bila ada.
        if self._cek_server():
            self.backend = "llama-server"
            self.perangkat_aktif = "server"
            self.apakah_siap = True
            self.pesan_status = f"{os.path.basename(self.jalur_model)} siap via llama-server (sudah aktif)"
            print(f"[LLM] {self.pesan_status}")
            return True

        perintah = [
            biner,
            "-m", self.jalur_model,
            "--port", str(_PORT_SERVER),
            "--host", "127.0.0.1",
            "-ngl", str(self.lapisan_gpu),
            "-c", str(self.konteks),
            "-np", "1",
        ]
        try:
            self._server_proses = subprocess.Popen(
                perintah,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(biner),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as galat:
            print(f"[LLM] Gagal menjalankan llama-server: {galat}")
            return False

        mulai = time.time()
        while time.time() - mulai < 90:
            if self._cek_server():
                self.backend = "llama-server"
                self.perangkat_aktif = "server"
                self.apakah_siap = True
                self.pesan_status = f"{os.path.basename(self.jalur_model)} siap via llama-server (Vulkan)"
                print(f"[LLM] {self.pesan_status}")
                return True
            time.sleep(0.5)
        print("[LLM] llama-server tidak merespons dalam batas waktu.")
        return False

    # ── Inferensi ─────────────────────────────────────────────────────────────
    @staticmethod
    def _bersihkan_think(token: str, state: Dict[str, Any]) -> str:
        """Buang blok penalaran <think>...</think> dari aliran token."""
        if "<think>" in token:
            state["dalam_think"] = True
            token = token.split("<think>", 1)[0]
        if state.get("dalam_think"):
            state["buffer"] = state.get("buffer", "") + token
            if "</think>" in state["buffer"]:
                state["dalam_think"] = False
                token = state["buffer"].split("</think>", 1)[1]
                state["buffer"] = ""
            else:
                return ""
        return token

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        suhu: float = _SUHU_DEFAULT,
        token_maksimal: int = _MAKS_TOKEN_DEFAULT,
    ) -> Generator[str, None, None]:
        """Alirkan token jawaban dari daftar pesan bergaya chat."""
        if not self.apakah_siap:
            return
        if self.backend == "llama-cpp-python":
            yield from self._stream_llama_cpp(messages, suhu, token_maksimal)
        else:
            yield from self._stream_llama_server(messages, suhu, token_maksimal)

    def _stream_llama_cpp(
        self, messages: List[Dict[str, str]], suhu: float, token_maksimal: int
    ) -> Generator[str, None, None]:
        state: Dict[str, Any] = {"dalam_think": False, "buffer": ""}
        try:
            with self._kunci_inferensi:
                aliran = self._llm.create_chat_completion(
                    messages=messages, stream=True, temperature=suhu, max_tokens=token_maksimal
                )
                for potongan in aliran:
                    pilihan = (potongan or {}).get("choices") or [{}]
                    token = (pilihan[0].get("delta") or {}).get("content") or ""
                    if token:
                        token = self._bersihkan_think(token, state)
                        if token:
                            yield token
        except Exception as galat:
            print(f"[LLM] Kendala inferensi (llama-cpp-python): {galat}")

    def _stream_llama_server(
        self, messages: List[Dict[str, str]], suhu: float, token_maksimal: int
    ) -> Generator[str, None, None]:
        state: Dict[str, Any] = {"dalam_think": False, "buffer": ""}
        data = json.dumps(
            {
                "messages": messages,
                "stream": True,
                "temperature": suhu,
                "max_tokens": token_maksimal,
                # Matikan fase penalaran agar SELA menjawab langsung (penting untuk
                # suara). Tanpa ini, model reasoning mengisi token_maksimal dengan
                # penalaran dan tidak pernah menghasilkan jawaban final.
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode("utf-8")
        try:
            with self._kunci_inferensi:
                req = urllib.request.Request(
                    f"{self._url_server}/v1/chat/completions",
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=300) as respon:
                    for baris in respon:
                        baris_str = baris.decode("utf-8", errors="ignore").strip()
                        if not baris_str.startswith("data: "):
                            continue
                        isi = baris_str[6:]
                        if isi == "[DONE]":
                            break
                        try:
                            token = (
                                (json.loads(isi).get("choices") or [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                        except json.JSONDecodeError:
                            continue
                        if token:
                            token = self._bersihkan_think(token, state)
                            if token:
                                yield token
        except Exception as galat:
            print(f"[LLM] Kendala inferensi (llama-server): {galat}")

    def generate_stream(
        self, prompt: str, suhu: float = _SUHU_DEFAULT, token_maksimal: int = _MAKS_TOKEN_DEFAULT
    ) -> Generator[str, None, None]:
        """Alirkan token dari prompt mentah (kompatibilitas prompt ChatML lama)."""
        if self.backend == "llama-cpp-python":
            state: Dict[str, Any] = {"dalam_think": False, "buffer": ""}
            try:
                with self._kunci_inferensi:
                    aliran = self._llm.create_completion(
                        prompt=prompt,
                        stream=True,
                        temperature=suhu,
                        max_tokens=token_maksimal,
                        stop=["<|im_end|>", "<|endoftext|>", "<|im_start|>"],
                    )
                    for potongan in aliran:
                        token = ((potongan or {}).get("choices") or [{}])[0].get("text") or ""
                        if token:
                            token = self._bersihkan_think(token, state)
                            if token:
                                yield token
            except Exception as galat:
                print(f"[LLM] Kendala inferensi prompt mentah: {galat}")
        else:
            # Server hanya menyediakan jalur chat; bungkus prompt mentah sebagai pesan user.
            yield from self.chat_stream(
                [{"role": "user", "content": prompt}], suhu=suhu, token_maksimal=token_maksimal
            )

    # ── Pengelompokan per kalimat untuk TTS ───────────────────────────────────
    @staticmethod
    def _indeks_pemisah(buffer: str, kalimat_pertama: bool = False) -> int:
        """Cari indeks akhir kalimat yang aman (hindari angka/uang & singkatan)."""
        n = len(buffer)
        if n < 10:
            return -1
        for i, char in enumerate(buffer):
            if char == "\n":
                if i >= 6:
                    return i
            elif char in ("?", "!"):
                if i >= 6:
                    return i
            elif char == ",":
                if kalimat_pertama and i >= 25 and i + 1 < n and buffer[i + 1].isspace():
                    return i
            elif char == ".":
                sebelum_angka = i > 0 and buffer[i - 1].isdigit()
                setelah_angka = i + 1 < n and buffer[i + 1].isdigit()
                if sebelum_angka and setelah_angka:
                    continue
                if sebelum_angka and i + 1 >= n:
                    continue
                kata_sebelum = buffer[:i].split()[-1].lower() if buffer[:i].split() else ""
                if kata_sebelum in ("rp", "jl", "dr", "prof", "s", "m", "ir", "no", "vs"):
                    continue
                if i + 1 < n:
                    if buffer[i + 1] in (" ", "\t", "\n", "*", "_", '"', "'", ")"):
                        if i >= 6:
                            return i
                elif i >= 30:
                    return i
        return -1

    def stream_per_kalimat(
        self,
        messages: List[Dict[str, str]],
        suhu: float = _SUHU_DEFAULT,
        token_maksimal: int = _MAKS_TOKEN_DEFAULT,
    ) -> Generator[Dict[str, Any], None, None]:
        """Kelompokkan token menjadi kalimat utuh agar TTS bisa mengalir paralel."""
        buffer = ""
        kalimat_pertama = True
        for token in self.chat_stream(messages, suhu=suhu, token_maksimal=token_maksimal):
            buffer += token
            idx = self._indeks_pemisah(buffer, kalimat_pertama)
            if idx != -1:
                kalimat = buffer[: idx + 1].strip()
                buffer = buffer[idx + 1 :].lstrip(" \t\r\n,")
                bersih = re.sub(r"^[*\-•#\s]+", "", kalimat).strip()
                if bersih and len(bersih) > 1:
                    kalimat_pertama = False
                    yield {"tipe": "kalimat", "teks": kalimat}
        sisa = buffer.strip()
        bersih = re.sub(r"^[*\-•#\s]+", "", sisa).strip()
        if bersih and len(bersih) > 1:
            yield {"tipe": "kalimat", "teks": sisa}

    # ── Status & pembersihan ──────────────────────────────────────────────────
    def info(self) -> Dict[str, Any]:
        return {
            "apakah_siap": self.apakah_siap,
            "backend": self.backend,
            "model": os.path.basename(self.jalur_model) if self.jalur_model else None,
            "lora": os.path.basename(self.jalur_lora) if self.jalur_lora else None,
            "perangkat": self.perangkat_aktif,
            "konteks": self.konteks,
            "pesan": self.pesan_status,
        }

    def tutup(self) -> None:
        """Hentikan subprocess llama-server dengan aman saat aplikasi berhenti."""
        if self._server_proses is not None:
            try:
                self._server_proses.terminate()
                self._server_proses.wait(timeout=3)
            except Exception:
                try:
                    self._server_proses.kill()
                except Exception:
                    pass
            self._server_proses = None


def dapatkan_llm() -> LlmEngine:
    """Ambil instansi tunggal LlmEngine."""
    return LlmEngine()


if __name__ == "__main__":
    mesin = dapatkan_llm()
    print("Status LLM:", mesin.info())
    if mesin.apakah_siap:
        uji = [
            {"role": "system", "content": "Kamu SELA, asisten kampus UCIC. Jawab sangat singkat."},
            {"role": "user", "content": "Sebutkan satu keunggulan UCIC."},
        ]
        print("Streaming per kalimat:")
        for item in mesin.stream_per_kalimat(uji, token_maksimal=120):
            print(" ->", item["teks"])
