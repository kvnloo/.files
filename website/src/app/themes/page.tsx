'use client'

import { useState } from 'react'
import { Header, Footer, GlassCard, TerminalBlock, Filter, Button } from '@/components'
import { Palette, Copy, Check, ExternalLink } from 'lucide-react'

const themes = [
  {
    name: 'shades',
    description: 'Minimal grayscale theme',
    colors: ['#1a1a1a', '#333333', '#666666', '#999999', '#cccccc'],
    style: 'minimal',
  },
  {
    name: 'cyberpunk',
    description: 'Neon-inspired cyberpunk aesthetic',
    colors: ['#ff00ff', '#00ffff', '#ff0080', '#80ff00', '#0080ff'],
    style: 'colorful',
  },
  {
    name: 'hack',
    description: 'Classic hacker green on black',
    colors: ['#0d1117', '#238636', '#3fb950', '#56d364', '#7ee787'],
    style: 'minimal',
  },
  {
    name: 'cuts',
    description: 'Clean geometric cuts theme',
    colors: ['#161b22', '#21262d', '#30363d', '#58a6ff', '#a371f7'],
    style: 'modern',
  },
  {
    name: 'docks',
    description: 'macOS dock-inspired design',
    colors: ['#1c1c1e', '#2c2c2e', '#3a3a3c', '#636366', '#ebebf5'],
    style: 'modern',
  },
  {
    name: 'forest',
    description: 'Nature-inspired forest greens',
    colors: ['#1a2f1a', '#2d4a2d', '#3d6b3d', '#4d8c4d', '#5dad5d'],
    style: 'colorful',
  },
  {
    name: 'grayblocks',
    description: 'Blocky grayscale segments',
    colors: ['#1a1a1a', '#2a2a2a', '#3a3a3a', '#4a4a4a', '#5a5a5a'],
    style: 'minimal',
  },
  {
    name: 'material',
    description: 'Google Material Design palette',
    colors: ['#121212', '#1e1e1e', '#bb86fc', '#03dac6', '#cf6679'],
    style: 'modern',
  },
  {
    name: 'shapes',
    description: 'Geometric shape accents',
    colors: ['#0d1117', '#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3'],
    style: 'colorful',
  },
  {
    name: 'waves',
    description: 'Smooth wave-inspired curves',
    colors: ['#0f0f23', '#1a1a3e', '#2d2d5a', '#4040ff', '#6060ff'],
    style: 'modern',
  },
]

const filterOptions = [
  { label: 'All', value: 'all' },
  { label: 'Minimal', value: 'minimal' },
  { label: 'Colorful', value: 'colorful' },
  { label: 'Modern', value: 'modern' },
]

export default function ThemesPage() {
  const [filter, setFilter] = useState('all')
  const [copiedTheme, setCopiedTheme] = useState<string | null>(null)

  const filteredThemes = filter === 'all'
    ? themes
    : themes.filter((t) => t.style === filter)

  const copyCommand = (themeName: string) => {
    navigator.clipboard.writeText(`stow -t ~/.config/polybar polybar/${themeName}`)
    setCopiedTheme(themeName)
    setTimeout(() => setCopiedTheme(null), 2000)
  }

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="container py-16 text-center">
          <div className="inline-flex items-center gap-3 mb-6">
            <Palette size={48} className="text-[var(--accent-purple)]" />
          </div>
          <h1 className="text-3xl md:text-5xl font-bold font-mono mb-4">
            polybar_themes/
          </h1>
          <p className="text-[var(--text-muted)] max-w-2xl mx-auto mb-8">
            10 handcrafted Polybar themes with Pywal integration for automatic color matching with your wallpaper
          </p>

          {/* Quick Install */}
          <div className="max-w-md mx-auto mb-8">
            <TerminalBlock
              title="install"
              lines={[
                { text: '$ stow -t ~/.config/polybar polybar/hack', type: 'command' },
              ]}
            />
          </div>
        </section>

        {/* Filter */}
        <section className="container pb-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="font-mono text-sm text-[var(--text-muted)]">
              → Filter by Style
            </h2>
            <Filter options={filterOptions} value={filter} onChange={setFilter} />
          </div>
        </section>

        {/* Themes Grid */}
        <section className="container pb-16">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredThemes.map((theme) => (
              <GlassCard key={theme.name} hover={false}>
                {/* Preview Area */}
                <div className="h-24 bg-[var(--bg-primary)] rounded-md mb-4 flex items-center justify-center border border-[var(--border-muted)] overflow-hidden">
                  <div className="w-full h-6 bg-[var(--bg-secondary)] flex items-center px-2 gap-1">
                    {theme.colors.map((color, i) => (
                      <div
                        key={i}
                        className="w-3 h-3 rounded-sm"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                    <span className="ml-auto font-mono text-[10px] text-[var(--text-muted)]">
                      {theme.name}
                    </span>
                  </div>
                </div>

                {/* Theme Info */}
                <h3 className="font-mono text-base font-semibold text-[var(--text-secondary)] mb-1">
                  {theme.name}/
                </h3>
                <p className="font-mono text-xs text-[var(--text-muted)] mb-4">
                  {theme.description}
                </p>

                {/* Color Palette */}
                <div className="flex gap-1 mb-4">
                  {theme.colors.map((color, i) => (
                    <div
                      key={i}
                      className="flex-1 h-6 rounded-sm first:rounded-l-md last:rounded-r-md"
                      style={{ backgroundColor: color }}
                      title={color}
                    />
                  ))}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={() => copyCommand(theme.name)}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-[var(--bg-tertiary)] rounded-md font-mono text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors border border-[var(--border-default)]"
                  >
                    {copiedTheme === theme.name ? (
                      <>
                        <Check size={12} className="text-[var(--accent-green)]" />
                        <span className="text-[var(--accent-green)]">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={12} />
                        <span>Apply theme</span>
                      </>
                    )}
                  </button>
                </div>
              </GlassCard>
            ))}
          </div>
        </section>

        {/* Pywal Integration */}
        <section className="container pb-16">
          <GlassCard hover={false} className="max-w-3xl mx-auto">
            <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-4">
              Pywal Integration
            </h2>
            <p className="font-mono text-sm text-[var(--text-muted)] mb-6">
              All themes support automatic color generation from your wallpaper using Pywal.
              Just run the command below after changing your wallpaper:
            </p>
            <TerminalBlock
              title="pywal"
              lines={[
                { text: '# Set wallpaper and generate colors', type: 'output' },
                { text: '$ wal -i /path/to/wallpaper.png', type: 'command' },
                { text: '', type: 'output' },
                { text: '# Reload Polybar with new colors', type: 'output' },
                { text: '$ polybar-msg cmd restart', type: 'command' },
              ]}
            />
          </GlassCard>
        </section>
      </main>
      <Footer />
    </>
  )
}
