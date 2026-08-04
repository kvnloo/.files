/**
 * liquid-glass-wal — Hermes Desktop runtime plugin (ESM only, no JSX).
 *
 * Polls pywal-built theme JSON and installs/activates `liquid-glass-wal`
 * with glass mix knobs. Wired from .files apply-pywal-theme.sh.
 *
 * IMPORTANT: never location.reload() on the poll path — that caused a 2.5–5s
 * full-window flash. Wallpaper changes apply live via CSS seeds + localStorage.
 *
 * Theme files (first hit wins):
 *   ~/.hermes/liquid-glass-wal/theme.json
 *   ~/.cache/wal/hermes-liquid-glass-theme.json
 */
import { host, PALETTE_AREA, THEMES_AREA } from '@hermes/plugin-sdk'

const ID = 'liquid-glass-wal'
const THEME_NAME = 'liquid-glass-wal'

const USER_THEMES_KEY = 'hermes-desktop-user-themes-v1'
const SKIN_KEY = 'hermes-desktop-theme-v2'
const MODE_KEY = 'hermes-desktop-mode-v1'
const PROFILE_SKINS_KEY = 'hermes-desktop-profile-themes-v1'
const PROFILE_MODES_KEY = 'hermes-desktop-profile-modes-v1'
const GLASS_KNOBS_KEY = 'hermes-desktop-glass-knobs-v1'
const AUTO_KEY = 'hermes.liquid-glass-wal.auto'
const LAST_HASH_KEY = 'hermes.liquid-glass-wal.lastHash'
const PATH_CACHE_KEY = 'hermes.liquid-glass-wal.themePath'
const POLL_MS = 4000

function readAuto() {
  try {
    const v = localStorage.getItem(AUTO_KEY)
    return v === null ? true : v === '1' || v === 'true'
  } catch {
    return true
  }
}

function setAuto(on) {
  try {
    localStorage.setItem(AUTO_KEY, on ? '1' : '0')
  } catch {
    /* ignore */
  }
}

