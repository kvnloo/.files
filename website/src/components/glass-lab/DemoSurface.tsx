'use client'

import { Sparkles } from 'lucide-react'

/** Identical demo content inside each glass variant (A / B / C). */
export function DemoCardBody() {
  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-[var(--accent-blue)]" />
        <h3 className="font-mono text-base font-semibold text-[var(--text-primary)]">
          featured_panel/
        </h3>
      </div>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        Same copy in every column so you can judge refraction, frost, and
        readability over Forgotten Ruins — not the markup.
      </p>
      <ul className="space-y-1 font-mono text-xs text-[var(--text-muted)]">
        <li>hyprland · noctalia · pipewire</li>
        <li>contrast check · teal accent</li>
      </ul>
    </div>
  )
}

export function DemoButtonLabel() {
  return <span className="font-mono text-sm font-medium">apply theme</span>
}
