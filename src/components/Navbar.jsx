import { useState, useEffect } from 'react'

const IconSun = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="5" />
    <path strokeLinecap="round" d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M17.66 6.34l1.42-1.42" />
  </svg>
)

const IconMoon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
  </svg>
)

// Badge status engine TTS — polling /api/status-tts setiap 15 detik
function TtsStatusBadge() {
  const [status, setStatus] = useState(null) // null = loading awal, {} = data

  useEffect(() => {
    const cekStatus = async () => {
      try {
        const r = await fetch('/api/status-tts', { signal: AbortSignal.timeout(4000) })
        if (r.ok) setStatus(await r.json())
      } catch (_) {}
    }
    cekStatus()
    const interval = setInterval(cekStatus, 15000) // polling tiap 15 detik
    return () => clearInterval(interval)
  }, [])

  if (!status) return null // Belum ada data

  if (status.omnivoice_siap || status.omnivoice_voice_design) {
    return (
      <div
        id="tts-status-badge"
        title={status.pesan_status || "OmniVoice Voice Design Aktif (Karakter Perempuan Imut, Ceria & Alami)"}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-100 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-600"
      >
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-[9px] font-bold text-emerald-700 dark:text-emerald-300 uppercase tracking-wide hidden sm:inline">
          OmniVoice
        </span>
      </div>
    )
  }

  if (status.omnivoice_gagal) {
    return (
      <div
        id="tts-status-badge"
        title="OmniVoice gagal diinisialisasi"
        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-100 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-600"
      >
        <span className="w-2 h-2 rounded-full bg-amber-500" />
        <span className="text-[9px] font-bold text-amber-700 dark:text-amber-300 uppercase tracking-wide hidden sm:inline">
          TTS Error
        </span>
      </div>
    )
  }

  // OmniVoice sedang memuat
  return (
    <div
      id="tts-status-badge"
      title="Memuat model OmniVoice..."
      className="flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-600"
    >
      <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
      <span className="text-[9px] font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide hidden sm:inline">
        Memuat AI...
      </span>
    </div>
  )
}

export default function Navbar({ onMenuClick, lang, setLang, theme, setTheme }) {
  const toggleLang = () => {
    if (setLang) setLang(lang === 'id' ? 'en' : 'id')
  }

  const toggleTheme = () => {
    if (setTheme) setTheme(theme === 'light' ? 'dark' : 'light')
  }

  return (
    <header className="flex items-center justify-between px-6 pt-5 pb-2">
      {/* Hamburger */}
      <button
        id="hamburger-btn"
        onClick={onMenuClick}
        className="w-10 h-10 flex flex-col justify-center gap-[5px] group"
        aria-label="Open menu"
      >
        <span className="block h-[2px] w-6 bg-gray-500 dark:bg-gray-400 rounded-full group-hover:bg-blue-500 transition-colors" />
        <span className="block h-[2px] w-6 bg-gray-500 dark:bg-gray-400 rounded-full group-hover:bg-blue-500 transition-colors" />
        <span className="block h-[2px] w-4 bg-gray-500 dark:bg-gray-400 rounded-full group-hover:bg-blue-500 transition-colors" />
      </button>

      {/* Logo */}
      <h1 className="text-xl font-bold tracking-widest text-gray-800 dark:text-gray-100 select-none">SELA</h1>

      <div className="flex items-center gap-2">
        {/* Badge status TTS engine */}
        <TtsStatusBadge />

        {/* Theme Toggle Shortcut */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 bg-white dark:bg-slate-900 shadow-sm hover:bg-gray-50 dark:hover:bg-slate-800 transition-all"
          aria-label="Toggle theme"
        >
          {theme === 'light' ? <IconMoon /> : <IconSun />}
        </button>

        {/* Lang Toggle Sidebar Shortcut */}
        <button
          onClick={toggleLang}
          className="px-2 py-1.5 text-xs font-bold rounded-lg border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 bg-white dark:bg-slate-900 shadow-sm hover:bg-gray-50 dark:hover:bg-slate-800 transition-all"
          aria-label="Toggle language"
        >
          {lang === 'id' ? 'ID' : 'EN'}
        </button>
      </div>
    </header>
  )
}
