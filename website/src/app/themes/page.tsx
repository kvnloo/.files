'use client'

import { useState } from 'react'
import { Header, Footer } from '@/components'
import { Palette, Copy, Check } from 'lucide-react'

const themes = [
  { name: 'shades', description: 'Minimal grayscale', colors: ['#1a1a1a', '#333333', '#666666', '#999999', '#cccccc'], style: 'minimal' },
  { name: 'cyberpunk', description: 'Neon aesthetic', colors: ['#ff00ff', '#00ffff', '#ff0080', '#80ff00', '#0080ff'], style: 'colorful' },
  { name: 'hack', description: 'Classic green', colors: ['#0d1117', '#238636', '#3fb950', '#56d364', '#7ee787'], style: 'minimal' },
  { name: 'cuts', description: 'Geometric cuts', colors: ['#161b22', '#21262d', '#30363d', '#58a6ff', '#a371f7'], style: 'modern' },
  { name: 'docks', description: 'Dock-inspired', colors: ['#1c1c1e', '#2c2c2e', '#3a3a3c', '#636366', '#ebebf5'], style: 'modern' },
  { name: 'forest', description: 'Nature greens', colors: ['#1a2f1a', '#2d4a2d', '#3d6b3d', '#4d8c4d', '#5dad5d'], style: 'colorful' },
  { name: 'grayblocks', description: 'Blocky segments', colors: ['#1a1a1a', '#2a2a2a', '#3a3a3a', '#4a4a4a', '#5a5a5a'], style: 'minimal' },
  { name: 'material', description: 'Material palette', colors: ['#121212', '#1e1e1e', '#bb86fc', '#03dac6', '#cf6679'], style: 'modern' },
  { name: 'shapes', description: 'Shape accents', colors: ['#0d1117', '#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3'], style: 'colorful' },
  { name: 'waves', description: 'Wave curves', colors: ['#0f0f23', '#1a1a3e', '#2d2d5a', '#4040ff', '#6060ff'], style: 'modern' },
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
    navigator.clipboard.writeText(`stow -t ~/.config/polybar polybar/${themeName}`)
    setCopiedTheme(themeName)
    setTimeout(() => setCopiedTheme(null), 2000)
  }

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex flex-col items-center gap-6 py-16 px-[120px]">
          <Palette size={48} className="text-[#A371F7]" />
          <h1 className="text-5xl font-bold font-mono text-[#E6EDF3]">polybar_themes/</h1>
          <p className="text-lg text-[#8B949E] font-[Inter] text-center">
            10 handcrafted themes with Pywal integration
          </p>

          {/* Filter Row */}
          <div className="flex items-center gap-3">
            {filters.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setActiveFilter(filter.value)}
                className={`px-4 py-2 text-sm font-mono transition-colors ${
                  activeFilter === filter.value
                    ? 'bg-[#A371F720] text-[#A371F7] border border-[#A371F7]'
                    : 'bg-transparent text-[#8B949E] border border-[#30363D] hover:text-[#E6EDF3]'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </section>

        {/* Theme Grid */}
        <section className="py-16 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// available_themes</p>
          <div className="grid grid-cols-3 gap-6">
            {filteredThemes.map((theme) => (
              <div
                key={theme.name}
                className="flex flex-col gap-4 p-6 bg-[#161B22] border border-[#30363D] rounded-lg"
              >
                {/* Preview Area */}
                <div className="h-20 bg-[#0D1117] rounded flex items-center justify-center border border-[#21262D]">
                  <div className="flex items-center gap-1">
                    {theme.colors.map((color, i) => (
                      <div
                        key={i}
                        className="w-5 h-5 rounded-sm"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                </div>

                {/* Theme Name */}
                <h3 className="text-base font-semibold font-mono text-[#E6EDF3]">{theme.name}/</h3>
                <p className="text-xs text-[#8B949E] font-[Inter]">{theme.description}</p>

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
                  className="flex items-center justify-center gap-2 px-4 py-2 bg-[#21262D] border border-[#30363D] text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                >
                  {copiedTheme === theme.name ? (
                    <>
                      <Check size={14} className="text-[#3FB950]" />
                      <span className="text-[#3FB950]">Copied!</span>
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
          <p className="text-sm font-mono text-[#6E7681] mb-6 self-start">// pywal_integration</p>
          <div className="w-[600px] border border-[#30363D] overflow-hidden">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 px-4 py-3 bg-[#161B22]">
              <div className="w-3 h-3 rounded-full bg-[#F85149]" />
              <div className="w-3 h-3 rounded-full bg-[#F59E0B]" />
              <div className="w-3 h-3 rounded-full bg-[#3FB950]" />
              <span className="ml-2 text-xs font-mono text-[#8B949E]">pywal</span>
            </div>
            {/* Terminal Body */}
            <div className="flex flex-col gap-2 p-5 bg-[#0D1117]">
              <div className="flex items-center gap-2">
                <span className="text-[#6E7681] font-mono text-sm">#</span>
                <span className="text-[#8B949E] font-mono text-sm">Generate colors from wallpaper</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#58A6FF] font-mono text-sm">$</span>
                <span className="text-[#E6EDF3] font-mono text-sm">wal -i ~/wallpaper.png</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#6E7681] font-mono text-sm">#</span>
                <span className="text-[#8B949E] font-mono text-sm">Reload Polybar</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#58A6FF] font-mono text-sm">$</span>
                <span className="text-[#E6EDF3] font-mono text-sm">polybar-msg cmd restart</span>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
