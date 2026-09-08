import { useState, useRef, useEffect } from "react";
import ChatBubble from "./ChatBubble";
import LiveCaption from "./LiveCaption";
import AvatarPlaceholder from "./AvatarPlaceholder";
import SuggestionButtons from "./SuggestionButtons";
import MediaCarousel from "./MediaCarousel";
import {
  transcribeAudio,
  getChatCompletion,
  speakText,
  stopSpeaking,
  streamChatAndVoice,
  getTimeBasedGreeting,
  archiveConversationSession,
  prepareTranscriptForRag,
  looksLikeShortValidQuery,
} from "../lib/ai";

// ── SVG Icons ────────────────────────────────────────────────────
const IconMic = ({ size = "md" }) => {
  const cls = size === "lg" ? "w-12 h-12" : size === "sm" ? "w-4 h-4" : "w-5 h-5";
  return (
    <svg
      className={`${cls} text-white`}
      fill="currentColor"
      viewBox="0 0 24 24"
    >
      <path d="M12 1a4 4 0 014 4v6a4 4 0 01-8 0V5a4 4 0 014-4zm-1 18v3h2v-3a8.03 8.03 0 005.65-2.35l-1.41-1.41A6 6 0 0112 19a6 6 0 01-4.24-1.76L6.35 18.65A8.03 8.03 0 0011 21z" />
    </svg>
  );
};

const IconKeyboard = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    viewBox="0 0 24 24"
  >
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path
      strokeLinecap="round"
      d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h12"
    />
  </svg>
);

const IconMicToggle = () => (
  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 1a4 4 0 014 4v6a4 4 0 01-8 0V5a4 4 0 014-4zm-1 18v3h2v-3a8.03 8.03 0 005.65-2.35l-1.41-1.41A6 6 0 0112 19a6 6 0 01-4.24-1.76L6.35 18.65A8.03 8.03 0 0011 21z" />
  </svg>
);

const IconSend = () => (
  <svg
    className="w-4 h-4 text-white"
    fill="none"
    stroke="currentColor"
    strokeWidth={2.2}
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M22 2L11 13M22 2L15 22l-4-9-9-4 19-7z"
    />
  </svg>
);

const IconSparkle = () => (
  <svg
    className="w-10 h-10 text-blue-200"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.2}
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
    />
  </svg>
);

const IconChevronDown = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    strokeWidth={2.5}
    viewBox="0 0 24 24"
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

const IconChevronRight = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
);

const IconChat = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
);
// ─────────────────────────────────────────────────────────────────

import { t } from "../lib/translations";

// Quick reply button definitions
const quickReplies = {
  id: [
    {
      label: "📝 Cara Daftar?",
      text: "Bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?",
    },
    {
      label: "💰 Biaya Kuliah",
      text: "Berapa rincian biaya kuliah di UCIC?",
    },
    {
      label: "🎓 Program Studi",
      text: "Apa saja program studi dan jurusan yang ada di UCIC?",
    },
    {
      label: "📍 Kontak & Lokasi",
      text: "Di mana alamat kampus UCIC dan kontak yang bisa dihubungi?",
    },
  ],
  en: [
    {
      label: "📝 How to Register?",
      text: "How do I register as a new student at UCIC?",
    },
    {
      label: "💰 Tuition Fees",
      text: "What are the tuition fees at UCIC?",
    },
    {
      label: "🎓 Study Programs",
      text: "What study programs are offered at UCIC?",
    },
    {
      label: "📍 Contact & Location",
      text: "Where is UCIC campus located and how to contact?",
    },
  ],
};

// ─────────────────────────────────────────────────────────────────
const SILENCE_DURATION = 800; // ms diam setelah ada suara → auto-stop lebih cepat
const MIN_SPEECH_MS = 250; // ms minimum bicara — ramah pertanyaan pendek
const MIN_BLOB_SIZE = 500; // bytes minimum audio
const MAX_RECORD_MS = 25000; // 25 detik maksimal recording sebagai failsafe
const THRESHOLD_MULTIPLIER = 1.6; // Multiplier noise floor → speech threshold (diturunkan agar mic pelan tetap terdeteksi)
const BASELINE_SAMPLE_MS = 400; // ms untuk sample baseline noise
const EARLY_SPEECH_THRESHOLD_MULTIPLIER = 1.25;
const MIN_TRANSCRIPT_CHARS = 2; // izinkan kata pendek (mis. "krs", "pmb", "ya")
const QUICK_COMMIT_SILENCE_MS = 500; // commit cepat setelah speech valid
const QUICK_COMMIT_MIN_SPEECH_MS = 300;
const MIN_RMS_FOR_VALID_SPEECH = 0.8; // Diturunkan: mikrofon laptop/built-in sering RMS rendah
// ── ASR Push-to-Talk (Hanya merekam saat tombol ditekan) ──
const BARGE_IN_AKTIF = false; // Dinonaktifkan: mic tidak live-stream terus-menerus
const BARGE_IN_GRACE_MS = 1200; // abaikan gema speaker di awal TTS
const BARGE_IN_AMBANG_MULTIPLIER = 3.0; // ambang tinggi anti-gema (x threshold normal)
const BARGE_IN_AMBANG_MIN = 12; // lantai ambang barge-in (skala RMS byte-domain)
const BARGE_IN_TAHAN_MS = 400; // suara harus bertahan selama ini → bukan gema sesaat
const IDLE_SESSION_MS = 90 * 1000; // 90 detik tanpa interaksi -> reset sesi
const FACE_LOST_END_MS = 12 * 1000; // 12 detik wajah hilang saat sesi aktif -> reset
// Farewell detection
const FAREWELL_KEYWORDS = [
  "terima kasih",
  "terimakasih",
  "makasih",
  "sampai jumpa",
  "sampai bertemu",
  "selamat tinggal",
  "dadah",
  "bye",
  "thanks",
  "thank you",
];
const isFarewell = (text) =>
  FAREWELL_KEYWORDS.some((kw) => text.toLowerCase().includes(kw));

