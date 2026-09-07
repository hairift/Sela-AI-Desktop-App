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
  getTimeBasedGreeting,
  archiveConversationSession,
  prepareTranscriptForRag,
  looksLikeShortValidQuery,
} from "../lib/ai";

// ── SVG Icons ────────────────────────────────────────────────────
const IconMic = ({ size = "md" }) => {
  const cls = size === "lg" ? "w-12 h-12" : "w-5 h-5";
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
// ─────────────────────────────────────────────────────────────────

import { t } from "../lib/translations";

// Quick reply button definitions
const quickReplies = {
  id: [
    {
      label: "📝 Cara Daftar?",
      text: "Bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?",
    },
    // { label: '🎓 Info Beasiswa', text: 'Apa saja program beasiswa yang tersedia di UCIC?' }, // DISABLED - Awaiting complete scholarship data
    // { label: '📞 Kontak BAA', text: 'Bagaimana cara menghubungi Biro Administrasi Akademik?' }, // DISABLED - Awaiting complete contact data
  ],
  en: [
    {
      label: "📝 How to Register?",
      text: "How do I register as a new student at UCIC?",
    },
    // { label: '🎓 Scholarship Info', text: 'What scholarship programs are available at UCIC?' }, // DISABLED - Awaiting complete scholarship data
    // { label: '📞 Contact BAA', text: 'How can I contact the Academic Administration Bureau?' }, // DISABLED - Awaiting complete contact data
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
// ── Full-duplex barge-in (potong ucapan SELA dengan suara) ──
const BARGE_IN_AKTIF = true; // interupsi suara otomatis saat SELA bicara
const BARGE_IN_GRACE_MS = 1200; // abaikan gema speaker di awal TTS
const BARGE_IN_AMBANG_MULTIPLIER = 3.0; // ambang tinggi anti-gema (x threshold normal)
const BARGE_IN_AMBANG_MIN = 12; // lantai ambang barge-in (skala RMS byte-domain)
const BARGE_IN_TAHAN_MS = 400; // suara harus bertahan selama ini → bukan gema sesaat
const IDLE_SESSION_MS = 90 * 1000; // 90 detik tanpa interaksi -> reset sesi
const FACE_LOST_END_MS = 12 * 1000; // 12 detik wajah hilang saat sesi aktif -> reset
// Deteksi mikrofon tidak aktif: jika RMS max < ambang batas setelah N siklus rekaman
const MAX_RMS_AKTIF = 1.2;       // RMS di bawah ini dianggap tidak ada sinyal suara nyata
const MAX_SIKLUS_TANPA_MIC = 2;  // Setelah 2 siklus tanpa sinyal → tandai sebagai tidak ada mic

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
  const [mode, setMode] = useState("speak");
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
  const modeRef = useRef(mode);
  const dynamicThresholdRef = useRef(10); // fallback fallback jika baseline gagal
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
  const activatedRef = useRef(false); // sync dengan activated state
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
    modeRef.current = mode;
  }, [mode]);
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
    // Interupsi suara (barge-in): hentikan SELA, langsung dengarkan pengguna
    const handleBargeInSuara = () => {
      stopSpeaking();
      hentikanMonitorBargeIn();
      setAvatarState("idle");
      isProcessingRef.current = false;
      setTimeout(() => startListeningRef.current?.(), 200);
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
    activatedRef.current = false;
    setActivated(false);
    setAvatarState("idle");
    setLangSelected(false);
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
      setTimeout(() => startListeningRef.current?.(), 200);
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
    if (modeRef.current !== "speak") return;

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

          // Deteksi mikrofon tidak aktif: cek apakah seluruh siklus tidak ada sinyal real
          const rmsMaxSiklus = rmsMaxSiklusIniRef.current;
          rmsMaxSiklusIniRef.current = 0; // reset untuk siklus berikutnya

          if (rmsMaxSiklus < MAX_RMS_AKTIF) {
            // RMS max siklus ini masih sangat rendah → kemungkinan besar tidak ada mic
            siklusRmsTinggiRef.current += 1;
            if (siklusRmsTinggiRef.current >= MAX_SIKLUS_TANPA_MIC) {
              console.warn("[SELA] Terdeteksi: tidak ada mikrofon hardware aktif. Beralih ke mode teks.");
              setMicTidakAktif(true);
              // Jangan hentikan sesi — biarkan pengguna tetap chat via Type Mode
            }
          } else {
            // Ada sinyal — mic aktif, reset penghitung
            siklusRmsTinggiRef.current = 0;
            setMicTidakAktif(false);
          }

          setAvatarState("idle");
          setTimeout(() => startListeningRef.current?.(), 300);
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
          setTimeout(() => startListeningRef.current?.(), 300);
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
      console.error("Mic error:", err);
      setMicDenied(true);
      setAvatarState("idle");
      isListeningRef.current = false;
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
        console.log("[SELA] Server filtered out background audio → retrying");
        isProcessingRef.current = false;
        setAvatarState("idle");
        setTimeout(() => startListeningRef.current?.(), 300);
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
        setTimeout(() => startListeningRef.current?.(), 300);
        return;
      }

      markSessionInteraction();
      if (isFarewell(text)) {
        handleFarewell(text);
        return;
      }

      onSend(text);
      setIsWaitingAI(true);
      const requestId = ++aiRequestSeqRef.current;

      const history = (currentChat?.messages || []).map((m) => ({
        role: m.role,
        content: m.text,
      }));
      history.push({ role: "user", content: text });
      const response = await getChatCompletion(history, lang);
      if (requestId !== aiRequestSeqRef.current) return;
      setIsWaitingAI(false);
      console.log("[SELA Voice] Query final ke RAG:", {
        original: rawText,
        final: text,
        transcriptMarker: preparedTranscript.marker,
      });

      // 2. Filter LLM-Side: SELA mendeteksi obrolan orang lewat
      if (response.text?.includes("[IGNORE_NOISE]")) {
        console.log(
          "[SELA] AI mendeteksi noise/obrolan acak, mengabaikan input.",
        );
        isProcessingRef.current = false;
        setAvatarState("idle");
        setTimeout(() => startListeningRef.current?.(), 300);
        return;
      }

      if (onReceive) onReceive(response);
      markSessionInteraction();

      // Fallback: kalau TTS onEnd tidak pernah terpanggil (bug Chrome),
      // paksa restart listen setelah estimasi durasi + buffer
      const spokenText = response.spokenText || response.text;
      const estDuration = Math.max(3000, spokenText.length * 80);
      const ttsFallback = setTimeout(() => {
        if (isProcessingRef.current) {
          console.warn("[SELA] TTS onEnd timeout — force restart listen");
          stopSpeaking();
          setAvatarState("idle");
          isProcessingRef.current = false;
          setTimeout(() => startListeningRef.current?.(), 800);
        }
      }, estDuration + 2000);

      speakText(
        spokenText,
        () => setAvatarState("speaking"),
        () => {
          clearTimeout(ttsFallback);
          setAvatarState("idle");
          isProcessingRef.current = false;
          // Delay 800ms — beri waktu speaker selesai bergema sebelum mic aktif lagi
          setTimeout(() => startListeningRef.current?.(), 800);
        },
        response.detectedLang || lang,
      );
    } catch (error) {
      console.error(error);
      setIsWaitingAI(false);
      if (onReceive) onReceive(t[lang].error_stt);
      setAvatarState("idle");
      isProcessingRef.current = false;
      setTimeout(() => startListeningRef.current?.(), 1500);
    }
  };

  // ── Auto-start saat mode speak DAN sudah diaktivasi ──────────
  useEffect(() => {
    if (mode !== "speak" || !activated) {
      stopListening();
      stopSpeaking();
      hentikanMonitorBargeIn();
      setAvatarState("idle");
      isProcessingRef.current = false;
      return;
    }
    const timer = setTimeout(() => startListeningRef.current?.(), 200);
    return () => {
      clearTimeout(timer);
      stopListening();
      stopSpeaking();
      hentikanMonitorBargeIn();
      isProcessingRef.current = false;
    };
  }, [mode, activated]);

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
      activatedRef.current = false;
      setAvatarState("idle");
      setActivated(false);
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
        activatedRef.current = false;
        setAvatarState("idle");
        setActivated(false);
        setLangSelected(false);
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

    setAvatarState("thinking");
    setIsWaitingAI(true);
    const requestId = ++aiRequestSeqRef.current;
    try {
      const history = (currentChat?.messages || []).map((m) => ({
        role: m.role,
        content: m.text,
      }));
      history.push({ role: "user", content: userText });
      const response = await getChatCompletion(history, lang);
      if (requestId !== aiRequestSeqRef.current) return;
      setIsWaitingAI(false);
      if (onReceive) onReceive(response);
      markSessionInteraction();
      speakWithAvatar(
        response.spokenText || response.text,
        response.detectedLang || lang,
        () => setAvatarState("idle"),
      );
    } catch {
      if (requestId !== aiRequestSeqRef.current) return;
      setIsWaitingAI(false);
      if (onReceive) onReceive(t[lang].error_network);
      setAvatarState("idle");
    }
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
    const confirm = timeBasedGreeting;

    if (mode === "type") {
      onSend(langLabel);
      if (onReceive) onReceive(confirm);
    }
    speakWithAvatar(
      confirm,
      chosen,
      () => {
        startListeningRef.current?.();
      },
    );
  };

  // ── Mode Toggle ───────────────────────────────────────────────
  const ModeToggle = () => (
    <div className="flex justify-center">
      <div className="inline-flex items-center bg-white/70 dark:bg-slate-900/70 backdrop-blur-sm border border-gray-100/80 dark:border-white/10 rounded-2xl shadow-sm overflow-hidden transition-colors">
        <button
          id="mode-type-btn"
          onClick={() => setMode("type")}
          className={`flex flex-col items-center gap-1 px-8 py-2.5 transition-all duration-200
            ${mode === "type" ? "text-blue-600 dark:text-blue-400" : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"}`}
        >
          <IconKeyboard />
          <span className="text-[10px] font-bold uppercase tracking-widest">
            {t[lang].type_mode}
          </span>
        </button>
        <div className="w-px h-8 bg-gray-200 dark:bg-white/10" />
        <button
          id="mode-speak-btn"
          onClick={() => setMode("speak")}
          className={`flex flex-col items-center gap-1 px-8 py-2.5 transition-all duration-200
            ${mode === "speak" ? "text-blue-600 dark:text-blue-400" : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"}`}
        >
          <IconMicToggle />
          <span className="text-[10px] font-bold uppercase tracking-widest">
            {t[lang].speak_mode}
          </span>
        </button>
      </div>
    </div>
  );

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

  // ── SPEAK MODE ────────────────────────────────────────────────
  if (mode === "speak") {
    const latestMsg = messages[messages.length - 1];

    // Overlay sebelum aktivasi — kamera preview + face detection status
    if (!activated) {
      return (
        <main className="flex-1 relative flex flex-col items-center justify-center overflow-hidden">
          {/* Avatar 3D Background - FULL SCREEN */}
          <div className="absolute inset-0 pointer-events-none z-0">
            <div className="pointer-events-auto w-full h-full">
              <AvatarPlaceholder state="idle" theme={theme} />
            </div>
          </div>

          {/* Hidden Camera for Face Detection */}
          <div className="absolute opacity-0 pointer-events-none overflow-hidden w-1 h-1">
            <video ref={videoRef} muted playsInline autoPlay />
          </div>

          <div className="absolute bottom-8 z-20">
            <ModeToggle />
          </div>
        </main>
      );
    }

    return (
      <main className="flex-1 relative flex flex-col overflow-hidden">
        {/* Avatar full screen */}
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="pointer-events-auto w-full h-full">
            <AvatarPlaceholder state={avatarState} theme={theme} />
          </div>
        </div>

        {/* Chat bubbles — landscape/wide mode only */}
        <div className="absolute top-0 right-0 bottom-28 w-[340px] hidden md:flex [@media(orientation:portrait)]:hidden flex-col justify-end pr-8 pb-6 pt-4 pointer-events-auto z-10 transition-colors overflow-hidden">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-2 pb-4 opacity-50">
              <IconSparkle />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 italic tracking-widest">
                SELA AI
              </p>
            </div>
          ) : (
            <div
              ref={chatScrollRef}
              onScroll={handleChatScroll}
              className="flex flex-col gap-1 overflow-y-auto hide-scrollbar"
            >
              {messages.map((msg) => (
                <div key={msg.id}>
                  <ChatBubble
                    role={msg.role}
                    text={msg.text}
                    lang={lang}
                    isNew={msg.role === "assistant" && msg.id === latestSelaId}
                  />
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
        </div>
        {/* Tombol scroll ke bawah — voice mode, di atas panel chat */}
        {!isAtBottom && messages.length > 0 && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-40 right-[155px] z-30 w-8 h-8 rounded-full hidden md:flex [@media(orientation:portrait)]:hidden
              bg-white/90 dark:bg-slate-800/90 border border-gray-200/70 dark:border-white/10
              shadow-lg items-center justify-center text-gray-500 dark:text-gray-300
              hover:bg-white dark:hover:bg-slate-700 active:scale-95 transition-all duration-150 animate-fade-in"
          >
            <IconChevronDown />
          </button>
        )}

        <div className="flex-1 pointer-events-none" />

        {/* Bottom content for speak mode */}
        <div className="flex flex-col items-center gap-3 pb-8 pt-2 px-4 relative z-20 pointer-events-auto">
          <div className="w-full max-w-sm md:hidden [@media(orientation:portrait)]:block">
            {/* Portrait mode: Show LiveCaption when SELA is speaking */}
            {avatarState === "speaking" && latestMsg?.role === "assistant" && (
              <LiveCaption
                text={latestMsg.text}
                isLoading={false}
                avatarState={avatarState}
              />
            )}
            {/* Show loading when waiting for AI response */}
            {isWaitingAI && avatarState !== "speaking" && (
              <ChatBubble role="assistant" text="" lang={lang} isLoading />
            )}
            {/* Show latest message when not speaking and not waiting */}
            {avatarState !== "speaking" && !isWaitingAI && latestMsg && (
              <div className="animate-fade-in">
                <ChatBubble
                  role={latestMsg.role}
                  text={latestMsg.text}
                  lang={lang}
                  qrVisibleMs={20000}
                  isNew={
                    latestMsg.role === "assistant" &&
                    latestMsg.id === latestSelaId
                  }
                />
                {latestMsg.role === "assistant" &&
                  latestMsg.media &&
                  latestMsg.media.length > 0 && (
                    <MediaCarousel media={latestMsg.media} />
                  )}
              </div>
            )}
          </div>

          {/* Tombol Interaktif Mikrofon / Suara Speak Mode */}
          <div className="flex flex-col items-center gap-2 my-2">
            <button
              id="voice-action-btn"
              type="button"
              onClick={handleToggleVoice}
              className={`relative w-20 h-20 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 transform active:scale-95 ${
                avatarState === "listening"
                  ? "bg-red-500 shadow-red-500/50 animate-pulse ring-8 ring-red-400/30 text-white"
                  : avatarState === "speaking"
                  ? "bg-amber-500 shadow-amber-500/50 animate-pulse ring-8 ring-amber-400/30 text-white"
                  : avatarState === "thinking"
                  ? "bg-indigo-600 shadow-indigo-500/50 ring-4 ring-indigo-300/30 text-white"
                  : "bg-gradient-to-tr from-blue-600 to-cyan-500 shadow-blue-500/40 hover:from-blue-700 hover:to-cyan-600 hover:scale-105 ring-4 ring-blue-300/30 text-white"
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
          </div>

          <p className="text-xs text-gray-400 dark:text-gray-500 font-bold uppercase tracking-tighter text-center">
            {statusLabel()}
          </p>

          {micDenied && (
            <button
              onClick={() => {
                setMicDenied(false);
                startListeningRef.current?.();
              }}
              className="text-xs text-blue-500 underline"
            >
              {lang === "id" ? "Coba lagi" : "Retry"}
            </button>
          )}

          {/* Banner notifikasi: tidak ada mikrofon hardware terdeteksi */}
          {micTidakAktif && !micDenied && (
            <div className="flex flex-col items-center gap-2 px-4 py-3 bg-amber-500/20 border border-amber-400/40 rounded-2xl backdrop-blur-sm max-w-xs text-center animate-fade-in">
              <span className="text-lg">🎤</span>
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">
                {lang === "id"
                  ? "Mikrofon tidak terdeteksi di komputer ini."
                  : "No microphone detected on this computer."}
              </p>
              <p className="text-xs text-amber-600/80 dark:text-amber-400/80">
                {lang === "id"
                  ? "Gunakan Mode Ketik untuk chat teks, atau sambungkan mikrofon."
                  : "Use Type Mode for text chat, or connect a microphone."}
              </p>
              <button
                onClick={() => setMode("type")}
                className="mt-1 px-4 py-1.5 rounded-full text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white active:scale-95 transition-all"
              >
                {lang === "id" ? "⌨️ Beralih ke Mode Ketik" : "⌨️ Switch to Type Mode"}
              </button>
            </div>
          )}

          {/* Tombol pilihan bahasa — muncul setelah greeting bilingual selesai */}
          {activated && awaitingLangSelect && !langSelected && avatarState === "idle" && (
            <div className="flex gap-3 animate-fade-in">
              <button
                onClick={() => handleLangSelect("id")}
                className="px-5 py-2 rounded-2xl text-sm font-semibold bg-blue-500 hover:bg-blue-600 active:scale-95 text-white shadow-md transition-all duration-150"
              >
                🇮🇩 Indonesia
              </button>
              <button
                onClick={() => handleLangSelect("en")}
                className="px-5 py-2 rounded-2xl text-sm font-semibold bg-white hover:bg-gray-50 active:scale-95 text-gray-700 border border-gray-200 shadow-md dark:bg-slate-700 dark:text-gray-100 dark:border-slate-600 transition-all duration-150"
              >
                🇬🇧 English
              </button>
            </div>
          )}

          <ModeToggle />
        </div>
      </main>
    );
  }

  // ── TYPE MODE ─────────────────────────────────────────────────
  return (
    <main className="flex-1 relative flex flex-col overflow-hidden px-4 pt-4 pb-8 transition-colors">
      <div className="flex-1 flex flex-col max-w-2xl w-full mx-auto overflow-hidden">
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-6 pb-8">
            <IconSparkle />
            <div>
              <h2 className="text-4xl font-light text-gray-600 dark:text-gray-200 tracking-tighter italic">
                SELA
              </h2>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-2 font-medium">
                {t[lang].type_message}
              </p>
            </div>

            {/* Quick reply buttons */}
            <div className="w-full px-2">
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-3 font-semibold uppercase tracking-widest">
                {lang === "id" ? "Pertanyaan Populer" : "Popular Questions"}
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {quickReplies[lang]?.map((qr, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSubmit(qr.text)}
                    className="px-4 py-2.5 rounded-full bg-gradient-to-r from-blue-500 to-blue-600
                               hover:from-blue-600 hover:to-blue-700
                               dark:from-blue-600 dark:to-blue-700
                               dark:hover:from-blue-700 dark:hover:to-blue-800
                               text-white text-xs font-semibold
                               active:scale-95 shadow-md
                               transition-all duration-150"
                  >
                    {qr.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div
            ref={chatScrollRef}
            onScroll={handleChatScroll}
            className="flex-1 overflow-y-auto py-4 flex flex-col gap-1 hide-scrollbar"
          >
            {messages.map((msg, idx) => (
              <div key={msg.id}>
                <ChatBubble
                  role={msg.role}
                  text={msg.text}
                  lang={lang}
                  isNew={msg.role === "assistant" && msg.id === latestSelaId}
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
      </div>

      <div className="w-full max-w-xl mx-auto mt-4">
        {/* Tombol scroll ke bawah — di atas input bar */}
        {!isAtBottom && messages.length > 0 && (
          <div className="flex justify-center mb-3 animate-fade-in">
            <button
              onClick={scrollToBottom}
              className="w-9 h-9 rounded-full bg-white/90 dark:bg-slate-800/90 border border-gray-200/70 dark:border-white/10
                shadow-lg flex items-center justify-center text-gray-500 dark:text-gray-300
                hover:bg-white dark:hover:bg-slate-700 active:scale-95 transition-all duration-150"
            >
              <IconChevronDown />
            </button>
          </div>
        )}
        {/* Tombol pilihan bahasa — muncul setelah greeting bilingual di type mode */}
        {awaitingLangSelect && !langSelected && (
          <div className="flex gap-3 justify-center mb-4 animate-fade-in">
            <button
              onClick={() => handleLangSelect("id")}
              className="px-5 py-2 rounded-2xl text-sm font-semibold bg-blue-500 hover:bg-blue-600 active:scale-95 text-white shadow-md transition-all duration-150"
            >
              🇮🇩 Indonesia
            </button>
            <button
              onClick={() => handleLangSelect("en")}
              className="px-5 py-2 rounded-2xl text-sm font-semibold bg-white hover:bg-gray-50 active:scale-95 text-gray-700 border border-gray-200 shadow-md dark:bg-slate-700 dark:text-gray-100 dark:border-slate-600 transition-all duration-150"
            >
              🇬🇧 English
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="relative mb-3">
          <input
            id="main-input"
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={
              isRecordingTypeInput
                ? (lang === "id" ? "🎙️ Sedang mendengarkan ucapan Anda... Silakan bicara!" : "🎙️ Listening... Speak now!")
                : t[lang].type_message
            }
            className={`w-full bg-white/85 dark:bg-slate-900/90 backdrop-blur-sm border rounded-full pl-5 pr-14 py-4
                        text-gray-700 dark:text-gray-100 text-sm placeholder-gray-400 outline-none shadow-md
                        transition-all duration-300
                        ${
                          isRecordingTypeInput
                            ? "border-red-400 ring-4 ring-red-400/40 shadow-red-200 animate-pulse"
                            : focused
                            ? "border-blue-300 dark:border-blue-500 ring-4 ring-blue-100/60 dark:ring-blue-900/40 shadow-blue-100/60"
                            : "border-gray-200/70 dark:border-white/10"
                        }`}
          />
          <button
            id="send-btn"
            type={value.trim() ? "submit" : "button"}
            onClick={value.trim() ? undefined : handleToggleTypeMic}
            aria-label={value.trim() ? "Send" : "Microphone"}
            className={`absolute right-2 top-1/2 -translate-y-1/2
                       w-10 h-10 rounded-full flex items-center justify-center
                       shadow-lg active:scale-95 transition-all duration-150 ${
                         isRecordingTypeInput
                           ? "bg-red-500 animate-pulse text-white shadow-red-500/40 ring-4 ring-red-300"
                           : "bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-400/40 hover:from-blue-600 hover:to-blue-700"
                       }`}
            title={
              value.trim()
                ? "Kirim pesan teks"
                : isRecordingTypeInput
                ? "Klik untuk berhenti dan kirim suara"
                : "Klik untuk berbicara lewat mikrofon"
            }
          >
            {value.trim() ? (
              <IconSend />
            ) : isRecordingTypeInput ? (
              <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
            ) : (
              <IconMic />
            )}
          </button>
        </form>
        <ModeToggle />
      </div>
    </main>
  );
}
