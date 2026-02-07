'use client'

import { useState } from 'react'
import { Header, Footer } from '@/components'
import { Image as ImageIcon } from 'lucide-react'
import Image from 'next/image'
import { assetPath } from '@/lib/utils'

const wallpapers = [
  // Space
  { name: 'galaxy-spiral-purple', file: 'galaxy-spiral-purple.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'space-nebula-stars', file: 'space-nebula-stars.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'space-planets-colorful', file: 'space-planets-colorful.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'space-galaxy-dark', file: 'space-galaxy-dark.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'northern-lights-aurora', file: 'northern-lights-aurora.jpg', category: 'space', resolution: '3440x1440' },
  // Nature
  { name: 'autumn-forest-lake', file: 'autumn-forest-lake.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'forest-path-fog', file: 'forest-path-fog.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'canyon-red-rocks', file: 'canyon-red-rocks.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'mountain-lake-reflection', file: 'mountain-lake-reflection.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'mountain-peak-clouds', file: 'mountain-peak-clouds.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'waterfall-jungle-green', file: 'waterfall-jungle-green.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'tropical-beach-palm', file: 'tropical-beach-palm.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'desert-dunes-golden', file: 'desert-dunes-golden.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'ocean-waves-sunset', file: 'ocean-waves-sunset.jpg', category: 'nature', resolution: '3440x1440' },
  // Abstract
  { name: 'abstract-colorful-shapes', file: 'abstract-colorful-shapes.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-geometric-blue', file: 'abstract-geometric-blue.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-purple-smoke', file: 'abstract-purple-smoke.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'geometric-purple-pattern', file: 'geometric-purple-pattern.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'minimalist-mountains-blue', file: 'minimalist-mountains-blue.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'low-poly-triangles', file: 'low-poly-triangles-colorful-abstract.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'gradient-blue-texture', file: 'gradient-blue-texture.png', category: 'abstract', resolution: '3440x1440' },
  // Urban
  { name: 'city-skyline-night', file: 'city-skyline-night.jpg', category: 'urban', resolution: '3440x1440' },
  { name: 'city-buildings-reflection', file: 'city-buildings-reflection.jpg', category: 'urban', resolution: '3440x1440' },
  { name: 'city-towers', file: 'city-towers.jpg', category: 'urban', resolution: '3440x1440' },
  // Gaming
  { name: 'star-wars-landscape', file: 'star-wars-landscape.jpg', category: 'gaming', resolution: '3440x1440' },
  { name: 'zelda-botw', file: 'the-legend-of-zelda-breath-of-the-wild-link-landscape-sky-scenic.jpg', category: 'gaming', resolution: '3440x1440' },
  { name: 'pc-gaming-neon', file: 'pc-gaming-neon-abstract.jpg', category: 'gaming', resolution: '3440x1440' },
]

const categories = ['all', 'space', 'nature', 'abstract', 'urban', 'gaming']
const resolutions = ['all', '3440x1440', '3840x2160', '2560x1440']

