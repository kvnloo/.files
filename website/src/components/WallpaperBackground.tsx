'use client'

import dynamic from 'next/dynamic'
import { useCallback, useEffect, useState } from 'react'
import { assetPath } from '@/lib/utils'
import { detectWallpaperTier } from '@/lib/wallpaper/capability'
import type { WallpaperTier } from '@/lib/wallpaper/types'

const RuinsWebGL = dynamic(
  () => import('@/components/wallpaper/RuinsWebGL').then((m) => m.RuinsWebGL),
  { ssr: false },
)

const POSTER_SRC = assetPath('/media/forgotten-ruins-poster.jpg')
const POSTER_WEBP = assetPath('/media/forgotten-ruins-poster.webp')
const WEBM_SRC = assetPath('/media/forgotten-ruins.webm')

type Props = {
  /** Lab override */
  forceTier?: WallpaperTier | null
  /** Prefer video over poster when WebGL is skipped (default: false — static until capable). */
  allowVideoFallback?: boolean
  showDebug?: boolean
  onTier?: (tier: WallpaperTier) => void
  onFps?: (fps: number) => void
}

/**
 * Adaptive Forgotten Ruins backdrop.
 * Always paints poster first (LCP). Enhances to WebGL when capable.
 */
export function WallpaperBackground({
  forceTier = null,
  allowVideoFallback = false,
  showDebug = false,
  onTier,
  onFps,
}: Props = {}) {
  const [tier, setTier] = useState<WallpaperTier>('poster')
  const [webglReady, setWebglReady] = useState(false)
  const [fps, setFps] = useState(0)
  const [idle, setIdle] = useState(false)

  useEffect(() => {
    const chosen = detectWallpaperTier({
      forceTier,
      allowVideo: allowVideoFallback,
    })
    setTier(chosen)
    onTier?.(chosen)

    // Defer WebGL mount until after first paint / idle
    const ric = window.requestIdleCallback
    let idleId = 0
    let timeoutId = 0
    if (typeof ric === 'function') {
      idleId = ric(() => setIdle(true), { timeout: 1200 })
    } else {
      timeoutId = window.setTimeout(() => setIdle(true), 400)
    }
    return () => {
      if (idleId && window.cancelIdleCallback) window.cancelIdleCallback(idleId)
      if (timeoutId) window.clearTimeout(timeoutId)
    }
  }, [forceTier, allowVideoFallback, onTier])

  const handleReady = useCallback(() => setWebglReady(true), [])
  const handleError = useCallback(() => {
    setTier(allowVideoFallback ? 'video' : 'poster')
    setWebglReady(false)
  }, [allowVideoFallback])
  const handleFps = useCallback(
    (v: number) => {
      setFps(v)
      onFps?.(v)
    },
    [onFps],
  )

  const showWebgl = tier === 'webgl' && idle
  const showVideo = tier === 'video' && (allowVideoFallback || forceTier === 'video')

  return (
    <div className="wallpaper-root" aria-hidden="true">
      <picture className={`wallpaper-poster-wrap${webglReady ? ' is-dimmed' : ''}`}>
        <source srcSet={POSTER_WEBP} type="image/webp" />
        <img
          className="wallpaper-poster"
          src={POSTER_SRC}
          alt=""
          decoding="async"
          fetchPriority="high"
        />
      </picture>

      {showVideo && (
        <video
          className="wallpaper-video"
          src={WEBM_SRC}
          muted
          loop
          playsInline
          autoPlay
          preload="metadata"
        />
      )}

      {showWebgl && (
        <RuinsWebGL
          posterUrl={POSTER_WEBP}
          className={`wallpaper-webgl${webglReady ? ' is-ready' : ''}`}
          onReady={handleReady}
          onError={handleError}
          onFps={handleFps}
        />
      )}

      <div className="wallpaper-scrim" />
      <div className="wallpaper-vignette" />
      <div className="wallpaper-noise" />

      {showDebug && (
        <div className="wallpaper-debug">
          tier={tier}
          {tier === 'webgl' ? ` · ${fps.toFixed(0)} fps · ${webglReady ? 'ready' : 'loading'}` : ''}
        </div>
      )}
    </div>
  )
}
