'use client'

import { useState } from 'react'
import { Header, Footer, TerminalBlock } from '@/components'
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
  Github,
} from 'lucide-react'
import Link from 'next/link'

const showcaseItems = [
  { id: 1, title: 'Polybar Themes', colors: ['#ff6b6b', '#4ecdc4', '#ffe66d', '#a855f7', '#3b82f6'] },
  { id: 2, title: 'Wallpapers', colors: ['#0ea5e9', '#8b5cf6', '#ec4899', '#f97316', '#22c55e'] },
  { id: 3, title: 'Desktop', colors: ['#6366f1', '#14b8a6', '#f43f5e', '#eab308', '#06b6d4'] },
  { id: 4, title: 'Audio Stack', colors: ['#f59e0b', '#84cc16', '#ef4444', '#8b5cf6', '#06b6d4'] },
]

const features = [
  {
    icon: FolderTree,
    iconColor: '#58A6FF',
    title: 'modular_architecture/',
    description: 'Clean hierarchy with symlink management. Each config is self-contained and independently deployable.',
    link: '#',
    linkText: 'Learn more →',
  },
  {
    icon: Palette,
    iconColor: '#A371F7',
    title: '10_polybar_themes/',
    description: 'Handcrafted Polybar themes with Pywal integration. One command to transform your entire desktop aesthetic.',
    link: '/themes',
    linkText: 'Browse themes →',
  },
  {
    icon: Headphones,
    iconColor: '#F59E0B',
    title: 'audiophile_setup/',
    description: '98% optimized PipeWire 1.5.85 with bit-perfect playback, AutoEQ convolver, and crossfeed DSP.',
    link: '/audio',
    linkText: 'View setup →',
  },
]

const categories = [
  {
    icon: Monitor,
    iconColor: '#58A6FF',
    title: 'desktop/',
    description: 'i3, Polybar, Rofi, Picom, Dunst',
    files: 15,
    os: ['linux'],
  },
  {
    icon: Terminal,
    iconColor: '#3FB950',
    title: 'shell/',
    description: 'ZSH, Fish, Tmux',
    files: 8,
    os: ['linux', 'macos'],
  },
  {
    icon: Headphones,
    iconColor: '#F59E0B',
    title: 'audio/',
    description: 'PipeWire, WirePlumber, EasyEffects',
    files: 11,
    os: ['linux'],
  },
  {
    icon: Code,
    iconColor: '#A371F7',
    title: 'dev/',
    description: 'Vim, Git, Fonts',
    files: 12,
    os: ['linux', 'macos'],
  },
]