export default function VoiceUI({
  currentChat,
  onSend,
  onReceive,
  onNewChat,
  onReset,
  lang = "id",
  setLang,
  theme = "light",
}) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [avatarState, setAvatarState] = useState("idle");
  const [micDenied, setMicDenied] = useState(false);
  const [micTidakAktif, setMicTidakAktif] = useState(false); // true jika tidak ada mic hardware
  const [activated, setActivated] = useState(true); // Aktif langsung di aplikasi desktop
  const [isRecordingTypeInput, setIsRecordingTypeInput] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [isWaitingAI, setIsWaitingAI] = useState(false); // loading bubble saat menunggu AI
  const [latestSelaId, setLatestSelaId] = useState(null); // id pesan SELA terbaru → typewriter
  const [langSelected, setLangSelected] = useState(true); // Default terpilih bahasa aktif
  const [awaitingLangSelect, setAwaitingLangSelect] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [latestSpokenText, setLatestSpokenText] = useState("");
  const [showTextInput, setShowTextInput] = useState(false);
  const [showChatPanel, setShowChatPanel] = useState(true);

  const messagesEndRef = useRef(null);
  const chatScrollRef = useRef(null);

  // Refs — tidak pernah stale di dalam callback/closure
  const isListeningRef = useRef(false); // mic sedang merekam
  const isProcessingRef = useRef(false); // sedang transcribe / chat / TTS
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const recorderRef = useRef(null);
  const aiRequestSeqRef = useRef(0);
  const vadFrameRef = useRef(null);
  const silenceStartRef = useRef(null);
  const hasSpeechRef = useRef(false);
  const speechStartRef = useRef(null);
  const firstSpeechDetectedAtRef = useRef(null);
  const baselineStartedAtRef = useRef(null);
  const dynamicThresholdRef = useRef(10); // fallback jika baseline gagal
  const suppressRecorderOnStopRef = useRef(false);
  const lastInteractionTimeRef = useRef(Date.now());
  const sessionEndingRef = useRef(false);
  const currentChatRef = useRef(currentChat);
  const langRef = useRef(lang);
  const siklusRmsTinggiRef = useRef(0); // menghitung berapa kali RMS maksimum siklus terdeteksi
  const rmsMaxSiklusIniRef = useRef(0);  // RMS tertinggi dalam siklus rekaman saat ini

  // Monitor full-duplex barge-in (mic tetap siaga saat SELA bicara)
  const monitorStreamRef = useRef(null);
  const monitorCtxRef = useRef(null);
  const monitorRafRef = useRef(null);
  const bargeInMulaiRef = useRef(0);
  const suaraKuatSejakRef = useRef(null);
  const avatarStateRef = useRef(avatarState);

  // Face detection refs
  const audioUnlockedRef = useRef(false); // true setelah tap pertama, tidak pernah reset
  const activatedRef = useRef(true); // sync dengan activated state (selalu siap di desktop)
  const videoRef = useRef(null);
  const videoStreamRef = useRef(null);
  const faceDetectorRef = useRef(null);
  const faceFrameRef = useRef(null);
  const lastFaceTimeRef = useRef(0);
  const lastDetectRef = useRef(0); // throttle detection ke ~500ms
  const properFaceTimeRef = useRef(null); // timestamp ketika wajah mulai menghadap dengan benar
  const PROPER_FACE_CONFIRMATION_MS = 1000; // 1 detik sebelum auto-activate
  const MIN_FACE_SIZE_RATIO = 0.2; // minimum 20% dari video width (~1m distance untuk kiosk)

  // Sinkronkan refs dengan state
  useEffect(() => {
    avatarStateRef.current = avatarState;
  }, [avatarState]);
  useEffect(() => {
    activatedRef.current = activated;
  }, [activated]);
  useEffect(() => {
    currentChatRef.current = currentChat;
  }, [currentChat]);
  useEffect(() => {
    langRef.current = lang;
  }, [lang]);

  // Kiosk mode — jika URL mengandung ?kiosk=1, langsung unlock audio tanpa tap
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("kiosk") === "1") {
      audioUnlockedRef.current = true;
      console.log(
        "[SELA] Kiosk mode aktif — audio auto-unlocked, menunggu wajah...",
      );
    }
  }, []);

  // Deteksi perangkat mikrofon fisik nyata pada perangkat
  useEffect(() => {
    async function deteksiPerangkatAudio() {
      try {
        if (navigator?.mediaDevices?.enumerateDevices) {
          const daftar = await navigator.mediaDevices.enumerateDevices();
          const adaMikrofon = daftar.some((d) => d.kind === "audioinput");
          if (!adaMikrofon) {
            console.warn("[SELA] Tidak ditemukan perangkat audio input (mikrofon fisik).");
            setMicTidakAktif(true);
          } else {
            setMicTidakAktif(false);
          }
        }
      } catch (err) {
        console.warn("[SELA] Gagal mendeteksi daftar perangkat audio:", err);
      }
    }
    deteksiPerangkatAudio();
    navigator?.mediaDevices?.addEventListener?.("devicechange", deteksiPerangkatAudio);
    return () => {
      navigator?.mediaDevices?.removeEventListener?.("devicechange", deteksiPerangkatAudio);
    };
  }, []);

  // Re-attach camera stream ke video element setiap kali overlay muncul
  // (video element di-unmount saat activated=true, jadi stream hilang)
  useEffect(() => {
    if (!activated && videoRef.current && videoStreamRef.current) {
      videoRef.current.srcObject = videoStreamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [activated]);

  // Auto scroll — hanya kalau user sudah di bawah
  useEffect(() => {
    if (isAtBottom)
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentChat?.messages]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChatScroll = (e) => {
    const el = e.currentTarget;
    setIsAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    setIsAtBottom(true);
  };

  const speakWithAvatar = (text, speechLang = lang, onDone = null) => {
    setLatestSpokenText(text);
    // Interupsi suara: hentikan ucapan SELA
    const handleBargeInSuara = () => {
      stopSpeaking();
      hentikanMonitorBargeIn();
      setAvatarState("idle");
      isProcessingRef.current = false;
    };
    speakText(
      text,
      () => {
        setAvatarState("speaking");
        mulaiMonitorBargeIn(handleBargeInSuara);
      },
      () => {
        hentikanMonitorBargeIn();
        setAvatarState("idle");
        if (onDone) onDone();
      },
      speechLang,
    );
  };

  // ── Monitor barge-in full-duplex: mic siaga anti-gema saat TTS berbunyi ──
  const hentikanMonitorBargeIn = () => {
    if (monitorRafRef.current) cancelAnimationFrame(monitorRafRef.current);
    monitorRafRef.current = null;
    try {
      monitorStreamRef.current?.getTracks().forEach((t) => t.stop());
    } catch (_) {} // eslint-disable-line no-empty
    monitorStreamRef.current = null;
    try {
      monitorCtxRef.current?.close().catch(() => {});
    } catch (_) {} // eslint-disable-line no-empty
    monitorCtxRef.current = null;
    suaraKuatSejakRef.current = null;
  };

  const mulaiMonitorBargeIn = (onBargeIn) => {
    if (!BARGE_IN_AKTIF) return;
    hentikanMonitorBargeIn();
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: { ideal: true },
            noiseSuppression: { ideal: true },
            autoGainControl: { ideal: true },
            channelCount: { ideal: 1 },
          },
        });
        // Batal jika TTS sudah selesai saat izin mic keluar
        if (avatarStateRef?.current === "idle") {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        monitorStreamRef.current = stream;
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        monitorCtxRef.current = ctx;
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        src.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);
        bargeInMulaiRef.current = Date.now();
        suaraKuatSejakRef.current = null;
        // Ambang TINGGI (anti-gema speaker) dari threshold normal terakhir
        const ambang = Math.max(
          (dynamicThresholdRef.current || MIN_RMS_FOR_VALID_SPEECH) *
            BARGE_IN_AMBANG_MULTIPLIER,
          BARGE_IN_AMBANG_MIN,
        );
        const loop = () => {
          if (!monitorStreamRef.current) return;
          analyser.getByteTimeDomainData(data);
          let s = 0;
          for (let i = 0; i < data.length; i++) {
            const d = data[i] - 128;
            s += d * d;
          }
          const rms = Math.sqrt(s / data.length);
          const dalamGrace =
            Date.now() - bargeInMulaiRef.current < BARGE_IN_GRACE_MS;
          if (!dalamGrace && rms > ambang) {
            if (!suaraKuatSejakRef.current) {
              suaraKuatSejakRef.current = Date.now();
            } else if (
              Date.now() - suaraKuatSejakRef.current >=
              BARGE_IN_TAHAN_MS
            ) {
              console.log(
                "[SELA Barge-in] Pengguna memotong ucapan SELA, RMS:",
                rms.toFixed(2),
              );
              hentikanMonitorBargeIn();
              if (onBargeIn) onBargeIn();
              return;
            }
          } else {
            suaraKuatSejakRef.current = null;
          }
          monitorRafRef.current = requestAnimationFrame(loop);
        };
        monitorRafRef.current = requestAnimationFrame(loop);
      } catch (e) {
        console.warn("[SELA Barge-in] Monitor gagal aktif:", e?.message);
      }
    })();
  };

  const speakSequenceWithAvatar = (segments = [], onComplete = null) => {
    const queue = segments.filter((segment) => segment?.text);

    const playNext = (index) => {
      if (index >= queue.length) {
        if (onComplete) onComplete();
        return;
      }

      const segment = queue[index];
      speakWithAvatar(segment.text, segment.lang || lang, () => {
        playNext(index + 1);
      });
    };

    playNext(0);
  };

  const markSessionInteraction = () => {
    lastInteractionTimeRef.current = Date.now();
  };

  const endSessionRef = useRef(null);
  endSessionRef.current = (endReason = "session_end") => {
    if (sessionEndingRef.current) return;
    sessionEndingRef.current = true;
    suppressRecorderOnStopRef.current = true;
    stopListening();
    stopSpeaking();
    hentikanMonitorBargeIn();

    const chatSnapshot = currentChatRef.current;
    if (chatSnapshot?.messages?.length) {
      archiveConversationSession({
        currentChat: chatSnapshot,
        lang: langRef.current,
        endedByFarewell: false,
        endReason,
      });
    }

    isProcessingRef.current = false;
    activatedRef.current = true;
    setActivated(true);
    setAvatarState("idle");
    setLangSelected(true);
    setAwaitingLangSelect(false);
    setFaceDetected(false);
    properFaceTimeRef.current = null;
    lastFaceTimeRef.current = 0;
    if (onReset) onReset();

    setTimeout(() => {
      sessionEndingRef.current = false;
      suppressRecorderOnStopRef.current = false;
      markSessionInteraction();
    }, 250);
  };

  // Track ID pesan SELA terbaru → untuk typewriter effect
  useEffect(() => {
    const msgs = currentChat?.messages ?? [];
    const last = msgs[msgs.length - 1];
    if (last && last.role === "assistant") {
      setLatestSelaId(last.id);
    }
  }, [currentChat?.messages?.length]);

  // ── autoActivate ref (untuk dibaca dari closure detection loop) ─
  const autoActivateRef = useRef(null);
  autoActivateRef.current = () => {
    if (activatedRef.current || isProcessingRef.current) return;
    activatedRef.current = true;
    isProcessingRef.current = true;
    markSessionInteraction();
    setActivated(true);
    setLangSelected(false);
    setAwaitingLangSelect(false);

    // Sapa dalam Bahasa Indonesia dulu
    const greetID = "Halo! Selamat datang di UCIC. Saya SELA.";
    const askID = "Mau bicara dalam Bahasa Indonesia atau Bahasa Inggris?";
    const greetEN = "Hello! Welcome to UCIC. I'm SELA.";
    const askEN = "Would you like to speak in Indonesian or English?";

    speakSequenceWithAvatar(
      [
        { text: greetID, lang: "id" },
        { text: greetEN, lang: "en" },
        { text: askID, lang: "id" },
        { text: askEN, lang: "en" },
      ],
      () => {
        isProcessingRef.current = false;
        setAvatarState("idle");
        setAwaitingLangSelect(true);
      },
    );
  };

  // ── Face detection (kamera) ───────────────────────────────────
  // Dinonaktifkan sementara sesuai instruksi pengguna (komputer tanpa webcam)
  useEffect(() => {
    setFaceDetected(true);
  }, []);

  // Bersihkan monitor barge-in saat komponen dilepas
  useEffect(() => {
    return () => {
      hentikanMonitorBargeIn();
    };
  }, []);

  // ── Stop & cleanup ────────────────────────────────────────────
  const stopListening = () => {
    isListeningRef.current = false;
    cancelAnimationFrame(vadFrameRef.current);
    if (recorderRef.current?.state !== "inactive") {
      recorderRef.current?.stop();
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    analyserRef.current = null;
    silenceStartRef.current = null;
    hasSpeechRef.current = false;
    speechStartRef.current = null;
    firstSpeechDetectedAtRef.current = null;
    baselineStartedAtRef.current = null;
  };

  // ── Kontrol Tombol Suara Speak Mode ──────────────────────────
  const handleToggleVoice = () => {
    if (avatarState === "speaking") {
      stopSpeaking();
      setAvatarState("idle");
      isProcessingRef.current = false;
      return;
    }
    if (isListeningRef.current) {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        hasSpeechRef.current = true;
        if (!speechStartRef.current) speechStartRef.current = Date.now() - 600;
        recorderRef.current.stop();
      }
      return;
    }
    if (avatarState === "thinking" || isProcessingRef.current) {
      return;
    }
    startListeningRef.current?.();
  };

  // ── Kontrol Tombol Suara Type Mode ───────────────────────────
  const typeRecorderRef = useRef(null);
  const typeStreamRef = useRef(null);

  const handleToggleTypeMic = async () => {
    if (isRecordingTypeInput) {
      if (typeRecorderRef.current && typeRecorderRef.current.state !== "inactive") {
        typeRecorderRef.current.stop();
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      typeStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      typeRecorderRef.current = recorder;
      const chunks = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      recorder.onstop = async () => {
        setIsRecordingTypeInput(false);
        stream.getTracks().forEach((t) => t.stop());
        const audioBlob = new Blob(chunks, { type: "audio/webm" });
        if (audioBlob.size > 400) {
          try {
            setAvatarState("thinking");
            const rawText = await transcribeAudio(audioBlob, lang);
            if (rawText && rawText.trim()) {
              handleSubmit(rawText.trim());
            } else {
              setAvatarState("idle");
            }
          } catch (err) {
            console.error("Transcribe error:", err);
            setAvatarState("idle");
          }
        } else {
          setAvatarState("idle");
        }
      };

      recorder.start();
      setIsRecordingTypeInput(true);
      setAvatarState("listening");
    } catch (err) {
      console.error("Mic error:", err);
      alert(lang === "id" ? "Gagal mengakses mikrofon. Pastikan izin mikrofon aktif." : "Failed to access microphone.");
    }
  };

  // ── Start auto-listen ─────────────────────────────────────────
  // Pakai fungsi biasa (bukan useCallback) yang disimpan di ref,
  // supaya pemanggil di dalam closure selalu dapat versi terbaru.
  const startListeningRef = useRef(null);
  startListeningRef.current = async () => {
    // Cek via ref — tidak pernah stale
    if (isListeningRef.current || isProcessingRef.current) return;

    try {
      // ── Aggressive audio constraints untuk noisy environments ──
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: { ideal: true },
          noiseSuppression: { ideal: true },
          autoGainControl: { ideal: true },
          channelCount: { ideal: 1 }, // Mono untuk lebih fokus
          sampleRate: { ideal: 16000 }, // Optimal untuk speech recognition
          sampleSize: { ideal: 16 },
          latency: { ideal: 0.01 },
        },
      });
      streamRef.current = stream;
      setMicDenied(false);
      setMicTidakAktif(false);
      isListeningRef.current = true;

      // AudioContext + Analyser untuk VAD
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      analyserRef.current = analyser;

      // MediaRecorder
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      let chunks = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      recorder.onstop = () => {
        if (suppressRecorderOnStopRef.current) {
          chunks = [];
          stopListening();
          suppressRecorderOnStopRef.current = false;
          return;
        }
        const speechDuration = speechStartRef.current
          ? Date.now() - speechStartRef.current
          : 0;
        const audioBlob = new Blob(chunks, { type: "audio/webm" });
        const hadSpeech = hasSpeechRef.current;
        
        if (
          !hadSpeech ||
          speechDuration < MIN_SPEECH_MS ||
          audioBlob.size < MIN_BLOB_SIZE
        ) {
          console.log("[SELA] Skip — noise/pendek/kecil:", {
            hadSpeech,
            speechDuration,
            blobSize: audioBlob.size,
          });

          // Siklus hening/noise biasa — kembali ke idle (tidak auto-restart)
          rmsMaxSiklusIniRef.current = 0;
          setAvatarState("idle");
          stopListening();
          return;
        }

        console.log(
          "[SELA] recorder.onstop | hadSpeech:",
          hadSpeech,
          "| speechDuration:",
          speechDuration,
          "ms | firstSpeechDelay:",
          firstSpeechDetectedAtRef.current && baselineStartedAtRef.current
            ? firstSpeechDetectedAtRef.current - baselineStartedAtRef.current
            : null,
          "ms | blobSize:",
          audioBlob.size,
        );
        stopListening();

        if (
          !hadSpeech ||
          speechDuration < MIN_SPEECH_MS ||
          audioBlob.size < MIN_BLOB_SIZE
        ) {
          console.log("[SELA] Skip — noise/pendek/kecil:", {
            hadSpeech,
            speechDuration,
            blobSize: audioBlob.size,
          });
          setAvatarState("idle");
          return;
        }

        // Ada suara valid → proses
        console.log("[SELA] Ada suara valid, mulai processing...");
        processAudioRef.current(audioBlob);
      };

      recorder.start(100);
      setAvatarState("listening");
      baselineStartedAtRef.current = Date.now();

      // Failsafe: force stop setelah MAX_RECORD_MS
      const maxTimer = setTimeout(() => {
        if (recorderRef.current?.state !== "inactive")
          recorderRef.current.stop();
      }, MAX_RECORD_MS);

      // ── Baseline sampling phase (500ms) ────────────────────
      const data = new Uint8Array(analyser.fftSize);
      let baselineRmsValues = [];

      const baselineCheck = () => {
        if (!isListeningRef.current) return;

        analyser.getByteTimeDomainData(data);
        const rms = Math.sqrt(
          data.reduce((s, v) => s + (v - 128) * (v - 128), 0) / data.length,
        );
        baselineRmsValues.push(rms);
        const avgSoFar =
          baselineRmsValues.reduce((a, b) => a + b, 0) /
          baselineRmsValues.length;
        const provisionalThreshold = Math.max(
          MIN_RMS_FOR_VALID_SPEECH,
          avgSoFar * EARLY_SPEECH_THRESHOLD_MULTIPLIER,
        );

        if (rms > provisionalThreshold && !hasSpeechRef.current) {
          hasSpeechRef.current = true;
          speechStartRef.current = Date.now();
          firstSpeechDetectedAtRef.current = speechStartRef.current;
          dynamicThresholdRef.current = Math.max(
            MIN_RMS_FOR_VALID_SPEECH,
            avgSoFar * THRESHOLD_MULTIPLIER,
          );
          console.log("[SELA VAD] Early speech detected during baseline", {
            rms: Number(rms.toFixed(2)),
            provisionalThreshold: Number(provisionalThreshold.toFixed(2)),
            threshold: Number(dynamicThresholdRef.current.toFixed(2)),
          });
          startActualVAD();
          return;
        }

        if (Date.now() - baselineStartedAtRef.current < BASELINE_SAMPLE_MS) {
          vadFrameRef.current = requestAnimationFrame(baselineCheck);
        } else {
          const avgBaseline =
            baselineRmsValues.reduce((a, b) => a + b, 0) /
            baselineRmsValues.length;

          // Calculate baseline variance — stable/low variance = noise floor
          const variance =
            baselineRmsValues.reduce(
              (sq, x) => sq + (x - avgBaseline) * (x - avgBaseline),
              0,
            ) / baselineRmsValues.length;

          dynamicThresholdRef.current = Math.max(
            MIN_RMS_FOR_VALID_SPEECH,
            avgBaseline * THRESHOLD_MULTIPLIER,
          );
          console.log(
            "[SELA VAD] Baseline:",
            avgBaseline.toFixed(2),
            "| Variance:",
            variance.toFixed(2),
            "→ Dynamic Threshold:",
            dynamicThresholdRef.current.toFixed(2),
          );
          startActualVAD();
        }
      };

      // Start baseline sampling
      vadFrameRef.current = requestAnimationFrame(baselineCheck);

      // ── Actual VAD loop ────────────────────────────────────
      const startActualVAD = () => {
        let logThrottle = 0;
        const checkSilence = () => {
          if (!isListeningRef.current) {
            clearTimeout(maxTimer);
            return;
          }
          analyser.getByteTimeDomainData(data);
          // Nilai time-domain: 128 = silence, deviation dari 128 = ada suara
          const rms = Math.sqrt(
            data.reduce((s, v) => s + (v - 128) * (v - 128), 0) / data.length,
          );

          // Log RMS setiap ~500ms supaya bisa debug threshold
          logThrottle++;
          if (logThrottle % 30 === 0)
            console.log(
              "[SELA VAD] RMS:",
              rms.toFixed(2),
              "| threshold:",
              dynamicThresholdRef.current.toFixed(2),
              "| hasSpeech:",
              hasSpeechRef.current,
            );
          // Lacak RMS maksimum siklus ini untuk deteksi mikrofon tidak aktif
          if (rms > rmsMaxSiklusIniRef.current) {
            rmsMaxSiklusIniRef.current = rms;
          }

          if (rms > dynamicThresholdRef.current) {

            if (!hasSpeechRef.current) {
              hasSpeechRef.current = true;
              speechStartRef.current = Date.now();
              firstSpeechDetectedAtRef.current = speechStartRef.current;
              console.log("[SELA VAD] Speech detected! RMS:", rms.toFixed(2));
            }
            silenceStartRef.current = null;
          } else if (hasSpeechRef.current) {
            if (!silenceStartRef.current) {
              silenceStartRef.current = Date.now();
              console.log("[SELA VAD] Silence window started");
            } else if (
              Date.now() - silenceStartRef.current >
              (speechStartRef.current &&
              Date.now() - speechStartRef.current >= QUICK_COMMIT_MIN_SPEECH_MS
                ? QUICK_COMMIT_SILENCE_MS
                : SILENCE_DURATION)
            ) {
              // Diam cukup lama → stop otomatis
              console.log("[SELA VAD] Auto-stop commit", {
                speechMs: speechStartRef.current
                  ? Date.now() - speechStartRef.current
                  : 0,
                silenceMs: Date.now() - silenceStartRef.current,
              });
              clearTimeout(maxTimer);
              if (recorderRef.current?.state !== "inactive") {
                recorderRef.current.stop();
              }
              return;
            }
          }
          vadFrameRef.current = requestAnimationFrame(checkSilence);
        };
        vadFrameRef.current = requestAnimationFrame(checkSilence);
      };
    } catch (err) {
      console.error("[SELA] Mic error:", err);
      if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        setMicTidakAktif(true);
        setMicDenied(false);
      } else if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setMicDenied(true);
        setMicTidakAktif(false);
      } else {
        setMicDenied(true);
      }
      setAvatarState("idle");
      isListeningRef.current = false;
    }
  };

  // ── Penanganan Interaksi Asisten (RAG Anti-Halusinasi Cepat & Responsif) ──
  const handleAssistantInteraction = async (userText, isVoice = false) => {
    setIsWaitingAI(true);
    isProcessingRef.current = true;
    setAvatarState("thinking");
    const requestId = ++aiRequestSeqRef.current;

    const history = (currentChat?.messages || []).map((m) => ({
      role: m.role,
      content: m.text,
    }));
    history.push({ role: "user", content: userText });

    try {
      // 1. Eksekusi RAG Anti-Halusinasi & Pencocokan Fakta Kampus UCIC
      const response = await getChatCompletion(history, lang);
      if (requestId !== aiRequestSeqRef.current) return;
      setIsWaitingAI(false);

      if (response.text?.includes("[IGNORE_NOISE]")) {
        console.log("[SELA] AI mendeteksi noise/obrolan acak, mengabaikan input.");
        isProcessingRef.current = false;
        setAvatarState("idle");
        return;
      }

      // 2. Tampilkan pesan asisten di layar secara instan (bubble, suggestion buttons, media)
      if (onReceive) onReceive(response);
      markSessionInteraction();

      // 3. Sintesis suara cepat (< 80ms) + Wawa Lipsync
      const spokenText = response.spokenText || response.text;
      setLatestSpokenText(spokenText);
      speakWithAvatar(
        spokenText,
        response.detectedLang || lang,
        () => {
          isProcessingRef.current = false;
        },
      );
    } catch (err) {
      console.error("[SELA Interaction] Kendala pemrosesan jawaban:", err);
      if (requestId !== aiRequestSeqRef.current) return;
      setIsWaitingAI(false);
      if (onReceive) onReceive(t[lang].error_network);
      setAvatarState("idle");
      isProcessingRef.current = false;
    }
  };

  // ── Process audio → transcribe → AI → TTS ────────────────────
  // Juga disimpan di ref supaya startListening bisa memanggilnya
  const processAudioRef = useRef(null);
  processAudioRef.current = async (audioBlob) => {
    isProcessingRef.current = true;
    setAvatarState("thinking");
    try {
      const rawText = await transcribeAudio(audioBlob, lang);

      // Check if server filtered out background audio
      if (!rawText || rawText.trim().length === 0) {
        console.log("[SELA] Server filtered out background audio");
        isProcessingRef.current = false;
        setAvatarState("idle");
        return;
      }

      const preparedTranscript = prepareTranscriptForRag(rawText);
      const text = preparedTranscript.cleanedText;
      console.log("[SELA Voice] Transcript pipeline:", {
        rawText: preparedTranscript.rawText,
        cleanedText: preparedTranscript.cleanedText,
        marker: preparedTranscript.marker,
        removedSegments: preparedTranscript.removedSegments,
      });

      // 1. Filter Client-Side: Hanya buang jika benar-benar kosong atau suara gumaman/filler mikrofon
      const trimmedText = text?.trim() || "";
      const isNoise =
        !trimmedText ||
        trimmedText.length < 2 ||
        /^(uh|um|ah|eh|oh|hmm|hm|mm|m)$/i.test(trimmedText);

      if (isNoise) {
        console.log("[SELA] Diabaikan (filler mikrofon):", text);
        isProcessingRef.current = false;
        setAvatarState("idle");
        return;
      }

      markSessionInteraction();
      if (isFarewell(text)) {
        handleFarewell(text);
        return;
      }

      onSend(text);
      await handleAssistantInteraction(text, true);
    } catch (error) {
      console.error(error);
      setIsWaitingAI(false);
      if (onReceive) onReceive(t[lang].error_stt);
      setAvatarState("idle");
      isProcessingRef.current = false;
    }
  };

  // ── Bersihkan audio saat unmount (tidak auto-listen) ──────────
  useEffect(() => {
    stopListening();
    stopSpeaking();
    hentikanMonitorBargeIn();
    setAvatarState("idle");
    isProcessingRef.current = false;
    return () => {
      stopListening();
      stopSpeaking();
      hentikanMonitorBargeIn();
      isProcessingRef.current = false;
    };
  }, [activated]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (!activatedRef.current || sessionEndingRef.current) return;
      // Jangan reset sesi jika tidak ada mikrofon (micTidakAktif) — biarkan pengguna chat via teks
      if (micTidakAktif) return;
      if (isListeningRef.current || isProcessingRef.current) return;
      if (Date.now() - lastInteractionTimeRef.current > IDLE_SESSION_MS) {
        console.log("[SELA Session] Sesi diakhiri karena idle timeout");
        endSessionRef.current?.("idle_timeout");
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [micTidakAktif]);

  // ── Farewell handler ──────────────────────────────────────────
  const handleFarewell = (userText) => {
    aiRequestSeqRef.current++;
    setIsWaitingAI(false);
    markSessionInteraction();
    onSend(userText);
    stopListening();
    stopSpeaking();
    isProcessingRef.current = true;

    const farewellChat = currentChat
      ? {
          ...currentChat,
          messages: [
            ...(currentChat.messages || []),
            { role: "user", text: userText, ts: new Date() },
          ],
        }
      : null;

    const msg =
      lang === "id"
        ? "Sama-sama! Senang bisa membantu. Selamat datang kembali kapan saja ya!"
        : "You're welcome! Happy to help. Feel free to come back anytime!";

    if (onReceive) onReceive(msg);

    // Fallback jika TTS onEnd tidak terpanggil (Chrome bug)
    const farewellFallback = setTimeout(() => {
      archiveConversationSession({
        currentChat: farewellChat,
        lang,
        endedByFarewell: true,
        endReason: "farewell",
      });
      isProcessingRef.current = false;
      activatedRef.current = true;
      setAvatarState("idle");
      setActivated(true);
      if (onReset) onReset();
    }, 6000);

    speakWithAvatar(
      msg,
      lang,
      () => {
        clearTimeout(farewellFallback);
        archiveConversationSession({
          currentChat: farewellChat,
          lang,
          endedByFarewell: true,
          endReason: "farewell",
        });
        isProcessingRef.current = false;
        activatedRef.current = true;
        setAvatarState("idle");
        setActivated(true);
        setLangSelected(true);
        setAwaitingLangSelect(false);
        if (onReset) onReset();
      },
    );
  };

  // ── Type mode ─────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    let textToSubmit = value;

    // Handle both form event and direct string call (from quick replies/suggestions)
    if (typeof e === "string") {
      // Direct call with text
      textToSubmit = e;
      setValue("");
      e = { preventDefault: () => {} };
    } else {
      e.preventDefault();
    }

    if (!textToSubmit.trim()) return;
    const userText = textToSubmit.trim();
    markSessionInteraction();
    setValue("");
    setIsAtBottom(true);
    if (isFarewell(userText)) {
      handleFarewell(userText);
      return;
    }
    onSend(userText);

    // Pesan pertama & bahasa belum dipilih → tampilkan bilingual greeting
    if (!langSelected && (currentChat?.messages ?? []).length === 0) {
      const greetID = "Hai, apa yang bisa SELA bantu hari ini, nih?";
      const greetEN = "Hello! How can I help you today?";
      const askID = "Mau bicara dalam Bahasa Indonesia atau Bahasa Inggris?";
      const askEN = "Would you like to speak in Indonesian or English?";
      const combined = `${greetID}\n\n${greetEN}\n\n${askID}\n\n${askEN}`;
      if (onReceive) onReceive(combined);
      setAwaitingLangSelect(false);
      speakSequenceWithAvatar(
        [
          { text: greetID, lang: "id" },
          { text: greetEN, lang: "en" },
          { text: askID, lang: "id" },
          { text: askEN, lang: "en" },
        ],
        () => {
          setAvatarState("idle");
          setAwaitingLangSelect(true);
        },
      );
      return;
    }

    await handleAssistantInteraction(userText, false);
  };

  // ── Pilih bahasa saat greeting ────────────────────────────────
  const handleLangSelect = (chosen) => {
    markSessionInteraction();
    if (setLang) setLang(chosen);
    setLangSelected(true);
    setAwaitingLangSelect(false);
    stopSpeaking();
    isProcessingRef.current = false;
    const langLabel = chosen === "id" ? "🇮🇩 Bahasa Indonesia" : "🇬🇧 English";

    // Use time-based greeting instead of static message
    const timeBasedGreeting = getTimeBasedGreeting(chosen);
    onSend(langLabel);
    if (onReceive) onReceive(timeBasedGreeting);
    setLatestSpokenText(timeBasedGreeting);
    speakWithAvatar(
      timeBasedGreeting,
      chosen,
      () => {
        setAvatarState("idle");
      },
    );
  };

  const statusLabel = () => {
    if (micDenied)
      return lang === "id"
        ? "Izin mikrofon ditolak"
        : "Microphone permission denied";
    switch (avatarState) {
      case "listening":
        return t[lang].listening;
      case "thinking":
        return lang === "id" ? "Sedang berpikir..." : "Thinking...";
      case "speaking":
        return lang === "id" ? "SELA sedang bicara..." : "SELA is speaking...";
      default:
        return lang === "id" ? "Siap mendengarkan" : "Ready to listen";
    }
  };

  const messages = currentChat?.messages ?? [];

  return (
    <main className="flex-1 relative flex flex-col overflow-hidden">
      {/* 3D Avatar full screen background */}
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="pointer-events-auto w-full h-full">
          <AvatarPlaceholder state={avatarState} theme={theme} />
        </div>
      </div>

      {/* Hidden Camera video element */}
      <div className="absolute opacity-0 pointer-events-none overflow-hidden w-1 h-1">
        <video ref={videoRef} muted playsInline autoPlay />
      </div>

      {/* Tombol Terapung Buka Chat Panel (Muncul saat bilah chat disembunyikan) */}
      {!showChatPanel && (
        <button
          type="button"
          onClick={() => setShowChatPanel(true)}
          className="absolute top-4 right-4 z-30 flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-white/85 dark:bg-slate-900/85 backdrop-blur-xl border border-white/60 dark:border-slate-700/60 shadow-xl hover:shadow-2xl hover:scale-105 active:scale-95 text-xs font-semibold text-gray-800 dark:text-gray-100 transition-all cursor-pointer group"
          title="Buka bilah chat"
        >
          <span className="p-1.5 rounded-lg bg-blue-500/15 text-blue-600 dark:text-blue-400 group-hover:bg-blue-500 group-hover:text-white transition-all">
            <IconChat />
          </span>
          <span>{lang === "id" ? "Buka Chat" : "Open Chat"}</span>
          {messages.length > 0 && (
            <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-600 text-white">
              {messages.length}
            </span>
          )}
        </button>
      )}

      {/* Bilah Chat Kanan Interaktif (Bisa Disembunyikan / Dimunculkan) */}
      <div
        className={`absolute top-3 right-4 bottom-3 w-[calc(100%-32px)] sm:w-[380px] lg:w-[420px] max-w-[420px] flex flex-col justify-between p-4 rounded-3xl bg-white/85 dark:bg-slate-900/90 backdrop-blur-2xl border border-white/60 dark:border-slate-700/60 shadow-2xl z-30 transition-all duration-300 ease-out overflow-hidden ${
          showChatPanel
            ? "translate-x-0 opacity-100 pointer-events-auto"
            : "translate-x-[115%] opacity-0 pointer-events-none"
        }`}
      >
        {/* Header Panel Kanan */}
        <div className="flex items-center justify-between pb-2.5 border-b border-gray-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-bold tracking-wider text-gray-800 dark:text-gray-200 uppercase">
              SELA Asisten UCIC
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {messages.length > 0 && (
              <button
                type="button"
                onClick={onNewChat}
                className="text-[11px] px-2.5 py-1 rounded-full text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/60 hover:bg-blue-100 dark:hover:bg-blue-900/60 font-semibold transition-all cursor-pointer"
                title="Mulai sesi percakapan baru"
              >
                {lang === "id" ? "+ Sesi Baru" : "+ New Chat"}
              </button>
            )}
            {/* Tombol Sembunyikan Bilah Chat */}
            <button
              type="button"
              onClick={() => setShowChatPanel(false)}
              className="p-1.5 rounded-xl hover:bg-gray-100 dark:hover:bg-slate-800 text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-all cursor-pointer"
              title="Sembunyikan bilah chat"
            >
              <IconChevronRight />
            </button>
          </div>
        </div>

        {/* Area Konten Chat / Tampilan Awal (Empty State) */}
        <div className="flex-1 overflow-hidden relative flex flex-col justify-end my-2">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center my-auto text-center gap-4 py-4 px-2 animate-fade-in">
              <div className="p-3.5 rounded-2xl bg-blue-50 dark:bg-slate-800/90 text-blue-500 shadow-inner">
                <IconSparkle />
              </div>
              <div>
                <h3 className="text-3xl font-light text-gray-800 dark:text-gray-100 tracking-tight italic font-serif">
                  SELA
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 font-medium">
                  {lang === "id"
                    ? "Ketik pesan, pilih topik, atau gunakan audio"
                    : "Type a message, pick a topic, or use voice"}
                </p>
              </div>

              {/* Tombol Cepat Pertanyaan Populer */}
              <div className="w-full mt-2">
                <p className="text-[10px] text-gray-400 dark:text-gray-500 mb-2.5 font-bold uppercase tracking-widest">
                  {lang === "id" ? "PERTANYAAN POPULER" : "POPULAR QUESTIONS"}
                </p>
                <div className="flex flex-col gap-2 w-full">
                  {quickReplies[lang]?.map((qr, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        handleSubmit(qr.text);
                      }}
                      className="w-full py-2.5 px-3.5 rounded-xl bg-white hover:bg-slate-50 dark:bg-slate-800/90 dark:hover:bg-slate-750 text-slate-700 dark:text-slate-100 hover:text-blue-700 dark:hover:text-blue-300 border border-slate-200/90 dark:border-slate-700/80 hover:border-blue-300 dark:hover:border-blue-500/40 text-xs font-medium shadow-sm hover:shadow active:scale-[0.98] transition-all text-left flex items-center justify-between gap-2 cursor-pointer group"
                    >
                      <span className="truncate">{qr.label}</span>
                      <svg className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 shrink-0 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div
              ref={chatScrollRef}
              onScroll={handleChatScroll}
              className="flex-1 overflow-y-auto pr-1 flex flex-col gap-1 hide-scrollbar"
            >
              {messages.map((msg) => (
                <div key={msg.id}>
                  <ChatBubble
                    role={msg.role}
                    text={msg.text}
                    lang={lang}
                    isNew={msg.role === "assistant" && msg.id === latestSelaId}
                    isSpeaking={avatarState === "speaking" && msg.id === latestSelaId}
                  />
                  {msg.role === "assistant" &&
                    msg.suggestions &&
                    msg.suggestions.length > 0 && (
                      <SuggestionButtons
                        suggestions={msg.suggestions}
                        onClick={(suggestion) => handleSubmit(suggestion)}
                        isVisible
                      />
                    )}
                  {msg.role === "assistant" &&
                    msg.media &&
                    msg.media.length > 0 && <MediaCarousel media={msg.media} />}
                </div>
              ))}
              {isWaitingAI && (
                <ChatBubble role="assistant" text="" lang={lang} isLoading />
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Tombol Scroll ke Bawah */}
          {!isAtBottom && messages.length > 0 && (
            <button
              type="button"
              onClick={scrollToBottom}
              className="absolute bottom-2 left-1/2 -translate-x-1/2 z-30 w-8 h-8 rounded-full
                bg-white/95 dark:bg-slate-800/95 border border-gray-200 dark:border-slate-700
                shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300
                hover:bg-white dark:hover:bg-slate-700 active:scale-95 transition-all animate-fade-in cursor-pointer"
              title="Gulir ke bawah"
            >
              <IconChevronDown />
            </button>
          )}
        </div>

        {/* Quick chips bila pesan sudah ada */}
        {messages.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar py-1 mb-1 z-10">
            {quickReplies[lang]?.map((qr, idx) => (
              <button
                key={idx}
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleSubmit(qr.text);
                }}
                className="whitespace-nowrap text-[11px] font-medium px-3 py-1 rounded-lg bg-blue-50 dark:bg-slate-800 text-blue-600 dark:text-blue-300 border border-blue-200/60 dark:border-slate-700 hover:bg-blue-100 dark:hover:bg-slate-700 transition-all flex-shrink-0 active:scale-95 cursor-pointer"
              >
                {qr.label}
              </button>
            ))}
          </div>
        )}

        {/* Bilah Form Input Ketik & Tombol Rekam Suara Langsung di Panel Kanan */}
        <form onSubmit={handleSubmit} className="relative w-full pt-1">
          <input
            id="side-main-input"
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={
              avatarState === "listening"
                ? (lang === "id" ? "🎙️ Sedang mendengarkan... Silakan bicara!" : "🎙️ Listening... Speak now!")
                : (lang === "id" ? "Ketik pesan untuk Sela..." : "Type a message...")
            }
            className={`w-full bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border rounded-2xl pl-3.5 pr-11 py-2.5
                        text-gray-800 dark:text-gray-100 text-xs placeholder-gray-400 outline-none shadow-sm
                        transition-all duration-200
                        ${
                          avatarState === "listening"
                            ? "border-red-400 ring-4 ring-red-400/30 animate-pulse shadow-red-200"
                            : focused
                            ? "border-blue-500 ring-2 ring-blue-200 dark:ring-blue-900"
                            : "border-gray-200 dark:border-slate-700"
                        }`}
          />
          <button
            id="side-send-btn"
            type={value.trim() ? "submit" : "button"}
            onClick={value.trim() ? undefined : handleToggleVoice}
            className={`absolute right-1.5 top-1/2 -translate-y-1/2 w-8 h-8 rounded-xl flex items-center justify-center shadow-md transition-all active:scale-95 cursor-pointer ${
              value.trim()
                ? "bg-blue-600 hover:bg-blue-700 text-white shadow-blue-500/30"
                : avatarState === "listening"
                ? "bg-red-500 hover:bg-red-600 text-white animate-pulse ring-2 ring-red-400 shadow-red-500/30"
                : "bg-blue-600 hover:bg-blue-700 text-white shadow-blue-500/20"
            }`}
            title={
              value.trim()
                ? "Kirim pesan teks"
                : avatarState === "listening"
                ? "Sedang mendengarkan... Klik untuk selesai dan kirim"
                : "Bicara lewat mikrofon"
            }
          >
            {value.trim() ? (
              <IconSend />
            ) : avatarState === "listening" ? (
              <svg className="w-3.5 h-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
            ) : (
              <IconMic size="sm" />
            )}
          </button>
        </form>
      </div>

      {/* Live Caption Terapung di Tengah (Tampil saat bilah chat disembunyikan) */}
      {!showChatPanel && (
        <div className="absolute bottom-44 left-1/2 -translate-x-1/2 w-full max-w-2xl z-20 pointer-events-none px-4 flex flex-col items-center">
          <LiveCaption
            text={latestSpokenText}
            isLoading={isWaitingAI}
            avatarState={avatarState}
          />
        </div>
      )}

      {/* Tombol Cepat Topik Populer Terapung (Tampil saat bilah chat disembunyikan) */}
      {!showChatPanel && (
        <div className="absolute bottom-28 left-1/2 -translate-x-1/2 z-20 flex items-center justify-center gap-2 max-w-2xl flex-wrap px-4 pointer-events-auto">
          {quickReplies[lang]?.map((qr, idx) => (
            <button
              key={idx}
              type="button"
              onClick={(e) => {
                e.preventDefault();
                handleSubmit(qr.text);
              }}
              className="px-3.5 py-1.5 rounded-full bg-white/80 dark:bg-slate-900/80 hover:bg-blue-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 border border-slate-200/80 dark:border-slate-700/80 shadow-md backdrop-blur-md text-xs font-semibold active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
            >
              <span>{qr.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Bottom Voice Action Button & Status (TERPUSAT PERSIS DI TENGAH DEPAN 3D AVATAR) */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-2 pointer-events-auto max-w-xs">
        {/* Tombol Suara Utama */}
        <button
          id="voice-action-btn"
          type="button"
          onClick={handleToggleVoice}
          className={`relative w-20 h-20 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 transform active:scale-95 cursor-pointer ${
            avatarState === "listening"
              ? "bg-red-500 shadow-red-500/50 animate-pulse ring-8 ring-red-400/30 text-white"
              : avatarState === "speaking"
              ? "bg-amber-500 shadow-amber-500/50 animate-pulse ring-8 ring-amber-400/30 text-white"
              : avatarState === "thinking"
              ? "bg-indigo-600 shadow-indigo-500/50 ring-4 ring-indigo-300/30 text-white"
              : "bg-blue-600 shadow-xl shadow-blue-600/30 hover:bg-blue-700 hover:scale-105 ring-4 ring-blue-200/60 dark:ring-blue-900/40 text-white"
          }`}
          title={
            avatarState === "listening"
              ? "Sedang merekam suara... Klik untuk mengirim sekarang"
              : avatarState === "speaking"
              ? "SELA sedang bicara... Klik untuk memotong (interupsi)"
              : "Klik untuk mulai berbicara"
          }
        >
          {avatarState === "speaking" ? (
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
            </svg>
          ) : avatarState === "thinking" ? (
            <svg className="w-8 h-8 text-white animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <IconMic size="lg" />
          )}
        </button>

        <p className="text-xs font-semibold tracking-wide text-gray-700 dark:text-gray-200">
          {avatarState === "listening"
            ? (lang === "id" ? "🎙️ Mendengarkan... (Bicara atau Klik untuk Kirim)" : "🎙️ Listening... (Speak or Click to Send)")
            : avatarState === "speaking"
            ? (lang === "id" ? "🔊 SELA Sedang Bicara (Klik untuk Potong)" : "🔊 SELA is Speaking (Click to Interrupt)")
            : avatarState === "thinking"
            ? (lang === "id" ? "⏳ Sedang Memproses Ucapan..." : "⏳ Processing Speech...")
            : (lang === "id" ? "🎙️ Klik untuk Berbicara" : "🎙️ Click to Speak")}
        </p>

        <p className="text-xs text-gray-400 dark:text-gray-500 font-bold uppercase tracking-tighter text-center">
          {statusLabel()}
        </p>

        {micDenied && (
          <button
            type="button"
            onClick={() => {
              setMicDenied(false);
              startListeningRef.current?.();
            }}
            className="text-xs text-blue-500 underline cursor-pointer"
          >
            {lang === "id" ? "Coba lagi izin mikrofon" : "Retry mic permission"}
          </button>
        )}

        {/* Banner info mikrofon tidak terdeteksi */}
        {micTidakAktif && !micDenied && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/10 border border-amber-400/30 rounded-xl text-center animate-fade-in">
            <span className="text-sm">🎤</span>
            <p className="text-[11px] font-medium text-amber-700 dark:text-amber-300">
              {lang === "id"
                ? "Mikrofon tidak terdeteksi. Silakan ketik pesan di bilah kanan."
                : "No mic detected. Please type in the right chat panel."}
            </p>
          </div>
        )}

        {/* Tombol pilihan bahasa jika greeting meminta bahasa */}
        {awaitingLangSelect && !langSelected && avatarState === "idle" && (
          <div className="flex gap-2 animate-fade-in mt-1">
            <button
              type="button"
              onClick={() => handleLangSelect("id")}
              className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-blue-500 hover:bg-blue-600 active:scale-95 text-white shadow transition-all cursor-pointer"
            >
              🇮🇩 Indonesia
            </button>
            <button
              type="button"
              onClick={() => handleLangSelect("en")}
              className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-gray-50 active:scale-95 text-gray-700 border border-gray-200 shadow dark:bg-slate-700 dark:text-gray-100 dark:border-slate-600 transition-all cursor-pointer"
            >
              🇬🇧 English
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
