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

test("buildSpokenText speaks the answer's actual core rather than a fixed template", () => {
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

  assert.match(spoken, /UCIC memiliki 3 fakultas/i);
  assert.doesNotMatch(spoken, /tampilkan di layar/i);
});

test("buildSpokenText preserves a useful spoken summary for detailed lists", () => {
  const plan = buildResponsePlan("kalau saya suka komputer masuk jurusan apa ya", {
    intent: "jurusan",
  });
  const shortAnswer = `Jika Anda suka komputer, maka jurusan yang cocok untuk Anda di UCIC adalah:

Teknik Informatika: jurusan ini fokus pada pemrograman dan pengembangan perangkat lunak.
Sistem Informasi: jurusan ini fokus pada pengelolaan sistem informasi dan aplikasi.`;

  const spoken = buildSpokenText(shortAnswer, plan, "id", []);

  assert.match(spoken, /Teknik Informatika/i);
  assert.match(spoken, /Jika Anda suka komputer/i);
  assert.doesNotMatch(spoken, /pengelolaan sistem informasi dan aplikasi/i);
});

test("buildSpokenText summarizes multi-paragraph answers without on-screen filler", () => {
  const plan = buildResponsePlan("kalau saya suka komputer masuk jurusan apa ya", {
    intent: "jurusan",
  });
  const detailedAnswer = `Jika Anda suka komputer, maka jurusan yang paling cocok di UCIC adalah Teknik Informatika atau Sistem Informasi.

Teknik Informatika lebih cocok jika Anda suka pemrograman, software, dan pengembangan teknologi.

Sistem Informasi lebih cocok jika Anda suka kombinasi komputer, data, dan proses bisnis.`;

  const spoken = buildSpokenText(detailedAnswer, plan, "id", []);

  assert.notEqual(spoken, detailedAnswer);
  assert.doesNotMatch(spoken, /layar/i);
  assert.match(spoken, /Teknik Informatika atau Sistem Informasi/i);
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
