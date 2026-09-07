/**
 * SELA AI Desktop - Script Preload IPC Bridge
 * Menjembatani komunikasi yang aman antara antarmuka React dan sistem operasi lokal.
 */

const { contextBridge, ipcRenderer } = require('electron');

// Mengekspos API desktop yang aman ke dalam konteks jendela browser (window.selaDesktop)
contextBridge.exposeInMainWorld('selaDesktop', {
  // Mendapatkan informasi platform sistem operasi (win32, linux, darwin)
  ambilPlatformSistem: () => process.platform,

  // Mendapatkan status kesehatan dan kesiapan mesin AI lokal
  ambilStatusMesinAi: () => ipcRenderer.invoke('ambil-status-ai'),

  // Mengubah mode tampilan jendela antara Kiosk layar penuh dan jendela biasa
  setelModeKiosk: (statusKiosk) => ipcRenderer.send('setel-mode-kiosk', statusKiosk),

  // Meminimalkan jendela aplikasi
  minimalkanJendela: () => ipcRenderer.send('minimalkan-jendela'),

  // Memaksimalkan atau mengembalikan ukuran jendela aplikasi
  maksimalkanJendela: () => ipcRenderer.send('maksimalkan-jendela'),

  // Menutup aplikasi secara menyeluruh
  tutupAplikasi: () => ipcRenderer.send('tutup-aplikasi'),

  // Menerima notifikasi atau event dari proses utama
  langgananEventUtama: (namaSaluran, fungsiCallback) => {
    const saluranValid = ['status-ai-diperbarui', 'mode-kiosk-berubah'];
    if (saluranValid.includes(namaSaluran)) {
      const pembungkusCallback = (event, ...argumen) => fungsiCallback(...argumen);
      ipcRenderer.on(namaSaluran, pembungkusCallback);
      return () => ipcRenderer.removeListener(namaSaluran, pembungkusCallback);
    }
  },
});
