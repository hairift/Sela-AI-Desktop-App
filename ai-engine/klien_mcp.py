"""Klien MCP untuk komunikasi SELA dengan robot kampus lain."""

import os
import json
import asyncio
import threading
from typing import Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor

try:
    import websockets
except ImportError:
    websockets = None


def _endpoint_terkonfigurasi() -> list[str]:
    """Ambil endpoint rahasia dari environment, tanpa menyimpannya di source."""
    return [
        endpoint.strip()
        for endpoint in (os.getenv("SELA_MCP_ENDPOINT_A", ""), os.getenv("SELA_MCP_ENDPOINT_B", ""))
        if endpoint.strip()
    ]


class KlienMcp:
    """
    Klien MCP untuk SELA AI.
    Menghubungkan ke dua endpoint MCP sekaligus untuk redundansi.
    """

    def __init__(self):
        self.endpoint_aktif: Dict[str, bool] = {
            "endpoint_a": False,
            "endpoint_b": False,
        }
        self.pesan_masuk: list = []
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mcp")
        self._threads: Dict[str, threading.Thread] = {}
        self._running = False
        self._on_message_callback: Optional[Callable] = None
        self._locks: Dict[str, threading.Lock] = {
            "endpoint_a": threading.Lock(),
            "endpoint_b": threading.Lock(),
        }

    def set_callback_pesan(self, callback: Callable[[str, str], None]):
        """Set callback yang dipanggil saat pesan dari robot kampus lain diterima."""
        self._on_message_callback = callback

    def mulai(self):
        """Memulai koneksi ke dua endpoint MCP secara paralel di background."""
        if self._running:
            return
        self._running = True

        if websockets is None:
            print("[MCP Klien] Pustaka 'websockets' belum terpasang. Install dengan: pip install websockets")
            return

        # Mulai thread untuk setiap endpoint
        endpoints = _endpoint_terkonfigurasi()
        if not endpoints:
            print("[MCP Klien] Endpoint belum dikonfigurasi; koneksi MCP dilewati.")
            return
        for indeks, token in enumerate(endpoints):
            nama = "endpoint_a" if indeks == 0 else "endpoint_b"
            t = threading.Thread(
                target=self._jalankan_loop_websocket,
                args=(nama, token),
                daemon=True,
                name=f"mcp_{nama}"
            )
            t.start()
            self._threads[nama] = t

        print("[MCP Klien] Dua koneksi MCP dimulai di background.")

    def hentikan(self):
        """Menghentikan semua koneksi MCP."""
        self._running = False
        print("[MCP Klien] Semua koneksi MCP dihentikan.")

    def _jalankan_loop_websocket(self, nama: str, token: str):
        """Menjalankan loop WebSocket untuk satu endpoint di thread terpisah."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._hubungkan_endpoint(nama, token))
        except Exception as e:
            print(f"[MCP Klien] {nama} error: {e}")
        finally:
            loop.close()

    async def _hubungkan_endpoint(self, nama: str, token: str):
        """Menghubungkan ke satu endpoint MCP dengan auto-reconnect."""
        while self._running:
            try:
                print(f"[MCP Klien] Menghubungkan ke {nama}...")
                async with websockets.connect(
                    token,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    with self._locks[nama]:
                        self.endpoint_aktif[nama] = True
                    print(f"[MCP Klien] {nama} terhubung!")

                    # Kirim pesan registrasi
                    await ws.send(json.dumps({
                        "type": "register",
                        "agent_name": "SELA_AI_UCIC",
                        "institution": "UCIC",
                        "capabilities": ["campus_info", "admissions", "voice_assistant"],
                    }))

                    # Dengarkan pesan masuk
                    async for pesan_raw in ws:
                        try:
                            data = json.loads(pesan_raw)
                            self._proses_pesan_masuk(nama, data)
                        except json.JSONDecodeError:
                            # Pesan teks biasa
                            self._proses_pesan_masuk(nama, {"type": "text", "content": pesan_raw})

            except Exception as e:
                print(f"[MCP Klien] {nama} terputus: {e}")
            finally:
                with self._locks[nama]:
                    self.endpoint_aktif[nama] = False

            if self._running:
                print(f"[MCP Klien] {nama} mencoba reconnect dalam 5 detik...")
                await asyncio.sleep(5)

    def _proses_pesan_masuk(self, nama_endpoint: str, data: Dict[str, Any]):
        """Memproses pesan yang diterima dari robot kampus lain."""
        tipe_pesan = data.get("type", "unknown")
        konten = data.get("content", data.get("message", ""))
        pengirim = data.get("agent_name", data.get("sender", "unknown"))

        print(f"[MCP Klien] Pesan dari {pengirim} via {nama_endpoint}: {tipe_pesan}")

        pesan_obj = {
            "pengirim": pengirim,
            "tipe": tipe_pesan,
            "konten": konten,
            "endpoint": nama_endpoint,
        }

        with self._locks["endpoint_a"]:
            self.pesan_masuk.append(pesan_obj)
            if len(self.pesan_masuk) > 100:
                self.pesan_masuk = self.pesan_masuk[-100:]

        if self._on_message_callback:
            try:
                self._on_message_callback(pengirim, str(konten))
            except Exception as e:
                print(f"[MCP Klien] Error callback pesan: {e}")

    def kirim_pesan(self, pesan: str, target: str = "broadcast") -> bool:
        """
        Mengirim pesan ke robot kampus lain via MCP.
        Mengembalikan True jika berhasil dikirim ke minimal satu endpoint.
        """
        if not websockets:
            return False

        berhasil = False
        for indeks, token in enumerate(_endpoint_terkonfigurasi()):
            nama = "endpoint_a" if indeks == 0 else "endpoint_b"
            if not self.endpoint_aktif.get(nama, False):
                continue
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._kirim_ke_endpoint(nama, token, pesan, target))
                loop.close()
                berhasil = True
            except Exception as e:
                print(f"[MCP Klien] Gagal kirim ke {nama}: {e}")

        return berhasil

    async def _kirim_ke_endpoint(self, nama: str, token: str, pesan: str, target: str):
        """Mengirim pesan ke satu endpoint MCP."""
        async with websockets.connect(token) as ws:
            await ws.send(json.dumps({
                "type": "message",
                "content": pesan,
                "target": target,
                "sender": "SELA_AI_UCIC",
            }))

    def status(self) -> Dict[str, Any]:
        """Mengembalikan status koneksi MCP."""
        return {
            "endpoint_a_aktif": self.endpoint_aktif.get("endpoint_a", False),
            "endpoint_b_aktif": self.endpoint_aktif.get("endpoint_b", False),
            "jumlah_pesan_masuk": len(self.pesan_masuk),
            "menjalankan": self._running,
        }

    def ambil_pesan_masuk(self) -> list:
        """Mengambil dan mengosongkan antrian pesan masuk."""
        with self._locks["endpoint_a"]:
            pesan = list(self.pesan_masuk)
            self.pesan_masuk = []
        return pesan


if __name__ == "__main__":
    klien = KlienMcp()
    klien.mulai()
    print("Status:", klien.status())
    import time
    time.sleep(10)
    print("Status setelah 10 detik:", klien.status())
    print("Pesan masuk:", klien.ambil_pesan_masuk())
    klien.hentikan()
