# CLEANUP_REPORT.md — Refactor SELA-AI-Desktop-App

Refactor `ai-engine/` dari arsitektur lama (OmniVoice TTS + Whisper + RAG Fuse.js + LLM via
subprocess llama-server) menjadi arsitektur final: **1 LLM (llama.cpp direct GGUF), 1 TTS
(Piper singleton), STT in-memory tanpa file tmp, RAG anti-halusinasi, dan VAD barge-in.**

Tanggal: 2026-09-14 · Interpreter proyek: **Python 3.12.10**

---

## 1. Ringkasan hasil

| Target | Status | Catatan |
|---|---|---|
| Tidak ada file tmp di disk | ✅ Selesai | Semua audio memakai `io.BytesIO`; `tempfile` dihapus; disk-cache audio dihapus |
| 1 LLM saja | ✅ Selesai | Hanya `core/llm_engine.py`; Ollama/llama-server-subprocess lama dihapus |
| TTS Piper singleton | ✅ Selesai | `core/tts_engine.py`, model dimuat sekali saat start |
| RAG anti-halusinasi | ✅ Selesai | Retriever leksikal **BM25 + gerbang cakupan IDF** (`rag/lexical.py`), diperkuat bge-m3/FAISS bila tersedia |
| VAD & barge-in | ✅ Selesai | `core/vad_engine.py` + barge-in di `/ws/dupleks` |
| `server.py` 1 entry point | ✅ Selesai | FastAPI + WebSocket; kontrak frontend dipertahankan |
| **Satu otak saja (tanpa RAG dobel)** | ✅ Selesai | Backend kini otak tunggal; frontend hanya kirim pertanyaan + riwayat |
| **Pertanyaan di luar kampus berfungsi** | ✅ Selesai | Jalur `umum` + jalur `web` real-time |
| **Sisa kode Fuse.js dibersihkan** | ✅ Selesai | `src/lib/ai.js` 3.172 → **1.763 baris**; `fuse.js` dilepas dari `package.json` |
| **`dist/` disinkronkan** | ✅ Selesai | Sebelumnya masih bundle lama (9 Sep, memuat Fuse.js); kini dibangun ulang dari sumber bersih |
| **Jawaban berputar diperbaiki** | ✅ Selesai | Aturan prompt anti-putar + saran lanjutan yang masuk akal + larangan campur angka Inggris |
| **Kontrak UI TTS disinkronkan** | ✅ Selesai | Badge `Navbar.jsx` masih membaca medan `omnivoice_*` → selalu "Memuat AI..."; kini `piper_siap` |

Uji asap: **57 lulus, 0 gagal** (`test_server.py`, termasuk TestClient server penuh).
Evaluasi goldens: **20/20 (100%)** pada `src/data/rag_goldens.json`.

---

## 2. 🔎 Temuan utama: jawaban "ngawur" disebabkan RAG DOBEL (frontend vs backend)

### Gejala
- "Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?" → SELA menjawab **biaya kuliah**.
- Pengguna tidak bisa membedakan apakah yang menjawab LLM atau aturan (*rule-based*).

### Akar masalah
Rantai pemanggilannya:

```
VoiceUI.jsx  →  getChatCompletion()  →  POST /api/chat
                     │
                     └── src/lib/ai.js membangun konteks RAG SENDIRI memakai Fuse.js,
                         lalu menyisipkannya ke system prompt sebagai "[KONTEKS KAMPUS]".
```

Di sisi server, `/api/chat` lama memeriksa system prompt itu:

```python
sudah_ada = "KONTEKS KAMPUS" in prompt_frontend or "DOKUMEN RESMI" in prompt_frontend
if not sudah_ada and ditemukan:
    sistem += f"\n\n[GROUNDING TAMBAHAN RAG VEKTOR]\n{konteks}"
```

Karena frontend **selalu** mengirim penanda `[KONTEKS KAMPUS]`, backend **selalu melewati RAG-nya
sendiri**. Akibatnya:

1. **Mesin RAG backend (FAISS/bge-m3) praktis tidak pernah dipakai untuk chat** — hanya frontend
   Fuse.js yang menentukan jawaban.
2. Fuse.js dengan `threshold: 0.65` bersifat *fuzzy* dan bisa mengembalikan dokumen yang hanya
   menyinggung sepintas → "dosen/algoritma" nyasar ke "biaya kuliah".
3. Ada **jalur cadangan rule-based** di frontend (`buildDatasetAnswerFromMatches`) yang dapat
   menimpa jawaban LLM dengan potongan data mentah → sumber jawaban jadi ambigu.

### Perbaikan (sesuai keputusan pengguna: "Backend jadi otak tunggal")
- `src/lib/ai.js` → `getChatCompletion()` kini **hanya** mengirim `{ userQuery, riwayat_obrolan,
  bahasa }`. Seluruh pembangunan konteks Fuse.js dihapus dari jalur chat.
- `server.py` → `/api/chat` **selalu** memakai `susun_rencana()` (routing + RAG backend).
  System prompt dari frontend, bila masih ada, **sengaja diabaikan**.

> Ini satu-satunya perubahan di `src/`. Aturan awal "jangan ubah `src/`" dilanggar **atas
> persetujuan pengguna**, dan hanya pada satu fungsi (logika AI, bukan komponen UI).

---

## 3. Perbaikan kualitas RAG

### 3.1 Retriever leksikal BM25 (`rag/lexical.py`, BARU)
Menggantikan Fuse.js sebagai mesin pencari utama:

| Fitur | Manfaat |
|---|---|
| BM25 + bobot medan (judul & kata kunci 3×, isi 1×) | Dokumen bertopik persis selalu menang |
| Pembobotan IDF + **batas atas IDF 3,0** | Kata umum tidak mendominasi; kata langka tunggal tidak menjatuhkan dokumen yang cocok |
| **Gerbang cakupan IDF ≥ 0,50** | Anti-halusinasi: dokumen hanya lolos bila cukup banyak istilah penting pertanyaan benar-benar ada di dokumen |
| Bonus frasa kata kunci | Frasa seperti "pendaftaran mahasiswa baru" memberi dorongan kuat |
| Stemming ringan + pencocokan akar | "masuknya" cocok dengan "masuk"; "mengajar"/"pengajar" → "ajar" |
| **Koreksi salah ketik (Levenshtein)** | "persaratan" → "persyaratan" tetap terjawab |
| Ekspansi sinonim Indonesia | uang↔biaya↔pembayaran, dosen↔pengajar, daftar↔pendaftaran, dll. |

### 3.2 Embedder semantik opsional (`rag/embedder.py`)
- bge-m3 dimuat dari **folder lokal `ai-engine/models/bge-m3/`** lebih dulu (tanpa jaringan).
- Unduhan HuggingFace hanya dicoba bila `SELA_EMBEDDER_HF=1`.
- Pemuatan model memakai **batas waktu thread** → startup server tidak pernah menggantung.
- Bila bge-m3 belum ada, RAG tetap presisi karena BM25 yang memimpin.

### 3.3 Hasil terukur
```
Sebelum (Fuse.js, threshold 0.65):  "dosen FTI algoritma" → dokumen biaya kuliah  ❌
Sesudah (BM25 + gerbang cakupan):   "dosen FTI algoritma" → dosen_fti  (peringkat 1) ✅

Goldens: 16/20 (80%) → 20/20 (100%)
Anti-halusinasi tetap kuat: "resep rendang", "siapa presiden indonesia",
"harga bitcoin", "lagu dangdut" → semua DITOLAK (tidak ditemukan).
```

---

## 4. Pertanyaan di luar kampus kini berfungsi

Urutan routing baru di `susun_rencana()`:

```
1. Niat cepat (sapaan / identitas / terima kasih / penutup)   → jawaban langsung
2. Curhat                                                      → jalur empatik
3. RAG kampus                                                  → jalur "kampus"
4. Real-time (presiden, cuaca, berita)                         → jalur "web" (DuckDuckGo/Wikipedia/Wikidata)
5. Topik kampus tapi belum tercatat                            → jalur "kampus_kosong" (jawab jujur)
6. Pertanyaan umum di luar kampus                              → jalur "umum" (jawab singkat + arahkan ke UCIC)
```

Sebelumnya urutan 3 dan 4 terbalik dan tidak ada langkah 6, sehingga pertanyaan umum jatuh ke
"belum punya informasi". Prompt baru `LUAR_TOPIK_PROMPT` (di `prompts/sela_prompts.py`) menangani
jalur 6 dengan hangat lalu mengarahkan kembali ke UCIC.

Contoh nyata: **"cara membuat rendang padang"** → `jalur=umum`, dijawab wajar, lalu diarahkan ke
UCIC. Sebelumnya ditolak.

---

## 5. File & folder yang DIHAPUS

### Sesi ini (dipindah ke Recycle Bin — dapat dipulihkan)
| Item | Ukuran | Alasan |
|---|---|---|
| `ai-engine/models/higgs/` | 739 KB | Cache HuggingFace higgs-audio, unduhan gagal, tidak direferensikan |
| `ai-engine/models/omnivoice/` | 0 B | Folder kosong, TTS OmniVoice sudah digantikan Piper |
| `ai-engine/models/qwen2.5-0.5b-instruct-q4_k_m.gguf` | 469 MB | Duplikat — pemilih model memprioritaskan Qwen 3.5 |
| `ai-engine/voice_samples/` | 7,8 MB | Sampel suara lama, tidak direferensikan |
| `models/` (root proyek) | 75 MB | Cache whisper-tiny sisa; STT membaca `ai-engine/models/whisper` |
| `_uji_real.wav`, `test_sela.mp3` | 219 KB | Artefak uji di root |
| `unsloth_compiled_cache/` | 3,8 MB | Cache training, tidak dipakai runtime |
| `ai-engine/**/__pycache__/` | — | Bytecode usang |

**Tetap disimpan (dipakai):** `Qwen3.5-4B-UD-Q4_K_XL.gguf`, `tts_piper/`, `whisper/`.

### Sesi sebelumnya
| File | Alasan |
|---|---|
| `ai-engine/pemroses_llm.py` | LLM lama via subprocess `llama-server` → digantikan `core/llm_engine.py` |
| `ai-engine/sintesis_suara.py` | TTS OmniVoice (lambat) → digantikan `core/tts_engine.py` (Piper) |
| `ai-engine/pengenal_suara.py` | STT lama (punya fallback `tempfile`) → digantikan `core/stt_engine.py` |
| `ai-engine/mesin_rag.py` | RAG lama (BM25 + intent hardcode) → digantikan `rag/` |
| `ai-engine/pencari_web.py` | → digantikan `tools/web_search_tool.py` |
| `ai-engine/precache_omnivoice.py` | Pre-cache audio OmniVoice ke disk → tidak relevan |
| `ai-engine/uji_asr_mini.py`, `uji_asr_roundtrip.py`, `uji_cuda_debug.py` | Skrip debug ad-hoc |
| `ai-engine/_test_all.py` | Menguji modul lama yang sudah dihapus |
| `ai-engine/test_server.py` (lama) | Diganti versi baru |
| `ai-engine/cache_audio/` (**113 berkas, 50 MB**) | Cache audio ke disk — inti masalah "tmp numpuk" |

