import { Suspense, useMemo, useRef, useEffect, Component } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { ContactShadows, Html, PerspectiveCamera, useGLTF, useAnimations, Environment } from '@react-three/drei'
import * as THREE from 'three'
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js'
import { lipsyncManager, VISEMES } from '../lib/lipsync'

/**
 * Komponen Pembatas Galat (ErrorBoundary) untuk melindungi antarmuka jika terjadi
 * kendala pada WebGL, shader grafis, atau pemuatan model 3D lokal.
 */
class PembatasGalatAvatar extends Component {
  constructor(props) {
    super(props)
    this.state = { terjadiGalat: false }
  }

  static getDerivedStateFromError() {
    return { terjadiGalat: true }
  }

  componentDidCatch(galat, info) {
    console.warn('[Avatar 3D] Menangani galat pada komponen 3D:', galat, info)
  }

  render() {
    if (this.state.terjadiGalat) {
      return (
        <div className="flex flex-col items-center justify-center w-full h-full">
          <div className="flex items-center justify-center w-36 h-36 rounded-full border border-sky-400/30 bg-slate-900/80 text-[12px] font-semibold tracking-widest text-sky-200 shadow-2xl backdrop-blur-md animate-pulse">
            SELA AI
          </div>
        </div>
      )
    }
    return this.props.children
  }
}


const STATE_CONFIG = {
  idle: {
    label: 'Idle',
    color: 'from-blue-400/20 to-indigo-400/20',
    ring: 'ring-blue-300/40',
    dot: 'bg-blue-400',
    pulse: false,
  },
  listening: {
    label: 'Listening',
    color: 'from-blue-500/25 to-cyan-400/20',
    ring: 'ring-blue-400/60',
    dot: 'bg-blue-500',
    pulse: true,
  },
  thinking: {
    label: 'Thinking',
    color: 'from-indigo-500/20 to-purple-400/20',
    ring: 'ring-indigo-400/50',
    dot: 'bg-indigo-500',
    pulse: true,
  },
  speaking: {
    label: 'Speaking',
    color: 'from-emerald-400/20 to-blue-400/20',
    ring: 'ring-emerald-400/50',
    dot: 'bg-emerald-400',
    pulse: true,
  },
}

const WAVE_HEIGHTS = [20, 36, 48, 30, 44, 26, 40, 32, 24]
const WAVE_COLORS = ['bg-blue-300', 'bg-blue-400', 'bg-blue-500', 'bg-indigo-400', 'bg-blue-400', 'bg-blue-300', 'bg-indigo-500', 'bg-blue-400', 'bg-blue-300']
const WAVE_ANIMS = ['animate-wave-1', 'animate-wave-3', 'animate-wave-2', 'animate-wave-4', 'animate-wave-1', 'animate-wave-5', 'animate-wave-2', 'animate-wave-3', 'animate-wave-1']

const MORPH_ALIASES = {
  visemeSil: ['viseme_sil', 'visemesil', 'sil', 'silence', 'mouthclose', 'mouth_close', 'mouthrest', 'mouth_rest', 'neutral'],
  visemeAa: ['viseme_aa', 'visemeaa', 'aa', 'a'],
  visemeIh: ['viseme_ih', 'visemeih', 'ih', 'i'],
  visemeU: ['viseme_u', 'visemeu', 'u', 'ou'],
  visemeE: ['viseme_e', 'visemee', 'e', 'eh'],
  visemeO: ['viseme_o', 'visemeo', 'o', 'oh'],
  eyeBlinkLeft: ['eyeblinkleft', 'eye_blink_left', 'blinkleft', 'blink_l', 'eyeclosedleft', 'eye_close_left'],
  eyeBlinkRight: ['eyeblinkright', 'eye_blink_right', 'blinkright', 'blink_r', 'eyeclosedright', 'eye_close_right'],
  eyeWideLeft: ['eyewideleft', 'eye_wide_left', 'wideleft', 'eyeopenwideleft'],
  eyeWideRight: ['eyewideright', 'eye_wide_right', 'wideright', 'eyeopenwideright'],
  browInnerUp: ['browinnerup', 'brow_inner_up'],
  browOuterUpLeft: ['browouterupleft', 'brow_outer_up_left'],
  browOuterUpRight: ['browouterupright', 'brow_outer_up_right'],
  browDownLeft: ['browdownleft', 'brow_down_left'],
  browDownRight: ['browdownright', 'brow_down_right'],
}

