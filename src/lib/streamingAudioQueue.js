/**
 * SELA AI Desktop - Client Audio Streaming Queue (Gapless Audio Playback)
 * Memutar chunk audio kalimat demi kalimat dari WebSocket tanpa jeda (gapless),
 * sekaligus menghubungkan setiap potongan audio ke Wawa Lipsync.
 */

import { connectAudioToLipsync, unlockAudioContext } from "./lipsync";

class AudioQueueManager {
  constructor() {
    this.queue = [];
    this.isPlaying = false;
    this.currentAudio = null;
    this.currentBlobUrl = null;
    this.isStreamFinished = false;
    this.onStartCallback = null;
    this.onEndCallback = null;
    this.onSentenceStart = null;
  }

  /**
   * Mulai sesi streaming baru
   */
  startSession({ onStart, onEnd, onSentence }) {
    this.stop();
    this.isStreamFinished = false;
    this.onStartCallback = onStart;
    this.onEndCallback = onEnd;
    this.onSentenceStart = onSentence;
    unlockAudioContext();
  }

  /**
   * Tambahkan potongan audio base64 ke dalam antrean
   */
  enqueue({ audio_base64, format = "audio/wav", sentence = "" }) {
    if (!audio_base64) return;

    try {
      const binaryString = atob(audio_base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: format });
      const blobUrl = URL.createObjectURL(blob);

      this.queue.push({
        blobUrl,
        sentence,
      });

      if (!this.isPlaying) {
        this.playNext();
      }
    } catch (err) {
      console.warn("[AudioQueue] Gagal mengantrekan audio chunk:", err);
    }
  }

  /**
   * Tandai bahwa seluruh kalimat dari LLM sudah selesai dikirim oleh server
   */
  markStreamFinished() {
    this.isStreamFinished = true;
    if (!this.isPlaying && this.queue.length === 0) {
      if (this.onEndCallback) this.onEndCallback();
    }
  }

  /**
   * Putar audio berikutnya dalam antrean
   */
  async playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      this.currentAudio = null;
      if (this.isStreamFinished) {
        if (this.onEndCallback) this.onEndCallback();
      }
      return;
    }

    this.isPlaying = true;
    const item = this.queue.shift();
    this.currentBlobUrl = item.blobUrl;

    const audio = new Audio(item.blobUrl);
    audio.volume = 1.0;
    this.currentAudio = audio;

    // Hubungkan ke Wawa Lipsync agar mulut 3D bergerak mengikuti audio kalimat ini
    connectAudioToLipsync(audio);

    if (this.onSentenceStart) {
      this.onSentenceStart(item.sentence);
    }

    audio.onplay = () => {
      if (this.onStartCallback) {
        this.onStartCallback();
        this.onStartCallback = null; // hanya panggil sekali di awal
      }
    };

    audio.onended = () => {
      URL.revokeObjectURL(item.blobUrl);
      this.playNext();
    };

    audio.onerror = (e) => {
      console.warn("[AudioQueue] Galat pemutaran audio chunk:", e);
      URL.revokeObjectURL(item.blobUrl);
      this.playNext();
    };

    try {
      await audio.play();
    } catch (playErr) {
      console.warn("[AudioQueue] Gagal memutar audio chunk (kebijakan browser):", playErr);
      URL.revokeObjectURL(item.blobUrl);
      this.playNext();
    }
  }

  /**
   * Hentikan seluruh antrean audio seketika (Barge-in / Interupsi)
   */
  stop() {
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } catch (_) {}
      this.currentAudio = null;
    }
    if (this.currentBlobUrl) {
      try {
        URL.revokeObjectURL(this.currentBlobUrl);
      } catch (_) {}
      this.currentBlobUrl = null;
    }
    // Bersihkan semua URL yang belum sempat diputar
    this.queue.forEach((item) => {
      try {
        URL.revokeObjectURL(item.blobUrl);
      } catch (_) {}
    });
    this.queue = [];
    this.isPlaying = false;
    this.isStreamFinished = true;
  }
}

export const audioQueueManager = new AudioQueueManager();
