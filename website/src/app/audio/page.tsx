'use client'

import { Header, Footer } from '@/components'
import { Headphones, Check, X } from 'lucide-react'

const setupRows = [
  { component: 'DAC', value: 'Topping DX5 USB DAC', status: 'excellent' },
  { component: 'Headphones', value: 'HD800S + ThieAudio Monarch MKII', status: 'excellent' },
  { component: 'Sound Server', value: 'PipeWire native filter-chain (no EasyEffects)', status: 'excellent' },
  { component: 'Transport', value: 'S32LE path + resample.quality=14 on DX5 (raw sink stays available)', status: 'excellent' },
  { component: 'RT Scheduling', value: 'SCHED_FIFO priority 88 (pipewire group)', status: 'optimal' },
  { component: 'Virtual Sinks', value: '4 headphone sinks (clean / crossfeed / room / movie) + Aural Evolution', status: 'excellent' },
]

const icebergLayers = [
  { level: 1, title: 'BIT-PERFECT TRANSPORT', subtitle: '(Foundation)', desc: 'Raw DX5 sink remains available; processed sinks intentionally alter the stream', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 2, title: 'HEADPHONE CORRECTION', subtitle: null, desc: 'AutoEQ per-headphone IRs with symlink profile switching', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 3, title: 'SPATIAL PROCESSING', subtitle: null, desc: 'bs2b crossfeed + ASH BRIR True Stereo room simulation', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 4, title: 'MOVIE FOLD-DOWN', subtitle: null, desc: 'Headphone DSP Movie sink: 7.1/5.1 → stereo fold-down → AutoEQ → limiter', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 5, title: 'AURAL EVOLUTION', subtitle: '(optional module)', desc: 'Persistent audition sink with level-matched variants via audio-evolve / Noctalia', impact: 'HIGH', color: '#58A6FF', active: true },
  { level: 6, title: 'LOUDNESS & DYNAMICS', subtitle: null, desc: 'ISO 226 loudness comp + GentleDynamics multiband on classic DSP sinks', impact: 'MEDIUM', color: '#F59E0B', active: true },
  { level: 7, title: 'SAFETY LIMITING', subtitle: null, desc: 'ZaMaximX2 limiter at -0.3 dBFS on classic DSP sinks', impact: 'MEDIUM', color: '#F59E0B', active: true },
  { level: 8, title: 'DIMINISHING RETURNS', subtitle: null, desc: 'RT kernel, memory playback, async USB isolation', impact: 'MINIMAL', color: '#6E7681', active: false },
]

export default function AudioPage() {
  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex flex-col items-start justify-between gap-8 px-4 py-12 sm:px-8 sm:py-16 lg:flex-row lg:gap-16 lg:px-[120px]">
          <div className="flex min-w-0 flex-col gap-6">
            <Headphones size={48} className="text-[#F59E0B]" />
            <h1 className="break-all text-3xl font-bold font-mono text-[var(--text-primary)] sm:text-5xl">audiophile_setup/</h1>
            <p className="text-lg text-[var(--text-muted)] leading-relaxed">
              Native PipeWire filter-chain DSP with AutoEQ, crossfeed, BRIR room, and a Movie fold-down sink —
              plus optional Aural Evolution for blind, level-matched listening experiments.
            </p>
          </div>

          {/* Score Badge */}
          <div className="flex w-full flex-col items-center gap-4 p-6 glass rounded-[var(--radius-lg)] border-[rgba(212,180,90,0.35)] sm:w-auto sm:p-8">
            <span className="text-xs font-mono text-[var(--text-muted)]">stack</span>
            <span className="text-4xl font-bold font-mono text-[var(--accent-green)]">PipeWire</span>
            <span className="text-sm text-[var(--accent-green)] ">native filter-chain</span>
          </div>
        </section>

        {/* Current Setup */}
        <section className="px-4 py-12 sm:px-8 sm:py-16 lg:px-[120px]">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-6">// current_setup</p>
          <div
            className="max-w-full overflow-x-auto glass rounded-[var(--radius-lg)]"
            role="region"
            aria-label="Current audio setup"
            tabIndex={0}
          >
            {/* Table Header */}
            <div className="flex min-w-[680px] items-center gap-6 px-6 py-4 bg-[rgba(18,28,38,0.45)]">
              <span className="flex-1 text-sm font-mono text-[var(--text-muted)]">component</span>
              <span className="flex-[2] text-sm font-mono text-[var(--text-muted)]">value</span>
              <span className="w-24 text-sm font-mono text-[var(--text-muted)] text-right">status</span>
            </div>
            {/* Table Rows */}
            {setupRows.map((row, index) => (
              <div
                key={row.component}
                className={`flex min-w-[680px] items-center gap-6 px-6 py-4 bg-[rgba(10,18,26,0.35)] ${
                  index < setupRows.length - 1 ? 'border-b border-[#30363D]' : ''
                }`}
              >
                <span className="flex-1 text-sm font-mono text-[var(--text-primary)]">{row.component}</span>
                <span className="flex-[2] text-sm font-mono text-[var(--text-muted)]">{row.value}</span>
                <span className={`w-24 text-xs font-mono text-right ${
                  row.status === 'excellent' ? 'text-[var(--accent-green)]' : 'text-[var(--accent-blue)]'
                }`}>
                  ● {row.status}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Iceberg */}
        <section className="flex flex-col items-center px-4 py-12 sm:px-8 sm:py-16 lg:px-[120px]">
          <p className="text-sm font-mono text-[var(--text-dim)] mb-8 self-start">// the_audiophile_iceberg</p>
          <div className="w-full max-w-[900px] glass rounded-[var(--radius-lg)] overflow-hidden">
            {/* Waterline */}
            <div className="flex items-center justify-center h-10 bg-[rgba(110,200,196,0.15)]">
              <span className="text-xs font-mono text-[var(--accent-blue)]">═══ WATERLINE ═══</span>
            </div>

            {/* Layers */}
            {icebergLayers.map((layer) => (
              <div
                key={layer.level}
                className="flex flex-col items-start justify-between gap-3 px-4 py-4 sm:flex-row sm:items-center sm:px-6"
                style={{
                  backgroundColor: `${layer.color}08`,
                  borderLeft: `4px solid ${layer.color}`,
                }}
              >
                <div className="flex min-w-0 items-start gap-3 sm:items-center sm:gap-4">
                  {layer.active ? (
                    <Check size={16} className="text-[var(--accent-green)]" />
                  ) : (
                    <X size={16} className="text-[var(--text-dim)]" />
                  )}
                  <div>
                    <span className="text-sm font-mono text-[var(--text-primary)]">
                      LAYER {layer.level}: {layer.title}
                    </span>
                    {layer.subtitle && (
                      <span className="text-xs font-mono text-[var(--accent-green)] ml-2">{layer.subtitle}</span>
                    )}
                    <p className="text-xs text-[var(--text-dim)]  mt-1">{layer.desc}</p>
                  </div>
                </div>
                <span className={`text-xs font-mono ${
                  layer.impact === 'HIGH' ? 'text-[var(--accent-green)]' :
                  layer.impact === 'MEDIUM' ? 'text-[#F59E0B]' :
                  layer.impact === 'LOW' ? 'text-[var(--text-muted)]' :
                  layer.impact === 'MINIMAL' ? 'text-[var(--text-dim)]' :
                  'text-[#F85149]'
                }`}>
                  {layer.impact}
                </span>
              </div>
            ))}
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
