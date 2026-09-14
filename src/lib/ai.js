import dataset from "../data/ucic_dataset.json";
import { buildSpokenText } from "./responsePlan";
import { connectAudioToLipsync, unlockAudioContext } from "./lipsync";
import { audioQueueManager } from "./streamingAudioQueue";

// ── RAG Setup ────────────────────────────────────────────────────────────────

let learnedTypoCache = null;

const EXCLUDED_RAG_CATEGORIES = new Set([]);
const EXCLUDED_RAG_IDS = new Set([
  "data_lengkap_ucic",
  "informasi_kampus_0",
  "info_pmb_1",
  "berita_seputar_kampus_2",
  "kegiatan_kampus_3",
  "informasi_artikel_berita_seputar_univers_0",
  "kegiatan_seputar_universitas_cic_0",
  "data_lengkap",
]);

const ragDataset = dataset.filter(
  (item) =>
    !EXCLUDED_RAG_CATEGORIES.has(item.category) &&
    !EXCLUDED_RAG_IDS.has(item.id),
);

const DATASET_CATEGORY_ALIASES = {
  akademik: [
    "akademik",
    "baak",
    "krs",
    "khs",
    "sks",
    "uts",
    "uas",
    "sidang",
    "skripsi",
    "wisuda",
    "yudisium",
    "cuti",
    "nilai",
    "absensi",
    "kehadiran",
    "hadir",
    "telat",
    "terlambat",
    "alpa",
    "perkuliahan",
  ],
  akreditasi: ["akreditasi", "ban pt", "mutu", "kualitas"],
  karir: ["karir", "career", "alumni", "kerja", "bursa kerja"],
  kegiatan: ["kegiatan", "ukm", "organisasi", "hmp", "ekskul", "pkkmb", "ospek"],
  kurikulum: ["kurikulum", "mata kuliah", "semester", "matkul", "curriculum"],
  nilai: ["nilai", "budaya", "karakter", "great", "commitment", "integrity"],
  profil: ["profil", "sejarah", "pimpinan", "rektor", "yayasan"],
  visi_misi: ["visi", "misi", "tujuan", "arah", "2030"],
};

const QUERY_PHRASE_ALIASES = [
  [/\bkelas karyawan\b/g, "kelas sore rpl"],
  [/\bbiaya masuk\b/g, "biaya pendaftaran"],
  [/\bdaftar ulang\b/g, "registrasi ulang"],
  [/\banak desain\b/g, "dkv desain komunikasi visual"],
  [/\banak komputer\b/g, "teknik informatika sistem informasi"],
  [/\bkuliah malam\b/g, "kelas sore"],
  [/\bwa\b/g, "whatsapp"],
  [/\bva\b/g, "virtual account"],
  [/\be wallet\b/g, "ewallet"],
  [/\bjalur masuk\b/g, "pendaftaran pmb"],
  [/\borang tua\b/g, "wali orang tua"],
  [/\btelat masuk kelas\b/g, "kehadiran kuliah telat alpa"],
  [/\bterlambat masuk kelas\b/g, "kehadiran kuliah terlambat alpa"],
  [/\bsiapa rektor\b/g, "rektor pimpinan"],
];

const RAG_STOPWORDS = new Set([
  "apa",
  "apakah",
  "siapa",
  "nama",
  "itu",
  "ini",
  "yang",
  "di",
  "ke",
  "dari",
  "dan",
  "atau",
  "untuk",
  "tentang",
  "mengenai",
  "dong",
  "nih",
  "sih",
  "ya",
  "ada",
  "aja",
  "saja",
  "mau",
  "ingin",
  "pengen",
  "boleh",
  "bisa",
  "ga",
  "gak",
  "nggak",
  "tidak",
  "kalo",
  "kalau",
  "mana",
  "kah",
  "min",
  "admin",
  "sela",
  "universitas",
  "kampus",
  "catur",
  "insan",
  "cendekia",
  "ucic",
  "cic",
  "cirebon",
  "gimana",
  "bagaimana",
  "berapa",
  "kapan",
  "gmn",
  "cara",
  "info",
  "informasi",
  "jelaskan",
  "minta",
  "tolong",
  "eh",
  "sila",
  "anu",
  "dongg",
  "nihh",
  "jadi",
  "kayak",
  "kaya",
  "ituh",
  "tuh",
  "nihh",
  "yaa",
  "what",
  "who",
  "where",
  "when",
  "why",
  "how",
  "is",
  "are",
  "the",
  "of",
  "about",
  "please",
  "campus",
  "university",
]);

const RAG_SYNONYMS = {
  biaya: [
    "uang",
    "bayar",
    "pembayaran",
    "spp",
    "ukt",
    "harga",
    "cost",
    "fee",
    "tuition",
  ],
  beasiswa: ["kip", "bantuan", "scholarship"],
  daftar: ["pendaftaran", "pmb", "registrasi", "masuk", "apply", "admission"],
  dosen: ["pengajar", "lecturer"],
  fasilitas: ["sarana", "lab", "laboratorium", "perpustakaan", "facility"],
  fakultas: ["jurusan", "prodi", "program", "studi", "major"],
  jurusan: ["fakultas", "prodi", "program", "studi", "major"],
  akademik: [
    "baak",
    "krs",
    "khs",
    "sks",
    "uts",
    "uas",
    "ujian",
    "sidang",
    "skripsi",
    "wisuda",
    "yudisium",
    "cuti",
    "nilai",
    "absensi",
    "kehadiran",
    "hadir",
    "telat",
    "terlambat",
    "alpa",
    "perkuliahan",
  ],
  akreditasi: ["mutu", "kualitas", "ban pt", "ban-pt"],
  karir: ["career", "alumni", "kerja", "bursa kerja", "tracer study"],
  kegiatan: ["ukm", "organisasi", "hmp", "ekskul", "pkkmb", "ospek"],
  kontak: ["nomor", "telepon", "wa", "whatsapp", "email", "alamat", "hubungi"],
  kurikulum: ["mata kuliah", "matkul", "semester", "curriculum"],
  kelas: ["jadwal", "jam", "pagi", "sore", "malam", "karyawan", "rpl"],
  lokasi: [
    "alamat",
    "alamatnya",
    "berada",
    "dimana",
    "letak",
    "letaknya",
    "lokasinya",
    "terletak",
    "where",
  ],
  orientasi: ["ospek", "pkkmb", "maba", "camaba"],
  pembayaran: [
    "bayar",
    "cicilan",
    "transfer",
    "virtual",
    "account",
    "midtrans",
    "ovo",
    "gopay",
    "dana",
  ],
  pendaftaran: ["daftar", "registrasi", "pmb", "masuk", "jalur"],
  rektor: [
    "pimpinan",
    "ketua",
    "pemimpin",
    "direktur",
    "kepala",
    "chancellor",
    "rector",
  ],
  syarat: ["persyaratan", "berkas", "dokumen", "requirement", "requirements"],
  visi: ["misi", "tujuan"],
};

