import { useState } from 'react'

export default function InputBar({ mode, onModeChange }) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (value.trim()) {
      // UI only – no backend
      setValue('')
    }
  }

  return (
    <div className="w-full max-w-xl mx-auto px-4">
      {/* Input row */}
      <form onSubmit={handleSubmit} className="relative mb-3">
        <input
          id="main-input"
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Ask anything..."
          className={`w-full bg-white/85 backdrop-blur-sm border rounded-full pl-5 pr-14 py-4
                      text-gray-700 text-sm placeholder-gray-400 outline-none shadow-md
                      transition-all duration-200
                      ${focused
                        ? 'border-blue-300 ring-4 ring-blue-100/60 shadow-blue-100/60'
                        : 'border-gray-200/70'
                      }`}
        />

        {/* Mic button */}
        <button
          id="mic-btn"
          type="button"
          aria-label="Microphone"
          className="absolute right-2 top-1/2 -translate-y-1/2
                     w-10 h-10 rounded-full flex items-center justify-center
                     bg-gradient-to-br from-blue-500 to-blue-600
                     shadow-lg shadow-blue-400/40
                     hover:from-blue-600 hover:to-blue-700
                     active:scale-95 transition-all duration-150"
        >
          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 1a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm6 10a6 6 0 0 1-12 0H4a8 8 0 0 0 16 0h-2zm-6 8v3h-2v-3a8.03 8.03 0 0 1-5.65-2.35l1.41-1.41A6 6 0 0 0 12 19a6 6 0 0 0 4.24-1.76l1.41 1.41A8.03 8.03 0 0 1 12 21z" />
          </svg>
        </button>
      </form>

      {/* Mode toggle */}
      <div className="flex justify-center">
        <div className="inline-flex items-center bg-white/70 backdrop-blur-sm border border-gray-100/80 rounded-2xl shadow-sm overflow-hidden">
          {/* Type */}
          <button
            id="mode-type-btn"
            onClick={() => onModeChange('type')}
            className={`flex flex-col items-center gap-1 px-8 py-2.5 transition-all duration-200
              ${mode === 'type' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M7 8h10M7 12h10M7 16h6" strokeLinecap="round" />
            </svg>
            <span className="text-[10px] font-semibold uppercase tracking-widest">Type</span>
          </button>

          {/* Divider */}
          <div className="w-px h-8 bg-gray-200" />

          {/* Speak */}
          <button
            id="mode-speak-btn"
            onClick={() => onModeChange('speak')}
            className={`flex flex-col items-center gap-1 px-8 py-2.5 transition-all duration-200
              ${mode === 'speak' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm-1 18v3h2v-3a8.03 8.03 0 0 0 5.65-2.35l-1.41-1.41A6 6 0 0 1 12 19a6 6 0 0 1-4.24-1.76L6.35 18.65A8.03 8.03 0 0 0 11 21z" />
            </svg>
            <span className="text-[10px] font-semibold uppercase tracking-widest">Speak</span>
          </button>
        </div>
      </div>
    </div>
  )
}
