"""
SELA AI Desktop - Retriever Leksikal BM25 + Gerbang Cakupan IDF
================================================================
Pencarian kata kunci cerdas untuk basis pengetahuan resmi UCIC.

Peran dalam arsitektur RAG:
- Jalur UTAMA saat embedder semantik (bge-m3) belum tersedia, sehingga RAG
  tetap presisi tanpa unduhan model besar.
- Penguat PRESISI saat bge-m3 aktif (hybrid: leksikal + semantik).

Mengapa lebih baik daripada pencarian fuzzy murni:
1. BM25 dengan bobot medan: judul dan kata kunci berbobot 3x, isi 1x.
   Dokumen yang topiknya persis akan selalu mengalahkan dokumen yang hanya
   menyinggung sepintas.
2. Pembobotan IDF: kata umum ("kampus", "mahasiswa") tidak mendominasi.
3. Bonus frasa kata kunci: bila frasa kata kunci dokumen muncul utuh di
   pertanyaan, dokumen diberi dorongan kuat.
4. Gerbang cakupan IDF (anti-halusinasi): dokumen hanya lolos bila cukup
   banyak istilah penting pertanyaan yang benar-benar tertulis di dokumen.
   Pertanyaan di luar kampus seperti "resep rendang" atau "siapa presiden"
   gagal di gerbang ini, sehingga SELA menjawab jujur, bukan mengarang.
5. Syarat minimal dua istilah berbeda cocok di SATU dokumen
   (_MIN_COCOK_DISTINCT), agar pertanyaan dua kata tidak lolos hanya karena
   satu kata kebetulan ada di sebuah dokumen.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── Parameter BM25 ────────────────────────────────────────────────────────────
K1 = 1.5
B = 0.75

# Bobot medan: judul & kata kunci jauh lebih menentukan daripada isi panjang.
BOBOT_MEDAN: Dict[str, float] = {
    "judul": 3.0,
    "kata_kunci": 3.0,
    "isi": 1.0,
}

# Ambang cakupan IDF untuk gerbang anti-halusinasi.
# 0,50 berarti setengah bobot istilah penting pertanyaan harus ada di dokumen.
AMBANG_CAKUPAN = 0.50

# Jumlah minimum istilah pertanyaan BERBEDA yang harus cocok di SATU dokumen.
# Gerbang cakupan saja tidak cukup: pada pertanyaan dua kata, satu kecocokan
# kebetulan sudah bernilai cakupan 0,50 sehingga lolos ambang. Kasus nyata:
# "resep rendang" -> koreksi salah ketik memetakan 'resep'->'reset' (ada di
# dokumen layanan CS) dan 'rendang'->'renang' (ada di dokumen kurikulum PKOR);
# masing-masing cakupan 0,50, padahal kedua kata itu ada di dokumen BERBEDA,
# sehingga tidak ada dokumen yang benar-benar membahas pertanyaannya.
# Bila pertanyaan hanya punya satu istilah bermakna, satu kecocokan cukup.
_MIN_COCOK_DISTINCT = 2

# Batas atas IDF untuk istilah yang ADA di korpus. Tanpa batas ini, satu kata
# yang sangat langka (mis. "dibuka" yang hanya muncul di 1 dokumen) bisa
# mendominasi cakupan dan menjatuhkan dokumen yang sebenarnya cocok.
_IDF_MAKS = 3.0

# ── Kata umum (tidak dihitung sebagai istilah penting) ────────────────────────
_STOPWORDS = {
    # kata fungsi umum
    "yang", "dan", "atau", "juga", "dengan", "untuk", "pada", "dalam", "oleh",
    "dari", "ke", "di", "ini", "itu", "ada", "adalah", "akan", "sudah", "telah",
    "belum", "masih", "saja", "aja", "juga", "pun", "nya", "nih", "deh", "kok",
    "kan", "sih", "ya", "yah", "dong", "lah", "kah", "deh", "gitu", "begitu",
    "begini", "sama", "buat", "bisa", "bisakah", "boleh", "tolong", "mohon",
    "silakan", "minta", "coba", "mau", "ingin", "pengen", "butuh", "perlu",
    "tentang", "soal", "mengenai", "seputar", "kasih", "tau", "tahu",
    # kata tanya
    "apa", "apakah", "siapa", "siapakah", "berapa", "berapakah", "kapan",
    "dimana", "kemana", "mana", "bagaimana", "bagaimanakah", "gimana",
    "kenapa", "mengapa", "kok", "apaan", "yang",
    # penanda / pembatas
    "lain", "lainnya", "semua", "seluruh", "setiap", "para", "suatu", "sebuah",
    "satu", "dua", "ada", "kah", "nah", "terus", "lewat", "banget", "banget",
    "loh", "lho", "mah", "atuh", "euy", "sih", "dong", "nih", "deh", "kok",
    "yah", "ya", "aja", "gitu", "kayak", "kaya", "kek", "tuh", "tu",
    # kata ganti
    "saya", "aku", "kamu", "anda", "kita", "kami", "mereka", "dia", "beliau",
    "kalian", "daku", "diriku",
    # sapaan & kesopanan
    "halo", "hai", "hallo", "hello", "hi", "hei", "selamat", "pagi", "siang",
    "sore", "malam", "terima", "makasih", "thanks", "thank", "you", "kak",
    "min", "mbak", "mas", "pak", "bu", "bang", "bapak", "ibu",
    # negasi ringan
    "tidak", "gak", "ga", "nggak", "engga", "bukan", "jangan", "tanpa",
    # Inggris
    "the", "a", "an", "is", "are", "was", "were", "be", "of", "to", "for",
    "in", "on", "at", "by", "with", "and", "or", "what", "who", "whom",
    "whose", "how", "much", "many", "when", "where", "which", "why", "do",
    "does", "did", "can", "could", "should", "would", "i", "you", "me", "my",
    "your", "we", "our", "they", "their", "there", "here", "please", "tell",
    "about", "give", "get", "want", "need", "any", "some", "this", "that",
}

# ── Sinonim ringan (memperluas daya ingat tanpa merusak gerbang cakupan) ──────
_SINONIM: Dict[str, Sequence[str]] = {
    "biaya": ("ukt", "harga", "tarif", "pembayaran", "bayar", "kuliah"),
    "ukt": ("biaya", "harga", "tarif", "pembayaran"),
    "harga": ("biaya", "tarif", "ukt"),
    "uang": ("biaya", "bayar", "pembayaran", "harga", "tarif"),
    "bayar": ("biaya", "pembayaran", "uang", "transfer"),
    "pembayaran": ("biaya", "bayar", "uang"),
    "masuk": ("pendaftaran", "daftar", "kuliah", "masuk"),
    "kuliah": ("biaya", "perkuliahan", "kampus"),
    "dosen": ("pengajar", "guru", "lecturer", "staf pengajar"),
    "pengajar": ("dosen", "mengajar", "ajar"),
    "mengajar": ("pengajar", "ajar", "dosen"),
    "jurusan": ("prodi", "program studi", "programstudi"),
    "prodi": ("jurusan", "program studi"),
    "daftar": ("pendaftaran", "registrasi", "mendaftar", "registrasi ulang"),
    "pendaftaran": ("daftar", "mendaftar", "registrasi", "pmb", "admisi"),
    "mendaftar": ("daftar", "pendaftaran", "registrasi"),
    "dibuka": ("pendaftaran", "jadwal", "daftar"),
    "buka": ("pendaftaran", "jadwal", "daftar"),
    "online": ("daring", "online"),
    "beasiswa": ("kip", "kip-kuliah", "bantuan biaya", "scholarship"),
    "kip": ("beasiswa", "kip-kuliah"),
    "syarat": ("persyaratan", "berkas", "dokumen", "ketentuan"),
    "persyaratan": ("syarat", "berkas", "dokumen"),
    "jadwal": ("waktu", "tanggal", "timeline", "gelombang"),
    "fasilitas": ("sarana", "prasarana", "gedung", "ruang", "lab", "laboratorium"),
    "lokasi": ("alamat", "tempat", "dimana", "kampus"),
    "alamat": ("lokasi", "tempat"),
    "kontak": ("telepon", "whatsapp", "wa", "email", "hubungi", "nomor"),
    "rektor": ("pimpinan", "ketua"),
    "akreditasi": ("peringkat", "akreditas"),
    "kurikulum": ("mata kuliah", "matakuliah", "semester"),
    "kelas": ("perkuliahan", "jadwal kuliah", "kelas karyawan", "kelas sore"),
    "alumni": ("lulusan", "tamatan"),
    "lulusan": ("alumni", "tamatan"),
    "kampus": ("ucic", "universitas", "kampus"),
}

# Awalan & akhiran bahasa Indonesia untuk stemming ringan (menambah varian,
# tidak mengganti token asli sehingga aman).
_AWALAN = (
    "meng", "meny", "mem", "men", "me", "peng", "peny", "pem", "pen", "per",
    "ber", "ter", "ke",
)
_AKHIRAN = ("kannya", "annya", "kan", "an", "nya", "i", "lah", "kah")

_ANGKA = re.compile(r"\d")


def _normalisasi(teks: str) -> str:
    """Huruf kecil, buang aksen, ubah pemisah menjadi spasi."""
    teks = unicodedata.normalize("NFKD", str(teks or ""))
    teks = "".join(c for c in teks if not unicodedata.combining(c))
    teks = teks.lower()
    teks = re.sub(r"[^a-z0-9]+", " ", teks)
    return re.sub(r"\s+", " ", teks).strip()


def _akar(kata: str) -> str:
    """Stemming ringan: buang akhiran lalu awalan yang aman."""
    if len(kata) <= 4:
        return kata
    for akhir in _AKHIRAN:
        if kata.endswith(akhir) and len(kata) - len(akhir) >= 3:
            kata = kata[: -len(akhir)]
            break
    for awal in _AWALAN:
        if kata.startswith(awal) and len(kata) - len(awal) >= 4:
            kata = kata[len(awal):]
            break
    return kata


def _token_dasar(teks: str) -> List[str]:
    """Token bermakna (tanpa kata umum) dari sebuah teks."""
    hasil: List[str] = []
    for t in _normalisasi(teks).split():
        if len(t) < 3 and not _ANGKA.search(t):
            continue
        if t in _STOPWORDS:
            continue
        hasil.append(t)
    return hasil


def _perluas(token: str) -> List[str]:
    """Token + akar + sinonim, untuk memperluas pencocokan BM25."""
    varian = [token]
    akar = _akar(token)
    if akar != token and len(akar) >= 3:
        varian.append(akar)
    for sin in _SINONIM.get(token, ()):  # sinonim frasa dipecah menjadi token
        for bagian in _normalisasi(sin).split():
            if bagian not in _STOPWORDS and len(bagian) >= 3:
                varian.append(bagian)
    # Buang duplikat, pertahankan urutan.
    terlihat = set()
    unik: List[str] = []
    for v in varian:
        if v not in terlihat:
            terlihat.add(v)
            unik.append(v)
    return unik


def _levenshtein_dibatasi(a: str, b: str, batas: int) -> int:
    """Jarak edit dengan pemotongan dini (mengembalikan batas+1 bila jauh)."""
    if abs(len(a) - len(b)) > batas:
        return batas + 1
    sebelumnya = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sekarang = [i]
        for j, cb in enumerate(b, 1):
            sekarang.append(
                min(
                    sebelumnya[j] + 1,
                    sekarang[j - 1] + 1,
                    sebelumnya[j - 1] + (0 if ca == cb else 1),
                )
            )
        sebelumnya = sekarang
    return sebelumnya[-1]


class LexicalIndex:
    """Indeks BM25 + gerbang cakupan IDF untuk sekumpulan dokumen UCIC."""

    def __init__(self, dokumen: Sequence[Dict[str, Any]]) -> None:
        self.dokumen = list(dokumen)
        self.n = len(self.dokumen)

        self._tf: List[Dict[str, float]] = []      # per dokumen: term -> bobot tf
        self._panjang: List[float] = []            # panjang dokumen (berbobot)
        self._df: Dict[str, int] = {}              # term -> jumlah dokumen
        self._frasa: List[List[str]] = []          # per dokumen: frasa kata kunci
        self._idf_asing = math.log(1.0 + (self.n + 0.5) / 0.5)

        self._bangun()

    # ── Pembangunan indeks ────────────────────────────────────────────────────
    @staticmethod
    def _medan(dok: Dict[str, Any]) -> Dict[str, str]:
        kata_kunci = dok.get("keywords") or dok.get("kata_kunci") or []
        if isinstance(kata_kunci, str):
            kata_kunci = [kata_kunci]
        return {
            "judul": str(dok.get("title") or dok.get("judul") or ""),
            "kata_kunci": " ".join(str(k) for k in kata_kunci),
            "isi": str(dok.get("content") or dok.get("teks") or ""),
        }

    def _bangun(self) -> None:
        for dok in self.dokumen:
            medan = self._medan(dok)
            tf: Dict[str, float] = {}
            panjang = 0.0
            for nama_medan, teks in medan.items():
                bobot = BOBOT_MEDAN.get(nama_medan, 1.0)
                for token in _token_dasar(teks):
                    for varian in _perluas(token):
                        tf[varian] = tf.get(varian, 0.0) + bobot
                        panjang += bobot
            self._tf.append(tf)
            self._panjang.append(max(panjang, 1.0))
            for term in tf:
                self._df[term] = self._df.get(term, 0) + 1

            # Frasa kata kunci (>= 2 kata) untuk bonus pencocokan utuh.
            frasa: List[str] = []
            for kk in (dok.get("keywords") or dok.get("kata_kunci") or []):
                frasa_norm = _normalisasi(kk)
                if len(frasa_norm.split()) >= 2:
                    frasa.append(frasa_norm)
            self._frasa.append(frasa)

        total = sum(self._panjang)
        self._rata_panjang = total / self.n if self.n else 1.0

    # ── IDF ───────────────────────────────────────────────────────────────────
    def _idf(self, term: str) -> float:
        df = self._df.get(term)
        if df is None:
            return self._idf_asing  # istilah di luar korpus -> bobot tertinggi
        return min(math.log(1.0 + (self.n - df + 0.5) / (df + 0.5)), _IDF_MAKS)

    # ── Koreksi salah ketik (OOV) ─────────────────────────────────────────────
    def _koreksi_oov(self, token: str) -> str:
        """
        Petakan token yang tidak ada di korpus ke istilah terdekat (jarak edit
        kecil). Menangani salah ketik umum seperti 'persaratan' -> 'persyaratan'
        agar gerbang cakupan tidak menghukum pertanyaan yang sebenarnya valid.
        """
        if token in self._df:
            return token
        batas = 2 if len(token) >= 7 else 1
        terbaik = None
        jarak_terbaik = batas + 1
        for kandidat in self._df:
            if abs(len(kandidat) - len(token)) > batas:
                continue
            jarak = _levenshtein_dibatasi(token, kandidat, batas)
            if jarak < jarak_terbaik:
                terbaik, jarak_terbaik = kandidat, jarak
                if jarak == 0:
                    break
        return terbaik or token

    # ── Pencarian ─────────────────────────────────────────────────────────────
    def cari(self, kueri: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Kembalikan daftar kandidat terurut:
        [{indeks, skor, cakupan, dokumen, cocok}]
        Hanya dokumen yang lolos gerbang cakupan IDF yang dikembalikan.
        """
        if self.n == 0:
            return []
        token_asli = [self._koreksi_oov(t) for t in _token_dasar(kueri)]
        if not token_asli:
            return []

        # Bobot istilah pertanyaan (tanpa sinonim) untuk gerbang cakupan.
        bobot_asli: Dict[str, float] = {}
        for t in token_asli:
            bobot_asli[t] = bobot_asli.get(t, 0.0) + 1.0
        total_bobot = sum(self._idf(t) * w for t, w in bobot_asli.items())
        if total_bobot <= 0:
            return []

        # Istilah yang dipakai BM25 = asli + sinonim/akar (bobot sinonim lebih kecil).
        istilah_bm25: Dict[str, float] = {}
        for t in token_asli:
            istilah_bm25[t] = istilah_bm25.get(t, 0.0) + 1.0
            for v in _perluas(t):
                if v != t:
                    istilah_bm25[v] = max(istilah_bm25.get(v, 0.0), 0.6)

        kueri_norm = _normalisasi(kueri)
        kandidat: List[Dict[str, Any]] = []

        # Berapa istilah berbeda yang wajib cocok di satu dokumen.
        min_cocok = _MIN_COCOK_DISTINCT if len(bobot_asli) >= _MIN_COCOK_DISTINCT else 1

        for i, tf in enumerate(self._tf):
            skor = 0.0
            cocok = 0.0
            jumlah_cocok = 0
            for t, w in bobot_asli.items():
                # Cocokkan juga lewat akar kata (mis. "masuknya" -> "masuk").
                if tf.get(t, 0.0) > 0 or tf.get(_akar(t), 0.0) > 0:
                    cocok += self._idf(t) * w
                    jumlah_cocok += 1
            cakupan = cocok / total_bobot

            if cakupan < AMBANG_CAKUPAN or jumlah_cocok < min_cocok:
                continue

            for term, qw in istilah_bm25.items():
                f = tf.get(term, 0.0)
                if f <= 0:
                    continue
                idf = self._idf(term)
                penyebut = f + K1 * (1.0 - B + B * self._panjang[i] / self._rata_panjang)
                skor += qw * idf * (f * (K1 + 1.0)) / penyebut

            # Bonus frasa: kata kunci dokumen muncul utuh di pertanyaan.
            for frasa in self._frasa[i]:
                if frasa and frasa in kueri_norm:
                    skor += 3.0 * len(frasa.split())

            kandidat.append(
                {
                    "indeks": i,
                    "skor": skor,
                    "cakupan": cakupan,
                    "dokumen": self.dokumen[i],
                    "cocok": [
                        t for t in bobot_asli
                        if tf.get(t, 0.0) > 0 or tf.get(_akar(t), 0.0) > 0
                    ],
                }
            )

        kandidat.sort(key=lambda k: (-k["skor"], -k["cakupan"]))
        return kandidat[:top_k]

    def info(self) -> Dict[str, Any]:
        return {
            "metode": "bm25-lexical",
            "jumlah_dokumen": self.n,
            "jumlah_kosakata": len(self._df),
            "ambang_cakupan": AMBANG_CAKUPAN,
            "min_cocok_distinct": _MIN_COCOK_DISTINCT,
        }


if __name__ == "__main__":
    import json
    import os

    jalur = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "src", "data", "ucic_dataset.json")
    )
    with open(jalur, "r", encoding="utf-8") as f:
        data = json.load(f)
    idx = LexicalIndex(data)
    print("Info:", idx.info())
    for q in [
        "Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?",
        "Bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?",
        "berapa biaya kuliah teknik informatika",
        "resep rendang",
        "siapa presiden indonesia sekarang",
    ]:
        print(f"\n[{q}]")
        for k in idx.cari(q, top_k=3):
            print(f"   - {k['dokumen'].get('id')} | skor {k['skor']:.2f} | cakupan {k['cakupan']:.2f}")
