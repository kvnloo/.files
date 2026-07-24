import { clsx } from 'clsx'
import { ReactNode } from 'react'

interface PreviewCardProps {
  title: string
  description?: string
  image?: string
  children?: ReactNode
  className?: string
  onClick?: () => void
}

export function PreviewCard({
  title,
  description,
  image,
  children,
  className,
  onClick,
}: PreviewCardProps) {
  return (
    <div
      className={clsx(
        'rounded-[var(--radius-lg)] overflow-hidden glass card-hover',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {image && (
        <div className="aspect-video overflow-hidden bg-[rgba(0,0,0,0.25)] relative z-10">
          <img
            src={image}
            alt={title}
            className="w-full h-full object-cover"
          />
        </div>
      )}
      <div className="p-5 relative z-10">
        <h3 className="font-mono text-base font-semibold text-[var(--text-primary)] mb-2">
          {title}
        </h3>
        {description && (
          <p className="font-mono text-xs text-[var(--text-muted)]">
            {description}
          </p>
        )}
        {children}
      </div>
    </div>
  )
}
