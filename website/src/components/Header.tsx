'use client'

import Link from 'next/link'
import { Crop, Github, Menu, PanelsTopLeft, X } from 'lucide-react'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { useWallpaperLab } from '@/components/wallpaper/WallpaperShell'
import type { WallpaperViewMode } from '@/lib/wallpaper/types'

const navItems = [
  { label: 'home', href: '/' },
  { label: 'themes', href: '/themes' },
  { label: 'audio', href: '/audio' },
  { label: 'wallpapers', href: '/wallpapers' },
  { label: 'icons', href: '/icons' },
]

function ViewModeControl({ compact = false }: { compact?: boolean }) {
  const { viewMode, setViewMode } = useWallpaperLab()
  const options: Array<{ mode: WallpaperViewMode; label: string; icon: typeof Crop }> = [
    { mode: 'crop', label: 'Crop', icon: Crop },
    { mode: 'cinema', label: 'Cinema', icon: PanelsTopLeft },
  ]

  return (
    <div className="flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-black/20 p-1" aria-label="Wallpaper viewing mode">
      {options.map(({ mode, label, icon: Icon }) => (
        <button
          key={mode}
          type="button"
          aria-pressed={viewMode === mode}
          title={`${label} wallpaper mode`}
          onClick={() => setViewMode(mode)}
          className={`flex min-h-9 items-center justify-center gap-1.5 rounded-[8px] px-2.5 font-mono text-xs transition-colors ${
            viewMode === mode
              ? 'bg-white/12 text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
          }`}
        >
          <Icon size={14} />
          {!compact && <span>{label}</span>}
        </button>
      ))}
    </div>
  )
}

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/' || pathname === ''
    return pathname.startsWith(href)
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-[72px] glass-strong border-b border-[var(--border-default)]">
      <div className="flex items-center justify-between h-full px-6 md:px-12">
        <Link href="/" className="flex items-center gap-3 relative z-10">
          <span className="text-2xl font-bold font-mono text-[var(--accent-blue)]">&gt;</span>
          <span className="text-xl font-medium font-mono text-[var(--text-primary)]">.files</span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 relative z-10">
          {navItems.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className={`text-sm font-mono transition-colors ${
                isActive(item.href)
                  ? 'text-[var(--text-primary)] font-semibold'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              {item.label}
            </Link>
          ))}
          <ViewModeControl compact />
          <a
            href="https://github.com/kvnloo/.files"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-5 py-3 glass-hairline rounded-[var(--radius-md)] text-sm font-mono text-[var(--text-primary)] hover:border-[var(--accent-blue)] transition-colors"
          >
            <Github size={18} />
            <span>GitHub</span>
          </a>
        </nav>

        <button
          className="md:hidden p-2 text-[var(--text-muted)] relative z-10"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="md:hidden glass-strong border-t border-[var(--border-default)]">
          <nav className="flex flex-col p-6 gap-4 relative z-10">
            {navItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className={`text-sm font-mono py-2 ${
                  isActive(item.href) ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'
                }`}
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
            <ViewModeControl />
            <a
              href="https://github.com/kvnloo/.files"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 glass-hairline rounded-[var(--radius-md)] text-sm font-mono text-[var(--text-primary)] w-fit"
            >
              <Github size={16} />
              <span>GitHub</span>
            </a>
          </nav>
        </div>
      )}
    </header>
  )
}
