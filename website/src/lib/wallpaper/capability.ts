import type { WallpaperTier } from './types'

export type CapabilityOptions = {
  /** Force a tier (lab / debug). */
  forceTier?: WallpaperTier | null
  /** Allow webm tier B when WebGL is skipped. Default true if asset exists. */
  allowVideo?: boolean
}

/**
 * Cheap one-shot capability gate. Poster always paints first; this only
 * decides whether to enhance.
 */
export function detectWallpaperTier(opts: CapabilityOptions = {}): WallpaperTier {
  if (typeof window === 'undefined') return 'poster'
  if (opts.forceTier) return opts.forceTier

  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
  if (reduce) return 'poster'

  const nav = navigator as Navigator & {
    connection?: { saveData?: boolean; downlink?: number; effectiveType?: string }
    deviceMemory?: number
  }
  if (nav.connection?.saveData) return 'poster'
  // Very low RAM → skip reactive tier (poster, or video if explicitly allowed)
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory > 0 && nav.deviceMemory <= 2) {
    return fallback(opts)
  }
  const downlink = nav.connection?.downlink
  if (typeof downlink === 'number' && downlink > 0 && downlink < 1.5) {
    return fallback(opts)
  }
  const et = nav.connection?.effectiveType
  if (et === 'slow-2g' || et === '2g') return 'poster'

  if (!hasWebGL()) return fallback(opts)

  return 'webgl'
}

function fallback(opts: CapabilityOptions): WallpaperTier {
  return opts.allowVideo ? 'video' : 'poster'
}

export function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl') || c.getContext('experimental-webgl'))
  } catch {
    return false
  }
}
