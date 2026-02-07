'use client'

import { useState } from 'react'
import { Header, Footer, GlassCard, Filter, Button } from '@/components'
import { Sparkles, Download, Apple, Info } from 'lucide-react'

// Sample icons organized by category
const icons = [
  // System
  { name: 'finder', category: 'system' },
  { name: 'app-store', category: 'system' },
  { name: 'automator', category: 'system' },
  { name: 'calculator', category: 'system' },
  { name: 'calendar', category: 'productivity' },
  { name: 'contacts', category: 'productivity' },
  { name: 'dictionary', category: 'productivity' },
  { name: 'font-book', category: 'system' },
  // Media
  { name: 'camera', category: 'media' },
  { name: 'camera-app', category: 'media' },
  { name: 'dvd', category: 'media' },
  { name: 'imovie', category: 'media' },
  { name: 'ibooks', category: 'media' },
  // Communication
  { name: 'facetime', category: 'communication' },
  { name: 'mail', category: 'communication' },
  { name: 'facebook', category: 'communication' },
  // Productivity
  { name: 'google-drive', category: 'productivity' },
  { name: 'google-inbox', category: 'communication' },
  { name: 'google-keep', category: 'productivity' },
  { name: 'google-voice', category: 'communication' },
  { name: 'kindle', category: 'media' },
  // Tools
  { name: 'dolphin-emulator', category: 'tools' },
  { name: 'igetter', category: 'tools' },
]

const categories = [
  { label: 'All', value: 'all' },
  { label: 'System', value: 'system' },
  { label: 'Productivity', value: 'productivity' },
  { label: 'Media', value: 'media' },
  { label: 'Communication', value: 'communication' },
  { label: 'Tools', value: 'tools' },
]

export default function IconsPage() {
  const [category, setCategory] = useState('all')
  const [selectedIcon, setSelectedIcon] = useState<typeof icons[0] | null>(null)

  const filteredIcons = category === 'all'
    ? icons
    : icons.filter((i) => i.category === category)

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="container py-16 text-center">
          <div className="inline-flex items-center gap-3 mb-6">
            <Sparkles size={48} className="text-[var(--accent-purple)]" />
          </div>
          <h1 className="text-3xl md:text-5xl font-bold font-mono mb-4">
            icons/
          </h1>
          <p className="text-[var(--text-muted)] max-w-2xl mx-auto mb-8">
            80+ custom macOS application icons with consistent design language. Perfect replacement icons for your dock.
          </p>

          {/* macOS Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-[#8B949E]/20 rounded-full border border-[#8B949E]/30">
            <Apple size={16} className="text-[#8B949E]" />
            <span className="font-mono text-sm text-[#8B949E]">macOS Icons</span>
          </div>
        </section>

        {/* Filters */}
        <section className="container pb-8">
          <div className="flex flex-wrap items-center gap-4">
            <span className="font-mono text-sm text-[var(--text-muted)]">Category:</span>
            <Filter options={categories} value={category} onChange={setCategory} />
          </div>
        </section>

        {/* Icons Grid */}
        <section className="container pb-16">
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-4">
            {filteredIcons.map((icon) => (
              <div
                key={icon.name}
                className="group flex flex-col items-center gap-2 p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-muted)] cursor-pointer card-hover"
                onClick={() => setSelectedIcon(icon)}
              >
                {/* Icon Placeholder */}
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[var(--accent-blue)]/20 to-[var(--accent-purple)]/20 flex items-center justify-center">
                  <Sparkles size={24} className="text-[var(--accent-blue)]" />
                </div>
                <span className="font-mono text-[10px] text-[var(--text-muted)] truncate max-w-full">
                  {icon.name}
                </span>
              </div>
            ))}
          </div>

          {filteredIcons.length === 0 && (
            <div className="text-center py-16">
              <p className="font-mono text-[var(--text-muted)]">
                No icons match your filter
              </p>
            </div>
          )}
        </section>

        {/* Installation Instructions */}
        <section className="container pb-16">
          <GlassCard hover={false} className="max-w-3xl mx-auto">
            <div className="flex items-start gap-4 mb-6">
              <Info size={24} className="text-[var(--accent-blue)] flex-shrink-0 mt-1" />
              <div>
                <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-2">
                  How to Install Icons on macOS
                </h2>
                <p className="font-mono text-sm text-[var(--text-muted)]">
                  Replace application icons with these custom designs
                </p>
              </div>
            </div>

            <ol className="space-y-4 font-mono text-sm text-[var(--text-secondary)]">
              <li className="flex gap-3">
                <span className="text-[var(--accent-blue)]">1.</span>
                <span>Find the app in <code className="px-1 bg-[var(--bg-tertiary)] rounded">/Applications</code></span>
              </li>
              <li className="flex gap-3">
                <span className="text-[var(--accent-blue)]">2.</span>
                <span>Right-click → <code className="px-1 bg-[var(--bg-tertiary)] rounded">Get Info</code> (or ⌘+I)</span>
              </li>
              <li className="flex gap-3">
                <span className="text-[var(--accent-blue)]">3.</span>
                <span>Drag the .icns file onto the icon in the top-left corner</span>
              </li>
              <li className="flex gap-3">
                <span className="text-[var(--accent-blue)]">4.</span>
                <span>Restart the app or run <code className="px-1 bg-[var(--bg-tertiary)] rounded">killall Dock</code></span>
              </li>
            </ol>
          </GlassCard>
        </section>

        {/* Download Info */}
        <section className="container pb-16">
          <GlassCard hover={false} className="max-w-3xl mx-auto text-center">
            <Download size={32} className="text-[var(--accent-purple)] mx-auto mb-4" />
            <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-4">
              Download All Icons
            </h2>
            <p className="font-mono text-sm text-[var(--text-muted)] mb-6">
              Clone the repository to get all 80+ icons in .icns and .png formats
            </p>
            <code className="block px-4 py-3 bg-[var(--bg-primary)] rounded-md font-mono text-sm text-[var(--text-secondary)] mb-4">
              git clone https://github.com/kvn/.files.git
            </code>
            <p className="font-mono text-xs text-[var(--text-dim)]">
              Icons are located in /icons/ directory
            </p>
          </GlassCard>
        </section>

        {/* Icon Detail Modal */}
        {selectedIcon && (
          <div
            className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
            onClick={() => setSelectedIcon(null)}
          >
            <div
              className="bg-[var(--bg-secondary)] rounded-xl p-8 max-w-sm w-full"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Large Icon Preview */}
              <div className="w-32 h-32 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-[var(--accent-blue)]/20 to-[var(--accent-purple)]/20 flex items-center justify-center">
                <Sparkles size={64} className="text-[var(--accent-blue)]" />
              </div>

              <h3 className="font-mono text-xl font-semibold text-[var(--text-primary)] text-center mb-2">
                {selectedIcon.name}
              </h3>
              <p className="font-mono text-sm text-[var(--text-muted)] text-center mb-6 capitalize">
                {selectedIcon.category}
              </p>

              <div className="flex gap-3">
                <Button variant="secondary" className="flex-1" onClick={() => setSelectedIcon(null)}>
                  Close
                </Button>
                <Button variant="primary" className="flex-1" href={`https://github.com/kvn/.files/tree/main/icons`}>
                  View on GitHub
                </Button>
              </div>
            </div>
          </div>
        )}
      </main>
      <Footer />
    </>
  )
}
