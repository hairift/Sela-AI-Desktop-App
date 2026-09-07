/* eslint-disable react/prop-types */
import { useState, useEffect, useRef } from 'react'
import QRCode from 'qrcode'
import { t } from '../lib/translations'

const URL_PATTERN = /(https?:\/\/[^\s]+)/g
const TRAILING_PUNCTUATION = /[.,!?;:)\]]$/
const SELA_ALIASES = new Set(['cela', 'sela', 'zela', 'selah', 'sella', 'selak'])
const BOLD_PATTERN = /(\*\*[^*]+\*\*)/g
const PROTECTED_TOKEN_PREFIX = '__SELA_PROTECTED_'
const FOLLOW_UP_PATTERN = /(?:^|\s)((?:\[[^\]\n]*\?]\s*(?:\|\s*)?){1,2})\s*$/

function isSelaAlias(word) {
  return SELA_ALIASES.has(word.toLowerCase())
}

function normalizeSelaAliases(text = '') {
  return text.replace(/[A-Za-z]+/g, word => (
    isSelaAlias(word) ? 'Sela' : word
  ))
}

function splitTextByLinks(text = '') {
  const parts = []
  let lastIndex = 0

  for (const match of text.matchAll(URL_PATTERN)) {
    const rawUrl = match[0]
    const start = match.index
    let url = rawUrl
    let trailing = ''

    while (TRAILING_PUNCTUATION.test(url)) {
      trailing = url.slice(-1) + trailing
      url = url.slice(0, -1)
    }

    if (start > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, start) })
    }

    if (url) {
      parts.push({ type: 'qr', value: url })
    }

    if (trailing) {
      parts.push({ type: 'text', value: trailing })
    }

    lastIndex = start + rawUrl.length
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return parts
}

function withProtectedLinks(text = '', formatter) {
  const links = []
  const protectedText = String(text || '').replace(URL_PATTERN, (url) => {
    const token = `${PROTECTED_TOKEN_PREFIX}${links.length}__`
    links.push(url)
    return token
  })

  const formatted = formatter(protectedText)
  return formatted.replace(
    new RegExp(`${PROTECTED_TOKEN_PREFIX}(\\d+)__`, 'g'),
    (_, index) => links[Number(index)] || ''
  )
}

function normalizeMarkdownStructure(text = '') {
  return withProtectedLinks(text, (value) => {
    let normalized = value
      .replace(/\r/g, '')
      .replace(/[ \t]+/g, ' ')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')

    // Jika AI menulis "A: 1. ... 2. ..." atau "A: - ... - ...",
    // ubah menjadi list markdown yang bisa dirender rapi.
    normalized = normalized
      .replace(/:\s+(?=(?:[-*]\s+|(?:[1-9]|[1-9]\d)[.)]\s+))/g, ':\n')
      .replace(/(^|\n)((?:[1-9]|[1-9]\d)[.)])(?=\S)/g, '$1$2 ')
      .replace(/([^\n])[\s,;]+((?:[1-9]|[1-9]\d)[.)]\s+)/g, '$1\n$2')
      .replace(/([^\n\d])[\s,;]+([-*]\s+(?=[A-Za-z0-9(]))/g, '$1\n$2')

    // Label bagian yang sering muncul dari dataset dibuat sebagai baris sendiri
    // agar "Program S1:" tidak menempel dengan paragraf sebelumnya.
    normalized = normalized.replace(
      /([.!?])\s+((?:Program|Fakultas|Syarat|Langkah|Biaya|Fasilitas|Beasiswa|Kontak|Lokasi)\b[^:\n]{0,60}:)/gi,
      '$1\n\n$2'
    )

    return normalized
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  })
}

function splitFollowUpSuggestions(text = '') {
  const value = String(text || '').trim()
  const match = value.match(FOLLOW_UP_PATTERN)
  if (!match) return { answerText: value, suggestions: [] }

  const rawSuggestions = match[1]
  const suggestions = [...rawSuggestions.matchAll(/\[([^\]\n]*\?)]/g)]
    .map((item) => item[1].trim())
    .filter(Boolean)

  if (suggestions.length === 0) return { answerText: value, suggestions: [] }

  return {
    answerText: value.slice(0, match.index).trim(),
    suggestions
  }
}