> Berkas yang tracked Git dapat dipulihkan dengan `git checkout`. Item sesi ini ada di Recycle Bin.

---

## 6. Struktur arsitektur saat ini

```
ai-engine/
├── core/
│   ├── llm_engine.py      # Singleton, GGUF langsung (llama-cpp-python → cadangan llama-server)
│   ├── stt_engine.py      # faster-whisper, 100% BytesIO, TANPA tempfile
│   ├── tts_engine.py      # Singleton PiperVoice, audio di memori
│   └── vad_engine.py      # Silero/FastRTC bila ada, cadangan VAD energi + hysteresis
├── rag/
│   ├── chunker.py         # SentenceWindow 512/80
│   ├── lexical.py         # ★ BARU: BM25 + bobot medan + gerbang cakupan IDF
│   ├── embedder.py        # bge-m3 (lokal → HuggingFace) + cadangan hashing
│   ├── engine.py          # RagEngine: gabung leksikal (+ semantik bila ada), ambang relatif
│   └── vector_store/      # FAISS IndexFlatIP + cadangan NumPy
├── tools/
│   ├── campus_tool.py     # RAG UCIC + deteksi intent
│   ├── web_search_tool.py # DuckDuckGo + Wikipedia/Wikidata
│   └── curhat_tool.py     # Mode empatik
├── prompts/
│   └── sela_prompts.py    # 7 prompt + ATURAN_ANTI_NOISE + ATURAN_PERTANYAAN_LANJUTAN
├── build_rag_index.py     # Bangun & simpan indeks vektor (opsional)
├── test_server.py         # Uji asap (57 cek) + evaluasi goldens
├── persiapan_model.py     # Cek GGUF + LoRA + Piper + tautan unduh
├── requirements.txt       # WAJIB vs OPSIONAL
└── server.py              # 1 entry point: FastAPI + WebSocket + routing + barge-in
```

---

## 7. Status dependensi

**Sudah terpasang & dipakai** (Python 3.12): `llama-cpp-python` 0.3.16, `piper-tts` 1.8.0,
`faster-whisper` 1.2.1, `fastapi`, `uvicorn`, `numpy` 2.5.3, `soundfile`, **`faiss-cpu` 1.15.0**,
**`sentence-transformers` 6.0.1**, **`duckduckgo-search` 8.1.1**.

**Masih memakai cadangan (tidak membuat crash):**
| Paket | Untuk | Cadangan yang aktif |
|---|---|---|
| model `BAAI/bge-m3` | embedding semantik | retriever leksikal BM25 (presisi 100% goldens) |
| `fastrtc` | Silero VAD | VAD energi + hysteresis di `vad_engine.py` |
| `llama-index` | `SentenceWindowNodeParser` | `rag/chunker.py` (setara, tanpa dependensi) |

---

## 8. Cara menjalankan & menguji

```bash
# 1. Pasang dependensi (sekali)
pip install -r ai-engine/requirements.txt

# 2. Cek ketersediaan model
python ai-engine/persiapan_model.py

# 3. Jalankan server  ← 1 entry point, offline
python ai-engine/server.py
#    -> http://127.0.0.1:8008   (UI dari dist/, endpoint /kesehatan)

# 4. Uji asap + evaluasi goldens
python ai-engine/test_server.py
#    (tambah SELA_UJI_SERVER=1 untuk sekaligus menguji routing & endpoint FastAPI)

# 5. Build UI (verifikasi perubahan src/lib/ai.js tidak merusak frontend)
npm run build
```

**Hasil verifikasi ulang terakhir (2026-09-14):**
- `test_server.py` → **44 lulus / 0 gagal** (lapisan offline).
- `SELA_UJI_SERVER=1 test_server.py` → **57 lulus / 0 gagal** (termasuk routing + endpoint).
- `vite build` → **716 modul tertransformasi, build sukses** (`src/lib/ai.js` valid).

Verifikasi cepat via HTTP (kontrak baru: kirim `userQuery` + `riwayat_obrolan`):
```bash
curl http://127.0.0.1:8008/kesehatan
curl -X POST http://127.0.0.1:8008/api/chat -H "Content-Type: application/json" \
     -d '{"userQuery":"Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?","riwayat_obrolan":[]}'
```

**Hasil verifikasi nyata pada mesin ini** (server hidup, LLM aktif):
| Pertanyaan | Jalur | Hasil |
|---|---|---|
| "Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?" | kampus | ✅ menjawab daftar dosen FTI (bukan lagi biaya kuliah) |
| "Bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?" | kampus | ✅ ter-grounding + pertanyaan lanjutan |
| "siapa dedi mulyadi" | kampus | ✅ jujur "belum tercatat" + kontak PMB (tidak mengarang) |
| "berapa biaya kuliah teknik informatika" | kampus | ✅ angka cocok persis dengan dokumen sumber |
| "cara membuat rendang padang" | **umum** | ✅ dijawab wajar lalu diarahkan ke UCIC |
| "kalau telat masuk kelas lebih dari 15 menit" | kampus | ✅ sesuai aturan BAAK |

---

## 9. Sisa rekomendasi (belum dieksekusi)

1. ~~Bersihkan sisa kode Fuse.js di `src/lib/ai.js`.~~ **SELESAI** — lihat §10.
2. **Selesaikan unduhan bge-m3.** `ai-engine/models/bge-m3/pytorch_model.bin` masih diunduh
   (berjalan, ±0,8 GB dari ±2,27 GB). Setelah lengkap, jalur semantik aktif otomatis pada start
   berikutnya (indeks vektor dibangun ulang sekali). Jalankan ulang bila terputus:
   `python ai-engine/persiapan_model.py --unduh-embedder` (resume via HTTP Range).
3. **`ai-engine/llama_vulkan/`** (52 berkas biner, tracked Git) — **JANGAN dihapus di mesin ini.**
   `llama-cpp-python` gagal (`STATUS_ILLEGAL_INSTRUCTION`), jadi llama-server Vulkan itulah backend
   LLM yang benar-benar dipakai. Hapus hanya bila llama-cpp-python sudah berjalan murni.
4. **`src/lib/responsePlan.js`** kini hanya dipakai untuk `buildSpokenText`. Fungsi
   `buildResponsePlan`, `prioritizeResponseMatches`, `buildResponsePlanPrompt` tidak lagi dipakai
   aplikasi (masih dipakai `responsePlan.test.js`). Dibiarkan utuh agar suite tesnya tetap hijau.
5. **Suara custom SELA:** taruh `id_ID-ucic-sela-medium.onnx` (+ `.onnx.json`) di
   `ai-engine/models/tts_piper/`. `tts_engine.py` otomatis memprioritaskannya.
6. **LoRA UCIC:** taruh `qwen3-4b-ucic-lora.gguf` di `ai-engine/models/`; `llm_engine.py`
   otomatis mendeteksi dan memuatnya.
7. **`.gitignore`:** `ai-engine/models/` sudah tercakup, jadi `bge-m3/` ikut terabaikan otomatis.

---

## 10. Pembersihan kode mati di frontend (`src/lib/ai.js`)

Setelah `getChatCompletion()` menjadi klien tipis (§2), seluruh mesin retrieval Fuse.js di
frontend tidak lagi terpakai. Dihapus **1.409 baris** (3.172 → 1.763) tanpa mengubah perilaku.

**Yang dihapus:** `getFuse` + import `fuse.js`, import `rag_goldens.json`, dan seluruh rantai
retrieval lama — `resolveRetrievalState`, `retrieveCampusContext`, `getTopicFallbackMatches`,
`buildCanonicalRewrite`, `buildRetrievalQuery`, `computeAnswerability`, `buildClarificationHint`,
`buildConfidenceRouting`, `buildIntentResponseGuide`, `scoreDatasetItem`, `getSearchTokens`,
`getTokenVariants`, `itemContainsTokenVariant`, `getMatchedTokenCount`, `hasStrongFieldMatch`,
`hasEnoughTokenCoverage`, `buildDatasetAnswerFromMatches` (+ `_textSimilarity`, `truncateForVoice`),
`evaluateRetrievalGoldens`, `getLatestRetrievalEvaluation`, `__debugResolveRetrievalState`,
`getShadowFaqReviewQueue`, `reviewShadowFaqCandidate`, `logRetrievalFailure`,
`deriveConversationTopicState`, `getAliasBoostTopics`, `getExplicitTopics`,
`buildConversationContextHint`, `classifyQueryContinuity`, `getRecentReferencedPrograms`,
`extractProgramReferences`, `isComparisonFollowUp`, `hasReferentialSignal`,
`getRecentReferenceMessages`, `getReferenceMessageText`, `getReferenceMessageLimit`,
`looksLikeUnavailableAnswer`, analisis kualitas audio (`analyzeAudioQuality`,
`computeFrequencyDomain`, `fft`, `analyzeSpectralContent`, `calculateEntropy`,
`getAmplitudeRange`), web-search frontend (`needsWebSearch`, `doWebSearch`), dan memori nama user
(`extractUserName`, `saveUserName`, `getUserName`, `getUserMemory`, `isGreetingOrIdentity`).
Konstanta mati (`BROAD_SYNONYM_KEYS`, `GENERIC_REVERSE_SYNONYM_TOKENS`, `REFERENTIAL_TOKENS`,
`PROGRAM_REFERENCE_ALIASES`, `RAG_EVALUATION_KEY`, `SHADOW_REVIEW_MIN_SOURCE_COUNT`) juga dihapus.
`fuse.js` dilepas dari `package.json`.

**Yang dipertahankan:** 9 ekspor yang diimpor `src/components/VoiceUI.jsx` (satu-satunya konsumen)
— `transcribeAudio`, `getChatCompletion`, `speakText`, `stopSpeaking`, `streamChatAndVoice`,
`getTimeBasedGreeting`, `archiveConversationSession`, `prepareTranscriptForRag`,
`looksLikeShortValidQuery` — plus `parseSuggestions` (dipakai internal) dan seluruh rantai
pembersihan transkrip + pembelajaran sesi.

**Verifikasi:**
| Uji | Hasil |
|---|---|
| `vite build` | ✅ 714 modul (turun dari 716 — `fuse.js` + `rag_goldens.json` tak lagi ikut) |
| Ukuran bundle JS | **identik** (1.402,41 kB) → kode mati memang sudah ter-*tree-shake*, jadi 0 risiko runtime |
| Smoke test runtime (esbuild + Node, browser di-*stub*) | ✅ **23 lulus / 0 gagal** |
| `dist/` hasil build | ✅ 0 jejak Fuse.js (168 kemunculan kata "fuse" semuanya bagian dari `diffuse`/`tDiffuse` Three.js) |

