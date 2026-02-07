'use client'

import { useState } from 'react'
import { Header, Footer } from '@/components'
import { Image as ImageIcon } from 'lucide-react'
import Image from 'next/image'
import { assetPath } from '@/lib/utils'

const wallpapers = [
  // 2560x1440
  { name: 'planet-ball', file: 'planet-ball.jpg', category: 'space', resolution: '2560x1440' },
  { name: 'valley-river-sunset', file: 'valley-river-sunset.png', category: 'nature', resolution: '2560x1440' },
  // 2800x1800
  { name: 'abstract', file: 'abstract.png', category: 'abstract', resolution: '2800x1800' },
  { name: 'cyan-city', file: 'cyan-city.jpg', category: 'urban', resolution: '2800x1800' },
  { name: 'dynasty-ep', file: 'dynasty-ep.jpg', category: 'abstract', resolution: '2800x1800' },
  { name: 'eclipse', file: 'eclipse.jpg', category: 'space', resolution: '2800x1800' },
  { name: 'elegance', file: 'elegance.png', category: 'abstract', resolution: '2800x1800' },
  { name: 'expand', file: 'expand.jpg', category: 'abstract', resolution: '2800x1800' },
  { name: 'firewatch', file: 'firewatch.jpg', category: 'gaming', resolution: '2800x1800' },
  { name: 'floating-islands', file: 'floating-islands.jpg', category: 'nature', resolution: '2800x1800' },
  { name: 'galaxies', file: 'galaxies.jpg', category: 'space', resolution: '2800x1800' },
  { name: 'ice-plane', file: 'ice-plane.png', category: 'nature', resolution: '2800x1800' },
  { name: 'i-like-architecture', file: 'i-like-architecture.jpg', category: 'urban', resolution: '2800x1800' },
  { name: 'lighthouse', file: 'lighthouse.jpg', category: 'nature', resolution: '2800x1800' },
  { name: 'night-reflection', file: 'night-reflection.jpg', category: 'nature', resolution: '2800x1800' },
  { name: 'oof', file: 'oof.jpg', category: 'abstract', resolution: '2800x1800' },
  { name: 'poly-planet', file: 'poly-planet.png', category: 'abstract', resolution: '2800x1800' },
  { name: 'tris', file: 'tris.png', category: 'abstract', resolution: '2800x1800' },
  { name: 'ubuntu', file: 'ubuntu.png', category: 'abstract', resolution: '2800x1800' },
  { name: 'wallhaven', file: 'wallhaven.jpg', category: 'nature', resolution: '2800x1800' },
  { name: 'wave', file: 'wave.jpg', category: 'nature', resolution: '2800x1800' },
  // 3440x1440
  { name: 'abstract-colorful-shapes', file: 'abstract-colorful-shapes.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-geometric-blue', file: 'abstract-geometric-blue.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-pattern-green', file: 'abstract-pattern-green.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-pink-gradient', file: 'abstract-pink-gradient.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'abstract-purple-smoke', file: 'abstract-purple-smoke.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'autumn-forest-lake', file: 'autumn-forest-lake.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'canyon-red-rocks', file: 'canyon-red-rocks.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'city-buildings-reflection', file: 'city-buildings-reflection.jpg', category: 'urban', resolution: '3440x1440' },
  { name: 'city-skyline-night', file: 'city-skyline-night.jpg', category: 'urban', resolution: '3440x1440' },
  { name: 'city-towers', file: 'city-towers.jpg', category: 'urban', resolution: '3440x1440' },
  { name: 'desert-dunes-golden', file: 'desert-dunes-golden.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'dual-screen-abstract', file: 'dual-screen-abstract.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'forest-path-fog', file: 'forest-path-fog.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'galaxy-spiral-purple', file: 'galaxy-spiral-purple.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'geometric-purple-pattern', file: 'geometric-purple-pattern.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'ghosts', file: 'ghosts.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'gradient-blue-texture', file: 'gradient-blue-texture.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'landscape-mountain-vista', file: 'landscape-mountain-vista.png', category: 'nature', resolution: '3440x1440' },
  { name: 'lighthouse-coastal-sunset', file: 'lighthouse-coastal-sunset.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'low-poly-triangles', file: 'low-poly-triangles-colorful-abstract.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'minimalist-mountains-blue', file: 'minimalist-mountains-blue.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'minimal-waves-gradient', file: 'minimal-waves-gradient.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'mountain-lake-reflection', file: 'mountain-lake-reflection.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'mountain-landscape-sunset', file: 'mountain-landscape-sunset.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'mountain-peak-clouds', file: 'mountain-peak-clouds.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'nature-valley-green', file: 'nature-valley-green.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'no-mans-sky-rick-morty', file: "no man's sky x rick and morty.jpg", category: 'gaming', resolution: '3440x1440' },
  { name: 'northern-lights-aurora', file: 'northern-lights-aurora.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'ocean-waves-sunset', file: 'ocean-waves-sunset.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'orange-abstract-blobs', file: 'orange-abstract-blobs-wallpaper.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'pc-gaming-neon', file: 'pc-gaming-neon-abstract.jpg', category: 'gaming', resolution: '3440x1440' },
  { name: 'snow-mountain-peak', file: 'snow-mountain-peak.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'space-galaxy-dark', file: 'space-galaxy-dark.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'space-nebula-stars', file: 'space-nebula-stars.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'space-planets-colorful', file: 'space-planets-colorful.jpg', category: 'space', resolution: '3440x1440' },
  { name: 'star-wars-landscape', file: 'star-wars-landscape.jpg', category: 'gaming', resolution: '3440x1440' },
  { name: 'zelda-botw', file: 'the-legend-of-zelda-breath-of-the-wild-link-landscape-sky-scenic.jpg', category: 'gaming', resolution: '3440x1440' },
  { name: 'triangles-colorful-low-poly', file: 'triangles-colorful-low-poly.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'triangles-geometric-colorful', file: 'triangles-geometric-colorful.jpg', category: 'abstract', resolution: '3440x1440' },
  { name: 'tropical-beach-palm', file: 'tropical-beach-palm.jpg', category: 'nature', resolution: '3440x1440' },
  { name: 'vector-geometric-minimal', file: 'vector-geometric-minimal.png', category: 'abstract', resolution: '3440x1440' },
  { name: 'waterfall-jungle-green', file: 'waterfall-jungle-green.jpg', category: 'nature', resolution: '3440x1440' },
  // 3840x2160 (4K)
  { name: 'abstract-geometric-colorful-4k', file: 'abstract-geometric-colorful.jpg', category: 'abstract', resolution: '3840x2160' },
  { name: 'big-stripe', file: 'big-stripe.jpg', category: 'abstract', resolution: '3840x2160' },
  { name: 'brooklyn-bridge', file: 'brooklyn-bridge.jpg', category: 'urban', resolution: '3840x2160' },
  { name: 'coexist', file: 'coexist.png', category: 'abstract', resolution: '3840x2160' },
  { name: 'ghosts-4k', file: 'ghosts.jpg', category: 'abstract', resolution: '3840x2160' },
  // 7680x4320 (8K)
  { name: 'ghosts-8k', file: 'ghosts.jpg', category: 'abstract', resolution: '7680x4320' },
  // other
  { name: 'abstract-colorful-11', file: 'abstract-colorful-11.png', category: 'abstract', resolution: 'other' },
  { name: 'cherry-blossom-fantasy', file: 'cherry-blossom-fantasy-landscape.jpg', category: 'nature', resolution: 'other' },
  { name: 'city-architecture', file: 'city-architecture-117.jpg', category: 'urban', resolution: 'other' },
  { name: 'mountain-sunset', file: 'mountain-sunset-118.jpg', category: 'nature', resolution: 'other' },
  { name: 'nature-landscape', file: 'nature-landscape-13.jpg', category: 'nature', resolution: 'other' },
  { name: 'ocean-coastal', file: 'ocean-coastal-119.jpg', category: 'nature', resolution: 'other' },
  { name: 'rick-and-morty', file: 'rick-and-morty.jpeg', category: 'gaming', resolution: 'other' },
  { name: 'rick-morty-portal', file: 'rick-morty-portal.png', category: 'gaming', resolution: 'other' },
  { name: 'space-nebula-40', file: 'space-nebula-40.png', category: 'space', resolution: 'other' },
  { name: 'xerus', file: 'xerus.png', category: 'abstract', resolution: 'other' },
]

// Get folder name for resolution (handles the 8K unicode issue)
function getResolutionFolder(resolution: string): string {
  if (resolution === '7680x4320') return '7680×4320'
  return resolution
}

const categories = ['all', 'space', 'nature', 'abstract', 'urban', 'gaming']
const resolutions = ['all', '3440x1440', '2800x1800', '3840x2160', '2560x1440', '7680x4320', 'other']

export default function WallpapersPage() {
  const [activeCategory, setActiveCategory] = useState('all')
  const [activeResolution, setActiveResolution] = useState('all')
  const [selectedWallpaper, setSelectedWallpaper] = useState<typeof wallpapers[0] | null>(null)

  const filtered = wallpapers.filter((w) => {
    const matchCat = activeCategory === 'all' || w.category === activeCategory
    const matchRes = activeResolution === 'all' || w.resolution === activeResolution
    return matchCat && matchRes
  })

  // Count by resolution for badges
  const resCounts: Record<string, number> = {}
  resolutions.forEach(r => {
    resCounts[r] = r === 'all' ? wallpapers.length : wallpapers.filter(w => w.resolution === r).length
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
              {wallpapers.length} curated wallpapers across 6 resolutions. From 2K to 8K, space to urban, minimal to vibrant.
            </p>
          </div>

          {/* Count Badge */}
          <div className="flex flex-col items-center gap-2 p-6 bg-[#ffffff08] border border-[#58A6FF40] rounded-lg">
            <span className="text-4xl font-bold font-mono text-[#58A6FF]">{wallpapers.length}</span>
            <span className="text-xs text-[#8B949E] font-mono">wallpapers</span>
          </div>
        </section>

        {/* Filters */}
        <section className="py-8 px-[120px]">
          <div className="flex flex-col gap-4">
            {/* Category Filter */}
            <div className="flex items-center gap-4">
              <span className="text-sm font-mono text-[#6E7681] w-20">category:</span>
              <div className="flex gap-2 flex-wrap">
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
              <div className="flex gap-2 flex-wrap">
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
                    {res === 'all' ? 'all' : res} ({resCounts[res]})
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Gallery Grid */}
        <section className="py-8 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// showing {filtered.length} wallpapers</p>
          <div className="grid grid-cols-3 gap-6">
            {filtered.map((wallpaper, index) => (
              <div
                key={`${wallpaper.name}-${index}`}
                className="group relative aspect-video bg-[#161B22] border border-[#30363D] rounded-lg overflow-hidden cursor-pointer hover:border-[#58A6FF50] transition-colors"
                onClick={() => setSelectedWallpaper(wallpaper)}
              >
                <Image
                  src={assetPath(`/wallpapers/${getResolutionFolder(wallpaper.resolution)}/${wallpaper.file}`)}
                  alt={wallpaper.name}
                  fill
                  className="object-cover"
                  sizes="(max-width: 768px) 100vw, 33vw"
                />
                {/* Overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="absolute bottom-0 left-0 right-0 p-4">
                    <p className="text-sm font-mono text-white truncate">{wallpaper.name}</p>
                    <p className="text-xs font-mono text-white/60">{wallpaper.resolution} • {wallpaper.category}</p>
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
                  src={assetPath(`/wallpapers/${getResolutionFolder(selectedWallpaper.resolution)}/${selectedWallpaper.file}`)}
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
