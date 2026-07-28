'use client'

import { useState } from 'react'
import { Header, Footer, TerminalBlock, Filter } from '@/components'
import {
  FolderTree,
  Palette,
  Headphones,
  Monitor,
  Terminal,
  Code,
  Copy,
  Check,
  Search,
} from 'lucide-react'
import Link from 'next/link'

const showcaseItems = [
  { id: 1, title: 'Hyprland Desktop', colors: ['#ff6b6b', '#4ecdc4', '#ffe66d', '#a855f7', '#3b82f6'] },
  { id: 2, title: 'Wallpapers', colors: ['#0ea5e9', '#8b5cf6', '#ec4899', '#f97316', '#22c55e'] },
  { id: 3, title: 'Noctalia / Waybar', colors: ['#6366f1', '#14b8a6', '#f43f5e', '#eab308', '#06b6d4'] },
  { id: 4, title: 'Audio Stack', colors: ['#f59e0b', '#84cc16', '#ef4444', '#8b5cf6', '#06b6d4'] },
]

const features = [
  {
    icon: FolderTree,
    iconColor: '#6ec8c4',
    title: 'dual_onboarding/',
    description: 'Install via ./install or an LLM harness that runs ./scripts/onboard. Shared modules for links, skills, audio, and optional Tailscale/Nix.',
    link: 'https://github.com/kvnloo/.files/blob/dev/docs/SETUP.md',
    linkText: 'Setup guide →',
  },
  {
    icon: Palette,
    iconColor: '#7eb8c9',
    title: 'hyprland_desktop/',
    description: 'Hyprland + Noctalia (or Waybar), Rofi, Dunst, nvim, and Sunshine phone display. Legacy Polybar themes remain under /themes.',
    link: '/themes',
    linkText: 'Browse themes →',
  },
  {
    icon: Headphones,
    iconColor: '#d4b45a',
    title: 'audiophile_setup/',
    description: 'Native PipeWire filter-chain DSP (AutoEQ, crossfeed, BRIR, Movie sink) plus optional Aural Evolution listening chain.',
    link: '/audio',
    linkText: 'View setup →',
  },
]

const categories = [
  {
    icon: Monitor,
    iconColor: '#6ec8c4',
    title: 'desktop/',
    description: 'Hyprland, Noctalia, Waybar, Rofi, Dunst, Sunshine',
    files: 15,
    os: ['linux'],
  },
  {
    icon: Terminal,
    iconColor: '#6fbf7a',
    title: 'shell/',
    description: 'Zsh, Fish, Tmux widgets',
    files: 8,
    os: ['linux', 'macos'],
  },
  {
    icon: Headphones,
    iconColor: '#d4b45a',
    title: 'audio/',
    description: 'PipeWire, WirePlumber, Aural Evolution',
    files: 11,
    os: ['linux'],
  },
  {
    icon: Code,
    iconColor: '#7eb8c9',
    title: 'dev/',
    description: 'nvim, Git, Zed, agent skills',
    files: 12,
    os: ['linux', 'macos'],
  },
]

