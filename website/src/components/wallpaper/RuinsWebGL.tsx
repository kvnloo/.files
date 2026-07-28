'use client'

import { useEffect, useRef, useState } from 'react'
import { assetPath } from '@/lib/utils'
import { loadRuinsScene, RuinsPlayer } from '@/lib/wallpaper/ruinsPlayer'
import type { RuinsScene } from '@/lib/wallpaper/types'

type Props = {
  posterUrl: string
  className?: string
  scene?: RuinsScene
  maxDpr?: number
  enableParticles?: boolean
  onReady?: () => void
  onError?: (err: Error) => void
  onFps?: (fps: number) => void
  /** Lab: expose player stats via callback each second */
  debug?: boolean
}

/**
 * Client-only WebGL Forgotten Ruins layer. Parent keeps the poster under this
 * canvas and crossfades once the first frame is ready.
 */
export function RuinsWebGL({
  posterUrl,
  className,
  scene,
  maxDpr = 2,
  enableParticles = true,
  onReady,
  onError,
  onFps,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let player: RuinsPlayer | null = null
    let cancelled = false
    let resizeObs: ResizeObserver | null = null
    let io: IntersectionObserver | null = null

    const onVis = () => {
      player?.setVisible(!document.hidden)
    }

    ;(async () => {
      try {
        const resolved = scene || (await loadRuinsScene(assetPath))
        if (cancelled) return
        player = new RuinsPlayer({
          canvas,
          resolveUrl: assetPath,
          posterUrl,
          assetRoot: '/media/ruins',
          scene: resolved,
          maxDpr,
          maxDimension: 1920,
          enableParticles,
          onReady: () => {
            if (!cancelled) onReady?.()
          },
          onError: (e) => {
            setFailed(true)
            onError?.(e)
          },
          onFps,
        })
        await player.init()
        if (cancelled) {
          player.dispose()
          return
        }
        player.start()
        resizeObs = new ResizeObserver(() => player?.resize())
        resizeObs.observe(canvas)
        io = new IntersectionObserver(
          ([entry]) => player?.setVisible(entry.isIntersecting && !document.hidden),
          { threshold: 0.01 },
        )
        io.observe(canvas)
        document.addEventListener('visibilitychange', onVis)
      } catch (e) {
        setFailed(true)
        onError?.(e instanceof Error ? e : new Error(String(e)))
      }
    })()

    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVis)
      resizeObs?.disconnect()
      io?.disconnect()
      player?.dispose()
    }
  }, [posterUrl, scene, maxDpr, enableParticles, onReady, onError, onFps])

  if (failed) return null

  return (
    <canvas
      ref={canvasRef}
      className={className ?? 'wallpaper-webgl'}
      aria-hidden="true"
    />
  )
}
