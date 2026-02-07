'use client'

import { Header, Footer, GlassCard, TerminalBlock, Button, Badge } from '@/components'
import { Headphones, Check, AlertTriangle, FileText, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'

const setupSummary = [
  { component: 'DAC', value: 'Topping DX5 (32-bit, 768kHz)', status: 'excellent' },
  { component: 'Headphones', value: 'HD800S + ThieAudio Monarch MKII', status: 'excellent' },
  { component: 'Sound Server', value: 'PipeWire 1.5.85 (built from source)', status: 'excellent' },
  { component: 'Session Manager', value: 'WirePlumber 1.5.85', status: 'excellent' },
  { component: 'Bit Depth', value: '32-bit float (native to DAC)', status: 'optimal' },
  { component: 'Sample Rate', value: '44.1-768kHz adaptive', status: 'optimal' },
]

const icebergLayers = [
  {
    level: 1,
    title: 'BIT-PERFECT CHAIN',
    subtitle: '(Essential)',
    description: 'Avoid resampling, lossless source, native sample rate, bypass software volume',
    impact: 'HIGH',
    status: 'active',
  },
  {
    level: 2,
    title: 'HEADPHONE CORRECTION',
    subtitle: null,
    description: 'AutoEQ / Harman target, convolution filters',
    impact: 'HIGH',
    status: 'active',
  },
  {
    level: 3,
    title: 'DSP & PSYCHOACOUSTICS',
    subtitle: null,
    description: 'Crossfeed (BS2B-style), dynamic range management',
    impact: 'MEDIUM',
    status: 'active',
  },
  {
    level: 4,
    title: 'SOFTWARE STACK TUNING',
    subtitle: null,
    description: 'Sound server selection, RT scheduling, buffer optimization',
    impact: 'MEDIUM',
    status: 'active',
  },
  {
    level: 5,
    title: 'ADVANCED RECONSTRUCTION',
    subtitle: null,
    description: 'HQPlayer upsampling, native DSD',
    impact: 'LOW',
    status: 'optional',
  },
  {
    level: 6,
    title: 'HARDWARE ENVIRONMENT',
    subtitle: null,
    description: 'Async USB mode, USB isolation (if needed)',
    impact: 'LOW',
    status: 'optional',
  },
  {
    level: 7,
    title: 'EXTREME DIMINISHING RETURNS',
    subtitle: null,
    description: 'RT kernel, memory playback, process isolation',
    impact: 'MINIMAL',
    status: 'not-needed',
  },
  {
    level: 8,
    title: 'PLACEBO / SNAKE OIL',
    subtitle: null,
    description: 'Audiophile USB cables, MQA, "quantum" anything',
    impact: 'NONE',
    status: 'avoid',
  },
]

const improvements = [
  { aspect: 'Sample rate switching', before: '44.1/48kHz only', after: 'Full range 44.1-768kHz' },
  { aspect: 'Latency', before: '~20-40ms', after: '~5-10ms' },
  { aspect: 'Buffer management', before: 'Fixed', after: 'Adaptive quantum' },
  { aspect: 'Resampling quality', before: 'speex-float-10', after: 'Native passthrough' },
  { aspect: 'Session management', before: 'Basic', after: 'WirePlumber rules' },
  { aspect: 'DSP integration', before: 'PulseEffects (legacy)', after: 'EasyEffects (native)' },
]

const documentationFiles = [
  { name: 'README.md', description: 'Main PipeWire setup guide' },
  { name: 'AUDIOPHILE-OPTIMIZATION.md', description: 'Complete optimization guide with iceberg diagram' },
  { name: 'AUTOEQ-CONVOLUTION-GUIDE.md', description: 'AutoEQ + EasyEffects setup' },
  { name: 'TROUBLESHOOTING.md', description: 'Common issues and solutions' },
  { name: 'STUTTER-FIX-TUNING.md', description: 'Buffer tuning for stutter issues' },
  { name: 'DROPOUT-SOLUTION.md', description: 'Audio dropout fixes' },
]

export default function AudioPage() {
  const [expandedLayer, setExpandedLayer] = useState<number | null>(null)

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'excellent':
        return <Badge variant="success">Excellent</Badge>
      case 'optimal':
        return <Badge variant="info">Optimal</Badge>
      case 'active':
        return <Badge variant="success">Active</Badge>
      case 'optional':
        return <Badge variant="warning">Optional</Badge>
      case 'not-needed':
        return <span className="text-[var(--text-dim)] font-mono text-xs">Not Needed</span>
      case 'avoid':
        return <Badge variant="error">Avoid</Badge>
      default:
        return null
    }
  }

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'HIGH':
        return 'text-[var(--accent-green)]'
      case 'MEDIUM':
        return 'text-[var(--accent-yellow)]'
      case 'LOW':
        return 'text-[var(--text-muted)]'
      case 'MINIMAL':
        return 'text-[var(--text-dim)]'
      case 'NONE':
        return 'text-[var(--accent-red)]'
      default:
        return 'text-[var(--text-muted)]'
    }
  }

  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero */}
        <section className="container py-16">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-8">
            <div>
              <div className="inline-flex items-center gap-3 mb-6">
                <Headphones size={48} className="text-[var(--accent-yellow)]" />
              </div>
              <h1 className="text-3xl md:text-5xl font-bold font-mono mb-4">
                audiophile_setup/
              </h1>
              <p className="text-[var(--text-muted)] max-w-xl mb-6">
                Bit-perfect PipeWire 1.5.85 audio configuration with AutoEQ convolver and crossfeed DSP for the ultimate listening experience.
              </p>
            </div>

            {/* Score Badge */}
            <div className="glass rounded-xl p-6 text-center">
              <div className="text-5xl font-bold gradient-text mb-2">98%</div>
              <div className="font-mono text-sm text-[var(--text-muted)]">Optimization Score</div>
            </div>
          </div>
        </section>

        {/* Current Setup */}
        <section className="container pb-16">
          <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-6">
            → Current Configuration
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border-default)]">
                  <th className="text-left py-3 px-4 font-mono text-sm text-[var(--text-muted)]">Component</th>
                  <th className="text-left py-3 px-4 font-mono text-sm text-[var(--text-muted)]">Value</th>
                  <th className="text-right py-3 px-4 font-mono text-sm text-[var(--text-muted)]">Status</th>
                </tr>
              </thead>
              <tbody>
                {setupSummary.map((row) => (
                  <tr key={row.component} className="border-b border-[var(--border-muted)]">
                    <td className="py-3 px-4 font-mono text-sm text-[var(--text-secondary)] font-medium">
                      {row.component}
                    </td>
                    <td className="py-3 px-4 font-mono text-sm text-[var(--text-muted)]">
                      {row.value}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {getStatusBadge(row.status)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Iceberg Diagram */}
        <section className="container pb-16">
          <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-2">
            → The Audiophile Optimization Iceberg
          </h2>
          <p className="font-mono text-sm text-[var(--text-muted)] mb-8">
            Click each layer to see details. Green = implemented in this setup.
          </p>

          <div className="max-w-4xl mx-auto space-y-2">
            {icebergLayers.map((layer) => (
              <div
                key={layer.level}
                className={`
                  rounded-lg border transition-all cursor-pointer
                  ${layer.status === 'active'
                    ? 'border-[var(--accent-green)]/30 bg-[var(--accent-green)]/5'
                    : layer.status === 'avoid'
                    ? 'border-[var(--accent-red)]/30 bg-[var(--accent-red)]/5'
                    : 'border-[var(--border-default)] bg-[var(--bg-secondary)]'
                  }
                `}
                style={{
                  marginLeft: `${(layer.level - 1) * 12}px`,
                  marginRight: `${(8 - layer.level) * 12}px`,
                }}
                onClick={() => setExpandedLayer(expandedLayer === layer.level ? null : layer.level)}
              >
                <div className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-3">
                    {layer.status === 'active' && (
                      <Check size={16} className="text-[var(--accent-green)]" />
                    )}
                    {layer.status === 'avoid' && (
                      <AlertTriangle size={16} className="text-[var(--accent-red)]" />
                    )}
                    <div>
                      <span className="font-mono text-sm font-medium text-[var(--text-secondary)]">
                        LAYER {layer.level}: {layer.title}
                      </span>
                      {layer.subtitle && (
                        <span className="font-mono text-xs text-[var(--accent-green)] ml-2">
                          {layer.subtitle}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`font-mono text-xs ${getImpactColor(layer.impact)}`}>
                      {layer.impact}
                    </span>
                    {expandedLayer === layer.level ? (
                      <ChevronUp size={16} className="text-[var(--text-muted)]" />
                    ) : (
                      <ChevronDown size={16} className="text-[var(--text-muted)]" />
                    )}
                  </div>
                </div>
                {expandedLayer === layer.level && (
                  <div className="px-4 pb-4 border-t border-[var(--border-muted)] pt-3">
                    <p className="font-mono text-sm text-[var(--text-muted)]">
                      {layer.description}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* PulseAudio vs PipeWire Comparison */}
        <section className="container pb-16">
          <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-6">
            → What Changed: PulseAudio → PipeWire
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border-default)]">
                  <th className="text-left py-3 px-4 font-mono text-sm text-[var(--text-muted)]">Improvement</th>
                  <th className="text-left py-3 px-4 font-mono text-sm text-[var(--accent-red)]">Before (PulseAudio)</th>
                  <th className="text-left py-3 px-4 font-mono text-sm text-[var(--accent-green)]">After (PipeWire)</th>
                </tr>
              </thead>
              <tbody>
                {improvements.map((row) => (
                  <tr key={row.aspect} className="border-b border-[var(--border-muted)]">
                    <td className="py-3 px-4 font-mono text-sm text-[var(--text-secondary)] font-medium">
                      {row.aspect}
                    </td>
                    <td className="py-3 px-4 font-mono text-sm text-[var(--text-dim)]">
                      {row.before}
                    </td>
                    <td className="py-3 px-4 font-mono text-sm text-[var(--text-secondary)]">
                      {row.after}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Documentation Files */}
        <section className="container pb-16">
          <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-6">
            → Documentation (11 files)
          </h2>
          <div className="grid md:grid-cols-2 gap-4">
            {documentationFiles.map((doc) => (
              <a
                key={doc.name}
                href={`https://github.com/kvn/.files/blob/main/config/pipewire/${doc.name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-3 p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-muted)] hover:border-[var(--accent-blue)]/50 transition-colors"
              >
                <FileText size={20} className="text-[var(--accent-blue)] flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm font-medium text-[var(--text-secondary)]">
                    {doc.name}
                  </div>
                  <div className="font-mono text-xs text-[var(--text-muted)] truncate">
                    {doc.description}
                  </div>
                </div>
                <ExternalLink size={14} className="text-[var(--text-dim)] flex-shrink-0" />
              </a>
            ))}
          </div>
        </section>

        {/* Quick Install */}
        <section className="container pb-16">
          <GlassCard hover={false} className="max-w-3xl mx-auto">
            <h2 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-4">
              Quick Setup
            </h2>
            <TerminalBlock
              title="install"
              lines={[
                { text: '# Install PipeWire + WirePlumber configs', type: 'output' },
                { text: '$ stow -t ~/.config pipewire wireplumber', type: 'command' },
                { text: '', type: 'output' },
                { text: '# Apply EasyEffects presets', type: 'output' },
                { text: '$ cp -r easyeffects/* ~/.config/easyeffects/', type: 'command' },
                { text: '', type: 'output' },
                { text: '# Restart PipeWire', type: 'output' },
                { text: '$ systemctl --user restart pipewire pipewire-pulse wireplumber', type: 'command' },
              ]}
            />
          </GlassCard>
        </section>
      </main>
      <Footer />
    </>
  )
}
