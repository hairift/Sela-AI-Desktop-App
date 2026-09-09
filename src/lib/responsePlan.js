const LIST_DETAIL_TOPICS = new Set([
  "jurusan",
  "beasiswa",
  "fasilitas",
  "biaya",
  "pembayaran",
]);

const BRIEF_INTENTS = new Set(["profil", "rektor", "lokasi", "kontak"]);

const AGGREGATE_PRIORITY_IDS = {
  profil: ["profil_ucic"],
  jurusan: ["jurusan_ucic", "jurusan_fti", "jurusan_feb", "jurusan_fps"],
  beasiswa: ["beasiswa"],
  fasilitas: ["fasilitas_kampus_lengkap"],
  biaya: ["biaya_kuliah"],
  lokasi: ["lokasi_kampus"],
  kontak: ["pmb_alur_kontak", "faq_awam_kontak_admin"],
  rektor: ["rektor"],
};

function normalizePlanText(text = "") {
  return String(text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function includesAny(normalized, phrases = []) {
  return phrases.some((phrase) => normalized.includes(phrase));
}

function truncateSentence(text = "", maxLength = 160) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  if (normalized.length <= maxLength) return normalized;

  const clipped = normalized.slice(0, maxLength);
  const sentenceEnd = Math.max(
    clipped.lastIndexOf("."),
    clipped.lastIndexOf("?"),
    clipped.lastIndexOf("!"),
  );
  if (sentenceEnd > 80) return clipped.slice(0, sentenceEnd + 1).trim();
  return `${clipped.replace(/\s+\S*$/, "").trim()}.`;
}

function countReadableParagraphs(text = "") {
  return String(text || "")
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean).length;
}

function extractLeadSentence(text = "", maxLength = 150) {
  let flattened = String(text || "")
    .replace(/^Baik,\s*berikut\s*informasi\s*resmi\s*dari\s*Universitas\s*Catur\s*Insan\s*Cendekia\s*\(UCIC\):\s*/i, "")
    .replace(/\[(.*?)\]/g, " ")
    .replace(/(?:^|\n)\s*\d+\.\s*/g, " ")
    .replace(/(?:^|\n)\s*-\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!flattened) return "";
  const firstSentence = flattened.match(/^.*?[.!?](?=\s|$)/)?.[0] || flattened;
  return truncateSentence(firstSentence, maxLength);
}

function extractJurusanCounts(matches = []) {
  const facultyNames = new Set();
  const programNames = new Set();

  for (const match of matches) {
    const item = match?.item || match;
    if (!item?.content) continue;

    const eligible =
      String(item.id || "").startsWith("jurusan_") ||
      /fakultas/i.test(String(item.title || ""));
    if (!eligible) continue;

    const lines = String(item.content)
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    for (const line of lines) {
      const clean = line.replace(/^-+\s*/, "").trim();

      if (/^Fakultas /i.test(clean)) {
        facultyNames.add(clean.split(":")[0].trim());
      }

      if (clean.includes(":")) {
        const afterColon = clean.split(":").slice(1).join(":");
        afterColon
          .split(",")
          .map((segment) =>
            segment
              .replace(/^(Program )?(S1|D3|S2)\s+/i, "")
              .replace(/[.]+$/g, "")
              .trim(),
          )
          .filter(Boolean)
          .forEach((program) => programNames.add(program));
        continue;
      }

      if (/^-\s*/.test(line)) {
        const program = clean.replace(/[.]+$/g, "").trim();
        if (
          program &&
          !/^Program /i.test(program) &&
          !/ fokus /i.test(program) &&
          !/^Fakultas /i.test(program)
        ) {
          programNames.add(program);
        }
      }
    }
  }

  return {
    facultyCount: facultyNames.size,
    programCount: programNames.size,
  };
}

