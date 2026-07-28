import { clsx } from 'clsx'

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'count' | 'os-linux' | 'os-macos' | 'os-android'

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  className?: string
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-[#238636] text-white',
  warning: 'bg-[var(--accent-yellow)] text-[var(--bg-primary)]',
  error: 'bg-[var(--accent-red)] text-white',
  info: 'bg-[var(--accent-blue)] text-[var(--bg-primary)]',
  count: 'bg-[var(--bg-tertiary)] text-[var(--accent-blue)] border border-[var(--border-default)]',
  'os-linux': 'bg-[#D29922]/20 text-[#D29922] border border-[#D29922]/30',
  'os-macos': 'bg-[#8B949E]/20 text-[#8B949E] border border-[#8B949E]/30',
  'os-android': 'bg-[#3FB950]/20 text-[#3FB950] border border-[#3FB950]/30',
}

export function Badge({ children, variant = 'info', className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center justify-center px-2 py-1 rounded-[var(--radius-sm)] font-mono text-[10px] font-semibold',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  )
}

interface CountBadgeProps {
  count: number | string
  label: string
  className?: string
}

export function CountBadge({ count, label, className }: CountBadgeProps) {
  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center gap-1 px-6 py-3 rounded-[var(--radius-lg)] glass',
        className
      )}
    >
      <span className="font-mono text-3xl font-bold text-[var(--accent-blue)] relative z-10">
        {count}
      </span>
      <span className="font-mono text-sm font-medium text-[var(--text-muted)] relative z-10">
        {label}
      </span>
    </div>
  )
}
