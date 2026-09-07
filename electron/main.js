/**
 * SELA AI Desktop - Proses Utama (Main Process)
 * Mengelola jendela aplikasi desktop, akselerasi GPU, perizinan media, dan integrasi dengan mesin AI offline.
 */

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const PengelolaProsesAi = require('./pengelola_proses');

// Mengaktifkan flag akselerasi grafis GPU untuk performa maksimal Three.js 3D Avatar
app.commandLine.appendSwitch('enable-gpu-rasterization');
app.commandLine.appendSwitch('enable-zero-copy');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
// Mengaktifkan autoplay audio tanpa interaksi pengguna (wajib untuk TTS)
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
// Izin akses mikrofon dan kamera nyata (JANGAN gunakan use-fake-ui-for-media-stream karena akan memblokir mikrofon nyata)
app.commandLine.appendSwitch('allow-running-insecure-content');

// Menetapkan folder data pengguna khusus agar tidak bentrok dengan sesi cache lain
try {
  app.setPath('userData', path.join(app.getPath('appData'), 'sela-ai-desktop-data'));
} catch (_) {}

// Instansiasi pengelola proses AI lokal
const pengelolaAi = new PengelolaProsesAi();

// Variabel referensi jendela utama desktop
let jendelaUtama = null;

/**
 * Membuat jendela utama aplikasi desktop
 */
async function buatJendelaUtama() {
  jendelaUtama = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 680,
    center: true,
    title: 'SELA AI Receptionist & Customer Service - UCIC',
    backgroundColor: '#0f172a',
    show: false, // Jendela disembunyikan sampai render awal selesai agar tidak muncul layar putih
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webgl: true,
      backgroundThrottling: false, // Mencegah Three.js melambat saat jendela kehilangan fokus
      webSecurity: false, // Mencegah kendala CORS saat mengakses berkas model 3D dan streaming audio
      allowRunningInsecureContent: true,
    },
  });

  // Tampilkan jendela segera setelah antarmuka selesai dimuat dan dirender
  jendelaUtama.once('ready-to-show', () => {
    console.log('[SELA Desktop] Antarmuka siap dirender, menampilkan jendela aplikasi!');
    jendelaUtama.show();
  });

  // Tangkap pesan konsol renderer ke terminal proses utama untuk diagnosa
  jendelaUtama.webContents.on('console-message', (event, level, message, line, sourceId) => {
    if (level >= 2) {
      console.warn(`[Renderer Warning/Error] ${message} (${sourceId}:${line})`);
    } else {
      console.log(`[Renderer] ${message}`);
    }
  });

  jendelaUtama.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.error(`[SELA Desktop] Gagal memuat antarmuka: ${errorDescription} (${errorCode}) pada ${validatedURL}`);
  });

  // Izinkan akses kamera dan mikrofon secara otomatis tanpa dialog pop-up
  jendelaUtama.webContents.session.setPermissionRequestHandler((halamanWeb, izin, fungsiSetuju) => {
    const izinDiizinkan = ['media', 'camera', 'microphone', 'audioCapture', 'notifications', 'geolocation', 'pointerLock', 'fullscreen'];
    if (izinDiizinkan.includes(izin)) {
      fungsiSetuju(true);
    } else {
      fungsiSetuju(false);
    }
  });

  // Handler pengecekan izin — pastikan SELALU setuju untuk media/mikrofon/kamera
  jendelaUtama.webContents.session.setPermissionCheckHandler((halamanWeb, izin) => {
    const izinDiizinkan = ['media', 'camera', 'microphone', 'audioCapture', 'notifications', 'geolocation', 'pointerLock', 'fullscreen'];
    return izinDiizinkan.includes(izin);
  });

  // Tangani permintaan getUserMedia di level sesi — izinkan langsung tanpa dialog
  jendelaUtama.webContents.session.setDevicePermissionHandler(() => true);

  const urlServerAi = `http://127.0.0.1:${pengelolaAi.portServerAi}`;

  if (process.env.NODE_ENV === 'development') {
    try {
      console.log('[SELA Desktop] Memuat antarmuka dev Vite: http://127.0.0.1:5174?desktop=1');
      await jendelaUtama.loadURL('http://127.0.0.1:5174?desktop=1');
    } catch {
      await jendelaUtama.loadURL(urlServerAi);
    }
  } else {
    // Mode produksi offline: muat antarmuka langsung dari server AI lokal terpadu (Port 8008)
    console.log(`[SELA Desktop] Memuat antarmuka produksi dari server AI lokal: ${urlServerAi}`);
    try {
      await jendelaUtama.loadURL(urlServerAi);
    } catch (galatMuat) {
      console.warn('[SELA Desktop] Server AI sedang inisialisasi, mencoba ulang...', galatMuat?.message);
      await new Promise((resolve) => setTimeout(resolve, 1500));
      try {
        await jendelaUtama.loadURL(urlServerAi);
      } catch (galatKedua) {
        console.warn('[SELA Desktop] Menggunakan fallback file dist:', galatKedua?.message);
        const jalurBerkasDist = path.join(__dirname, '..', 'dist', 'index.html');
        await jendelaUtama.loadFile(jalurBerkasDist);
      }
    }
  }

  // Tangani penutupan jendela
  jendelaUtama.on('closed', () => {
    jendelaUtama = null;
  });
}

// ── Penanganan Komunikasi IPC dari Antarmuka ────────────────────────────────────

ipcMain.handle('ambil-status-ai', () => {
  return {
    siap: pengelolaAi.apakahSiap(),
    platform: process.platform,
    portServer: pengelolaAi.portServerAi,
  };
});

ipcMain.on('setel-mode-kiosk', (event, statusKiosk) => {
  if (jendelaUtama) {
    jendelaUtama.setKiosk(Boolean(statusKiosk));
    jendelaUtama.webContents.send('mode-kiosk-berubah', statusKiosk);
  }
});

ipcMain.on('minimalkan-jendela', () => {
  if (jendelaUtama) jendelaUtama.minimize();
});

ipcMain.on('maksimalkan-jendela', () => {
  if (jendelaUtama) {
    if (jendelaUtama.isMaximized()) {
      jendelaUtama.unmaximize();
    } else {
      jendelaUtama.maximize();
    }
  }
});

ipcMain.on('tutup-aplikasi', () => {
  app.quit();
});

// ── Siklus Hidup Aplikasi Electron ─────────────────────────────────────────────

app.whenReady().then(async () => {
  console.log('[SELA Desktop] Memulai aplikasi desktop SELA AI...');

  // 1. Jalankan proses AI lokal di latar belakang jika belum aktif dan pastikan server siap
  const jalurAkar = path.join(__dirname, '..');
  try {
    await pengelolaAi.jalankanMesinAi(jalurAkar);
  } catch (galat) {
    console.warn('[SELA Desktop] Catatan status mesin AI:', galat?.message);
  }

  // 2. Buat jendela antarmuka pengguna
  await buatJendelaUtama();

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await buatJendelaUtama();
    }
  });
});

// Saat semua jendela ditutup
app.on('window-all-closed', () => {
  // Hentikan proses AI lokal
  pengelolaAi.hentikanMesinAi();

  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Saat aplikasi akan keluar
app.on('before-quit', () => {
  pengelolaAi.hentikanMesinAi();
});
