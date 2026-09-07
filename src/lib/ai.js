import Fuse from "fuse.js";
import dataset from "../data/ucic_dataset.json";
import ragGoldens from "../data/rag_goldens.json";
import {
  buildResponsePlan,
  buildResponsePlanPrompt,
  buildSpokenText,
  prioritizeResponseMatches,
} from "./responsePlan";

// ── RAG Setup ────────────────────────────────────────────────────────────────

let fuse = null;
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

const BROAD_SYNONYM_KEYS = new Set(["akademik"]);
const GENERIC_REVERSE_SYNONYM_TOKENS = new Set([
  "fakultas",
  "jurusan",
  "prodi",
  "program",
  "studi",
]);

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

const REFERENTIAL_TOKENS = new Set([
  "itu",
  "ituh",
  "tadi",
  "yang",
  "yg",
  "nya",
  "terus",
  "trus",
  "lanjut",
  "lanjutnya",
  "kalo",
  "kalau",
  "tersebut",
  "begitu",
  "gitu",
  "gini",
  "ini",
  "ygitu",
]);

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
const RAG_EVALUATION_KEY = "sela_rag_evaluation_v1";
const SESSION_RETENTION_LIMIT = 20;
const SESSION_RETENTION_MS = 1000 * 60 * 60 * 24 * 14;
const SHADOW_REVIEW_MIN_SOURCE_COUNT = 2;

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

const PROGRAM_REFERENCE_ALIASES = [
  {
    label: "S1 Teknik Informatika",
    aliases: ["s1 teknik informatika", "teknik informatika", "informatika", "ti"],
  },
  {
    label: "S1 Sistem Informasi",
    aliases: ["s1 sistem informasi", "sistem informasi", "si"],
  },
  {
    label: "S1 Desain Komunikasi Visual",
    aliases: ["s1 desain komunikasi visual", "desain komunikasi visual", "dkv"],
  },
  {
    label: "D3 Manajemen Informatika",
    aliases: ["d3 manajemen informatika", "manajemen informatika"],
  },
  {
    label: "S1 Manajemen",
    aliases: ["s1 manajemen", "manajemen"],
  },
  {
    label: "S1 Akuntansi",
    aliases: ["s1 akuntansi", "akuntansi"],
  },
  {
    label: "S1 Bisnis Digital",
    aliases: ["s1 bisnis digital", "bisnis digital"],
  },
  {
    label: "D3 Manajemen Bisnis",
    aliases: ["d3 manajemen bisnis", "manajemen bisnis"],
  },
  {
    label: "S1 Pendidikan Kepelatihan Olahraga",
    aliases: [
      "s1 pendidikan kepelatihan olahraga",
      "pendidikan kepelatihan olahraga",
      "pko",
      "pkor",
      "olahraga",
    ],
  },
];

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

function getSearchTokens(text = "") {
  const tokens = getBaseSearchTokens(text);

  const expanded = new Set(tokens);
  for (const token of tokens) {
    if (RAG_SYNONYMS[token] && !BROAD_SYNONYM_KEYS.has(token)) {
      RAG_SYNONYMS[token].forEach((alias) => expanded.add(alias));
    }
    for (const [canonical, aliases] of Object.entries(RAG_SYNONYMS)) {
      if (
        aliases.includes(token) &&
        !GENERIC_REVERSE_SYNONYM_TOKENS.has(token)
      ) {
        expanded.add(canonical);
      }
    }
  }

  return [...expanded];
}

function getBaseSearchTokens(text = "") {
  return normalizeText(text)
    .split(" ")
    .map(normalizeToken)
    .filter((token) => token.length > 1 && !RAG_STOPWORDS.has(token));
}

function getExplicitTopics(text = "") {
  return [
    ...new Set([
      classifyCampusIntent(text),
      ...detectTopicHints(text),
      ...getAliasBoostTopics(text),
    ].filter(Boolean)),
  ];
}

function includesNormalizedPhrase(text = "", phrase = "") {
  const normalizedText = ` ${normalizeText(text)} `;
  const normalizedPhrase = normalizeText(phrase);
  if (!normalizedPhrase) return false;
  return normalizedText.includes(` ${normalizedPhrase} `);
}

function extractProgramReferences(text = "") {
  return PROGRAM_REFERENCE_ALIASES.filter((program) =>
    program.aliases.some((alias) => includesNormalizedPhrase(text, alias)),
  ).map((program) => program.label);
}

function getRecentReferencedPrograms(
  messageHistory = [],
  queryContinuity = "standalone",
) {
  if (queryContinuity === "standalone") return [];

  const referenceMessages = getRecentReferenceMessages(
    messageHistory,
    getReferenceMessageLimit(queryContinuity),
  );

  const latestAssistantWithPrograms = [...referenceMessages]
    .reverse()
    .find((message) => {
      if (message.role !== "assistant") return false;
      return extractProgramReferences(message.content).length > 0;
    });

  if (latestAssistantWithPrograms) {
    return [
      ...new Set(extractProgramReferences(latestAssistantWithPrograms.content)),
    ];
  }

  return [
    ...new Set(
      referenceMessages.flatMap((message) =>
        extractProgramReferences(message.content),
      ),
    ),
  ];
}

function isComparisonFollowUp(text = "") {
  const normalized = normalizeText(text);
  return [
    "beda",
    "bedanya",
    "perbedaan",
    "perbedaannya",
    "banding",
    "bandingkan",
    "dibanding",
    "vs",
    "versus",
  ].some((phrase) => normalized.includes(phrase));
}

function hasReferentialSignal(text = "") {
  const normalized = normalizeText(text);
  const tokens = normalized.split(" ").filter(Boolean);
  return tokens.some(
    (token) =>
      REFERENTIAL_TOKENS.has(token) ||
      (token.length > 4 && token.endsWith("nya")),
  );
}

function classifyQueryContinuity(userQuery = "", messageHistory = []) {
  const previousUserMessages = messageHistory
    .slice(0, -1)
    .filter((message) => message.role === "user" && message.content);
  if (previousUserMessages.length === 0) return "standalone";

  const baseTokens = getBaseSearchTokens(userQuery);
  const explicitTopics = getExplicitTopics(userQuery);
  const referential = hasReferentialSignal(userQuery);

  if (referential) return "referential_followup";
  if (baseTokens.length <= 1 && explicitTopics.length === 0)
    return "ambiguous_followup";

  return "standalone";
}

function getRecentReferenceMessages(messageHistory = [], limit = 4) {
  return messageHistory
    .slice(0, -1)
    .filter(
      (message) =>
        (message.role === "user" || message.role === "assistant") &&
        message.content,
    )
    .slice(-limit);
}

