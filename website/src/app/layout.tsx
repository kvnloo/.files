import type { Metadata } from 'next'
import { WallpaperShell } from '@/components/wallpaper/WallpaperShell'
import './globals.css'

export const metadata: Metadata = {
  title: '.files + UX | Dotfiles Showcase',
  description: 'Hyprland/Noctalia desktop, PipeWire DSP, agent onboarding, and curated wallpapers & icons.',
  keywords: ['dotfiles', 'linux', 'hyprland', 'noctalia', 'waybar', 'pipewire', 'nvim', 'tmux', 'zsh', 'sunshine'],
  authors: [{ name: 'kvn' }],
  openGraph: {
    title: '.files + UX | Dotfiles Showcase',
    description: 'Hyprland desktop, PipeWire DSP, and curated visual assets',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <WallpaperShell>{children}</WallpaperShell>
      </body>
    </html>
  )
}
