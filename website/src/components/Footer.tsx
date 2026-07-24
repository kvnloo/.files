import Link from 'next/link'
import { Github } from 'lucide-react'

export function Footer() {
  return (
    <footer className="glass-footer mt-8">
      <div className="flex flex-col gap-6 py-12 px-6 md:px-[120px] relative z-10">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-lg font-bold font-mono text-[var(--accent-blue)]">&gt;</span>
            <span className="text-base font-medium font-mono text-[var(--text-primary)]">.files</span>
          </Link>

          <nav className="flex flex-wrap items-center gap-6 md:gap-8">
            <Link href="/" className="text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              home
            </Link>
            <Link href="/themes" className="text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              themes
            </Link>
            <Link href="/audio" className="text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              audio
            </Link>
            <Link href="/wallpapers" className="text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              wallpapers
            </Link>
            <Link href="/icons" className="text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              icons
            </Link>
            <a
              href="https://github.com/kvnloo/.files"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Github size={16} />
              <span>GitHub</span>
            </a>
          </nav>
        </div>

        <div className="h-px bg-[var(--border-muted)]" />

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <span className="text-xs text-[var(--text-dim)]">
            Made with care for the Linux community · backdrop: Forgotten Ruins
          </span>
          <span className="text-xs text-[var(--text-dim)] font-mono">
            MIT License
          </span>
        </div>
      </div>
    </footer>
  )
}
