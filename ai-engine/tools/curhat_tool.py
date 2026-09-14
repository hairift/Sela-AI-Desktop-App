"""
SELA AI Desktop - Alat Mode Curhat (Empatik)
============================================
Mendeteksi keluh kesah, kebingungan, atau kekhawatiran pengguna dan menyiapkan
respons yang hangat, memvalidasi perasaan lebih dahulu, lalu menawarkan
dukungan yang relevan dengan kampus (beasiswa, keringanan biaya, kelas sore,
layanan konseling).

Respons di sini adalah jaring pengaman: bila LLM siap, catatan emosional
dikirim ke prompt CURHAT agar jawaban tetap personal. Bila LLM belum siap,
respons baku di bawah ini dipakai langsung.
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional

_POLA_CURHAT = [
    r"(bingung|ragu|takut|khawatir|cemas|gelisah|stress|stres|capek|lelah|putus\s+asa)",
    r"(bingung\s+(milih|memilih|pilih).*(jurusan|fakultas|prodi|kuliah))",
    r"(ragu.*(diterima|masuk|daftar|mendaftar))",
    r"(tidak\s+(yakin|percaya\s+diri).*(diri|kuliah|mampu))",
    r"(mau\s+nanya.*tapi.*malu)",
    r"(galau|sedih|kesel|nyesel|kecewa|frustasi)",
    r"(cerita|curhat|keluh|keluhan)",
    r"(orang\s+tua.*(marah|ngotak|tidak\s+setuju|nggak\s+setuju|kurang\s+setuju))",
    r"(biaya.*mahal.*keluarga|biaya.*berat|tidak\s+mampu.*biaya)",
    r"(kerja\s+sambil\s+kuliah|kuliah\s+sambil\s+kerja)",
    r"(putus\s+kuliah|drop\s+out|nyerah|menyerah)",
    r"(lagi\s+sedih|lagi\s+galau|lagi\s+stress|lagi\s+stres)",
    r"(negatif|dipandang\s+sebelah\s+mata|dihina|diremehkan|dinilai)",
    r"(kesepian|sepi|sendirian|tidak\s+punya\s+teman)",
    r"(motivasi|semangat|semangatin|beri\s+semangat)",
    r"(patah\s+hati|patah\s+semangat|gagal\s+tes|gagal\s+masuk|ditolak)",
    r"(takut\s+gagal|khawatir\s+gagal|berat\s+banget)",
    r"(mau\s+nyerah|capek\s+banget|lelah\s+banget|penat)",
]

_POLA_TIPS = [
    r"(gimana|bagaimana|caranya|cara)\s+.*(belajar|fokus|rajin|semangat|malas|lulus|ipk|nilai|manajemen\s+waktu|atur\s+waktu)",
    r"(belajar\s+(efektif|efisien)|fokus\s+belajar|rajin\s+belajar|cara\s+belajar)",
    r"(tips|motivasi\s+tips|cara\s+(motivasi|semangat|rajin))",
    r"(gimana\s+cara\s+(tidak\s+malas|fokus\s+kuliah|manajemen\s+waktu))",
    r"(jauhi\s+(gangguan|distraksi|distaksi|hp|sosmed|media\s+sosial))",
    r"(gimana\s+caranya\s+(lulus|lancar|nilai\s+bagus|ipk\s+tinggi))",
    r"(tips\s+masuk\s+kuliah|tips\s+kuliah|tips\s+maba)",
]

_PEMBUKA = [
    "SELA dengar keluh kesahmu.",
    "Aku paham perasaanmu saat ini.",
    "Wajar banget kalau kamu merasa begitu.",
    "Terima kasih sudah berbagi ke SELA.",
    "Aku di sini buat kamu.",
]
_ISI = (
    "Setiap orang punya jalan masing-masing, dan kamu tidak sendirian dalam merasakan ini. "
    "Kalau boleh SELA tahu, kamu sebenarnya tertarik dengan bidang apa? "
    "Soal biaya, UCIC punya beasiswa KIP Kuliah dan opsi kelas sore untuk yang ingin kerja sambil kuliah."
)
_PENUTUP = [
    "Yang penting jangan menyerah ya. Coba ceritakan lebih detail, mungkin SELA bisa bantu.",
    "Kamu hebat sudah berani cerita. Cerita lagi dong, SELA simak.",
    "Jangan ragu buat terus cerita. SELA di sini buat kamu kok.",
    "Sekarang atau nanti, SELA tetap siap dengar kamu. Semangat ya!",
]


class CurhatTool:
    """Detektor dan penyusun respons mode curhat."""

    @staticmethod
    def _norm(teks: str) -> str:
        return re.sub(r"\s+", " ", str(teks).lower()).strip()

    def deteksi(self, kueri: str) -> Optional[Dict[str, Any]]:
        """Kembalikan {intent, catatan} bila pesan bernuansa curhat."""
        q = self._norm(kueri)
        if not q:
            return None
        for pola in _POLA_CURHAT:
            if re.search(pola, q):
                return {"intent": "curhat", "catatan": q[:200]}
        for pola in _POLA_TIPS:
            if re.search(pola, q):
                return {"intent": "tips", "catatan": q[:200]}
        return None

    def jawab(self, kueri: str, nama_user: Optional[str] = None) -> str:
        """Respons empatik cadangan bila LLM belum siap."""
        sapa = f"{nama_user}, " if nama_user else ""
        q = self._norm(kueri)
        if any(re.search(p, q) for p in _POLA_TIPS):
            return (
                f"{sapa}ini beberapa tips dari SELA. "
                "Pertama, buat jadwal harian yang seimbang antara belajar, istirahat, dan hiburan. "
                "Kedua, pakai teknik Pomodoro dua puluh lima menit fokus lalu lima menit istirahat. "
                "Ketiga, matikan notifikasi saat belajar dan tidur cukup tujuh sampai delapan jam. "
                "Kalau kamu mahasiswa UCIC, manfaatkan juga laboratorium dan perpustakaan kampus ya."
            )
        return f"{sapa}{random.choice(_PEMBUKA)} {_ISI} {random.choice(_PENUTUP)}"

    def info(self) -> Dict[str, Any]:
        return {"pola_curhat": len(_POLA_CURHAT), "pola_tips": len(_POLA_TIPS)}


_instance: Optional[CurhatTool] = None


def dapatkan_curhat_tool() -> CurhatTool:
    """Ambil instansi CurhatTool."""
    global _instance
    if _instance is None:
        _instance = CurhatTool()
    return _instance


if __name__ == "__main__":
    alat = dapatkan_curhat_tool()
    for t in ["aku bingung milih jurusan", "gimana cara biar fokus belajar", "biaya kuliah"]:
        print(f"'{t}' -> {alat.deteksi(t)}")