export default function HomePage() {
  const [copied, setCopied] = useState(false)
  const [activeShowcase, setActiveShowcase] = useState(0)
  const [activeFilter, setActiveFilter] = useState('all')

  const copyClone = () => {
    navigator.clipboard.writeText('git clone https://github.com/kvnloo/.files.git')
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
            <div className="flex items-center gap-4">
              <span className="text-[72px] font-bold font-mono text-[#58A6FF]">.</span>
              <span className="text-[72px] font-bold font-mono text-[#E6EDF3]">files</span>
              <span className="text-[72px] font-bold font-mono text-[#8B949E]">+</span>
              <span className="text-[72px] font-bold font-mono bg-gradient-to-b from-[#A371F7] to-[#58A6FF] bg-clip-text text-transparent">UX</span>
            </div>

            {/* Tagline */}
            <p className="text-xl text-[#8B949E] text-center font-[Inter]">
              Meticulously Organized Linux Dotfiles & Visual Assets
            </p>

            {/* Stats inline */}
            <p className="text-sm text-[#6E7681] font-mono text-center">
              72+ configs  •  160+ wallpapers  •  80+ icons  •  10 themes
            </p>

            {/* Clone Command */}
            <div className="flex items-center justify-between gap-4 px-6 py-4 bg-[#161B22] border border-[#30363D] rounded-none w-[600px]">
              <div className="flex items-center gap-3">
                <span className="text-[#58A6FF] font-mono text-sm">$</span>
                <span className="text-[#E6EDF3] font-mono text-sm">git clone https://github.com/kvnloo/.files.git</span>
              </div>
              <button
                onClick={copyClone}
                className="flex items-center gap-2 px-3 py-2 bg-[#21262D] border border-[#30363D] hover:bg-[#30363D] transition-colors"
              >
                {copied ? (
                  <Check size={16} className="text-[#3FB950]" />
                ) : (
                  <Copy size={16} className="text-[#8B949E]" />
                )}
              </button>
            </div>

            {/* Showcase Carousel */}
            <div className="w-[900px] p-6 bg-[#ffffff08] border border-[#30363D] rounded-lg backdrop-blur-xl">
              <div className="grid grid-cols-4 gap-4 h-[240px]">
                {showcaseItems.map((item, index) => (
                  <div
                    key={item.id}
                    className={`flex flex-col gap-3 p-4 bg-[#ffffff05] border border-[#30363D] rounded-lg backdrop-blur-sm cursor-pointer transition-all ${
                      activeShowcase === index ? 'border-[#58A6FF]' : ''
                    }`}
                    onClick={() => setActiveShowcase(index)}
                  >
                    <div className="flex-1 flex items-center justify-center">
                      <div className="flex gap-1">
                        {item.colors.map((color, i) => (
                          <div
                            key={i}
                            className="w-4 h-4 rounded-sm"
                            style={{ backgroundColor: color }}
                          />
                        ))}
                      </div>
                    </div>
                    <span className="text-xs font-mono text-[#8B949E] text-center">{item.title}</span>
                  </div>
                ))}
              </div>
              {/* Dot indicators */}
              <div className="flex justify-center gap-2 mt-4">
                {showcaseItems.map((_, index) => (
                  <div
                    key={index}
                    className={`w-2 h-2 rounded-full cursor-pointer ${
                      activeShowcase === index ? 'bg-[#58A6FF]' : 'bg-[#30363D]'
                    }`}
                    onClick={() => setActiveShowcase(index)}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Stats Bar */}
        <section className="flex items-center justify-center gap-12 py-6 px-[120px] bg-[#161B22] border-y border-[#21262D]">
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-bold font-mono text-[#E6EDF3]">72+</span>
            <span className="text-xs text-[#8B949E] font-[Inter]">configs</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-bold font-mono text-[#E6EDF3]">160+</span>
            <span className="text-xs text-[#8B949E] font-[Inter]">wallpapers</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-bold font-mono text-[#E6EDF3]">80+</span>
            <span className="text-xs text-[#8B949E] font-[Inter]">icons</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-bold font-mono text-[#58A6FF]">10</span>
            <span className="text-xs text-[#8B949E] font-[Inter]">themes</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-bold font-mono text-[#E6EDF3]">3</span>
            <span className="text-xs text-[#8B949E] font-[Inter]">platforms</span>
          </div>
        </section>

        {/* Feature Highlights */}
        <section className="py-16 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-10">// feature_highlights</p>
          <div className="grid grid-cols-3 gap-6">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="flex flex-col gap-5 p-8 bg-[#ffffff05] border border-[#30363D] rounded-lg backdrop-blur-sm"
              >
                <feature.icon size={40} style={{ color: feature.iconColor }} />
                <h3 className="text-lg font-semibold font-mono text-[#E6EDF3]">{feature.title}</h3>
                <p className="text-sm text-[#8B949E] font-[Inter] leading-relaxed">{feature.description}</p>
                <Link href={feature.link} className="flex items-center gap-2 text-sm text-[#58A6FF] font-mono hover:underline">
                  {feature.linkText}
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* Categories */}
        <section className="py-16 px-[120px]">
          <div className="flex items-center justify-between mb-8">
            <p className="text-sm font-mono text-[#6E7681]">// categories</p>
            <div className="flex items-center gap-4">
              {['all', 'linux', 'macos'].map((filter) => (
                <button
                  key={filter}
                  onClick={() => setActiveFilter(filter)}
                  className={`px-4 py-2 text-sm font-mono rounded-none transition-colors ${
                    activeFilter === filter
                      ? 'bg-[#58A6FF20] text-[#58A6FF] border border-[#58A6FF]'
                      : 'bg-transparent text-[#8B949E] border border-[#30363D] hover:text-[#E6EDF3]'
                  }`}
                >
                  {filter}
                </button>
              ))}
              <div className="flex items-center gap-2 px-3 py-2 bg-[#161B22] border border-[#30363D] w-[180px]">
                <Search size={14} className="text-[#6E7681]" />
                <input
                  type="text"
                  placeholder="search..."
                  className="bg-transparent text-sm font-mono text-[#E6EDF3] placeholder-[#6E7681] outline-none w-full"
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-5">
            {categories
              .filter((cat) => activeFilter === 'all' || cat.os.includes(activeFilter))
              .map((category) => (
                <div
                  key={category.title}
                  className="flex flex-col gap-4 p-6 bg-[#161B22] border border-[#30363D] rounded-lg backdrop-blur-sm hover:border-[#58A6FF50] transition-colors cursor-pointer"
                >
                  <category.icon size={28} style={{ color: category.iconColor }} />
                  <h3 className="text-base font-semibold font-mono text-[#E6EDF3]">{category.title}</h3>
                  <p className="text-xs text-[#8B949E] font-[Inter]">{category.description}</p>
                  <div className="flex items-center gap-2 mt-auto">
                    {category.os.map((os) => (
                      <span
                        key={os}
                        className={`px-2 py-0.5 text-[10px] font-mono rounded ${
                          os === 'linux'
                            ? 'bg-[#D29922]/20 text-[#D29922]'
                            : 'bg-[#8B949E]/20 text-[#8B949E]'
                        }`}
                      >
                        {os}
                      </span>
                    ))}
                    <span className="ml-auto text-xs font-mono text-[#6E7681]">{category.files} files</span>
                  </div>
                </div>
              ))}
          </div>
        </section>

        {/* Quick Start */}
        <section className="py-16 px-[120px] flex flex-col items-center">
          <p className="text-sm font-mono text-[#6E7681] mb-8 self-start">// quick_start</p>
          <div className="w-[700px] border border-[#30363D] overflow-hidden">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 px-4 py-3 bg-[#161B22]">
              <div className="w-3 h-3 rounded-full bg-[#F85149]" />
              <div className="w-3 h-3 rounded-full bg-[#F59E0B]" />
              <div className="w-3 h-3 rounded-full bg-[#3FB950]" />
              <span className="ml-2 text-xs font-mono text-[#8B949E]">terminal</span>
            </div>
            {/* Terminal Body */}
            <div className="flex flex-col gap-4 p-6 bg-[#0D1117]">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[#6E7681] font-mono text-sm">#</span>
                  <span className="text-[#8B949E] font-mono text-sm">Clone the repository</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[#58A6FF] font-mono text-sm">$</span>
                  <span className="text-[#E6EDF3] font-mono text-sm">git clone https://github.com/kvnloo/.files.git ~/.files</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[#6E7681] font-mono text-sm">#</span>
                  <span className="text-[#8B949E] font-mono text-sm">Run the installer</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[#58A6FF] font-mono text-sm">$</span>
                  <span className="text-[#E6EDF3] font-mono text-sm">cd ~/.files && ./install.sh</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
