'use client'

import { Header, Footer } from '@/components'
import { Headphones, Check, X } from 'lucide-react'

const setupRows = [
  { component: 'DAC', value: 'Topping DX5 USB DAC', status: 'excellent' },
  { component: 'Headphones', value: 'HD800S + ThieAudio Monarch MKII', status: 'excellent' },
  { component: 'Sound Server', value: 'PipeWire native filter-chain', status: 'excellent' },
  { component: 'Transport', value: 'S32LE bit-perfect, resample.quality=14', status: 'excellent' },
  { component: 'RT Scheduling', value: 'SCHED_FIFO priority 88 (pipewire group)', status: 'optimal' },
  { component: 'Virtual Sinks', value: '3-sink instant A/B/C spatial switching', status: 'excellent' },
]

const icebergLayers = [
  { level: 1, title: 'BIT-PERFECT TRANSPORT', subtitle: '(Foundation)', desc: 'S32LE native, no resampling, quality=14 SRC', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 2, title: 'HEADPHONE CORRECTION', subtitle: null, desc: 'AutoEQ per-headphone IEF Preference 2025 + Harman target curves', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 3, title: 'SPATIAL PROCESSING', subtitle: null, desc: 'bs2b crossfeed + ASH BRIR True Stereo room simulation', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 4, title: 'LOUDNESS & DYNAMICS', subtitle: null, desc: 'ISO 226:2003 loudness comp, GentleDynamics 8-band Bark-scale MBC', impact: 'MEDIUM', color: '#F59E0B', active: true },
  { level: 5, title: 'SAFETY LIMITING', subtitle: null, desc: 'ZaMaximX2 limiter at -0.3 dBFS', impact: 'MEDIUM', color: '#F59E0B', active: true },
  { level: 6, title: 'RT SCHEDULING & SWITCHING', subtitle: null, desc: 'SCHED_FIFO pri 88, headphone-switch.sh instant profiles', impact: 'MEDIUM', color: '#58A6FF', active: true },
  { level: 7, title: 'DIMINISHING RETURNS', subtitle: null, desc: 'RT kernel, memory playback, async USB isolation', impact: 'MINIMAL', color: '#6E7681', active: false },
  { level: 8, title: 'SNAKE OIL', subtitle: null, desc: 'Audiophile cables, MQA, quantum dot fuses', impact: 'NONE', color: '#F85149', active: false },
]

export default function AudioPage() {
  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="flex items-start justify-between gap-16 py-16 px-[120px]">
          <div className="flex flex-col gap-6 flex-1">
            <Headphones size={48} className="text-[#F59E0B]" />
            <h1 className="text-5xl font-bold font-mono text-[#E6EDF3]">audiophile_setup/</h1>
            <p className="text-lg text-[#8B949E] font-[Inter] leading-relaxed">
              Bit-perfect PipeWire native filter-chain with AutoEQ correction, BRIR True Stereo spatial, bs2b crossfeed, loudness compensation, GentleDynamics multiband compressor, and 3-sink instant A/B/C switching.
            </p>
          </div>

          {/* Score Badge */}
          <div className="flex flex-col items-center gap-4 p-8 bg-[#ffffff08] border border-[#F59E0B40] rounded-lg backdrop-blur-xl">
            <span className="text-xs font-mono text-[#8B949E]">optimization_score</span>
            <span className="text-6xl font-bold font-mono text-[#3FB950]">100%</span>
            <span className="text-sm text-[#3FB950] font-[Inter]">stack complete</span>
          </div>
        </section>

        {/* Current Setup */}
        <section className="py-16 px-[120px]">
          <p className="text-sm font-mono text-[#6E7681] mb-6">// current_setup</p>
          <div className="border border-[#30363D] rounded-lg overflow-hidden">
            {/* Table Header */}
            <div className="flex items-center gap-6 px-6 py-4 bg-[#21262D]">
              <span className="flex-1 text-sm font-mono text-[#8B949E]">component</span>
              <span className="flex-[2] text-sm font-mono text-[#8B949E]">value</span>
              <span className="w-24 text-sm font-mono text-[#8B949E] text-right">status</span>
            </div>
            {/* Table Rows */}
            {setupRows.map((row, index) => (
              <div
                key={row.component}
                className={`flex items-center gap-6 px-6 py-4 bg-[#161B22] ${
                  index < setupRows.length - 1 ? 'border-b border-[#30363D]' : ''
                }`}
              >
                <span className="flex-1 text-sm font-mono text-[#E6EDF3]">{row.component}</span>
                <span className="flex-[2] text-sm font-mono text-[#8B949E]">{row.value}</span>
                <span className={`w-24 text-xs font-mono text-right ${
                  row.status === 'excellent' ? 'text-[#3FB950]' : 'text-[#58A6FF]'
                }`}>
                  ● {row.status}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Iceberg */}
        <section className="py-16 px-[120px] flex flex-col items-center">
          <p className="text-sm font-mono text-[#6E7681] mb-8 self-start">// the_audiophile_iceberg</p>
          <div className="w-[900px] border border-[#30363D] rounded-lg overflow-hidden">
            {/* Waterline */}
            <div className="flex items-center justify-center h-10 bg-[#58A6FF20]">
              <span className="text-xs font-mono text-[#58A6FF]">═══ WATERLINE ═══</span>
            </div>

            {/* Layers */}
            {icebergLayers.map((layer) => (
              <div
                key={layer.level}
                className="flex items-center justify-between px-6 py-4"
                style={{
                  backgroundColor: `${layer.color}08`,
                  borderLeft: `4px solid ${layer.color}`,
                }}
              >
                <div className="flex items-center gap-4">
                  {layer.active ? (
                    <Check size={16} className="text-[#3FB950]" />
                  ) : (
                    <X size={16} className="text-[#6E7681]" />
                  )}
                  <div>
                    <span className="text-sm font-mono text-[#E6EDF3]">
                      LAYER {layer.level}: {layer.title}
                    </span>
                    {layer.subtitle && (
                      <span className="text-xs font-mono text-[#3FB950] ml-2">{layer.subtitle}</span>
                    )}
                    <p className="text-xs text-[#6E7681] font-[Inter] mt-1">{layer.desc}</p>
                  </div>
                </div>
                <span className={`text-xs font-mono ${
                  layer.impact === 'HIGH' ? 'text-[#3FB950]' :
                  layer.impact === 'MEDIUM' ? 'text-[#F59E0B]' :
                  layer.impact === 'LOW' ? 'text-[#8B949E]' :
                  layer.impact === 'MINIMAL' ? 'text-[#6E7681]' :
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
