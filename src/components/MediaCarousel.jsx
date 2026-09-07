import { useRef, useState, useCallback } from 'react'
import MediaCard from './MediaCard'

/**
 * Menampilkan satu atau lebih media item dalam layout:
 * - 1 item → satu kartu penuh
 * - 2+ item → carousel horizontal yang bisa digeser
 *
 * @param {{ media: Array<{type, url, caption}> }} props
 */
export default function MediaCarousel({ media }) {
  const scrollRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(true)

  if (!media || media.length === 0) return null

  // Single item — no carousel needed
  if (media.length === 1) {
    return (
      <div className="mt-2 px-1">
        <MediaCard item={media[0]} />
      </div>
    )
  }

  // Multiple items — horizontal carousel
  const updateScrollState = () => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
  }

  const scrollBy = (direction) => {
    const el = scrollRef.current
    if (!el) return
    el.scrollBy({ left: direction * 240, behavior: 'smooth' })
    setTimeout(updateScrollState, 350)
  }

  return (
    <div className="mt-2 relative group/carousel">
      {/* Scroll left button */}
      {canScrollLeft && (
        <button
          onClick={() => scrollBy(-1)}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 -translate-x-1
            w-7 h-7 rounded-full bg-white/90 dark:bg-slate-700/90 border border-gray-200/70 dark:border-white/10
            shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300
            hover:bg-white dark:hover:bg-slate-600 active:scale-90 transition-all duration-150
            opacity-0 group-hover/carousel:opacity-100"
          aria-label="Geser kiri"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
      )}

      {/* Carousel track */}
      <div
        ref={scrollRef}
        onScroll={updateScrollState}
        className="flex gap-3 overflow-x-auto pb-1 hide-scrollbar snap-x snap-mandatory px-1"
      >
        {media.map((item, idx) => (
          <div key={idx} className="flex-shrink-0 w-[220px] snap-start">
            <MediaCard item={item} />
          </div>
        ))}
      </div>

      {/* Scroll right button */}
      {canScrollRight && (
        <button
          onClick={() => scrollBy(1)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 translate-x-1
            w-7 h-7 rounded-full bg-white/90 dark:bg-slate-700/90 border border-gray-200/70 dark:border-white/10
            shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300
            hover:bg-white dark:hover:bg-slate-600 active:scale-90 transition-all duration-150
            opacity-0 group-hover/carousel:opacity-100"
          aria-label="Geser kanan"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="m9 18 6-6-6-6" />
          </svg>
        </button>
      )}

      {/* Dot indicators */}
      {media.length > 1 && (
        <div className="flex justify-center gap-1.5 mt-2">
          {media.map((_, idx) => (
            <button
              key={idx}
              onClick={() => {
                const el = scrollRef.current
                if (!el) return
                el.scrollTo({ left: idx * 240, behavior: 'smooth' })
                setTimeout(updateScrollState, 350)
              }}
              className="w-1.5 h-1.5 rounded-full bg-gray-300 dark:bg-slate-600 hover:bg-blue-400 dark:hover:bg-blue-400 transition-colors"
              aria-label={`Ke item ${idx + 1}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
