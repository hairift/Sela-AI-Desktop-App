import { useState, useRef, useEffect } from 'react'
import Navbar from './components/Navbar'
import VoiceUI from './components/VoiceUI'
import HamburgerMenu from './components/HamburgerMenu'
import Settings from './components/Settings'
import Help from './components/Help'

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

function createChat(title = 'New Chat') {
  return { id: generateId(), title, messages: [], createdAt: new Date() }
}

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [page, setPage] = useState('home')
  const [chats, setChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)
  const [scrolled, setScrolled] = useState(false)
  const [lang, setLang] = useState('id') // Default language is Indonesian
  const [theme, setTheme] = useState('light') // Default theme is Light

  // Handle dark mode class toggling
  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [theme])

  const currentChatIdRef = useRef(currentChatId)
  useEffect(() => {
    currentChatIdRef.current = currentChatId
  }, [currentChatId])

  const navigate = (target) => {
    setMenuOpen(false)
    setPage(target)
  }

  const goHome = () => setPage('home')

  const handleNewChat = () => {
    const chat = createChat('New Chat')
    setChats(prev => [chat, ...prev])
    setCurrentChatId(chat.id)
    setMenuOpen(false)
    setPage('home')
  }

  const handleSelectChat = (id) => {
    setCurrentChatId(id)
    setMenuOpen(false)
    setPage('home')
  }

  const handleResetChat = () => {
    setChats([])
    setCurrentChatId(null)
    currentChatIdRef.current = null
  }

  const handleDeleteChat = (id) => {
    setChats(prev => prev.filter(c => c.id !== id))
    if (currentChatId === id) {
      const remaining = chats.filter(c => c.id !== id)
      setCurrentChatId(remaining.length > 0 ? remaining[0].id : null)
    }
  }

  const handleSendMessage = (text) => {
    if (!text.trim()) return
    const msgId = generateId()
    let targetId = currentChatIdRef.current;

    if (!targetId) {
      const newChat = createChat(text.slice(0, 40));
      newChat.messages = [{ id: msgId, role: 'user', text, ts: new Date() }];
      setChats(prev => [newChat, ...prev]);
      setCurrentChatId(newChat.id);
      currentChatIdRef.current = newChat.id; // Immediate sync
      return;
    }

    setChats(prev => prev.map(c => {
      if (c.id !== targetId) return c
      const updatedTitle = c.messages.length === 0 ? text.slice(0, 40) : c.title
      return {
        ...c,
        title: updatedTitle,
        messages: [...c.messages, { id: msgId, role: 'user', text, ts: new Date() }]
      }
    }))
  }

  const handleReceiveMessage = (data) => {
    const targetId = currentChatIdRef.current;

    // Handle both string (legacy) and object with text + suggestions + media (new)
    const text = typeof data === 'string' ? data : data?.text
    const suggestions = typeof data === 'object' ? data?.suggestions : undefined
    const media = typeof data === 'object' ? data?.media : undefined

    if (!text?.trim() || !targetId) return

    const msgId = generateId()
    setChats(prev => prev.map(c => {
      if (c.id !== targetId) return c
      const msgObj = { id: msgId, role: 'assistant', text: text.trim(), ts: new Date() }
      if (suggestions && suggestions.length > 0) {
        msgObj.suggestions = suggestions
      }
      if (media && media.length > 0) {
        msgObj.media = media
      }
      return {
        ...c,
        messages: [...c.messages, msgObj]
      }
    }))
  }

  const currentChat = chats.find(c => c.id === currentChatId) || null

  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden">
      {/* Background animated mesh gradient */}
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden bg-[#f8faff] dark:bg-slate-950 transition-colors duration-500">
        <div className="absolute -top-[10%] -left-[10%] w-[50%] h-[50%] rounded-full bg-blue-200/40 dark:bg-blue-900/20 blur-[120px] animate-float-1" />
        <div className="absolute top-[20%] -right-[10%] w-[45%] h-[45%] rounded-full bg-indigo-200/30 dark:bg-indigo-900/15 blur-[120px] animate-float-2" />
        <div className="absolute -bottom-[10%] left-[20%] w-[40%] h-[40%] rounded-full bg-sky-100/50 dark:bg-blue-800/20 blur-[120px] animate-float-3" />
      </div>

      {page === 'home' ? (
        <>
          <Navbar
            onMenuClick={() => setMenuOpen(true)}
            lang={lang}
            setLang={setLang}
            theme={theme}
            setTheme={setTheme}
          />
          <VoiceUI
            currentChat={currentChat}
            onSend={handleSendMessage}
            onReceive={handleReceiveMessage}
            onNewChat={handleNewChat}
            onReset={handleResetChat}
            lang={lang}
            setLang={setLang}
            theme={theme}
          />
        </>
      ) : (
        <div className="flex-1 overflow-y-auto" onScroll={(e) => setScrolled(e.target.scrollTop > 10)}>
          {page === 'settings' && <Settings onBack={goHome} scrolled={scrolled} lang={lang} setLang={setLang} theme={theme} setTheme={setTheme} />}
          {page === 'help'     && <Help     onBack={goHome} scrolled={scrolled} lang={lang} theme={theme} />}
        </div>
      )}

      <HamburgerMenu
        isOpen={menuOpen}
        onClose={() => setMenuOpen(false)}
        chats={chats}
        currentChatId={currentChatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        onOpenSettings={() => navigate('settings')}
        onOpenHelp={() => navigate('help')}
        lang={lang}
        theme={theme}
      />
    </div>
  )
}