const TYPO_TOKEN_MAP = {
  dmn: "dimana",
  dmnnya: "dimana",
  gmn: "gimana",
  gmna: "gimana",
  gimna: "gimana",
  knp: "kenapa",
  kpn: "kapan",
  brp: "berapa",
  syg: "sayang",
  daftarin: "daftar",
  daftarnya: "daftar",
  daftar2: "daftar",
  daftaru: "daftar",
  persaratan: "persyaratan",
  persyaratn: "persyaratan",
  persyaratanya: "persyaratan",
  persyaratannya: "persyaratan",
  syaratny: "syarat",
  bayarannya: "pembayaran",
  bayarnya: "pembayaran",
  biayanya: "biaya",
  kuliahnya: "kuliah",
  kelasnya: "kelas",
  jadwalnya: "jadwal",
  jurusannya: "jurusan",
  prodinya: "prodi",
  ospeknya: "ospek",
  orientasinya: "orientasi",
  kampusnya: "kampus",
  ewallet: "ewallet",
  gopaynya: "gopay",
};

const TOPIC_HINTS = {
  pendaftaran: [
    "daftar",
    "pendaftaran",
    "pmb",
    "registrasi",
    "masuk",
    "camaba",
  ],
  syarat: ["syarat", "persyaratan", "berkas", "dokumen", "upload"],
  biaya: [
    "biaya",
    "bayar",
    "pembayaran",
    "cicilan",
    "spp",
    "ukt",
    "virtual",
    "account",
    "ewallet",
    "midtrans",
  ],
  kelas: ["kelas", "jadwal", "jam", "pagi", "sore", "malam", "rpl", "karyawan"],
  jurusan: [
    "jurusan",
    "prodi",
    "fakultas",
    "informatika",
    "si",
    "dkv",
    "manajemen",
    "akuntansi",
    "bisnis",
  ],
  kontak: ["kontak", "whatsapp", "telepon", "email", "alamat", "hubungi"],
  rektor: [
    "rektor",
    "pimpinan",
    "ketua",
    "pemimpin",
    "kepala kampus",
    "chandra",
    "lukita",
  ],
  lokasi: [
    "lokasi",
    "alamat",
    "alamatnya",
    "dimana",
    "di mana",
    "berada",
    "letak",
    "letaknya",
    "terletak",
  ],
  orientasi: ["ospek", "orientasi", "pkkmb", "maba"],
  beasiswa: ["beasiswa", "kip", "bantuan"],
  fasilitas: ["fasilitas", "lab", "perpustakaan", "gedung", "ruang"],
};

const INTENT_PATTERNS = {
  profil: [
    "profil",
    "profile",
    "tentang ucic",
    "apa itu ucic",
    "ucic itu apa",
    "universitas catur insan cendekia",
  ],
  pendaftaran: [
    "daftar",
    "pendaftaran",
    "registrasi",
    "pmb",
    "masuk kuliah",
    "masuk kampus",
  ],
  syarat: [
    "syarat",
    "persyaratan",
    "berkas",
    "dokumen",
    "siapin apa",
    "bawa apa",
  ],
  biaya: ["biaya", "bayar", "cicilan", "uang masuk", "spp", "ukt", "mahal"],
  kelas: ["kelas", "jam", "jadwal", "sore", "malam", "karyawan", "rpl"],
  jurusan: [
    "jurusan",
    "prodi",
    "fakultas",
    "anak komputer",
    "anak desain",
    "anak bisnis",
  ],
  kontak: ["kontak", "nomor", "whatsapp", "telepon", "hubungi", "alamat"],
  rektor: [
    "rektor",
    "siapa rektor",
    "pimpinan ucic",
    "ketua ucic",
    "pemimpin ucic",
    "kepala kampus",
    "chandra lukita",
  ],
  lokasi: [
    "lokasi",
    "alamat",
    "alamat kampus",
    "kampus dimana",
    "kampus di mana",
    "berada dimana",
    "letak kampus",
  ],
  orientasi: ["ospek", "orientasi", "pkkmb", "maba"],
  beasiswa: ["beasiswa", "kip", "potongan", "bantuan"],
  fasilitas: ["fasilitas", "lab", "perpustakaan", "wifi", "gedung"],
};

const AWAM_TOPIC_ALIASES = {
  pendaftaran: [
    "masuk sini",
    "masuk kampus ini",
    "jadi mahasiswa sini",
    "daftar kuliah",
    "cara masuk ucic",
  ],
  syarat: [
    "harus apa",
    "siapin apa",
    "bawa apa",
    "surat lulus",
    "ijazah sementara",
    "berkas sekolah",
  ],
  biaya: [
    "uang masuk",
    "bayar awal",
    "uang pertama",
    "biaya pertama",
    "uang daftar",
  ],
  kelas: [
    "kelas orang kerja",
    "kuliah sambil kerja",
    "kuliah malam",
    "kelas malam",
    "kelas pegawai",
  ],
  jurusan: [
    "anak komputer",
    "anak desain",
    "anak bisnis",
    "bagusan jurusan mana",
    "pilih jurusan apa",
  ],
  kontak: ["nomor admin", "wa kampus", "hubungi kampus", "kontak pmb"],
  rektor: [
    "rektor ucic siapa",
    "siapa rektor ucic",
    "yang memimpin ucic",
    "pimpinan kampus siapa",
  ],
  lokasi: [
    "kampusnya dimana",
    "kampusnya di mana",
    "alamat kampusnya",
    "ucic ada dimana",
    "ucic berada dimana",
    "letak ucic",
  ],
  orientasi: ["ospek maba", "acara anak baru", "orientasi anak baru"],
  beasiswa: ["potongan biaya", "bantuan biaya", "beasiswa anak pintar"],
  fasilitas: ["gedungnya gimana", "ada lab ga", "fasilitas kampus apa aja"],
};

