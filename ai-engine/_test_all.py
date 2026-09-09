"""Test komprehensif seluruh fitur AI offline (tanpa FastAPI)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_rag_intents():
    from mesin_rag import MesinRagOffline
    rag = MesinRagOffline()
    print("=== TEST RAG INTENTS ===")
    tests = [
        ("halo", "sapaan"),
        ("siapa kamu", "identitas"),
        ("terima kasih", "terima_kasih"),
        ("saya bingung memilih jurusan", "curhat"),
        ("saya ragu bisa diterima", "curhat"),
        ("bye", "penutup"),
    ]
    for query, expected_intent in tests:
        result = rag.deteksi_intent_percakapan(query)
        if result:
            status = "OK" if result["intent"] == expected_intent else "FAIL"
            print(f"  [{status}] '{query}' -> {result['intent']}")
        else:
            print(f"  [FAIL] '{query}' -> None (expected {expected_intent})")

def test_rag_search():
    from mesin_rag import MesinRagOffline
    rag = MesinRagOffline()
    print("\n=== TEST RAG SEARCH ===")
    queries = [
        "biaya kuliah teknik informatika",
        "fakultas di ucic",
        "lokasi kampus",
        "beasiswa",
        "cara mendaftar",
    ]
    for q in queries:
        docs = rag.cari_relevan(q)
        print(f"  [OK] '{q}' -> {len(docs)} docs")
        if docs:
            print(f"       Top: {docs[0]['judul']} (skor: {docs[0]['skor']})")

def test_multi_turn():
    from mesin_rag import MesinRagOffline
    rag = MesinRagOffline()
    print("\n=== TEST MULTI-TURN CONTEXT ===")
    riwayat = [{"role": "user", "text": "Berapa biaya kuliah S1 Teknik Informatika?"}]
    enriched = rag.perkaya_kueri_dengan_konteks("Lalu syaratnya apa?", riwayat)
    print(f"  Query: 'Lalu syaratnya apa?'")
    print(f"  Enriched: '{enriched}'")
    assert "teknik informatika" in enriched.lower()
    print("  [OK] Context linking berhasil!")

def test_user_memory():
    from pengenal_user import PengenalUser
    pu = PengenalUser()
    pu.reset()
    print("\n=== TEST USER MEMORY ===")
    assert not pu.apakah_dikenal()
    print("  [OK] Awalnya tidak dikenal")
    
    nama = pu.ekstrak_nama_dari_pesan("halo nama saya Andi")
    assert nama == "Andi"
    print(f"  [OK] Ekstraksi nama: '{nama}'")
    
    pu.simpan_nama("Andi")
    assert pu.apakah_dikenal()
    print(f"  [OK] Nama disimpan: {pu.nama_user}")
    
    konteks = pu.dapatkan_konteks_user()
    assert "Andi" in konteks
    print(f"  [OK] Konteks user: '{konteks[:50]}...'")
    
    pu.reset()

def test_auto_correct():
    from koreksi_asr import KoreksiAsr
    k = KoreksiAsr()
    print("\n=== TEST AUTO-CORRECT ASR ===")
    tests = [
        ("gmn cara daftar maba di ucic", "Gimana"),
        ("brapa biyaya uktinya", "Berapa biaya"),
        ("halo halo sela", "Halo"),
        ("dimna letak kampus ucic di cerbon", "Dimana"),
    ]
    for teks, expected_prefix in tests:
        hasil = k.koreksi_teks(teks)
        status = "OK" if hasil.startswith(expected_prefix) else "FAIL"
        print(f"  [{status}] '{teks}'")
        print(f"         -> '{hasil}'")

def test_web_search():
    from pencari_web import PencariWeb
    p = PencariWeb()
    print("\n=== TEST WEB SEARCH DETECTION ===")
    tests = [
        ("siapa presiden indonesia sekarang", True),
        ("siapa walikota cirebon", True),
        ("berita terbaru", True),
        ("berapa biaya kuliah UCIC", False),
        ("halo sela", False),
    ]
    for query, expected in tests:
        result = p.apakah_perlu_web_search(query)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{query}' -> {result}")

def test_tts_omnivoice():
    from sintesis_suara import SintesisSuaraOffline
    print("\n=== TEST TTS STATUS ===")
    tts = SintesisSuaraOffline()
    status = tts.status_engine()
    print(f"  OmniVoice siap: {status.get('omnivoice_siap')}")
    print(f"  Cache audio: {status.get('jumlah_cache_audio')}")
    print(f"  Engine aktif: {status.get('engine_aktif')}")
    assert status.get("omnivoice_siap")
    print("  [OK] OmniVoice siap!")

if __name__ == "__main__":
    test_rag_intents()
    test_rag_search()
    test_multi_turn()
    test_user_memory()
    test_auto_correct()
    test_web_search()
    test_tts_omnivoice()
    print("\n" + "=" * 60)
    print("SEMUA TEST FITUR SELESAI!")
    print("=" * 60)
