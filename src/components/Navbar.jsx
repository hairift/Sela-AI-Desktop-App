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

export default function Navbar({ onMenuClick, lang, setLang, theme, setTheme }) {
  const toggleLang = () => {
    if (setLang) setLang(lang === 'id' ? 'en' : 'id');
  }

  const toggleTheme = () => {
    if (setTheme) setTheme(theme === 'light' ? 'dark' : 'light');
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