function buildGenericSummary(intent, displayMode, lang) {
  const labels = {
    id: {
      jurusan: "daftar jurusan",
      beasiswa: "daftar beasiswa",
      fasilitas: "daftar fasilitas",
      biaya: "rincian biaya",
      pembayaran: "rincian pembayaran",
      pendaftaran: "langkah pendaftaran",
      syarat: "syarat lengkap",
      akademik: "langkah akademik",
      defaultList: "daftar lengkap",
      defaultSteps: "langkah lengkap",
      defaultCompare: "perbandingan ringkas",
    },
    en: {
      jurusan: "the full program list",
      beasiswa: "the full scholarship list",
      fasilitas: "the full facilities list",
      biaya: "the cost details",
      pembayaran: "the payment details",
      pendaftaran: "the registration steps",
      syarat: "the full requirements",
      akademik: "the academic steps",
      defaultList: "the full list",
      defaultSteps: "the full steps",
      defaultCompare: "the comparison summary",
    },
  };

  const copy = labels[lang] || labels.id;

  if (displayMode === "list_detail") {
    const noun = copy[intent] || copy.defaultList;
    return lang === "en"
      ? `I am showing ${noun} on screen so it is easier to review.`
      : `${noun.charAt(0).toUpperCase() + noun.slice(1)} saya tampilkan di layar supaya lebih mudah dilihat.`;
  }

  if (displayMode === "step_detail") {
    const noun = copy[intent] || copy.defaultSteps;
    return lang === "en"
      ? `I am showing ${noun} on screen.`
      : `${noun.charAt(0).toUpperCase() + noun.slice(1)} saya tampilkan di layar.`;
  }

  return lang === "en"
    ? `I am showing ${copy.defaultCompare} on screen.`
    : `${copy.defaultCompare.charAt(0).toUpperCase() + copy.defaultCompare.slice(1)} saya tampilkan di layar.`;
}

export function buildResponsePlan(userQuery = "", { intent = null } = {}) {
  const normalized = normalizePlanText(userQuery);
  const hasEnumerationRequest =
    includesAny(normalized, [
      "apa aja",
      "apa saja",
      "semua",
      "seluruh",
      "sebutkan",
      "rincikan",
      "list",
    ]) ||
    /\bdaftar (jurusan|prodi|fakultas|beasiswa|fasilitas|metode|pembayaran)\b/.test(
      normalized,
    );

  const hasCompareRequest =
    includesAny(normalized, [
      "beda",
      "bedanya",
      "perbedaan",
      "bandingkan",
      "vs",
      "mana yang cocok",
      "pilih mana",
      "lebih cocok",
    ]) || /cocok.*(jurusan|prodi)|(?:jurusan|prodi).*cocok/.test(normalized);

  const hasStepRequest =
    includesAny(normalized, [
      "cara",
      "alur",
      "langkah",
      "proses",
      "tahapan",
      "syarat",
      "persyaratan",
    ]) ||
    ((intent === "pendaftaran" || intent === "akademik") &&
      includesAny(normalized, ["gimana", "bagaimana"]));

  const specificCostFact =
    includesAny(normalized, ["biaya pendaftaran", "uang daftar"]) &&
    !hasEnumerationRequest;
  const directFactQuestion =
    /^(siapa|where|who|alamat|dimana|di mana|nomor|kontak|jam)\b/.test(
      normalized,
    ) || specificCostFact;

  const hasListTopicSignal =
    includesAny(normalized, [
      "jurusan",
      "prodi",
      "fakultas",
      "beasiswa",
      "fasilitas",
      "metode pembayaran",
      "pembayaran",
    ]) &&
    (hasEnumerationRequest ||
      includesAny(normalized, ["ada", "tersedia", "pilihan", "apa"]));

  let displayMode = "brief";
  if (hasCompareRequest) {
    displayMode = "compare_detail";
  } else if (hasStepRequest || intent === "syarat") {
    displayMode = "step_detail";
  } else if (
    hasListTopicSignal ||
    (LIST_DETAIL_TOPICS.has(intent) &&
      !directFactQuestion &&
      includesAny(normalized, ["ada", "apa", "pilihan", "tersedia", "metode"]))
  ) {
    displayMode = "list_detail";
  } else if (!directFactQuestion && BRIEF_INTENTS.has(intent) === false) {
    if (
      intent === "pendaftaran" &&
      includesAny(normalized, ["gimana", "bagaimana"])
    ) {
      displayMode = "step_detail";
    }
  }

  const mustEnumerateAll = displayMode === "list_detail" && hasEnumerationRequest;

  return {
    displayMode,
    ttsMode: displayMode === "brief" ? "full" : "adaptive",
    mustEnumerateAll,
    maxContextItems: displayMode === "brief" ? 3 : 6,
    intent,
  };
}

