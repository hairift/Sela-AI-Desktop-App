"""
SELA AI Desktop - Pemroses Model LLM Offline (GGUF via llama.cpp)
Mengeksekusi model format GGUF (Qwen 3.5 4B Parameter) secara native offline
menggunakan engine llama.cpp berakselerasi GPU (NVIDIA GeForce RTX 3050).
Mendukung streaming token demi token dan pemotongan per kalimat untuk sintesis suara OmniVoice ultra-low latency.
"""

import os
import sys
import re
import json
import time
import atexit
import subprocess
import urllib.request
import urllib.error
from typing import Generator, Optional, Dict, Any, List


class PemrosesLlmOffline:
    """
    Eksekutor Model Bahasa Besar (LLM) GGUF Lokal berbasis engine resmi llama.cpp.
    """

    def __init__(self, jalur_model_gguf: Optional[str] = None, lapisan_gpu: int = 35, port: int = 8088):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.join(self.direktori_induk, "models")
        os.makedirs(self.direktori_model, exist_ok=True)

        if jalur_model_gguf is None:
            jalur_model_gguf = self._temukan_model_gguf_tersedia()

        self.jalur_model = jalur_model_gguf
        self.lapisan_gpu = lapisan_gpu
        self.port = port
        self.url_dasar = f"http://127.0.0.1:{self.port}"
        self.proses_server: Optional[subprocess.Popen] = None
        self.apakah_siap = False

        self.inisialisasi_model()
        atexit.register(self.tutup)

    def _temukan_model_gguf_tersedia(self) -> str:
        """Mencari file .gguf di direktori models/ dengan prioritas Qwen 3.5 4B."""
        if os.path.exists(self.direktori_model):
            berkas_gguf = [f for f in os.listdir(self.direktori_model) if f.endswith(".gguf")]
            
            # 1. Prioritaskan Qwen 3.5 4B
            for nama in berkas_gguf:
                if "qwen3.5" in nama.lower() or "qwen-3.5" in nama.lower():
                    return os.path.join(self.direktori_model, nama)
            
            # 2. Prioritaskan model Qwen lainnya
            for nama in berkas_gguf:
                if "qwen" in nama.lower():
                    return os.path.join(self.direktori_model, nama)
            
            # 3. Model GGUF pertama yang tersedia
            if berkas_gguf:
                return os.path.join(self.direktori_model, berkas_gguf[0])

        return os.path.join(self.direktori_model, "Qwen3.5-4B-UD-Q4_K_XL.gguf")

    def _temukan_binari_llama_server(self) -> Optional[str]:
        """Mencari binary llama-server.exe (prioritaskan Vulkan GPU, lalu CPU)."""
        jalur_vulkan = os.path.join(self.direktori_induk, "llama_vulkan", "llama-server.exe")
        if os.path.exists(jalur_vulkan):
            return jalur_vulkan

        jalur_cpu = os.path.join(self.direktori_induk, "llama_bin", "llama-server.exe")
        if os.path.exists(jalur_cpu):
            return jalur_cpu

        return None

    def _cek_server_aktif(self) -> bool:
        """Memeriksa apakah server llama.cpp lokal sedang merespons."""
        try:
            url_kesehatan = f"{self.url_dasar}/health"
            req = urllib.request.Request(url_kesehatan, headers={"User-Agent": "SELA-AI"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status in (200, 503):  # 503 is loading, but alive
                    data = json.loads(resp.read().decode("utf-8"))
                    status = data.get("status", "")
                    return status in ("ok", "loading model", "ready") or resp.status == 200
        except Exception:
            pass
        return False

    def inisialisasi_model(self):
        """Memastikan llama-server lokal aktif dan melayani model Qwen 3.5 GGUF."""
        if not os.path.exists(self.jalur_model):
            print(f"[Pemroses LLM] Catatan: Berkas model GGUF belum diletakkan di:\n  -> {self.jalur_model}")
            print("[Pemroses LLM] Mode Fallback Terstruktur (Ekstraksi Fakta Langsung) aktif.")
            self.apakah_siap = False
            return

        # Periksa apakah server sudah berjalan di port 8088
        if self._cek_server_aktif():
            print(f"[Pemroses LLM] llama-server aktif terdeteksi di {self.url_dasar}!")
            self.apakah_siap = True
            return

        binari_server = self._temukan_binari_llama_server()
        if not binari_server:
            print("[Pemroses LLM] Biner llama-server.exe tidak ditemukan di folder llama_vulkan atau llama_bin.")
            self.apakah_siap = False
            return

        nama_model = os.path.basename(self.jalur_model)
        tipe_engine = "Vulkan GPU (NVIDIA RTX 3050)" if "llama_vulkan" in binari_server else "CPU Multi-Core"
        print(f"[Pemroses LLM] Memulai llama-server ({tipe_engine}) untuk model: {nama_model}...")

        perintah = [
            binari_server,
            "-m", self.jalur_model,
            "--port", str(self.port),
            "-ngl", str(self.lapisan_gpu),
            "-c", "4096",
            "--host", "127.0.0.1",
            "-np", "1",
        ]

        try:
            self.proses_server = subprocess.Popen(
                perintah,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(binari_server),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            # Tunggu hingga server siap melayani permintaan
            waktu_mulai = time.time()
            while time.time() - waktu_mulai < 15:
                if self._cek_server_aktif():
                    self.apakah_siap = True
                    print(f"[Pemroses LLM] Model {nama_model} siap melayani inferensi lokal via llama.cpp!")
                    return
                time.sleep(0.5)

            if self._cek_server_aktif():
                self.apakah_siap = True
                print(f"[Pemroses LLM] Model {nama_model} siap melayani inferensi lokal via llama.cpp!")
            else:
                print("[Pemroses LLM] Peringatan: llama-server membutuhkan waktu lebih lama untuk memuat.")
                self.apakah_siap = True  # Tandai siap karena proses berjalan
        except Exception as e:
            print(f"[Pemroses LLM] Kendala menjalankan llama-server: {e}")
            self.apakah_siap = False

    def hasilkan_jawaban_streaming(
        self, prompt_instruksi: str, suhu: float = 0.6, token_maksimal: int = 500
    ) -> Generator[str, None, None]:
        """
        Menghasilkan token teks secara streaming token demi token dari llama-server.
        Membersihkan tag penalaran <think>...</think> agar respons SELA langsung bersih dan cepat.
        """
        # Cek jika prompt sudah memiliki jawaban instan (misal intent sapaan/identitas cepat)
        tag_asisten = "<|im_start|>assistant\n"
        if tag_asisten in prompt_instruksi and prompt_instruksi.rstrip().endswith("<|im_end|>"):
            bagian_asisten = prompt_instruksi.split(tag_asisten)[-1].split("<|im_end|>")[0].strip()
            if bagian_asisten:
                for kata in bagian_asisten.split(" "):
                    yield kata + " "
                return

        if self.apakah_siap:
            try:
                # Pastikan server aktif jika sempat terhenti
                if not self._cek_server_aktif():
                    self.inisialisasi_model()

                # Jika prompt berakhir dengan <|im_start|>assistant\n, bypass fase penalaran <think>
                # agar respons SELA langsung mengalir seketika untuk TTS & UI
                prompt_efektif = prompt_instruksi
                if prompt_efektif.endswith("<|im_start|>assistant\n"):
                    prompt_efektif += "<think>\n</think>\n"

                data_permintaan = {
                    "prompt": prompt_efektif,
                    "stream": True,
                    "n_predict": token_maksimal,
                    "temperature": suhu,
                    "stop": ["<|im_end|>", "<|endoftext|>", "user:", "\nuser\n", "<|im_start|>user"],
                }

                req = urllib.request.Request(
                    f"{self.url_dasar}/completion",
                    data=json.dumps(data_permintaan).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )

                di_dalam_think = False
                buffer_think = ""
                with urllib.request.urlopen(req, timeout=30) as respon:
                    for baris in respon:
                        baris_str = baris.decode("utf-8", errors="ignore").strip()
                        if not baris_str.startswith("data: "):
                            continue

                        isi_data = baris_str[6:]
                        if isi_data == "[DONE]":
                            break

                        try:
                            potongan = json.loads(isi_data)
                            token = potongan.get("content", "")
                            if not token:
                                continue

                            # Filter tag penalaran <think>...</think>
                            if "<think>" in token:
                                di_dalam_think = True
                                token = token.split("<think>", 1)[0]

                            if di_dalam_think:
                                buffer_think += token
                                if "</think>" in buffer_think:
                                    di_dalam_think = False
                                    token = buffer_think.split("</think>", 1)[1]
                                    buffer_think = ""
                                else:
                                    continue

                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue

                return
            except Exception as galat:
                print(f"[Pemroses LLM] Kendala inferensi llama-server: {galat}")

        # Fallback Cerdas: Ekstraksi Fakta Dokumen
        yield from self._hasilkan_ekstraksi_fallback(prompt_instruksi)

    def _hasilkan_ekstraksi_fallback(self, prompt_lengkap: str) -> Generator[str, None, None]:
        """Fallback cerdas berbasis ekstraksi dokumen jika binary/model belum siap."""
        tag_asisten = "<|im_start|>assistant\n"
        if tag_asisten in prompt_lengkap:
            bagian_asisten = prompt_lengkap.split(tag_asisten)[-1].split("<|im_end|>")[0].strip()
            if bagian_asisten:
                for kata in bagian_asisten.split(" "):
                    yield kata + " "
                return

        tag_dokumen = "DOKUMEN RESMI KAMPUS UCIC:\n"
        if tag_dokumen not in prompt_lengkap:
            teks_default = (
                "Halo! Terima kasih telah menghubungi SELA Customer Service UCIC. "
                "Informasi yang Anda tanyakan belum tercatat secara spesifik pada basis data kami. "
                "Silakan kunjungi situs resmi Universitas CIC di https://pmb.cic.ac.id atau hubungi WhatsApp PMB di 0812 1670 0519 ya!"
            )
            for kata in teks_default.split(" "):
                yield kata + " "
            return

        konten_dokumen = prompt_lengkap.split(tag_dokumen)[-1].split("<|im_end|>")[0].strip()
        baris_dokumen = [b.strip() for b in konten_dokumen.split("\n") if b.strip() and not b.startswith("---")]

        baris_terpilih = []
        url_ditemukan = set()
        for baris in baris_dokumen:
            if len(baris_terpilih) >= 3:
                break
            if not baris or baris in baris_terpilih:
                continue
            if baris.startswith("http"):
                continue
            urls = re.findall(r"https?://\S+", baris)
            if urls:
                if any(u in url_ditemukan for u in urls):
                    continue
                for u in urls:
                    url_ditemukan.add(u)
            baris_terpilih.append(baris)

        import random
        kalimat_pembuka_pilihan = [
            "Tentu, berikut informasi resmi dari UCIC yang kamu tanyakan:\n\n",
            "Jadi begini, terkait pertanyaanmu, ini datanya:\n\n",
            "Baik, ini informasi resmi dari Universitas Catur Insan Cendekia:\n\n",
            "Untuk yang itu, ini jawabannya berdasarkan data resmi kampus:\n\n",
        ]
        kalimat_pembuka = random.choice(kalimat_pembuka_pilihan)
        for kata in kalimat_pembuka.split(" "):
            yield kata + " "

        for baris in baris_terpilih:
            yield baris + "\n"

        kalimat_penutup_pilihan = [
            "\nAda lagi informasi seputar kampus UCIC yang ingin Anda tanyakan?",
            "\nMasih ada yang ingin SELA bantu seputar kampus UCIC?",
            "\nKalau ada pertanyaan lain seputar UCIC, silakan tanyakan ya!",
            "\nSELA siap bantu kalau ada yang ingin ditanyakan lagi seputar kampus.",
        ]
        kalimat_penutup = random.choice(kalimat_penutup_pilihan)
        for kata in kalimat_penutup.split(" "):
            yield kata + " "

    def _cari_indeks_pemisah_kalimat(self, buffer: str, apakah_kalimat_pertama: bool = False) -> int:
        """
        Mencari indeks pemisah kalimat (. ? ! \n) yang valid.
        Menghindari pemotongan di tengah format angka/uang (misal Rp2.820.000),
        singkatan gelar (S.Kom, Dr., Prof.), atau nomor.
        """
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
                if apakah_kalimat_pertama and i >= 25:
                    if i + 1 < n and buffer[i + 1].isspace():
                        return i
            elif char == ".":
                # Cek apakah bagian dari angka/uang (misal 2.820.000)
                sebelum_angka = (i > 0 and buffer[i - 1].isdigit())
                setelah_angka = (i + 1 < n and buffer[i + 1].isdigit())
                if sebelum_angka and setelah_angka:
                    continue
                if sebelum_angka and i + 1 >= n:
                    # Menunggu token berikutnya untuk memastikan bukan kelanjutan digit uang
                    continue
                # Cek apakah singkatan umum / nomor urut (misal 1. atau S.Kom)
                kata_sebelum = buffer[:i].split()[-1].lower() if buffer[:i].split() else ""
                if kata_sebelum in ("rp", "jl", "dr", "prof", "s", "m", "ir", "no", "vs"):
                    continue
                # Pemisah titik yang valid jika diikuti spasi, newline, kutip, bintang, atau tutup kurung
                if i + 1 < n:
                    if buffer[i + 1] in (" ", "\t", "\n", "*", "_", '"', "'", ")"):
                        if i >= 6:
                            return i
                elif i >= 30:
                    return i

        return -1

    def streaming_per_kalimat(
        self, prompt_instruksi: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Mengelompokkan token streaming menjadi kalimat utuh (. ? ! \n)
        segera setelah kalimat selesai untuk langsung disintesis oleh TTS.
        """
        buffer_kalimat = ""
        apakah_kalimat_pertama = True

        for token in self.hasilkan_jawaban_streaming(prompt_instruksi):
            buffer_kalimat += token

            indeks_pemisah = self._cari_indeks_pemisah_kalimat(buffer_kalimat, apakah_kalimat_pertama)
            if indeks_pemisah != -1:
                kalimat_siap = buffer_kalimat[: indeks_pemisah + 1].strip()
                buffer_kalimat = buffer_kalimat[indeks_pemisah + 1 :].lstrip(" \t\r\n,")

                # Bersihkan jika hanya markdown bullet kosong atau tanda baca
                teks_bersih = re.sub(r"^[*\-•#\s]+", "", kalimat_siap).strip()
                if teks_bersih and len(teks_bersih) > 1:
                    apakah_kalimat_pertama = False
                    yield {"tipe": "kalimat", "teks": kalimat_siap}

        sisa = buffer_kalimat.strip()
        teks_sisa_bersih = re.sub(r"^[*\-•#\s]+", "", sisa).strip()
        if teks_sisa_bersih and len(teks_sisa_bersih) > 1:
            yield {"tipe": "kalimat", "teks": sisa}

    def tutup(self):
        """Menutup subprocess llama-server dengan aman saat aplikasi berhenti."""
        if self.proses_server is not None:
            try:
                self.proses_server.terminate()
                self.proses_server.wait(timeout=2)
            except Exception:
                try:
                    self.proses_server.kill()
                except Exception:
                    pass
            self.proses_server = None


if __name__ == "__main__":
    pemroses = PemrosesLlmOffline()
    print(f"Status Model Siap: {pemroses.apakah_siap}")
    prompt_tes = "<|im_start|>system\nKamu SELA, asisten AI resmi UCIC.<|im_end|>\n<|im_start|>user\nSebutkan keunggulan UCIC secara singkat.<|im_end|>\n<|im_start|>assistant\n"
    print("Hasil streaming per kalimat untuk TTS:")
    for potongan in pemroses.streaming_per_kalimat(prompt_tes):
        print(f"-> [TTS KALIMAT]: {potongan['teks']}")
