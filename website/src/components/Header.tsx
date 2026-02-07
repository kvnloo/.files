'use client'

import Link from 'next/link'
import { Github, Menu, X } from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { label: 'Themes', href: '/themes' },
  { label: 'Wallpapers', href: '/wallpapers' },
  { label: 'Icons', href: '/icons' },
  { label: 'Audio', href: '/audio' },
  { label: 'Docs', href: 'https://github.com/kvn/.files#readme' },
]

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass border-b border-[var(--border-default)]">
      <div className="container flex items-center justify-between h-[72px]">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-1 group">
          <span className="text-[var(--accent-blue)] font-mono text-2xl font-bold group-hover:text-[var(--accent-purple)] transition-colors">
            &gt;
          </span>
          <span className="text-[var(--text-secondary)] font-mono text-xl font-medium">
            .files
          </span>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-8">
          {navItems.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className="text-[var(--text-muted)] font-mono text-sm hover:text-[var(--text-primary)] transition-colors"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* GitHub Button */}
        <div className="hidden md:flex items-center">
          <a
            href="https://github.com/kvn/.files"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-secondary)] font-mono text-sm hover:bg-[var(--border-default)] transition-colors"
          >
            <Github size={16} />
            <span>GitHub</span>
          </a>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2 text-[var(--text-muted)]"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden glass border-t border-[var(--border-default)]">
          <nav className="container py-4 flex flex-col gap-4">
            {navItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className="text-[var(--text-muted)] font-mono text-sm hover:text-[var(--text-primary)] transition-colors py-2"
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
            <a
              href="https://github.com/kvn/.files"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-secondary)] font-mono text-sm w-fit"
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
