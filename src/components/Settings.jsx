import { useState } from 'react'

function Toggle({ id, enabled, onChange }) {
  return (
    <button
      id={id}
      role="switch"
      aria-checked={enabled}
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-300 focus:outline-none
        ${enabled ? 'bg-blue-500' : 'bg-gray-200'}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-md
                    transform transition-transform duration-300
                    ${enabled ? 'translate-x-5' : 'translate-x-0'}`}
      />
    </button>
  )
}

function SectionHeader({ icon, label }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="text-blue-700">{icon}</span>
      <span className="text-[11px] font-bold uppercase tracking-widest text-gray-500">{label}</span>
    </div>
  )
}

import { t } from '../lib/translations'

export default function Settings({ onBack, scrolled, lang, setLang, theme, setTheme }) {
  const [notifications, setNotifications] = useState(true)
  const [incognito, setIncognito] = useState(false)
  const [langOpen, setLangOpen] = useState(false)

  const languages = [
    { value: 'id', label: t[lang].lang_id },
    { value: 'en', label: t[lang].lang_en }
  ]

  return (
    <div className="min-h-screen page-enter bg-[#f8faff] dark:bg-slate-950 transition-colors duration-200">
      {/* Top nav bar */}
      <header className={`sticky top-0 z-50 flex items-center justify-between px-6 pt-5 pb-4 border-b transition-colors duration-200 
        ${scrolled 
          ? 'bg-white/70 dark:bg-slate-900/70 backdrop-blur-md border-gray-200/50 dark:border-white/10 shadow-sm' 
          : 'bg-transparent border-transparent'}`}>
        <button
          id="settings-back-btn"
          onClick={onBack}
          className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:text-blue-700 transition-colors"
          aria-label="Go back"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <span className="text-base font-semibold text-gray-700 dark:text-gray-100 italic tracking-widest">SELA</span>
        <div className="w-5" /> {/* Spacer */}
      </header>

      {/* Content */}
      <div className="max-w-2xl mx-auto px-6 py-10">

        {/* Page title */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-semibold text-gray-800 dark:text-gray-100 mb-2">{t[lang].settings_title}</h1>
        </div>

        {/* ── GENERAL ── */}
        <section className="mb-8">
          <SectionHeader
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
              </svg>
            }
            label="General"
          />

          <div className="bg-white/80 dark:bg-slate-900/80 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm overflow-hidden divide-y divide-gray-100/80 dark:divide-white/5">
            {/* Language */}
            <div className="flex items-center justify-between px-5 py-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{t[lang].language}</p>
              </div>
              <div className="relative">
                <button
                  id="language-dropdown-btn"
                  onClick={() => setLangOpen(!langOpen)}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-slate-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm text-gray-600 dark:text-gray-300 hover:border-blue-300 transition-colors"
                >
                  {languages.find(l => l.value === lang)?.label}
                  <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${langOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {langOpen && (
                  <div className="absolute right-0 mt-1 w-44 bg-white dark:bg-slate-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-10 overflow-hidden animate-fade-in">
                    {languages.map((l) => (
                      <button
                        key={l.value}
                        id={`lang-option-${l.value}`}
                        onClick={() => { setLang(l.value); setLangOpen(false) }}
                        className={`w-full text-left px-4 py-2.5 text-sm transition-colors
                          ${lang === l.value ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-700'}`}
                      >
                        {l.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Notifications */}
            <div className="flex items-center justify-between px-5 py-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{t[lang].notifications}</p>
              </div>
              <Toggle id="notifications-toggle" enabled={notifications} onChange={setNotifications} />
            </div>
          </div>
        </section>

        {/* ── SECURITY ── */}
        <section className="mb-8">
          <SectionHeader
            icon={
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 1L3 5v6c0 5.52 3.84 10.74 9 12 5.16-1.26 9-6.48 9-12V5l-9-4z" />
              </svg>
            }
            label="Security"
          />

          <div className="bg-white/80 dark:bg-slate-900/80 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm overflow-hidden divide-y divide-gray-100/80 dark:divide-white/5">
            {/* 2FA */}
            <div className="flex items-center justify-between px-5 py-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{t[lang].clear_all_chats}</p>
              </div>
              <button
                id="clear-all-btn"
                className="px-5 py-2 rounded-xl bg-gray-800 dark:bg-slate-700 text-white text-sm font-semibold
                           hover:bg-gray-700 dark:hover:bg-slate-600 active:scale-95 transition-all duration-150"
              >
                {t[lang].delete}
              </button>
            </div>

            {/* Incognito Mode */}
            <div className="flex items-center justify-between px-5 py-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">Incognito Mode</p>
                <p className="text-xs text-gray-400 mt-0.5">Do not save chat history or personal data</p>
              </div>
              <Toggle id="incognito-toggle" enabled={incognito} onChange={setIncognito} />
            </div>
          </div>
        </section>

        {/* ── APPEARANCE ── */}
        <section className="mb-12">
          <SectionHeader
            icon={
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z" />
              </svg>
            }
            label="Appearance"
          />

          <div className="bg-white/80 dark:bg-slate-900/80 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm p-5">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-5">{t[lang].theme}</p>

            <div className="grid grid-cols-2 gap-4">
              {/* Light Aura */}
              <button
                id="theme-light-btn"
                onClick={() => setTheme('light')}
                className={`relative rounded-2xl border-2 overflow-hidden transition-all duration-200 text-left
                  ${theme === 'light' ? 'border-blue-500 shadow-md shadow-blue-100 dark:shadow-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}`}
              >
                {/* Preview */}
                <div className="h-24 bg-gradient-to-br from-gray-100 to-blue-50 p-3">
                  <div className="h-2 w-16 bg-gray-300 rounded-full mb-1.5" />
                  <div className="h-2 w-24 bg-gray-200 rounded-full mb-1.5" />
                  <div className="h-2 w-14 bg-gray-200 rounded-full" />
                </div>
                <div className="px-3 py-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-400">Light Aura</span>
                  {theme === 'light' && (
                    <span className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center">
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth={3} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                  )}
                </div>
              </button>

              {/* Midnight Blue */}
              <button
                id="theme-dark-btn"
                onClick={() => setTheme('dark')}
                className={`relative rounded-2xl border-2 overflow-hidden transition-all duration-200 text-left
                  ${theme === 'dark' ? 'border-blue-500 shadow-md shadow-blue-100 dark:shadow-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}`}
              >
                {/* Preview */}
                <div className="h-24 bg-gradient-to-br from-gray-900 to-blue-950 p-3">
                  <div className="h-2 w-16 bg-blue-800/60 rounded-full mb-1.5" />
                  <div className="h-2 w-24 bg-blue-900/50 rounded-full mb-1.5" />
                  <div className="h-2 w-14 bg-blue-900/50 rounded-full" />
                </div>
                <div className="px-3 py-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-400">Midnight Blue</span>
                  {theme === 'dark' && (
                    <span className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center">
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth={3} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                  )}
                </div>
              </button>
            </div>
          </div>
        </section>

        {/* Sign Out */}
        <div className="flex justify-center">
          <button
            id="sign-out-btn"
            className="flex items-center gap-2 px-8 py-3.5 rounded-full bg-gray-100 dark:bg-slate-800 text-gray-500 dark:text-gray-400
                       text-sm font-medium hover:bg-gray-200 dark:hover:bg-slate-700 hover:text-gray-700 dark:hover:text-gray-200
                       active:scale-95 transition-all duration-150 shadow-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v1" />
            </svg>
            {t[lang].logout}
          </button>
        </div>
      </div>
    </div>
  )
}
