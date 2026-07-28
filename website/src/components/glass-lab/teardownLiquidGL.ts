type LiquidGLWindow = Window & {
  __liquidGLRenderer__?: {
    _rafId?: number | null
    canvas?: HTMLCanvasElement
    lenses?: Array<{
      setShadow?: (enabled: boolean) => void
      _sizeObs?: { disconnect: () => void }
      _unbindTiltHandlers?: () => void
      _shadowEl?: HTMLElement | null
    }>
  }
  __liquidGLNoWebGL__?: boolean
}

/** Tear down the liquid-gl singleton so lab remounts stay clean. */
export function teardownLiquidGL() {
  if (typeof window === 'undefined') return

  const w = window as LiquidGLWindow
  const renderer = w.__liquidGLRenderer__
  if (!renderer) return

  if (renderer._rafId) {
    cancelAnimationFrame(renderer._rafId)
    renderer._rafId = null
  }

  renderer.lenses?.forEach((lens) => {
    try {
      lens.setShadow?.(false)
      lens._unbindTiltHandlers?.()
      lens._sizeObs?.disconnect()
      lens._shadowEl?.remove()
    } catch {
      /* ignore */
    }
  })

  renderer.canvas?.remove()
  delete w.__liquidGLRenderer__
}
