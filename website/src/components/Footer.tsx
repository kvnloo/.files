import Link from 'next/link'

const navItems = [
  { label: 'Themes', href: '/themes' },
  { label: 'Wallpapers', href: '/wallpapers' },
  { label: 'Icons', href: '/icons' },
  { label: 'Audio', href: '/audio' },
  { label: 'Docs', href: 'https://github.com/kvn/.files#readme' },
]

export function Footer() {
  return (
    <footer className="border-t border-[var(--border-muted)] bg-[var(--bg-primary)]">
      <div className="container py-12 flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-1">
          <span className="text-[var(--accent-blue)] font-mono text-2xl font-bold">
            &gt;
          </span>
          <span className="text-[var(--text-secondary)] font-mono text-xl font-medium">
            .files
          </span>
        </Link>

        {/* Navigation */}
        <nav className="flex flex-wrap items-center justify-center gap-8">
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

        {/* Copyright */}
        <p className="text-[var(--text-dim)] font-mono text-xs">
          2024 .files - MIT License
        </p>
      </div>
    </footer>
  )
}
