import { useRef } from "react";

/**
 * SuggestionButtons component - displays follow-up question suggestions with horizontal navigation
 * @param {Array<string>} suggestions - Array of follow-up questions
 * @param {function} onClick - Callback when suggestion is clicked, receives the suggestion text
 * @param {boolean} isVisible - Whether to show buttons (for conditional rendering)
 */
export default function SuggestionButtons({
  suggestions = [],
  onClick,
  isVisible = true,
}) {
  const containerRef = useRef(null);

  if (!isVisible || !suggestions || suggestions.length === 0) {
    return null;
  }

  const scrollSuggestions = (direction) => {
    if (containerRef.current) {
      containerRef.current.scrollBy({
        left: direction * 160,
        behavior: "smooth",
      });
    }
  };

  return (
    <div className="relative flex items-center gap-1 mt-2.5 mb-1.5 w-full group/sug">
      {/* Tombol Navigasi Kiri */}
      {suggestions.length > 1 && (
        <button
          type="button"
          onClick={() => scrollSuggestions(-1)}
          className="w-6 h-6 rounded-full bg-white/95 dark:bg-slate-800/95 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 shadow-sm flex items-center justify-center shrink-0 hover:scale-105 active:scale-95 transition-all cursor-pointer z-10"
          title="Geser opsi ke kiri"
          aria-label="Sebelumnya"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Kontainer Tombol Saran Berjalan Horizontal */}
      <div
        ref={containerRef}
        className="flex items-center gap-1.5 overflow-x-auto scroll-smooth hide-scrollbar py-0.5 w-full"
      >
        {suggestions.map((suggestion, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onClick?.(suggestion)}
            className="whitespace-nowrap px-3 py-1.5 rounded-full bg-gradient-to-r from-blue-100/90 to-blue-50/90
                       dark:from-blue-900/40 dark:to-blue-800/25
                       text-blue-700 dark:text-blue-300 text-xs font-medium
                       hover:from-blue-200 hover:to-blue-100
                       dark:hover:from-blue-800/60 dark:hover:to-blue-700/40
                       hover:shadow-sm active:scale-95
                       transition-all duration-150
                       border border-blue-200/90 dark:border-blue-700/50
                       shrink-0 cursor-pointer"
            title={suggestion}
          >
            {suggestion}
          </button>
        ))}
      </div>

      {/* Tombol Navigasi Kanan */}
      {suggestions.length > 1 && (
        <button
          type="button"
          onClick={() => scrollSuggestions(1)}
          className="w-6 h-6 rounded-full bg-white/95 dark:bg-slate-800/95 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 shadow-sm flex items-center justify-center shrink-0 hover:scale-105 active:scale-95 transition-all cursor-pointer z-10"
          title="Geser opsi ke kanan"
          aria-label="Berikutnya"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}
    </div>
  );
}
