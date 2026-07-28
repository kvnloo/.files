declare module 'liquid-gl' {
  export type LiquidGLOptions = {
    target: string
    snapshot?: string
    resolution?: number
    refraction?: number
    bevelDepth?: number
    bevelWidth?: number
    frost?: number
    shadow?: boolean
    specular?: boolean
    reveal?: 'none' | 'fade'
    tilt?: boolean
    tiltFactor?: number
    magnify?: number
    on?: {
      init?: (instance: LiquidGLInstance) => void
    }
  }

  export type LiquidGLInstance = {
    el: HTMLElement
    options: LiquidGLOptions
    setTilt: (enabled: boolean) => void
    setShadow: (enabled: boolean) => void
    updateMetrics: () => void
  }

  export default function liquidGL(
    options: LiquidGLOptions,
  ): LiquidGLInstance | LiquidGLInstance[] | HTMLElement | HTMLElement[] | undefined
}
