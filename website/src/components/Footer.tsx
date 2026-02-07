import Link from 'next/link'
import { Github } from 'lucide-react'

export function Footer() {
  return (
    <footer className="bg-[#0D1117] border-t border-[#21262D]">
      <div className="flex flex-col gap-6 py-12 px-[120px]">
        {/* Top row */}
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <span className="text-lg font-bold font-mono text-[#58A6FF]">&gt;</span>
            <span className="text-base font-medium font-mono text-[#E6EDF3]">.files</span>
          </Link>

          {/* Navigation */}
          <nav className="flex items-center gap-8">
            <Link href="/" className="text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors">
              home
            </Link>
            <Link href="/themes" className="text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors">
              themes
            </Link>
            <Link href="/audio" className="text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors">
              audio
            </Link>
            <Link href="/wallpapers" className="text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors">
              wallpapers
            </Link>
            <Link href="/icons" className="text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors">
              icons
            </Link>
            <a
              href="https://github.com/kvnloo/.files"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm font-mono text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
            >
              <Github size={16} />
              <span>GitHub</span>
            </a>
          </nav>
        </div>

        {/* Divider */}
        <div className="h-px bg-[#21262D]" />

        {/* Bottom row */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-[#6E7681] font-[Inter]">
            Made with ♥ for the Linux community
          </span>
          <span className="text-xs text-[#6E7681] font-mono">
            MIT License
          </span>
        </div>
      </div>
    </footer>
  )
}
