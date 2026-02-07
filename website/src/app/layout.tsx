import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '.files + UX | Dotfiles Showcase',
  description: 'Meticulously organized Linux dotfiles & visual assets. 72+ configs, 160+ wallpapers, 80+ icons, 10 themes.',
  keywords: ['dotfiles', 'linux', 'i3', 'polybar', 'pipewire', 'zsh', 'configuration', 'rice'],
  authors: [{ name: 'kvn' }],
  openGraph: {
    title: '.files + UX | Dotfiles Showcase',
    description: 'Meticulously organized Linux dotfiles & visual assets',
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
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
