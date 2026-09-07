import { useState } from 'react'
import { t } from '../lib/translations'

// ── SVG Icons ─────────────────────────────────────────────────────
const IconBack = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5M12 5l-7 7 7 7" />
  </svg>
)
const IconSearch = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <circle cx="11" cy="11" r="8" /><path strokeLinecap="round" d="M21 21l-4.35-4.35" />
  </svg>
)
const IconQuestion = () => (
  <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" />
    <path strokeLinecap="round" d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01" />
  </svg>
)
const IconChevron = ({ open }) => (
  <svg className={`shrink-0 w-4 h-4 text-gray-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" d="M19 9l-7 7-7-7" />
  </svg>
)
const IconMic = () => (
  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 1a4 4 0 014 4v6a4 4 0 01-8 0V5a4 4 0 014-4zm-1 18v3h2v-3a8.03 8.03 0 005.65-2.35l-1.41-1.41A6 6 0 0112 19a6 6 0 01-4.24-1.76L6.35 18.65A8.03 8.03 0 0011 21z" />
  </svg>
)
const IconShield = () => (
  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 1L3 5v6c0 5.52 3.84 10.74 9 12 5.16-1.26 9-6.48 9-12V5l-9-4z" />
  </svg>
)
const IconSettings = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.559.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)
const IconCreditCard = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <rect x="1" y="4" width="22" height="16" rx="2" />
    <line x1="1" y1="10" x2="23" y2="10" strokeLinecap="round" />
  </svg>
)
const IconCpu = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <rect x="9" y="9" width="6" height="6" />
    <line x1="9" y1="1" x2="9" y2="4" strokeLinecap="round" />
    <line x1="15" y1="1" x2="15" y2="4" strokeLinecap="round" />
    <line x1="9" y1="20" x2="9" y2="23" strokeLinecap="round" />
    <line x1="15" y1="20" x2="15" y2="23" strokeLinecap="round" />
    <line x1="20" y1="9" x2="23" y2="9" strokeLinecap="round" />
    <line x1="20" y1="14" x2="23" y2="14" strokeLinecap="round" />
    <line x1="1" y1="9" x2="4" y2="9" strokeLinecap="round" />
    <line x1="1" y1="14" x2="4" y2="14" strokeLinecap="round" />
  </svg>
)
const IconBug = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 01-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 011-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 011.52 0C14.51 3.81 17 5 19 5a1 1 0 011 1z" />
  </svg>
)
const IconMail = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
)
const IconChat = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.41-4.03 8-9 8a9.9 9.9 0 01-4.26-.96L3 20l1.14-3.42A7.96 7.96 0 013 12c0-4.41 4.03-8 9-8s9 3.59 9 8z" />
  </svg>
)
const IconBook = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
  </svg>
)

function FaqItem({ item, index }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-gray-100 dark:border-white/5 last:border-0">
      <button
        id={`faq-item-${index}`}
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50/50 dark:hover:bg-slate-800/40 transition-colors"
      >
        <span className="text-sm font-medium text-gray-700 dark:text-gray-200 pr-4">{item.q}</span>
        <IconChevron open={open} />
      </button>
      {open && (
        <div className="px-5 pb-4 animate-fade-in">
          <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{item.a}</p>
        </div>
      )}
    </div>
  )
}

export default function Help({ onBack, scrolled, lang = 'id', theme = 'light' }) {
  const [search, setSearch] = useState('')

  const FAQ = [
    { q: t[lang].q1, a: t[lang].a1 },
    { q: t[lang].q2, a: t[lang].a2 },
    { q: t[lang].q3, a: t[lang].a3 },
    { q: t[lang].q4, a: t[lang].a4 },
  ]

  const TOPICS = [
    { id: 'topic-voice',    icon: <IconMic />,        label: t[lang].topic_voice },
    { id: 'topic-privacy',  icon: <IconShield />,     label: t[lang].topic_privacy },
    { id: 'topic-settings', icon: <IconSettings />,   label: t[lang].topic_settings },
    { id: 'topic-billing',  icon: <IconCreditCard />, label: t[lang].topic_billing },
    { id: 'topic-ai',       icon: <IconCpu />,        label: t[lang].topic_ai },
    { id: 'topic-bug',      icon: <IconBug />,        label: t[lang].topic_bug },
  ]

  const CONTACTS = [
    { id: 'contact-email', icon: <IconMail />, title: t[lang].email_support,   subtitle: 'support@sela.ai',             badge: t[lang].reply_24h, badgeColor: 'bg-blue-100 text-blue-600' },
    { id: 'contact-chat',  icon: <IconChat />, title: t[lang].live_chat,       subtitle: t[lang].online_now,        badge: 'Online',       badgeColor: 'bg-green-100 text-green-600' },
    { id: 'contact-docs',  icon: <IconBook />, title: t[lang].documentation,   subtitle: t[lang].browse_guides,   badge: (lang === 'id' ? 'Mandiri' : 'Self-serve'),   badgeColor: 'bg-purple-100 text-purple-600' },
  ]

  const filtered = FAQ.filter(f =>
    f.q.toLowerCase().includes(search.toLowerCase()) ||
    f.a.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="min-h-screen page-enter bg-[#f8faff] dark:bg-slate-950 transition-colors duration-200 text-gray-800 dark:text-gray-100">
      <header className={`sticky top-0 z-50 flex items-center justify-between px-6 pt-5 pb-4 border-b transition-colors duration-200 
        ${scrolled 
          ? 'bg-white/70 dark:bg-slate-900/70 backdrop-blur-md border-gray-200/50 dark:border-white/10 shadow-sm' 
          : 'bg-transparent border-transparent'}`}>
        <button id="help-back-btn" onClick={onBack} className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:text-blue-700 transition-colors" aria-label="Go back">
          <IconBack />
        </button>
        <span className="text-base font-semibold text-gray-700 dark:text-gray-100 italic tracking-widest">SELA</span>
        <div className="w-5" />
      </header>

      <div className="max-w-2xl mx-auto px-6 py-10">

        {/* Hero */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-xl shadow-blue-300/40 dark:shadow-blue-900/30 mb-5">
            <IconQuestion />
          </div>
          <h1 className="text-4xl font-semibold text-gray-800 dark:text-gray-100 mb-2">{t[lang].help_center}</h1>
          <p className="text-sm text-gray-400 dark:text-gray-500 ">{t[lang].help_desc}</p>
        </div>

        {/* Search */}
        <div className="relative mb-8">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none"><IconSearch /></span>
          <input
            id="help-search-input"
            type="text"
            placeholder={t[lang].search_answers}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-12 pr-4 py-3.5 bg-white/80 dark:bg-slate-900/80 border border-gray-200 dark:border-white/10 rounded-2xl text-sm text-gray-700 dark:text-gray-100 placeholder-gray-400 outline-none shadow-sm
                       focus:ring-2 focus:ring-blue-200 dark:focus:ring-blue-900/40 focus:border-blue-300 dark:focus:border-blue-500 transition-all"
          />
        </div>

        {/* Quick Topics */}
        <div className="mb-8">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">{t[lang].quick_topics}</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {TOPICS.map((topic) => (
              <button
                key={topic.id} id={topic.id}
                className="flex items-center gap-2 px-4 py-3 bg-white/80 dark:bg-slate-900/80 border border-gray-100 dark:border-white/5 rounded-xl text-sm font-medium text-gray-600 dark:text-gray-300 shadow-sm hover:border-blue-200 dark:hover:border-blue-500/50 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-900/20 active:scale-95 transition-all"
              >
                <span className="text-blue-400 dark:text-blue-500">{topic.icon}</span>
                {topic.label}
              </button>
            ))}
          </div>
        </div>

        {/* FAQ */}
        <div className="mb-8">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
            {t[lang].faq_title}
            {search && <span className="ml-2 text-blue-400 normal-case tracking-normal font-normal">({filtered.length} {lang === 'id' ? 'hasil' : 'results'})</span>}
          </h2>
          <div className="bg-white/80 dark:bg-slate-900/80 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm overflow-hidden">
            {filtered.length > 0
              ? filtered.map((item, i) => <FaqItem key={i} item={item} index={i} />)
              : (
                <div className="px-5 py-8 text-center">
                  <p className="text-gray-400 text-sm">{lang === 'id' ? 'Tidak ada hasil untuk' : 'No results for'} "<strong>{search}</strong>"</p>
                  <p className="text-gray-300 text-xs mt-1">{lang === 'id' ? 'Coba kata kunci lain' : 'Try different keywords or browse topics above'}</p>
                </div>
              )
            }
          </div>
        </div>

        {/* Contact Support */}
        <div className="mb-8">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">{t[lang].contact_support}</h2>
          <div className="flex flex-col gap-3">
            {CONTACTS.map((c) => (
              <button
                key={c.id} id={c.id}
                className="flex items-center gap-4 bg-white/80 dark:bg-slate-900/80 border border-gray-100 dark:border-white/10 rounded-2xl px-5 py-4 shadow-sm text-left hover:border-blue-200 dark:hover:border-blue-500/30 hover:shadow-md hover:shadow-blue-50 dark:hover:shadow-black/20 active:scale-[0.99] transition-all group"
              >
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center text-blue-500 dark:text-blue-400 group-hover:bg-blue-100 dark:group-hover:bg-blue-900/50 transition-colors shrink-0">
                  {c.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">{c.title}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{c.subtitle}</p>
                </div>
                <span className={`shrink-0 text-[10px] font-semibold px-2.5 py-1 rounded-full ${c.badgeColor}`}>{c.badge}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center">
          <p className="text-xs text-gray-400">
            SELA v1.0.0 &nbsp;·&nbsp; {lang === 'id' ? 'Kami merespon dalam 24 jam' : 'We usually respond within 24 hours'}
          </p>
          <p className="text-xs text-gray-300 mt-0.5">{lang === 'id' ? 'Dibuat dengan segenap hati oleh tim SELA' : 'Made with care by the SELA team'}</p>
        </div>

      </div>
    </div>
  )
}
