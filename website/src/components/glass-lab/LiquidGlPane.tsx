'use client'

import { useEffect, useId, useRef, type ReactNode } from 'react'
import liquidGL, { type LiquidGLInstance } from 'liquid-gl'
import { teardownLiquidGL } from './teardownLiquidGL'

export type LiquidGlControls = {
  refraction: number
  frost: number
  bevelDepth: number
  bevelWidth: number
  specular: boolean
  tilt: boolean
  shadow: boolean
  magnify: number
}

type Props = LiquidGlControls & {
  children: ReactNode
  className?: string
  /** CSS selector for the non-fixed snapshot source (must not be position:fixed). */
  snapshot?: string
}

/**
 * Thin React wrapper around liquid-gl (vanilla WebGL).
 * Init once; live-tweak shader options via the returned instance.
 */
export function LiquidGlPane({
  children,
  className,
  snapshot = '#glass-lab-snapshot',
  refraction,
  frost,
  bevelDepth,
  bevelWidth,
  specular,
  tilt,
  shadow,
  magnify,
}: Props) {
  const reactId = useId().replace(/:/g, '')
  const targetId = `liquid-gl-target-${reactId}`
  const instanceRef = useRef<LiquidGLInstance | null>(null)
  const statusRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    let cancelled = false
    let retries = 0

    const init = () => {
      if (cancelled) return
      const el = document.getElementById(targetId)
      const snap = document.querySelector(snapshot)
      if (!el || !snap) {
        if (retries < 20) {
          retries += 1
          requestAnimationFrame(init)
        } else if (statusRef.current) {
          statusRef.current.textContent = 'liquid-gl: target/snapshot not found'
        }
        return
      }

      teardownLiquidGL()

      try {
        const result = liquidGL({
          target: `#${targetId}`,
          snapshot,
          resolution: 1.35,
          reveal: 'none',
          refraction,
          frost,
          bevelDepth,
          bevelWidth,
          specular,
          tilt,
          shadow,
          magnify,
          on: {
            init() {
              if (statusRef.current) statusRef.current.textContent = ''
            },
          },
        })

        const inst = Array.isArray(result) ? result[0] : result
        if (inst && typeof inst === 'object' && 'options' in inst) {
          instanceRef.current = inst as LiquidGLInstance
        } else if (statusRef.current) {
          statusRef.current.textContent =
            'liquid-gl: WebGL unavailable — CSS backdrop-filter fallback'
        }
      } catch (err) {
        console.warn('[glass-lab] liquid-gl init failed', err)
        if (statusRef.current) {
          statusRef.current.textContent = 'liquid-gl: init failed (see console)'
        }
      }
    }

    const t = window.setTimeout(init, 50)

    return () => {
      cancelled = true
      window.clearTimeout(t)
      instanceRef.current = null
      teardownLiquidGL()
    }
    // Intentionally mount-once; live options applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetId, snapshot])

  useEffect(() => {
    const inst = instanceRef.current
    if (!inst?.options) return

    inst.options.refraction = refraction
    inst.options.frost = frost
    inst.options.bevelDepth = bevelDepth
    inst.options.bevelWidth = bevelWidth
    inst.options.specular = specular
    inst.options.magnify = magnify

    inst.setTilt?.(tilt)
    inst.setShadow?.(shadow)
  }, [
    refraction,
    frost,
    bevelDepth,
    bevelWidth,
    specular,
    tilt,
    shadow,
    magnify,
  ])

  return (
    <div className="relative">
      <p
        ref={statusRef}
        className="mb-2 min-h-[1.25rem] font-mono text-xs text-[var(--accent-yellow)]"
        aria-live="polite"
      />
      <div
        id={targetId}
        className={className}
        style={{ zIndex: 10, borderRadius: 16 }}
      >
        <div className="relative z-[3]" style={{ pointerEvents: 'auto' }}>
          {children}
        </div>
      </div>
    </div>
  )
}
