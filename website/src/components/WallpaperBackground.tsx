import { assetPath } from '@/lib/utils'

const POSTER_SRC = assetPath('/media/forgotten-ruins-poster.jpg')
const POSTER_WEBP = assetPath('/media/forgotten-ruins-poster.webp')

/**
 * Site-wide Forgotten Ruins backdrop (static poster).
 * Video/WebM playback removed until a native Wallpaper Engine bridge exists.
 */
export function WallpaperBackground() {
  return (
    <div className="wallpaper-root" aria-hidden="true">
      <picture>
        <source srcSet={POSTER_WEBP} type="image/webp" />
        <img
          className="wallpaper-poster"
          src={POSTER_SRC}
          alt=""
          decoding="async"
          fetchPriority="high"
        />
      </picture>

      <div className="wallpaper-scrim" />
      <div className="wallpaper-vignette" />
      <div className="wallpaper-noise" />
    </div>
  )
}
