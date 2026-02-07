'use client'

import { Header, Footer } from '@/components'
import { Headphones, Check, X } from 'lucide-react'

const setupRows = [
  { component: 'DAC', value: 'Topping DX5 (32-bit, 768kHz)', status: 'excellent' },
  { component: 'Headphones', value: 'HD800S + ThieAudio Monarch MKII', status: 'excellent' },
  { component: 'Sound Server', value: 'PipeWire 1.5.85', status: 'excellent' },
  { component: 'Session Manager', value: 'WirePlumber 1.5.85', status: 'excellent' },
  { component: 'Bit Depth', value: '32-bit float (native)', status: 'optimal' },
]

const icebergLayers = [
  { level: 1, title: 'BIT-PERFECT CHAIN', subtitle: '(Essential)', desc: 'Avoid resampling, native sample rate', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 2, title: 'HEADPHONE CORRECTION', subtitle: null, desc: 'AutoEQ / Harman target', impact: 'HIGH', color: '#3FB950', active: true },
  { level: 3, title: 'DSP & PSYCHOACOUSTICS', subtitle: null, desc: 'Crossfeed, dynamic range', impact: 'MEDIUM', color: '#F59E0B', active: true },
  { level: 4, title: 'SOFTWARE STACK', subtitle: null, desc: 'PipeWire, RT scheduling', impact: 'MEDIUM', color: '#58A6FF', active: true },
  { level: 5, title: 'ADVANCED RECONSTRUCTION', subtitle: null, desc: 'HQPlayer, native DSD', impact: 'LOW', color: '#A371F7', active: false },
  { level: 6, title: 'HARDWARE ENVIRONMENT', subtitle: null, desc: 'Async USB, isolation', impact: 'LOW', color: '#58A6FF', active: false },
  { level: 7, title: 'DIMINISHING RETURNS', subtitle: null, desc: 'RT kernel, memory playback', impact: 'MINIMAL', color: '#6E7681', active: false },
  { level: 8, title: 'SNAKE OIL', subtitle: null, desc: 'Audiophile cables, MQA', impact: 'NONE', color: '#F85149', active: false },
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
              Bit-perfect PipeWire 1.5.85 audio configuration with AutoEQ convolver and crossfeed DSP for the ultimate listening experience.
            </p>
          </div>

          {/* Score Badge */}
          <div className="flex flex-col items-center gap-4 p-8 bg-[#ffffff08] border border-[#F59E0B40] rounded-lg backdrop-blur-xl">
            <span className="text-xs font-mono text-[#8B949E]">optimization_score</span>
            <span className="text-6xl font-bold font-mono text-[#F59E0B]">98%</span>
            <span className="text-sm text-[#3FB950] font-[Inter]">bit-perfect achieved</span>
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
