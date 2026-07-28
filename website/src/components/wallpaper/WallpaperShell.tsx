'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { usePathname } from 'next/navigation'
import type { WallpaperTier, WallpaperViewMode } from '@/lib/wallpaper/types'
import { WallpaperBackground } from '@/components/WallpaperBackground'


type WallpaperLabState = {
  forceTier: WallpaperTier | null
  allowVideoFallback: boolean
  showDebug: boolean
  tier: WallpaperTier
  fps: number
  viewMode: WallpaperViewMode
  setForceTier: (t: WallpaperTier | null) => void
  setAllowVideoFallback: (v: boolean) => void
  setShowDebug: (v: boolean) => void
  setViewMode: (mode: WallpaperViewMode) => void
}

const WallpaperLabContext = createContext<WallpaperLabState | null>(null)

export function useWallpaperLab(): WallpaperLabState {
  const ctx = useContext(WallpaperLabContext)
  if (!ctx) {
    throw new Error('useWallpaperLab requires WallpaperShell')
  }
  return ctx
}

export function WallpaperShell({ children }: { children: ReactNode }) {
  const [forceTier, setForceTier] = useState<WallpaperTier | null>(null)
  const [allowVideoFallback, setAllowVideoFallback] = useState(false)
  const [showDebug, setShowDebug] = useState(false)
  const [tier, setTier] = useState<WallpaperTier>('poster')
  const [fps, setFps] = useState(0)
  const pathname = usePathname()
  const [viewMode, setViewModeState] = useState<WallpaperViewMode>('crop')

  useEffect(() => {
    const orientation = window.matchMedia('(orientation: portrait)')
    const applyMode = () => {
      const saved = window.localStorage.getItem('wallpaper-view-mode')
      setViewModeState(
        saved === 'crop' || saved === 'cinema'
          ? saved
          : orientation.matches
            ? 'cinema'
            : 'crop',
      )
    }
    applyMode()
    orientation.addEventListener('change', applyMode)
    return () => orientation.removeEventListener('change', applyMode)
  }, [])

  const setViewMode = useCallback((mode: WallpaperViewMode) => {
    window.localStorage.setItem('wallpaper-view-mode', mode)
    setViewModeState(mode)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let frame = 0
    const updateParallax = () => {
      frame = 0
      const offset = reducedMotion.matches ? 0 : Math.max(-32, -window.scrollY * 0.035)
      root.style.setProperty('--wallpaper-parallax', `${offset}px`)
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateParallax)
    }
    updateParallax()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  useEffect(() => {
    const cards = Array.from(document.querySelectorAll<HTMLElement>('main .glass'))
    cards.forEach((card) => card.classList.add('motion-card'))
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      cards.forEach((card) => card.classList.add('is-inview'))
      return
    }
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => entry.target.classList.toggle('is-inview', entry.isIntersecting)),
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    cards.forEach((card) => observer.observe(card))
    return () => observer.disconnect()
  }, [pathname])

  const onTier = useCallback((t: WallpaperTier) => setTier(t), [])
  const onFps = useCallback((v: number) => setFps(v), [])

  const value = useMemo(
    () => ({
      forceTier,
      allowVideoFallback,
      showDebug,
      tier,
      fps,
      viewMode,
      setForceTier,
      setAllowVideoFallback,
      setShowDebug,
      setViewMode,
    }),
    [forceTier, allowVideoFallback, showDebug, tier, fps, viewMode, setViewMode],
  )

  return (
    <WallpaperLabContext.Provider value={value}>
      <WallpaperBackground
        forceTier={forceTier}
        allowVideoFallback={allowVideoFallback}
        showDebug={showDebug}
        viewMode={viewMode}
        onTier={onTier}
        onFps={onFps}
      />
      {children}
    </WallpaperLabContext.Provider>
  )
}
