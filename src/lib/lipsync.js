import { Lipsync, VISEMES } from "wawa-lipsync";

// Instansiasi tunggal Lipsync Manager berbasis Web Audio API (100% Wawa Lipsync)
export const lipsyncManager = new Lipsync({
  fftSize: 1024,
  historySize: 8,
});

export { VISEMES };

/**
 * Buka kunci AudioContext secara eager melalui interaksi pengguna (user gesture)
 * untuk mematuhi kebijakan autoplay browser modern dan mencegah audio terbisukan.
 */
export function unlockAudioContext() {
  if (lipsyncManager?.audioContext && lipsyncManager.audioContext.state === "suspended") {
    lipsyncManager.audioContext.resume().then(() => {
      console.log("[Wawa Lipsync] AudioContext berhasil dibuka (running)");
    }).catch((err) => {
      console.warn("[Wawa Lipsync] Gagal membuka AudioContext:", err);
    });
  }
}

// Pasang listener interaksi pengguna pertama kali
if (typeof window !== "undefined") {
  const handler = () => {
    unlockAudioContext();
  };
  window.addEventListener("click", handler, { passive: true });
  window.addEventListener("pointerdown", handler, { passive: true });
  window.addEventListener("keydown", handler, { passive: true });
}

/**
 * Hubungkan elemen Audio HTML ke Lipsync Manager
 * @param {HTMLAudioElement} audioElement 
 */
export function connectAudioToLipsync(audioElement) {
  if (!audioElement) return;
  try {
    unlockAudioContext();
    lipsyncManager.connectAudio(audioElement);
  } catch (err) {
    console.warn("[Wawa Lipsync] Kendala menghubungkan audio element:", err);
  }
}
