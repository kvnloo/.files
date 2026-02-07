'use client'

import { useState } from 'react'
import { Header, Footer } from '@/components'
import { Image, Monitor } from 'lucide-react'

const wallpapers = [
  { name: 'galaxy-spiral-purple', category: 'space', resolution: '3440x1440' },
  { name: 'autumn-forest-lake', category: 'nature', resolution: '3440x1440' },
  { name: 'abstract-colorful-shapes', category: 'abstract', resolution: '3440x1440' },
  { name: 'city-skyline-night', category: 'urban', resolution: '3440x1440' },
  { name: 'forest-path-fog', category: 'nature', resolution: '3440x1440' },
  { name: 'geometric-purple-pattern', category: 'abstract', resolution: '3440x1440' },
  { name: 'canyon-red-rocks', category: 'nature', resolution: '3440x1440' },
  { name: 'minimalist-mountains-blue', category: 'abstract', resolution: '3440x1440' },
]

const categories = ['all', 'space', 'nature', 'abstract', 'urban', 'gaming']
const resolutions = ['all', '2K', '3440x1440', '4K', '8K']

export default function WallpapersPage() {
  const [activeCategory, setActiveCategory] = useState('all')
  const [activeResolution, setActiveResolution] = useState('all')

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
            <Image size={48} className="text-[#58A6FF]" />
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
              >
                {/* Placeholder */}
                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[#161B22] to-[#21262D]">
                  <Monitor size={32} className="text-[#30363D]" />
                </div>
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

        {/* Pagination */}
        <section className="py-8 px-[120px] flex justify-center">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[#58A6FF]" />
            <div className="w-2 h-2 rounded-full bg-[#30363D]" />
            <div className="w-2 h-2 rounded-full bg-[#30363D]" />
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
