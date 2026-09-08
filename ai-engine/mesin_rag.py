"""
SELA AI Desktop - Mesin RAG Canggih, Percakapan Alami, & Anti-Halusinasi
Menerapkan Hybrid Search (BM25 + Semantic Boosting), Conversational Intent Classifier,
Multi-Turn Context Linking, dan Strict Grounding secara Offline untuk Universitas CIC.
"""

import json
import os
import re
import math
from typing import List, Dict, Any, Optional, Tuple


class MesinRagOffline:
    """
    Mesin Pencarian RAG Cerdas & Berbasis Dokumen Resmi UCIC.
    Menghilangkan halusinasi dengan membatasi jawaban hanya pada fakta yang ada di dataset
    serta memahami percakapan sapaan/identitas secara alami.
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
            "ti": ["teknik informatika", "informatika", "it"],
            "si": ["sistem informasi", "is"],
            "dkv": ["desain komunikasi visual", "desain grafis", "animasi"],
            "rektor": ["pimpinan", "kepala kampus", "pejabat"],
            "lokasi": ["alamat", "tempat", "gedung", "jalan", "cirebon", "posisi"],
            "kontak": ["telepon", "whatsapp", "wa", "email", "hubungi", "call center", "nomor"],
            "beasiswa": ["bantuan dana", "keringanan", "prestasi", "kip"],
            "fasilitas": ["laboratorium", "lab", "perpustakaan", "gedung", "parkir", "wifi"],
            "karyawan": ["kelas sore", "kelas pekerja", "rpl", "kuliah malam"],
            "baa": ["akademik", "baak", "krs", "khs", "ijazah", "transkrip", "surat aktif"],
        }

        # Daftar prodi / topik utama untuk context linking percakapan
        self.daftar_topik_kampus = [
            "teknik informatika", "sistem informasi", "desain komunikasi visual", "dkv",
            "manajemen", "akuntansi", "bisnis digital", "pendidikan kepelatihan olahraga",
            "manajemen informatika", "manajemen bisnis", "beasiswa", "kip kuliah",
            "biaya kuliah", "biaya pendaftaran", "kelas karyawan", "kelas sore",
            "perpustakaan", "fasilitas", "alumni", "asrama", "syarat pendaftaran",
            "jadwal pendaftaran", "lokasi kampus", "kontak pmb",
        ]

        # Stop words / kata abaian percakapan harian
        self.kata_abaian = {
            "yang", "di", "ke", "dari", "dan", "atau", "untuk", "ini", "itu",
            "ada", "apa", "dong", "sih", "lah", "deh", "kok", "kan", "ya", "yah",
            "gimana", "bagaimana", "apakah", "kenapa", "mengapa", "kapan", "dimana",
            "tahu", "tau", "tolong", "bisa", "kasih", "info", "tentang", "mengenai",
        }

        self.muat_dan_indeks_dataset()

    def normalisasi_teks(self, teks: str) -> str:
        """Membersihkan dan menormalisasi string ke huruf kecil tanpa tanda baca berlebih."""
        teks_bersih = re.sub(r"[^\w\s]", " ", str(teks).lower())
        return re.sub(r"\s+", " ", teks_bersih).strip()

    def pisahkan_kata(self, teks: str) -> List[str]:
        """Memecah teks menjadi daftar token kata bermakna (stopword ringan)."""
        kata_kata = self.normalisasi_teks(teks).split()
        return [k for k in kata_kata if k not in self.kata_abaian and len(k) > 1]

    def muat_dan_indeks_dataset(self):
        """Memuat dataset JSON kampus dan membangun indeks inverted index BM25."""
        if not os.path.exists(self.jalur_dataset):
            print(f"[Mesin RAG] Peringatan: File dataset tidak ditemukan di {self.jalur_dataset}")
            return

        with open(self.jalur_dataset, "r", encoding="utf-8") as berkas:
            data_mentah = json.load(berkas)

        self.katalog_dokumen = []
        for item in data_mentah:
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

    # ── Conversational Intent Classifier ──────────────────────────
    def deteksi_intent_percakapan(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Mendeteksi intent percakapan murni (sapaan, identitas, apresiasi, penutup)
        agar dijawab ramah dan manusiawi tanpa memicu pencarian dokumen acak.
        """
        q = self.normalisasi_teks(query)
        if not q:
            return None

        # 1. Sapaan Ramah (Greetings)
        pola_sapaan = [
            r"^(halo|hai|hello|hi|hei|helo)(\s+sela|\s+kak|\s+admin|\s+mbak|\s+kamu)?$",
            r"^(selamat\s+(pagi|siang|sore|malam))(\s+sela)?$",
            r"^(assalam|assalamu\s*alaikum|assalamualaikum)",
            r"^(apa\s*kabar|gimana\s*kabarnya|bagaimana\s*kabarnya)",
            r"^(halo\s+apa\s*kabar|hai\s+apa\s*kabar)",
            r"^(sampurasun|kulonuwun|salam)",
        ]
        for pola in pola_sapaan:
            if re.search(pola, q):
                return {
                    "intent": "sapaan",
                    "jawaban": (
                        "Halo! Selamat datang di Universitas Catur Insan Cendekia (UCIC) Cirebon. "
                        "Saya SELA, asisten virtual dan resepsionis cerdas resmi UCIC. "
                        "Ada yang bisa SELA bantu seputar pendaftaran mahasiswa baru (PMB), program studi, "
                        "biaya kuliah, beasiswa, atau fasilitas kampus?"
                    ),
                    "ditemukan": True,
                }

        # 2. Identitas SELA (Who Are You / Identity)
        pola_identitas = [
            r"^(siapa\s+kamu|kamu\s+siapa|siapakah\s+kamu|kenalan\s+dong)$",
            r"^(apa\s+itu\s+sela|tentang\s+kamu|profil\s+kamu)$",
            r"^(kamu\s+bisa\s+apa|apa\s+saja\s+kemampuan\s+kamu|bisa\s+bantu\s+apa)$",
            r"^kamu\s+(asisten|bot|robot|ai|manusia)",
        ]
        for pola in pola_identitas:
            if re.search(pola, q):
                return {
                    "intent": "identitas",
                    "jawaban": (
                        "Saya SELA (Smart Electronic Learning & Academic Assistant), asisten virtual cerdas resmi "
                        "Universitas Catur Insan Cendekia (UCIC) Cirebon.\n\n"
                        "Saya siap membantu Anda dengan informasi resmi mengenai:\n"
                        "1. Program Studi dan Fakultas (FTI, FEB, FPS)\n"
                        "2. Biaya Kuliah & Skema Pembayaran (Reguler & Kelas Sore)\n"
                        "3. Pendaftaran Mahasiswa Baru (PMB Online/Offline)\n"
                        "4. Program Beasiswa (KIP, Yayasan, Prestasi)\n"
                        "5. Fasilitas Kampus, Lokasi, dan Kontak Resmi UCIC.\n\n"
                        "Ada informasi spesifik yang ingin Anda ketahui?"
                    ),
                    "ditemukan": True,
                }

        # 3. Ucapan Terima Kasih (Gratitude)
        pola_makasih = [
            r"^(terima\s*kasih|makasih|makasi|tengkyu|thank\s*you|thanks|matur\s*nuwun|hatur\s*nuhun)",
            r"^(makasih\s+ya|terima\s*kasih\s+banyak)",
        ]
        for pola in pola_makasih:
            if re.search(pola, q):
                return {
                    "intent": "terima_kasih",
                    "jawaban": (
                        "Sama-sama! Senang sekali bisa membantu Anda. Jika masih ada pertanyaan lain "
                        "seputar kampus UCIC, silakan tanyakan kapan saja ya. Sukses selalu!"
                    ),
                    "ditemukan": True,
                }

        # 4. Penutup / Pamit (Farewell)
        pola_pamit = [
            r"^(sampai\s+jumpa|dadah|bye|good\s*bye|selamat\s+tinggal)",
            r"^(sudah\s+cukup|cukup\s+itu\s+saja|tidak\s+ada\s+lagi)",
        ]
        for pola in pola_pamit:
            if re.search(pola, q):
                return {
                    "intent": "penutup",
                    "jawaban": (
                        "Baik, terima kasih telah berkunjung dan berbincang dengan SELA UCIC. "
                        "Semoga hari Anda menyenangkan dan sukses selalu!"
                    ),
                    "ditemukan": True,
                }

        return None

    # ── Context Linking Percakapan Multi-Turn ─────────────────────
    def ekstrak_konteks_sebelumnya(self, riwayat_obrolan: Optional[List[Dict[str, str]]]) -> str:
        """
        Mengekstrak topik prodi/layanan dari riwayat obrolan terakhir.
        Berguna untuk menghubungkan pertanyaan lanjutan seperti 'biayanya berapa?'
        menjadi 'biaya teknik informatika'.
        """
        if not riwayat_obrolan:
            return ""

        # Periksa 4 pesan terakhir dari riwayat
        for pesan in reversed(riwayat_obrolan[-4:]):
            teks = self.normalisasi_teks(pesan.get("text", "") or pesan.get("content", ""))
            for topik in self.daftar_topik_kampus:
                if topik in teks:
                    return topik
        return ""

    def perkaya_kueri_dengan_konteks(self, query: str, riwayat_obrolan: Optional[List[Dict[str, str]]]) -> str:
        """
        Jika pertanyaan pengguna adalah kalimat lanjutan yang elips (misal: 'biayanya berapa?'),
        gabungkan dengan prodi/topik yang sedang dibicarakan di giliran sebelumnya.
        """
        q = self.normalisasi_teks(query)
        # Cek apakah query sudah menyebut topik spesifik secara eksplisit
        for topik in self.daftar_topik_kampus:
            if topik in q:
                return query

        # Kata-kata indikator pertanyaan lanjutan
        indikator_lanjutan = [
            "biaya", "biayanya", "syarat", "syaratnya", "cara", "caranya",
            "jadwal", "jadwalnya", "kelas sore", "kelas karyawan", "akreditasi",
            "lulusan", "prospek", "gelombang", "pembayaran", "gedung", "dimana",
            "kapan", "berapa", "gimana", "bagaimana", "kalau", "terus", "lalu",
        ]

        apakah_pertanyaan_lanjutan = any(ind in q for ind in indikator_lanjutan)
        if apakah_pertanyaan_lanjutan:
            konteks_sebelumnya = self.ekstrak_konteks_sebelumnya(riwayat_obrolan)
            if konteks_sebelumnya:
                query_diperkaya = f"{konteks_sebelumnya} {query}"
                return query_diperkaya

        return query

    # ── Pencarian & Perluasan BM25 ────────────────────────────────
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

    def cari_relevan(self, query: str, batas_hasil: int = 3) -> List[Dict[str, Any]]:
        """
        Melakukan pencarian BM25 Sparse dengan Semantic Boosting pada judul dan kata kunci.
        Dilengkapi ambang skor minimum yang ketat untuk mencegah kecocokan acak.
        """
        tokens_kueri = self.perluas_query_dengan_sinonim(query)
        if not tokens_kueri or self.total_dokumen == 0:
            return []

        skor_dokumen: Dict[int, float] = {i: 0.0 for i in range(self.total_dokumen)}
        k1 = 1.5
        b = 0.75
        teks_query_bersih = self.normalisasi_teks(query)

        for token in tokens_kueri:
            daftar_dokumen = self.indeks_kata_kunci.get(token, [])
            n_q = len(daftar_dokumen)
            if n_q == 0:
                continue

            idf = math.log(1 + (self.total_dokumen - n_q + 0.5) / (n_q + 0.5))

            for idx_dok in daftar_dokumen:
                dok = self.katalog_dokumen[idx_dok]
                frekuensi_kata = dok["tokens"].count(token)
                panjang_dok = self.panjang_dokumen[idx_dok]

                skor_bm25 = idf * ((frekuensi_kata * (k1 + 1)) /
                                   (frekuensi_kata + k1 * (1 - b + b * (panjang_dok / self.rata_rata_panjang_dokumen))))

                # Bobot ekstra signifikan jika kata kunci ada di judul atau kata kunci dokumen
                judul_norm = self.normalisasi_teks(dok["judul"])
                if token in judul_norm:
                    skor_bm25 += 3.0

                # Exact phrase matching bonus jika kueri pengguna muncul utuh di judul/konten
                if token in [self.normalisasi_teks(k) for k in dok["kata_kunci"]]:
                    skor_bm25 += 2.0

                skor_dokumen[idx_dok] += skor_bm25

        # Bonus kecocokan frasa utuh
        for idx_dok, dok in enumerate(self.katalog_dokumen):
            judul_norm = self.normalisasi_teks(dok["judul"])
            konten_norm = self.normalisasi_teks(dok["konten"])
            if teks_query_bersih and (teks_query_bersih in judul_norm or teks_query_bersih in konten_norm):
                skor_dokumen[idx_dok] += 5.0

        # Urutkan berdasarkan skor tertinggi
        dokumen_terurut = sorted(skor_dokumen.items(), key=lambda x: x[1], reverse=True)
        hasil: List[Dict[str, Any]] = []

        # Ambang batas skor minimum yang dinaikkan agar tidak mencocokkan dokumen sembarangan
        AMBANG_SKOR_MINIMUM = 1.8

        for idx_dok, skor in dokumen_terurut:
            if skor >= AMBANG_SKOR_MINIMUM and len(hasil) < batas_hasil:
                item = self.katalog_dokumen[idx_dok]
                hasil.append({
                    "id": item["id"],
                    "judul": item["judul"],
                    "konten": item["konten"],
                    "kategori": item["kategori"],
                    "skor": round(skor, 3),
                })

        return hasil

    def bangun_konteks_grounding(
        self, query: str, riwayat_obrolan: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Membangun prompt konteks ketat (Grounding Prompt) untuk model LLM.
        Mengembalikan (teks_konteks, daftar_dokumen, apakah_ditemukan).
        """
        # 1. Periksa intent percakapan umum terlebih dahulu
        intent_data = self.deteksi_intent_percakapan(query)
        if intent_data is not None:
            return f"INTENT_PERCAKAPAN:{intent_data['intent']}:{intent_data['jawaban']}", [], True

        # 2. Hubungkan konteks percakapan multi-turn
        kueri_efektif = self.perkaya_kueri_dengan_konteks(query, riwayat_obrolan)
        dokumen_cocok = self.cari_relevan(kueri_efektif, batas_hasil=3)

        if not dokumen_cocok:
            teks_konteks = "INFORMASI_TIDAK_TERSEDIA_DI_DATASET"
            return teks_konteks, [], False

        bagian_konteks = []
        for i, dok in enumerate(dokumen_cocok, 1):
            bagian_konteks.append(f"--- DOKUMEN {i}: {dok['judul']} (Kategori: {dok['kategori']}) ---\n{dok['konten']}")

        teks_konteks = "\n\n".join(bagian_konteks)
        return teks_konteks, dokumen_cocok, True

    def buat_prompt_instruksi_ketat(
        self, query: str, riwayat_obrolan: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Menyusun instruksi bebas halusinasi untuk Qwen/LLM atau ekstraktor fallback.
        Model HANYA diizinkan merespon berbasis fakta dokumen resmi UCIC.
        """
        konteks, dokumen_cocok, ditemukan = self.bangun_konteks_grounding(query, riwayat_obrolan)

        system_prompt = (
            "Kamu adalah SELA, asisten virtual dan resepsionis cerdas resmi Universitas Catur Insan Cendekia (UCIC) Cirebon.\n"
            "Pedoman Menjawab:\n"
            "1. Jawablah dengan ramah, santun, jelas, dan percaya diri seperti resepsionis customer service profesional.\n"
            "2. WAJIB menggunakan informasi HANYA dari DOKUMEN RESMI yang disediakan di bawah.\n"
            "3. DILARANG KERAS mengarang, berhalusinasi, atau menambahkan asumsi di luar isi dokumen.\n"
            "4. Jika informasi spesifik tidak ditemukan di dokumen, sampaikan dengan jujur dan arahkan pengunjung untuk menghubungi Admin PMB/BAA UCIC.\n"
            "5. Berikan jawaban dalam bentuk ringkasan poin yang mudah dibaca dan didengar."
        )

        # Kasus Intent Percakapan Cepat (Sapaan / Identitas / Terima Kasih)
        if konteks.startswith("INTENT_PERCAKAPAN:"):
            parts = konteks.split(":", 2)
            jawaban_langsung = parts[2] if len(parts) > 2 else ""
            prompt_lengkap = (
                f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
                f"<|im_start|>user\n{query}\n<|im_end|>\n"
                f"<|im_start|>assistant\n{jawaban_langsung}\n<|im_end|>"
            )
            return prompt_lengkap

        if not ditemukan:
            prompt_lengkap = (
                f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
                f"<|im_start|>user\n{query}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
                f"Halo! Untuk pertanyaan mengenai '{query}', informasinya saat ini belum tercantum secara spesifik dalam basis data resmi kami. "
                f"Silakan dapat langsung menghubungi Front Desk / Layanan Informasi Kampus UCIC melalui WhatsApp PMB di 0812 1670 0519 atau mengunjungi website resmi di https://pmb.cic.ac.id ya! Ada hal lain yang bisa SELA bantu?"
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
                teks = pesan.get("text", "") or pesan.get("content", "")
                nama_peran = "assistant" if peran == "assistant" else "user"
                prompt_lengkap += f"<|im_start|>{nama_peran}\n{teks}\n<|im_end|>\n"

        prompt_lengkap += f"<|im_start|>user\n{query}\n<|im_end|>\n<|im_start|>assistant\n"
        return prompt_lengkap


if __name__ == "__main__":
    rag = MesinRagOffline()
    uji_kasus = [
        "halo",
        "siapa kamu",
        "Fakultas apa saja yang ada di UCIC?",
        "Berapa biaya kuliah S1 Teknik Informatika?",
        "Lalu syaratnya apa?",
    ]
    riwayat = []
    print("\n" + "=" * 60)
    print("PENGUJIAN MANDIRI MESIN RAG OFFLINE BERBASIS KONTEKS")
    print("=" * 60)
    for q in uji_kasus:
        print(f"\n[USER]: '{q}'")
        konteks, docs, ditemukan = rag.bangun_konteks_grounding(q, riwayat)
        if konteks.startswith("INTENT_PERCAKAPAN:"):
            print(f"[SELA INTENT]: {konteks.split(':', 2)[2]}")
        elif docs:
            print(f"[SELA DOKUMEN]: {docs[0]['judul']} (Skor: {docs[0]['skor']})")
        else:
            print("[SELA]: Dokumen tidak ditemukan.")
        riwayat.append({"role": "user", "text": q})
        if docs:
            riwayat.append({"role": "assistant", "text": docs[0]["konten"][:100]})