const MODEL_SCALE = 5.0
const MODEL_BASE_Y = -4.65
const SHADOW_Y = -4.0

function normalizeMorphName(name = '') {
  return name.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function findMorphIndex(dictionary, aliases) {
  if (!dictionary || !aliases?.length) return null

  const normalizedAliases = aliases.map(normalizeMorphName)

  for (const [name, index] of Object.entries(dictionary)) {
    if (normalizedAliases.includes(normalizeMorphName(name))) {
      return index
    }
  }

  return null
}

function createBinding(mesh) {
  const dictionary = mesh.morphTargetDictionary
  const influences = mesh.morphTargetInfluences

  if (!dictionary || !influences) return null

  const targets = Object.fromEntries(
    Object.entries(MORPH_ALIASES).map(([key, aliases]) => [key, findMorphIndex(dictionary, aliases)])
  )

  return { mesh, influences, targets }
}

function applyMorph(bindings, key, value, smoothing = 0.18) {
  bindings.forEach(({ influences, targets }) => {
    const index = targets[key]
    if (index == null) return
    influences[index] = THREE.MathUtils.lerp(influences[index], value, smoothing)
  })
}

function resetUntrackedMorphs(bindings, protectedKeys) {
  const protectedSet = new Set(protectedKeys)

  bindings.forEach(({ influences, targets }) => {
    Object.entries(targets).forEach(([key, index]) => {
      if (index == null || protectedSet.has(key)) return
      influences[index] = THREE.MathUtils.lerp(influences[index], 0, 0.18)
    })
  })
}

function AvatarFallback() {
  return (
    <Html center>
      <div className="flex items-center justify-center w-36 h-36 rounded-full border border-white/15 bg-slate-900/70 text-[11px] font-medium tracking-[0.3em] text-slate-200 uppercase shadow-2xl backdrop-blur-md">
        Loading 3D
      </div>
    </Html>
  )
}

function SelaModel({ state }) {
  const groupRef = useRef(null)
  const blinkRef = useRef({
    elapsed: 0,
    active: false,
    start: 0,
    nextAt: 1.2 + Math.random() * 2.8,
  })
  const { scene, animations } = useGLTF('/models/SELA_BARU.glb')
  const { actions } = useAnimations(animations, groupRef)

  useEffect(() => {
    if (!actions) return

    // Jalankan animasi Idle alami secara terus-menerus (tangan rileks di samping)
    // Gerakan mulut saat bicara 100% dikendalikan oleh Wawa Lipsync di useFrame
    const idleAction = actions['Idle'] || Object.values(actions)[0]
    if (idleAction && !idleAction.isRunning()) {
      Object.values(actions).forEach(act => {
        if (act !== idleAction) act?.fadeOut(0.3)
      })
      idleAction.reset().fadeIn(0.4).play()
    }
  }, [actions])

  const bindings = useMemo(() => {
    const nextBindings = []
    scene.traverse((child) => {
      const binding = createBinding(child)
      if (binding) nextBindings.push(binding)
    })
    return nextBindings
  }, [scene])

  useFrame((renderState, delta) => {
    const group = groupRef.current
    if (!group) return

    const t = renderState.clock.getElapsedTime()

    group.rotation.y = Math.sin(t * 0.5) * 0.08
    group.rotation.x = Math.sin(t * 0.9) * 0.02
    group.position.y = MODEL_BASE_Y + Math.sin(t * 1.6) * 0.03

    const blink = blinkRef.current
    blink.elapsed += delta

    if (!blink.active && blink.elapsed >= blink.nextAt) {
      blink.active = true
      blink.start = blink.elapsed
      blink.nextAt = blink.elapsed + 2.4 + Math.random() * 3.8
    }

    let blinkWeight = 0
    if (blink.active) {
      const progress = (blink.elapsed - blink.start) / 0.16
      if (progress >= 1) {
        blink.active = false
      } else {
        blinkWeight = Math.sin(progress * Math.PI)
      }
    }

    // ── 100% Wawa Lipsync: Analisis frekuensi audio real-time Web Audio API ──
    let currentViseme = VISEMES.sil
    let currentVolume = 0

    if (state === 'speaking') {
      try {
        lipsyncManager.processAudio()
        currentViseme = lipsyncManager.viseme || VISEMES.sil
        currentVolume = lipsyncManager.features?.volume || 0
      } catch (_) {}
    }

    // Skala bukaan mulut berbasis energi audio Wawa. Di beberapa GPU/browser,
    // analyser memberi nol pada frame pembuka walau <audio> sudah berbunyi;
    // gunakan gerak sangat kecil sementara sebagai jembatan agar avatar tidak
    // tampak beku, lalu Wawa kembali mengambil alih begitu energi tersedia.
    const wawaAktif = currentVolume > 0.012
    const volumeMultiplier = state === 'speaking'
      ? (wawaAktif
          ? Math.min(1.25, Math.max(0.24, currentVolume * 2.6))
          : 0.28 + Math.sin(t * 11) * 0.07)
      : 0

    let targetAa = 0
    let targetIh = 0
    let targetU = 0
    let targetE = 0
    let targetO = 0
    let targetSil = state === 'speaking' ? 0.05 : 0.85

    if (state === 'speaking') {
      switch (currentViseme) {
        case VISEMES.aa:
          targetAa = 1.0 * volumeMultiplier
          targetE = 0.25 * volumeMultiplier
          break
        case VISEMES.E:
          targetE = 1.0 * volumeMultiplier
          targetAa = 0.3 * volumeMultiplier
          break
        case VISEMES.I:
          targetIh = 1.0 * volumeMultiplier
          targetE = 0.3 * volumeMultiplier
          break
        case VISEMES.O:
          targetO = 1.0 * volumeMultiplier
          targetU = 0.25 * volumeMultiplier
          break
        case VISEMES.U:
          targetU = 1.0 * volumeMultiplier
          targetO = 0.3 * volumeMultiplier
          break
        // Fricatives, dental, plosives (gigi merapat & sedikit membuka)
        case VISEMES.CH:
        case VISEMES.SS:
        case VISEMES.FF:
        case VISEMES.TH:
        case VISEMES.DD:
        case VISEMES.kk:
        case VISEMES.nn:
        case VISEMES.RR:
          targetIh = 0.45 * volumeMultiplier
          targetE = 0.2 * volumeMultiplier
          break
        case VISEMES.PP:
        default:
          // Hanya gunakan animasi jembatan jika analyser belum menyediakan
          // viseme. Nilai viseme dari Wawa tetap menjadi sumber utama.
          if (!wawaAktif) {
            targetAa = 0.48 * volumeMultiplier
            targetE = 0.20 * volumeMultiplier
            targetSil = 0.38
          } else {
            targetSil = 0.8
          }
          break
      }
    }

    const eyeWideBase =
      state === 'listening' ? 0.24 :
        state === 'thinking' ? 0.08 + (Math.sin(t * 1.8) + 1) * 0.04 :
          state === 'speaking' ? 0.1 :
            0

    const browLift =
      state === 'listening' ? 0.14 :
        state === 'thinking' ? 0.2 :
          state === 'speaking' ? 0.08 :
            0.03

    const browDown =
      state === 'thinking' ? 0.06 :
        0

    const trackedKeys = [
      'visemeSil',
      'visemeAa',
      'visemeIh',
      'visemeU',
      'visemeE',
      'visemeO',
      'eyeBlinkLeft',
      'eyeBlinkRight',
      'eyeWideLeft',
      'eyeWideRight',
      'browInnerUp',
      'browOuterUpLeft',
      'browOuterUpRight',
      'browDownLeft',
      'browDownRight',
    ]

    resetUntrackedMorphs(bindings, trackedKeys)

    trackedKeys.forEach((key) => {
      let target = 0
      let smoothing = 0.28 // Halus dan sinkron dengan frekuensi audio

      if (key === 'visemeSil') target = targetSil
      else if (key === 'visemeAa') target = targetAa
      else if (key === 'visemeIh') target = targetIh
      else if (key === 'visemeU') target = targetU
      else if (key === 'visemeE') target = targetE
      else if (key === 'visemeO') target = targetO
      else if (key === 'eyeBlinkLeft' || key === 'eyeBlinkRight') {
        target = blinkWeight
        smoothing = 0.4
      } else if (key === 'eyeWideLeft' || key === 'eyeWideRight') {
        target = Math.max(0, eyeWideBase - blinkWeight * 0.8)
      } else if (key === 'browInnerUp' || key === 'browOuterUpLeft' || key === 'browOuterUpRight') {
        target = browLift
      } else if (key === 'browDownLeft' || key === 'browDownRight') {
        target = browDown
      }

      applyMorph(bindings, key, target, smoothing)
    })
  })

  return (
    <group ref={groupRef} scale={MODEL_SCALE} position={[0, MODEL_BASE_Y, 0]}>
      <primitive object={scene} />
    </group>
  )
}

function SelaAvatar3D({ state, theme }) {
  const isDark = theme === 'dark'

  return (
    <Canvas
      dpr={[1, 2]}
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: isDark ? 1.08 : 1.15,
      }}
    >
      <PerspectiveCamera makeDefault position={[0, 0.8, 5.5]} fov={32} />

      {/* Pencahayaan Studio Proporsional: Cerah, Segar, Berdimensi Alami, Bebas Busem dan Tidak Silau */}
      <ambientLight intensity={isDark ? 0.48 : 0.58} color="#ffffff" />
      <hemisphereLight intensity={isDark ? 0.46 : 0.58} skyColor="#f8fafc" groundColor="#1e293b" />

      {/* Key Light: Cahaya utama hangat lembut dari sudut atas kanan */}
      <directionalLight
        position={[3.0, 3.5, 4.0]}
        intensity={isDark ? 1.55 : 1.80}
        color="#fffbf0"
      />

      {/* Fill Light: Cahaya pengisi sejuk lembut dari kiri agar bayangan wajah transparan & kulit segar */}
      <directionalLight
        position={[-3.0, 2.0, 3.0]}
        intensity={isDark ? 0.85 : 1.05}
        color="#f0f9ff"
      />

      {/* Rim / Hair Backlight: Garis kontur elektrik di tepi rambut & bahu */}
      <directionalLight
        position={[0, 3.5, -3.0]}
        intensity={isDark ? 2.2 : 2.6}
        color="#38bdf8"
      />
      <directionalLight
        position={[-2.5, 2.5, -2.0]}
        intensity={isDark ? 1.1 : 1.4}
        color="#818cf8"
      />

      {/* Beauty Front Light: Cahaya sorot titik lembut di mata & wajah agar segar dan berkilau alami */}
      <pointLight
        position={[0, 1.2, 3.0]}
        intensity={isDark ? 0.65 : 0.85}
        distance={8}
        color="#ffffff"
      />

      <Suspense fallback={<AvatarFallback />}>
        {/* Environment map dengan intensitas proporsional untuk refleksi halus */}
        <Environment preset="city" environmentIntensity={isDark ? 0.50 : 0.60} />
        <SelaModel state={state} />
        <ContactShadows
          position={[0, SHADOW_Y, 0]}
          opacity={isDark ? 0.4 : 0.25}
          scale={5.5}
          blur={2.0}
          far={4.5}
          color={isDark ? "#020617" : "#0f172a"}
        />

      </Suspense>
    </Canvas>
  )
}

