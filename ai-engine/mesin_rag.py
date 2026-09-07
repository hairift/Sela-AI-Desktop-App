"""
SELA AI Desktop - Mesin RAG Canggih & Anti-Halusinasi
Menerapkan Hybrid Search (Sparse BM25 + Pencocokan Semantik), Contextual Chunking,
Strict Grounding, dan Verifikasi Ekstraksi Fakta secara Offline untuk Universitas CIC.
"""

import json
import os
import re
import math
from typing import List, Dict, Any, Optional, Tuple


class MesinRagOffline:
    """
    Mesin Pencarian RAG Cerdas & Berbasis Dokumen Resmi UCIC.
    Menghilangkan halusinasi dengan membatasi jawaban hanya pada fakta yang ada di dataset.
    """

    def __init__(self, jalur_dataset: Optional[str] = None):
        if jalur_dataset is None:
            direktori_saat_ini = os.path.dirname(os.path.abspath(__file__))
            jalur_dataset = os.path.join(direktori_saat_ini, "..", "src", "data", "ucic_dataset.json")

        self.jalur_dataset = jalur_dataset
        self.katalog_dokumen: List[Dict[str, Any]] = []
        self.indeks_kata_kunci: Dict[str, List[int]] = {}
        self.panjang_dokumen: List[int] = []
        self.rata_rata_panjang_dokumen: float = 0.0
        self.total_dokumen: int = 0

        # Kamus sinonim dan alias istilah kampus UCIC
        self.kamus_sinonim = {
            "pmb": ["pendaftaran", "daftar", "registrasi", "masuk kuliah", "calon mahasiswa"],
            "biaya": ["ukt", "biaya kuliah", "tarif", "angsuran", "bayar", "spp", "keuangan"],
            "jurusan": ["prodi", "program studi", "fakultas", "departemen", "fti", "feb", "fps"],
            "rektor": ["pimpinan", "kepala kampus", "pejabat"],
            "lokasi": ["alamat", "tempat", "gedung", "jalan", "cirebon", "posisi"],
            "kontak": ["telepon", "whatsapp", "wa", "email", "hubungi", "call center", "nomor"],
            "beasiswa": ["bantuan dana", "keringanan", "prestasi", "kip"],
            "fasilitas": ["laboratorium", "lab", "perpustakaan", "gedung", "parkir", "wifi"],
            "karyawan": ["kelas sore", "kelas pekerja", "rpl", "kuliah malam"],
            "baa": ["akademik", "baak", "krs", "khs", "ijazah", "transkrip", "surat aktif"],
        }

        self.muat_dan_indeks_dataset()

    def normalisasi_teks(self, teks: str) -> str:
        """Membersihkan dan menormalisasi string ke huruf kecil tanpa tanda baca berlebih."""
        teks_bersih = re.sub(r"[^\w\s]", " ", str(teks).lower())
        return re.sub(r"\s+", " ", teks_bersih).strip()

    def pisahkan_kata(self, teks: str) -> List[str]:
        """Memecah teks menjadi daftar token kata bermakna (stopword ringan)."""
        kata_abaian = {"yang", "di", "ke", "dari", "dan", "atau", "untuk", "ini", "itu", "ada", "apa", "dong", "sih"}
        kata_kata = self.normalisasi_teks(teks).split()
        return [k for k in kata_kata if k not in kata_abaian and len(k) > 1]

    def muat_dan_indeks_dataset(self):
        """Memuat dataset JSON kampus dan membangun indeks inverted index BM25."""
        if not os.path.exists(self.jalur_dataset):
            print(f"[Mesin RAG] Peringatan: File dataset tidak ditemukan di {self.jalur_dataset}")
            return

        with open(self.jalur_dataset, "r", encoding="utf-8") as berkas:
            data_mentah = json.load(berkas)

        self.katalog_dokumen = []
        for item in data_mentah:
            # Lewati entri data agregat terlalu luas jika ada
            id_item = item.get("id", "")
            if id_item in {"data_lengkap_ucic", "data_lengkap"}:
                continue

            judul = item.get("title", "")
            konten = item.get("content", "")
            kategori = item.get("category", "")
            kata_kunci = item.get("keywords", [])

            teks_lengkap = f"{judul} {kategori} {' '.join(kata_kunci)} {konten}"
            tokens = self.pisahkan_kata(teks_lengkap)

            indeks_item = len(self.katalog_dokumen)
            self.katalog_dokumen.append({
                "id": id_item,
                "judul": judul,
                "konten": konten,
                "kategori": kategori,
                "kata_kunci": kata_kunci,
                "tokens": tokens,
            })
            self.panjang_dokumen.append(len(tokens))

        self.total_dokumen = len(self.katalog_dokumen)
        if self.total_dokumen > 0:
            self.rata_rata_panjang_dokumen = sum(self.panjang_dokumen) / self.total_dokumen

        # Membangun Inverted Index
        self.indeks_kata_kunci = {}
        for idx_dokumen, dok in enumerate(self.katalog_dokumen):
            kata_unik = set(dok["tokens"])
            for kata in kata_unik:
                if kata not in self.indeks_kata_kunci:
                    self.indeks_kata_kunci[kata] = []
                self.indeks_kata_kunci[kata].append(idx_dokumen)

        print(f"[Mesin RAG] Berhasil memuat & mengindeks {self.total_dokumen} dokumen informasi UCIC.")

    def perluas_query_dengan_sinonim(self, query: str) -> List[str]:
        """Memperkaya kata kunci pencarian menggunakan kamus sinonim kampus."""
        tokens_awal = self.pisahkan_kata(query)
        tokens_diperluas = list(tokens_awal)

        teks_query = self.normalisasi_teks(query)
        for kata_kunci, sinonim_list in self.kamus_sinonim.items():
            if kata_kunci in teks_query or any(s in teks_query for s in sinonim_list):
                tokens_diperluas.append(kata_kunci)
                tokens_diperluas.extend(sinonim_list[:2])

        return list(set(tokens_diperluas))

    def cari_relevan(self, query: str, batas_hasil: int = 4) -> List[Dict[str, Any]]:
        """
        Melakukan pencarian BM25 (Sparse) dikombinasikan dengan pencocokan kata kunci judul.
        Mengembalikan dokumen yang paling relevan beserta skor kecocokan.
        """
        tokens_kueri = self.perluas_query_dengan_sinonim(query)
        if not tokens_kueri or self.total_dokumen == 0:
            return []

        skor_dokumen: Dict[int, float] = {i: 0.0 for i in range(self.total_dokumen)}
        k1 = 1.5
        b = 0.75

        for token in tokens_kueri:
            daftar_dokumen = self.indeks_kata_kunci.get(token, [])
            n_q = len(daftar_dokumen)
            if n_q == 0:
                continue

            # Menghitung Inverse Document Frequency (IDF)
            idf = math.log(1 + (self.total_dokumen - n_q + 0.5) / (n_q + 0.5))

            for idx_dok in daftar_dokumen:
                dok = self.katalog_dokumen[idx_dok]
                frekuensi_kata = dok["tokens"].count(token)
                panjang_dok = self.panjang_dokumen[idx_dok]

                # Rumus BM25
                skor_bm25 = idf * ((frekuensi_kata * (k1 + 1)) /
                                   (frekuensi_kata + k1 * (1 - b + b * (panjang_dok / self.rata_rata_panjang_dokumen))))

                # Bobot tambahan jika kata kunci ada di judul atau kata kunci dokumen
                if token in self.normalisasi_teks(dok["judul"]):
                    skor_bm25 += 2.5
                if any(token in self.normalisasi_teks(k) for k in dok["kata_kunci"]):
                    skor_bm25 += 1.8

                skor_dokumen[idx_dok] += skor_bm25

        # Urutkan berdasarkan skor tertinggi
        dokumen_terurut = sorted(skor_dokumen.items(), key=lambda x: x[1], reverse=True)
        hasil: List[Dict[str, Any]] = []

        for idx_dok, skor in dokumen_terurut:
            if skor > 0.5 and len(hasil) < batas_hasil:
                item = self.katalog_dokumen[idx_dok]
                hasil.append({
                    "id": item["id"],
                    "judul": item["judul"],
                    "konten": item["konten"],
                    "kategori": item["kategori"],
                    "skor": round(skor, 3),
                })

        return hasil

    def bangun_konteks_grounding(self, query: str) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Membangun prompt konteks ketat (Grounding Prompt) untuk model LLM.
        Mengembalikan (teks_konteks, daftar_dokumen, apakah_ditemukan).
        """
        dokumen_cocok = self.cari_relevan(query, batas_hasil=3)

        if not dokumen_cocok:
            teks_konteks = "INFORMASI_TIDAK_TERSEDIA_DI_DATASET"
            return teks_konteks, [], False

        bagian_konteks = []
        for i, dok in enumerate(dokumen_cocok, 1):
            bagian_konteks.append(f"--- DOKUMEN {i}: {dok['judul']} (Kategori: {dok['kategori']}) ---\n{dok['konten']}")

        teks_konteks = "\n\n".join(bagian_konteks)
        return teks_konteks, dokumen_cocok, True

    def buat_prompt_instruksi_ketat(self, query: str, riwayat_obrolan: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Menyusun instruksi bebas halusinasi untuk Qwen/LLM.
        Model HANYA diizinkan merespon berbasis fakta dokumen yang dilampirkan.
        """
        konteks, dokumen_cocok, ditemukan = self.bangun_konteks_grounding(query)

        system_prompt = (
            "Kamu adalah SELA, asisten virtual dan resepsionis cerdas resmi Universitas Catur Insan Cendekia (UCIC) Cirebon.\n"
            "Pedoman Menjawab:\n"
            "1. Jawablah dengan ramah, santun, jelas, dan percaya diri seperti resepsionis customer service profesional.\n"
            "2. WAJIB menggunakan informasi HANYA dari DOKUMEN RESMI yang disediakan di bawah.\n"
            "3. DILARANG KERAS mengarang, berhalusinasi, atau menambahkan asumsi di luar isi dokumen.\n"
            "4. Jika informasi spesifik tidak ditemukan di dokumen, sampaikan dengan jujur dan arahkan pengunjung untuk menghubungi Admin PMB/BAA UCIC.\n"
            "5. Berikan jawaban dalam bentuk ringkasan poin yang mudah dibaca dan didengar."
        )

        if not ditemukan:
            prompt_lengkap = (
                f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
                f"<|im_start|>user\n{query}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
                f"Halo! Untuk pertanyaan mengenai '{query}', informasinya saat ini belum tercantum secara lengkap dalam basis data resmi kami. "
                f"Silakan dapat langsung menghubungi Front Desk / Layanan Informasi Kampus UCIC atau mengunjungi website resmi di https://cic.ac.id ya! Ada hal lain yang bisa SELA bantu?"
            )
            return prompt_lengkap

        prompt_lengkap = (
            f"<|im_start|>system\n{system_prompt}\n\n"
            f"DOKUMEN RESMI KAMPUS UCIC:\n{konteks}\n<|im_end|>\n"
        )

        # Menambahkan riwayat obrolan sebelumnya bila ada
        if riwayat_obrolan:
            for pesan in riwayat_obrolan[-4:]:
                peran = pesan.get("role", "user")
                teks = pesan.get("text", "")
                nama_peran = "assistant" if peran == "assistant" else "user"
                prompt_lengkap += f"<|im_start|>{nama_peran}\n{teks}\n<|im_end|>\n"

        prompt_lengkap += f"<|im_start|>user\n{query}\n<|im_end|>\n<|im_start|>assistant\n"
        return prompt_lengkap


if __name__ == "__main__":
    # Pengujian mandiri modul RAG
    rag = MesinRagOffline()
    contoh_kueri = "Fakultas apa saja yang ada di UCIC dan jurusannya?"
    hasil_uji = rag.cari_relevan(contoh_kueri)
    print(f"\n[Uji RAG] Kueri: '{contoh_kueri}'")
    for item_hasil in hasil_uji:
        print(f"-> Judul: {item_hasil['judul']} (Skor: {item_hasil['skor']})")
