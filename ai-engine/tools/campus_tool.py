"""
SELA AI Desktop - Alat Informasi Kampus (RAG UCIC)
==================================================
Membungkus RagEngine vektor dan menambahkan deteksi niat percakapan ringan
(sapaan, identitas, terima kasih, penutup). Niat curhat ditangani curhat_tool.

Jawaban kampus selalu berasal dari dokumen resmi; bila tidak ada yang lolos
ambang kemiripan, alat ini melaporkan "tidak ditemukan" agar server meminta
LLM menjawab jujur alih-alih mengarang.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from rag import RagEngine

# Pola niat percakapan (tanpa perlu LLM, agar respons instan).
_POLA = {
    "sapaan": [
        r"^(halo|hai|hello|hi|hei|helo)(\s+(sela|kak|admin|mbak|kamu))?$",
        r"^selamat\s+(pagi|siang|sore|malam)(\s+sela)?$",
        r"^(assalam|assalamu\s*alaikum|assalamualaikum)",
        r"^(apa\s*kabar|gimana\s*kabarnya|bagaimana\s*kabarnya)",
        r"^(sampurasun|kulonuwun|salam)$",
    ],
    "identitas": [
        r"^(siapa\s+kamu|kamu\s+siapa|siapakah\s+kamu|kenalan\s+dong)$",
        r"^(apa\s+itu\s+sela|tentang\s+kamu|profil\s+kamu)$",
        r"^(kamu\s+bisa\s+apa|apa\s+saja\s+kemampuan\s+kamu|bisa\s+bantu\s+apa)$",
        r"^kamu\s+(asisten|bot|robot|ai|manusia)",
    ],
    "terima_kasih": [
        r"^(terima\s*kasih|makasih|makasi|tengkyu|thank\s*you|thanks|matur\s*nuwun|hatur\s*nuhun)",
        r"^(makasih\s+ya|terima\s*kasih\s+banyak)",
    ],
    "penutup": [
        r"^(sampai\s+jumpa|dadah|bye|good\s*bye|selamat\s+tinggal)",
        r"^(sudah\s+cukup|cukup\s+itu\s+saja|tidak\s+ada\s+lagi)",
    ],
}

_JAWABAN_INTENT = {
    "sapaan": (
        "Halo! Selamat datang di Universitas Catur Insan Cendekia Cirebon. "
        "Saya SELA, asisten virtual resmi UCIC. Ada yang bisa SELA bantu soal pendaftaran, "
        "program studi, biaya kuliah, beasiswa, atau fasilitas kampus?"
    ),
    "identitas": (
        "Saya SELA, asisten virtual dan resepsionis cerdas resmi Universitas Catur Insan Cendekia "
        "Cirebon. SELA siap membantu informasi program studi dan fakultas, biaya kuliah, "
        "pendaftaran mahasiswa baru, beasiswa, fasilitas, lokasi, dan kontak resmi UCIC. "
        "Ada informasi yang ingin kamu ketahui?"
    ),
    "terima_kasih": (
        "Sama-sama! Senang sekali bisa membantu. Kalau masih ada pertanyaan seputar kampus UCIC, "
        "silakan tanyakan kapan saja ya. Sukses selalu!"
    ),
    "penutup": (
        "Baik, terima kasih sudah berbincang dengan SELA UCIC. "
        "Semoga harimu menyenangkan dan sukses selalu!"
    ),
}


class CampusTool:
    """Alat pencarian informasi resmi UCIC berbasis RAG vektor."""

    def __init__(self, rag: Optional[RagEngine] = None) -> None:
        self.rag = rag or RagEngine()

    # ── Niat percakapan ───────────────────────────────────────────────────────
    @staticmethod
    def _norm(teks: str) -> str:
        return re.sub(r"\s+", " ", str(teks).lower()).strip()

    def deteksi_intent(self, kueri: str) -> Optional[Dict[str, Any]]:
        """Kenali sapaan/identitas/terima kasih/penutup (respons instan)."""
        q = self._norm(kueri)
        if not q:
            return None
        for intent, pola_list in _POLA.items():
            for pola in pola_list:
                if re.search(pola, q):
                    return {"intent": intent, "jawaban": _JAWABAN_INTENT[intent]}
        return None

    # ── Pencarian kampus ──────────────────────────────────────────────────────
    def cari(
        self, kueri: str, riwayat: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """Kembalikan (konteks, dokumen, ditemukan) untuk pertanyaan kampus."""
        return self.rag.bangun_konteks(kueri, riwayat)

    @property
    def total_dokumen(self) -> int:
        return self.rag.total_dokumen

    @property
    def total_chunk(self) -> int:
        return self.rag.total_chunk

    def info(self) -> Dict[str, Any]:
        return self.rag.info()


_instance: Optional[CampusTool] = None


def dapatkan_campus_tool() -> CampusTool:
    """Ambil instansi CampusTool (dimuat sekali agar indeks tidak dibangun ulang)."""
    global _instance
    if _instance is None:
        _instance = CampusTool()
    return _instance


if __name__ == "__main__":
    alat = dapatkan_campus_tool()
    print("Info:", alat.info())
    for q in ["halo", "siapa kamu", "biaya kuliah dkv"]:
        intent = alat.deteksi_intent(q)
        if intent:
            print(f"[{q}] intent={intent['intent']}")
        else:
            _, docs, ada = alat.cari(q)
            print(f"[{q}] ditemukan={ada} -> {[d['judul'] for d in docs]}")
