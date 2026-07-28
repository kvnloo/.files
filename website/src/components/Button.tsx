import { clsx } from 'clsx'
import { ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost'

interface ButtonProps {
  children: ReactNode
  variant?: ButtonVariant
  className?: string
  href?: string
  onClick?: () => void
  disabled?: boolean
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--accent-teal)] text-[#041014] font-semibold hover:bg-[var(--accent-blue)] shadow-[var(--shadow-glow)]',
  secondary:
    'glass-hairline text-[var(--text-secondary)] hover:border-[var(--accent-blue)]',
  ghost:
    'bg-transparent text-[var(--text-muted)] border border-[var(--border-default)] hover:text-[var(--text-primary)] hover:border-[var(--text-muted)]',
}

export function Button({
  children,
  variant = 'primary',
  className,
  href,
  onClick,
  disabled,
}: ButtonProps) {
  const baseStyles = clsx(
    'inline-flex items-center justify-center gap-2 px-6 py-3 rounded-[var(--radius-md)] font-mono text-sm transition-colors',
    variantStyles[variant],
    disabled && 'opacity-50 cursor-not-allowed',
    className
  )

  if (href) {
    return (
      <a href={href} className={baseStyles}>
        {children}
      </a>
    )
  }

  return (
    <button onClick={onClick} disabled={disabled} className={baseStyles}>
      {children}
    </button>
  )
}