function splitMarkdownBlocks(text = '') {
  const lines = normalizeMarkdownStructure(text).split('\n')
  const blocks = []
  let paragraphLines = []
  let activeList = null

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return
    blocks.push({
      type: 'paragraph',
      content: paragraphLines.join('\n').trim()
    })
    paragraphLines = []
  }

  const flushList = () => {
    if (!activeList) return
    blocks.push(activeList)
    activeList = null
  }

  lines.forEach((line) => {
    const trimmed = line.trim()

    if (!trimmed) {
      flushParagraph()
      flushList()
      return
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        content: headingMatch[2]
      })
      return
    }

    const unorderedMatch = trimmed.match(/^[-*]\s+(.*)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (!activeList || activeList.type !== 'ordered-list') {
        flushList()
        activeList = { type: 'ordered-list', items: [] }
      }
      activeList.items.push(unorderedMatch[1])
      return
    }

    const orderedMatch = trimmed.match(/^(\d+)[.)]\s+(.*)$/)
    if (orderedMatch) {
      flushParagraph()
      if (!activeList || activeList.type !== 'ordered-list') {
        flushList()
        activeList = { type: 'ordered-list', items: [] }
      }
      activeList.items.push(orderedMatch[2])
      return
    }

    flushList()
    paragraphLines.push(line)
  })

  flushParagraph()
  flushList()

  return blocks
}

function renderInlineMarkdown(text = '', keyPrefix = 'inline', qrVisibleMs = null) {
  const normalized = normalizeSelaAliases(text)
  const parts = splitTextByLinks(normalized)

  return parts.flatMap((part, partIndex) => {
    if (part.type === 'qr') {
      return (
        <QrLinkCard
          key={`${keyPrefix}-qr-${partIndex}`}
          url={part.value}
          visibleMs={qrVisibleMs}
        />
      )
    }

    return part.value
      .split(BOLD_PATTERN)
      .filter(Boolean)
      .map((segment, segmentIndex) => {
        const boldMatch = segment.match(/^\*\*(.*)\*\*$/)
        if (boldMatch) {
          return (
            <strong key={`${keyPrefix}-bold-${partIndex}-${segmentIndex}`} className="font-semibold text-gray-800 dark:text-white">
              {boldMatch[1]}
            </strong>
          )
        }

        return (
          <span key={`${keyPrefix}-text-${partIndex}-${segmentIndex}`}>
            {segment}
          </span>
        )
      })
  })
}

function QrLinkCard({ url, visibleMs = null }) {
  const [qrSrc, setQrSrc] = useState('')
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    let active = true

    QRCode.toDataURL(url, {
      width: 132,
      margin: 1,
      color: {
        dark: '#111827',
        light: '#ffffff'
      }
    }).then(src => {
      if (active) setQrSrc(src)
    }).catch(() => {
      if (active) setQrSrc('')
    })

    return () => {
      active = false
    }
  }, [url])

  useEffect(() => {
    setIsVisible(true)

    if (!visibleMs) return undefined

    const timeout = setTimeout(() => {
      setIsVisible(false)
    }, visibleMs)

    return () => clearTimeout(timeout)
  }, [url, visibleMs])

  if (!isVisible) return null

  return (
    <span className="my-2 flex w-fit max-w-full flex-col items-center gap-1 rounded-xl border border-gray-200/80 bg-white p-2 shadow-sm dark:border-white/10 dark:bg-slate-900/80">
      {qrSrc ? (
        <img
          src={qrSrc}
          alt="QR code untuk link"
          className="h-28 w-28 rounded-md"
          loading="lazy"
        />
      ) : (
        <span className="flex h-28 w-28 items-center justify-center rounded-md bg-gray-100 text-[10px] font-medium text-gray-400 dark:bg-slate-800 dark:text-gray-500">
          QR
        </span>
      )}
      <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
        Scan QR
      </span>
    </span>
  )
}

