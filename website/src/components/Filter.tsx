'use client'

import { clsx } from 'clsx'

interface FilterOption {
  label: string
  value: string
}

type FilterAccent = 'teal' | 'green' | 'purple'

interface FilterProps {
  options: FilterOption[]
  value: string
  onChange: (value: string) => void
  className?: string
  /** Page accent for the selected chip — matches each gallery’s existing accent. */
  accent?: FilterAccent
}

const accentActive: Record<FilterAccent, string> = {
  teal:
    'text-[var(--accent-blue)] border-[var(--accent-blue)] bg-[rgba(110,200,196,0.22)] shadow-[0_0_12px_rgba(110,200,196,0.2)]',
  green:
    'text-[var(--accent-green)] border-[var(--accent-green)] bg-[rgba(111,191,122,0.22)] shadow-[0_0_12px_rgba(111,191,122,0.2)]',
  purple:
    'text-[var(--accent-purple)] border-[var(--accent-purple)] bg-[rgba(126,184,201,0.22)] shadow-[0_0_12px_rgba(126,184,201,0.2)]',
}

export function Filter({
  options,
  value,
  onChange,
  className,
  accent = 'teal',
}: FilterProps) {
  return (
    <div className={clsx('flex flex-wrap gap-2', className)}>
      {options.map((option) => {
        const isActive = option.value === value

        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={clsx(
              // Same glass family as wallpaper resolution badges (glass-hairline + radius-sm)
              'px-3 py-1.5 rounded-[var(--radius-sm)] font-mono text-xs font-medium transition-colors',
              'glass-hairline bg-[rgba(12,20,28,0.52)]',
              isActive
                ? accentActive[accent]
                : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)]'
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
