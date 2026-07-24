import { clsx } from 'clsx'
import { ReactNode } from 'react'

interface GlassCardProps {
  children: ReactNode
  className?: string
  hover?: boolean
  strong?: boolean
}

export function GlassCard({ children, className, hover = true, strong = false }: GlassCardProps) {
  return (
    <div
      className={clsx(
        strong ? 'glass-strong' : 'glass',
        'rounded-[var(--radius-lg)] p-6',
        hover && 'card-hover cursor-pointer',
        className
      )}
    >
      <div className="relative z-10">{children}</div>
    </div>
  )
}
