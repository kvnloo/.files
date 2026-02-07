'use client'

import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

interface TerminalBlockProps {
  lines: Array<{
    text: string
    type?: 'command' | 'output' | 'success' | 'error'
  }>
  title?: string
}

export function TerminalBlock({ lines, title }: TerminalBlockProps) {
  const [copied, setCopied] = useState(false)

  const copyToClipboard = () => {
    const commands = lines
      .filter((line) => line.type === 'command' || !line.type)
      .map((line) => line.text.replace(/^\$ /, ''))
      .join('\n')

    navigator.clipboard.writeText(commands)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const getLineColor = (type?: string) => {
    switch (type) {
      case 'success':
        return 'text-[var(--accent-green)]'
      case 'error':
        return 'text-[var(--accent-red)]'
      case 'output':
        return 'text-[var(--text-muted)]'
      default:
        return 'text-[var(--text-secondary)]'
    }
  }

  return (
    <div className="rounded-lg overflow-hidden border border-[var(--border-default)]">
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[var(--bg-secondary)]">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-[var(--accent-red)]" />
          <div className="w-3 h-3 rounded-full bg-[var(--accent-yellow)]" />
          <div className="w-3 h-3 rounded-full bg-[var(--accent-green)]" />
        </div>
        {title && (
          <span className="text-[var(--text-muted)] font-mono text-xs">
            {title}
          </span>
        )}
        <button
          onClick={copyToClipboard}
          className="flex items-center gap-1 px-2 py-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          aria-label="Copy to clipboard"
        >
          {copied ? (
            <>
              <Check size={14} className="text-[var(--accent-green)]" />
              <span className="font-mono text-xs text-[var(--accent-green)]">Copied!</span>
            </>
          ) : (
            <>
              <Copy size={14} />
              <span className="font-mono text-xs">Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Terminal Body */}
      <div className="p-6 bg-[var(--bg-primary)]">
        <div className="flex flex-col gap-2">
          {lines.map((line, index) => (
            <code
              key={index}
              className={`font-mono text-sm ${getLineColor(line.type)}`}
            >
              {line.text}
            </code>
          ))}
        </div>
      </div>
    </div>
  )
}
