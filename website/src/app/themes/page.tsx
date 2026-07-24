'use client'

import { useState } from 'react'
import { Header, Footer, Filter } from '@/components'
import { Palette, Copy, Check } from 'lucide-react'

const themes = [
  { name: 'shades', description: 'Minimal grayscale', colors: ['#1a1a1a', '#333333', '#666666', '#999999', '#cccccc'], style: 'minimal' },
  { name: 'blocks', description: 'Segmented blocks', colors: ['#0d1117', '#58a6ff', '#3fb950', '#d29922', '#f85149'], style: 'modern' },
  { name: 'hack', description: 'Classic green', colors: ['#0d1117', '#238636', '#3fb950', '#56d364', '#7ee787'], style: 'minimal' },
  { name: 'cuts', description: 'Geometric cuts', colors: ['#161b22', '#21262d', '#30363d', '#58a6ff', '#a371f7'], style: 'modern' },
  { name: 'docky', description: 'Dock-inspired', colors: ['#1c1c1e', '#2c2c2e', '#3a3a3c', '#636366', '#ebebf5'], style: 'modern' },
  { name: 'forest', description: 'Nature greens', colors: ['#1a2f1a', '#2d4a2d', '#3d6b3d', '#4d8c4d', '#5dad5d'], style: 'colorful' },
  { name: 'grayblocks', description: 'Blocky segments', colors: ['#1a1a1a', '#2a2a2a', '#3a3a3a', '#4a4a4a', '#5a5a5a'], style: 'minimal' },
  { name: 'material', description: 'Material palette', colors: ['#121212', '#1e1e1e', '#bb86fc', '#03dac6', '#cf6679'], style: 'modern' },
  { name: 'shapes', description: 'Shape accents', colors: ['#0d1117', '#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3'], style: 'colorful' },
  { name: 'colorblocks', description: 'Colorful blocks', colors: ['#0f0f23', '#ff6b6b', '#4ecdc4', '#ffe66d', '#a855f7'], style: 'colorful' },
]

const filters = [
  { label: 'all', value: 'all' },
  { label: 'minimal', value: 'minimal' },
  { label: 'colorful', value: 'colorful' },
  { label: 'modern', value: 'modern' },
]

export default function ThemesPage() {
  const [activeFilter, setActiveFilter] = useState('all')
  const [copiedTheme, setCopiedTheme] = useState<string | null>(null)

  const filteredThemes = activeFilter === 'all'
    ? themes
    : themes.filter((t) => t.style === activeFilter)

  const copyCommand = (themeName: string) => {
    navigator.clipboard.writeText(
      `~/.config/polybar/launch.sh --${themeName}   # legacy; current desktop uses bar-mode noctalia|waybar`,
    )
    setCopiedTheme(themeName)
    setTimeout(() => setCopiedTheme(null), 2000)
  }

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex flex-col items-center gap-6 py-16 px-[120px]">
          <Palette size={48} className="text-[var(--accent-purple)]" />
          <h1 className="text-5xl font-bold font-mono text-[var(--text-primary)]">polybar_themes/</h1>
          <p className="text-lg text-[var(--text-muted)]  text-center max-w-2xl">
            Legacy Polybar themes (still in-repo). Current desktop shell is Noctalia or Waybar via{' '}
            <span className="font-mono text-[var(--text-primary)]">bar-mode</span>.
          </p>

          {/* Filter Row */}
          <Filter
            accent="purple"
            value={activeFilter}
            onChange={setActiveFilter}
            options={filters}
          />
        </section>

        {/* Theme Grid */}
        <section className="py-16 px-[120px]">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-6">// available_themes</p>
          <div className="grid grid-cols-3 gap-6">
            {filteredThemes.map((theme) => (
              <div
                key={theme.name}
                className="flex flex-col gap-4 p-6 glass rounded-[var(--radius-lg)]"
              >
                {/* Preview Area */}
                <div className="h-20 bg-[rgba(5,10,14,0.35)] rounded-[var(--radius-md)] flex items-center justify-center border border-[#21262D]">
                  <div className="flex items-center gap-1">
                    {theme.colors.map((color, i) => (
                      <div
                        key={i}
                        className="w-5 h-5 rounded-[var(--radius-sm)]"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                </div>

                {/* Theme Name */}
                <h3 className="text-base font-semibold font-mono text-[var(--text-primary)]">{theme.name}/</h3>
                <p className="text-xs text-[var(--text-muted)] ">{theme.description}</p>

                {/* Color Palette */}
                <div className="flex gap-1">
                  {theme.colors.map((color, i) => (
                    <div
                      key={i}
                      className="flex-1 h-4 first:rounded-l last:rounded-r"
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>

                {/* Apply Button */}
                <button
                  onClick={() => copyCommand(theme.name)}
                  className="flex items-center justify-center gap-2 px-4 py-2 bg-[rgba(18,28,38,0.45)] border border-[var(--border-default)] text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                  {copiedTheme === theme.name ? (
                    <>
                      <Check size={14} className="text-[var(--accent-green)]" />
                      <span className="text-[var(--accent-green)]">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy size={14} />
                      <span>Apply theme</span>
                    </>
                  )}
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Pywal Integration */}
        <section className="py-12 px-[120px] flex flex-col items-center">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-6 self-start">// pywal_integration</p>
          <div className="w-[600px] glass overflow-hidden rounded-[var(--radius-lg)]">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 px-4 py-3 bg-[rgba(10,18,26,0.35)]">
              <div className="w-3 h-3 rounded-full bg-[#F85149]" />
              <div className="w-3 h-3 rounded-full bg-[#F59E0B]" />
              <div className="w-3 h-3 rounded-full bg-[var(--accent-green)]" />
              <span className="ml-2 text-xs font-mono text-[var(--text-muted)]">pywal</span>
            </div>
            {/* Terminal Body */}
            <div className="flex flex-col gap-2 p-5 bg-[rgba(5,10,14,0.35)]">
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)] font-mono text-sm">#</span>
                <span className="text-[var(--text-muted)] font-mono text-sm">Generate colors from wallpaper</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-blue)] font-mono text-sm">$</span>
                <span className="text-[var(--text-primary)] font-mono text-sm">wal -i ~/wallpaper.png</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)] font-mono text-sm">#</span>
                <span className="text-[var(--text-muted)] font-mono text-sm">Current desktop: switch bar mode</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-blue)] font-mono text-sm">$</span>
                <span className="text-[var(--text-primary)] font-mono text-sm">bar-mode noctalia   # or: bar-mode waybar</span>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
