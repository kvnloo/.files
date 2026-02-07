'use client'

import Link from 'next/link'
import { Github, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { usePathname } from 'next/navigation'

const navItems = [
  { label: 'home', href: '/' },
  { label: 'themes', href: '/themes' },
  { label: 'audio', href: '/audio' },
  { label: 'wallpapers', href: '/wallpapers' },
  { label: 'icons', href: '/icons' },
]

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname.startsWith(href)
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-[72px] bg-[#0D1117CC] backdrop-blur-xl border-b border-[#30363D]">
      <div className="flex items-center justify-between h-full px-12">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3">
          <span className="text-2xl font-bold font-mono text-[#58A6FF]">&gt;</span>
          <span className="text-xl font-medium font-mono text-[#E6EDF3]">.files</span>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-8">
          {navItems.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className={`text-sm font-mono transition-colors ${
                isActive(item.href)
                  ? 'text-[#E6EDF3] font-semibold'
                  : 'text-[#8B949E] hover:text-[#E6EDF3]'
              }`}
            >
              {item.label}
            </Link>
          ))}
          <a
            href="https://github.com/kvnloo/.files"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-5 py-3 bg-[#21262D] border border-[#30363D] rounded-md text-sm font-mono text-[#E6EDF3] hover:bg-[#30363D] transition-colors"
          >
            <Github size={18} />
            <span>GitHub</span>
          </a>
        </nav>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2 text-[#8B949E]"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#0D1117] border-t border-[#30363D]">
          <nav className="flex flex-col p-6 gap-4">
            {navItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className={`text-sm font-mono py-2 ${
                  isActive(item.href) ? 'text-[#E6EDF3]' : 'text-[#8B949E]'
                }`}
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
            <a
              href="https://github.com/kvnloo/.files"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-[#21262D] border border-[#30363D] rounded-md text-sm font-mono text-[#E6EDF3] w-fit"
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
