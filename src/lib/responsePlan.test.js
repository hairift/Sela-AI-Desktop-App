import test from "node:test";
import assert from "node:assert/strict";

import {
  buildResponsePlan,
  buildSpokenText,
  prioritizeResponseMatches,
} from "./responsePlan.js";

test("buildResponsePlan classifies detail modes from representative queries", () => {
  assert.equal(
    buildResponsePlan("ucic ada jurusan apa aja", { intent: "jurusan" })
      .displayMode,
    "list_detail",
  );
  assert.equal(
    buildResponsePlan("syarat daftar kuliah apa aja", { intent: "syarat" })
      .displayMode,
    "step_detail",
  );
  assert.equal(
    buildResponsePlan("cara daftar di ucic gimana", { intent: "pendaftaran" })
      .displayMode,
    "step_detail",
  );
  assert.equal(
    buildResponsePlan("siapa rektor ucic", { intent: "rektor" }).displayMode,
    "brief",
  );
  assert.equal(
    buildResponsePlan("alamat kampus dimana", { intent: "lokasi" }).displayMode,
    "brief",
  );
  assert.equal(
    buildResponsePlan("beda TI dan SI apa", { intent: "jurusan" }).displayMode,
    "compare_detail",
  );
});

test("buildResponsePlan marks enumerate-all and summary-only voice modes", () => {
  const plan = buildResponsePlan("sebutkan semua jurusan di UCIC", {
    intent: "jurusan",
  });

  assert.equal(plan.mustEnumerateAll, true);
  assert.equal(plan.ttsMode, "adaptive");
  assert.equal(plan.maxContextItems, 6);
});

test("prioritizeResponseMatches pins aggregate jurusan entries first", () => {
  const plan = buildResponsePlan("ucic ada jurusan apa aja", {
    intent: "jurusan",
  });
  const catalog = [
    { id: "jurusan_ucic", title: "Fakultas dan Program Studi UCIC" },
    { id: "jurusan_fti", title: "FTI" },
    { id: "jurusan_feb", title: "FEB" },
    { id: "jurusan_fps", title: "FPS" },
  ];
  const ranked = [
    { item: catalog[1], score: 17 },
    { item: catalog[2], score: 16 },
    { item: catalog[3], score: 15 },
  ];

  const prioritized = prioritizeResponseMatches(ranked, {
    responsePlan: plan,
    intent: "jurusan",
    catalog,
  });

  assert.deepEqual(
    prioritized.slice(0, 4).map((entry) => entry.item.id),
    ["jurusan_ucic", "jurusan_fti", "jurusan_feb", "jurusan_fps"],
  );
});

test("buildSpokenText reads the full answer, not a fixed template", () => {
  const plan = buildResponsePlan("ucic ada jurusan apa aja", {
    intent: "jurusan",
  });
  const matches = [
    {
      item: {
        id: "jurusan_ucic",
        title: "Fakultas dan Program Studi UCIC",
        content:
          "UCIC memiliki 3 fakultas:\n- Fakultas Teknologi Informasi (FTI): S1 Teknik Informatika, S1 Sistem Informasi, S1 Desain Komunikasi Visual, D3 Manajemen Informatika, D3 Komputerisasi Akuntansi.\n- Fakultas Ekonomi dan Bisnis (FEB): S1 Akuntansi, S1 Manajemen, S1 Bisnis Digital, D3 Manajemen Bisnis.\n- Fakultas Pendidikan dan Sains (FPS): S1 Pendidikan Kepelatihan Olahraga.",
      },
    },
  ];

  const longAnswer = `UCIC memiliki 3 fakultas dengan program studi yang cukup beragam untuk calon mahasiswa.

Fakultas Teknologi Informasi mencakup beberapa pilihan yang fokus pada komputer, sistem, dan desain.

Fakultas Ekonomi dan Bisnis mencakup pilihan yang berhubungan dengan bisnis, akuntansi, dan manajemen.

Fakultas Pendidikan dan Sains memiliki pilihan program studi di bidang olahraga.

Daftar lengkap setiap program studi saya tampilkan di layar agar lebih mudah dibaca.`;

  const spoken = buildSpokenText(longAnswer, plan, "id", matches);

  // Seluruh paragraf jawaban harus ikut dibacakan, bukan hanya 2 kalimat awal.
  assert.match(spoken, /UCIC memiliki 3 fakultas/i);
  assert.match(spoken, /Fakultas Teknologi Informasi mencakup/i);
  assert.match(spoken, /Fakultas Ekonomi dan Bisnis mencakup/i);
  assert.match(spoken, /Fakultas Pendidikan dan Sains memiliki/i);
  assert.match(spoken, /tampilkan di layar/i);
});

test("buildSpokenText keeps every item of a detailed list", () => {
  const plan = buildResponsePlan("kalau saya suka komputer masuk jurusan apa ya", {
    intent: "jurusan",
  });
  const shortAnswer = `Jika Anda suka komputer, maka jurusan yang cocok untuk Anda di UCIC adalah:

Teknik Informatika: jurusan ini fokus pada pemrograman dan pengembangan perangkat lunak.
Sistem Informasi: jurusan ini fokus pada pengelolaan sistem informasi dan aplikasi.`;

  const spoken = buildSpokenText(shortAnswer, plan, "id", []);

  assert.match(spoken, /Jika Anda suka komputer/i);
  assert.match(spoken, /Teknik Informatika/i);
  // Uraian tiap item tidak boleh lagi dipotong.
  assert.match(spoken, /pengelolaan sistem informasi dan aplikasi/i);
});

