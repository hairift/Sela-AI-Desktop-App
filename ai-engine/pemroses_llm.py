"""
SELA AI Desktop - Pemroses Model LLM Offline (GGUF)
Mengeksekusi model format GGUF (Qwen 2.5) secara langsung tanpa ketergantungan Ollama/LM Studio.
Mendukung akselerasi GPU NVIDIA CUDA (RTX 3050) dan streaming kalimat untuk TTS berlatensi nol.
"""

import os
import sys
import re
from typing import Generator, Optional, Dict, Any, List


class PemrosesLlmOffline:
    """
    Eksekutor Model Bahasa Besar (LLM) GGUF Lokal.
    """

    def __init__(self, jalur_model_gguf: Optional[str] = None, lapisan_gpu: int = 35):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.direktori_model = os.path.join(self.direktori_induk, "models")
        os.makedirs(self.direktori_model, exist_ok=True)

        if jalur_model_gguf is None:
            # Cari model GGUF di direktori models/
            jalur_model_gguf = self._temukan_model_gguf_tersedia()

        self.jalur_model = jalur_model_gguf
        self.lapisan_gpu = lapisan_gpu
        self.model_llama = None
        self.apakah_siap = False

        self.inisialisasi_model()

    def _temukan_model_gguf_tersedia(self) -> str:
        """Mencari file .gguf di direktori models/."""
        if os.path.exists(self.direktori_model):
            for nama_berkas in os.listdir(self.direktori_model):
                if nama_berkas.endswith(".gguf"):
                    return os.path.join(self.direktori_model, nama_berkas)

        # Nama berkas model default yang direkomendasikan
        return os.path.join(self.direktori_model, "qwen2.5-7b-instruct-q4_k_m.gguf")

    def inisialisasi_model(self):
        """Memuat model GGUF ke dalam memori RAM/VRAM GPU."""
        if not os.path.exists(self.jalur_model):
            print(f"[Pemroses LLM] Catatan: Berkas model GGUF belum diletakkan di:\n  -> {self.jalur_model}")
            print("[Pemroses LLM] Mode Fallback Terstruktur (Ekstraksi Fakta Langsung) aktif.")
            self.apakah_siap = False
            return

        try:
            print(f"[Pemroses LLM] Memuat model GGUF: {os.path.basename(self.jalur_model)}")
            print(f"[Pemroses LLM] Mengaktifkan offloading ke GPU NVIDIA (n_gpu_layers={self.lapisan_gpu})...")

            # Mencoba mengimpor llama_cpp secara dinamis
            import importlib
            modul_llama = importlib.import_module("llama_cpp")
            Llama = getattr(modul_llama, "Llama")

            self.model_llama = Llama(
                model_path=self.jalur_model,
                n_gpu_layers=self.lapisan_gpu,
                n_ctx=4096,
                n_threads=8,
                verbose=False,
            )
            self.apakah_siap = True
            print("[Pemroses LLM] Model GGUF berhasil dimuat dan siap melayani inferensi lokal!")
        except ImportError:
            print("[Pemroses LLM] Pustaka 'llama-cpp-python' belum terpasang.")
            print("[Pemroses LLM] Gunakan 'pip install llama-cpp-python' untuk akselerasi native.")
            self.apakah_siap = False
        except Exception as galat:
            print(f"[Pemroses LLM] Kendala inisialisasi model: {galat}")
            self.apakah_siap = False

    def hasilkan_jawaban_streaming(
        self, prompt_instruksi: str, suhu: float = 0.6, token_maksimal: int = 400
    ) -> Generator[str, None, None]:
        """
        Menghasilkan token teks secara streaming token demi token.
        Jika binary GGUF belum dimasukkan pengguna, fallback cerdas ekstraksi fakta langsung berjalan.
        """
        if self.apakah_siap and self.model_llama is not None:
            try:
                aliran_keluaran = self.model_llama(
                    prompt_instruksi,
                    max_tokens=token_maksimal,
                    temperature=suhu,
                    top_p=0.9,
                    stream=True,
                    stop=["<|im_end|>", "<|endoftext|>", "user:", "\nuser\n"],
                )

                for potongan in aliran_keluaran:
                    teks_potongan = potongan["choices"][0]["text"]
                    if teks_potongan:
                        yield teks_potongan
                return
            except Exception as galat:
                print(f"[Pemroses LLM] Galat saat inferensi GGUF: {galat}")

        # Fallback Cerdas: Ekstraksi Fakta Dokumen (Bebas Halusinasi 100%)
        # Menerapkan strategi Ekstraksi Fakta yang disarankan
        yield from self._hasilkan_ekstraksi_fallback(prompt_instruksi)

    def _hasilkan_ekstraksi_fallback(self, prompt_lengkap: str) -> Generator[str, None, None]:
        # 1. Periksa apakah sudah ada respon terarah dari intent classifier
        tag_asisten = "<|im_start|>assistant\n"
        if tag_asisten in prompt_lengkap:
            bagian_asisten = prompt_lengkap.split(tag_asisten)[-1].split("<|im_end|>")[0].strip()
            if bagian_asisten:
                for kata in bagian_asisten.split(" "):
                    yield kata + " "
                return

        # 2. Ekstrak bagian dokumen dari prompt
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
        # Ambil ringkasan kalimat utama dokumen
        baris_dokumen = [b.strip() for b in konten_dokumen.split("\n") if b.strip() and not b.startswith("---")]

        kalimat_pembuka = "Baik, berikut informasi resmi dari Universitas Catur Insan Cendekia (UCIC):\n\n"
        for kata in kalimat_pembuka.split(" "):
            yield kata + " "

        # Format baris dokumen dengan rapi, hindari pengulangan URL
        url_ditemukan = set()
        baris_terpilih = []
        for baris in baris_dokumen:
            if len(baris_terpilih) >= 7:
                break
            # Lewati baris kosong atau duplikat
            if not baris or baris in baris_terpilih:
                continue
            # Batasi URL berulang agar tidak menimbulkan QR ganda
            urls = re.findall(r"https?://\S+", baris)
            if urls:
                if any(u in url_ditemukan for u in urls):
                    continue
                for u in urls:
                    url_ditemukan.add(u)
            baris_terpilih.append(baris)

        for baris in baris_terpilih:
            yield baris + "\n"

        kalimat_penutup = "\nAda lagi informasi seputar kampus UCIC yang ingin Anda tanyakan?"
        for kata in kalimat_penutup.split(" "):
            yield kata + " "

    def streaming_per_kalimat(
        self, prompt_instruksi: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Mengelompokkan token streaming menjadi kalimat utuh (. ? ! \n)
        segera setelah kalimat selesai untuk langsung disintesis oleh TTS.
        """
        buffer_kalimat = ""
        tanda_akhir_kalimat = {".", "?", "!", "\n"}
        apakah_kalimat_pertama = True

        for token in self.hasilkan_jawaban_streaming(prompt_instruksi):
            buffer_kalimat += token

            # Untuk kalimat pertama, izinkan tanda koma jika sudah mencapai panjang minimum
            tanda_aktif = set(tanda_akhir_kalimat)
            if apakah_kalimat_pertama and len(buffer_kalimat.strip()) > 20:
                tanda_aktif.add(",")

            apakah_ada_tanda = any(tanda in buffer_kalimat for tanda in tanda_aktif)
            if apakah_ada_tanda and len(buffer_kalimat.strip()) > 10:
                # Cari pemisah kalimat pertama yang muncul
                indeks_pemisah = -1
                for tanda in tanda_aktif:
                    pos = buffer_kalimat.find(tanda)
                    if pos != -1 and (indeks_pemisah == -1 or pos < indeks_pemisah):
                        indeks_pemisah = pos

                if indeks_pemisah != -1:
                    kalimat_siap = buffer_kalimat[: indeks_pemisah + 1].strip()
                    buffer_kalimat = buffer_kalimat[indeks_pemisah + 1 :]

                    if kalimat_siap:
                        apakah_kalimat_pertama = False
                        yield {"tipe": "kalimat", "teks": kalimat_siap}

        # Keluarkan sisa buffer jika ada
        sisa = buffer_kalimat.strip()
        if sisa:
            yield {"tipe": "kalimat", "teks": sisa}


if __name__ == "__main__":
    pemroses = PemrosesLlmOffline()
    print(f"Status Model Siap: {pemroses.apakah_siap}")
    prompt_tes = "<|im_start|>system\nKamu SELA.<|im_end|>\n<|im_start|>user\nTes respon<|im_end|>\n<|im_start|>assistant\n"
    print("Hasil streaming pengujian:")
    for potongan_kalimat in pemroses.streaming_per_kalimat(prompt_tes):
        print(f"-> Kalimat siap untuk TTS: {potongan_kalimat['teks']}")