const CANONICAL_REWRITE_MAP = {
  profil: "profil universitas catur insan cendekia ucic",
  pendaftaran: "cara pendaftaran mahasiswa baru ucic",
  syarat: "syarat berkas pendaftaran mahasiswa baru ucic",
  biaya: "biaya kuliah dan metode pembayaran ucic",
  kelas: "jadwal kelas sore pagi rpl untuk mahasiswa bekerja ucic",
  jurusan: "jurusan program studi rekomendasi jurusan ucic",
  kontak: "kontak admin pmb dan alamat kampus ucic",
  rektor: "rektor pimpinan ucic chandra lukita",
  lokasi: "lokasi alamat kampus ucic",
  orientasi: "orientasi mahasiswa baru ospek pkkmb ucic",
  beasiswa: "program beasiswa dan bantuan biaya ucic",
  fasilitas: "fasilitas kampus laboratorium perpustakaan ucic",
};

const RAG_FAILURE_LOG_KEY = "sela_rag_failure_log";
const SESSION_ARCHIVE_KEY = "sela_session_archive_v1";
const LEARNED_ARTIFACTS_KEY = "sela_learned_artifacts_v1";
const SESSION_RETENTION_LIMIT = 20;
const SESSION_RETENTION_MS = 1000 * 60 * 60 * 24 * 14;
const SLOT_PATTERNS = {
  biaya: {
    pendaftaran: ["pendaftaran", "daftar", "uang daftar", "uang masuk"],
    metode: [
      "metode",
      "transfer",
      "virtual account",
      "va",
      "ovo",
      "gopay",
      "dana",
      "midtrans",
    ],
    cicilan: ["cicilan", "nyicil", "bertahap", "angsuran"],
  },
  kelas: {
    pagi: ["pagi"],
    sore: ["sore", "malam", "kelas malam", "kuliah malam"],
    pekerja: ["kerja", "karyawan", "orang kerja", "pegawai"],
    rpl: ["rpl"],
  },
  jurusan: {
    komputer: ["komputer", "it", "programming", "coding"],
    desain: ["desain", "dkv", "gambar", "visual"],
    bisnis: ["bisnis", "usaha", "marketing"],
    olahraga: ["olahraga", "sport"],
  },
  kontak: {
    pmb: ["pmb", "daftar", "admin"],
    umum: ["kampus", "umum", "informasi"],
  },
  syarat: {
    dokumen: ["dokumen", "berkas", "file", "upload"],
    identitas: ["ktp", "kk", "akta"],
    kelulusan: ["ijazah", "skl", "surat lulus"],
  },
};

const DECOMPOSITION_SEPARATORS = [
  /\bterus\b/g,
  /\blalu\b/g,
  /\bhabis itu\b/g,
  /\babis itu\b/g,
  /\bselain itu\b/g,
  /\btrus\b/g,
];

const SHORT_VALID_QUERY_TOKENS = new Set([
  "daftar",
  "pendaftaran",
  "pmb",
  "syarat",
  "persyaratan",
  "biaya",
  "bayar",
  "kelas",
  "jurusan",
  "prodi",
  "kontak",
  "alamat",
  "lokasi",
  "kampus",
  "kuliah",
  "beasiswa",
  "jadwal",
  "jam",
  "cicilan",
  "daftarnya",
  "biayanya",
  "syaratnya",
]);

function normalizeText(text = "") {
  let normalized = String(text)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  for (const [pattern, replacement] of QUERY_PHRASE_ALIASES) {
    normalized = normalized.replace(pattern, replacement);
  }

  return normalized
    .replace(/([a-z])\1{2,}/g, "$1")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function areSimilarPhrases(a = "", b = "") {
  const normalizedA = normalizeText(a);
  const normalizedB = normalizeText(b);
  if (!normalizedA || !normalizedB) return false;
  if (normalizedA === normalizedB) return true;
  if (normalizedA.includes(normalizedB) || normalizedB.includes(normalizedA))
    return true;
  const maxLength = Math.max(normalizedA.length, normalizedB.length);
  if (maxLength < 8) return false;
  return levenshtein(normalizedA, normalizedB) / maxLength <= 0.2;
}

function splitTranscriptSegments(text = "") {
  const normalized = String(text)
    .replace(/[!?]+/g, ".")
    .replace(/\s+/g, " ")
    .trim();

  const rawSegments = normalized
    .split(/[.,;:\n]/)
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (rawSegments.length > 1) return rawSegments;

  return normalized
    .split(/\s{2,}|\s-\s| \| /)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function isFillerSegment(segment = "") {
  const normalized = normalizeText(segment);
  return ["e", "ee", "eee", "eh", "emm", "em", "hmm", "hm", "anu"].includes(
    normalized,
  );
}

function collapseRepeatedTokenRuns(text = "") {
  const tokens = normalizeText(text).split(" ").filter(Boolean);
  if (tokens.length < 4) return text.trim();

  const joined = (seq) => seq.join(" ").trim();
  const startsWithSequence = (source, target) =>
    target.length >= 3 && joined(source).startsWith(joined(target));
  const endsWithSequence = (source, target) =>
    target.length >= 3 && joined(source).endsWith(joined(target));

  for (let split = Math.floor(tokens.length / 2); split >= 2; split--) {
    const left = tokens.slice(0, split);
    const right = tokens.slice(split);
    if (right.length < 2) continue;

    if (
      areSimilarPhrases(joined(left), joined(right)) ||
      startsWithSequence(left, right) ||
      startsWithSequence(right, left) ||
      endsWithSequence(left, right) ||
      endsWithSequence(right, left)
    ) {
      return joined(left.length >= right.length ? left : right);
    }
  }

  return text.trim();
}

function stripLeadingCorrectionPhrase(text = "") {
  return String(text)
    .replace(/^(ya|yah|iya|eh|eee|em|emm)\s+salah\s+/i, "")
    .replace(/^(eh|eee|em|emm|anu)\s+/i, "")
    .trim();
}

function stripSelaAddressNoise(text = "") {
  return String(text)
    .replace(/^(sela|sella|selah|cela|zela|selak)[\s,.:;!?-]+/i, "")
    .replace(/[\s,.:;!?-]+(sela|sella|selah|cela|zela|selak)\s*$/i, "")
    .trim();
}

export function prepareTranscriptForRag(text = "") {
  const rawText = String(text || "").trim();
  if (!rawText) {
    return {
      rawText: "",
      cleanedText: "",
      repeatedTranscript: false,
      removedSegments: [],
      marker: "empty_transcript",
    };
  }

  const segments = splitTranscriptSegments(rawText);
  const uniqueSegments = [];
  const removedSegments = [];

  for (const segment of segments) {
    if (isFillerSegment(segment)) {
      removedSegments.push(segment);
      continue;
    }
    const isDuplicate = uniqueSegments.some((existing) =>
      areSimilarPhrases(existing, segment),
    );
    if (isDuplicate) {
      removedSegments.push(segment);
      continue;
    }
    uniqueSegments.push(segment);
  }

  let cleanedText = uniqueSegments.join(". ").trim();
  cleanedText = stripLeadingCorrectionPhrase(cleanedText);
  cleanedText = stripSelaAddressNoise(cleanedText);
  cleanedText = collapseRepeatedTokenRuns(cleanedText);
  cleanedText = stripSelaAddressNoise(cleanedText);
  if (!cleanedText) cleanedText = rawText;

  const repeatedTranscript =
    removedSegments.length > 0 || /(.{8,})\s+\1/i.test(rawText);
  return {
    rawText,
    cleanedText,
    repeatedTranscript,
    removedSegments,
    marker: repeatedTranscript ? "repeated_transcript" : "clean_transcript",
  };
}

export function looksLikeShortValidQuery(text = "") {
  const normalized = normalizeText(text);
  if (!normalized) return false;
  const tokens = normalized.split(" ").filter(Boolean);
  return tokens.some(
    (token) =>
      SHORT_VALID_QUERY_TOKENS.has(token) || detectTopicHints(token).length > 0,
  );
}

function levenshtein(a = "", b = "") {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  const dp = Array.from({ length: m + 1 }, (_, i) => [i]);
  for (let j = 1; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost,
      );
    }
  }

  return dp[m][n];
}