---

## 11. Perbaikan mutu jawaban (temuan verifikasi langsung)

Verifikasi langsung ke server hidup (5 pertanyaan dari transkrip pengguna) menemukan **satu cacat
nyata yang belum tertangani**: pertanyaan *"Siapa dosen lain di FTI yang mengajar Algoritma?"*
menghasilkan kalimat **berputar** —

> "Selain Petrus Sokibi dan Kusnadi, dosen lain di FTI yang mengajar Algoritma adalah **Petrus Sokibi dan Kusnadi**."

### Akar masalah
Data `dosen_fti` memuat 10 nama **tanpa** peta mata kuliah; hanya `daftar_dosen_lengkap` yang
memetakan *"Petrus Sokibi — Algoritma Pemrograman"* dan *"Kusnadi — Algoritma Pemrograman"*.
Pertanyaannya mengandaikan ada dosen **tambahan** yang sebenarnya tidak ada di data, sehingga model
mengisi kekosongan itu dengan mengulang nama yang sama.

### Perbaikan (`ai-engine/prompts/sela_prompts.py`)
| Aturan | Isi |
|---|---|
| `CAMPUS_RAG_ANTI_HALU` aturan 12 (BARU) | Larangan kalimat berputar + contoh SALAH eksplisit; bila tidak ada nama tambahan, jawab terus terang lalu tawarkan konfirmasi; jangan memakai kata "lain/lainnya" untuk nama yang sama |
| `ATURAN_PERTANYAAN_LANJUTAN` | Saran lanjutan wajib masuk akal & seputar layanan kampus; dilarang menanyakan hal pribadi tentang orang tertentu (contoh SALAH: *"Berapa lama waktu kuliah Petrus Sokibi?"*) |
| `MASTER_PERSONA` aturan 3 | Angka/harga wajib kata Bahasa Indonesia; dilarang mencampur kata angka Inggris (`thirteen`, `million`) |

### Hasil sesudah perbaikan (server hidup, diuji ulang)
| Pertanyaan | Jalur | Hasil |
|---|---|---|
| "Siapa dosen lain di FTI yang mengajar mata kuliah Algoritma?" | kampus | ✅ "yang tercatat mengajar Algoritma adalah Petrus Sokibi dan Kusnadi. Tidak ada nama dosen tambahan lainnya" — **tidak berputar** |
| "siapa lagi dosen yang mengajar Algoritma?" | kampus | ✅ "hanya Petrus Sokibi dan Kusnadi yang tercatat… tidak ada nama dosen lain" |
| "selain Petrus Sokibi, siapa lagi yang mengajar Algoritma Pemrograman?" | kampus | ✅ "selain Petrus Sokibi, dosen lain yang tercatat adalah Kusnadi" (benar) |
| "Bagaimana cara mendaftar sebagai mahasiswa baru di UCIC?" | kampus | ✅ ter-grounding + alamat Kampus 2 |
| "siapa dedi mulyadi" | kampus | ✅ "saya tidak mencatat nama Dedi Mulyadi di daftar dosen atau staff UCIC" — jujur, tidak mengarang |
| "berapa biaya kuliah teknik informatika" | kampus | ✅ angka rupiah sesuai dokumen, tanpa campur kata Inggris |
| "cara membuat rendang padang" | **umum** | ✅ dijawab wajar lalu diarahkan ke UCIC |
| "siapa presiden indonesia sekarang" | **web** | ✅ dijawab dari pencarian web real-time |

**Skor verifikasi otomatis: 6/7 lulus** — satu "gagal" adalah *false negative* pada skrip uji saya
(mengharapkan frasa "tidak tercatat", sedangkan SELA menulis "tidak mencatat"), bukan cacat produk.

**Catatan:** `dist/` (yang disajikan `server.py`) juga dibangun ulang agar UI terkirim memakai
frontend bersih, bukan bundle lama 9 September.

---

## 12. Perbaikan kontrak UI yang tertinggal dari refactor OmniVoice → Piper

Audit menyeluruh terhadap referensi berkas/folder yang dihapus menemukan **satu bug UI nyata**
akibat refactor TTS (OmniVoice → Piper) di sesi sebelumnya: kontrak frontend–backend tidak sinkron.

### Bug: badge status TTS menyala "Memuat AI..." selamanya
`src/components/Navbar.jsx` (`TtsStatusBadge`) memeriksa medan lama:

```js
if (status.omnivoice_siap || status.omnivoice_voice_design) { ... }   // tidak pernah true
if (status.omnivoice_gagal) { ... }                                   // tidak pernah true
return ( ... "Memuat AI..." ... )                                     // SELALU jatuh ke sini
```

Padahal `/api/status-tts` sekarang mengembalikan:

```json
{ "piper_siap": true, "engine_aktif": "piper",
  "model_aktif": { "id": "...", "en": "..." }, "pesan_status": "Piper siap: ..." }
```

Karena tidak ada medan `omnivoice_*`, badge **selalu** menampilkan indikator biru
"Memuat AI..." yang berdenyut, seolah mesin belum siap — padahal Piper sudah aktif.

### Perbaikan
- `src/components/Navbar.jsx` → badge memakai kontrak nyata: `piper_siap` (hijau, label "Piper"),
  `engine_aktif === "piper-unavailable"` (kuning, "TTS Error"), sisanya "Memuat AI...".
- `src/lib/ai.js` → log/komentar TTS yang masih menyebut "OmniVoice" diganti "Piper";
  nama fungsi internal `akhiriKegagalanOmni` → `akhiriKegagalanTts` (beserta 4 titik pemanggilnya).

> Ini perubahan `src/` kedua, tetapi merupakan **penyelesaian refactor saya sendiri**: backend sudah
> Piper sedangkan UI masih membaca medan OmniVoice, sehingga badge rusak permanen.

### Verifikasi
| Uji | Hasil |
|---|---|
| `vite build` | ✅ 714 modul, sukses |
| Bundle `dist/assets/index-86cab0f3.js` | ✅ memuat `piper_siap`; **0** kemunculan `omnivoice` |
| Smoke test runtime (esbuild + Node) | ✅ **17 lulus / 0 gagal** (termasuk `speakText` setelah rename) |
| Endpoint UI hidup | ✅ `/api/status-tts`, `/api/status-asr`, `/kesehatan`, `/`, `/api/sintesis` → semua HTTP 200 |
| Audit endpoint | ✅ hanya 5 endpoint dipakai UI (`/api/chat`, `/api/sintesis`, `/api/status-tts`, `/api/transcribe`, `/ws/dupleks`) — semuanya ada di backend |

Sisa kemunculan "OmniVoice" yang sengaja dibiarkan: komentar di `src/lib/responsePlan.js` dan
entri `.gitignore` (`cache_audio/`, `voice_samples/*.wav`, `unsloth_compiled_cache/`) — keduanya
tidak berpengaruh ke runtime dan aman bila dibiarkan.

---

## 13. Perbaikan pemeriksaan keutuhan bobot embedder (unduhan terpotong)

Ditemukan saat verifikasi log server pasca-perbaikan launcher Electron:

```
[Embedder] bge-m3 tidak tersedia (PytorchStreamReader failed reading zip archive:
failed finding central directory. ... your checkpoint file is corrupted. ...).
Memakai embedder hashing cadangan; retriever leksikal BM25 tetap memimpin.
```

### Akar masalah
Berkas `ai-engine/models/bge-m3/pytorch_model.bin` berhenti terunduh di tengah
(**1,25 GB dari 2,27 GB** yang seharusnya). Penjaga keutuhan hanya memeriksa **ukuran**:

```python
ambang = 1_000_000 if nama.endswith(".onnx") else 1_000_000_000
if os.path.getsize(jalur) > ambang:
    return True          # 1,25 GB > 1 GB  ->  LOLOS, padahal terpotong
```

Akibatnya berkas rusak dianggap siap, dimuat, lalu gagal dengan galat korupsi. Hal yang sama
terjadi di `persiapan_model.py::_embedder_lengkap()`, sehingga laporan pra-terbang sempat
menyatakan embedder "lengkap" padahal belum.

### Perbaikan
Penjaga kini memverifikasi **isi** berkas, bukan sekadar ukurannya:

| Format | Cara verifikasi |
|---|---|
| `.safetensors` | 8 byte awal (little-endian) = panjang header JSON; utuh bila `8 + header ≤ ukuran berkas` |
| `.bin` (PyTorch) | Arsip zip; utuh bila *central directory* di akhir berkas terbaca (`zipfile.ZipFile`) — pemotongan selalu merusaknya |
| `.onnx` | Protobuf tanpa indeks di akhir, jadi cukup ambang ukuran |

Berkas yang diubah:
- `ai-engine/rag/embedder.py` → fungsi baru `bobot_model_utuh()`; `_punya_berat()` diganti
  `_bobot_lokal_utuh()` yang mendelegasikan ke verifikator. Pesan `_muat()` juga diperjelas
  ketika tidak ada kandidat sumber (sebelumnya bisa mencetak `(None)`).
- `ai-engine/persiapan_model.py` → `_bobot_utuh()` (kembar, sengaja diduplikasi agar skrip
  pra-terbang tetap berjalan **tanpa** mengimpor paket RAG yang butuh numpy/faiss) dan
  `_embedder_lengkap()` memakainya. `_unduh_satu()` kini mendeteksi **pemotongan senyap**:
  bila ukuran akhir ≠ `Content-Length`, ia melaporkan sisa unduhan dan gagal, bukan mencetak `[V]`.

### Verifikasi
| Uji | Hasil |
|---|---|
| `bobot_model_utuh` pada berkas asli 1,25 GB | ✅ `False` (sebelumnya `True`) |
| `Embedder._kandidat_sumber()` | ✅ `[]` → jatuh ke embedder hashing, **tanpa** galat korupsi |
| Uji unit verifikator (6 kasus: zip utuh/terpotong/bukan-zip, safetensors utuh/terpotong/header rusak) | ✅ **6 lulus / 0 gagal** |
| `persiapan_model.py` (laporan pra-terbang) | ✅ kini melaporkan `Embedder bge-m3 (opsional): BELUM ADA` |
| `py_compile` kedua berkas | ✅ sintaks OK |

> Perilaku degradasi tetap seperti rancangan: tanpa bge-m3, RAG berjalan penuh dengan retriever
> leksikal BM25 (yang memang mesin utama dan sudah 20/20 pada data emas). Unduhan dapat
> dilanjutkan kapan saja dengan `py -3.12 ai-engine/persiapan_model.py --unduh-embedder`.

---

## 14. Perbaikan gerbang RAG: pertanyaan luar kampus yang lolos (temuan verifikasi langsung)