export default function AvatarPlaceholder({ state = 'idle', theme = 'light' }) {
  const cfg = STATE_CONFIG[state] ?? STATE_CONFIG.idle
  const isSpeaking = state === 'speaking'

  return (
    <div className="relative w-full h-full select-none flex flex-col items-center">
      {/* Background glow centered behind the model */}
      <div className="absolute top-[15%] left-1/2 -translate-x-1/2 w-[90vw] max-w-[800px] h-[60vh] pointer-events-none">
        <div
          className={`absolute inset-0 rounded-full transition-all duration-700
            bg-gradient-to-b ${cfg.color} opacity-40 blur-[100px]`}
        />
        {cfg.pulse && (
          <span className="absolute inset-[15%] rounded-full animate-pulse opacity-15 bg-cyan-300 blur-[80px]" />
        )}
      </div>

      <div className="absolute inset-0 z-10 w-full h-full pointer-events-auto">
        <PembatasGalatAvatar>
          <SelaAvatar3D state={state} theme={theme} />
        </PembatasGalatAvatar>
      </div>

      <div className="absolute bottom-[22%] z-20 flex flex-col items-center pointer-events-none">
        <div className={`flex items-end justify-center gap-1 h-10 transition-all duration-500 ${isSpeaking ? 'opacity-100' : 'opacity-0'}`}>
          {WAVE_HEIGHTS.map((height, index) => (
            <div
              key={index}
              className={`w-[4px] rounded-full ${WAVE_COLORS[index]} ${isSpeaking ? WAVE_ANIMS[index] : ''}`}
              style={{ height: `${height}px` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

try {
  useGLTF.preload('/models/SELA_BARU.glb')
} catch (_) {}