export default function WallpapersPage() {
  const [activeCategory, setActiveCategory] = useState('all')
  const [activeResolution, setActiveResolution] = useState('all')
  const [selectedWallpaper, setSelectedWallpaper] = useState<typeof wallpapers[0] | null>(null)

  const filtered = wallpapers.filter((w) => {
    const matchCat = activeCategory === 'all' || w.category === activeCategory
    const matchRes = activeResolution === 'all' || w.resolution === activeResolution
    return matchCat && matchRes
  })

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex items-start justify-between gap-16 py-16 px-[120px]">
          <div className="flex flex-col gap-6">
            <ImageIcon size={48} className="text-[#58A6FF]" />
            <h1 className="text-5xl font-bold font-mono text-[#E6EDF3]">wallpaper_gallery/</h1>
            <p className="text-lg text-[#8B949E] font-[Inter] leading-relaxed max-w-xl">
              160+ curated wallpapers across 5 resolutions. From 2K to 8K, space to urban, minimal to vibrant.
            </p>
          </div>

          {/* Count Badge */}
          <div className="flex flex-col items-center gap-2 p-6 bg-[#ffffff08] border border-[#58A6FF40] rounded-lg">
            <span className="text-4xl font-bold font-mono text-[#58A6FF]">160+</span>
            <span className="text-xs text-[#8B949E] font-mono">wallpapers</span>
          </div>
        </section>

        {/* Filters */}
        <section className="py-8 px-[120px]">
          <div className="flex flex-col gap-4">
            {/* Category Filter */}
            <div className="flex items-center gap-4">
              <span className="text-sm font-mono text-[#6E7681] w-20">category:</span>
              <div className="flex gap-2">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setActiveCategory(cat)}
                    className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                      activeCategory === cat
                        ? 'bg-[#58A6FF20] text-[#58A6FF] border border-[#58A6FF]'
                        : 'bg-transparent text-[#8B949E] border border-[#30363D] hover:text-[#E6EDF3]'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>
            {/* Resolution Filter */}
            <div className="flex items-center gap-4">
              <span className="text-sm font-mono text-[#6E7681] w-20">resolution:</span>
              <div className="flex gap-2">
                {resolutions.map((res) => (
                  <button
                    key={res}
                    onClick={() => setActiveResolution(res)}
                    className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                      activeResolution === res
                        ? 'bg-[#58A6FF20] text-[#58A6FF] border border-[#58A6FF]'
                        : 'bg-transparent text-[#8B949E] border border-[#30363D] hover:text-[#E6EDF3]'
                    }`}
                  >
                    {res}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Gallery Grid */}
        <section className="py-8 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// browse_gallery</p>
          <div className="grid grid-cols-3 gap-6">
            {filtered.map((wallpaper) => (
              <div
                key={wallpaper.name}
                className="group relative aspect-video bg-[#161B22] border border-[#30363D] rounded-lg overflow-hidden cursor-pointer hover:border-[#58A6FF50] transition-colors"
                onClick={() => setSelectedWallpaper(wallpaper)}
              >
                <Image
                  src={assetPath(`/wallpapers/3440x1440/${wallpaper.file}`)}
                  alt={wallpaper.name}
                  fill
                  className="object-cover"
                  sizes="(max-width: 768px) 100vw, 33vw"
                />
                {/* Overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="absolute bottom-0 left-0 right-0 p-4">
                    <p className="text-sm font-mono text-white truncate">{wallpaper.name}</p>
                    <p className="text-xs font-mono text-white/60">{wallpaper.resolution}</p>
                  </div>
                </div>
                {/* Resolution Badge */}
                <div className="absolute top-3 right-3 px-2 py-1 bg-[#0D1117CC] rounded text-[10px] font-mono text-[#8B949E]">
                  {wallpaper.resolution}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Lightbox */}
        {selectedWallpaper && (
          <div
            className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center p-8"
            onClick={() => setSelectedWallpaper(null)}
          >
            <div className="relative max-w-6xl w-full" onClick={(e) => e.stopPropagation()}>
              <div className="relative aspect-video">
                <Image
                  src={assetPath(`/wallpapers/3440x1440/${selectedWallpaper.file}`)}
                  alt={selectedWallpaper.name}
                  fill
                  className="object-contain"
                  sizes="100vw"
                />
              </div>
              <div className="mt-4 flex items-center justify-between">
                <div>
                  <p className="text-lg font-mono text-white">{selectedWallpaper.name}</p>
                  <p className="text-sm font-mono text-white/60">{selectedWallpaper.resolution} • {selectedWallpaper.category}</p>
                </div>
                <button
                  onClick={() => setSelectedWallpaper(null)}
                  className="px-4 py-2 bg-[#21262D] border border-[#30363D] rounded text-sm font-mono text-[#E6EDF3] hover:bg-[#30363D]"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
      <Footer />
    </>
  )
}
