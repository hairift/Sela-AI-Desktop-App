"""
SELA AI Desktop - Auto-Correct untuk ASR (Speech-to-Text)
Mengoreksi typo dan kesalahan pengucapan hasil transkripsi Whisper.
Menggunakan kamus koreksi kontekstual kampus UCIC + algoritma fuzzy matching.
"""

import re
from typing import List, Dict, Tuple


class KoreksiAsr:
    """
    Mengoreksi hasil transkripsi ASR yang mengandung typo/kesalahan pengucapan.
    """

    def __init__(self):
        # Kamus koreksi: kata_salah -> kata_benar
        # Berdasarkan kesalahan umum pengucapan bahasa Indonesia
        self.kamus_koreksi = {
            # Kesalahan umum pengucapan
            "biyaya": "biaya",
            "biaya2": "biaya",
            "biayanya2": "biayanya",
            "kulia": "kuliah",
            "kuliah": "kuliah",
            "kuliahan": "perkuliahan",
            "universitas2": "universitas",
            "univ": "universitas",
            "kampus2": "kampus",
            "mahasiwa": "mahasiswa",
            "mahaswa": "mahasiswa",
            "mahsiswa": "mahasiswa",
            "maba": "mahasiswa baru",
            "camaba": "calon mahasiswa baru",
            "pendaftar": "pendaftaran",
            "pendaftarn": "pendaftaran",
            "daftaar": "daftar",
            "daftr": "daftar",
            "regstrasi": "registrasi",
            "registrasi2": "registrasi",
            "beasiswa": "beasiswa",
            "beasiswanya": "beasiswa",
            "fasilitas2": "fasilitas",
            "fasilitasnya": "fasilitas",
            "fakultas2": "fakultas",
            "fakultasnya": "fakultas",
            "jurusan2": "jurusan",
            "jurusannya2": "jurusannya",
            "prodi2": "prodi",
            "prodinya2": "prodinya",
            "program2": "program",
            "studie": "studi",
            "study": "studi",
            "tekhnik": "teknik",
            "teknik2": "teknik",
            "informatka": "informatika",
            "informatika2": "informatika",
            "infomatika": "informatika",
            "sistim": "sistem",
            "sistem2": "sistem",
            "informsi": "informasi",
            "informasi2": "informasi",
            "infonya": "informasinya",
            "kontaks": "kontak",
            "kontaknya2": "kontaknya",
            "walikota": "walikota",
            "walikota2": "walikota",
            "walikotanya": "walikota",
            "presiden2": "presiden",
            "presidenn": "presiden",
            "beritanya": "berita",
            "berita2": "berita",
            # Singkatan yang sering diucapkan salah
            "ukti": "ukt",
            "uktnya": "ukt",
            "kp": "kip",
            "kip2": "kip",
            "kipnya": "kip kuliah",
            "krs2": "krs",
            "khs2": "khs",
            "sks2": "sks",
            "uts2": "uts",
            "uas2": "uas",
            # Istilah UCIC yang sering salah transkripsi
            "ucic2": "ucic",
            "ucicnya": "ucic",
            "uicic": "ucic",
            "usic": "ucic",
            "ucik": "ucic",
            "cic2": "cic",
            "cicnya": "cic",
            "cirebon2": "cirebon",
            "cirebonnya": "cirebon",
            "cerbon": "cirebon",
            "cirebonan": "cirebon",
            # Prodi yang sering salah
            "dkf": "dkv",
            "dkb": "dkv",
            "dka": "dkv",
            "dkv2": "dkv",
            "dkvnya": "dkv",
            "desain2": "desain",
            "visual2": "visual",
            "manajemen2": "manajemen",
            "manejemen": "manajemen",
            "manajement": "manajemen",
            "manajemennya": "manajemen",
            "akuntansi2": "akuntansi",
            "akuntansinya2": "akuntansinya",
            "akutansi": "akuntansi",
            "bisnis2": "bisnis",
            "bisnisnya2": "bisnisnya",
            "bisnis digital2": "bisnis digital",
            "digital2": "digital",
            "olahraga2": "olahraga",
            "kepelatihan2": "kepelatihan",
            "pko2": "pko",
            # Sapaan yang salah
            "helo": "halo",
            "hallo": "halo",
            "haloo": "halo",
            "hii": "hai",
            "hay": "hai",
            "hii2": "hai",
            "asalamualaikum": "assalamualaikum",
            "assalamualaikum2": "assalamualaikum",
            "selmat": "selamat",
            "selmatpagi": "selamat pagi",
            # Kata tanya yang salah
            "dimna": "dimana",
            "dmana": "dimana",
            "dmna": "dimana",
            "gimna": "gimana",
            "gmana": "gimana",
            "gmn": "gimana",
            "gmn2": "gimana",
            "brp": "berapa",
            "brapa": "berapa",
            "berapa2": "berapa",
            "kpn": "kapan",
            "kpan": "kapan",
            "kapan2": "kapan",
            "knp": "kenapa",
            "kenpa": "kenapa",
            "kenapa2": "kenapa",
            "ap2": "apa",
            "apah": "apa",
            "apa2": "apa",
            "siapa2": "siapa",
            "siapa3": "siapa",
            # Rektor UCIC
            "candra": "chandra",
            "chandra2": "chandra",
            "lukita2": "lukita",
            "lukitanya": "lukita",
            # Lokasi
            "kesambi2": "kesambi",
            "kesambinya": "kesambi",
            "kesambi3": "kesambi",
            # Lain-lain
            "iya2": "iya",
            "iyah": "iya",
            "iya3": "iya",
            "nggak2": "tidak",
            "gak2": "tidak",
            "ga2": "tidak",
            "ngga": "tidak",
            "tidak2": "tidak",
            "tdk": "tidak",
            "bisa2": "bisa",
            "bisanya2": "bisanya",
            "mau2": "mau",
            "maun": "mau",
            "mau3": "mau",
            "sudh": "sudah",
            "udah2": "sudah",
            "udh": "sudah",
            "sudah2": "sudah",
            "belum2": "belum",
            "blm": "belum",
            "blom": "belum",
            "blum": "belum",
            "ada2": "ada",
            "adanya2": "adanya",
            "gini2": "gini",
            "gitu2": "gitu",
            "gini3": "gini",
            "gitu3": "gitu",
            "dong2": "dong",
            "sih2": "sih",
            "ya2": "ya",
            "ya3": "ya",
            "yah2": "ya",
            "nih2": "nih",
            "nih3": "nih",
            "sih3": "sih",
            "kok2": "kok",
            "tapi2": "tapi",
            "tp": "tapi",
            "tpi": "tapi",
            "karna": "karena",
            "karena2": "karena",
            "krn": "karena",
            "jga": "juga",
            "juga2": "juga",
            "jg": "juga",
            "atau2": "atau",
            "ato": "ataau",
            "dan2": "dan",
            "dgn": "dengan",
            "dengan2": "dengan",
            "utk": "untuk",
            "untuk2": "untuk",
            "buat2": "untuk",
            "ke2": "ke",
            "dari2": "dari",
            "dri": "dari",
            "di2": "di",
            "ke3": "ke",
            "yang2": "yang",
            "yg": "yang",
            "yang3": "yang",
            "itu2": "itu",
            "itu3": "itu",
            "ini2": "ini",
            "ini3": "ini",
            "akan2": "akan",
            "akn": "akan",
            "sangat2": "sangat",
            "sngat": "sangat",
            "terlalu2": "terlalu",
            "terlalu3": "terlalu",
            "lebih2": "lebih",
            "lbih": "lebih",
            "kurang2": "kurang",
            "krang": "kurang",
            # Tambahan: kesalahan umum Whisper untuk bahasa Indonesia
            "selesa": "selesai",
            "selesainya": "selesainya",
            "denger": "dengar",
            "ngomong": "ngomong",
            "bilang": "bilang",
            "jawab": "jawab",
            "tanyain": "tanyakan",
            "nanyain": "nanyakan",
            "jawabnya": "jawabnya",
            "selsi": "selamat",
            "dtng": "datang",
            "dthing": "datang",
            "slmat": "selamat",
            "selmat": "selamat",
            "misi": "misi",
            "visi": "visi",
            "fakultasnya": "fakultasnya",
            "jurusan3": "jurusan",
            "daftarnya": "pendaftaran",
            "daftar2": "daftar",
            "daftar3": "daftar",
            "kampus3": "kampus",
            "kuliah3": "kuliah",
            "informasinya2": "informasinya",
            "kontak2": "kontak",
            "kontak3": "kontak",
            "biaya3": "biaya",
            "biayanya2": "biayanya",
            "biayanya3": "biayanya",
            "beasiswa3": "beasiswa",
            "kip3": "kip",
            "kipnya2": "kip",
            "kipnya3": "kip",
            "reguler2": "reguler",
            "reguler3": "reguler",
            "spp2": "spp",
            "spp3": "spp",
            "ukt2": "ukt",
            "ukt3": "ukt",
            "angsuran2": "angsuran",
            "cicilan2": "cicilan",
            "pembayaran2": "pembayaran",
            "pembayaran3": "pembayaran",
            "gelombang2": "gelombang",
            "gelombang3": "gelombang",
            "gelombangnya": "gelombang",
            "jadwal2": "jadwal",
            "jadwal3": "jadwal",
            "jadwalnya2": "jadwalnya",
            "syarat2": "syarat",
            "syarat3": "syarat",
            "syaratnya2": "syaratnya",
            "persyaratan2": "persyaratan",
            "berkas2": "berkas",
            "berkasnya": "berkas",
            "dokumen2": "dokumen",
            "dokumen3": "dokumen",
            "ijazah2": "ijazah",
            "transkrip2": "transkrip",
            "skl2": "skl",
            "skl3": "skl",
            "ktp2": "ktp",
            "kk2": "kk",
            "akta2": "akta",
            "alumni2": "alumni",
            "lulusan2": "lulusan",
            "lulus2": "lulus",
            "wisuda2": "wisuda",
            "yudisium2": "yudisium",
            "dosen2": "dosen",
            "dosen3": "dosen",
            "rektor2": "rektor",
            "rektor3": "rektor",
            "dekan2": "dekan",
            "dekan3": "dekan",
            "ketua2": "ketua",
            "ketua3": "ketua",
            "direktur2": "direktur",
            "yayasan2": "yayasan",
            "yayasan3": "yayasan",
            "gelar2": "gelar",
            "sarjana2": "sarjana",
            "d32": "d3",
            "s12": "s1",
            "s22": "s2",
            "akreditasi2": "akreditasi",
            "akreditasi3": "akreditasi",
            "banpt2": "banpt",
            "perpustakaan2": "perpustakaan",
            "laboratorium2": "laboratorium",
            "lab2": "lab",
            "lab3": "lab",
            "masjid2": "masjid",
            "kantin2": "kantin",
            "parkir2": "parkir",
            "wifi2": "wifi",
            "asrama2": "asrama",
            "asrama3": "asrama",
            # Istilah pembayaran digital
            "va2": "virtual account",
            "va3": "virtual account",
            "ewallet2": "ewallet",
            "ewallet3": "ewallet",
            "e wallet2": "ewallet",
            "dana2": "dana",
            "ovo2": "ovo",
            "gopay2": "gopay",
            "shopeepay2": "shopeepay",
            "transfer2": "transfer",
            "transfer3": "transfer",
            # Kesalahan Whisper untuk kata tanya
            "giman": "gimana",
            "gimn": "gimana",
            "gmn3": "gimana",
            "bagaimna": "bagaimana",
            "bgaimana": "bagaimana",
            "bgaimna": "bagaimana",
            "dimana2": "dimana",
            "dimana3": "dimana",
            "dmna2": "dimana",
            "mana2": "dimana",
            "kpn2": "kapan",
            "kpn3": "kapan",
            "knp2": "kenapa",
            "knp3": "kenapa",
            "kenpa2": "kenapa",
            "kenpa3": "kenapa",
            "brp2": "berapa",
            "brp3": "berapa",
            "brapa2": "berapa",
            "brapa3": "berapa",
            # Tambahan kata penghubung
            "klo": "kalau",
            "klo2": "kalau",
            "klu": "kalau",
            "klau": "kalau",
            "kalau3": "kalau",
            "kalo2": "kalau",
            "kalo3": "kalau",
            "jga2": "juga",
            "jga3": "juga",
            "jg2": "juga",
            "jg3": "juga",
            "tapi3": "tapi",
            "tp2": "tapi",
            "tpi2": "tapi",
            "tpi3": "tapi",
            "krn2": "karena",
            "krn3": "karena",
            "karna2": "karena",
            "karna3": "karena",
            # Tambahan kata sifat
            "bagus2": "bagus",
            "bagus3": "bagus",
            "bagusnya": "bagus",
            "keren2": "keren",
            "keren3": "keren",
            "mantap2": "mantap",
            "mantap3": "mantap",
            "oke2": "oke",
            "oke3": "oke",
            "ok2": "oke",
            "ok3": "oke",
            "okey": "oke",
            "okae": "oke",
        }

        # Kata-kata yang valid di konteks kampus (jangan dikoreksi)
        self.kata_valid = {
            "kuliah", "kampus", "mahasiswa", "universitas", "fakultas",
            "jurusan", "prodi", "program", "studi", "teknik", "informatika",
            "sistem", "informasi", "beasiswa", "fasilitas", "pendaftaran",
            "registrasi", "biaya", "ukt", "krs", "khs", "sks",
            "uts", "uas", "wisuda", "yudisium", "ipk", "transkrip",
            "ijazah", "skl", "ktp", "kk", "akta",
            "ucic", "cic", "cirebon", "kesambi",
            "fti", "feb", "fps", "dkv", "pko",
            "manajemen", "akuntansi", "bisnis", "digital", "olahraga",
            "kepelatihan", "desain", "visual", "komunikasi",
            "chandra", "lukita", "rektor", "pimpinan",
            "halo", "hai", "selamat", "pagi", "siang", "sore", "malam",
            "terima", "kasih", "makasih", "sama",
            "bisa", "tidak", "sudah", "belum", "ada", "mau",
            "ya", "nih", "sih", "dong", "tapi", "dan", "atau",
            "karena", "juga", "untuk", "dari", "ke", "di",
            "yang", "itu", "ini", "akan", "sangat", "lebih",
            "kurang", "terlalu", "gimana", "bagaimana", "apa",
            "siapa", "dimana", "kapan", "kenapa", "berapa",
            "walikota", "presiden", "berita", "kabar",
            "cara", "daftar", "camaba", "rpl", "spp",
            "gelombang", "karyawan", "kelas", "sore", "malam",
            "syarat", "persyaratan", "berkas", "dokumen",
            "kontak", "telepon", "whatsapp", "email", "hubungi",
            "alamat", "jalan", "gedung", "lokasi",
            "asrama", "perpustakaan", "laboratorium", "lab",
            "wifi", "parkir", "kantin", "masjid",
            "yayasan", "ketua", "direktur", "dekan",
            "gelar", "sarjana", "d3", "s1",
            "pendidikan", "sains", "ekonomi", "teknologi",
            "informasi", "pmb", "kip", "prestasi",
            "angsuran", "cicilan", "transfer", "pembayaran",
            "jadwal", "waktu", "jam", "tanggal", "bulan",
            "tahun", "semester", "ganjil", "genap",
            "lulus", "lulusan", "alumni", "kerja",
            "masuk", "nilai", "grade", "ipk",
            "absensi", "kehadiran", "hadir", "telat", "terlambat", "alpa",
            "cuti", "libur", "ujian", "tugas",
            "skripsi", "sidang", "seminar", "proposal",
            "dosen", "pengajar", "staff", "tendik",
            "him", "hmp", "ukm", "organisasi", "ospek", "pkkmb",
            "kegiatan", "event", "seminar", "workshop",
            "online", "offline", "website", "web", "situs",
            "form", " formulir", "upload", "unduh",
            "akreditasi", "banpt", "mutu", "kualitas",
            "selamat", "datang", "ucapan", "salam",
            "assalamualaikum", "sampai", "jumpa", "dadah", "bye",
        }

        # Pola regex untuk angka yang diucapkan
        self.pola_angka = re.compile(r'\b(nol|satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh|sebelas|dua belas|tiga belas|dua puluh|tiga puluh|lima puluh|seratus|dua ratus|ribu|juta)\b', re.IGNORECASE)

    def koreksi_teks(self, teks: str) -> str:
        """
        Mengoreksi teks hasil ASR:
        1. Hapus pengulangan kata
        2. Koreksi typo berdasarkan kamus
        3. Koreksi huruf kapital di awal kalimat
        """
        if not teks or not teks.strip():
            return teks

        # 1. Normalisasi spasi
        teks = re.sub(r'\s+', ' ', teks.strip())

        # 2. Hapus pengulangan kata yang sama berurutan
        teks = self._hapus_pengulangan_kata(teks)

        # 3. Koreksi typo per kata
        teks = self._koreksi_kata(teks)

        # 4. Kapital di awal kalimat
        teks = self._kapital_awal_kalimat(teks)

        return teks.strip()

    def _hapus_pengulangan_kata(self, teks: str) -> str:
        """Hapus kata yang diulang berurutan (misal "halo halo halo" -> "halo")."""
        kata_list = teks.split()
        hasil = []
        for kata in kata_list:
            # Cek apakah kata sebelumnya sama (case-insensitive)
            if hasil and hasil[-1].lower().rstrip('.,!?') == kata.lower().rstrip('.,!?'):
                # Lewati kata yang berulang
                continue
            hasil.append(kata)
        return ' '.join(hasil)

    def _koreksi_kata(self, teks: str) -> str:
        """Koreksi typo per kata berdasarkan kamus."""
        kata_list = teks.split()
        hasil = []

        for kata in kata_list:
            # Simpan tanda baca di awal/akhir
            prefix = ''
            suffix = ''
            kata_bersih = kata

            # Pisahkan tanda baca
            while kata_bersih and kata_bersih[0] in '.,!?;:()[]{}""\'\'-':
                prefix += kata_bersih[0]
                kata_bersih = kata_bersih[1:]
            while kata_bersih and kata_bersih[-1] in '.,!?;:()[]{}""\'\'-':
                suffix = kata_bersih[-1] + suffix
                kata_bersih = kata_bersih[:-1]

            if not kata_bersih:
                hasil.append(kata)
                continue

            # Cek apakah kata sudah valid
            kata_lower = kata_bersih.lower()
            if kata_lower in self.kata_valid:
                # Tetap pertahankan kapital asli
                hasil.append(prefix + kata_bersih + suffix)
                continue

            # Cek di kamus koreksi
            if kata_lower in self.kamus_koreksi:
                koreksi = self.kamus_koreksi[kata_lower]
                # Pertahankan kapital jika kata asli diawali kapital
                if kata_bersih[0].isupper():
                    koreksi = koreksi[0].upper() + koreksi[1:]
                hasil.append(prefix + koreksi + suffix)
            else:
                # Coba koreksi dengan fuzzy matching (jarak Levenshtein)
                koreksi = self._koreksi_fuzzy(kata_lower)
                if koreksi and koreksi != kata_lower:
                    if kata_bersih[0].isupper():
                        koreksi = koreksi[0].upper() + koreksi[1:]
                    hasil.append(prefix + koreksi + suffix)
                else:
                    hasil.append(prefix + kata_bersih + suffix)

        return ' '.join(hasil)

    def _koreksi_fuzzy(self, kata: str) -> str:
        """
        Koreksi menggunakan fuzzy matching (jarak Levenshtein).
        Jika kata mirip dengan entri di kamus koreksi dalam jarak <= 2,
        kembalikan koreksinya.
        """
        if len(kata) < 3:
            return kata

        # Cari kata di kamus yang paling mirip
        best_match = None
        best_distance = 999

        for kata_salah, kata_benar in self.kamus_koreksi.items():
            # Hanya bandingkan jika panjangnya mirip
            if abs(len(kata_salah) - len(kata)) > 2:
                continue
            distance = self._levenshtein(kata, kata_salah)
            if distance < best_distance and distance <= 2:
                best_distance = distance
                best_match = kata_benar

        return best_match if best_match else kata

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Menghitung jarak Levenshtein antara dua string."""
        m, n = len(a), len(b)
        if m == 0:
            return n
        if n == 0:
            return m

        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,
                    dp[i][j - 1] + 1,
                    dp[i - 1][j - 1] + cost,
                )
        return dp[m][n]

    def _kapital_awal_kalimat(self, teks: str) -> str:
        """Kapital di awal setiap kalimat."""
        if not teks:
            return teks
        # Split berdasarkan tanda akhir kalimat
        kalimat_list = re.split(r'([.!?]+\s*)', teks)
        hasil = []
        for bagian in kalimat_list:
            if bagian and bagian[0].isalpha():
                bagian = bagian[0].upper() + bagian[1:]
            hasil.append(bagian)
        return ''.join(hasil)


if __name__ == "__main__":
    koreksi = KoreksiAsr()

    tes_teks = [
        "halo halo sela siapa biyaya kuliah",
        "saya mau tanya jurusan informatka di ucic",
        "gmn cara daftar maba di kampusnya",
        "brapa uktinya untuk teknik informatika",
        "siapa rektornya chandra lukita",
        "dimna letak kampus ucic di cerbon",
        "iya iya iya saya mau daftar",
        "haloo halo hai apa kabar",
        "biyaya2 kuliahnya brapa",
    ]

    for teks in tes_teks:
        hasil = koreksi.koreksi_teks(teks)
        print(f"ASL: '{teks}'")
        print(f"KRS: '{hasil}'")
        print()