function getKnownVocabulary() {
  const vocab = new Set([
    ...Object.keys(RAG_SYNONYMS),
    ...Object.keys(TYPO_TOKEN_MAP),
    ...Object.keys(CANONICAL_REWRITE_MAP),
  ]);
  const intentBank = getIntentSynonymBank();

  for (const values of Object.values(RAG_SYNONYMS))
    values.forEach((v) => vocab.add(v));
  for (const values of Object.values(TOPIC_HINTS))
    values.forEach((v) => vocab.add(v));
  for (const values of Object.values(AWAM_TOPIC_ALIASES))
    values.forEach((v) =>
      normalizeText(v)
        .split(" ")
        .forEach((token) => vocab.add(token)),
    );
  for (const values of Object.values(intentBank))
    values.forEach((v) =>
      normalizeText(v)
        .split(" ")
        .forEach((token) => vocab.add(token)),
    );
  for (const groups of Object.values(SLOT_PATTERNS)) {
    Object.values(groups).forEach((values) =>
      values.forEach((v) =>
        normalizeText(v)
          .split(" ")
          .forEach((token) => vocab.add(token)),
      ),
    );
  }
  const learnedArtifacts = getLearnedArtifacts();
  Object.values(learnedArtifacts.learned_typo_map || {}).forEach((v) =>
    vocab.add(v),
  );
  Object.entries(learnedArtifacts.learned_awam_aliases || {}).forEach(
    ([topic, aliases]) => {
      vocab.add(topic);
      (aliases || []).forEach((alias) =>
        normalizeText(alias)
          .split(" ")
          .forEach((token) => vocab.add(token)),
      );
    },
  );

  return [...vocab].filter(Boolean);
}

function sanitizeTextForLearning(text = "") {
  return String(text)
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[email]")
    .replace(/\b(?:\+?\d[\d\s-]{7,}\d)\b/g, "[number]")
    .replace(/\s+/g, " ")
    .trim();
}

function createEmptyArtifacts() {
  return {
    learned_typo_map: {},
    learned_awam_aliases: {},
    learned_topic_patterns: {},
    shadow_faq_candidates: [],
    shadow_faq_reviews: {
      approved_topics: {},
      rejected_topics: {},
      last_reviewed_at: null,
    },
    session_stats: {
      total_sessions: 0,
      total_turns: 0,
      farewell_sessions: 0,
      last_session_at: null,
    },
  };
}

