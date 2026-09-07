import { useState, useCallback } from 'react'

/**
 * Ubah URL YouTube biasa → URL embed yang bisa diputar di iframe
 */
function getYouTubeEmbedUrl(url) {
  try {
    const u = new URL(url)
    let videoId = null
    if (u.hostname.includes('youtu.be')) {
      videoId = u.pathname.slice(1)
    } else if (u.hostname.includes('youtube.com')) {
      videoId = u.searchParams.get('v')
    }
    if (videoId) return `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`
  } catch (_) { /* bukan URL valid */ }
  return null
}

function isYouTubeUrl(url) {
  return url.includes('youtube.com') || url.includes('youtu.be')
}

// ── Lightbox Overlay ─────────────────────────────────────────────
function Lightbox({ src, caption, onClose }) {
  return (
    <div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-black/85 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <button
        className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/20 hover:bg-white/30 text-white flex items-center justify-center text-xl transition-colors"
        onClick={onClose}
        aria-label="Tutup"
      >
        ✕
      </button>
      <img
        src={src}
        alt={caption}
        className="max-w-[90vw] max-h-[80vh] rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />
      {caption && (
        <p className="mt-3 text-white/70 text-sm text-center max-w-md px-4">{caption}</p>
      )}
    </div>
  )
}

// ── Media Card ───────────────────────────────────────────────────
/**
 * @param {{ type: 'image'|'video', url: string, caption?: string }} item
 */
export default function MediaCard({ item }) {
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [videoActive, setVideoActive] = useState(false)

  const openLightbox = useCallback(() => setLightboxOpen(true), [])
  const closeLightbox = useCallback(() => setLightboxOpen(false), [])

  if (!item?.url) return null

  // ── Video ────────────────────────────────────────────────────
  if (item.type === 'video') {
    const embedUrl = isYouTubeUrl(item.url) ? getYouTubeEmbedUrl(item.url) : null

    return (
      <div className="rounded-xl overflow-hidden border border-gray-200/60 dark:border-white/10 bg-white dark:bg-slate-800/50 shadow-md animate-fade-in">
        <div className="relative w-full aspect-video bg-black">
          {videoActive && embedUrl ? (
            <iframe
              src={embedUrl}
              title={item.caption || 'Video'}
              className="w-full h-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          ) : videoActive && !embedUrl ? (
            // Video langsung (mp4 dll)
            <video
              src={item.url}
              controls
              autoPlay
              className="w-full h-full object-cover"
            />
          ) : (
            // Thumbnail / play button overlay
            <button
              className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 transition-all duration-200 group"
              onClick={() => setVideoActive(true)}
            >
              {/* Play icon */}
              <div className="w-14 h-14 rounded-full bg-white/15 group-hover:bg-white/25 flex items-center justify-center transition-all duration-200 group-hover:scale-110">
                <svg className="w-6 h-6 text-white ml-1" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
              <span className="text-white/60 text-xs font-medium">
                {isYouTubeUrl(item.url) ? '▶ Putar video YouTube' : '▶ Putar video'}
              </span>
            </button>
          )}
        </div>
        {item.caption && (
          <p className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 font-medium">{item.caption}</p>
        )}
      </div>
    )
  }

  // ── Image ────────────────────────────────────────────────────
  return (
    <>
      <div
        className="rounded-xl overflow-hidden border border-gray-200/60 dark:border-white/10 bg-white dark:bg-slate-800/50 shadow-md animate-fade-in cursor-zoom-in group"
        onClick={openLightbox}
      >
        <div className="relative overflow-hidden">
          <img
            src={item.url}
            alt={item.caption || 'Media'}
            className="w-full object-cover max-h-48 transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
          {/* Zoom hint overlay */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/15 transition-colors duration-200 flex items-center justify-center">
            <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 w-10 h-10 rounded-full bg-white/25 flex items-center justify-center backdrop-blur-sm">
              <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
              </svg>
            </div>
          </div>
        </div>
        {item.caption && (
          <p className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 font-medium">{item.caption}</p>
        )}
      </div>

      {lightboxOpen && (
        <Lightbox src={item.url} caption={item.caption} onClose={closeLightbox} />
      )}
    </>
  )
}
