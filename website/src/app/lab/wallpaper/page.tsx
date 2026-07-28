'use client'

import { useEffect } from 'react'
import { Header } from '@/components/Header'
import { Footer } from '@/components/Footer'
import { useWallpaperLab } from '@/components/wallpaper/WallpaperShell'
import type { WallpaperTier } from '@/lib/wallpaper/types'

const TIERS: Array<WallpaperTier | 'auto'> = ['auto', 'webgl', 'video', 'poster']

export default function WallpaperLabPage() {
  const {
    forceTier,
    allowVideoFallback,
    tier,
    fps,
    setForceTier,
    setAllowVideoFallback,
    setShowDebug,
  } = useWallpaperLab()

  useEffect(() => {
    setShowDebug(true)
    return () => setShowDebug(false)
  }, [setShowDebug])

  return (
    <div className="min-h-screen flex flex-col relative z-10">
      <Header />
      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-16">
        <p className="font-mono text-xs text-[var(--text-muted)] mb-2">/lab/wallpaper</p>
        <h1 className="font-mono text-3xl font-bold text-[var(--text-primary)] mb-3">
          Forgotten Ruins player
        </h1>
        <p className="text-[var(--text-secondary)] mb-8 max-w-prose">
          Thin WebGL1 spike: base plate + water distortion passes + light particles.
          Poster paints first; WebGL enhances when capable. Workshop textures stay
          gitignored — run the unpack script locally for full masks.
        </p>

        <div className="glass rounded-xl p-6 space-y-5">
          <div className="flex flex-wrap gap-2">
            {TIERS.map((t) => {
              const active = t === 'auto' ? forceTier === null : forceTier === t
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setForceTier(t === 'auto' ? null : t)}
                  className={`font-mono text-xs px-3 py-1.5 rounded-md border transition-colors ${
                    active
                      ? 'border-[var(--accent-blue)] text-[var(--accent-blue)] bg-white/5'
                      : 'border-white/10 text-[var(--text-muted)] hover:border-white/25'
                  }`}
                >
                  {t}
                </button>
              )
            })}
          </div>

          <label className="flex items-center gap-2 font-mono text-xs text-[var(--text-muted)]">
            <input
              type="checkbox"
              checked={allowVideoFallback}
              onChange={(e) => setAllowVideoFallback(e.target.checked)}
            />
            allow webm tier B when WebGL skipped
          </label>

          <dl className="grid grid-cols-2 gap-3 font-mono text-sm">
            <div>
              <dt className="text-[var(--text-muted)] text-xs">active tier</dt>
              <dd className="text-[var(--text-primary)]">{tier}</dd>
            </div>
            <div>
              <dt className="text-[var(--text-muted)] text-xs">fps</dt>
              <dd className="text-[var(--text-primary)]">
                {tier === 'webgl' ? fps.toFixed(1) : '—'}
              </dd>
            </div>
          </dl>

          <pre className="text-xs font-mono text-[var(--text-dim)] whitespace-pre-wrap leading-relaxed">
{`# local textures (gitignored)
python3 website/scripts/unpack-wallpaper.py \\
  --src /path/to/unpacked/forgotten-ruins \\
  --out website/public/media/ruins

# preview
cd website && npm run dev
# open /lab/wallpaper`}
          </pre>
        </div>
      </main>
      <Footer />
    </div>
  )
}