function ChatContent({ text, qrVisibleMs = null }) {
  const { answerText, suggestions } = splitFollowUpSuggestions(text)
  const blocks = splitMarkdownBlocks(answerText)

  if (blocks.length === 0) {
    return (
      <ChatSuggestionLayout suggestions={suggestions}>
        <span className="whitespace-pre-wrap break-words">
          {renderInlineMarkdown(answerText, 'fallback', qrVisibleMs)}
        </span>
      </ChatSuggestionLayout>
    )
  }

  return (
    <ChatSuggestionLayout suggestions={suggestions}>
      <div className="space-y-2 break-words">
        {blocks.map((block, blockIndex) => {
          if (block.type === 'heading') {
            const headingClass =
              block.level === 1
                ? 'text-base font-semibold text-gray-900 dark:text-white'
                : 'text-sm font-semibold text-gray-800 dark:text-gray-100'

            return (
              <p key={`heading-${blockIndex}`} className={headingClass}>
                {renderInlineMarkdown(block.content, `heading-${blockIndex}`, qrVisibleMs)}
              </p>
            )
          }

          if (block.type === 'ordered-list') {
            return (
              <ol key={`ol-${blockIndex}`} className="list-decimal space-y-1.5 pl-5 leading-relaxed">
                {block.items.map((item, itemIndex) => (
                  <li key={`ol-${blockIndex}-${itemIndex}`} className="whitespace-pre-wrap pl-0.5">
                    {renderInlineMarkdown(item, `ol-${blockIndex}-${itemIndex}`, qrVisibleMs)}
                  </li>
                ))}
              </ol>
            )
          }

          return (
            <p key={`p-${blockIndex}`} className="whitespace-pre-wrap break-words">
              {renderInlineMarkdown(block.content, `p-${blockIndex}`, qrVisibleMs)}
            </p>
          )
        })}
      </div>
    </ChatSuggestionLayout>
  )
}

function ChatSuggestionLayout({ children, suggestions = [] }) {
  return (
    <div className="space-y-2 break-words">
      {children}
      {suggestions.length > 0 && (
        <div className="border-t border-gray-100 pt-2 text-xs leading-snug text-gray-500 dark:border-white/10 dark:text-gray-400">
          <div className="space-y-1">
            {suggestions.map((suggestion, index) => (
              <p key={`suggestion-${index}`}>{suggestion}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ChatBubble({ role, text, lang = 'id', isLoading = false, isNew = false, qrVisibleMs = null }) {
  const isUser = role === 'user'
  const [displayed, setDisplayed] = useState(isNew ? '' : text)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!isNew || !text) {
      setDisplayed(text)
      return
    }

    setDisplayed('')
    let i = 0
    intervalRef.current = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) clearInterval(intervalRef.current)
    }, 18) // ~55 karakter/detik — natural typing speed

    return () => clearInterval(intervalRef.current)
  }, [text, isNew])

  return (
    <div className={`animate-fade-in flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-3`}>
      <span className={`text-[10px] font-semibold uppercase tracking-widest mb-1 ${isUser ? 'text-blue-400' : 'text-gray-400'}`}>
        {isUser ? t[lang].you : t[lang].sela}
      </span>
      <div
        className={`max-w-[min(380px,85vw)] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm transition-colors
          ${isUser
            ? 'bg-blue-50/90 dark:bg-blue-900/40 text-gray-700 dark:text-blue-100 rounded-tr-sm border border-blue-100/60 dark:border-blue-800/50'
            : 'bg-white/90 dark:bg-slate-800/90 text-gray-600 dark:text-gray-200 rounded-tl-sm border border-gray-100/80 dark:border-white/5'
          }`}
      >
        {isLoading ? (
          // Animasi 3 titik bergerak (thinking/loading indicator)
          <span className="flex gap-1.5 items-center h-4 px-1">
            <span className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:-0.3s]" />
            <span className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:-0.15s]" />
            <span className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" />
          </span>
        ) : (
          <ChatContent text={displayed} qrVisibleMs={qrVisibleMs} />
        )}
      </div>
    </div>
  )
}