function guessHomes() {
  const homes = []
  try {
    const cached = localStorage.getItem(PATH_CACHE_KEY)
    if (cached && cached.includes('/')) {
      const m = cached.match(/^(.*)\/(?:\.hermes|\.cache)\//)
      if (m) homes.push(m[1])
    }
  } catch {
    /* ignore */
  }
  homes.push('/home/kvn')
  return [...new Set(homes)]
}

function themeCandidates() {
  const out = []
  try {
    const cached = localStorage.getItem(PATH_CACHE_KEY)
    if (cached) out.push(cached)
  } catch {
    /* ignore */
  }
  for (const home of guessHomes()) {
    out.push(
      `${home}/.hermes/liquid-glass-wal/theme.json`,
      `${home}/.cache/wal/hermes-liquid-glass-theme.json`
    )
  }
  return [...new Set(out)]
}

function themeHash(theme) {
  try {
    const c = theme?.colors || {}
    const g = theme?.hermesGlass || {}
    const w = theme?.hermesWal || {}
    return [
      c.background,
      c.foreground,
      c.primary,
      c.sidebarBackground,
      c.card,
      g.chrome,
      g.card,
      w.wallpaper,
      w.builtAt
    ].join('|')
  } catch {
    return String(Math.random())
  }
}

function applyGlassKnobs(knobs) {
  if (typeof document === 'undefined' || !knobs) return
  const root = document.documentElement
  if (knobs.chrome) root.style.setProperty('--theme-mix-chrome', knobs.chrome)
  if (knobs.sidebar) root.style.setProperty('--theme-mix-sidebar', knobs.sidebar)
  if (knobs.card) root.style.setProperty('--theme-mix-card', knobs.card)
  if (knobs.elevated) root.style.setProperty('--theme-mix-elevated', knobs.elevated)
  if (knobs.bubble) root.style.setProperty('--theme-mix-bubble', knobs.bubble)
  root.style.setProperty('--dt-input-bg', '0%')
}

function stripPluginFields(theme) {
  const next = { ...theme }
  delete next.hermesGlass
  delete next.hermesWal
  return next
}

function textFromRead(res) {
  if (typeof res === 'string') return res
  if (!res || typeof res !== 'object') return null
  return res.content || res.text || res.data || null
}

/** Live-paint seeds so ThemeProvider does not need a full reload. */
function paintSeeds(theme) {
  try {
    const c = theme.colors || {}
    const root = document.documentElement
    const mode = theme.hermesWal?.isDark === false ? 'light' : 'dark'
    if (c.background) root.style.setProperty('--theme-background-seed', c.background)
    if (c.foreground) root.style.setProperty('--theme-foreground', c.foreground)
    if (c.primary) {
      root.style.setProperty('--theme-primary', c.primary)
      root.style.setProperty('--theme-midground', c.midground || c.primary)
      root.style.setProperty('--theme-secondary', c.secondary || c.primary)
      root.style.setProperty('--theme-accent-soft', c.accent || c.primary)
    }
    if (c.sidebarBackground) root.style.setProperty('--theme-sidebar-seed', c.sidebarBackground)
    if (c.card) root.style.setProperty('--theme-card-seed', c.card)
    if (c.popover) root.style.setProperty('--theme-elevated-seed', c.popover)
    if (c.userBubble) root.style.setProperty('--theme-bubble-seed', c.userBubble)
    if (c.border) root.style.setProperty('--dt-border', c.border)
    if (c.ring) root.style.setProperty('--dt-ring', c.ring)
    root.classList.toggle('dark', mode === 'dark')
    root.dataset.hermesTheme = THEME_NAME
    root.dataset.hermesMode = mode
    root.style.setProperty('color-scheme', mode)
    applyGlassKnobs(theme.hermesGlass)
    window.hermesDesktop?.setTitleBarTheme?.({
      background: c.background,
      foreground: c.foreground
    })
    window.hermesDesktop?.setNativeTheme?.(mode)
  } catch {
    /* ignore */
  }
}

function installTheme(theme, { activate }) {
  const clean = stripPluginFields(theme)
  clean.name = THEME_NAME
  if (!clean.label) clean.label = 'Liquid Glass (pywal)'

  let store = {}
  try {
    store = JSON.parse(localStorage.getItem(USER_THEMES_KEY) || '{}') || {}
  } catch {
    store = {}
  }
  if (!store || typeof store !== 'object' || Array.isArray(store)) store = {}
  store[THEME_NAME] = clean
  localStorage.setItem(USER_THEMES_KEY, JSON.stringify(store))

  if (theme.hermesGlass) {
    localStorage.setItem(GLASS_KNOBS_KEY, JSON.stringify(theme.hermesGlass))
  }

  if (activate) {
    localStorage.setItem(SKIN_KEY, THEME_NAME)
    const mode = theme.hermesWal?.isDark === false ? 'light' : 'dark'
    localStorage.setItem(MODE_KEY, mode)
    try {
      const skins = JSON.parse(localStorage.getItem(PROFILE_SKINS_KEY) || '{}') || {}
      skins.default = THEME_NAME
      localStorage.setItem(PROFILE_SKINS_KEY, JSON.stringify(skins))
      const modes = JSON.parse(localStorage.getItem(PROFILE_MODES_KEY) || '{}') || {}
      modes.default = mode
      localStorage.setItem(PROFILE_MODES_KEY, JSON.stringify(modes))
    } catch {
      /* ignore */
    }
    paintSeeds(theme)
  }

  return clean
}

async function readThemeFile() {
  const api = window.hermesDesktop?.readFileText
  if (!api) return null
  for (const path of themeCandidates()) {
    try {
      const res = await api(path)
      const text = textFromRead(res)
      if (!text) continue
      const theme = JSON.parse(text)
      if (!theme?.colors) continue
      try {
        localStorage.setItem(PATH_CACHE_KEY, path)
      } catch {
        /* ignore */
      }
      return { path, theme, hash: themeHash(theme) }
    } catch {
      /* try next */
    }
  }
  return null
}

export default {
  id: ID,
  name: 'Liquid Glass (pywal)',
  description: 'Pywal + Hyprland liquid glass theme for Hermes Desktop.',
  defaultEnabled: true,
  register(ctx) {
    let disposeTheme = () => {}
    let lastPublishedHash = ''
    let contributed = {
      name: THEME_NAME,
      label: 'Liquid Glass (pywal)',
      description: 'Waiting for pywal…',
      colors: {
        background: '#181f23',
        foreground: '#d1deda',
        card: '#1c252a',
        cardForeground: '#d1deda',
        muted: '#1a2328',
        mutedForeground: '#929b98',
        popover: '#1e282e',
        popoverForeground: '#d1deda',
        primary: '#4FA5B3',
        primaryForeground: '#0c0c0e',
        secondary: '#243037',
        secondaryForeground: '#d1deda',
        accent: '#243037',
        accentForeground: '#d1deda',
        border: '#3a4a52',
        input: '#181f23',
        ring: '#4FA5B3',
        midground: '#4FA5B3',
        destructive: '#e75e78',
        destructiveForeground: '#ffffff'
      }
    }

    const publishTheme = (theme, hash) => {
      if (hash && hash === lastPublishedHash) return
      if (theme?.colors) {
        contributed = {
          ...stripPluginFields(theme),
          name: THEME_NAME,
          label: theme.label || 'Liquid Glass (pywal)'
        }
      }
      disposeTheme()
      if (typeof THEMES_AREA === 'string') {
        disposeTheme = ctx.register({
          id: `${ID}:theme`,
          area: THEMES_AREA,
          order: 5,
          data: contributed
        })
      }
      if (hash) lastPublishedHash = hash
    }

    publishTheme(contributed, 'seed')

    ctx.register({
      id: `${ID}:sync`,
      area: PALETTE_AREA,
      data: {
        id: `${ID}.sync`,
        label: 'Liquid Glass: sync from pywal now',
        keywords: ['pywal', 'wallpaper', 'theme', 'glass', 'liquid', 'wal'],
        run: async () => {
          const got = await readThemeFile()
          if (!got) {
            host.toast?.({
              title: 'Liquid Glass',
              message: 'No theme file — run wal / change wallpaper once.',
              tone: 'warn'
            })
            return
          }
          publishTheme(got.theme, got.hash)
          installTheme(got.theme, { activate: true })
          localStorage.setItem(LAST_HASH_KEY, got.hash)
          host.toast?.({
            title: 'Liquid Glass',
            message: `Synced · ${got.theme?.hermesWal?.accent || 'ok'}`,
            tone: 'success'
          })
          // Manual sync only: one reload so ThemeProvider fully re-reads registry.
          location.reload()
        }
      }
    })

    ctx.register({
      id: `${ID}:toggle-auto`,
      area: PALETTE_AREA,
      data: {
        id: `${ID}.toggleAuto`,
        label: 'Liquid Glass: toggle auto-apply on wallpaper change',
        run: () => {
          const next = !readAuto()
          setAuto(next)
          host.toast?.({
            title: 'Liquid Glass',
            message: next ? 'Auto-apply ON' : 'Auto-apply OFF',
            tone: 'info'
          })
        }
      }
    })

    let stopped = false
    let lastAppliedHash = ''
    try {
      lastAppliedHash = localStorage.getItem(LAST_HASH_KEY) || ''
    } catch {
      /* ignore */
    }

    const tick = async () => {
      if (stopped) return
      try {
        const got = await readThemeFile()
        if (!got?.theme) return

        // Only touch the contribution registry when the file actually changed.
        if (got.hash !== lastPublishedHash) {
          publishTheme(got.theme, got.hash)
        }

        if (!readAuto()) return

        if (got.hash !== lastAppliedHash) {
          installTheme(got.theme, { activate: true })
          lastAppliedHash = got.hash
          try {
            localStorage.setItem(LAST_HASH_KEY, got.hash)
          } catch {
            /* ignore */
          }
          // No location.reload() — live paintSeeds is enough and avoids flash.
          return
        }

        // Stable theme: do nothing. Re-applying knobs every poll caused flicker.
      } catch (err) {
        console.warn('[liquid-glass-wal]', err)
      }
    }

    tick()
    const interval = setInterval(tick, POLL_MS)

    // One-shot knob apply after mount (ThemeProvider may overwrite seeds once).
    const boot = () => {
      try {
        if (localStorage.getItem(SKIN_KEY) !== THEME_NAME) return
        applyGlassKnobs(JSON.parse(localStorage.getItem(GLASS_KNOBS_KEY) || 'null'))
      } catch {
        /* ignore */
      }
    }
    setTimeout(boot, 300)

    return () => {
      stopped = true
      clearInterval(interval)
      disposeTheme()
    }
  }
}
