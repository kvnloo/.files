'use client'

import { clsx } from 'clsx'

interface FilterOption {
  label: string
  value: string
}

interface FilterProps {
  options: FilterOption[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function Filter({ options, value, onChange, className }: FilterProps) {
  return (
    <div className={clsx('flex flex-wrap gap-2', className)}>
      {options.map((option) => {
        const isActive = option.value === value

        return (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            className={clsx(
              'px-3 py-1.5 rounded-md font-mono text-xs font-medium transition-colors',
              isActive
                ? 'bg-[rgba(88,166,255,0.1)] text-[var(--accent-blue)] border border-[var(--accent-blue)]'
                : 'bg-transparent text-[var(--text-muted)] border border-[var(--border-default)] hover:text-[var(--text-primary)] hover:border-[var(--text-muted)]'
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
