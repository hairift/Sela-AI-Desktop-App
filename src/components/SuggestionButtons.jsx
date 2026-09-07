/**
 * SuggestionButtons component - displays follow-up question suggestions
 * @param {Array<string>} suggestions - Array of follow-up questions
 * @param {function} onClick - Callback when suggestion is clicked, receives the suggestion text
 * @param {boolean} isVisible - Whether to show buttons (for conditional rendering)
 */
export default function SuggestionButtons({ suggestions = [], onClick, isVisible = true }) {
  if (!isVisible || !suggestions || suggestions.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 mt-3 mb-2 animate-fade-in">
      {suggestions.map((suggestion, idx) => (
        <button
          key={idx}
          onClick={() => onClick?.(suggestion)}
          className="px-3 py-1.5 rounded-full bg-gradient-to-r from-blue-100 to-blue-50
                     dark:from-blue-900/50 dark:to-blue-800/30
                     text-blue-600 dark:text-blue-300 text-xs font-medium
                     hover:bg-gradient-to-r hover:from-blue-200 hover:to-blue-100
                     dark:hover:from-blue-800 dark:hover:to-blue-700
                     active:scale-95
                     transition-all duration-150
                     border border-blue-200 dark:border-blue-700/30
                     cursor-pointer"
          title={suggestion}
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
