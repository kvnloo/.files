import { clsx } from 'clsx'
import { LucideIcon } from 'lucide-react'

interface IconCardProps {
  icon: LucideIcon
  label: string
  className?: string
  onClick?: () => void
}

export function IconCard({ icon: Icon, label, className, onClick }: IconCardProps) {
  return (
    <div
      className={clsx(
        'flex flex-col items-center gap-3 p-4 rounded-[var(--radius-lg)] bg-[var(--bg-secondary)] border border-[var(--border-muted)] card-hover',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      <Icon size={32} className="text-[var(--accent-blue)]" />
      <span className="font-mono text-xs font-medium text-[var(--text-secondary)]">
        {label}
      </span>
    </div>
  )
}
