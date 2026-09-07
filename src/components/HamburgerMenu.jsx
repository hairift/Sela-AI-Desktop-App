import { useState, useEffect, useRef } from 'react'

// ── SVG icon helpers ──────────────────────────────────────────────
const IconClock = () => (
  <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
  </svg>
)

const IconTrash = () => (
  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
)

const IconSearch = () => (
  <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <circle cx="11" cy="11" r="8" />
    <path strokeLinecap="round" d="M21 21l-4.35-4.35" />
  </svg>
)

const IconPlus = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" d="M12 5v14M5 12h14" />
  </svg>
)

const IconX = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
)

const IconSettings = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.559.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)

const IconHelp = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" />
    <path strokeLinecap="round" d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01" />
  </svg>
)

const IconChevronRight = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
)

const IconMessageCircle = () => (
  <svg className="w-10 h-10 text-gray-200" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
)

// ─────────────────────────────────────────────────────────────────

import { t } from '../lib/translations'

export default function HamburgerMenu({
  isOpen, onClose,
  chats, currentChatId,
  onNewChat, onSelectChat, onDeleteChat,
  onOpenSettings, onOpenHelp,
  lang = 'id',
  theme = 'light'
}) {
  const [search, setSearch] = useState('')
  const [hoveredId, setHoveredId] = useState(null)
  const searchRef = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    if (isOpen) setTimeout(() => searchRef.current?.focus(), 300)
  }, [isOpen])

  const filtered = chats.filter(c =>
    c.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <>
      {/* Backdrop */}
      <div
        id="menu-backdrop"
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-gray-900/20 dark:bg-black/40 backdrop-blur-[2px] transition-opacity duration-300
          ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
      />

      {/* Side Panel */}
      <aside
        id="hamburger-menu"
        className={`fixed top-0 left-0 h-full w-[260px] z-50 flex flex-col
                    bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border-r border-gray-100 dark:border-white/10 shadow-2xl
                    transition-transform duration-300 ease-out
                    ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-6 pb-4">
          <span className="text-xl font-bold tracking-widest text-gray-800 dark:text-gray-100 select-none">SELA</span>
          <button
            id="menu-close-btn"
            onClick={onClose}
            aria-label="Close menu"
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 dark:hover:bg-slate-800 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <IconX />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="px-4 mb-4">
          <button
            id="new-chat-btn"
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-full
                       bg-gradient-to-r from-blue-500 to-blue-600 text-white text-sm font-semibold
                       shadow-md shadow-blue-300/40 hover:from-blue-600 hover:to-blue-700
                       active:scale-95 transition-all duration-200"
          >
            <IconPlus />
            {t[lang].new_chat}
          </button>
        </div>

        {/* Search */}
        <div className="px-4 mb-3">
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
              <IconSearch />
            </span>
            <input
              ref={searchRef}
              id="menu-search"
              type="text"
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-gray-50 dark:bg-slate-800/50 border border-gray-200/80 dark:border-gray-700
                         rounded-xl outline-none placeholder-gray-400 text-gray-600 dark:text-gray-300
                         focus:ring-2 focus:ring-blue-200 focus:border-blue-300 transition-all"
            />
          </div>
        </div>

        {/* Chat List */}
        <div className="flex-1 overflow-y-auto px-3 pb-2">
          {chats.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full py-10 text-center">
              <IconMessageCircle />
              <p className="mt-3 text-sm text-gray-400 font-medium">No conversations yet</p>
              <p className="text-xs text-gray-300 mt-1">Start a new chat above</p>
            </div>
          ) : (
            <>
              <p className="px-2 mb-2 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                Recent Chats
              </p>
              <nav className="flex flex-col gap-0.5">
                {filtered.map((chat) => (
                  <div
                    key={chat.id}
                    className="relative group"
                    onMouseEnter={() => setHoveredId(chat.id)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <button
                      id={`chat-item-${chat.id}`}
                      onClick={() => onSelectChat(chat.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-left transition-all duration-150 pr-10
                        ${currentChatId === chat.id
                          ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 font-medium'
                          : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800/50 hover:text-gray-800 dark:hover:text-gray-100'
                        }`}
                    >
                      <span className={currentChatId === chat.id ? 'text-blue-500' : 'text-gray-400 dark:text-gray-500'}>
                        <IconClock />
                      </span>
                      <span className="truncate">{chat.title}</span>
                    </button>

                    {/* Delete button */}
                    {hoveredId === chat.id && (
                      <button
                        id={`delete-chat-${chat.id}`}
                        onClick={(e) => { e.stopPropagation(); onDeleteChat(chat.id) }}
                        aria-label="Delete chat"
                        className="absolute right-2 top-1/2 -translate-y-1/2
                                   w-6 h-6 flex items-center justify-center rounded-lg
                                   text-gray-300 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                      >
                        <IconTrash />
                      </button>
                    )}
                  </div>
                ))}

                {filtered.length === 0 && search && (
                  <div className="px-4 py-6 text-center">
                    <p className="text-sm text-gray-400">No results for "{search}"</p>
                  </div>
                )}
              </nav>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 dark:border-white/10 px-3 pt-3 pb-2">
          <button
            id="settings-nav-btn"
            onClick={onOpenSettings}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-xl text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-800 hover:text-gray-700 dark:hover:text-gray-200 transition-all"
          >
            <IconSettings />
            {t[lang].settings}
          </button>

          <button
            id="help-nav-btn"
            onClick={onOpenHelp}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-xl text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-800 hover:text-gray-700 dark:hover:text-gray-200 transition-all"
          >
            <IconHelp />
            {t[lang].help}
          </button>
        </div>
      </aside>
    </>
  )
}
