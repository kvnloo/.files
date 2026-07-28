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

const accentActiveClass: Record<FilterAccent, string> = {
  teal: 'filter-chip-active-teal',
  green: 'filter-chip-active-green',
  purple: 'filter-chip-active-purple',
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
              // Same glass family as wallpaper resolution badges (blur + inset highlight)
              // denser fill via .filter-chip so text stays readable over busy backgrounds
              'filter-chip px-3 py-1.5 rounded-[var(--radius-sm)] font-mono text-xs font-medium transition-colors',
              isActive
                ? accentActiveClass[accent]
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
