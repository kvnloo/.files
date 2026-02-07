'use client'

import { useState } from 'react'
import { Header, Footer, GlassCard, Filter, Button } from '@/components'
import { Image, Download, Monitor, Maximize2 } from 'lucide-react'
import Link from 'next/link'

// Sample wallpapers organized by category
const wallpapers = [
  // Space/Astronomy
  { name: 'galaxy-spiral-purple', category: 'space', resolution: '3440x1440', ext: 'jpg' },
  { name: 'ghosts', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  // Nature
  { name: 'autumn-forest-lake', category: 'nature', resolution: '3440x1440', ext: 'jpg' },
  { name: 'forest-path-fog', category: 'nature', resolution: '3440x1440', ext: 'jpg' },
  { name: 'canyon-red-rocks', category: 'nature', resolution: '3440x1440', ext: 'jpg' },
  { name: 'desert-dunes-golden', category: 'nature', resolution: '3440x1440', ext: 'jpg' },
  { name: 'landscape-mountain-vista', category: 'nature', resolution: '3440x1440', ext: 'png' },
  { name: 'lighthouse-coastal-sunset', category: 'nature', resolution: '3440x1440', ext: 'jpg' },
  // Abstract
  { name: 'abstract-colorful-shapes', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  { name: 'abstract-geometric-blue', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  { name: 'abstract-pattern-green', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  { name: 'abstract-pink-gradient', category: 'abstract', resolution: '3440x1440', ext: 'jpg' },
  { name: 'abstract-purple-smoke', category: 'abstract', resolution: '3440x1440', ext: 'jpg' },
  { name: 'geometric-purple-pattern', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  { name: 'gradient-blue-texture', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  { name: 'low-poly-triangles-colorful-abstract', category: 'abstract', resolution: '3440x1440', ext: 'png' },
  // Urban
  { name: 'city-skyline-night', category: 'urban', resolution: '3440x1440', ext: 'jpg' },
  { name: 'city-buildings-reflection', category: 'urban', resolution: '3440x1440', ext: 'jpg' },
  { name: 'city-towers', category: 'urban', resolution: '3440x1440', ext: 'jpg' },
]

const resolutions = [
  { label: 'All', value: 'all' },
  { label: '2K', value: '2560x1440' },
  { label: 'Ultrawide', value: '3440x1440' },
  { label: '4K', value: '3840x2160' },
  { label: '8K', value: '7680x4320' },
]

const categories = [
  { label: 'All', value: 'all' },
  { label: 'Space', value: 'space' },
  { label: 'Nature', value: 'nature' },
  { label: 'Abstract', value: 'abstract' },
  { label: 'Urban', value: 'urban' },
]

export default function WallpapersPage() {
  const [resolution, setResolution] = useState('all')
  const [category, setCategory] = useState('all')
  const [selectedWallpaper, setSelectedWallpaper] = useState<typeof wallpapers[0] | null>(null)

  const filteredWallpapers = wallpapers.filter((w) => {
    const matchesRes = resolution === 'all' || w.resolution === resolution
    const matchesCat = category === 'all' || w.category === category
    return matchesRes && matchesCat
  })

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="container py-16 text-center">
          <div className="inline-flex items-center gap-3 mb-6">
            <Image size={48} className="text-[var(--accent-blue)]" />
          </div>
          <h1 className="text-3xl md:text-5xl font-bold font-mono mb-4">
            wallpapers/
          </h1>
          <p className="text-[var(--text-muted)] max-w-2xl mx-auto mb-8">
            160+ curated wallpapers spanning 5 resolutions from 2K to 8K. Perfect for any display setup.
          </p>

          {/* Resolution Stats */}
          <div className="flex flex-wrap justify-center gap-4">
            {[
              { res: '2560×1440', label: '2K' },
              { res: '2800×1800', label: 'Retina' },
              { res: '3440×1440', label: 'Ultrawide' },
              { res: '3840×2160', label: '4K' },
              { res: '7680×4320', label: '8K' },
            ].map((item) => (
              <div
                key={item.res}
                className="px-4 py-2 bg-[var(--bg-tertiary)] rounded-md border border-[var(--border-default)]"
              >
                <span className="font-mono text-xs text-[var(--text-muted)]">
                  {item.res}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Filters */}
        <section className="container pb-8">
          <div className="flex flex-col md:flex-row md:items-center gap-4 md:gap-8">
            <div className="flex items-center gap-4">
              <span className="font-mono text-sm text-[var(--text-muted)]">Resolution:</span>
              <Filter options={resolutions} value={resolution} onChange={setResolution} />
            </div>
            <div className="flex items-center gap-4">
              <span className="font-mono text-sm text-[var(--text-muted)]">Category:</span>
              <Filter options={categories} value={category} onChange={setCategory} />
            </div>
          </div>
        </section>

        {/* Wallpapers Grid */}
        <section className="container pb-16">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {filteredWallpapers.map((wallpaper) => (
              <div
                key={wallpaper.name}
                className="group relative aspect-video rounded-lg overflow-hidden bg-[var(--bg-secondary)] border border-[var(--border-muted)] cursor-pointer card-hover"
                onClick={() => setSelectedWallpaper(wallpaper)}
              >
                {/* Placeholder - in production, use actual images */}
                <div className="w-full h-full bg-gradient-to-br from-[var(--bg-secondary)] to-[var(--bg-tertiary)] flex items-center justify-center">
                  <Monitor size={32} className="text-[var(--text-dim)]" />
                </div>

                {/* Overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="absolute bottom-0 left-0 right-0 p-3">
                    <p className="font-mono text-xs text-white truncate">
                      {wallpaper.name}
                    </p>
                    <p className="font-mono text-[10px] text-white/60">
                      {wallpaper.resolution}
                    </p>
                  </div>
                  <button className="absolute top-2 right-2 p-1.5 bg-white/20 rounded-md hover:bg-white/30 transition-colors">
                    <Maximize2 size={14} className="text-white" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {filteredWallpapers.length === 0 && (
            <div className="text-center py-16">
              <p className="font-mono text-[var(--text-muted)]">
                No wallpapers match your filters
              </p>
            </div>
          )}
        </section>

        {/* Download Info */}
        <section className="container pb-16">
          <GlassCard hover={false} className="max-w-3xl mx-auto text-center">
            <Download size={32} className="text-[var(--accent-blue)] mx-auto mb-4" />
            <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-4">
              Download All Wallpapers
            </h2>
            <p className="font-mono text-sm text-[var(--text-muted)] mb-6">
              Clone the repository to get all 160+ wallpapers organized by resolution
            </p>
            <code className="block px-4 py-3 bg-[var(--bg-primary)] rounded-md font-mono text-sm text-[var(--text-secondary)] mb-4">
              git clone https://github.com/kvn/.files.git
            </code>
            <p className="font-mono text-xs text-[var(--text-dim)]">
              Wallpapers are located in /background/{'{resolution}'}/ directory
            </p>
          </GlassCard>
        </section>

        {/* Lightbox Modal */}
        {selectedWallpaper && (
          <div
            className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
            onClick={() => setSelectedWallpaper(null)}
          >
            <div className="max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
              {/* Placeholder for actual image */}
              <div className="aspect-video bg-[var(--bg-secondary)] rounded-lg flex items-center justify-center mb-4">
                <Monitor size={64} className="text-[var(--text-dim)]" />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-mono text-lg text-white">
                    {selectedWallpaper.name}
                  </p>
                  <p className="font-mono text-sm text-white/60">
                    {selectedWallpaper.resolution} • {selectedWallpaper.category}
                  </p>
                </div>
                <Button variant="primary" onClick={() => setSelectedWallpaper(null)}>
                  Close
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
