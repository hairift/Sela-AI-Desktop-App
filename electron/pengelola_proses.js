/**
 * SELA AI Desktop - Pengelola Proses Mesin AI Lokal
 * Bertanggung jawab meluncurkan, memantau, dan mematikan server AI Python lokal secara aman.
 */

const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

class PengelolaProsesAi {
  constructor() {
    this.prosesPython = null;
    this.portServerAi = 8008;
    this.statusSiap = false;
    this.upayaKoneksiMaksimal = 30;
  }

  /**
   * Menjalankan server AI Python lokal di latar belakang
   * @param {string} jalurAkarProyek Jalur absolut ke direktori proyek
   * @returns {Promise<boolean>}
   */
  async jalankanMesinAi(jalurAkarProyek) {
    const jalurSkripServer = path.join(jalurAkarProyek, 'ai-engine', 'server.py');
    const direktoriKerjaAi = path.join(jalurAkarProyek, 'ai-engine');

    // 1. Cek apakah server AI sudah aktif berjalan di port 8008
    const sudahAktif = await this.periksaKesehatanSekali();
    if (sudahAktif) {
      console.log(`[Pengelola AI] Mesin AI lokal sudah aktif dan siap di port ${this.portServerAi}!`);
      this.statusSiap = true;
      return true;
    }

    console.log('[Pengelola AI] Memulai mesin AI offline lokal...');
    console.log(`[Pengelola AI] Menjalankan: python ${jalurSkripServer}`);

    try {
      // Menjalankan proses Python server
      this.prosesPython = spawn('python', [jalurSkripServer], {
        cwd: direktoriKerjaAi,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PORT_SELA_AI: String(this.portServerAi),
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      // Menangkap keluaran stdout dari server AI
      this.prosesPython.stdout.on('data', (dataMentah) => {
        const teksPesan = dataMentah.toString().trim();
        console.log(`[Mesin AI (Stdout)] ${teksPesan}`);
      });

      // Menangkap keluaran stderr dari server AI
      this.prosesPython.stderr.on('data', (dataMentah) => {
        const teksPeringatan = dataMentah.toString().trim();
        // Hanya tampilkan jika bukan sekadar log info
        if (teksPeringatan.includes('ERROR') || teksPeringatan.includes('Traceback')) {
          console.error(`[Mesin AI (Error)] ${teksPeringatan}`);
        } else {
          console.log(`[Mesin AI (Log)] ${teksPeringatan}`);
        }
      });

      // Menangani saat proses Python berhenti tak terduga
      this.prosesPython.on('close', (kodeKeluar) => {
        console.log(`[Pengelola AI] Proses AI selesai dengan kode keluar: ${kodeKeluar}`);
        this.statusSiap = false;
      });

      // Menunggu hingga server siap menerima koneksi HTTP/WebSocket
      const siap = await this.tungguKesiapanServer();
      this.statusSiap = siap;
      return siap;
    } catch (kesalahan) {
      console.error('[Pengelola AI] Gagal menjalankan proses Python:', kesalahan);
      this.statusSiap = false;
      return false;
    }
  }

  /**
   * Memeriksa kesehatan server AI satu kali dengan timeout singkat (800ms)
   * @returns {Promise<boolean>}
   */
  periksaKesehatanSekali() {
    return new Promise((resolve) => {
      const permintaan = http.get(`http://127.0.0.1:${this.portServerAi}/kesehatan`, (respons) => {
        resolve(respons.statusCode === 200);
      });
      permintaan.on('error', () => resolve(false));
      permintaan.setTimeout(800, () => {
        permintaan.destroy();
        resolve(false);
      });
    });
  }

  /**
   * Melakukan polling berkala ke endpoint healthcheck server AI
   * @returns {Promise<boolean>}
   */
  tungguKesiapanServer() {
    return new Promise((resolve) => {
      let percobaan = 0;

      const periksaKesehatan = () => {
        percobaan += 1;
        const permintaan = http.get(`http://localhost:${this.portServerAi}/kesehatan`, (respons) => {
          if (respons.statusCode === 200) {
            console.log('[Pengelola AI] Server AI lokal berhasil terhubung dan siap digunakan!');
            resolve(true);
          } else if (percobaan < this.upayaKoneksiMaksimal) {
            setTimeout(periksaKesehatan, 1000);
          } else {
            console.warn('[Pengelola AI] Waktu tunggu koneksi server AI habis.');
            resolve(false);
          }
        });

        permintaan.on('error', () => {
          if (percobaan < this.upayaKoneksiMaksimal) {
            setTimeout(periksaKesehatan, 1000);
          } else {
            console.warn('[Pengelola AI] Server AI belum merespons setelah upaya maksimal.');
            resolve(false);
          }
        });

        permintaan.setTimeout(1500, () => {
          permintaan.destroy();
        });
      };

      periksaKesehatan();
    });
  }

  /**
   * Menghentikan server AI Python secara bersih
   */
  hentikanMesinAi() {
    if (this.prosesPython) {
      console.log('[Pengelola AI] Menghentikan proses AI lokal...');
      try {
        if (process.platform === 'win32') {
          // Di Windows, gunakan taskkill untuk mematikan sub-proses secara menyeluruh
          spawn('taskkill', ['/pid', String(this.prosesPython.pid), '/f', '/t']);
        } else {
          this.prosesPython.kill('SIGTERM');
        }
      } catch (kesalahan) {
        console.error('[Pengelola AI] Terjadi kendala saat menghentikan proses Python:', kesalahan);
      }
      this.prosesPython = null;
      this.statusSiap = false;
    }
  }

  /**
   * Mendapatkan status kesiapan mesin AI
   * @returns {boolean}
   */
  apakahSiap() {
    return this.statusSiap;
  }
}

module.exports = PengelolaProsesAi;