function getReferenceMessageText(message = "", maxLength = 500) {
  return String(message?.content || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function getReferenceMessageLimit(queryContinuity = "standalone") {
  return queryContinuity === "referential_followup" ? 2 : 4;
}

function buildConversationContextHint(
  messageHistory = [],
  latestIntent = null,
  queryContinuity = "standalone",
) {
  if (queryContinuity === "standalone") return "";

  const referenceMessages = getRecentReferenceMessages(
    messageHistory,
    getReferenceMessageLimit(queryContinuity),
  );
  if (referenceMessages.length === 0) return "";

  const topics = [];
  const details = [];
  const referencedPrograms = getRecentReferencedPrograms(
    messageHistory,
    queryContinuity,
  );

  for (const message of [...referenceMessages].reverse()) {
    const content = getReferenceMessageText(message, 400);
    topics.push(...getExplicitTopics(content));
    details.push(...getBaseSearchTokens(content).slice(0, 14));
  }

  const topicText = [...new Set(topics.filter((topic) => topic !== latestIntent))]
    .slice(0, 3)
    .join(", ");
  const detailText = [...new Set(details)].slice(0, 14).join(", ");

  if (!topicText && !detailText) return "";

  return [
    "Pertanyaan terbaru tampak merujuk ke percakapan sebelumnya.",
    referencedPrograms.length > 0
      ? `Rujukan paling mungkin: ${referencedPrograms.join(", ")}.`
      : "",
    topicText ? `Topik sebelumnya: ${topicText}.` : "",
    detailText ? `Kata kunci sebelumnya: ${detailText}.` : "",
    referencedPrograms.length > 1 && isComparisonFollowUp(messageHistory.at(-1)?.content)
      ? "Jika user menanyakan perbedaan/bedanya, bandingkan rujukan tersebut saja."
      : "",
    "Gunakan ini hanya untuk memahami rujukan user di sesi aktif; fakta jawaban tetap wajib dari KONTEKS KAMPUS. Jangan anggap ini sebagai preferensi permanen.",
  ]
    .filter(Boolean)
    .join(" ");
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

function getAliasBoostTopics(text = "") {
  const normalized = normalizeText(text);
  const topics = new Set();
  for (const [topic, aliases] of Object.entries(getIntentSynonymBank())) {
    if (
      (aliases || []).some((alias) => normalized.includes(normalizeText(alias)))
    )
      topics.add(topic);
  }
  return [...topics];
}

function deriveConversationTopicState(messageHistory = []) {
  const recentUserMessages = [...messageHistory]
    .filter((message) => message.role === "user" && message.content)
    .slice(-4);

  const scores = new Map();
  const orderedTopics = [];
  const learnedPatterns = getLearnedArtifacts().learned_topic_patterns || {};

  for (const message of recentUserMessages) {
    const topics = new Set(
      [
        classifyCampusIntent(message.content),
        ...detectTopicHints(message.content),
        ...getAliasBoostTopics(message.content),
      ].filter(Boolean),
    );

    for (const topic of topics) {
      scores.set(topic, (scores.get(topic) || 0) + 1);
    }
  }

  const latestMessage =
    recentUserMessages[recentUserMessages.length - 1]?.content || "";
  const latestNormalized = normalizeText(latestMessage);
  for (const [topic, patternData] of Object.entries(learnedPatterns)) {
    if (
      (patternData?.common_followups || []).some((pattern) =>
        latestNormalized.includes(normalizeText(pattern)),
      )
    ) {
      scores.set(topic, (scores.get(topic) || 0) + 2);
    }
  }

  orderedTopics.push(
    ...[...scores.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([topic]) => topic),
  );

  return {
    activeTopic: orderedTopics[0] || null,
    orderedTopics,
    recentUserMessages: recentUserMessages.map((message) => message.content),
  };
}

function getTokenVariants(token) {
  const variants = new Set([token]);
  if (RAG_SYNONYMS[token] && !BROAD_SYNONYM_KEYS.has(token)) {
    RAG_SYNONYMS[token].forEach((alias) => variants.add(alias));
  }
  for (const [canonical, aliases] of Object.entries(RAG_SYNONYMS)) {
    if (
      aliases.includes(token) &&
      !GENERIC_REVERSE_SYNONYM_TOKENS.has(token)
    ) {
      variants.add(canonical);
    }
  }
  return [...variants];
}

function itemContainsTokenVariant(item, token) {
  const variants = getTokenVariants(token);
  const title = normalizeText(item.title);
  const category = normalizeText(item.category);
  const keywords = (item.keywords || []).map(normalizeText);
  const content = normalizeText(item.content);

  return variants.some(
    (variant) =>
      keywords.some((keyword) => keyword.includes(variant)) ||
      title.includes(variant) ||
      category.includes(variant) ||
      content.includes(variant),
  );
}

function getMatchedTokenCount(item, baseTokens) {
  return baseTokens.filter((token) =>
    itemContainsTokenVariant(item, token),
  ).length;
}

function hasStrongFieldMatch(item, baseTokens) {
  const title = normalizeText(item.title);
  const category = normalizeText(item.category);
  const keywords = (item.keywords || []).map(normalizeText);

  return baseTokens.some((token) => {
    const variants = getTokenVariants(token);
    return variants.some(
      (variant) =>
        category === variant ||
        title.split(" ").includes(variant) ||
        keywords.some(
          (keyword) => keyword === variant || keyword.split(" ").includes(variant),
        ),
    );
  });
}

function hasEnoughTokenCoverage(item, baseTokens, score = 0) {
  if (baseTokens.length === 0) return item.id === "profil_ucic";
  const matchedCount = getMatchedTokenCount(item, baseTokens);
  if (matchedCount === 0) return false;
  if (baseTokens.length <= 2) return true;
  if (hasStrongFieldMatch(item, baseTokens)) return true;
  if (score >= 14 && matchedCount >= 1) return true;

  const requiredMatches =
    baseTokens.length === 1 ? 1 : Math.min(2, baseTokens.length);
  return matchedCount >= requiredMatches;
}

function scoreDatasetItem(item, tokens, topicHints = [], userQuery = "") {
  if (tokens.length === 0) {
    const q = normalizeText(item.title);
    return item.id === "profil_ucic" || q.includes("profil universitas")
      ? 1
      : 0;
  }

  const title = normalizeText(item.title);
  const category = normalizeText(item.category);
  const keywords = (item.keywords || []).map(normalizeText);
  const content = normalizeText(item.content);
  const searchableText = [title, category, ...keywords, content].join(" ");
  const normalizedQuery = normalizeText(userQuery);
  let score = 0;

  if (normalizedQuery) {
    if (keywords.some((keyword) => keyword.includes(normalizedQuery)))
      score += 24;
    if (title.includes(normalizedQuery)) score += 18;
    if (content.includes(normalizedQuery)) score += 6;

    for (const keyword of keywords) {
      if (keyword.length < 4) continue;
      if (normalizedQuery.includes(keyword)) score += 18;
    }
  }

  for (const token of tokens) {
    if (keywords.some((keyword) => keyword === token)) score += 8;
    if (keywords.some((keyword) => keyword.includes(token))) score += 4;
    if (title.split(" ").includes(token)) score += 7;
    else if (title.includes(token)) score += 3;
    if (category === token) score += 3;
    if (content.split(" ").includes(token)) score += 2.5;
    else if (content.includes(token)) score += 1;
  }

  const matchedTokens = tokens.filter(
    (token) =>
      keywords.some((keyword) => keyword.includes(token)) ||
      title.includes(token) ||
      content.includes(token) ||
      category.includes(token),
  );

  if (tokens.length > 1 && matchedTokens.length > 1)
    score += matchedTokens.length * 3;

  for (const topic of topicHints) {
    if (
      keywords.some((keyword) => keyword.includes(topic)) ||
      title.includes(topic) ||
      category.includes(topic) ||
      content.includes(topic)
    ) {
      score += 4;
    }
  }

  const adjacentPairs = tokens
    .map((token, index) => [token, tokens[index + 1]].filter(Boolean).join(" "))
    .filter((pair) => pair.split(" ").length === 2);
  for (const pair of adjacentPairs) {
    if (keywords.some((keyword) => keyword.includes(pair))) score += 12;
    else if (title.includes(pair)) score += 10;
    else if (content.includes(pair)) score += 5;
  }

  return score;
}

function retrieveCampusContext(userQuery, fuseResults = [], topicState = null) {
  const tokens = getSearchTokens(userQuery);
  const baseTokens = getBaseSearchTokens(userQuery);
  const explicitTopics = [
    ...new Set([
      classifyCampusIntent(userQuery),
      ...detectTopicHints(userQuery),
      ...getAliasBoostTopics(userQuery),
    ].filter(Boolean)),
  ];
  const topicHints = [
    ...new Set(
      explicitTopics.length > 0
        ? explicitTopics
        : (topicState?.orderedTopics || []).slice(0, 2),
    ),
  ];
  const intent = explicitTopics[0] || topicState?.activeTopic || null;
  const fuseRank = new Map(
    fuseResults.map((result, index) => [
      result.item.id,
      {
        score: result.score ?? 1,
        rank: index,
      },
    ]),
  );

  const ranked = ragDataset
    .map((item) => {
      const lexicalScore = scoreDatasetItem(item, tokens, topicHints, userQuery);
      const fuseMeta = fuseRank.get(item.id);
      const fuseBoost = fuseMeta ? Math.max(0, 4 - fuseMeta.rank * 0.35) : 0;
      const fuseQualityBoost = fuseMeta ? Math.max(0, 1 - fuseMeta.score) : 0;
      const score = lexicalScore + fuseBoost + fuseQualityBoost;
      return {
        item,
        score,
        matchedTokenCount: getMatchedTokenCount(item, baseTokens),
        fuseScore: fuseMeta?.score,
      };
    })
    .filter(
      (result) =>
        result.score >= 4 &&
        hasEnoughTokenCoverage(result.item, baseTokens, result.score),
    )
    .sort((a, b) => b.score - a.score);

  const fuseFallback = fuseResults
    .slice(0, 5)
    .filter((result) => (result.score ?? 1) <= 0.42)
    .map((result, index) => ({
      item: result.item,
      score: Math.max(8, 14 - index),
      fuseScore: result.score,
    }))
    .filter(
      (result) =>
        !ranked.some((rankedResult) => rankedResult.item.id === result.item.id),
    );

  const combined = [...ranked, ...fuseFallback].sort(
    (a, b) => b.score - a.score,
  );

  return {
    matches: combined.slice(0, 5),
    tokens,
    topicHints,
    intent,
  };
}

function getTopicFallbackMatches(intent = null, topicHints = []) {
  const topics = new Set([intent, ...topicHints].filter(Boolean));
  if (topics.size === 0) return [];

  const fallback = ragDataset
    .map((item) => ({
      item,
      score: scoreDatasetItem(item, [...topics], [...topics]),
    }))
    .filter((result) => result.score >= 6)
    .sort((a, b) => b.score - a.score);

  return fallback.slice(0, 3);
}

function buildCanonicalRewrite(userQuery = "", topicState = null) {
  const decomposed = decomposeUserQuery(userQuery, topicState);
  const rewrites = decomposed
    .map((part) => {
      const detectedTopic =
        part.intent ||
        detectTopicHints(part.text)[0] ||
        getAliasBoostTopics(part.text)[0] ||
        topicState?.activeTopic ||
        null;

      if (!detectedTopic) return "";

      const canonical = CANONICAL_REWRITE_MAP[detectedTopic] || "";
      if (!canonical) return "";

      const slotTokens = Object.keys(part.slots || {}).join(" ");
      const baseTokens = getBaseSearchTokens(part.text);
      const specifics = baseTokens
        .filter((token) => !Object.keys(CANONICAL_REWRITE_MAP).includes(token))
        .slice(0, 4)
        .join(" ");

      return `${canonical} ${slotTokens} ${specifics}`.trim();
    })
    .filter(Boolean);

  return rewrites.join(" ");
}

function buildRetrievalQuery(
  messageHistory = [],
  userQuery = "",
  topicState = null,
  queryContinuity = "standalone",
) {
  const explicitLatestTopics = getExplicitTopics(userQuery);

  if (queryContinuity === "standalone") return userQuery;
  const referenceMessages = getRecentReferenceMessages(
    messageHistory,
    getReferenceMessageLimit(queryContinuity),
  );
  if (referenceMessages.length === 0) return userQuery;

  const previousContext = referenceMessages
    .map((message) => getReferenceMessageText(message, 500))
    .filter(Boolean)
    .join(" ");

  const historyTopics = detectTopicHints(previousContext).filter(
    (topic) => !explicitLatestTopics.includes(topic),
  );
  const topicSuffix =
    historyTopics.length > 0 ? ` ${historyTopics.join(" ")}` : "";
  const canonicalRewrite = buildCanonicalRewrite(userQuery, topicState);
  const referencedPrograms = getRecentReferencedPrograms(
    messageHistory,
    queryContinuity,
  );
  const referenceFocus =
    referencedPrograms.length > 0
      ? `${isComparisonFollowUp(userQuery) ? "perbedaan " : ""}${referencedPrograms.join(" ")}`
      : "";

  return `${referenceFocus} ${previousContext} ${userQuery} ${canonicalRewrite}${topicSuffix}`.trim();
}

function computeAnswerability(
  finalMatches = [],
  userQuery = "",
  topicState = null,
) {
  if (finalMatches.length === 0) return { level: "none", reason: "no_match" };

  const top = finalMatches[0];
  const score = top.score || 0;
  const detectedTopic =
    classifyCampusIntent(userQuery) || topicState?.activeTopic;

  if (score >= 18)
    return { level: "high", reason: "strong_match", detectedTopic };
  if (score >= 10)
    return { level: "partial", reason: "medium_match", detectedTopic };
  return { level: "weak", reason: "low_confidence", detectedTopic };
}

function buildClarificationHint(answerability, decomposedQueries, topicState) {
  if (answerability.level === "high") return "";

  const intents = [
    ...new Set(decomposedQueries.map((part) => part.intent).filter(Boolean)),
  ];
  if (intents.length > 1) {
    return `User tampaknya menanyakan beberapa hal sekaligus: ${intents.join(", ")}. Jika konteks tidak cukup untuk semua bagian, jawab bagian yang jelas terlebih dahulu lalu minta user memilih bagian yang ingin diperjelas.`;
  }

  if (answerability.level === "partial") {
    return `Jika ada informasi yang hanya terjawab sebagian, berikan jawaban parsial dulu lalu akhiri dengan satu klarifikasi singkat yang spesifik ke topik ${answerability.detectedTopic || topicState?.activeTopic || "kampus"}.`;
  }

  return `Maksud user masih samar. Ajukan satu pertanyaan klarifikasi yang sangat singkat dan ramah, fokus pada topik ${answerability.detectedTopic || topicState?.activeTopic || "yang paling mungkin dimaksud"}.`;
}

function buildConfidenceRouting(answerability, decomposedQueries, topicState) {
  const intents = [
    ...new Set(decomposedQueries.map((part) => part.intent).filter(Boolean)),
  ];
  const primaryTopic =
    answerability.detectedTopic ||
    topicState?.activeTopic ||
    intents[0] ||
    "kampus";

  if (answerability.level === "high") {
    return {
      route: "answer_direct",
      label: "tinggi",
      instruction: `Confidence tinggi. Jawab langsung dengan fokus utama pada topik ${primaryTopic}.`,
    };
  }

  if (answerability.level === "partial") {
    return {
      route: "answer_then_clarify",
      label: "sedang",
      instruction: `Confidence sedang. Jawab dulu bagian yang paling jelas dari topik ${primaryTopic}, lalu akhiri dengan satu klarifikasi singkat jika masih ada detail yang belum pasti.`,
    };
  }

  return {
    route: "clarify_first",
    label: "rendah",
    instruction: `Confidence rendah. Jangan menebak. Ajukan satu pertanyaan klarifikasi yang pendek, ramah, dan spesifik ke topik ${primaryTopic}.`,
  };
}

function buildIntentResponseGuide(intent = null) {
  switch (intent) {
    case "pendaftaran":
      return "Untuk topik pendaftaran, jawab cara daftar dan langkah inti saja. Jangan jelaskan detail lain kecuali diminta.";
    case "biaya":
      return "Untuk topik biaya, jawab nominal yang ditanya secara langsung. Tambahkan komponen lain hanya jika user meminta rincian.";
    case "jurusan":
      return "Untuk topik jurusan, jawab sesuai yang ditanya: daftar prodi jika user minta daftar, rekomendasi jika user minta jurusan yang cocok, atau perbedaan prodi jika user minta bedanya. Jangan melebar ke semua prodi jika user sedang merujuk prodi tertentu dari percakapan sebelumnya.";
    case "syarat":
      return "Untuk topik syarat, beri daftar berkas inti saja dengan nomor pendek.";
    case "kelas":
      return "Untuk topik kelas, sebutkan pilihan kelas dan jamnya secara singkat.";
    case "lokasi":
      return "Untuk topik lokasi, jawab alamat langsung. Jika ada dua kampus, sebutkan keduanya secara singkat.";
    case "akademik":
      return "Untuk topik akademik, jawab sesuai prosedur BAAK atau pedoman akademik di konteks. Sebutkan syarat, alur, atau batasan penting yang memang tertulis.";
    case "kurikulum":
      return "Untuk topik kurikulum, sebutkan program studi yang dimaksud dan ringkas mata kuliah atau semester yang tersedia di konteks.";
    case "fasilitas":
      return "Untuk topik fasilitas, sebutkan fasilitas yang relevan saja. Jika user menanyakan tempat tertentu seperti perpustakaan, lab, parkir, atau WiFi, fokus ke tempat itu.";
    case "dosen":
      return "Untuk topik dosen, sebutkan nama dosen dan bidang atau prodi terkait hanya jika ada di konteks.";
    case "kegiatan":
      return "Untuk topik kegiatan mahasiswa, jawab jenis kegiatan, UKM, organisasi, atau agenda mahasiswa yang tersedia di konteks.";
    case "profil":
      return "Untuk topik profil kampus, jawab fakta identitas, sejarah, pimpinan, kerja sama, atau keunggulan UCIC sesuai konteks.";
    case "rektor":
      return "Untuk topik rektor atau pimpinan, jawab nama rektor secara langsung sesuai konteks. Jangan meminta user menghubungi kampus jika nama rektor ada di konteks.";
    default:
      return "Jawab ringkas, ramah, dan langsung ke inti informasi yang ditanya.";
  }
}

const UNAVAILABLE_RESPONSE_PATTERNS = [
  /belum punya informasi/i,
  /belum memiliki informasi/i,
  /tidak memiliki informasi/i,
  /tidak punya informasi/i,
  /informasi.*belum tersedia/i,
  /menanyakannya langsung/i,
  /hubungi.*kampus/i,
  /check with the campus/i,
  /does not have.*information/i,
  /do not have.*information/i,
  /not have.*information/i,
  /information.*not available/i,
];

function looksLikeUnavailableAnswer(text = "") {
  return UNAVAILABLE_RESPONSE_PATTERNS.some((pattern) =>
    pattern.test(String(text || "")),
  );
}

function truncateForVoice(text = "", maxLength = 650) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;

  const clipped = normalized.slice(0, maxLength);
  const sentenceEnd = Math.max(
    clipped.lastIndexOf("."),
    clipped.lastIndexOf("?"),
    clipped.lastIndexOf("!"),
  );
  if (sentenceEnd > 180) return clipped.slice(0, sentenceEnd + 1).trim();
  return `${clipped.replace(/\s+\S*$/, "").trim()}.`;
}

function buildDatasetAnswerFromMatches(
  matches = [],
  effectiveLang = "id",
  responsePlan = null,
) {
  const contents = matches
    .map((match) => match?.item?.content?.trim())
    .filter(Boolean);
  if (contents.length === 0) return "";

  const topContent = contents[0];
  if (!responsePlan || responsePlan.displayMode === "brief") {
    const content = truncateForVoice(topContent);
    if (effectiveLang === "en") return content;
    return content;
  }

  const maxSections = responsePlan.displayMode === "list_detail" ? 4 : 2;
  const merged = [...new Set(contents)].slice(0, maxSections).join("\n\n");
  if (effectiveLang === "en") return merged;
  return merged;
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

function logRetrievalFailure(payload) {
  console.warn("[SELA RAG] Retrieval weakness:", payload);
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    const existing = JSON.parse(
      window.localStorage.getItem(RAG_FAILURE_LOG_KEY) || "[]",
    );
    const next = [
      ...existing,
      { ...payload, ts: new Date().toISOString() },
    ].slice(-50);
    window.localStorage.setItem(RAG_FAILURE_LOG_KEY, JSON.stringify(next));
    learnedTypoCache = null;
  } catch (error) {
    console.warn("[SELA RAG] Gagal menyimpan log retrieval:", error);
  }
}

function setLatestRetrievalEvaluation(report) {
  setStoredJson(RAG_EVALUATION_KEY, report);
}

export function getLatestRetrievalEvaluation() {
  return getStoredJson(RAG_EVALUATION_KEY, null);
}

async function getFuse() {
  if (fuse) return fuse;
  try {
    fuse = new Fuse(ragDataset, {
      keys: [
        { name: "title", weight: 0.4 },
        { name: "keywords", weight: 0.35 },
        { name: "category", weight: 0.1 },
        { name: "content", weight: 0.15 },
      ],
      threshold: 0.65,
      ignoreLocation: true,
      includeScore: true,
    });
  } catch (e) {
    console.error("Gagal inisialisasi RAG dataset:", e);
  }
  return fuse;
}

async function resolveRetrievalState(messageHistory = [], userQuery = "") {
  const cappedHistory = messageHistory.slice(-10);
  const topicState = deriveConversationTopicState(cappedHistory);
  const queryContinuity = classifyQueryContinuity(userQuery, cappedHistory);
  const decomposedQueries = decomposeUserQuery(userQuery, topicState);
  const retrievalQuery = buildRetrievalQuery(
    cappedHistory,
    userQuery,
    topicState,
    queryContinuity,
  );
  const canonicalRewrite = buildCanonicalRewrite(userQuery, topicState);
  const f = await getFuse();
  const initialIntent = classifyCampusIntent(userQuery) || topicState.activeTopic;

  let matches = [];
  let finalMatches = [];
  let topicHints = [];
  let intent = initialIntent;
  let ragScore = 1;
  let contextStr = "";
  let mediaResults = [];
  let responsePlan = buildResponsePlan(userQuery, { intent: initialIntent });
  let conversationContextHint = "";
  let answerability = {
    level: "none",
    reason: "no_match",
    detectedTopic: topicState.activeTopic || null,
  };

  if (f && userQuery) {
    const fuseResults = f.search(retrievalQuery);
    const retrieval = retrieveCampusContext(
      retrievalQuery,
      fuseResults,
      topicState,
    );
    matches = retrieval.matches;
    topicHints = retrieval.topicHints;
    intent = retrieval.intent || initialIntent;
    responsePlan = buildResponsePlan(userQuery, { intent });
    const rawMatches =
      matches.length > 0 ? matches : getTopicFallbackMatches(intent, topicHints);
    finalMatches = prioritizeResponseMatches(rawMatches, {
      responsePlan,
      intent,
      catalog: ragDataset,
    });
    answerability = computeAnswerability(finalMatches, userQuery, topicState);
    conversationContextHint = buildConversationContextHint(
      cappedHistory,
      intent,
      queryContinuity,
    );

    if (finalMatches.length > 0) {
      ragScore =
        finalMatches[0].fuseScore ??
        Math.max(0, 1 - finalMatches[0].score / 20);
      contextStr = finalMatches
        .map(
          (r) =>
            `Topik: ${r.item.title}\nKategori: ${r.item.category}\nInfo: ${r.item.content}`,
        )
        .join("\n\n");
      mediaResults = finalMatches
        .flatMap((r) => r.item.media || [])
        .filter((m) => m?.url);
    }
  }

  return {
    cappedHistory,
    queryContinuity,
    conversationContextHint,
    topicState,
    decomposedQueries,
    retrievalQuery,
    canonicalRewrite,
    matches,
    finalMatches,
    topicHints,
    intent,
    responsePlan,
    ragScore,
    contextStr,
    mediaResults,
    answerability,
    confidenceRouting: buildConfidenceRouting(
      answerability,
      decomposedQueries,
      topicState,
    ),
    clarificationHint: buildClarificationHint(
      answerability,
      decomposedQueries,
      topicState,
    ),
  };
}

export const __debugResolveRetrievalState = resolveRetrievalState;

export async function evaluateRetrievalGoldens() {
  const cases = [];
  let passed = 0;

  for (const golden of ragGoldens) {
    const state = await resolveRetrievalState(
      [{ role: "user", content: golden.query }],
      golden.query,
    );
    const topIds = state.finalMatches.map((match) => match.item.id);
    const retrievedIntents = [
      ...new Set(
        [
          state.intent,
          state.answerability.detectedTopic,
          ...state.topicHints,
          ...state.decomposedQueries.map((part) => part.intent),
        ].filter(Boolean),
      ),
    ];
    const idHit = (golden.expected_ids || []).some((id) => topIds.includes(id));
    const intentHit = (golden.expected_intents || []).some((intentName) =>
      retrievedIntents.includes(intentName),
    );
    const ok = idHit || intentHit;

    cases.push({
      id: golden.id,
      query: golden.query,
      ok,
      answerability: state.answerability.level,
      confidence_route: state.confidenceRouting.route,
      expected_ids: golden.expected_ids || [],
      expected_intents: golden.expected_intents || [],
      top_ids: topIds.slice(0, 5),
      retrieved_intents: retrievedIntents,
    });

    if (ok) passed += 1;
  }

  const report = {
    evaluated_at: new Date().toISOString(),
    total: ragGoldens.length,
    passed,
    failed: ragGoldens.length - passed,
    pass_rate:
      ragGoldens.length > 0
        ? Number(((passed / ragGoldens.length) * 100).toFixed(1))
        : 0,
    cases,
  };

  setLatestRetrievalEvaluation(report);
  return report;
}

export function getShadowFaqReviewQueue(
  minSourceCount = SHADOW_REVIEW_MIN_SOURCE_COUNT,
) {
  const artifacts = getLearnedArtifacts();
  const approvedTopics = artifacts.shadow_faq_reviews?.approved_topics || {};
  const rejectedTopics = artifacts.shadow_faq_reviews?.rejected_topics || {};

  return (artifacts.shadow_faq_candidates || [])
    .filter((candidate) => (candidate.source_count || 0) >= minSourceCount)
    .filter(
      (candidate) =>
        !approvedTopics[candidate.suggested_topic] &&
        !rejectedTopics[candidate.suggested_topic],
    )
    .sort((a, b) => (b.source_count || 0) - (a.source_count || 0));
}

export function reviewShadowFaqCandidate(topic, action = "approve") {
  if (!topic) return null;

  const artifacts = getLearnedArtifacts();
  const candidate = (artifacts.shadow_faq_candidates || []).find(
    (item) => item.suggested_topic === topic,
  );
  if (!candidate) return null;

  const next =
    typeof structuredClone !== "undefined"
      ? structuredClone(artifacts)
      : JSON.parse(JSON.stringify(artifacts));

  next.shadow_faq_reviews = next.shadow_faq_reviews || {
    approved_topics: {},
    rejected_topics: {},
    last_reviewed_at: null,
  };

  if (action === "approve") {
    next.shadow_faq_reviews.approved_topics[topic] = {
      ...candidate,
      reviewed_at: new Date().toISOString(),
    };
    delete next.shadow_faq_reviews.rejected_topics[topic];
    next.learned_awam_aliases[topic] = mergeUniqueStrings(
      next.learned_awam_aliases[topic],
      candidate.query_forms || [],
      60,
    );
  } else {
    next.shadow_faq_reviews.rejected_topics[topic] = {
      topic,
      reviewed_at: new Date().toISOString(),
    };
    delete next.shadow_faq_reviews.approved_topics[topic];
  }

  next.shadow_faq_reviews.last_reviewed_at = new Date().toISOString();
  setLearnedArtifacts(next);
  learnedTypoCache = null;

  return next.shadow_faq_reviews;
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

// ── Enhanced Audio Quality Detection ──────────────────────────────────────
/**
 * Analisis audio untuk mendeteksi kualitas suara
 * Hitung metrik untuk membedakan ucapan manusia dari background noise
 * @param {Uint8Array} audioData - Time-domain audio samples (0-255)
 * @returns {object} Audio quality metrics
 */
function analyzeAudioQuality(audioData) {
  if (!audioData || audioData.length < 512) {
    return {
      speechScore: 0.3,
      isLikelyNoise: true,
      confidence: 0.2,
    };
  }

  // 1. RMS Energy untuk speech presence
  const rms = Math.sqrt(
    audioData.reduce((s, v) => s + (v - 128) * (v - 128), 0) / audioData.length,
  );
  const normalizedRms = Math.min(rms / 50, 1); // normalize ke 0-1

  // 2. Zero-Crossing Rate — human speech punya ZCR tertentu
  let zeroCrossingCount = 0;
  for (let i = 1; i < audioData.length; i++) {
    const crossing = (audioData[i] - 128) * (audioData[i - 1] - 128) < 0;
    if (crossing) zeroCrossingCount++;
  }
  const zcr = zeroCrossingCount / audioData.length;
  // Speech ZCR biasanya 0.04-0.15, noise bisa lebih tinggi atau lebih rendah
  const zcrScore = Math.max(0, 1 - Math.abs(zcr - 0.08) / 0.15);

  // 3. Spectral properties — gunakan Fourier untuk frequency analysis
  const frequencies = computeFrequencyDomain(audioData);
  const { spectralCentroid, voiceFrequencyRatio } =
    analyzeSpectralContent(frequencies);

  // Speech biasanya terkonsentrasi di 200-3000Hz
  // Background noise sering ada di frequencies ekstrem
  const spectralScore = voiceFrequencyRatio;

  // 4. Entropy — speech punya higher entropy dibanding pure tone/noise
  const entropy = calculateEntropy(audioData);
  const entropyScore = Math.min(entropy, 1.0) / 8; // normalize

  // 5. Dynamic Range — speech punya variety amplitude, pure tone repetitif
  const { min, max } = getAmplitudeRange(audioData);
  const dynamicRange = (max - min) / 255;
  const rangeScore = Math.min(dynamicRange * 1.5, 1);

  // Combine scores dengan weights
  const speechScore =
    normalizedRms * 0.2 +
    zcrScore * 0.2 +
    spectralScore * 0.35 +
    entropyScore * 0.15 +
    rangeScore * 0.1;

  // Deteksi likely noise
  const isLikelyNoise =
    speechScore < 0.35 ||
    (normalizedRms < 0.15 && voiceFrequencyRatio < 0.4) ||
    zcr > 0.25 ||
    zcr < 0.02; // ekstrem ZCR

  return {
    speechScore: speechScore,
    rmsLevel: normalizedRms,
    zcr: zcr,
    spectralCentroid: spectralCentroid,
    voiceFrequencyRatio: voiceFrequencyRatio,
    entropy: entropy,
    dynamicRange: dynamicRange,
    isLikelyNoise: isLikelyNoise,
    confidence: Math.max(Math.min(speechScore, 1), 0),
  };
}

/**
 * Simple FFT untuk mendapat frequency domain
 * @param {Uint8Array} timeDomain
 * @returns {array} Magnitude spectrum
 */
function computeFrequencyDomain(timeDomain) {
  const N = timeDomain.length;
  const real = new Array(N);
  const imag = new Array(N);

  for (let i = 0; i < N; i++) {
    real[i] = (timeDomain[i] - 128) / 128;
    imag[i] = 0;
  }

  // Simple Cooley-Tukey FFT
  const X = fft(real, imag);
  return X;
}
/**
 * Cooley-Tukey FFT implementation
 */
function fft(real, imag) {
  const N = real.length;
  if (N <= 1) return { real, imag };

  const mag = new Array(N);
  for (let i = 0; i < N; i++) {
    mag[i] = Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
  }
  return mag;
}
/**
 * Analisis konten spectral untuk deteksi voice frequencies
 */
function analyzeSpectralContent(frequencies) {
  const N = frequencies.length;
  if (N === 0) return { spectralCentroid: 0, voiceFrequencyRatio: 0 };

  // Hitung spectral centroid (center of mass dari frequency)
  let weightedSum = 0;
  let magnitudeSum = 0;
  for (let i = 0; i < N; i++) {
    weightedSum += i * frequencies[i];
    magnitudeSum += frequencies[i];
  }
  const spectralCentroid = magnitudeSum > 0 ? weightedSum / magnitudeSum : 0;

  // Hitung ratio energy di voice frequency range (250-3000Hz @ 16kHz sample rate)
  // Bin range: 250Hz = bin ~2, 3000Hz = bin ~24 (roughly @ 16kHz)
  const voiceBinStart = Math.floor((N * 250) / 8000); // assuming 16kHz
  const voiceBinEnd = Math.floor((N * 3000) / 8000);

  let voiceEnergy = 0;
  let totalEnergy = 0;
  for (let i = 0; i < N; i++) {
    totalEnergy += frequencies[i];
    if (i >= voiceBinStart && i <= voiceBinEnd) {
      voiceEnergy += frequencies[i];
    }
  }

  const voiceFrequencyRatio = totalEnergy > 0 ? voiceEnergy / totalEnergy : 0;
  return { spectralCentroid, voiceFrequencyRatio };
}
/**
 * Calculate Shannon entropy sebagai measure dari randomness
 */
function calculateEntropy(audioData) {
  const bins = 256;
  const hist = new Array(bins).fill(0);
  for (let i = 0; i < audioData.length; i++) {
    hist[audioData[i]]++;
  }

  const N = audioData.length;
  let entropy = 0;
  for (let i = 0; i < bins; i++) {
    if (hist[i] > 0) {
      const p = hist[i] / N;
      entropy -= p * Math.log2(p);
    }
  }
  return entropy;
}
/**
 * Get amplitude range
 */
function getAmplitudeRange(audioData) {
  let min = 255;
  let max = 0;
  for (let i = 0; i < audioData.length; i++) {
    if (audioData[i] < min) min = audioData[i];
    if (audioData[i] > max) max = audioData[i];
  }
  return { min, max };
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
 * Get AI response dengan Hybrid RAG. System prompt + konteks dibangun di sini
 * (di frontend), lalu dikirim ke backend sebagai messages array biasa.
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
  const retrievalState = await resolveRetrievalState(messageHistory, userQuery);
  const {
    topicState,
    decomposedQueries,
    queryContinuity,
    conversationContextHint,
    retrievalQuery,
    canonicalRewrite,
    matches,
    finalMatches,
    topicHints,
    intent,
    responsePlan,
    ragScore,
    contextStr,
    mediaResults,
    answerability,
    confidenceRouting,
    clarificationHint,
  } = retrievalState;

  // Auto-detect bahasa dari query user — override lang kalau deteksi yakin
  const autoLang = detectLang(userQuery);
  const effectiveLang = autoLang || lang;
  if (autoLang && autoLang !== lang) {
    console.log(`[SELA Lang] Auto-detect: "${autoLang}" (prop: "${lang}")`);
  }
  console.log("RAG Retrieval State:", {
    query: userQuery,
    retrievalQuery,
    canonicalRewrite,
    responsePlan,
    queryContinuity,
    answerability: answerability.level,
    route: confidenceRouting.route,
    transcriptMarker: preparedQuery.marker,
    intent,
    topicHints,
    topicState,
    conversationContextHint,
    matches: matches.map((r) => ({
      id: r.item.id,
      score: Number(r.score.toFixed(2)),
      fuseScore: r.fuseScore,
    })),
  });

  if (matches.length === 0 && finalMatches.length > 0) {
    console.log(
      "RAG Fallback activated with topic-based matches:",
      finalMatches.map((r) => r.item.id),
    );
  }

  if (finalMatches.length === 0) {
    console.log("RAG no relevant context found for query:", userQuery);
  }

  if (answerability.level === "none" || answerability.level === "weak") {
    logRetrievalFailure({
      userQuery,
      rawUserQuery,
      retrievalQuery,
      canonicalRewrite,
      topicState,
      decomposedQueries,
      answerability,
      confidenceRouting,
      transcriptMarker: preparedQuery.marker,
      topMatches: finalMatches.map((match) => ({
        id: match.item.id,
        title: match.item.title,
        score: Number((match.score || 0).toFixed(2)),
      })),
    });
  }

  // 2. System prompt bilingual + konteks RAG
  const today = new Date().toLocaleDateString("id-ID", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const todayEN = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const systemPromptID = `Kamu adalah SELA, wujud Customer Service virtual Universitas Catur Insan Cendekia (UCIC) yang berkarakter lembut, karismatik, berwibawa, dan memancarkan aura cerdas.
Hari ini adalah ${today}.
Gaya bicaramu tenang, hangat, elegan, dan profesional. Kamu adalah "Wajah Digital" UCIC.
Kamu boleh menggunakan partikel bahasa lisan seperti 'nih', 'sih', 'dong', atau 'ya', namun penggunaannya HARUS sangat tepat, natural secara tata bahasa, dan tidak berlebihan agar wibawamu tetap terjaga. Penempatannya harus dilihat dari kata sebelumnya apakah cocok atau tidak.
Jawabanmu HARUS singkat, ramah, dan langsung ke inti seperti customer service. Hindari pembuka panjang, promosi, dan penjelasan tambahan yang tidak ditanya. Untuk daftar, langkah, atau perbandingan, gunakan nomor pendek (1, 2, 3), bukan bullet lingkaran. Untuk fakta tunggal, jawab dalam 1 kalimat.

[TUGAS UTAMAMU]:
Kamu HANYA bertugas dan DIIZINKAN menjawab pertanyaan seputar kampus UCIC (seperti Pendaftaran, Akademik, Fasilitas, dan Informasi Kampus lainnya).

[ATURAN MENJAWAB]:
1. Jika pertanyaan BERHUBUNGAN dengan UCIC:
   - Jawab menggunakan DARI [KONTEKS KAMPUS] di bawah ini sebagai FAKTA MUTLAK.
   - Jika [KONTEKS KAMPUS] memuat informasi yang ditanyakan, WAJIB jawab berdasarkan konteks tersebut. Jangan mengatakan belum punya informasi kalau jawabannya ada di konteks.
   - Jika [KONTEKS KAMPUS] tidak kosong, kamu DILARANG menjawab "maaf belum punya informasi", "hubungi kampus", atau penolakan sejenis sebelum memakai informasi yang tersedia.
   - Riwayat chat BUKAN sumber fakta. Jika riwayat chat berbeda dengan [KONTEKS KAMPUS], abaikan riwayat chat dan ikuti [KONTEKS KAMPUS].
   - Untuk pertanyaan langsung seperti "siapa", "dimana", "berapa", "kapan", atau "apa", jawab langsung dari kalimat paling relevan di [KONTEKS KAMPUS].
   - Jangan menyalin semua konteks. Ambil hanya informasi yang menjawab pertanyaan user.
   - Jika pertanyaan user masih samar seperti "yang itu", "terus gimana", atau "berapa yang tadi", gunakan konteks percakapan terakhir dan jawab bagian yang paling mungkin dimaksud user dengan tetap hati-hati.
   - Ingatan SELA hanya berlaku dalam sesi chat aktif. Gunakan riwayat hanya untuk memahami rujukan, bukan sebagai sumber fakta dan bukan sebagai memori permanen.
   - Jika [KONTEKS PERCAKAPAN UNTUK RUJUKAN] menyebut rujukan program studi dan user bertanya "bedanya", "perbedaannya", atau "itu apa bedanya", bandingkan HANYA program studi yang dirujuk itu. Jangan melebar ke semua jurusan UCIC.
   - Jika konteks yang ada hanya menjawab sebagian, berikan jawaban parsial yang membantu. Jangan langsung menolak kalau masih ada bagian yang bisa dijawab dari konteks.
   - Jika transcript user tampak mengulang frasa yang sama, ANGGAP itu artefak suara. Jangan menegur, jangan berkomentar bahwa user mengulang, dan jangan mengatakan akan menjelaskan sekali saja. Cukup jawab inti pertanyaannya dengan normal.
   - Jika [KONTEKS KAMPUS] kosong atau benar-benar tidak memuat informasinya, tolak dengan jujur dan berwibawa: "Mohon maaf, SELA belum punya informasi sedetail itu saat ini. Mungkin Anda bisa menanyakannya langsung ke bagian informasi kampus." Jangan mengarang info.

2. Jika pertanyaan TIDAK BERHUBUNGAN dengan UCIC (Topik umum, tokoh dunia, cuaca, hiburan, politik, dll):
   - Kamu DILARANG KERAS menjawab kelanjutan dari pertanyaan tersebut (Bahkan jika kamu tahu faktanya).
   - Selalu tolak dengan elegan dan lembut khas SELA, lalu arahkan kembali pembicaraan ke UCIC.
   - Contoh penolakan elegan: "Maaf ya, ranah SELA saat ini spesifik hanya untuk membantu informasi seputar kampus UCIC. Ada hal tentang pendaftaran atau akademik yang bisa SELA bantu jelaskan?"

3. ANTI-NOISE (ABAIKAN OBROLAN ACAK):
   - Jika kalimat dari user sangat pendek, tidak memiliki makna yang jelas, atau terdengar seperti potongan obrolan orang yang sedang lewat (contoh: "eh", "iya", "halo", "oh gitu", "lagi apa", "makan yuk"), JANGAN dijawab.
   - Kamu HANYA boleh membalas dengan SATU KATA ini: [IGNORE_NOISE]
   - Jangan tambahkan teks apa pun selain [IGNORE_NOISE] jika mendeteksi obrolan acak.

[KONTEKS KAMPUS]:
${contextStr || "Kosong"}

[KONTEKS PERCAKAPAN UNTUK RUJUKAN]:
${conversationContextHint || "Tidak ada. Pertanyaan terbaru berdiri sendiri."}

[ATURAN KEDALAMAN JAWABAN]:
${buildResponsePlanPrompt(responsePlan, "id")}

[ARAH KLARIFIKASI]:
${clarificationHint || "Kosong"}

[ROUTING KEPERCAYAAN]:
${confidenceRouting.instruction}

[GAYA JAWABAN BERDASARKAN INTENT]:
${buildIntentResponseGuide(intent)}

[PERTANYAAN LANJUTAN]:
Setelah menjawab pertanyaan SEPUTAR UCIC, berikan maksimal 2 saran pertanyaan lanjutan yang pendek dan relevan.
Saran ini HARUS DITULIS DARI SUDUT PANDANG USER (seolah-olah user yang sedang bertanya), BUKAN AI yang bertanya kepada user.
Gunakan format di AKHIR jawaban: [Pertanyaan 1?] | [Pertanyaan 2?]
Contoh: "Pendaftaran dibuka bulan Maret. [Bagaimana cara mendaftar ke UCIC?] | [Apa saja syarat pendaftarannya?]"
JIKA kamu MENOLAK menjawab karena di luar topik kampus, kamu TIDAK PERLU menambahkan pertanyaan lanjutan.`;

  const systemPromptEN = `You are SELA, the virtual receptionist for Universitas Catur Insan Cendekia (UCIC) who embodies a gentle, charismatic, authoritative, and deeply intelligent persona.
Today is ${todayEN}.
Your speaking style is calm, warm, elegant, and highly professional. You are the "Digital Face" of UCIC.
Your answers MUST be concise, friendly, and direct like a customer service representative. Avoid long openings, promotion-like wording, and extra details the user did not ask for. For lists, steps, or comparisons, use short numbered lines (1, 2, 3), not bullet points. For a single fact, answer in one sentence.
You MUST ALWAYS answer the user in ENGLISH.

[YOUR MAIN TASK]:
You ONLY serve and are PERMITTED to answer questions related to the UCIC campus (such as Admissions, Academics, Facilities, and other Campus Information).

[ANSWERING RULES]:
1. If the question is RELATED to UCIC:
   - Answer using the [CAMPUS CONTEXT] below as ABSOLUTE FACT.
   - If the [CAMPUS CONTEXT] contains the requested information, you MUST answer from that context. Do not say the information is unavailable when it exists in the context.
   - If [CAMPUS CONTEXT] is not empty, you are FORBIDDEN from saying the information is unavailable, telling the user to check with campus staff, or refusing before using the available context.
   - Chat history is NOT a fact source. If chat history conflicts with [CAMPUS CONTEXT], ignore chat history and follow [CAMPUS CONTEXT].
   - For direct questions like "who", "where", "how much", "when", or "what", answer directly from the most relevant sentence in [CAMPUS CONTEXT].
   - Do not copy all context. Use only the information needed to answer the user's question.
   - If the user's wording is vague, such as "that one", "then how", or "how much for that", use the recent conversation context and answer the most likely intended topic carefully.
   - SELA's memory only applies within the active chat session. Use history only to resolve references, not as a fact source or permanent memory.
   - If [CONVERSATION CONTEXT FOR REFERENCE] names referenced study programs and the user asks for the difference, compare ONLY those referenced programs. Do not broaden the answer to all UCIC majors.
   - If the context only answers part of the request, still provide the helpful partial answer instead of declining immediately.
   - If the transcript appears to repeat the same phrase, treat that as a voice artifact. Do not scold the user, do not comment on repetition, and do not say you will explain it only once. Just answer normally.
   - If the [CAMPUS CONTEXT] is empty or truly does not contain the specific info, answer honestly and elegantly: "I apologize, but SELA does not have detailed information on that just yet. You might want to check with the campus staff." Do not make up answers.

2. If the question is NOT RELATED to UCIC (General topics, world figures, weather, entertainment, politics, etc.):
   - You are STRICTLY FORBIDDEN from answering the question.
   - Always politely decline in your gentle and authoritative style, then steer the conversation back to UCIC topics.
   - Example refusal: "I apologize, but SELA's focus is perfectly tailored to serving information regarding the UCIC campus. Is there anything about our academic programs or admissions that I can help you with?"

3. ANTI-NOISE (IGNORE RANDOM CHATTER):
   - If the user's sentence is very short, meaningless, or sounds like fragmented background chatter of passersby (e.g., "uh", "yeah", "hello", "oh really", "what's up", "let's eat"), DO NOT answer it.
   - You MUST ONLY reply with this EXACT WORD: [IGNORE_NOISE]
   - Do not add any other text besides [IGNORE_NOISE] if you detect random chatter.

[CAMPUS CONTEXT]:
${contextStr || "Empty"}

[CONVERSATION CONTEXT FOR REFERENCE]:
${conversationContextHint || "None. The latest question is standalone."}

[RESPONSE DEPTH RULE]:
${buildResponsePlanPrompt(responsePlan, "en")}

[CLARIFICATION DIRECTION]:
${clarificationHint || "Empty"}

[CONFIDENCE ROUTING]:
${confidenceRouting.instruction}

[INTENT RESPONSE STYLE]:
${buildIntentResponseGuide(intent)}

[FOLLOW-UP QUESTIONS]:
After answering a UCIC-RELATED question, add up to 2 short relevant follow-up questions at the END that the USER CAN ASK NEXT.
These suggestions MUST BE WRITTEN FROM THE USER'S PERSPECTIVE (as if the user is asking), NOT as the AI asking the user.
Use the format: [Question 1?] | [Question 2?]
Example: "Registration opens in March. [How do I apply to UCIC?] | [What are the admission requirements?]"
IF you DECLINE to answer because the topic is unrelated to the campus, DO NOT add follow-up questions.`;

  const messages = [
    {
      role: "system",
      content: effectiveLang === "en" ? systemPromptEN : systemPromptID,
    },
    {
      role: "user",
      content: userQuery,
    },
  ];

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      lang: effectiveLang,
      userQuery,
      ragScore,
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
  const { text } = await res.json();

  // Cek IGNORE_NOISE sebelum parsing, agar tidak muncul sebagai suggestion
  if (text?.trim().includes("[IGNORE_NOISE]")) {
    return {
      text: "[IGNORE_NOISE]",
      suggestions: [],
      media: [],
      detectedLang: effectiveLang,
    };
  }

  // Parse follow-up suggestions from response
  const { text: cleanText, suggestions } = parseSuggestions(text || "");
  const datasetFallbackAnswer = buildDatasetAnswerFromMatches(
    finalMatches,
    effectiveLang,
    responsePlan,
  );
  const shouldUseDatasetFallback =
    datasetFallbackAnswer &&
    finalMatches.length > 0 &&
    looksLikeUnavailableAnswer(cleanText);
  const displayText =
    (shouldUseDatasetFallback ? datasetFallbackAnswer : cleanText) ||
    "Maaf, SELA agak bingung. Bisa diulang?";
  const spokenText = buildSpokenText(
    displayText,
    responsePlan,
    effectiveLang,
    finalMatches,
  );

  return {
    text: displayText,
    spokenText,
    suggestions: shouldUseDatasetFallback ? [] : suggestions,
    media: mediaResults,
    detectedLang: effectiveLang,
  };
}

// ── Text-to-Speech ───────────────────────────────────────────────────────────

// ── Text-to-Speech & Voice Cloning Offline ──────────────────────────────────

// Variabel referensi pemutar audio aktif untuk interupsi instan (barge-in)
let pemutarAudioAktif = null;

/**
 * Menghentikan seluruh pemutaran suara yang sedang berjalan (Audio Cloned & Web Speech)
 */
export function stopSpeaking() {
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
 * Fungsi cadangan menggunakan Web Speech API bawaan browser jika server offline
 */
function jalankanFallbackWebSpeech(teks, onStart, onEnd, lang = "id") {
  if (!("speechSynthesis" in window)) {
    if (onEnd) onEnd();
    return;
  }

  window.speechSynthesis.cancel();

  const doSpeak = () => {
    const utterance = new SpeechSynthesisUtterance(teks);
    let settled = false;
    utterance.lang = lang === "en" ? "en-US" : "id-ID";
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    const finalize = () => {
      if (settled) return;
      settled = true;
      if (onEnd) onEnd();
    };

    utterance.onstart = () => {
      if (onStart) onStart();
    };
    utterance.onend = () => {
      finalize();
    };
    utterance.onerror = (e) => {
      if (e?.error !== "interrupted") {
        console.warn("[SELA SpeechSynthesis]", e?.error);
      }
      finalize();
    };

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      const targetedLang = lang === "en" ? "en" : "id";
      const available = voices.filter((v) => v.lang.includes(targetedLang));
      if (available.length > 0) {
        utterance.voice =
          available.find((v) => v.name.toLowerCase().includes("female")) ||
          available[0];
      }
    }

    window.speechSynthesis.speak(utterance);
  };

  if (window.speechSynthesis.getVoices().length > 0) {
    setTimeout(doSpeak, 60);
  } else {
    window.speechSynthesis.onvoiceschanged = () => setTimeout(doSpeak, 60);
  }
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

  if (!text || !text.trim()) {
    if (onEnd) onEnd();
    return;
  }

  // 1. Prioritaskan sintesis audio kloning dari server AI lokal
  try {
    const respons = await fetch("/api/sintesis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teks_kalimat: text, bahasa: lang }),
    });

    if (respons.ok) {
      const dataSintesis = await respons.json();
      if (dataSintesis.audio_base64) {
        console.log(`[SELA TTS] Memainkan suara hasil sintesis kloning (${dataSintesis.engine || 'voice-cloned'})`);
        const tipeFormat = dataSintesis.format || "audio/mpeg";
        const audio = new Audio(`data:${tipeFormat};base64,${dataSintesis.audio_base64}`);
        pemutarAudioAktif = audio;

        audio.onplay = () => {
          if (onStart) onStart();
        };

        audio.onended = () => {
          pemutarAudioAktif = null;
          if (onEnd) onEnd();
        };

        audio.onerror = (galatAudio) => {
          console.warn("[SELA TTS] Kendala pemutaran audio kloning, beralih ke cadangan Web Speech:", galatAudio);
          pemutarAudioAktif = null;
          jalankanFallbackWebSpeech(text, onStart, onEnd, lang);
        };

        await audio.play();
        return;
      }
    }
  } catch (galatKoneksi) {
    console.warn("[SELA TTS] Endpoint sintesis backend tidak merespons:", galatKoneksi?.message);
  }

  // 2. Gunakan cadangan Web Speech jika backend belum siap
  jalankanFallbackWebSpeech(text, onStart, onEnd, lang);
}

// ── Time-based Greeting ──────────────────────────────────────────────────────

/**
 * Get greeting based on current time of day
 * @param {string} lang - 'id' | 'en'
 * @returns {string} - Time-appropriate greeting
 */
export function getTimeBasedGreeting(lang = "id") {
  const hour = new Date().getHours();
  let period;

  if (hour >= 5 && hour < 11) period = "morning";
  else if (hour >= 11 && hour < 15) period = "afternoon";
  else if (hour >= 15 && hour < 19) period = "evening";
  else period = "night";

  const greetings = {
    id: {
      morning:
        "Selamat pagi. SELA siap membantu melayani Anda hari ini. Ada informasi kampus yang bisa dibantu?",
      afternoon:
        "Selamat siang. Mari, ada informasi seputar UCIC yang bisa SELA pandu untuk Anda?",
      evening:
        "Selamat sore. SELA siap membantu menjawab pertanyaan Anda terkait kampus tercinta ini.",
      night:
        "Selamat malam. Ada informasi pendaftaran atau akademik yang ingin Anda ketahui dari SELA?",
    },
    en: {
      morning:
        "Good morning. SELA is ready to assist you today. How may I help?",
      afternoon:
        "Good afternoon. Is there any campus information I can guide you through?",
      evening:
        "Good evening. SELA is here to kindly assist with your questions about UCIC.",
      night:
        "Good night. Is there anything regarding academics or admissions you would like to know?",
    },
  };

  return greetings[lang]?.[period] || greetings[lang].afternoon;
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
