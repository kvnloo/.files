'use client'

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { WallpaperTier } from '@/lib/wallpaper/types'
import { WallpaperBackground } from '@/components/WallpaperBackground'

type WallpaperLabState = {
  forceTier: WallpaperTier | null
  allowVideoFallback: boolean
  showDebug: boolean
  tier: WallpaperTier
  fps: number
  setForceTier: (t: WallpaperTier | null) => void
  setAllowVideoFallback: (v: boolean) => void
  setShowDebug: (v: boolean) => void
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

  const onTier = useCallback((t: WallpaperTier) => setTier(t), [])
  const onFps = useCallback((v: number) => setFps(v), [])

  const value = useMemo(
    () => ({
      forceTier,
      allowVideoFallback,
      showDebug,
      tier,
      fps,
      setForceTier,
      setAllowVideoFallback,
      setShowDebug,
    }),
    [forceTier, allowVideoFallback, showDebug, tier, fps],
  )

  return (
    <WallpaperLabContext.Provider value={value}>
      <WallpaperBackground
        forceTier={forceTier}
        allowVideoFallback={allowVideoFallback}
        showDebug={showDebug}
        onTier={onTier}
        onFps={onFps}
      />
      {children}
    </WallpaperLabContext.Provider>
  )
}
