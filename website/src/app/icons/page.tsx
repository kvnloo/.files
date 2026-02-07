'use client'

import { useState } from 'react'
import { Header, Footer } from '@/components'
import { Box, Download } from 'lucide-react'
import Image from 'next/image'

const icons = [
  // System
  { name: 'finder', file: 'finder.icns.png', category: 'system' },
  { name: 'system-preferences', file: 'system-preferences.png', category: 'system' },
  { name: 'terminal', file: 'terminal.icns.png', category: 'system' },
  { name: 'automator', file: 'automator.png', category: 'system' },
  { name: 'calculator', file: 'calculator.png', category: 'system' },
  { name: 'dictionary', file: 'dictionary.png', category: 'system' },
  { name: 'font-book', file: 'font-book.png', category: 'system' },
  // Productivity
  { name: 'safari', file: 'safari.icns.png', category: 'productivity' },
  { name: 'safari-alt', file: 'safari-alt.png', category: 'productivity' },
  { name: 'calendar', file: 'calendar.png', category: 'productivity' },
  { name: 'contacts', file: 'contacts.icns.png', category: 'productivity' },
  { name: 'notes', file: 'notes.png', category: 'productivity' },
  { name: 'maps', file: 'maps.png', category: 'productivity' },
  { name: 'ibooks', file: 'ibooks.png', category: 'productivity' },
  { name: 'kindle', file: 'kindle.png', category: 'productivity' },
  { name: 'google-drive', file: 'google-drive.png', category: 'productivity' },
  { name: 'google-inbox', file: 'google-inbox.png', category: 'productivity' },
  { name: 'google-keep', file: 'google_keep.png', category: 'productivity' },
  // Communication
  { name: 'mail', file: 'mail.png', category: 'communication' },
  { name: 'messages', file: 'messages.icns.png', category: 'communication' },
  { name: 'facetime', file: 'facetime.png', category: 'communication' },
  { name: 'slack', file: 'slack.icns.png', category: 'communication' },
  { name: 'skype', file: 'skype.png', category: 'communication' },
  { name: 'facebook', file: 'facebook.icns.png', category: 'communication' },
  { name: 'twitter', file: 'twitter.icns.png', category: 'communication' },
  { name: 'nylas', file: 'nylas.icns.png', category: 'communication' },
  { name: 'google-voice', file: 'google-voice.png', category: 'communication' },
  // Media
  { name: 'photos', file: 'photos.icns.png', category: 'media' },
  { name: 'camera', file: 'camera.png', category: 'media' },
  { name: 'camera-app', file: 'camera-app.png', category: 'media' },
  { name: 'imovie', file: 'imovie.png', category: 'media' },
  { name: 'spotify', file: 'spotify.icns.png', category: 'media' },
  { name: 'vlc', file: 'vlc.icns.png', category: 'media' },
  { name: 'plex', file: 'plex.png', category: 'media' },
  { name: 'youtube', file: 'youtube.icns.png', category: 'media' },
  { name: 'dvd', file: 'dvd.png', category: 'media' },
  // Tools
  { name: 'app-store', file: 'app-store.png', category: 'tools' },
  { name: 'xcode', file: 'xcode.icns.png', category: 'tools' },
  { name: 'sublime-text', file: 'sublime-text.png', category: 'tools' },
  { name: 'sketch', file: 'sketch.icns.png', category: 'tools' },
  { name: 'photoshop', file: 'photoshop.icns.png', category: 'tools' },
  { name: 'photoshop-file', file: 'photoshop-file.png', category: 'tools' },
  { name: 'steam', file: 'steam.icns.png', category: 'tools' },
  { name: 'dolphin-emulator', file: 'dolphin-emulator.png', category: 'tools' },
  { name: 'pokemon-reborn', file: 'pokemon-reborn.png', category: 'tools' },
  { name: 'opera', file: 'opera.png', category: 'tools' },
  { name: 'utorrent', file: 'utorrent.png', category: 'tools' },
  { name: 'purevpn', file: 'purevpn.png', category: 'tools' },
  { name: 'vnc-viewer', file: 'vnc-viewer.png', category: 'tools' },
  { name: 'igetter', file: 'igetter.png', category: 'tools' },
  { name: 'superbeam', file: 'superbeam.png', category: 'tools' },
  // Microsoft Office
  { name: 'microsoft-word', file: 'microsoft-word.png', category: 'productivity' },
  { name: 'microsoft-excel', file: 'microsoft-excel.png', category: 'productivity' },
  { name: 'microsoft-powerpoint', file: 'microsoft-powerpoint.png', category: 'productivity' },
  { name: 'microsoft-onenote', file: 'microsoft-onenote.png', category: 'productivity' },
]

