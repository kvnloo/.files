import Image from 'next/image'

interface AssetImageProps {
  src: string
  alt: string
  className?: string
  fill?: boolean
  width?: number
  height?: number
}

export function AssetImage({ src, alt, className, fill, width, height }: AssetImageProps) {
  // Next.js Image component automatically handles basePath
  if (fill) {
    return (
      <Image
        src={src}
        alt={alt}
        className={className}
        fill
        sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
      />
    )
  }

  return (
    <Image
      src={src}
      alt={alt}
      className={className}
      width={width || 400}
      height={height || 300}
    />
  )
}