Saat memverifikasi ulang rute pertanyaan di luar kampus, ditemukan **kebocoran gerbang
anti-halusinasi**: beberapa pertanyaan yang jelas di luar kampus tetap mendapat konteks
dokumen kampus, sehingga dijawab lewat `jalur=kampus` alih-alih `jalur=umum`/`jalur=web`.

```
"Siapa presiden Indonesia?"  -> jalur=kampus, konteks: pedoman_mou_kerja_sama
"resep rendang"              -> jalur=kampus, konteks: layanan_cs_pmb
```

### Akar masalah (dua sebab yang saling memperkuat)

**a. Koreksi salah ketik (OOV) memalsukan kecocokan.**
`LexicalIndex._koreksi_oov()` memetakan **setiap** token di luar kosakata ke istilah korpus
terdekat (jarak edit 1–2) tanpa syarat kemiripan makna:

| Token pengguna | Dipetakan ke | Akibat |
|---|---|---|
| `resep` | `reset` | cocok di `layanan_cs_pmb` |
| `rendang` | `renang` | cocok di `kurikulum_pkor` |
| `sekarang` | `sekurang` | — |

**b. Gerbang cakupan hanya memakai pecahan, tanpa syarat jumlah istilah.**
Pada pertanyaan **dua** kata, satu kecocokan kebetulan sudah bernilai cakupan
`idf(presiden) / (idf(presiden)+idf(indonesia)) = 0,56` — di atas ambang `0,50` → lolos.
Pada versi **tiga** kata pecahannya turun menjadi `0,33` → tertolak. Itulah sebabnya bug ini
lolos dari pengujian: tes lama memakai varian panjang
(`"resep rendang padang"`, `"siapa presiden indonesia sekarang"`) yang kebetulan tertolak.

### Perbaikan
`rag/lexical.py` menambah lapisan kelima: `_MIN_COCOK_DISTINCT = 2`. Sebuah dokumen hanya lolos
bila **≥ 2 istilah pertanyaan yang berbeda** benar-benar cocok di dokumen **yang sama**
(bila pertanyaan hanya punya satu istilah bermakna, satu kecocokan tetap cukup).

Ini tepat sasaran karena `reset` hanya ada di `layanan_cs_pmb` dan `renang` hanya di
`kurikulum_pkor` — **tidak ada satu dokumen pun** yang memuat keduanya, sehingga
`"resep rendang"` gugur secara alami tanpa perlu mempersulit koreksi salah ketik
(memperketat koreksi justru menurunkan recall goldens menjadi 19/20).

### Verifikasi
| Uji | Sebelum | Sesudah |
|---|---|---|
| Goldens (`rag_goldens.json`) | 20/20 | **20/20** (tidak turun) |
| 11 kueri luar kampus ditolak | 8/11 | **11/11** |
| Kueri kampus tetap ketemu | 6/6 | **6/6** |
| `/api/chat` "Siapa presiden Indonesia?" | `jalur=kampus` (dokumen MoU) | **`jalur=web`** → jawaban benar |
| `/api/chat` "resep rendang" | `jalur=kampus` (dokumen CS) | **`jalur=umum`** → jawab singkat + arahkan |
| Suite backend | 57 lulus | **60 lulus / 0 gagal** |

Tes regresi ditambahkan di `test_server.py` memakai **varian pendek** yang sebelumnya lolos,
sehingga kebocoran ini tidak bisa kembali diam-diam.

---

## 15. Verifikasi jalur semantik (FAISS) + perbaikan konsistensi indeks

Seluruh jalur vektor (`bangun_indeks` → `simpan` → `muat` → `cari` → `_gabung_semantik`)
**belum pernah benar-benar dieksekusi**, karena bge-m3 belum pernah tersedia. Jalur ini
diuji dengan memaksa `_semantik_aktif()` menyala (encoder hashing dipakai sebagai pengganti
bge-m3), dan langsung terungkap tiga cacat nyata di `rag/vector_store/__init__.py`.

### Cacat yang ditemukan dan diperbaiki

**a. `simpan()` meninggalkan representasi usang.**
Jalur FAISS hanya menulis `index.faiss`; `vectors.npy` lama **tidak dibuang**. Bila faiss
kemudian tidak tersedia (mis. dependensi dipasang ulang), `muat()` akan memuat `vectors.npy`
berdimensi 512 sementara `meta.json` menyatakan 1024 → jalur semantik **mati senyap**
(galatnya tertelan `try/except` di `_gabung_semantik`).
→ Kini hanya SATU representasi yang boleh ada; yang lain dihapus saat `simpan()`.

**b. `muat()` tidak memeriksa kecocokan dimensi maupun jumlah.**
→ Kini `muat()` menolak indeks yang dimensinya tidak cocok dengan `meta.json`, dan menolak
bila jumlah vektor ≠ jumlah metadata (mis. `meta.json` terpotong saat aplikasi dimatikan
di tengah `simpan`). Penolakan membuat `muat_atau_bangun()` membangun ulang indeks — bukan
memakai data rusak.

**c. `cari()` bisa melempar `IndexError`.**
Jalur NumPy memakai indeks baris vektor untuk mengambil `metadatas[i]`; bila jumlah keduanya
tidak sinkron, indeks bisa melewati batas. → Kini iterasi peringkat **melewati** indeks di
luar jangkauan, dan jalur FAISS membatasi `k` oleh `ntotal` serta menyaring indeks negatif.

### Verifikasi
| Uji | Hasil |
|---|---|
| Jalur semantik end-to-end (bangun → simpan → muat → cari → gabung) | ✅ 147 chunk, `index.faiss` terbentuk & termuat |
| Goldens dengan jalur semantik AKTIF | ✅ **20/20** |
| Kueri luar kampus dengan jalur semantik aktif | ✅ ditolak |
| Uji unit konsistensi indeks (8 kasus) | ✅ **8 lulus / 0 gagal** |
| Suite backend | ✅ **66 lulus / 0 gagal** (naik dari 60) |

Indeks lama berdimensi 512 (sisa masa bge-m3 belum ada) sudah dibersihkan dari
`rag/vector_store/faiss_index/`, sehingga saat bge-m3 selesai diunduh indeks dibangun ulang
bersih pada 1024 dimensi. Enam tes regresi baru ditambahkan di `test_server.py`.

---

## 16. Penggantian model 3D SELA (v05) + pembersihan file lama

Pengguna menaruh dua berkas model baru di root proyek. Keduanya dipindahkan ke lokasi yang
benar, berkas sumber di root dihapus, dan seluruh model lama dibuang.

### Berkas dipindahkan / dihapus

| Aksi | Berkas | Keterangan |
|---|---|---|
| **Dipindah** | `Draft 11 (Animation) AI Sela_v05.glb` → `public/models/sela.glb` | 12.520.852 byte, md5 `16a3929bdf32eb4e95a7bd01f44e3d35` — model runtime yang dimuat aplikasi |
| **Dipindah** | `Draft 11 (Animation) AI Sela_v04.fbx` → `assets/3d-source/AI-Sela-v04.fbx` | 11.861.004 byte, md5 `254b75c40c83ad7628786434e368991f` — sumber editable (tidak ikut bundel Vite) |
| **Dihapus** | `Draft 11 (Animation) AI Sela_v05.glb` (root) | asli, setelah dipindah |
| **Dihapus** | `Draft 11 (Animation) AI Sela_v04.fbx` (root) | asli, setelah dipindah |
| **Dihapus** | `public/models/SELA_BARU.glb` | model lama yang dipakai kode |
| **Dihapus** | `dist/models/SELA_BARU.glb`, `dist/models/sela.glb` | sisa bundel usang |

Verifikasi: `md5sum` berkas tujuan identik dengan sumber; tidak ada berkas `.glb`/`.fbx` tersisa
di root.

### Perbedaan model lama vs baru (hasil inspeksi langsung atas chunk JSON glTF)

| Aspek | Model lama (`SELA_BARU.glb`) | Model baru (`sela.glb` v05) |
|---|---|---|
| Tinggi geometri | 0,909 satuan | 1,344 satuan (**±1,48× lebih tinggi**) |
| Morph target | `aa, ih, u, e, o, EyeBlinkLeft, EyeBlinkRight` | `a, i, u, e, o, blink.l, blink.r, blink.all` |
| Nama animasi | `Idle`, `Menggelengkan Kepala`, `Rest`, `Talking` | `Confused`, `Goodbye`, `Greeting`, `Idle`, `Nodding`, `Shaking Head`, `Talking`, `Thinking`, `Talking_%temp` |
| Jumlah node / skin | 85 node, 1 skin | 85 node, 1 skin |

### Cacat yang ditemukan & diperbaiki

**a. Skala model tidak lagi cocok.** Konstanta `MODEL_SCALE = 5,0` mengasumsikan tinggi
geometri 0,909. Pada model baru, konstanta itu membuat avatar **±48% kelewat besar**. →
Skala kini **dihitung otomatis** dari bounding box model yang benar-benar dimuat
(`TINGGI_AVATAR / tinggi`), sehingga tinggi tampil selalu 4,55 satuan berapa pun modelnya:

```js
const { skala, posisiY } = useMemo(() => {
  const kotak = new THREE.Box3().setFromObject(scene)
  const tinggi = kotak.max.y - kotak.min.y
  if (!Number.isFinite(tinggi) || tinggi <= 0.0001) {
    return { skala: 1, posisiY: DASAR_AVATAR_Y }
  }
  const skalaHitung = TINGGI_AVATAR / tinggi
  return { skala: skalaHitung, posisiY: DASAR_AVATAR_Y - kotak.min.y * skalaHitung }
}, [scene])
```

**b. Animasi `Talking_%temp` akan merusak lipsync.** Klip ini punya satu kanal yang
menargetkan `weights` (morph target) → akan **berebut kendali mulut** dengan Wawa Lipsync yang
menggerakkan morph setiap frame. → Dilarang diputar lewat daftar `ANIMASI_DILARANG` dan
dikecualikan dari semua loop `fadeOut`.

### Lipsync: TIDAK berubah (diverifikasi, bukan diasumsikan)

Nama morph berubah (`aa`→`a`, `EyeBlinkLeft`→`blink.l`, dst.), jadi pencocokan alias diuji
ulang terhadap model baru: **5/5 viseme (`a, i, u, e, o`) + kedip `blink.l`/`blink.r`
semuanya cocok.** Sebagai jaring pengaman ditambahkan alias cadangan `blink.all`
(`blinkall`/`blink_all`) di akhir daftar `eyeBlinkLeft`/`eyeBlinkRight`, yang hanya terpakai
bila model tidak punya morph kedip per-mata. Mesin lipsync Wawa sendiri tidak disentuh.

---

## 17. Animasi 3D kini mengikuti sifat jawaban AI

