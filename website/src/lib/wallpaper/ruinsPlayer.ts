/**
 * Thin WebGL1 Forgotten Ruins player.
 * Ping-pong FBO chain: base plate → waterripple/waterwaves passes → screen.
 * Optional lightweight snow particles (additive). No WASM.
 */

import { DEFAULT_RUINS_SCENE } from './defaultScene'
import type { RuinsScene, ScenePass, WaterRipplePass, WaterWavesPass } from './types'

export type RuinsPlayerOptions = {
  canvas: HTMLCanvasElement
  /** Absolute or site-relative URL prefix helper */
  resolveUrl: (path: string) => string
  /** Poster used when base.webp missing */
  posterUrl: string
  /** Asset root for relative mask paths, e.g. /media/ruins */
  assetRoot?: string
  scene?: RuinsScene
  maxDpr?: number
  maxDimension?: number
  enableParticles?: boolean
  onReady?: () => void
  onError?: (err: Error) => void
  onFps?: (fps: number) => void
}

type GL = WebGLRenderingContext

type FBO = {
  fb: WebGLFramebuffer
  tex: WebGLTexture
  w: number
  h: number
}

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`

const FRAG_COPY = `
precision mediump float;
varying vec2 v_uv;
uniform sampler2D u_tex;
void main() {
  gl_FragColor = texture2D(u_tex, v_uv);
}
`

const FRAG_WAVES = `
precision mediump float;
varying vec2 v_uv;
uniform sampler2D u_fb;
uniform sampler2D u_mask;
uniform float u_time;
uniform float u_speed;
uniform float u_scale;
uniform float u_strength;
uniform float u_perspective;
uniform vec2 u_dir;
void main() {
  float mask = texture2D(u_mask, v_uv).r;
  vec2 tc = v_uv;
  float pos = abs(dot(tc - 0.5, u_dir));
  float dist = u_time * u_speed + dot(tc, u_dir) * (u_scale + u_perspective * pos);
  vec2 offset = vec2(u_dir.y, -u_dir.x);
  float strength = u_strength * u_strength + u_perspective * pos;
  tc += sin(dist) * offset * strength * mask;
  gl_FragColor = texture2D(u_fb, tc);
}
`

const FRAG_RIPPLE = `
precision mediump float;
varying vec2 v_uv;
uniform sampler2D u_fb;
uniform sampler2D u_mask;
uniform sampler2D u_normal;
uniform float u_time;
uniform float u_strength;
uniform float u_scale;
uniform float u_anim;
uniform float u_scroll;
uniform float u_dir;
uniform float u_ratio;
uniform float u_aspect;
void main() {
  float mask = texture2D(u_mask, v_uv).r;
  float pi = 3.14159265;
  vec2 scroll = vec2(sin(u_dir), -cos(u_dir)) * u_scroll * u_scroll * u_time;
  vec2 c1 = v_uv + u_time * u_anim * u_anim + scroll;
  vec2 c2 = v_uv * 1.333 - u_time * u_anim * u_anim + scroll;
  c1 *= u_scale;
  c2 *= u_scale;
  c1.x *= u_aspect;
  c2.x *= u_aspect;
  c1.y *= u_ratio;
  c2.y *= u_ratio;
  vec3 n1 = texture2D(u_normal, c1).xyz * 2.0 - 1.0;
  vec3 n2 = texture2D(u_normal, c2).xyz * 2.0 - 1.0;
  vec3 n = normalize(vec3(n1.xy + n2.xy, n1.z));
  vec2 tc = v_uv + n.xy * u_strength * u_strength * mask;
  gl_FragColor = texture2D(u_fb, tc);
}
`

const VERT_PARTICLE = `
attribute vec2 a_pos;
attribute vec2 a_center;
attribute float a_size;
attribute vec4 a_color;
varying vec4 v_color;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  v_color = a_color;
  gl_Position = vec4(a_center + a_pos * a_size, 0.0, 1.0);
}
`

const FRAG_PARTICLE = `
precision mediump float;
varying vec4 v_color;
varying vec2 v_uv;
void main() {
  vec2 d = v_uv - 0.5;
  float a = exp(-dot(d, d) * 18.0);
  gl_FragColor = vec4(v_color.rgb, v_color.a * a);
}
`

function compile(gl: GL, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!
  gl.shaderSource(s, src)
  gl.compileShader(s)
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s) || 'shader compile failed'
    gl.deleteShader(s)
    throw new Error(log)
  }
  return s
}

function program(gl: GL, vs: string, fs: string): WebGLProgram {
  const p = gl.createProgram()!
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs))
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs))
  gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(p) || 'link failed')
  }
  return p
}

function createTexture(gl: GL): WebGLTexture {
  const t = gl.createTexture()!
  gl.bindTexture(gl.TEXTURE_2D, t)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  return t
}

function createFBO(gl: GL, w: number, h: number): FBO {
  const tex = createTexture(gl)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
  const fb = gl.createFramebuffer()!
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb)
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0)
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER)
  gl.bindFramebuffer(gl.FRAMEBUFFER, null)
  if (status !== gl.FRAMEBUFFER_COMPLETE) {
    throw new Error('framebuffer incomplete')
  }
  return { fb, tex, w, h }
}

function loadImage(url: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = url
  })
}

function uploadImage(gl: GL, tex: WebGLTexture, img: HTMLImageElement, repeat = false) {
  gl.bindTexture(gl.TEXTURE_2D, tex)
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, 1)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  const wrap = repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap)
}

function solidTexture(gl: GL, r: number, g: number, b: number, a = 255): WebGLTexture {
  const t = createTexture(gl)
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.RGBA,
    1,
    1,
    0,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    new Uint8Array([r, g, b, a]),
  )
  return t
}

/** Cheap procedural ripple normal when workshop normal is absent. */
function proceduralNormal(gl: GL, size = 128): WebGLTexture {
  const data = new Uint8Array(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size
      const v = y / size
      const nx = Math.sin(u * Math.PI * 6) * 0.35 + Math.sin(v * Math.PI * 4) * 0.2
      const ny = Math.cos(v * Math.PI * 5) * 0.35 + Math.cos(u * Math.PI * 3) * 0.2
      const i = (y * size + x) * 4
      data[i] = Math.round((nx * 0.5 + 0.5) * 255)
      data[i + 1] = Math.round((ny * 0.5 + 0.5) * 255)
      data[i + 2] = 255
      data[i + 3] = 255
    }
  }
  const t = createTexture(gl)
  gl.bindTexture(gl.TEXTURE_2D, t)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, size, size, 0, gl.RGBA, gl.UNSIGNED_BYTE, data)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT)
  return t
}

function rotateDir(radians: number): [number, number] {
  // WE: rotateVec2(vec2(0,-1), g_Direction)
  const c = Math.cos(radians)
  const s = Math.sin(radians)
  const x = 0
  const y = -1
  return [x * c - y * s, x * s + y * c]
}

type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
  r: number
  g: number
  b: number
  a: number
}

export class RuinsPlayer {
  private gl: GL
  private opts: RuinsPlayerOptions
  private scene: RuinsScene
  private disposed = false
  private running = false
  private visible = true
  private raf = 0
  private startedAt = 0
  private lastFps = 0
  private frames = 0

  private quad!: WebGLBuffer
  private progCopy!: WebGLProgram
  private progWaves!: WebGLProgram
  private progRipple!: WebGLProgram
  private progParticle!: WebGLProgram | null

  private baseTex!: WebGLTexture
  private normalTex!: WebGLTexture
  private whiteMask!: WebGLTexture
  private maskTex = new Map<string, WebGLTexture>()
  private fboA: FBO | null = null
  private fboB: FBO | null = null
  private drawW = 0
  private drawH = 0

  private particles: Particle[] = []
  private particleBuf: WebGLBuffer | null = null
  private enableParticles: boolean

  width = 0
  height = 0
  ready = false
  fps = 0
  passCount = 0

  constructor(opts: RuinsPlayerOptions) {
    const gl = opts.canvas.getContext('webgl', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
      preserveDrawingBuffer: false,
    })
    if (!gl) throw new Error('WebGL unavailable')
    this.gl = gl
    this.opts = opts
    this.scene = opts.scene || DEFAULT_RUINS_SCENE
    this.passCount = this.scene.passes.length
    this.enableParticles = opts.enableParticles !== false
  }

  async init(): Promise<void> {
    const gl = this.gl
    this.progCopy = program(gl, VERT, FRAG_COPY)
    this.progWaves = program(gl, VERT, FRAG_WAVES)
    this.progRipple = program(gl, VERT, FRAG_RIPPLE)
    try {
      this.progParticle = program(gl, VERT_PARTICLE, FRAG_PARTICLE)
    } catch {
      this.progParticle = null
    }

    this.quad = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)

    this.whiteMask = solidTexture(gl, 255, 255, 255)
    this.baseTex = createTexture(gl)
    this.normalTex = createTexture(gl)

    const root = this.opts.assetRoot || '/media/ruins'
    const resolve = (p: string) => {
      if (p.startsWith('http') || p.startsWith('data:')) return p
      if (p.startsWith('/')) return this.opts.resolveUrl(p)
      return this.opts.resolveUrl(`${root}/${p}`)
    }

    const baseUrl = resolve(this.scene.base)
    let baseImg = await loadImage(baseUrl)
    if (!baseImg) {
      baseImg = await loadImage(this.opts.posterUrl)
    }
    if (!baseImg) throw new Error('failed to load base plate / poster')
    uploadImage(gl, this.baseTex, baseImg)

    const normalImg = await loadImage(resolve(this.scene.rippleNormal))
    if (normalImg) {
      uploadImage(gl, this.normalTex, normalImg, true)
    } else {
      this.normalTex = proceduralNormal(gl)
    }

    const maskKeys = new Set<string>()
    for (const pass of this.scene.passes) {
      if (pass.mask) maskKeys.add(pass.mask)
    }
    await Promise.all(
      Array.from(maskKeys).map(async (key) => {
        const img = await loadImage(resolve(key))
        if (img) {
          const t = createTexture(gl)
          uploadImage(gl, t, img)
          this.maskTex.set(key, t)
        }
      }),
    )

    if (this.enableParticles && this.progParticle) {
      this.particleBuf = gl.createBuffer()
      this.seedParticles()
    }

    this.resize()
    this.ready = true
    this.opts.onReady?.()
  }

  private seedParticles() {
    // Lightweight stub: soft snow flakes drifting down (not full WE emitters).
    const count = 48
    this.particles = []
    for (let i = 0; i < count; i++) {
      this.particles.push(this.spawnParticle(true))
    }
  }

  private spawnParticle(randomLife = false): Particle {
    return {
      x: Math.random() * 2 - 1,
      y: randomLife ? Math.random() * 2 - 1 : 1.1,
      vx: (Math.random() - 0.5) * 0.04,
      vy: -0.05 - Math.random() * 0.08,
      life: randomLife ? Math.random() : 0,
      maxLife: 6 + Math.random() * 8,
      size: 0.004 + Math.random() * 0.01,
      r: 0.85 + Math.random() * 0.15,
      g: 0.9 + Math.random() * 0.1,
      b: 1,
      a: 0.25 + Math.random() * 0.35,
    }
  }

  resize = () => {
    if (this.disposed) return
    const canvas = this.opts.canvas
    const maxDpr = this.opts.maxDpr ?? 2
    const maxDim = this.opts.maxDimension ?? 1920
    const dpr = Math.min(window.devicePixelRatio || 1, maxDpr)
    let w = Math.max(1, Math.floor(canvas.clientWidth * dpr))
    let h = Math.max(1, Math.floor(canvas.clientHeight * dpr))
    const longest = Math.max(w, h)
    if (longest > maxDim) {
      const s = maxDim / longest
      w = Math.max(1, Math.floor(w * s))
      h = Math.max(1, Math.floor(h * s))
    }
    if (w === this.drawW && h === this.drawH) return
    canvas.width = w
    canvas.height = h
    this.drawW = w
    this.drawH = h
    this.width = w
    this.height = h
    this.gl.viewport(0, 0, w, h)
    this.rebuildFBOs(w, h)
  }

  private rebuildFBOs(w: number, h: number) {
    const gl = this.gl
    for (const f of [this.fboA, this.fboB]) {
      if (!f) continue
      gl.deleteFramebuffer(f.fb)
      gl.deleteTexture(f.tex)
    }
    this.fboA = createFBO(gl, w, h)
    this.fboB = createFBO(gl, w, h)
  }

  start() {
    if (this.disposed || this.running) return
    this.running = true
    this.startedAt = performance.now()
    this.lastFps = performance.now()
    const loop = (now: number) => {
      if (!this.running || this.disposed) return
      this.raf = requestAnimationFrame(loop)
      if (!this.visible || document.hidden) return
      this.frame((now - this.startedAt) / 1000)
      this.frames++
      const dt = now - this.lastFps
      if (dt >= 500) {
        this.fps = (this.frames * 1000) / dt
        this.frames = 0
        this.lastFps = now
        this.opts.onFps?.(this.fps)
      }
    }
    this.raf = requestAnimationFrame(loop)
  }

  setVisible(v: boolean) {
    this.visible = v
  }

  stop() {
    this.running = false
    if (this.raf) cancelAnimationFrame(this.raf)
    this.raf = 0
  }

  dispose() {
    this.stop()
    this.disposed = true
    const gl = this.gl
    for (const f of [this.fboA, this.fboB]) {
      if (!f) continue
      gl.deleteFramebuffer(f.fb)
      gl.deleteTexture(f.tex)
    }
    gl.deleteTexture(this.baseTex)
    gl.deleteTexture(this.normalTex)
    gl.deleteTexture(this.whiteMask)
    this.maskTex.forEach((t) => gl.deleteTexture(t))
    gl.deleteBuffer(this.quad)
    if (this.particleBuf) gl.deleteBuffer(this.particleBuf)
    gl.deleteProgram(this.progCopy)
    gl.deleteProgram(this.progWaves)
    gl.deleteProgram(this.progRipple)
    if (this.progParticle) gl.deleteProgram(this.progParticle)
  }

  private maskFor(pass: ScenePass): WebGLTexture {
    if (pass.mask && this.maskTex.has(pass.mask)) return this.maskTex.get(pass.mask)!
    return this.whiteMask
  }

  private drawQuad(prog: WebGLProgram) {
    const gl = this.gl
    const loc = gl.getAttribLocation(prog, 'a_pos')
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad)
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }

  private bindTex(unit: number, tex: WebGLTexture, prog: WebGLProgram, name: string) {
    const gl = this.gl
    gl.activeTexture(gl.TEXTURE0 + unit)
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.uniform1i(gl.getUniformLocation(prog, name), unit)
  }

  private frame(time: number) {
    const gl = this.gl
    if (!this.fboA || !this.fboB) return
    const aspect = this.drawW / Math.max(1, this.drawH)

    // Pass 0: draw base → A
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboA.fb)
    gl.viewport(0, 0, this.drawW, this.drawH)
    gl.useProgram(this.progCopy)
    this.bindTex(0, this.baseTex, this.progCopy, 'u_tex')
    this.drawQuad(this.progCopy)

    let read = this.fboA
    let write = this.fboB

    for (const pass of this.scene.passes) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, write.fb)
      if (pass.type === 'waterwaves') {
        this.drawWaves(pass, read.tex, time)
      } else {
        this.drawRipple(pass, read.tex, time, aspect)
      }
      const tmp = read
      read = write
      write = tmp
    }

    // To screen
    gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    gl.viewport(0, 0, this.drawW, this.drawH)
    gl.useProgram(this.progCopy)
    this.bindTex(0, read.tex, this.progCopy, 'u_tex')
    this.drawQuad(this.progCopy)

    if (this.enableParticles && this.progParticle && this.particleBuf) {
      this.updateAndDrawParticles(time)
    }
  }

  private drawWaves(pass: WaterWavesPass, src: WebGLTexture, time: number) {
    const gl = this.gl
    const p = this.progWaves
    gl.useProgram(p)
    this.bindTex(0, src, p, 'u_fb')
    this.bindTex(1, this.maskFor(pass), p, 'u_mask')
    gl.uniform1f(gl.getUniformLocation(p, 'u_time'), time)
    gl.uniform1f(gl.getUniformLocation(p, 'u_speed'), pass.speed)
    gl.uniform1f(gl.getUniformLocation(p, 'u_scale'), pass.scale)
    gl.uniform1f(gl.getUniformLocation(p, 'u_strength'), pass.strength)
    gl.uniform1f(gl.getUniformLocation(p, 'u_perspective'), pass.perspective)
    const [dx, dy] = rotateDir(pass.direction)
    gl.uniform2f(gl.getUniformLocation(p, 'u_dir'), dx, dy)
    this.drawQuad(p)
  }

  private drawRipple(pass: WaterRipplePass, src: WebGLTexture, time: number, aspect: number) {
    const gl = this.gl
    const p = this.progRipple
    gl.useProgram(p)
    this.bindTex(0, src, p, 'u_fb')
    this.bindTex(1, this.maskFor(pass), p, 'u_mask')
    this.bindTex(2, this.normalTex, p, 'u_normal')
    gl.uniform1f(gl.getUniformLocation(p, 'u_time'), time)
    gl.uniform1f(gl.getUniformLocation(p, 'u_strength'), pass.ripplestrength)
    gl.uniform1f(gl.getUniformLocation(p, 'u_scale'), pass.scale)
    gl.uniform1f(gl.getUniformLocation(p, 'u_anim'), pass.animationspeed)
    gl.uniform1f(gl.getUniformLocation(p, 'u_scroll'), pass.scrollspeed)
    gl.uniform1f(gl.getUniformLocation(p, 'u_dir'), pass.scrolldirection)
    gl.uniform1f(gl.getUniformLocation(p, 'u_ratio'), pass.ratio)
    gl.uniform1f(gl.getUniformLocation(p, 'u_aspect'), aspect)
    this.drawQuad(p)
  }

  private updateAndDrawParticles(_time: number) {
    const gl = this.gl
    const prog = this.progParticle!
    const dt = 1 / 60
    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i]
      p.life += dt
      p.x += p.vx * dt
      p.y += p.vy * dt
      if (p.life > p.maxLife || p.y < -1.2) {
        this.particles[i] = this.spawnParticle(false)
      }
    }

    // Interleaved: pos(2) + center(2) + size(1) + color(4) per vertex × 6 verts
    const strideFloats = 9
    const data = new Float32Array(this.particles.length * 6 * strideFloats)
    const corners = [
      [-1, -1],
      [1, -1],
      [-1, 1],
      [-1, 1],
      [1, -1],
      [1, 1],
    ]
    let o = 0
    for (const p of this.particles) {
      const fade = Math.min(1, p.life * 2) * Math.min(1, (p.maxLife - p.life) * 0.5)
      for (const [cx, cy] of corners) {
        data[o++] = cx
        data[o++] = cy
        data[o++] = p.x
        data[o++] = p.y
        data[o++] = p.size
        data[o++] = p.r
        data[o++] = p.g
        data[o++] = p.b
        data[o++] = p.a * fade
      }
    }

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE)
    gl.useProgram(prog)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.particleBuf)
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW)
    const stride = strideFloats * 4
    const aPos = gl.getAttribLocation(prog, 'a_pos')
    const aCenter = gl.getAttribLocation(prog, 'a_center')
    const aSize = gl.getAttribLocation(prog, 'a_size')
    const aColor = gl.getAttribLocation(prog, 'a_color')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, stride, 0)
    gl.enableVertexAttribArray(aCenter)
    gl.vertexAttribPointer(aCenter, 2, gl.FLOAT, false, stride, 8)
    gl.enableVertexAttribArray(aSize)
    gl.vertexAttribPointer(aSize, 1, gl.FLOAT, false, stride, 16)
    gl.enableVertexAttribArray(aColor)
    gl.vertexAttribPointer(aColor, 4, gl.FLOAT, false, stride, 20)
    gl.drawArrays(gl.TRIANGLES, 0, this.particles.length * 6)
    gl.disable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  }
}

export async function loadRuinsScene(resolveUrl: (p: string) => string): Promise<RuinsScene> {
  try {
    const res = await fetch(resolveUrl('/media/ruins/scene.gen.json'), { cache: 'force-cache' })
    if (res.ok) {
      const json = (await res.json()) as RuinsScene
      if (json?.passes?.length) return json
    }
  } catch {
    /* use defaults */
  }
  return DEFAULT_RUINS_SCENE
}