export default function HomePage() {
  const [copied, setCopied] = useState(false)
  const [activeShowcase, setActiveShowcase] = useState(0)
  const [activeFilter, setActiveFilter] = useState('all')

  const copyClone = () => {
    navigator.clipboard.writeText('git clone https://github.com/kvnloo/.files.git ~/workspace/.files')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero Section */}
        <section className="py-20 px-[120px]">
          <div className="flex flex-col items-center gap-8">
            {/* Title */}
            <div className="flex items-center gap-3 md:gap-4 flex-wrap justify-center">
              <span className="text-[56px] md:text-[72px] font-bold font-mono text-[var(--accent-blue)]">.</span>
              <span className="text-[56px] md:text-[72px] font-bold font-mono text-[var(--text-primary)]">files</span>
              <span className="text-[56px] md:text-[72px] font-bold font-mono text-[var(--text-muted)]">+</span>
              <span className="text-[56px] md:text-[72px] font-bold font-mono gradient-text">UX</span>
            </div>

            {/* Tagline */}
            <p className="text-xl text-[var(--text-muted)] text-center max-w-xl">
              Hyprland desktop, PipeWire DSP, agent tooling, and curated visual assets
            </p>

            {/* Stats inline */}
            <p className="text-sm text-[var(--text-dim)] font-mono text-center">
              Hyprland · Noctalia · PipeWire · nvim · Sunshine
            </p>

            {/* Clone Command */}
            <div className="flex items-center justify-between gap-3 px-4 sm:px-6 py-4 glass rounded-[var(--radius-lg)] w-full max-w-[600px]">
              <div className="flex min-w-0 items-start gap-3 relative z-10">
                <span className="shrink-0 text-[var(--accent-blue)] font-mono text-sm">$</span>
                <span className="min-w-0 break-all text-[var(--text-primary)] font-mono text-sm">git clone https://github.com/kvnloo/.files.git ~/workspace/.files</span>
              </div>
              <button
                onClick={copyClone}
                aria-label={copied ? 'Clone command copied' : 'Copy clone command'}
                className="relative z-10 shrink-0 flex items-center gap-2 px-3 py-2 glass-hairline rounded-[var(--radius-md)] hover:border-[var(--accent-blue)] transition-colors"
              >
                {copied ? (
                  <Check size={16} className="text-[var(--accent-green)]" />
                ) : (
                  <Copy size={16} className="text-[var(--text-muted)]" />
                )}
              </button>
            </div>

            {/* Showcase Carousel */}
            <div className="w-full max-w-[900px] p-6 glass rounded-[var(--radius-xl)]">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 min-h-[240px] relative z-10">
                {showcaseItems.map((item, index) => (
                  <div
                    key={item.id}
                    className={`flex flex-col gap-3 p-4 glass-hairline rounded-[var(--radius-md)] cursor-pointer transition-all ${
                      activeShowcase === index ? 'border-[var(--accent-blue)]' : ''
                    }`}
                    onClick={() => setActiveShowcase(index)}
                  >
                    <div className="flex-1 flex items-center justify-center">
                      <div className="flex gap-1">
                        {item.colors.map((color, i) => (
                          <div
                            key={i}
                            className="w-4 h-4 rounded-[var(--radius-sm)]"
                            style={{ backgroundColor: color }}
                          />
                        ))}
                      </div>
                    </div>
                    <span className="text-xs font-mono text-[var(--text-muted)] text-center">{item.title}</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-center gap-2 mt-4 relative z-10">
                {showcaseItems.map((_, index) => (
                  <div
                    key={index}
                    className={`w-2 h-2 rounded-full cursor-pointer ${
                      activeShowcase === index ? 'bg-[var(--accent-blue)]' : 'bg-[var(--border-default)]'
                    }`}
                    onClick={() => setActiveShowcase(index)}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Stats Bar */}
        <section className="flex flex-wrap items-center justify-center gap-8 md:gap-12 py-6 px-6 md:px-[120px] glass border-y border-[var(--border-muted)]">
          <div className="flex flex-col items-center gap-1 relative z-10">
            <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">Hyprland</span>
            <span className="text-xs text-[var(--text-muted)]">Wayland desktop</span>
          </div>
          <div className="flex flex-col items-center gap-1 relative z-10">
            <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">79+</span>
            <span className="text-xs text-[var(--text-muted)]">wallpapers</span>
          </div>
          <div className="flex flex-col items-center gap-1 relative z-10">
            <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">80+</span>
            <span className="text-xs text-[var(--text-muted)]">icons</span>
          </div>
          <div className="flex flex-col items-center gap-1 relative z-10">
            <span className="text-2xl font-bold font-mono text-[var(--accent-blue)]">PipeWire</span>
            <span className="text-xs text-[var(--text-muted)]">native DSP</span>
          </div>
          <div className="flex flex-col items-center gap-1 relative z-10">
            <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">./install</span>
            <span className="text-xs text-[var(--text-muted)]">or harness</span>
          </div>
        </section>

        {/* Feature Highlights */}
        <section className="py-16 px-6 md:px-[120px]">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-10">// feature_highlights</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="flex flex-col gap-5 p-8 glass rounded-[var(--radius-lg)] card-hover"
              >
                <feature.icon size={40} style={{ color: feature.iconColor }} className="relative z-10" />
                <h3 className="text-lg font-semibold font-mono text-[var(--text-primary)] relative z-10">{feature.title}</h3>
                <p className="text-sm text-[var(--text-muted)] leading-relaxed relative z-10">{feature.description}</p>
                <Link href={feature.link} className="flex items-center gap-2 text-sm text-[var(--accent-blue)] font-mono hover:underline relative z-10">
                  {feature.linkText}
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* Categories */}
        <section className="py-16 px-6 md:px-[120px]">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-8">
            <p className="text-sm font-mono text-[var(--text-dim)]">// categories</p>
            <div className="flex flex-wrap items-center gap-3">
              <Filter
                value={activeFilter}
                onChange={setActiveFilter}
                options={['all', 'linux', 'macos'].map((filter) => ({
                  label: filter,
                  value: filter,
                }))}
              />
              <div className="flex items-center gap-2 px-3 py-2 glass-hairline rounded-[var(--radius-md)] w-[180px]">
                <Search size={14} className="text-[var(--text-dim)]" />
                <input
                  type="text"
                  placeholder="search..."
                  className="bg-transparent text-sm font-mono text-[var(--text-primary)] placeholder-[var(--text-dim)] outline-none w-full"
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {categories
              .filter((cat) => activeFilter === 'all' || cat.os.includes(activeFilter))
              .map((category) => (
                <div
                  key={category.title}
                  className="flex flex-col gap-4 p-6 glass rounded-[var(--radius-lg)] card-hover cursor-pointer"
                >
                  <category.icon size={28} style={{ color: category.iconColor }} className="relative z-10" />
                  <h3 className="text-base font-semibold font-mono text-[var(--text-primary)] relative z-10">{category.title}</h3>
                  <p className="text-xs text-[var(--text-muted)] relative z-10">{category.description}</p>
                  <div className="flex items-center gap-2 mt-auto relative z-10">
                    {category.os.map((os) => (
                      <span
                        key={os}
                        className={`px-2 py-0.5 text-[10px] font-mono rounded-[var(--radius-sm)] ${
                          os === 'linux'
                            ? 'bg-[rgba(210,153,34,0.18)] text-[var(--accent-yellow)] border border-[rgba(210,153,34,0.28)]'
                            : 'bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)] border border-[var(--border-muted)]'
                        }`}
                      >
                        {os}
                      </span>
                    ))}
                    <span className="ml-auto text-xs font-mono text-[var(--text-dim)]">{category.files} files</span>
                  </div>
                </div>
              ))}
          </div>
        </section>

        {/* Quick Start */}
        <section className="py-16 px-6 md:px-[120px] flex flex-col items-center">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-8 self-start">// quick_start</p>
          <div className="w-full max-w-[700px] glass rounded-[var(--radius-lg)] overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border-muted)] relative z-10">
              <div className="w-3 h-3 rounded-full bg-[var(--accent-red)]" />
              <div className="w-3 h-3 rounded-full bg-[var(--accent-yellow)]" />
              <div className="w-3 h-3 rounded-full bg-[var(--accent-green)]" />
              <span className="ml-2 text-xs font-mono text-[var(--text-muted)]">terminal</span>
            </div>
            <div className="flex flex-col gap-4 p-6 relative z-10">
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)] font-mono text-sm">#</span>
                <span className="text-[var(--text-muted)] font-mono text-sm">Clone the repository</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-blue)] font-mono text-sm">$</span>
                <span className="text-[var(--text-primary)] font-mono text-sm break-all">git clone https://github.com/kvnloo/.files.git ~/workspace/.files</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)] font-mono text-sm">#</span>
                <span className="text-[var(--text-muted)] font-mono text-sm">Run the interactive installer (or open in Cursor/Claude)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-blue)] font-mono text-sm">$</span>
                <span className="text-[var(--text-primary)] font-mono text-sm">cd ~/workspace/.files && ./install</span>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