test("buildSpokenText speaks multi-paragraph answers in full", () => {
  const plan = buildResponsePlan("kalau saya suka komputer masuk jurusan apa ya", {
    intent: "jurusan",
  });
  const detailedAnswer = `Jika Anda suka komputer, maka jurusan yang paling cocok di UCIC adalah Teknik Informatika atau Sistem Informasi.

Teknik Informatika lebih cocok jika Anda suka pemrograman, software, dan pengembangan teknologi.

Sistem Informasi lebih cocok jika Anda suka kombinasi komputer, data, dan proses bisnis.`;

  const spoken = buildSpokenText(detailedAnswer, plan, "id", []);

  // Semua paragraf digabung apa adanya — tidak ada yang dibuang.
  assert.equal(
    spoken,
    "Jika Anda suka komputer, maka jurusan yang paling cocok di UCIC adalah Teknik Informatika atau Sistem Informasi. Teknik Informatika lebih cocok jika Anda suka pemrograman, software, dan pengembangan teknologi. Sistem Informasi lebih cocok jika Anda suka kombinasi komputer, data, dan proses bisnis.",
  );
});

test("buildSpokenText does not truncate long answers at the old 260-char cap", () => {
  // Regresi: dulu TTS berhenti setelah 2 kalimat / 260 karakter. Kalimat dibuat
  // berbeda-beda agar tidak dibuang oleh de-duplikasi.
  const sentences = Array.from(
    { length: 12 },
    (_, i) => `Kalimat nomor ${i + 1} berisi keterangan tambahan yang panjang.`,
  );
  const longAnswer = `${sentences.join(" ")} Kalimat terakhir yang wajib ikut terdengar sampai habis.`;

  const spoken = buildSpokenText(longAnswer, null, "id", []);

  assert.ok(spoken.length > 260, `spoken length ${spoken.length} harus > 260`);
  assert.match(spoken, /Kalimat nomor 1 berisi/i);
  assert.match(spoken, /Kalimat nomor 12 berisi/i);
  assert.match(spoken, /Kalimat terakhir yang wajib ikut terdengar sampai habis\.$/);
});

test("buildSpokenText replaces raw URLs with a natural spoken cue", () => {
  const spoken = buildSpokenText(
    "Daftar melalui https://pmb.example.test/daftar untuk melanjutkan proses.",
    buildResponsePlan("cara daftar", { intent: "pendaftaran" }),
    "id",
  );

  assert.match(spoken, /Linknya bisa kamu akses di sini/i);
  assert.doesNotMatch(spoken, /https?:\/\//i);
});

test("buildSpokenText strips list markers so TTS never reads dashes or numbers", () => {
  // UI kini boleh menampilkan daftar bullet/bernomor (agar mudah dibaca),
  // tetapi mesin suara tidak boleh mengucapkan penanda "- " atau "1. ".
  const answer = `Ada dua paket biaya kuliah.

- Early Bird standar mulai dua juta delapan ratus ribu rupiah.
- Early Bird diskon lima puluh lima persen sekitar empat juta rupiah.

Langkah pendaftarannya:
1. Isi formulir pendaftaran secara online.
2. Bayar biaya pendaftaran dua ratus lima puluh ribu rupiah.`;

  const spoken = buildSpokenText(answer, null, "id", []);

  // Penanda daftar tidak boleh tersisa dalam teks yang diucapkan.
  assert.doesNotMatch(spoken, /(^|\s)[-*]\s/);
  assert.doesNotMatch(spoken, /\b\d+[.)]\s/);

  // Namun seluruh isi setiap poin tetap dibacakan.
  assert.match(spoken, /Early Bird standar mulai dua juta delapan ratus ribu rupiah/i);
  assert.match(spoken, /Early Bird diskon lima puluh lima persen sekitar empat juta rupiah/i);
  assert.match(spoken, /Isi formulir pendaftaran secara online/i);
  assert.match(spoken, /Bayar biaya pendaftaran dua ratus lima puluh ribu rupiah/i);
});

test("buildSpokenText speaks follow-up suggestions without brackets or pipe", () => {
  // Backend menulis saran lanjutan sebagai "[Pertanyaan?] | [Pertanyaan?]".
  // Tanda kurung siku dan pipa tidak boleh ikut diucapkan mesin suara.
  const answer =
    "Pendaftaran UCIC dibuka bulan Maret. " +
    "[Bagaimana cara mendaftar ke UCIC?] | [Apa saja syarat pendaftarannya?]";

  const spoken = buildSpokenText(answer, null, "id", []);

  assert.ok(!spoken.includes("["), "kurung siku buka tidak boleh diucapkan");
  assert.ok(!spoken.includes("]"), "kurung siku tutup tidak boleh diucapkan");
  assert.ok(!spoken.includes("|"), "pemisah pipa tidak boleh diucapkan");

  // Namun pertanyaan saran tetap dibacakan.
  assert.match(spoken, /Bagaimana cara mendaftar ke UCIC\?/);
  assert.match(spoken, /Apa saja syarat pendaftarannya\?/);
});
