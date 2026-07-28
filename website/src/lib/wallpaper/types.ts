/** Forgotten Ruins web player — shared types (no Steam assets). */

export type WallpaperTier = 'webgl' | 'video' | 'poster'
export type WallpaperViewMode = 'crop' | 'cinema'

export type WaterRipplePass = {
  type: 'waterripple'
  mask?: string | null
  scale: number
  ripplestrength: number
  scrollspeed: number
  animationspeed: number
  ratio: number
  scrolldirection: number
}

export type WaterWavesPass = {
  type: 'waterwaves'
  mask?: string | null
  direction: number
  scale: number
  speed: number
  strength: number
  perspective: number
}

export type ScenePass = WaterRipplePass | WaterWavesPass

export type SceneParticle = {
  name?: string
  origin: number[]
  scale: number
  rate: number
  size?: number | null
  alpha?: number | null
  color?: number[] | null
}

export type RuinsScene = {
  version: number
  size: [number, number]
  base: string
  rippleNormal: string
  passes: ScenePass[]
  particles?: SceneParticle[]
}

export type PlayerStats = {
  fps: number
  tier: WallpaperTier
  width: number
  height: number
  passes: number
  ready: boolean
}
