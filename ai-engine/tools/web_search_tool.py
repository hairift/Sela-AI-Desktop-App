"""
SELA AI Desktop - Alat Pencarian Web Real-Time (Gratis)
=======================================================
Menjawab pertanyaan terkini di luar data kampus, misalnya pejabat yang sedang
menjabat, berita, cuaca, atau harga.

Dua jalur:
1. duckduckgo-search (paket `duckduckgo_search`) bila terpasang.
2. Cadangan: pengambilan HTML DuckDuckGo memakai urllib (tanpa dependensi).

Pelengkap: Wikipedia API dan Wikidata (untuk pemegang jabatan terstruktur).
Semuanya gratis, tanpa API key.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class WebSearchTool:
    """Pencarian web gratis berbasis DuckDuckGo + Wikipedia + Wikidata."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    POLA_REALTIME = [
        r"presiden\s+(indonesia|sekarang|saat\s+ini)",
        r"walikota\s+(cirebon|sekarang|saat\s+ini)",
        r"berita\s+(terbaru|sekarang|hari\s+ini|cirebon)",
        r"kabar\s+(terbaru|terkini|hari\s+ini)",
        r"cuaca\s+(hari\s+ini|sekarang|cirebon)",
        r"harga\s+(saat\s+ini|sekarang|terbaru)",
        r"jadwal\s+(terbaru|terkini|sekarang)",
        r"hasil\s+(pertandingan|skor|bola)",
        r"trending\s+topic",
        r"apa\s+yang\s+sedang\s+terjadi",
        r"peristiwa\s+(terbaru|terkini)",
    ]
    KATA_KUNCI_REALTIME = (
        "siapa presiden", "walikota cirebon", "berita terbaru", "kabar terkini",
        "apa yang terjadi", "peristiwa terbaru", "hari ini", "saat ini", "sekarang",
    )

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self._ddgs = None
        try:
            from duckduckgo_search import DDGS  # type: ignore

            self._ddgs = DDGS
            print("[WebSearch] duckduckgo-search aktif.")
        except Exception:
            print("[WebSearch] duckduckgo-search tidak ada; memakai scraper HTML urllib.")

    # ── Deteksi kebutuhan ─────────────────────────────────────────────────────
    def perlu_web_search(self, kueri: str) -> bool:
        teks = (kueri or "").lower().strip()
        if any(re.search(pola, teks) for pola in self.POLA_REALTIME):
            return True
        return any(kk in teks for kk in self.KATA_KUNCI_REALTIME)

    # ── Utilitas HTTP ─────────────────────────────────────────────────────────
    def _fetch(self, url: str) -> Optional[str]:
        try:
            req = urllib.request.Request(url, headers=self.HEADERS)
            try:
                import certifi

                konteks = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                konteks = ssl.create_default_context()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=konteks) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.URLError as galat:
                if not isinstance(getattr(galat, "reason", None), ssl.SSLCertVerificationError):
                    raise
                with urllib.request.urlopen(
                    req, timeout=self.timeout, context=ssl._create_unverified_context()
                ) as resp:
                    return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[WebSearch] Gagal fetch {url}: {e}")
            return None

    # ── DuckDuckGo ────────────────────────────────────────────────────────────
    def cari_duckduckgo(self, kueri: str, maks: int = 5) -> List[Dict[str, str]]:
        if self._ddgs is not None:
            try:
                hasil = []
                with self._ddgs() as ddgs:
                    for item in ddgs.text(kueri, region="id-id", max_results=maks):
                        hasil.append(
                            {
                                "judul": item.get("title", ""),
                                "url": item.get("href", ""),
                                "snippet": item.get("body", ""),
                            }
                        )
                if hasil:
                    return hasil
            except Exception as e:
                print(f"[WebSearch] duckduckgo-search gagal: {e}; fallback scraper HTML.")

        # Cadangan: scraper HTML DuckDuckGo.
        hasil: List[Dict[str, str]] = []
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(kueri)}&kl=id-id"
            html = self._fetch(url)
            if not html:
                return hasil
            pola_judul = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
            pola_snippet = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
            judul_m = pola_judul.findall(html)
            snippet_m = pola_snippet.findall(html)
            for i in range(min(len(judul_m), maks)):
                url_hasil = judul_m[i][0]
                judul = re.sub(r"<[^>]+>", "", judul_m[i][1]).strip()
                snippet = re.sub(r"<[^>]+>", "", snippet_m[i]).strip() if i < len(snippet_m) else ""
                if "uddg=" in url_hasil:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_hasil).query)
                    if "uddg" in parsed:
                        url_hasil = urllib.parse.unquote(parsed["uddg"][0])
                hasil.append({"judul": judul, "url": url_hasil, "snippet": snippet})
        except Exception as e:
            print(f"[WebSearch] Error DuckDuckGo HTML: {e}")
        return hasil

    # ── Wikipedia ─────────────────────────────────────────────────────────────
    def cari_wikipedia(self, kueri: str, bahasa: str = "id") -> Optional[Dict[str, str]]:
        try:
            lang = "id" if (bahasa or "id").startswith("id") else "en"
            url_search = (
                f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(kueri)}&format=json&srlimit=1"
            )
            html = self._fetch(url_search)
            if not html:
                return None
            hasil = json.loads(html).get("query", {}).get("search", [])
            if not hasil:
                return None
            judul = hasil[0]["title"]
            url_extract = (
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                f"{urllib.parse.quote(judul)}"
            )
            html = self._fetch(url_extract)
            if not html:
                return None
            data = json.loads(html)
            extract = data.get("extract", "")
            if extract:
                return {
                    "judul": judul,
                    "snippet": extract,
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "sumber": "Wikipedia",
                }
        except Exception as e:
            print(f"[WebSearch] Error Wikipedia: {e}")
        return None

    # ── Wikidata: pemegang jabatan terstruktur ────────────────────────────────
    def cari_presiden_indonesia(self, kueri: str) -> Optional[Dict[str, str]]:
        q = (kueri or "").lower()
        if "presiden" not in q or "indonesia" not in q:
            return None
        try:
            data = self._fetch(
                "https://www.wikidata.org/w/api.php?action=wbgetentities"
                "&ids=Q252&props=claims&format=json"
            )
            if not data:
                return None
            klaim = json.loads(data)["entities"]["Q252"]["claims"].get("P35", [])
            aktif = next(
                (i for i in klaim if i.get("rank") == "preferred" and "P582" not in i.get("qualifiers", {})),
                None,
            )
            identitas = (aktif or {}).get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if not identitas:
                return None
            nama_data = self._fetch(
                "https://www.wikidata.org/w/api.php?action=wbgetentities"
                f"&ids={identitas}&props=labels&languages=id,en&format=json"
            )
            if not nama_data:
                return None
            label = json.loads(nama_data)["entities"][identitas].get("labels", {})
            nama = (label.get("id") or label.get("en") or {}).get("value")
            if not nama:
                return None
            return {
                "judul": "Data jabatan Presiden Indonesia",
                "snippet": f"Presiden Indonesia saat ini adalah {nama}.",
                "url": f"https://www.wikidata.org/wiki/{identitas}",
                "sumber": "Wikidata",
            }
        except Exception as e:
            print(f"[WebSearch] Data presiden gagal: {e}")
            return None

    # ── Pencarian utama ───────────────────────────────────────────────────────
    def cari(self, kueri: str, bahasa: str = "id") -> Dict[str, Any]:
        """Gabungkan Wikipedia/Wikidata + DuckDuckGo menjadi konteks untuk LLM."""
        print(f"[WebSearch] Mencari: '{kueri}'")
        hasil_jabatan = self.cari_presiden_indonesia(kueri)
        hasil_wiki = hasil_jabatan or self.cari_wikipedia(kueri, bahasa)
        hasil_ddg = self.cari_duckduckgo(kueri, maks=5)

        bagian: List[str] = []
        if hasil_wiki:
            bagian.append(
                f"[DARI WIKIPEDIA]\n{hasil_wiki['snippet']}\nSumber: {hasil_wiki.get('url', '')}"
            )
        for h in hasil_ddg[:3]:
            if h.get("snippet"):
                bagian.append(
                    f"[DARI WEB]\n{h['judul']}\n{h['snippet']}\nSumber: {h.get('url', '')}"
                )

        if not bagian:
            return {"ditemukan": False, "konteks": "", "pesan": "Tidak ada hasil relevan."}
        return {
            "ditemukan": True,
            "konteks": "\n\n".join(bagian),
            "hasil_wikipedia": hasil_wiki,
            "hasil_duckduckgo": hasil_ddg,
        }

    def info(self) -> Dict[str, Any]:
        return {"mesin": "duckduckgo-search" if self._ddgs else "duckduckgo-html+urllib"}


_instance: Optional[WebSearchTool] = None


def dapatkan_web_search() -> WebSearchTool:
    """Ambil instansi WebSearchTool."""
    global _instance
    if _instance is None:
        _instance = WebSearchTool()
    return _instance


if __name__ == "__main__":
    alat = dapatkan_web_search()
    print("Info:", alat.info())
    for t in ["Siapa presiden Indonesia sekarang?", "Berapa biaya kuliah UCIC?"]:
        print(f"  '{t}' -> perlu={alat.perlu_web_search(t)}")
