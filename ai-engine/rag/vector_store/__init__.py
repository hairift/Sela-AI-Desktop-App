"""
SELA AI Desktop - Vector Store (FAISS, dengan cadangan NumPy)
=============================================================
Jalur utama: faiss.IndexFlatIP (kemiripan kosinus pada vektor ternormalisasi).
Jalur cadangan: pencarian brute-force NumPy bila faiss-cpu belum terpasang,
sehingga RAG tetap berfungsi offline.

Indeks disimpan di rag/vector_store/faiss_index/ sebagai:
- index.faiss  (bila faiss tersedia) atau vectors.npy (cadangan)
- meta.json    (metadata chunk, urutannya sama dengan vektor)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


class VectorStore:
    """Penyimpan vektor sederhana yang mendukung FAISS maupun NumPy."""

    def __init__(self, dimensi: int, direktori: Optional[str] = None) -> None:
        self.dimensi = int(dimensi)
        if direktori is None:
            direktori = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faiss_index")
        self.direktori = direktori
        self.metadatas: List[Dict[str, Any]] = []
        self._index = None
        self._vektor = None
        self.metode = "numpy"
        self._siapkan_index()

    # ── Inisialisasi ──────────────────────────────────────────────────────────
    def _siapkan_index(self) -> None:
        try:
            import faiss  # type: ignore

            self._faiss = faiss
            self._index = faiss.IndexFlatIP(self.dimensi)
            self.metode = "faiss"
        except Exception:
            self._faiss = None
            self.metode = "numpy"

    # ── Penambahan & pencarian ────────────────────────────────────────────────
    def tambah(self, vektor: "Any", metadatas: List[Dict[str, Any]]) -> None:
        import numpy as np

        arr = np.asarray(vektor, dtype="float32")
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.dimensi:
            self.dimensi = arr.shape[1]
            self._siapkan_index()
        if self._faiss is not None:
            self._index.add(arr)
        else:
            self._vektor = arr if self._vektor is None else np.vstack([self._vektor, arr])
        self.metadatas.extend(metadatas)

    def cari(self, vektor: "Any", top_k: int = 3) -> List[Tuple[float, Dict[str, Any]]]:
        import numpy as np

        if not self.metadatas:
            return []
        kueri = np.asarray(vektor, dtype="float32")
        if kueri.ndim == 1:
            kueri = kueri.reshape(1, -1)

        # Batasi k oleh jumlah metadata DAN jumlah vektor yang benar-benar ada.
        # Bila keduanya tidak sinkron (mis. meta.json terpotong), pencarian harus
        # tetap aman alih-alih melempar IndexError.
        if self._faiss is not None and self._index is not None and self._index.ntotal > 0:
            k = min(top_k, len(self.metadatas), int(self._index.ntotal))
            if k <= 0:
                return []
            skor, idx = self._index.search(kueri, k)
            pasangan = [
                (float(skor[0][i]), self.metadatas[int(idx[0][i])])
                for i in range(k)
                if 0 <= int(idx[0][i]) < len(self.metadatas)
            ]
        else:
            if self._vektor is None or self._vektor.shape[0] == 0:
                return []
            # Vektor ternormalisasi -> dot product = kemiripan kosinus.
            # Iterasi menurut peringkat lalu LEWATI indeks yang di luar jangkauan
            # metadata: indeks baris vektor harus selalu < len(metadatas) agar
            # pencarian tetap aman saat kedua berkas tidak sinkron.
            skor_all = self._vektor @ kueri[0]
            pasangan = []
            for i in np.argsort(-skor_all):
                if len(pasangan) >= top_k:
                    break
                if int(i) >= len(self.metadatas):
                    continue
                pasangan.append((float(skor_all[i]), self.metadatas[int(i)]))
        return pasangan

    @property
    def ukuran(self) -> int:
        return len(self.metadatas)

    # ── Persistensi ───────────────────────────────────────────────────────────
    @staticmethod
    def _hapus_jika_ada(jalur: str) -> None:
        try:
            os.remove(jalur)
        except OSError:
            pass

    def simpan(self) -> None:
        import numpy as np

        os.makedirs(self.direktori, exist_ok=True)
        jalur_faiss = os.path.join(self.direktori, "index.faiss")
        jalur_npy = os.path.join(self.direktori, "vectors.npy")

        # Hanya SATU representasi yang boleh ada, agar tidak bertentangan dengan
        # meta.json. Tanpa ini, sisa berkas dari backend lain (mis. vectors.npy
        # berdimensi 512 dari masa faiss belum terpasang) bisa ikut termuat
        # bersama meta berdimensi 1024 dan membuat jalur semantik mati senyap.
        if self._faiss is not None and self._index is not None:
            self._faiss.write_index(self._index, jalur_faiss)
            self._hapus_jika_ada(jalur_npy)
        if self._vektor is not None:
            np.save(jalur_npy, self._vektor)
            self._hapus_jika_ada(jalur_faiss)

        with open(os.path.join(self.direktori, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"dimensi": self.dimensi, "metode": self.metode, "metadatas": self.metadatas},
                f,
                ensure_ascii=False,
            )

    def muat(self) -> bool:
        import numpy as np

        jalur_meta = os.path.join(self.direktori, "meta.json")
        if not os.path.exists(jalur_meta):
            return False
        try:
            with open(jalur_meta, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.dimensi = int(data.get("dimensi", self.dimensi))
            self.metadatas = data.get("metadatas", [])
            self._siapkan_index()

            jalur_faiss = os.path.join(self.direktori, "index.faiss")
            jalur_npy = os.path.join(self.direktori, "vectors.npy")
            # Catat jumlah vektor dari representasi yang BENAR-BENAR dimuat
            # (`_siapkan_index` selalu membuat indeks FAISS kosong, jadi `_index`
            # tidak boleh dijadikan patokan hanya karena tidak None).
            n_vektor = 0
            if self._faiss is not None and os.path.exists(jalur_faiss):
                self._index = self._faiss.read_index(jalur_faiss)
                if self._index.d != self.dimensi:
                    print(
                        f"[VectorStore] Indeks FAISS ({self._index.d} dim) tidak cocok dengan "
                        f"meta.json ({self.dimensi} dim); indeks diabaikan agar dibangun ulang."
                    )
                    return False
                n_vektor = int(self._index.ntotal)
            elif os.path.exists(jalur_npy):
                self._vektor = np.load(jalur_npy)
                if self._vektor.ndim != 2 or self._vektor.shape[1] != self.dimensi:
                    print(
                        f"[VectorStore] vectors.npy tidak cocok dengan meta.json "
                        f"({self.dimensi} dim); indeks diabaikan agar dibangun ulang."
                    )
                    return False
                n_vektor = int(self._vektor.shape[0])

            # Jumlah metadata wajib sama dengan jumlah vektor. Bila tidak, indeks
            # tidak konsisten (mis. meta.json terpotong saat aplikasi dimatikan di
            # tengah simpan) -> tolak agar dibangun ulang, jangan dipakai.
            if n_vektor != len(self.metadatas):
                print(
                    f"[VectorStore] Jumlah vektor ({n_vektor}) tidak sama dengan metadata "
                    f"({len(self.metadatas)}); indeks diabaikan agar dibangun ulang."
                )
                return False
            return bool(self.metadatas)
        except Exception as galat:
            print(f"[VectorStore] Gagal memuat indeks: {galat}")
            return False

    def info(self) -> Dict[str, Any]:
        return {"metode": self.metode, "dimensi": self.dimensi, "jumlah": self.ukuran}


if __name__ == "__main__":
    import numpy as np

    vs = VectorStore(dimensi=4)
    vs.tambah(np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype="float32"),
              [{"judul": "A"}, {"judul": "B"}])
    print("Info:", vs.info())
    print("Cari:", vs.cari(np.array([0.9, 0.1, 0, 0], dtype="float32"), top_k=2))
