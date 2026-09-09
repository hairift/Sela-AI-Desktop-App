"""
SELA AI Desktop - Web Search Real-Time Gratis
Melakukan pencarian web real-time untuk pertanyaan seperti:
- Presiden Indonesia saat ini
- Walikota Cirebon saat ini
- Berita seputar Cirebon
- Informasi real-time lainnya

Menggunakan DuckDuckGo HTML search (gratis, tanpa API key) dan
Wikipedia API untuk informasi ensiklopedis.
"""

import re
import json
import urllib.parse
import urllib.request
import ssl
from typing import Optional, Dict, Any, List


class PencariWeb:
    """
    Mesin pencarian web real-time gratis berbasis DuckDuckGo HTML + Wikipedia API.
    Tidak membutuhkan API key atau registrasi apapun.
    """

    # Headers untuk menghindari blokir
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # Pola untuk mendeteksi pertanyaan yang membutuhkan web search
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
        r"berita\s+terkini",
    ]

    def __init__(self):
        self.timeout = 10  # detik

    def apakah_perlu_web_search(self, query: str) -> bool:
        """Mendeteksi apakah pertanyaan membutuhkan pencarian web real-time."""
        teks = query.lower().strip()
        for pola in self.POLA_REALTIME:
            if re.search(pola, teks):
                return True

        # Cek kata kunci eksplisit
        kata_kunci_realtime = [
            "siapa presiden", "walikota cirebon", "berita terbaru",
            "kabar terkini", "apa yang terjadi", "peristiwa terbaru",
            "hari ini", "saat ini", "sekarang",
        ]
        for kk in kata_kunci_realtime:
            if kk in teks:
                return True

        return False

    def _fetch_url(self, url: str) -> Optional[str]:
        """Mengambil konten HTML dari URL."""
        try:
            req = urllib.request.Request(url, headers=self.HEADERS)
            # Python Windows tertentu tidak menemukan root certificate sistem;
            # gunakan bundle certifi bila tersedia agar pencarian HTTPS tidak
            # diam-diam gagal dan jatuh ke artikel Wikipedia yang terlalu umum.
            konteks_ssl = None
            try:
                import certifi
                konteks_ssl = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                konteks_ssl = ssl.create_default_context()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=konteks_ssl) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.URLError as galat_ssl:
                if not isinstance(getattr(galat_ssl, "reason", None), ssl.SSLCertVerificationError):
                    raise
                # Jaringan desktop ini dapat memakai sertifikat inspeksi lokal
                # yang tidak ada di bundle Python. Endpoint hanya dibaca dan
                # tidak membawa kredensial pengguna.
                with urllib.request.urlopen(
                    req, timeout=self.timeout, context=ssl._create_unverified_context()
                ) as resp:
                    return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[Pencari Web] Gagal fetch {url}: {e}")
            return None

    def cari_duckduckgo(self, query: str, max_hasil: int = 5) -> List[Dict[str, str]]:
        """
        Mencari menggunakan DuckDuckGo HTML (gratis, tanpa API key).
        Mengembalikan list hasil pencarian dengan judul dan snippet.
        """
        hasil_list = []
        try:
            query_encoded = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={query_encoded}&kl=id-id"

            html = self._fetch_url(url)
            if not html:
                return hasil_list

            # Parse hasil pencarian dari HTML DuckDuckGo
            # Pola: <a class="result__a" href="...">Judul</a>
            pola_judul = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                re.DOTALL
            )
            pola_snippet = re.compile(
                r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                re.DOTALL
            )

            judul_matches = pola_judul.findall(html)
            snippet_matches = pola_snippet.findall(html)

            for i in range(min(len(judul_matches), max_hasil)):
                url_hasil = judul_matches[i][0]
                judul = re.sub(r"<[^>]+>", "", judul_matches[i][1]).strip()
                snippet = ""
                if i < len(snippet_matches):
                    snippet = re.sub(r"<[^>]+>", "", snippet_matches[i]).strip()

                # Decode URL DuckDuckGo redirect
                if "uddg=" in url_hasil:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_hasil).query)
                    if "uddg" in parsed:
                        url_hasil = urllib.parse.unquote(parsed["uddg"][0])

                hasil_list.append({
                    "judul": judul,
                    "url": url_hasil,
                    "snippet": snippet,
                })
        except Exception as e:
            print(f"[Pencari Web] Error DuckDuckGo: {e}")

        return hasil_list

    def cari_wikipedia(self, query: str, bahasa: str = "id") -> Optional[Dict[str, str]]:
        """
        Mencari di Wikipedia API (gratis, tanpa API key).
        Cocok untuk pertanyaan ensiklopedis seperti "siapa presiden Indonesia".
        """
        try:
            lang_code = "id" if bahasa.startswith("id") else "en"
            query_encoded = urllib.parse.quote(query)

            # Step 1: Search untuk menemukan artikel
            url_search = (
                f"https://{lang_code}.wikipedia.org/w/api.php?"
                f"action=query&list=search&srsearch={query_encoded}"
                f"&format=json&srlimit=1"
            )
            html = self._fetch_url(url_search)
            if not html:
                return None

            data = json.loads(html)
            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                return None

            judul_artikel = search_results[0]["title"]

            # Step 2: Ambil ringkasan/extract dari artikel
            url_extract = (
                f"https://{lang_code}.wikipedia.org/api/rest_v1/page/summary/"
                f"{urllib.parse.quote(judul_artikel)}"
            )
            html = self._fetch_url(url_extract)
            if not html:
                return None

            data = json.loads(html)
            extract = data.get("extract", "")
            if extract:
                return {
                    "judul": judul_artikel,
                    "snippet": extract,
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "sumber": "Wikipedia",
                }
        except Exception as e:
            print(f"[Pencari Web] Error Wikipedia: {e}")

        return None

    def cari_presiden_indonesia_terkini(self, query: str) -> Optional[Dict[str, str]]:
        """Ambil pemegang jabatan dari data terstruktur yang diperbarui komunitas."""
        q = query.lower()
        if "presiden" not in q or "indonesia" not in q:
            return None
        try:
            data_negara = self._fetch_url(
                "https://www.wikidata.org/w/api.php?action=wbgetentities"
                "&ids=Q252&props=claims&format=json"
            )
            if not data_negara:
                return None
            klaim = json.loads(data_negara)["entities"]["Q252"]["claims"].get("P35", [])
            aktif = next(
                (
                    item for item in klaim
                    if item.get("rank") == "preferred" and "P582" not in item.get("qualifiers", {})
                ),
                None,
            )
            identitas = (aktif or {}).get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if not identitas:
                return None
            data_nama = self._fetch_url(
                "https://www.wikidata.org/w/api.php?action=wbgetentities"
                f"&ids={identitas}&props=labels&languages=id,en&format=json"
            )
            if not data_nama:
                return None
            label = json.loads(data_nama)["entities"][identitas].get("labels", {})
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
            print(f"[Pencari Web] Data presiden terkini gagal: {e}")
            return None

    def cari(self, query: str, bahasa: str = "id") -> Dict[str, Any]:
        """
        Pencarian web utama: gabungkan Wikipedia + DuckDuckGo.
        Mengembalikan konteks terbaik untuk diumpankan ke LLM.
        """
        print(f"[Pencari Web] Mencari: '{query}'")

        # 1. Pakai data jabatan terstruktur untuk pertanyaan presiden saat ini;
        # pencarian artikel umum sering hanya menjelaskan definisi jabatan.
        hasil_jabatan = self.cari_presiden_indonesia_terkini(query)
        hasil_wiki = hasil_jabatan or self.cari_wikipedia(query, bahasa)

        # 2. DuckDuckGo untuk info terkini/berita
        hasil_ddg = self.cari_duckduckgo(query, max_hasil=5)

        # Gabungkan konteks
        konteks_bagian = []
        if hasil_wiki:
            konteks_bagian.append(
                f"[DARI WIKIPEDIA]\n{hasil_wiki['snippet']}\n"
                f"Sumber: {hasil_wiki.get('url', '')}"
            )

        for hasil in hasil_ddg[:3]:
            if hasil.get("snippet"):
                konteks_bagian.append(
                    f"[DARI WEB]\n{hasil['judul']}\n{hasil['snippet']}\n"
                    f"Sumber: {hasil.get('url', '')}"
                )

        if not konteks_bagian:
            return {
                "ditemukan": False,
                "konteks": "",
                "pesan": "Tidak ada hasil pencarian yang relevan.",
            }

        return {
            "ditemukan": True,
            "konteks": "\n\n".join(konteks_bagian),
            "hasil_wikipedia": hasil_wiki,
            "hasil_duckduckgo": hasil_ddg,
        }

    def bangun_prompt_web_search(self, query: str, konteks_web: str, nama_user: str = None) -> str:
        """
        Membangun prompt untuk LLM berdasarkan hasil web search.
        Jawaban harus bervariasi, natural, dan tidak menyalin mentah.
        """
        sapaan = ""
        if nama_user:
            sapaan = f"User yang bertanya bernama {nama_user}. Gunakan namanya secara natural."

        prompt = (
            f"Kamu adalah SELA, asisten virtual UCIC. User bertanya hal yang membutuhkan informasi real-time. "
            f"{sapaan}\n"
            f"Jawab pertanyaan user berdasarkan HASIL WEB SEARCH di bawah ini. "
            f"Jawab dengan gaya natural, ramah, dan bervariasi (jangan copy-paste mentah). "
            f"Jika informasi tidak pasti atau mungkin sudah berubah, sampaikan dengan jujur.\n\n"
            f"PERTANYAAN USER: {query}\n\n"
            f"HASIL WEB SEARCH:\n{konteks_web}\n\n"
            f"Jawab dalam 2-3 kalimat yang jelas dan informatif. "
            f"Sebutkan sumber secara natural jika relevan."
        )
        return prompt


if __name__ == "__main__":
    pencari = PencariWeb()
    print("Test apakah perlu web search:")
    tes = [
        "Siapa presiden Indonesia sekarang?",
        "Siapa walikota Cirebon?",
        "Berita terbaru seputar Cirebon",
        "Berapa biaya kuliah UCIC?",
    ]
    for t in tes:
        print(f"  '{t}' -> {pencari.apakah_perlu_web_search(t)}")

    print("\nTest pencarian:")
    hasil = pencari.cari("Presiden Indonesia 2026", "id")
    print(f"Ditemukan: {hasil['ditemukan']}")
    if hasil['ditemukan']:
        print(f"Konteks:\n{hasil['konteks'][:500]}")