export function buildResponsePlanPrompt(responsePlan, lang = "id") {
  const plan = responsePlan || buildResponsePlan();

  if (lang === "en") {
    switch (plan.displayMode) {
      case "list_detail":
        return `Depth mode: concise numbered list. Use short numbered lines (1, 2, 3). No long intro, no extra explanation.${plan.mustEnumerateAll ? " Enumerate every relevant item, but keep each item short." : " Include only the most relevant items."}`;
      case "step_detail":
        return "Depth mode: concise steps. Use short numbered lines. Mention only the core steps or requirements.";
      case "compare_detail":
        return "Depth mode: concise comparison. Use short numbered lines (1, 2, 3) for the main differences only.";
      default:
        return "Depth mode: brief. Answer directly in 1 or 2 short sentences, focusing only on the fact the user asked for.";
    }
  }

  switch (plan.displayMode) {
    case "list_detail":
      return `Mode jawaban: daftar bernomor singkat. Jawab langsung dengan nomor pendek (1, 2, 3). Jangan pakai bullet lingkaran, pembuka panjang, atau penjelasan yang tidak ditanya.${plan.mustEnumerateAll ? " Sebutkan semua item relevan, tetapi tiap item tetap pendek." : " Cukup item yang paling relevan."}`;
    case "step_detail":
      return "Mode jawaban: langkah singkat. Gunakan nomor pendek. Sebutkan inti langkah, syarat, atau alurnya saja.";
    case "compare_detail":
      return "Mode jawaban: perbandingan singkat. Gunakan nomor pendek (1, 2, 3) untuk perbedaan utama saja.";
    default:
      return "Mode jawaban: singkat. Jawab langsung ke inti dalam 1 atau 2 kalimat pendek tanpa pengantar bertele-tele.";
  }
}

export function prioritizeResponseMatches(
  matches = [],
  { responsePlan = null, intent = null, catalog = [] } = {},
) {
  const plan = responsePlan || buildResponsePlan();
  const limit = plan.maxContextItems || 4;
  const preferredIds =
    AGGREGATE_PRIORITY_IDS[intent] &&
    (plan.displayMode === "list_detail" || plan.displayMode === "brief")
      ? AGGREGATE_PRIORITY_IDS[intent]
      : [];

  if (preferredIds.length === 0) return matches.slice(0, limit);

  const existingById = new Map(
    matches
      .filter((match) => match?.item?.id)
      .map((match) => [match.item.id, match]),
  );
  const injected = [];
  const baseScore = matches[0]?.score || 20;

  preferredIds.forEach((id, index) => {
    if (existingById.has(id)) return;
    const item = catalog.find((entry) => entry.id === id);
    if (!item) return;

    injected.push({
      item,
      score: baseScore - index * 0.1,
      injected: true,
    });
  });

  const orderedPreferred = preferredIds
    .map(
      (id) =>
        existingById.get(id) ||
        injected.find((candidate) => candidate.item?.id === id),
    )
    .filter(Boolean);

  const preferredSet = new Set(preferredIds);
  const remaining = [...matches, ...injected]
    .filter((match) => !preferredSet.has(match?.item?.id))
    .sort((a, b) => (b.score || 0) - (a.score || 0));

  const ordered = [];
  const seen = new Set();

  for (const match of [...orderedPreferred, ...remaining]) {
    const id = match?.item?.id;
    if (!id || seen.has(id)) continue;
    ordered.push(match);
    seen.add(id);
    if (ordered.length >= limit) break;
  }

  return ordered;
}

export function buildSpokenText(
  displayText = "",
  responsePlan = null,
  lang = "id",
  matches = [],
) {
  const plan = responsePlan || buildResponsePlan();
  const cleanedText = String(displayText || "").trim();
  if (!cleanedText) return "";

  // Audio harus tetap berasal dari jawaban yang tampil, bukan template per
  // intent. Ambil inti 2--3 gagasan sehingga terdengar natural, informatif,
  // dan tidak membacakan URL/markdown secara harfiah.
  const withoutLinks = cleanedText
    .replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/gi, "$1. Linknya bisa kamu akses di sini.")
    .replace(/https?:\/\/\S+/gi, "Linknya bisa kamu akses di sini.")
    .replace(/[*_`#>]/g, "");
  const units = withoutLinks
    .split(/\n+|(?<=[.!?])\s+/)
    .map((unit) => unit.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const selected = [];
  const seen = new Set();
  for (const unit of units) {
    const key = normalizePlanText(unit);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    // Untuk daftar, nama item lebih enak didengar daripada uraian panjang
    // setiap item. Kalimat pembuka tetap dipertahankan sebagai konteks.
    const spokenUnit =
      plan.displayMode === "list_detail" && unit.includes(":")
        ? `${unit.split(":")[0].trim()}.`
        : unit;
    selected.push(spokenUnit);
    if (selected.length >= (plan.displayMode === "brief" ? 2 : 2)) break;
  }

  let spoken = selected.join(" ") || extractLeadSentence(withoutLinks, 320);
  // Batas moderat menjaga OmniVoice CPU responsif tanpa mengorbankan inti.
  if (spoken.length > 260) spoken = truncateSentence(spoken, 260);
  return spoken;
}