const categories = ['all', 'system', 'productivity', 'media', 'communication', 'tools']

export default function IconsPage() {
  const [activeCategory, setActiveCategory] = useState('all')

  const filtered = activeCategory === 'all' ? icons : icons.filter((i) => i.category === activeCategory)

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex items-start justify-between gap-16 py-16 px-[120px]">
          <div className="flex flex-col gap-6">
            <Box size={48} className="text-[#3FB950]" />
            <h1 className="text-5xl font-bold font-mono text-[#E6EDF3]">icon_collection/</h1>
            <p className="text-lg text-[#8B949E] font-[Inter] leading-relaxed max-w-xl">
              {icons.length}+ custom macOS application icons with consistent design language. Categories: system, productivity, media, and communication.
            </p>
          </div>

          {/* Count Badge */}
          <div className="flex flex-col items-center gap-2 p-6 bg-[#ffffff08] border border-[#3FB95040] rounded-lg">
            <span className="text-4xl font-bold font-mono text-[#3FB950]">{icons.length}+</span>
            <span className="text-xs text-[#8B949E] font-mono">icons</span>
          </div>
        </section>

        {/* Filters */}
        <section className="py-8 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-4">// filter_by_category</p>
          <div className="flex gap-2">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                  activeCategory === cat
                    ? 'bg-[#3FB95020] text-[#3FB950] border border-[#3FB950]'
                    : 'bg-transparent text-[#8B949E] border border-[#30363D] hover:text-[#E6EDF3]'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </section>

        {/* Icons Grid */}
        <section className="py-8 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// all_icons</p>
          <div className="grid grid-cols-6 gap-4">
            {filtered.map((icon) => (
              <div
                key={icon.name}
                className="group flex flex-col items-center gap-3 p-4 bg-[#161B22] border border-[#30363D] rounded-lg hover:border-[#3FB95050] transition-colors cursor-pointer"
              >
                {/* Icon Image */}
                <div className="relative w-12 h-12">
                  <Image
                    src={`/icons/${icon.file}`}
                    alt={icon.name}
                    fill
                    className="object-contain"
                    sizes="48px"
                  />
                </div>
                <span className="text-[10px] font-mono text-[#8B949E] truncate max-w-full">{icon.name}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Quick Install */}
        <section className="py-12 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// quick_install</p>
          <div className="flex items-center justify-between p-6 bg-[#161B22] border border-[#30363D] rounded-lg">
            <div>
              <h3 className="text-lg font-semibold font-mono text-[#E6EDF3] mb-2">Download all icons</h3>
              <p className="text-sm text-[#8B949E] font-mono">git clone to get all {icons.length}+ icons</p>
            </div>
            <a
              href="https://github.com/kvnloo/.files/tree/master/icons"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-6 py-3 bg-[#3FB950] text-[#0D1117] text-sm font-semibold font-mono rounded hover:bg-[#2ea043] transition-colors"
            >
              <Download size={16} />
              <span>Download All</span>
            </a>
          </div>
        </section>

        {/* Installation */}
        <section className="py-12 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// how_to_use</p>
          <div className="w-[600px] border border-[#30363D] overflow-hidden rounded-lg">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 px-4 py-3 bg-[#161B22]">
              <div className="w-3 h-3 rounded-full bg-[#F85149]" />
              <div className="w-3 h-3 rounded-full bg-[#F59E0B]" />
              <div className="w-3 h-3 rounded-full bg-[#3FB950]" />
              <span className="ml-2 text-xs font-mono text-[#8B949E]">terminal</span>
            </div>
            {/* Terminal Body */}
            <div className="flex flex-col gap-2 p-5 bg-[#0D1117]">
              <div className="flex items-center gap-2">
                <span className="text-[#6E7681] font-mono text-sm">#</span>
                <span className="text-[#8B949E] font-mono text-sm">Right-click app → Get Info</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#6E7681] font-mono text-sm">#</span>
                <span className="text-[#8B949E] font-mono text-sm">Drag .icns onto icon in top-left</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#58A6FF] font-mono text-sm">$</span>
                <span className="text-[#E6EDF3] font-mono text-sm">killall Dock</span>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
