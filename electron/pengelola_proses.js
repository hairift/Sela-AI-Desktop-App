/**
 * SELA AI Desktop - Pengelola Proses Mesin AI Lokal
 * Bertanggung jawab meluncurkan, memantau, dan mematikan server AI Python lokal secara aman.
 */

const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

class PengelolaProsesAi {
  constructor() {
    this.prosesPython = null;
    this.portServerAi = 8008;
    this.statusSiap = false;
    // Cold start bisa lama: llama-server perlu memuat model ~4,9 GB ke memori.
    // 120 percobaan x 1 detik = 120 detik batas tunggu.
    this.upayaKoneksiMaksimal = 120;
    this.jalurAkarProyek = null;
    this.pythonTerpilih = null; // { cmd, args } interpreter yang benar-benar punya dependensi
  }

  /**
   * Mencari interpreter Python yang benar-benar memiliki dependensi SELA
   * (fastapi + uvicorn). Penting: `python` di PATH sering menunjuk versi lain
   * yang belum terpasang paketnya, sehingga server gagal dijalankan.
   * Urutan: SELA_PYTHON -> venv proyek -> py -3.12 (Windows) -> py -> python -> python3
   * @returns {{cmd: string, args: string[]}|null}
   */
  temukanPython() {
    if (this.pythonTerpilih) return this.pythonTerpilih;

    const akar = this.jalurAkarProyek || process.cwd();
    const namaExe = process.platform === 'win32' ? 'python.exe' : 'python';
    const kandidat = [];

    // 1. Override eksplisit
    if (process.env.SELA_PYTHON) {
      kandidat.push({ cmd: process.env.SELA_PYTHON, args: [] });
    }

    // 2. Virtualenv di dalam proyek (paling dapat diandalkan bila ada)
    const subVenv = process.platform === 'win32'
      ? ['Scripts', namaExe]
      : ['bin', 'python'];
    for (const dasar of [path.join(akar, 'ai-engine', '.venv'), path.join(akar, '.venv')]) {
      const kandidatVenv = path.join(dasar, ...subVenv);
      if (fs.existsSync(kandidatVenv)) kandidat.push({ cmd: kandidatVenv, args: [] });
    }

    // 3. Peluncur `py` Windows dengan versi yang dipakai proyek
    if (process.platform === 'win32') {
      kandidat.push({ cmd: 'py', args: ['-3.12'] });
      kandidat.push({ cmd: 'py', args: ['-3'] });
      kandidat.push({ cmd: 'py', args: [] });
    }

    // 4. Nama generik
    kandidat.push({ cmd: 'python', args: [] });
    kandidat.push({ cmd: 'python3', args: [] });

    for (const k of kandidat) {
      try {
        const uji = spawnSync(k.cmd, [...k.args, '-c', 'import fastapi, uvicorn'], {
          encoding: 'utf8',
          timeout: 25000,
          windowsHide: true,
        });
        if (uji.status === 0) {
          console.log(`[Pengelola AI] Interpreter Python dipakai: ${k.cmd} ${k.args.join(' ')}`.trim());
          this.pythonTerpilih = k;
          return k;
        }
      } catch (_) {
        // lanjut ke kandidat berikutnya
      }
    }

    console.warn('[Pengelola AI] Tidak menemukan Python dengan fastapi+uvicorn. ' +
      'Pasang dependensi (pip install -r ai-engine/requirements.txt) atau set SELA_PYTHON.');
    return null;
  }

  /**
   * Menjalankan server AI Python lokal di latar belakang
   * @param {string} jalurAkarProyek Jalur absolut ke direktori proyek
   * @returns {Promise<boolean>}
   */
  async jalankanMesinAi(jalurAkarProyek) {
    this.jalurAkarProyek = jalurAkarProyek;
    const jalurSkripServer = path.join(jalurAkarProyek, 'ai-engine', 'server.py');
    const direktoriKerjaAi = path.join(jalurAkarProyek, 'ai-engine');

    // 1. Cek apakah server AI sudah aktif berjalan di port 8008
    const sudahAktif = await this.periksaKesehatanSekali();
    if (sudahAktif) {
      console.log(`[Pengelola AI] Mesin AI lokal sudah aktif dan siap di port ${this.portServerAi}!`);
      this.statusSiap = true;
      return true;
    }

    // 2. Pastikan interpreter Python punya dependensi (fastapi + uvicorn)
    const python = this.temukanPython();
    if (!python) {
      console.error('[Pengelola AI] Server AI tidak dapat dijalankan: interpreter Python tidak siap.');
      this.statusSiap = false;
      return false;
    }

    console.log('[Pengelola AI] Memulai mesin AI offline lokal...');
    console.log(`[Pengelola AI] Menjalankan: ${python.cmd} ${python.args.join(' ')} ${jalurSkripServer}`.trim());

    try {
      // Menjalankan proses Python server
      this.prosesPython = spawn(python.cmd, [...python.args, jalurSkripServer], {
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

      // Menunggu hingga server siap menerima koneksi HTTP/WebSocket.
      // Bila proses berhenti lebih awal (mis. dependensi kurang), jangan tunggu 30 detik penuh.
      const siap = await Promise.race([
        this.tungguKesiapanServer(),
        new Promise((resolve) => {
          this.prosesPython.once('close', (kodeKeluar) => {
            if (!this.statusSiap) {
              console.error(`[Pengelola AI] Proses AI berhenti lebih awal (kode ${kodeKeluar}). ` +
                'Periksa pesan error di atas (biasanya dependensi Python belum terpasang).');
              resolve(false);
            }
          });
        }),
      ]);
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
        // Pakai 127.0.0.1 (bukan "localhost") agar tidak bergantung pada
        // resolusi IPv6/IPv4; server uvicorn mengikat alamat IPv4.
        const permintaan = http.get(`http://127.0.0.1:${this.portServerAi}/kesehatan`, (respons) => {
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
            // Beri tahu pengguna setiap 10 detik agar tidak terkesan menggantung
            if (percobaan % 10 === 0) {
              console.log(`[Pengelola AI] Menunggu server AI siap... (${percobaan} detik)`);
            }
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