function getStoredJson(key, fallback) {
  if (typeof window === "undefined" || !window.localStorage) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function setStoredJson(key, value) {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function getArchivedSessions() {
  return getStoredJson(SESSION_ARCHIVE_KEY, []);
}

function setArchivedSessions(sessions) {
  setStoredJson(SESSION_ARCHIVE_KEY, sessions);
}

function getLearnedArtifacts() {
  return getStoredJson(LEARNED_ARTIFACTS_KEY, createEmptyArtifacts());
}

function setLearnedArtifacts(artifacts) {
  setStoredJson(LEARNED_ARTIFACTS_KEY, artifacts);
}

function getDatasetTopicAliasBank() {
  const bank = {};

  for (const [category, aliases] of Object.entries(DATASET_CATEGORY_ALIASES)) {
    bank[category] = mergeUniqueStrings(bank[category], aliases, 220);
  }

  for (const item of ragDataset) {
    const category = normalizeText(item.category);
    if (!category) continue;

    const rawAliases = [
      category,
      String(item.id || "").replace(/_/g, " "),
      item.title,
      ...(item.keywords || []),
      ...(DATASET_CATEGORY_ALIASES[category] || []),
    ];

    const expandedAliases = [];
    for (const alias of rawAliases) {
      const normalizedAlias = normalizeText(alias);
      if (!normalizedAlias) continue;

      expandedAliases.push(normalizedAlias);
      normalizedAlias
        .split(" ")
        .filter((token) => token.length > 2 && !RAG_STOPWORDS.has(token))
        .forEach((token) => expandedAliases.push(token));
    }

    bank[category] = mergeUniqueStrings(bank[category], expandedAliases, 220);
  }

  return bank;
}

function getIntentSynonymBank() {
  const learnedArtifacts = getLearnedArtifacts();
  const approvedTopics =
    learnedArtifacts.shadow_faq_reviews?.approved_topics || {};
  const datasetTopicAliases = getDatasetTopicAliasBank();
  const bank = {};

  for (const intent of new Set([
    ...Object.keys(datasetTopicAliases),
    ...Object.keys(INTENT_PATTERNS),
    ...Object.keys(TOPIC_HINTS),
    ...Object.keys(AWAM_TOPIC_ALIASES),
    ...Object.keys(learnedArtifacts.learned_awam_aliases || {}),
    ...Object.keys(approvedTopics),
  ])) {
    bank[intent] = mergeUniqueStrings(
      [],
      [
        intent,
        ...(INTENT_PATTERNS[intent] || []),
        ...(TOPIC_HINTS[intent] || []),
        ...(AWAM_TOPIC_ALIASES[intent] || []),
        ...(datasetTopicAliases[intent] || []),
        ...(learnedArtifacts.learned_awam_aliases?.[intent] || []),
        ...(approvedTopics[intent]?.query_forms || []),
      ],
      120,
    )
      .map(normalizeText)
      .filter(Boolean);
  }

  return bank;
}

function getBaseTokensForLearning(text = "") {
  return normalizeText(text)
    .split(" ")
    .map((token) => {
      let normalized = normalizeText(token);
      if (normalized.length > 4) {
        normalized = normalized
          .replace(/(nya|kah|lah|pun)$/g, "")
          .replace(/(ku|mu)$/g, "")
          .trim();
      }
      return TYPO_TOKEN_MAP[normalized] || normalized;
    })
    .filter((token) => token.length > 1 && !RAG_STOPWORDS.has(token));
}

function getLearnedTypoMap() {
  if (learnedTypoCache) return learnedTypoCache;
  if (typeof window === "undefined" || !window.localStorage) return {};

  try {
    const failures = JSON.parse(
      window.localStorage.getItem(RAG_FAILURE_LOG_KEY) || "[]",
    );
    const tokenCounts = new Map();
    for (const entry of failures) {
      const tokens = getBaseTokensForLearning(entry?.userQuery || "");
      tokens.forEach((token) =>
        tokenCounts.set(token, (tokenCounts.get(token) || 0) + 1),
      );
    }

    const knownVocabulary = getKnownVocabulary();
    const learned = {};

    for (const [token, count] of tokenCounts.entries()) {
      if (
        count < 2 ||
        token.length < 4 ||
        knownVocabulary.includes(token) ||
        TYPO_TOKEN_MAP[token]
      )
        continue;

      let bestMatch = null;
      let bestDistance = Infinity;

      for (const vocab of knownVocabulary) {
        if (Math.abs(vocab.length - token.length) > 2) continue;
        const distance = levenshtein(token, vocab);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestMatch = vocab;
        }
      }

      if (bestMatch && bestDistance <= 2) learned[token] = bestMatch;
    }

    const persistedTypoMap = getLearnedArtifacts().learned_typo_map || {};
    learnedTypoCache = { ...persistedTypoMap, ...learned };
    return learnedTypoCache;
  } catch {
    return {};
  }
}

function normalizeToken(token = "") {
  let normalized = normalizeText(token);

  if (normalized.length > 4) {
    normalized = normalized
      .replace(/(nya|kah|lah|pun)$/g, "")
      .replace(/(ku|mu)$/g, "")
      .trim();
  }

  normalized = TYPO_TOKEN_MAP[normalized] || normalized;
  normalized = getLearnedTypoMap()[normalized] || normalized;

  return normalized;
}

function getBaseSearchTokens(text = "") {
  return normalizeText(text)
    .split(" ")
    .map(normalizeToken)
    .filter((token) => token.length > 1 && !RAG_STOPWORDS.has(token));
}

function detectTopicHints(text = "") {
  const normalized = normalizeText(text);
  const tokens = getBaseSearchTokens(text);
  const hints = new Set();
  const intentBank = getIntentSynonymBank();

  for (const [topic, aliases] of Object.entries(intentBank)) {
    if (
      aliases.some(
        (alias) => normalized.includes(alias) || tokens.includes(alias),
      )
    ) {
      hints.add(topic);
    }
  }

  return [...hints];
}

function classifyCampusIntent(text = "") {
  const normalized = normalizeText(text);
  const hits = Object.entries(getIntentSynonymBank())
    .map(([intent, patterns]) => ({
      intent,
      score: patterns.reduce(
        (sum, pattern) =>
          sum +
          (normalized.includes(pattern) ? (pattern.includes(" ") ? 2 : 1) : 0),
        0,
      ),
    }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  return hits[0]?.intent || null;
}

function resolveSlots(text = "", intent = null) {
  const normalized = normalizeText(text);
  const slotGroups = SLOT_PATTERNS[intent] || {};
  const resolved = {};

  for (const [slotName, patterns] of Object.entries(slotGroups)) {
    if (
      patterns.some((pattern) => normalized.includes(normalizeText(pattern)))
    ) {
      resolved[slotName] = true;
    }
  }

  return resolved;
}

function decomposeUserQuery(userQuery = "", topicState = null) {
  let normalized = userQuery;
  for (const separator of DECOMPOSITION_SEPARATORS) {
    normalized = normalized.replace(separator, " | ");
  }
  normalized = normalized.replace(/\s+(dan|sama)\s+/g, " | ");

  const parts = normalized
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean);

  const decomposed = (parts.length > 0 ? parts : [userQuery]).map((part) => {
    const intent =
      classifyCampusIntent(part) || topicState?.activeTopic || null;
    return {
      text: part,
      intent,
      slots: resolveSlots(part, intent),
    };
  });

  return decomposed;
}

function mergeUniqueStrings(existing = [], next = [], limit = 25) {
  return [...new Set([...(existing || []), ...(next || [])])]
    .filter(Boolean)
    .slice(-limit);
}

function extractSessionSignals(messages = []) {
  const userMessages = messages.filter((message) => message.role === "user");
  const topicCounts = new Map();
  const typoCandidates = new Map();
  const shadowCandidates = new Map();
  const followupPatterns = [];

  for (let index = 0; index < userMessages.length; index++) {
    const message = userMessages[index];
    const cleanText = sanitizeTextForLearning(message.text || "");
    const topicState = {
      activeTopic: null,
      orderedTopics: [],
    };
    const parts = decomposeUserQuery(cleanText, topicState);
    const intents = [
      ...new Set(parts.map((part) => part.intent).filter(Boolean)),
    ];

    intents.forEach((intent) =>
      topicCounts.set(intent, (topicCounts.get(intent) || 0) + 1),
    );

    const rawTokens = normalizeText(cleanText)
      .split(" ")
      .filter((token) => token.length > 2 && !RAG_STOPWORDS.has(token));
    const normalizedTokens = getBaseTokensForLearning(cleanText);
    rawTokens.forEach((token, tokenIndex) => {
      const canonical = normalizedTokens[tokenIndex];
      if (canonical && token !== canonical && !TYPO_TOKEN_MAP[token]) {
        typoCandidates.set(token, canonical);
      }
    });

    intents.forEach((intent) => {
      const bucket = shadowCandidates.get(intent) || [];
      bucket.push(cleanText);
      shadowCandidates.set(intent, bucket);
    });

    if (index < userMessages.length - 1) {
      const nextMessage = userMessages[index + 1];
      const nextIntent =
        classifyCampusIntent(nextMessage.text || "") ||
        detectTopicHints(nextMessage.text || "")[0] ||
        null;
      const currentIntent = intents[0] || null;
      if (currentIntent && nextIntent) {
        followupPatterns.push({
          topic: currentIntent,
          followup: sanitizeTextForLearning(nextMessage.text || ""),
          nextIntent,
        });
      }
    }
  }

  const dominantTopic =
    [...topicCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || null;

  return {
    dominantTopic,
    topicCounts: Object.fromEntries(topicCounts),
    typoCandidates: Object.fromEntries(typoCandidates),
    shadowCandidates: Object.fromEntries(
      [...shadowCandidates.entries()].map(([topic, queries]) => [
        topic,
        queries.slice(0, 5),
      ]),
    ),
    followupPatterns,
  };
}

function applySessionLearningToArtifacts(artifacts, session) {
  const next =
    typeof structuredClone !== "undefined"
      ? structuredClone(artifacts)
      : JSON.parse(JSON.stringify(artifacts));
  const signals = extractSessionSignals(session.messages || []);

  next.session_stats.total_sessions += 1;
  next.session_stats.total_turns += session.turns || 0;
  if (session.ended_by_farewell) next.session_stats.farewell_sessions += 1;
  next.session_stats.last_session_at = session.ended_at;

  Object.entries(signals.typoCandidates || {}).forEach(([token, canonical]) => {
    if (token && canonical && token !== canonical) {
      next.learned_typo_map[token] = canonical;
    }
  });

  Object.entries(signals.shadowCandidates || {}).forEach(([topic, queries]) => {
    next.learned_awam_aliases[topic] = mergeUniqueStrings(
      next.learned_awam_aliases[topic],
      queries,
      40,
    );

    const patternBucket = next.learned_topic_patterns[topic] || {
      common_followups: [],
    };
    patternBucket.common_followups = mergeUniqueStrings(
      patternBucket.common_followups,
      queries.slice(0, 3),
      20,
    );
    next.learned_topic_patterns[topic] = patternBucket;

    const existingCandidate = next.shadow_faq_candidates.find(
      (candidate) => candidate.suggested_topic === topic,
    );
    if (existingCandidate) {
      existingCandidate.query_forms = mergeUniqueStrings(
        existingCandidate.query_forms,
        queries,
        15,
      );
      existingCandidate.source_count += 1;
      existingCandidate.last_seen_at = session.ended_at;
    } else {
      next.shadow_faq_candidates.push({
        suggested_topic: topic,
        query_forms: [...new Set(queries)].slice(0, 10),
        source_count: 1,
        last_seen_at: session.ended_at,
      });
    }
  });

  for (const pattern of signals.followupPatterns || []) {
    const bucket = next.learned_topic_patterns[pattern.topic] || {
      common_followups: [],
    };
    bucket.common_followups = mergeUniqueStrings(
      bucket.common_followups,
      [pattern.followup],
      25,
    );
    next.learned_topic_patterns[pattern.topic] = bucket;
  }

  next.shadow_faq_candidates = next.shadow_faq_candidates
    .sort((a, b) => (b.source_count || 0) - (a.source_count || 0))
    .slice(0, 50);

  return {
    artifacts: next,
    signals,
  };
}

function pruneArchivedSessions(sessions = []) {
  const now = Date.now();
  return sessions
    .filter((session) => {
      const endedAt = new Date(session.ended_at || 0).getTime();
      return endedAt && now - endedAt <= SESSION_RETENTION_MS;
    })
    .slice(-SESSION_RETENTION_LIMIT);
}

export function archiveConversationSession({
  currentChat,
  lang = "id",
  endedByFarewell = true,
  endReason = endedByFarewell ? "farewell" : "session_end",
} = {}) {
  if (
    !currentChat?.messages?.length ||
    typeof window === "undefined" ||
    !window.localStorage
  ) {
    return null;
  }

  const endedAt = new Date().toISOString();
  const sanitizedMessages = currentChat.messages.map((message) => ({
    role: message.role,
    text: sanitizeTextForLearning(message.text || ""),
    ts: message.ts ? new Date(message.ts).toISOString() : null,
  }));

  const session = {
    session_id: currentChat.id || `session_${Date.now()}`,
    started_at: currentChat.createdAt
      ? new Date(currentChat.createdAt).toISOString()
      : endedAt,
    ended_at: endedAt,
    lang,
    turns: sanitizedMessages.length,
    messages: sanitizedMessages,
    ended_by_farewell: endedByFarewell,
    end_reason: endReason,
  };

  const sessions = pruneArchivedSessions([...getArchivedSessions(), session]);
  setArchivedSessions(sessions);

  const { artifacts, signals } = applySessionLearningToArtifacts(
    getLearnedArtifacts(),
    session,
  );
  setLearnedArtifacts(artifacts);
  learnedTypoCache = null;

  return {
    session,
    dominantTopic: signals.dominantTopic,
    artifacts,
  };
}

// ── Language Auto-Detection ──────────────────────────────────────────────────
// Deteksi bahasa dari teks user — digunakan untuk override lang prop
// kalau user jelas bicara dalam bahasa yang berbeda

const EN_INDICATORS = [
  "the ",
  " is ",
  " are ",
  " was ",
  " were ",
  "what ",
  "how ",
  "when ",
  "where ",
  "why ",
  " can ",
  " could ",
  " would ",
  "please ",
  " you ",
  " your ",
  " my ",
  " me ",
  " i ",
  "i'm ",
  "it's ",
  "don't ",
  "can't ",
  "what's ",
];

const ID_INDICATORS = [
  "yang ",
  " di ",
  " ke ",
  " dari ",
  " ini ",
  " itu ",
  " ada ",
  " tidak ",
  " bisa ",
  " saya ",
  " kamu ",
  " kami ",
  " apa ",
  "gimana",
  "bagaimana",
  "dimana",
  "kapan",
  "kenapa",
  " nih",
  " sih",
  " ya ",
  " dong",
  " deh",
  "apakah",
  "tolong",
  "banget",
  "emang",
];

/**
 * Deteksi bahasa teks — return 'en' atau 'id'
 * Hanya override jika deteksi Inggris jelas (margin > 1) agar tidak false positive
 */
function detectLang(text) {
  if (!text || text.length < 5) return null; // terlalu pendek, tidak bisa deteksi
  const lower = " " + text.toLowerCase() + " ";
  const enScore = EN_INDICATORS.filter((w) => lower.includes(w)).length;
  const idScore = ID_INDICATORS.filter((w) => lower.includes(w)).length;
  if (enScore > idScore + 1) return "en"; // jelas Inggris
  if (idScore > enScore) return "id"; // jelas Indonesia
  return null; // tidak yakin — pakai lang dari prop
}

// ── Transcribe ───────────────────────────────────────────────────────────────

/**
 * Transcribe audio blob ke teks via backend proxy
 * @param {Blob} audioBlob
 * @param {string} lang - 'id' | 'en'
 * @returns {Promise<string>}
 */
export async function transcribeAudio(audioBlob, lang = "id") {
  const formData = new FormData();
  formData.append("file", audioBlob, "audio.webm");
  formData.append("lang", lang);

  const res = await fetch("/api/transcribe", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Gagal mengenali suara. Coba lagi ya!");
  const { text } = await res.json();
  return text;
}

// ── Chat Completion ──────────────────────────────────────────────────────────

/**
 * Minta jawaban SELA dari backend. Klien tipis: hanya membersihkan transkrip,
 * mendeteksi bahasa, lalu mengirim { userQuery, riwayat_obrolan, bahasa }.
 * Seluruh RAG, routing, dan penyusunan prompt dikerjakan server (otak tunggal).
 * @param {Array} messageHistory - [{role, content}]
 * @param {string} lang - 'id' | 'en'
 * @returns {Promise<{ text: string, detectedLang: string }>}
 */
export async function getChatCompletion(messageHistory, lang = "id") {
  const rawUserQuery =
    messageHistory.length > 0
      ? messageHistory[messageHistory.length - 1].content
      : "";
  const preparedQuery = prepareTranscriptForRag(rawUserQuery);
  const userQuery = preparedQuery.cleanedText || rawUserQuery;

  // Auto-detect bahasa dari query user — override lang kalau deteksi yakin
  const autoLang = detectLang(userQuery);
  const effectiveLang = autoLang || lang;

  // ── Backend adalah OTAK TUNGGAL ─────────────────────────────────────────
  // Kirim pertanyaan mentah + riwayat saja. Seluruh RAG (leksikal BM25 +
  // semantik bge-m3), routing niat, web search, dan penyusunan prompt
  // dikerjakan server. Konteks TIDAK lagi dibangun di sini agar tidak ada dua
  // mesin retrieval yang bertabrakan (dulu Fuse.js di sini vs RAG backend).
  const riwayat = messageHistory
    .slice(0, -1)
    .map((m) => ({ role: m.role, content: m.content }));

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userQuery,
      riwayat_obrolan: riwayat,
      bahasa: effectiveLang,
      transcriptDebug: {
        rawUserQuery,
        cleanedUserQuery: userQuery,
        transcriptMarker: preparedQuery.marker,
        removedSegments: preparedQuery.removedSegments,
      },
    }),
  });

  if (!res.ok)
    throw new Error("Maaf, otak SELA lagi loading nih. Coba tanya lagi ya.");
  const data = await res.json();
  const text = data.text ?? data.teks ?? "";

  // Cek IGNORE_NOISE sebelum parsing, agar tidak muncul sebagai suggestion
  if (text?.trim().includes("[IGNORE_NOISE]")) {
    return {
      text: "[IGNORE_NOISE]",
      suggestions: [],
      media: [],
      detectedLang: effectiveLang,
    };
  }

  // Saran lanjutan sudah dikirim backend dalam format [Tanya?] | [Tanya?]
  const { text: cleanText, suggestions } = parseSuggestions(text || "");
  const displayText = cleanText || "Maaf, SELA agak bingung. Bisa diulang?";
  const spokenText = buildSpokenText(displayText, null, effectiveLang, []);

  return {
    text: displayText,
    spokenText,
    suggestions,
    media: Array.isArray(data.media) ? data.media : [],
    // Gerakan avatar dipilih backend sesuai sifat jawaban (Greeting, Goodbye,
    // Confused, Nodding, Shaking Head) agar animasi 3D sinkron dengan respons.
    gerakan: data.gerakan || null,
    detectedLang: effectiveLang,
  };
}

