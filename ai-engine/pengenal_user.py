"""
SELA AI Desktop - Pengenal & Memori User
Mengingat nama user dan konteks percakapan pribadi.
Jika user belum dikenal, AI akan menanyakan namanya.
Setelah user menyebutkan namanya, AI mengingatnya untuk sesi berikutnya.
"""

import os
import re
import json
from typing import Optional, Dict, Any


class PengenalUser:
    """
    Mengelola identitas user: nama, minat jurusan/fakultas, riwayat curhat.
    Data disimpan ke file JSON lokal agar persisten antar sesi.
    """

    def __init__(self):
        self.direktori_induk = os.path.dirname(os.path.abspath(__file__))
        self.jalur_data_user = os.path.join(self.direktori_induk, "data_user.json")
        self.data_user: Dict[str, Any] = {}
        self.nama_user: Optional[str] = None
        self.minat_user: list = []
        self.riwayat_curhat: list = []
        self._muat_data()

    def _muat_data(self):
        """Memuat data user dari file JSON lokal."""
        if os.path.exists(self.jalur_data_user):
            try:
                with open(self.jalur_data_user, "r", encoding="utf-8") as f:
                    self.data_user = json.load(f)
                self.nama_user = self.data_user.get("nama_user")
                self.minat_user = self.data_user.get("minat_user", [])
                self.riwayat_curhat = self.data_user.get("riwayat_curhat", [])
            except Exception as e:
                print(f"[Pengenal User] Gagal memuat data: {e}")
                self.data_user = {}

    def _simpan_data(self):
        """Menyimpan data user ke file JSON lokal."""
        try:
            self.data_user["nama_user"] = self.nama_user
            self.data_user["minat_user"] = self.minat_user
            self.data_user["riwayat_curhat"] = self.riwayat_curhat
            with open(self.jalur_data_user, "w", encoding="utf-8") as f:
                json.dump(self.data_user, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Pengenal User] Gagal menyimpan data: {e}")

    def apakah_dikenal(self) -> bool:
        """Cek apakah nama user sudah diketahui."""
        return self.nama_user is not None and len(self.nama_user) > 0

    def ekstrak_nama_dari_pesan(self, pesan: str) -> Optional[str]:
        """
        Mendeteksi apakah user sedang menyebutkan namanya.
        Pola yang dikenali:
        - "nama saya Andi"
        - "aku Andi"
        - "saya Rina"
        - "namaku Budi"
        - "Aku dipanggil Sari"
        - "panggil aku Joko"
        - "kenalan, saya Andi"
        - "aku dari kelas X, nama ku Y"
        """
        if not pesan:
            return None

        teks = pesan.strip()

        # Pola untuk mendeteksi pengenalan diri
        pola_nama = [
            r"(?:nama\s+saya|namaku|nama\s+aku|namanya)\s+([A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20}(?:\s+[A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20})?)",
            r"(?:saya|aku|beta|saya\s+ini)\s+(?:adalah|itu|dipanggil)\s+([A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20}(?:\s+[A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20})?)",
            r"(?:panggil\s+(?:saya|aku|beta))\s+([A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20}(?:\s+[A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20})?)",
            r"(?:saya|aku)\s+([A-ZÀ-Ý][a-z]{2,15}(?:\s+[A-ZÀ-Ý][a-z]{2,15})?)(?:\s+(?:sih|ya|dong|nih))",
            r"(?:boleh\s+kenalan|kenalan\s+dong|perkenalkan|halo\s+saya|hai\s+saya|halo\s+nama\s+saya|hai\s+nama\s+saya)(?:.*?)([A-ZÀ-Ý][a-z]{2,15}(?:\s+[A-ZÀ-Ý][a-z]{2,15})?)",
            # Pola tambahan: "saya [Nama] dari..." atau "saya [Nama] nih"
            r"(?:saya|aku)\s+([A-ZÀ-Ý][a-z]{2,15}(?:\s+[A-ZÀ-Ý][a-z]{2,15})?)\s+(?:dari|nih|dong|sih)",
            # Pola: "sebut saja [Nama]"
            r"(?:sebut\s+saja|panggil\s+saja)\s+([A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20}(?:\s+[A-ZÀ-Ýa-z][a-zA-ZÀ-Ý]{1,20})?)",
        ]

        for pola in pola_nama:
            hasil = re.search(pola, teks)
            if hasil:
                nama = hasil.group(1).strip()
                # Filter kata yang bukan nama
                kata_terlarang = {
                    "sela", "tidak", "ingin", "mau", "tidak", "saja",
                    "belum", "sudah", "kalau", "jika", "yang", "ini",
                    "itu", "ada", "bukan", "ya", "dong", "sih", "nih",
                    "tapi", "dan", "atau", "karena", "sekarang", "nanti",
                    "kuliah", "kampus", "ucic", "cirebon", "mahasiswa",
                    "daftar", "pendaftaran", "biaya", "jurusan",
                }
                if nama.lower() not in kata_terlarang and len(nama) >= 2:
                    return nama

        return None

    def deteksi_kebutuhan_nama(self, pesan: str) -> bool:
        """
        Mendeteksi apakah user sedang menanyakan nama SELA atau menyebut identitasnya sendiri.
        Jika user hanya bertanya "siapa kamu" tanpa menyebutkan namanya, dan user belum dikenal,
        maka setelah menjawab, SELA harus menanyakan nama user.
        """
        if self.apakah_dikenal():
            return False

        teks = pesan.lower().strip()
        # Jika user baru memulai percakapan dan belum menyebutkan namanya
        pola_sapaan = [
            r"^(halo|hai|hello|hi|hei|helo)",
            r"^selamat\s+(pagi|siang|sore|malam)",
            r"^assalam",
            r"^(apa\s+kabar|gimana\s+kabarnya)",
        ]
        for pola in pola_sapaan:
            if re.search(pola, teks):
                return True

        # Jika user bertanya tentang SELA
        pola_tanya_sela = [
            r"siapa\s+kamu",
            r"kamu\s+siapa",
            r"kamu\s+bisa\s+apa",
            r"apa\s+itu\s+sela",
        ]
        for pola in pola_tanya_sela:
            if re.search(pola, teks):
                return True

        return False

    def simpan_nama(self, nama: str):
        """Menyimpan nama user."""
        self.nama_user = nama.strip()
        self._simpan_data()
        print(f"[Pengenal User] Nama user disimpan: {self.nama_user}")

    def simpan_minat(self, minat: str):
        """Menyimpan minat/jurusan yang diminati user."""
        if minat and minat not in self.minat_user:
            self.minat_user.append(minat)
            self._simpan_data()

    def simpan_curhat(self, curhat: str):
        """Menyimpan riwayat curhat user."""
        if curhat:
            self.riwayat_curhat.append({
                "teks": curhat[:500],
                "status": "baru"
            })
            if len(self.riwayat_curhat) > 20:
                self.riwayat_curhat = self.riwayat_curhat[-20:]
            self._simpan_data()

    def dapatkan_konteks_user(self) -> str:
        """Mengembalikan konteks user untuk ditambahkan ke prompt LLM."""
        konteks = []
        if self.nama_user:
            konteks.append(f"Nama user yang sedang diajak bicara: {self.nama_user}. "
                          f"Gunakan namanya secara natural dalam percakapan (tidak setiap kalimat, cukup sesekali).")
        if self.minat_user:
            konteks.append(f"Minat/jurusan yang sedang dipertimbangkan user: {', '.join(self.minat_user[-3:])}")
        if self.riwayat_curhat:
            curhat_terakhir = self.riwayat_curhat[-1]
            konteks.append(f"User pernah bercerita tentang: {curhat_terakhir['teks'][:200]}")

        return "\n".join(konteks) if konteks else ""

    def reset(self):
        """Reset semua data user (untuk debugging/testing)."""
        self.nama_user = None
        self.minat_user = []
        self.riwayat_curhat = []
        self.data_user = {}
        self._simpan_data()


if __name__ == "__main__":
    pu = PengenalUser()
    print(f"User dikenal: {pu.apakah_dikenal()}")
    print(f"Nama: {pu.nama_user}")

    # Test ekstraksi nama
    tes_pesan = [
        "Halo, nama saya Andi",
        "panggil aku Rina",
        "aku Budi sih",
        "namaku Sari",
        "perkenalkan, saya Joko",
    ]
    for pesan in tes_pesan:
        nama = pu.ekstrak_nama_dari_pesan(pesan)
        print(f"'{pesan}' -> nama: {nama}")