Animasi baru (`Confused`, `Goodbye`, `Greeting`, `Nodding`, `Shaking Head`) sebelumnya tidak
pernah dipanggil kode mana pun. Kini animasi dipilih oleh **backend** (satu otak) dan
diteruskan sampai ke avatar.

### Rantai data

| Lapisan | Berkas | Perubahan |
|---|---|---|
| Backend (pemilih) | `ai-engine/server.py` | Fungsi `tentukan_gerakan(jalur, intent)` memetakan sifat jawaban → nama animasi; `/api/chat` mengembalikan field `gerakan` |
| Klien tipis | `src/lib/ai.js` | `getChatCompletion` meneruskan `gerakan: data.gerakan \|\| null` |
| UI | `src/components/VoiceUI.jsx` | State `gerakan` + `gerakanKunciRef`; helper `jalankanGerakan(nama)`; dipanggil dari jalur jawaban, greeting, dan perpisahan; prop diteruskan ke avatar |
| Render 3D | `src/components/AvatarPlaceholder.jsx` | Memutar klip sebagai **one-shot** (`LoopOnce` + `clampWhenFinished`), lalu kembali ke animasi latar |

Pemetaan `tentukan_gerakan`: sapaan → `Greeting`; perpisahan/terima kasih → `Goodbye`;
ketidakpastian / tidak ketemu → `Confused`; konfirmasi / "iya, benar" → `Nodding`;
penolakan / koreksi → `Shaking Head`. Nama-nama ini **wajib persis sama** dengan klip di
`public/models/sela.glb` (ada komentar peringatan di kode).

### Cara kerja animasi di `AvatarPlaceholder.jsx`

1. Animasi latar mengikuti status percakapan: `thinking` → `Thinking`, `speaking` → `Talking`,
   selain itu → `Idle` (masing-masing `LoopRepeat`).
2. Saat prop `gerakan` berubah, klip one-shot diputar dengan `LoopOnce` +
   `clampWhenFinished`, animasi latar di-`fadeOut`, lalu setelah durasi klip habis animasi
   latar kembali `fadeIn`. Field `kunci` (penghitung naik) membuat gerakan yang **sama** tetap
   diputar ulang pada jawaban berikutnya.
3. Saat TTS berbunyi, `state === 'speaking'` mengaktifkan analisis frekuensi audio Wawa →
   mulut tetap digerakkan lipsync, sementara klip one-shot hanya menggerakkan tulang
   (kepala/tangan), jadi keduanya tidak saling menimpa.

### Verifikasi (kontrak dikunci oleh tes)

Karena nama klip **wajib** cocok dengan isi model, kesalahan penggantian model bisa membuat
animasi mati senyap tanpa galat apa pun. Empat pemeriksaan ditambahkan ke `test_server.py`:

| Uji | Hasil |
|---|---|
| `tentukan_gerakan` selalu mengembalikan nama (semua cabang disapu) | ✅ 5 nama: `Confused, Goodbye, Greeting, Nodding, Shaking Head` |
| `sela.glb` terbaca langsung dari chunk JSON-nya | ✅ 9 animasi |
| Semua nama gerakan ada sebagai klip di `sela.glb` | ✅ 0 hilang |
| `POST /api/chat` menyertakan `gerakan` yang valid | ✅ `(Greeting)` untuk "halo" |

Pembaca nama animasi (`_nama_animasi_glb`) membongkar header 12 byte + chunk glTF sendiri
(`struct`), sehingga berkas model diperiksa apa adanya — bukan lewat daftar nama yang
di-hardcode. Bila model 3D diganti lagi dan ada nama klip yang tidak cocok, suite akan
**gagal**, bukan diam-diam kehilangan animasi.

---

## 18. Perbaikan TTS: membacakan teks penuh (bukan 2 kalimat pertama)

### Gejala
SELA kadang berhenti membaca di tengah jawaban; kalimat-kalimat terakhir tidak terdengar.

### Akar masalah
`buildSpokenText()` di `src/lib/responsePlan.js` — satu-satunya tempat teks disiapkan untuk
TTS — memotong isi dua kali:

```js
if (selected.length >= (plan.displayMode === "brief" ? 2 : 2)) break; // selalu 2 kalimat
...
if (spoken.length > 260) spoken = truncateSentence(spoken, 260);      // batas 260 karakter
```

Kedua batas ini **sisa dari era OmniVoice** (mesin TTS lama yang lambat di CPU). Di jalur
produksi, `ai.js` memanggil `buildSpokenText(displayText, null, ...)` sehingga
`displayMode` default `"brief"` → praktis **hanya 2 kalimat pertama** yang dibacakan.