// ── Text-to-Speech ───────────────────────────────────────────────────────────

// ── Text-to-Speech & Voice Cloning Offline ──────────────────────────────────

// Variabel referensi pemutar audio aktif untuk interupsi instan (barge-in)
let pemutarAudioAktif = null;
let sesiPemutaranAktif = 0;

/**
 * Menghentikan seluruh pemutaran suara yang sedang berjalan (Audio Cloned & Web Speech)
 */
export function stopSpeaking() {
  sesiPemutaranAktif += 1;
  audioQueueManager.stop();
  if (pemutarAudioAktif) {
    try {
      pemutarAudioAktif.pause();
      pemutarAudioAktif.currentTime = 0;
    } catch (_) {}
    pemutarAudioAktif = null;
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {}
  }
}

/**
 * SELA Streaming Pipeline:
 * Mengirim kueri ke WebSocket /ws/dupleks, menerima potongan teks dan audio,
 * serta memutarnya secara berantai via audioQueueManager tanpa blocking.
 */
export function streamChatAndVoice({
  query,
  history = [],
  lang = "id",
  onTextChunk,
  onAudioChunk,
  onSentencePlay,
  onStart,
  onEnd,
  onDone,
  onError,
}) {
  const isSecure = typeof window !== "undefined" && window.location.protocol === "https:";
  const defaultHost = "127.0.0.1:8008";
  const host =
    typeof window !== "undefined" &&
    window.location.host &&
    !window.location.protocol.startsWith("file")
      ? window.location.host
      : defaultHost;
  const protocol = isSecure ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${host}/ws/dupleks`;
  let socket = null;
  let hasOpened = false;

  audioQueueManager.startSession({
    onStart,
    onEnd,
    onSentence: (sentence) => {
      if (onSentencePlay) onSentencePlay(sentence);
    },
  });

  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    if (onError) onError(err);
    return null;
  }

  const connectionTimeout = setTimeout(() => {
    if (!hasOpened) {
      console.warn("[SELA Streaming] WebSocket connection timeout, closing...");
      try {
        socket.close();
      } catch (_) {}
      if (onError) onError(new Error("WebSocket connection timeout"));
    }
  }, 4000);

  socket.onopen = () => {
    hasOpened = true;
    clearTimeout(connectionTimeout);
    socket.send(
      JSON.stringify({
        tipe: "tanya",
        kueri: query,
        riwayat: history,
        bahasa: lang,
      })
    );
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.tipe === "potongan_teks" && data.kalimat) {
        if (onTextChunk) onTextChunk(data.kalimat);
      } else if (data.tipe === "potongan_teks_fallback_tts" && data.kalimat) {
        // TTS server gagal - gunakan Web Speech API untuk kalimat ini
        if (onTextChunk) onTextChunk(data.kalimat);
        try {
          if ("speechSynthesis" in window) {
            const utter = new SpeechSynthesisUtterance(data.kalimat);
            utter.lang = data.bahasa === "en" ? "en-US" : "id-ID";
            utter.rate = 1.0;
            utter.pitch = 1.1;
            window.speechSynthesis.speak(utter);
          }
        } catch (_) {}
      } else if (data.tipe === "potongan_audio" && data.audio_base64) {
        audioQueueManager.enqueue({
          audio_base64: data.audio_base64,
          format: data.format || "audio/wav",
          sentence: data.kalimat,
        });
        if (onAudioChunk) onAudioChunk(data);
      } else if (data.tipe === "selesai") {
        audioQueueManager.markStreamFinished();
        if (onDone) onDone(data);
        try {
          socket.close();
        } catch (_) {}
      }
    } catch (parseErr) {
      console.warn("[SELA Streaming] Gagal membaca paket WebSocket:", parseErr);
    }
  };

  socket.onerror = (err) => {
    console.warn("[SELA Streaming] WebSocket error:", err);
    clearTimeout(connectionTimeout);
    if (onError) onError(err);
  };

  return {
    cancel: () => {
      clearTimeout(connectionTimeout);
      audioQueueManager.stop();
      if (socket && socket.readyState === WebSocket.OPEN) {
        try {
          socket.send(JSON.stringify({ tipe: "interupsi" }));
          socket.close();
        } catch (_) {}
      }
    },
  };
}


/**
 * Memainkan suara respon SELA menggunakan audio hasil Voice Cloning offline dari backend
 * @param {string} text Teks yang akan diucapkan
 * @param {function} onStart Callback saat audio mulai bersuara (mengubah avatar ke 'speaking')
 * @param {function} onEnd Callback saat audio selesai (mengubah avatar kembali ke 'idle')
 * @param {string} lang Bahasa ('id' | 'en')
 */
export async function speakText(text, onStart, onEnd, lang = "id") {
  // Hentikan suara sebelumnya seketika (barge-in)
  stopSpeaking();
  const sesiIni = sesiPemutaranAktif;
  unlockAudioContext();

  if (!text || !text.trim()) {
    if (onEnd) onEnd();
    return;
  }

  const masihSesiAktif = () => sesiIni === sesiPemutaranAktif;
  let fallbackDimulai = false;
  const selesai = () => {
    if (masihSesiAktif() && onEnd) onEnd();
  };
  const akhiriKegagalanTts = () => {
    if (!masihSesiAktif() || fallbackDimulai) return;
    fallbackDimulai = true;
    console.warn("[SELA TTS] Audio Piper gagal diputar; tidak mengganti suara SELA dengan engine lain.");
    selesai();
  };

  // Hanya gunakan audio Piper agar karakter suara SELA konsisten.
  try {
    const controller = new AbortController();
    // Sintesis Piper pada CPU bisa butuh waktu untuk kalimat panjang.
    // Timeout lama mencegah audio dibatalkan tepat sebelum siap.
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    const respons = await fetch("/api/sintesis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teks_kalimat: text, bahasa: lang }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (respons.ok) {
      const dataSintesis = await respons.json();
      if (dataSintesis.audio_base64) {
        console.log(`[SELA TTS] Memainkan suara Piper (${dataSintesis.engine || 'piper'})`);
        
        // Konversi base64 ke Blob URL untuk performa audio dan lipsync optimal
        const binaryString = atob(dataSintesis.audio_base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: dataSintesis.format || "audio/wav" });
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        audio.volume = 1.0;
        pemutarAudioAktif = audio;

        // Hubungkan ke Wawa Lipsync untuk analisis frekuensi audio real-time
        connectAudioToLipsync(audio);

        audio.onplay = () => {
          if (masihSesiAktif() && onStart) onStart();
        };

        audio.onended = () => {
          URL.revokeObjectURL(audioUrl);
          if (masihSesiAktif()) pemutarAudioAktif = null;
          selesai();
        };

        audio.onerror = (galatAudio) => {
          console.warn("[SELA TTS] Kendala pemutaran audio Piper:", galatAudio);
          URL.revokeObjectURL(audioUrl);
          if (masihSesiAktif()) pemutarAudioAktif = null;
          akhiriKegagalanTts();
        };

        try {
          await audio.play();
          return;
        } catch (playErr) {
          console.warn("[SELA TTS] audio.play() gagal diputar (kebijakan browser):", playErr);
          URL.revokeObjectURL(audioUrl);
          if (masihSesiAktif()) pemutarAudioAktif = null;
          akhiriKegagalanTts();
          return;
        }
      }
    }
  } catch (galatKoneksi) {
    console.warn("[SELA TTS] Endpoint sintesis backend error:", galatKoneksi?.message);
  }

  akhiriKegagalanTts();
}

// ── Time-based Greeting ──────────────────────────────────────────────────────

/**
 * Get greeting based on current time of day
 * @param {string} lang - 'id' | 'en'
 * @returns {string} - Time-appropriate greeting
 */
export function getTimeBasedGreeting(lang = "id") {
  if (lang === "en") {
    return "Hello! Welcome to Catur Insan Cendekia University. How can Sela assist you today?";
  }
  return "Halo! Selamat datang di Universitas Catur Insan Cendekia Cirebon. Ada yang bisa Sela bantu?";
}

// ── Follow-up Suggestion Parser ──────────────────────────────────────────────

/**
 * Parse follow-up suggestions from LLM response
 * Format: "Some response text [Question1?] | [Question2?] | [Question3?]"
 * Returns: { text (without suggestions), suggestions (array of strings) }
 * @param {string} text - Response text from LLM
 * @returns {object} - { text: string, suggestions: Array<string> }
 */
export function parseSuggestions(text) {
  if (!text) return { text: "", suggestions: [] };

  // Extract all [Question?] patterns
  const matches = text.match(/\[(.*?)\]/g);

  if (matches && matches.length > 0) {
    const suggestions = matches
      .map((s) => s.slice(1, -1).trim())
      .filter((s) => s.length > 0);
    // Remove suggestion markers from display text, including separator pipes
    const cleanText = text.replace(/\s*\[.*?\]\s*\|?\s*/g, "").trim();
    return { text: cleanText, suggestions };
  }

  return { text, suggestions: [] };
}