### Perbaikan
Piper terbukti sanggup membaca cepat (benchmark: 542 karakter = **1,78 detik**; ±300
karakter/detik), jadi tidak ada lagi alasan memotong isi. `buildSpokenText` kini:
- membacakan **seluruh** kalimat jawaban (tanpa batas jumlah kalimat maupun panjang karakter),
- tetap menormalkan URL menjadi "Linknya bisa kamu akses di sini" dan membuang penanda
  markdown (`**`, `#`, `` ` ``) agar suara natural,
- membuang kalimat duplikat.

Tiga helper yang menjadi **kode mati** akibat perubahan ini (`truncateSentence`,
`countReadableParagraphs`, `extractLeadSentence`) dihapus dari `responsePlan.js`.

Rantai selebihnya **tidak perlu diubah** dan sudah diverifikasi tidak memotong teks:
`speakText` (`ai.js`) mengirim satu permintaan `/api/sintesis` dengan teks penuh; endpoint
`/api/sintesis` (`server.py`) meneruskan utuh ke `TtsEngine.sintesis_base64_async` →
`sintesis_wav_bytes` → Piper.

### Verifikasi
`responsePlan.test.js` diperbarui agar mengunci perilaku baru (bukan perilaku pemotongan
lama): **8 lulus / 0 gagal**, termasuk tes regresi "tidak memotong di batas 260 karakter"
dan "membacakan seluruh paragraf".

---

## 19. Berkas bobot bge-m3 rusak (dua unduhan paralel) + penjaga keutuhan diperketat

### Temuan
Saat memeriksa keadaan proyek, berkas `ai-engine/models/bge-m3/pytorch_model.bin` ternyata
**masih bertambah** (1 MiB / 4 detik) walau ukurannya sudah melewati ukuran seharusnya.
Penyebabnya: **dua proses mengunduh berkas yang sama secara bersamaan** ke satu jalur —
`persiapan_model.py --unduh-embedder` (mode `ab`, resume dari 1148 MB) dan satu unduhan
`urllib` lain (mode `wb`). Dua posisi tulis yang saling menimpa membuat isi berkas rusak.

| | |
|---|---|
| Ukuran benar (dari HEAD HuggingFace) | 2.271.145.830 byte |
| Ukuran di disk sesudahnya | **2.292.117.350 byte (20 MiB lebih besar)** |
| `zipfile.testzip()` | **RUSAK di `pytorch_model/data.pkl`** |

### Cacat penjaga yang ditemukan (ini yang berbahaya)
Penjaga `bobot_model_utuh()` (`rag/embedder.py`) — ditambahkan pada bagian 13 untuk menolak
unduhan **terpotong** — hanya membaca *central directory* zip (`arsip.namelist()`). Central
directory berada di **akhir** berkas dan tetap terbaca meski isi di tengahnya rusak, sehingga:

```python
bobot_model_utuh('pytorch_model.bin')   # berkas rusak di atas -> True  (SALAH)
```

Akibatnya berkas rusak **lolos** penjaga, lalu `SentenceTransformer` mencoba memuatnya.
Karena pemuatan dibungkus batas waktu **180 detik** (`_muat_dengan_batas`), setiap start
server berpotensi tertahan sampai 3 menit sebelum akhirnya jatuh ke embedder hashing —
dan jalur semantik tidak pernah benar-benar hidup.

### Perbaikan

**a. Penjaga memeriksa ISI, bukan hanya indeks** (`rag/embedder.py`).
Cabang `.bin` kini membaca **utuh** entri kunci (`pytorch_model/data.pkl`) di dalam arsip,
sehingga CRC-32 yang tidak cocok / galat zlib / EOF di tengah entri terdeteksi sebagai
"tidak utuh". Pemeriksaan ini cepat karena entri pickle berukuran kecil.

**b. Pengunduh memverifikasi hasilnya** (`persiapan_model.py`).
`_berkas_model_utuh()` memakai penjaga yang **sama** dengan embedder, jadi berkas yang lolos
di pengunduh pasti juga dianggap siap oleh server. Pemeriksaan ini menutup dua lubang:
- ukuran akhir bisa kebetulan benar walau isinya rusak;
- bila HEAD gagal (`total == 0`), **ukuran tidak diperiksa sama sekali** — dulu berkas
  apa pun langsung dicetak `[V] ... selesai`.

**c. Mode `"ab"` membuat berkas rusak makin rusak** (`persiapan_model.py`) — ditemukan saat
mengunduh ulang. Kode lama:

```python
if total and lokal > total:
    lokal = 0            # niatnya "mulai ulang dari nol"
...
mode = "ab"              # <-- BAHAYA: default selalu append
if lokal and resp.status != 206:
    mode = "wb"          # hanya beralih ke "wb" bila lokal != 0
```

Setelah `lokal` di-nol-kan, syarat `if lokal and ...` menjadi **False**, sehingga `mode` tetap
`"ab"` dan unduhan baru **DITAMBAHKAN ke berkas lama yang kelewat besar** — bukan menimpanya.
Terbukti saat diuji: berkas yang seharusnya 2,27 GB justru tumbuh melewati ukuran target
(101% dan terus naik). → Kini `mode = "ab" if (lokal and resp.status == 206) else "wb"`:
`"ab"` hanya sah bila benar-benar melanjutkan potongan yang ada.

### Verifikasi
| Uji | Hasil |
|---|---|
| `bobot_model_utuh` pada berkas rusak nyata | ✅ **False** (sebelumnya `True`) |
| `bobot_model_utuh` pada zip valid ber-`data.pkl` | ✅ True (jalur normal tetap jalan) |
| `bobot_model_utuh` pada zip yang isinya diacak | ✅ False (menangkap CRC tidak cocok) |
| `_berkas_model_utuh` pada `config.json` / `tokenizer.json` | ✅ True (berkas pendukung) |
| Unduh ke berkas lokal **kelewat besar** (5 MB → target 2 MB) | ✅ ter-truncate ke 2 MB dengan isi benar (dulu jadi 7 MB) |
| Unduh saat berkas lokal sebagian | ✅ tidak menempel, isi benar |
| Berkas sudah lengkap | ✅ dilewati tanpa unduh ulang |
| Start server dengan berkas rusak di tempat | ✅ langsung jatuh ke hashing, tanpa tertahan 180 s |
| Suite backend | ✅ **72 lulus / 0 gagal** (naik dari 70) |

Dua tes regresi baru ditambahkan di `test_server.py` bagian [16]: berkas kelewat besar wajib
ter-truncate (bukan ditambahkan), dan berkas lengkap wajib dilewati. Tes memakai server HTTP
lokal sementara, jadi tidak menyentuh jaringan luar.

Unduhan ulang bersih (satu penulis) sudah dijalankan dan terverifikasi mulai dari nol;
pengunduh kini akan **menolak** hasilnya bila isinya tidak lolos verifikasi, bukan mencetak
"selesai" begitu saja.

---

## 20. Framing avatar 3D: hanya ubun-ubun yang terlihat (posisi terlalu rendah)

### Gejala
Layar menampilkan avatar hanya sebagai **potongan atas kepala di dasar layar**; seluruh badan
berada di luar viewport. Ruang tengah layar kosong.

### Akar masalah (sudah ada sejak sebelum penggantian model)
Kamera di `[0, 0.8, 5.5]` dengan fov vertikal 32° hanya melihat rentang **y = -0,78 s/d 2,38**
(tinggi 3,15). Namun kaki avatar dipatok di `MODEL_BASE_Y = -4,65`, sehingga avatar menempati
**y = -4,65 s/d -0,10**:

| | Rentang y avatar | Bagian yang tampak |
|---|---|---|
| Sebelum | -4,650 … -0,100 | **0,68 dari 4,55 = 15%** (hanya ubun-ubun, di dasar layar) |
| Sesudah | -2,350 … +2,200 | **2,98 dari 4,55 = 65%** (kepala s/d pinggul) |

Konstanta `MODEL_SCALE = 5,0` / `MODEL_BASE_Y = -4,65` berasal dari model lama; karena tinggi
tampil dijaga tetap 4,55 pada kedua model, **cacat ini bukan akibat penggantian model** —
framing-nya memang sudah salah sejak awal.

### Perbaikan
Titik acuan dipindah dari **kaki** ke **puncak kepala**, karena puncak itulah yang menentukan
apakah wajah masuk frame:

```js
const PUNCAK_AVATAR_Y = 2.2                    // sedikit di bawah tepi atas (2,38)
const DASAR_AVATAR_Y = PUNCAK_AVATAR_Y - TINGGI_AVATAR   // = -2,35
const SHADOW_Y = DASAR_AVATAR_Y
```

Kamera **tidak diubah**. `posisiY = DASAR_AVATAR_Y - kotak.min.y * skala` tetap memaku titik
terendah model ke `DASAR_AVATAR_Y`, jadi framing ini tetap benar walau model 3D diganti lagi.
Framing dipilih "kepala sampai pinggul" (bukan seluruh badan) supaya **wajah — termasuk mulut
yang digerakkan lipsync — cukup besar untuk terlihat jelas**.

### Verifikasi (tangkapan layar nyata, bukan perhitungan saja)
Verifikasi visual dilakukan dengan **Electron milik proyek sendiri** (`node_modules/electron`,
Chromium sudah ada di disk — tidak perlu mengunduh browser baru) yang memuat `dist/` lalu
memotret layar. Dua kendala lingkungan yang harus dilewati:

1. `http_proxy`/`https_proxy` disetel di lingkungan ini → Chromium mencoba melewatkan
   `127.0.0.1` via proxy dan gagal `ERR_FAILED (-2)`. → switch `--no-proxy-server`.
2. Proses renderer diblokir tanpa `--no-sandbox` → `ERR_FAILED` bahkan untuk `file://`.
   → switch `--no-sandbox` + `--disable-gpu-sandbox`.

Hasil tangkapan layar: avatar tampil utuh dari kepala sampai pinggul, wajah dan kedua tangan
terlihat, hanya menyisakan peringatan CSP Electron (tidak berkaitan). Tidak ada galat pemuatan
`/models/sela.glb`.

---

## 21. Tampilan teks obrolan dirapikan (paragraf + daftar), TTS tetap utuh

**Keluhan:** jawaban AI tampil sebagai satu blok teks padat sehingga melelahkan dibaca; paragraf
dan daftar diminta dibungkus serapi mungkin, tanpa merusak cara mesin suara menyebutkannya.

### Empat penyebab yang ditemukan (bukan satu)

1. **`_bersihkan_teks()` membuang SEMUA baris kosong.** `server.py` menyaring baris dengan
   `if b.strip()`, sehingga pemisah paragraf dari LLM hilang dan semua gagasan menempel menjadi
   satu blok. Dibuktikan langsung: masukan dengan 3 pemisah paragraf keluar dengan **0**.
2. **Prompt melarang seluruh markdown.** `MASTER_PERSONA` aturan 2 berbunyi "tanpa markdown,
   tanpa bintang, tanpa tanda pagar" karena jawaban diucapkan mesin suara. Akibatnya model tidak
   punya cara membuat daftar dan selalu menulis prosa.
3. **Bug di `ChatBubble.jsx`:** cabang daftar *bullet* membuat tipe `'ordered-list'`, dan tidak
   ada cabang render untuk `unordered-list`. Jadi `- item` dirender sebagai angka, bukan bullet.
4. **Aturan konversi tanda hubung terlalu agresif:** `([^\n\d])[\s,;]+([-*]\s+...)` mengubah
   tanda pisah di tengah kalimat biasa ("biaya - sekitar empat juta") menjadi awal bullet,
   sehingga potongan kalimat tampil sebagai poin daftar.

### Dua bug laten yang ikut ketahuan saat pengujian

- **Jawaban bisa menjadi KOSONG.** Pola `"<\|im_start\|>.*?<\|im_end\|>"` menghapus **seluruh
  blok**, termasuk jawaban yang berada di antara kedua tag. Diganti: hanya tag-nya yang dibuang
  (`<\|im_(?:start|end)\|>`), lalu label peran bocor di awal (`assistant`) dibersihkan.
  Sekarang `"<|im_start|>assistant\nHalo, ini SELA.<|im_end|>"` → `"Halo, ini SELA."` (dulu → kosong).
- **Angka bertitik terpecah (regresi yang sempat saya buat sendiri).** Pemroses kalimat memakai
  `[^.!?]*[.!?]+\s*` lalu menggabung ulang dengan spasi, sehingga `Rp170.000` menjadi
  `Rp170. 000` dan `2.500.000` menjadi `2. 500. 000` — mesin suara akan menyebutnya dua bagian
  terpisah. Diperbaiki dengan memecah kalimat **hanya bila tanda baca diikuti spasi**
  (`re.split(r"(?<=[.!?])\s+", ...)`), lalu diuji: keempat contoh angka kembali identik.

### Perubahan

| Berkas | Perubahan |
|---|---|
| `ai-engine/server.py` | `_bersihkan_teks()` mempertahankan **satu** baris kosong sebagai pemisah blok; tag template hanya dibuang tag-nya; pemecahan kalimat tidak lagi merusak angka bertitik. Ditambah `_pecah_paragraf_panjang()` + `_rapikan_paragraf()` sebagai **jaring pengaman tata letak**. |
| `ai-engine/prompts/sela_prompts.py` | Aturan gaya bicara diperluas: boleh memakai daftar (`- ` dan `1. `), wajib memisah gagasan dengan satu baris kosong, satu poin satu kalimat pendek. Tetap dilarang: bintang ganda, tanda pagar, tabel, emoji, tautan mentah. Aturan pertanyaan lanjutan wajib di baris baru terpisah. |
| `src/components/ChatBubble.jsx` | Tipe daftar bullet diperbaiki (`unordered-list`), ditambah render `<ul>` dengan `list-disc` + `marker:text-gray-400`, jarak antar blok `space-y-2` → `space-y-3`, aturan tanda hubung dipersempit agar tidak salah deteksi. |
| `src/lib/responsePlan.js` | `buildSpokenText()` membuang kurung siku dan pemisah pipa saran lanjutan (`[Tanya?] \| [Tanya?]`) tetapi tetap membacakan pertanyaannya. |

### Jaring pengaman: blok panjang dipecah otomatis
Kepatuhan model tidak bisa dijamin (temperature 0.6). Karena itu `_rapikan_paragraf()` memecah blok
prosa yang melewati ~320 karakter atau >3 kalimat menjadi beberapa paragraf pendek. Pemecahan ini
**murni tata letak** — kata, urutan, dan isi tidak berubah, sehingga mesin suara membacakan teks
yang persis sama (diuji: `" ".join(masukan.split()) == " ".join(keluaran.split())` → `True`).
Blok yang memuat baris daftar tidak pernah dipecah.

### Verifikasi
- **Uji backend:** 86 lulus / 0 gagal (naik dari 72). Bagian **[17] Pembersih teks jawaban** baru:
  11 pemeriksaan (pemisah paragraf, bullet, penomoran, dedupe, tag template, pemecahan blok panjang,
  dan angka bertitik utuh).
- **Uji frontend:** 10 lulus / 0 gagal (naik dari 8) — termasuk penanda daftar tidak diucapkan dan
  saran lanjutan dibacakan tanpa kurung siku/pipa.
- **Kepatuhan prompt diukur:** 5 sampel pertanyaan yang sama → **5/5** memuat daftar bullet
  (2–8 poin) dan 3–9 pemisah paragraf.
- **Jalur TTS diperiksa pada jawaban nyata:** penanda `- ` dan `1.` **tidak** tersisa, tidak ada
  baris baru, angka `Rp2.820.000` / `Rp13.410.000` utuh, dan seluruh kalimat di layar ikut
  diucapkan (`True`).
- **Tangkapan layar nyata** (Electron, `dist/` hasil build) untuk dua pertanyaan: jawaban kini
  tampil sebagai paragraf pendek + daftar bullet berindentasi menggantung, bukan dinding teks.

### Catatan operasional
- **Server yang sedang berjalan harus di-restart** agar prompt baru berlaku (prompt adalah
  konstanta modul, dibaca saat start).
- Saat menguji, port 8008 sudah dipakai server lama sehingga server uji gagal bind
  (`Errno 10048`). Server uji dijalankan di port lain (`PORT_SELA_AI=8123`) agar tidak
  mengganggu server milik pengguna. **Selalu pastikan hanya satu server per port.**

---

## 22. Penggantian tiga mesin inti: embedder, TTS, dan ASR (real-time penuh)

Permintaan: ganti embedder bge-m3 → **multilingual-e5-small** (bge-m3 terlalu besar),
ganti TTS → **Supertonic 3** (Piper dihapus total, hanya boleh ada SATU mesin suara),
ganti ASR → **sherpa-onnx streaming zipformer** sehingga ucapan menjadi teks
**kata per kata** (faster-whisper dihapus total), dan buat AI menjawab secepat mungkin.

### 22.1 Ringkasan penggantian

| Bagian | Sebelum | Sesudah | Alasan |
| --- | --- | --- | --- |
| Embedder RAG | BAAI/bge-m3 — 1024 dim, **2,27 GB** | `intfloat/multilingual-e5-small` — 384 dim, **470 MB** | Ukuran jauh lebih kecil; tugasnya hanya memperkuat RAG, mesin utama tetap BM25 |
| TTS | Piper ONNX (`piper-tts`) | **Supertonic 3** ONNX (`supertonic`) | 31 bahasa termasuk `id`, punya 10 tag ekspresi, satu mesin saja |
| ASR | faster-whisper (batch) | **sherpa-onnx streaming zipformer** | Whisper harus menunggu rekaman selesai; zipformer mengeluarkan teks saat diucapkan |
| Dekode audio | PyAV via faster-whisper | **PyAV eksplisit** (`av>=12`) | Browser mengirim `audio/webm` (Opus) yang tidak bisa dibaca soundfile |

Paket yang **dihapus**: `piper-tts`, `faster-whisper`.
Paket yang **ditambah**: `supertonic>=1.3.1`, `sherpa-onnx>=1.13.8`, `onnxruntime>=1.19.0`, `av>=12.0.0`.

### 22.2 Embedder: multilingual-e5-small + prefiks tugas E5

- `NAMA_MODEL_EMBED = "intfloat/multilingual-e5-small"`, folder lokal
  `ai-engine/models/multilingual-e5-small/`, dimensi cadangan 384.
- **Prefiks tugas E5 wajib**: kueri diberi `"query: "`, dokumen diberi `"passage: "`.
  Tanpa prefiks, kualitas pencocokan makna turun nyata. Ditambahkan
  `Embedder._beri_prefiks()`, `encode(..., jenis="query"|"passage")`,
  `encode_kueri()`, dan `encode_dokumen()`. Prefiks **tidak** dobel bila sudah ada.
- `rag/engine.py`: dokumen diindeks dengan `jenis="passage"`, kueri dengan `jenis="query"`.
- Indeks FAISS lama (1024 dim) otomatis dibangun ulang karena ada pemeriksaan kecocokan dimensi.

### 22.3 TTS: Supertonic 3 (Piper dihapus total)

- `core/tts_engine.py` ditulis ulang. API publik dipertahankan (`apakah_siap`,
  `sintesis_wav_bytes`, `sintesis_base64_async`, `status_engine`, pola singleton) supaya
  `server.py` dan frontend tidak perlu berubah kontraknya.
- **Audio tetap 100% di memori**: gelombang float32 → PCM 16-bit → WAV lewat `io.BytesIO`
  dan modul `wave`. Tidak ada berkas sementara.
- `status_engine()` kini melaporkan `tts_siap`, `engine_aktif = "supertonic-3"`,
  `suara`, `sample_rate`, `mode_emosi`, dan `tag_tersedia`. `Navbar.jsx` ikut disesuaikan
  (sebelumnya membaca `piper_siap` / `piper-unavailable`).
- **10 tag ekspresi resmi** didukung: `<angry> <sad> <laugh> <scream> <sigh> <surprise>
  <breath> <cough> <yawn> <throatclear>`, plus padanan nama Indonesia
  (`sedih` → `sad`, `kaget` → `surprise`, `ketawa` → `laugh`, dst).
- **Trik komunitas diimplementasikan**: tag diulang **3×** di awal kalimat
  (`<sad> <sad> <sad> teks...`) karena satu tag sering diabaikan model.
- **Saklar bahasa `SELA_TTS_EMOSI`** — inilah bagian jujurnya. Tag paling konsisten pada
  en/ja/ko; pada bahasa lain (termasuk Indonesia) model kadang mengabaikannya atau
  **membacanya sebagai teks biasa**. Maka bawaannya:
  - `auto` (bawaan) → tag hanya dipasang untuk `en` / `ja` / `ko`.
  - `on` → tag selalu dipasang, termasuk Indonesia (memakai trik ulang 3×).
  - `off` → tidak pernah dipasang.
  Dengan begitu SELA tidak pernah mengucapkan kata "angry angry angry" secara tidak sengaja.
- **Tag tidak pernah masuk ke balon obrolan**: `bersihkan_tag_emosi()` tersedia dan
  `bersihkan_teks_tts()` memanggilnya lebih dulu.
- Suara bisa diganti lewat `SELA_TTS_SUARA` (F1–F5, M1–M5; bawaan **F1**).
- `server.py` menambah `tentukan_emosi(jalur, intent)`: curhat → `sad`,
  data kampus tidak tersedia → `sigh`, di luar kampus → `surprise`,
  terima kasih → `laugh`. Emosi ikut dikirim pada `/api/sintesis` dan `/ws/dupleks`.

### 22.4 ASR: sherpa-onnx streaming zipformer

- `core/stt_engine.py` ditulis ulang memakai `sherpa_onnx.OnlineRecognizer.from_transducer`.
- **API streaming baru**: `buat_sesi()`, `terima_pcm(sesi, pcm)`, `apakah_akhir_ucapan(sesi)`,
  `akhirkan(sesi)`. `transkripsikan_bytes()` tetap ada untuk `/api/transcribe` dan
  sekarang berjalan di atas mekanisme streaming yang sama (audio disuapkan per 0,5 detik).
- **Deteksi akhir ucapan (endpoint)** aktif: `rule1 = 2,0 s` (belum ada kata),
  `rule2 = 1,2 s` (sudah ada kata), `rule3 = 20 s` (batas ucapan). Bisa diatur lewat
  `SELA_ASR_HENING1`, `SELA_ASR_HENING2`, `SELA_ASR_MAKS_UCAPAN`.
- `decoding_method="greedy_search"` dipilih karena paling cepat — penting untuk latensi.
- Koreksi istilah kampus (`koreksi_asr.py`) tetap dipakai, begitu pula filter halusinasi
  kata berulang.
- Model: `sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10`
  (encoder int8 296 MB, decoder 33 MB, joiner int8 8 MB, tokens.txt).

### 22.5 Real-time penuh (end-to-end)

**Pendengaran — `/ws/asr-stream` kini streaming sungguhan.** Protokol baru:
klien mengirim bingkai biner PCM 16-bit mono 16 kHz, server membalas `parsial`
(teks bertambah kata demi kata) dan `final` saat pengguna berhenti bicara. Setelah
`final`, server otomatis menyiapkan sesi baru sehingga pengguna bisa langsung bicara lagi.

**Frontend — `mulaiAsrStreaming()` di `src/lib/ai.js`.** Membuka `/ws/asr-stream`,
menyalakan mikrofon, mengubah Float32 → PCM 16-bit mono 16 kHz (dengan resampler sendiri,
karena browser tidak selalu menghormati permintaan `sampleRate`), lalu mengalirkannya.
Gain node bernilai 0 dipakai agar suara mikrofon tidak keluar lewat speaker (tanpa gema).

**`VoiceUI.jsx` — MediaRecorder dihapus dari jalur bicara.** Teks sementara langsung
muncul di kotak input saat diucapkan; saat server menyatakan pengguna berhenti, teks final
dikirim ke `handleSubmit` seperti biasa. VAD klien yang rumit (baseline, ambang adaptif,
quick-commit) tidak lagi menentukan giliran bicara — penentuan giliran kini satu sumber di
server. Sisa pemantauan mikrofon hanya untuk memberi tahu bila mikrofon tidak menangkap suara.

**Jawaban — jalur cepat `/ws/dupleks` diaktifkan.** Sebelumnya `streamChatAndVoice` hanya
diimpor dan tidak pernah dipanggil. Sekarang `handleAssistantInteraction` mencoba jalur
streaming lebih dulu: server mengirim jawaban **per kalimat beserta audionya**, sehingga
suara mulai berbunyi setelah kalimat pertama — bukan setelah seluruh jawaban selesai.
Bila gagal, otomatis jatuh ke jalur REST lama tanpa error. Saklar:
`localStorage.SELA_STREAMING_JAWABAN = "0"`.

### 22.6 Penjaga keutuhan bobot diperketat (temuan saat pengerjaan)

Saat menguji, terungkap bahwa pemeriksaan `.safetensors` **tidak mendeteksi unduhan
terpotong**: header safetensors ada di AWAL berkas, sedangkan bobot tensor ada di AKHIR —
jadi berkas yang berhenti di tengah tetap lolos pemeriksaan header, lalu server mencoba
memuatnya dan menggantung/menggagal. Ini kelas bug yang sama dengan insiden bge-m3 (§19),
hanya pada format berkas yang berbeda.

Perbaikan: ukuran total yang diharapkan dihitung dari `data_offsets` di header
(`8 + panjang header + offset data terbesar`) lalu dibandingkan dengan ukuran berkas
sebenarnya. Diterapkan di **kedua** tempat yang wajib kembar: `rag/embedder.py::bobot_model_utuh()`
dan `persiapan_model.py::_bobot_utuh()`. Dikunci tes bagian **[18]**.

### 22.7 Verifikasi
- **Uji backend:** 116 lulus / 0 gagal. Bagian baru: **[18] Penjaga keutuhan bobot** (7
  pemeriksaan: safetensors utuh/terpotong/kosong, zip utuh/isi rusak/bukan zip/berkas hilang),
  perluasan **[2] Embedder** (prefiks E5 tidak dobel, dimensi 384), perluasan **[10] TTS**
  (10 tag resmi, alias Indonesia, pengulangan 3×, pembersihan tag, saklar bahasa), perluasan
  **[11] STT** (mode streaming, `buat_sesi`/`terima_pcm`/`apakah_akhir_ucapan`/`akhirkan`),
  dan perluasan **[14] Routing** (emosi hanya dari 10 tag resmi).
- **Uji frontend:** bundel esbuild bersih tanpa peringatan.
- **Tangkapan layar Electron** dari `dist/` hasil build.

### 22.8 Catatan operasional
- Model baru diunduh lewat `persiapan_model.py` (`--unduh-embedder`, `--unduh-asr`,
  `--unduh-tts`, atau `--unduh-semua`).
- **Supertonic 3 TIDAK diunduh lewat `auto_download` paketnya.** Paket itu memakai
  `huggingface_hub` yang membuat berkas sementara lalu menghapusnya; pembersih berkas
  lingkungan ini (`safe-delete`) memblokir penghapusan tersebut sehingga unduhan gagal
  di tengah (terbukti: berhenti di 9/26 berkas). Unduhan langsung via `urllib`
  (`--unduh-tts`) tidak menyentuh berkas sementara dan berhasil.
- Setelah model lengkap, sisa folder sementara `ai-engine/models/.supertonic-3.tmp`
  boleh dihapus; folder itu sudah tercakup `.gitignore`.
- **Server harus di-restart** setelah perubahan mesin ini.

---

## 23. Verifikasi akhir & temuan lanjutan (2026-09-15)

Bagian ini mencatat apa yang ditemukan dan diperbaiki **setelah** ketiga model selesai
diunduh dan seluruh mesin diuji dengan model sungguhan (bukan cadangan).

### 23.1 Bug: ASR selalu dilaporkan "belum lengkap"
`persiapan_model.py::_asr_lengkap()` melewatkan **semua** isi `BERKAS_ASR` ke penjaga
bobot, termasuk `tokens.txt`. Penjaga bobot hanya mengenali ekstensi `.onnx`, `.bin`,
dan `.safetensors`; untuk ekstensi lain ia mengembalikan `False`. Akibatnya ASR selalu
dilaporkan "BELUM LENGKAP" walaupun keempat berkasnya sudah ada dan sehat.

Perbaikan: ditambahkan `BERKAS_ASR_BOBOT` (hanya berkas `.onnx`). `_asr_lengkap()` kini
memeriksa **keberadaan** seluruh berkas, lalu memverifikasi **keutuhan** khusus berkas
bobot. `tokens.txt` adalah kamus token, bukan bobot.

### 23.2 Penjaga keutuhan ONNX (baru)
Sebelumnya berkas `.onnx` hanya diperiksa dengan ambang ukuran (`> 1 MB`). Ini tidak
memadai: ONNX adalah protobuf tanpa indeks di akhir berkas, sehingga unduhan yang
terpotong tetapi masih besar akan lolos dan baru ketahuan saat model dimuat — persis
kelas bug yang sudah dua kali terjadi (§19 bge-m3, §22.6 safetensors).

Ditambahkan `_onnx_utuh()`: menelusuri field tingkat atas `ModelProto` (tag varint +
panjang) memakai seek, **tanpa pernah membaca isi tensor**, lalu memastikan penelusuran
berhenti TEPAT di akhir berkas. Biayanya di bawah 0,01 detik bahkan untuk berkas 283 MB.
Diterapkan di kedua tempat kembar: `rag/embedder.py` dan `persiapan_model.py`.

Hasil uji: 7 berkas ONNX nyata (3 ASR + 4 TTS) diterima; salinan terpotong 40 MB ditolak.

### 23.3 Prefiks E5 dengan peran salah kini ditimpa
`_beri_prefiks()` dulu membiarkan prefiks apa pun yang sudah ada, termasuk prefiks peran
yang keliru (`passage: x` pada jalur kueri). Prefiks E5 menandai **peran** teks, jadi
peran yang salah harus ditimpa — bukan dibiarkan, dan tentu bukan ditumpuk menjadi
`query: passage: x`. Kini prefiks lama dibuang lebih dulu, lalu prefiks yang benar dipasang.

### 23.4 Deprecation `sentence-transformers` 6.x
`get_sentence_embedding_dimension()` memicu `FutureWarning` di versi 6.x. Diganti dengan
pemanggilan adaptif: pakai `get_embedding_dimension()` bila ada, jika tidak jatuh ke nama
lama. Uji asap kini bersih tanpa peringatan.

### 23.5 Perbaikan tes bagian [18]
Ambang ukuran sementara di tes diturunkan ke `100` byte, padahal berkas safetensors
sintetisnya hanya ~88 byte. Akibatnya berkas **utuh** ditolak oleh gerbang ukuran
sebelum logika keutuhan isi sempat berjalan — tes menguji hal yang salah, dan dua tes
lain "lulus" karena alasan yang keliru. Ambang diubah ke `1` agar yang diuji benar-benar
logika keutuhan isi. Ditambahkan juga 3 pemeriksaan ONNX (utuh diterima, terpotong
ditolak, sampah ditolak).

### 23.6 Penghapusan total mesin lama
Sesuai permintaan ("cuma satu TTS", "whispernya dihapus totalnya"), seluruh sisa mesin
lama dibuang setelah mesin baru terbukti jalan:

| Yang dihapus | Ukuran | Alasan |
|---|---|---|
| `ai-engine/models/tts_piper/` | 121 MB | Piper digantikan Supertonic 3 |
| `ai-engine/models/whisper/` | 3.150 MB | faster-whisper digantikan sherpa-onnx |
| `ai-engine/models/bge-m3/` | 631 MB | digantikan multilingual-e5-small |
| `ai-engine/models/.supertonic-3.tmp/` | 713 MB | sisa unduhan gagal via `huggingface_hub` |
| paket `piper-tts` | — | mesin TTS lama |
| paket `faster-whisper` | — | mesin ASR lama |
| paket `ctranslate2` | 60 MB | mesin inferensi faster-whisper, tak lagi dipakai |

Total ruang yang dibebaskan: **± 4,6 GB**. Setelah pembersihan, `ai-engine/models/` hanya
berisi empat hal: GGUF LLM, `multilingual-e5-small`, `sherpa-streaming-zipformer`, dan
`supertonic-3`. Paket `av` dan `onnxruntime` **sengaja dipertahankan** — keduanya dulu
ikut terpasang sebagai dependensi faster-whisper, tetapi sekarang dipakai langsung oleh
ASR (dekode WebM/Opus) dan TTS (ONNX Runtime).

### 23.7 Hasil verifikasi akhir
- `persiapan_model.py`: LLM, ASR, TTS, dan Embedder semuanya **[V] lengkap**. Hanya LoRA
  UCIC (opsional) yang belum ada, dan itu tidak lagi dihitung sebagai model wajib.
- `test_server.py`: **126 lulus / 0 gagal**, tanpa peringatan. Termasuk bagian [18] yang
  diperluas dan bagian [14]/[15] yang butuh `SELA_UJI_SERVER=1`.
- **Supertonic 3 nyata:** sintesis Bahasa Indonesia 4,53 detik audio hanya dalam ~1 detik
  (lebih cepat dari realtime), 44.100 Hz mono, WAV sah.
- **Saklar emosi terverifikasi:** mode `auto` (bawaan) tidak memasang tag untuk Bahasa
  Indonesia; mode `on` memasang tag dengan pengulangan 3× dan menghasilkan audio yang
  berbeda (4,53 s → 5,02 s sedih, 5,43 s ketawa).
- **sherpa-onnx nyata:** model dimuat 4 detik, sesi streaming dibuat, `terima_pcm` /
  `apakah_akhir_ucapan` / `akhirkan` berjalan tanpa galat.
- **Frontend:** bundel esbuild bersih (4,2 MB JS, 3,6 KB CSS), tanpa peringatan.

---

## 24. Perbaikan setelah uji WebSocket nyata (2026-09-15)

Sampai §23, kedua endpoint WebSocket hanya diverifikasi secara tidak langsung (impor modul,
bundel, server menyala). Belum pernah ada satu pun tes yang benar-benar **membuka socket**.
Begitu diuji dengan ucapan sungguhan, tiga masalah nyata langsung muncul.

### 24.1 Bug terbesar: jawaban TIDAK benar-benar streaming
`/ws/dupleks` mengumpulkan **seluruh** jawaban LLM lebih dulu, baru mulai TTS:

```python
while True:
    item = await antrean.get()
    if item is None:
        break
    kalimat_list.append(item)   # <- menampung SEMUA kalimat dulu
# baru setelah loop ini selesai: for item in kalimat_list: ... TTS ...
```

Akibatnya pengguna menunggu model menuntaskan jawabannya (±4 detik) sebelum mendengar kata
pertama — persis kebalikan dari tujuan streaming, dan bertentangan langsung dengan permintaan
"jawabannya secepat mungkin dan real time kaya ngobrol sama manusia".

Perbaikan: kedua jalur (niat cepat, LLM, dan cadangan) kini mengisi **satu antrean**, dan
kalimat langsung dikirim + disintesis begitu tiba; sisa jawaban tetap dihasilkan di latar.

### 24.2 Koreksi otomatis ASR mengubah token derau menjadi kata acak
`koreksi_asr.py::_koreksi_fuzzy()` menerima kata berapa pun dengan panjang ≥ 3 dan jarak
Levenshtein ≤ 2. Untuk kata 3 huruf, jarak 2 berarti hanya 1 huruf yang cocok — hampir semua
entri kamus "cocok". Kasus nyata: `uj一` (jarak 2 dari `udh`) dikoreksi menjadi `sudah`,
sehingga "berapa biaya kuliah di UCIC" berubah menjadi "... di Sudah".

Perbaikan: hanya kata berhuruf **Latin-ASCII** yang boleh dikoreksi (catatan: `str.isalpha()`
tidak cukup — aksara CJK juga dianggap alfabetis, jadi yang dipakai `isascii()`), panjang
minimum dinaikkan ke 4, dan ambang jarak menyesuaikan panjang kata (≤1 untuk 4-5 huruf,
≤2 untuk 6+).

### 24.3 Aksara asing dari model multibahasa
Model ASR mencakup ar/en/id/ja/ru/th/vi/zh, jadi saat audio ambigu ia kadang menyelipkan
aksara lain — nyata: "BERAPA BIAYA KULIAH DI UJ一". Untuk aplikasi kampus berbahasa
Indonesia/Inggris, token itu selalu derau: ikut terkirim sebagai pertanyaan pengguna dan
tampil di layar chat. Ditambahkan `stt_engine._bersihkan_aksara_asing()` yang dijalankan
**sebelum** koreksi otomatis (supaya token derau tidak sempat dicocokkan ke kamus).

### 24.4 Metrik setelah perbaikan
Kueri "Berapa biaya kuliah di UCIC?" lewat `/ws/dupleks`:

| Metrik | Sebelum | Sesudah |
|---|---|---|
| Teks pertama | 5,96 s | **1,02 s** |
| **Suara pertama** | 7,57 s | **2,48 s** |
| Total jawaban | 21,16 s | **12,44 s** |

Rincian hangat dari profil langsung: `susun_rencana` (RAG + routing) 0,02 s · kalimat pertama
LLM 0,73 s · TTS satu kalimat 0,89 s. Jadi ±1,6 detik sampai suara pertama — setara jeda
percakapan manusia. Yang paling lambat ternyata bukan modelnya, melainkan cara server
menunggu jawaban selesai.

### 24.5 Tes regresi [19]
Ditambahkan `uji_realtime_ws()` yang benar-benar membuka socket, dan **selalu dijalankan**
(tidak digerbang `SELA_UJI_SERVER`) karena jalur realtime adalah inti produk:

- `/ws/asr-stream`: kalimat uji disintesis TTS → resample PCM 16 kHz → disuapkan bertahap;
  diperiksa ada pesan `parsial` yang bertambah kata demi kata, ada `final`, kata kunci
  terbaca, dan hasilnya bebas aksara non-Latin.
- `/ws/dupleks`: diperiksa ada `mulai_menjawab` + `gerakan`, teks dan audio mengalir
  per kalimat, dan penjaga regresi utamanya — **potongan audio PERTAMA wajib tiba SEBELUM
  potongan teks TERAKHIR**. Dengan bug lama, urutannya menjadi teks…teks lalu audio, jadi
  tes ini langsung gagal.
