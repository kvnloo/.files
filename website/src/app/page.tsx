import {
  Header,
  Footer,
  GlassCard,
  TerminalBlock,
  Button,
  CountBadge,
} from '@/components'
import {
  Palette,
  Image,
  Sparkles,
  Music,
  Terminal,
  Settings,
  Monitor,
  Layers,
  Folder,
} from 'lucide-react'
import Link from 'next/link'

const stats = [
  { count: '72+', label: 'Configs' },
  { count: '160+', label: 'Wallpapers' },
  { count: '80+', label: 'Icons' },
  { count: '10', label: 'Themes' },
  { count: '3', label: 'Platforms' },
]

const categories = [
  {
    icon: Monitor,
    title: 'Desktop Environment',
    description: 'i3 window manager, Polybar, Rofi launcher, Picom compositor, Dunst notifications',
    href: '/themes',
    count: 15,
    os: ['linux'],
  },
  {
    icon: Palette,
    title: '10 Polybar Themes',
    description: 'Complete theme collection with Pywal integration for dynamic color matching',
    href: '/themes',
    count: 10,
    os: ['linux'],
    featured: true,
  },
  {
    icon: Music,
    title: 'Audiophile Setup',
    description: 'PipeWire 1.5.85 bit-perfect audio, WirePlumber DAC rules, EasyEffects + AutoEQ',
    href: '/audio',
    count: 11,
    os: ['linux'],
    featured: true,
  },
  {
    icon: Terminal,
    title: 'Shell Environment',
    description: 'Modular ZSH with oh-my-zsh, Fish shell, Tmux multiplexer, custom aliases',
    href: '#shell',
    count: 8,
    os: ['linux', 'macos'],
  },
  {
    icon: Settings,
    title: 'System Services',
    description: 'Systemd user services, autostart scripts, environment configuration',
    href: '#system',
    count: 6,
    os: ['linux'],
  },
  {
    icon: Layers,
    title: 'Development Tools',
    description: 'Vim/Neovim configs, Git settings, fonts, development environment setup',
    href: '#dev',
    count: 12,
    os: ['linux', 'macos'],
  },
]

const featuresHighlights = [
  {
    icon: Folder,
    title: 'Modular Architecture',
    description: 'Clean separation of concerns with stow-compatible symlink structure for easy deployment',
  },
  {
    icon: Palette,
    title: '10 Complete Themes',
    description: 'Polybar themes with Pywal integration for automatic color matching with wallpapers',
  },
  {
    icon: Music,
    title: 'Audiophile Audio',
    description: 'PipeWire bit-perfect setup with DAC-specific rules and headphone correction via AutoEQ',
  },
]

export default function HomePage() {
  return (
    <>
      <Header />
      <main className="min-h-screen pt-[72px]">
        {/* Hero Section */}
        <section className="container py-16 md:py-24">
          <div className="text-center max-w-4xl mx-auto">
            {/* Title */}
            <h1 className="text-4xl md:text-6xl font-bold mb-6">
              <span className="gradient-text">.files</span>
              <span className="text-[var(--text-muted)]"> + </span>
              <span className="text-[var(--text-primary)]">UX</span>
            </h1>

            {/* Tagline */}
            <p className="text-lg md:text-xl text-[var(--text-muted)] mb-4">
              Meticulously Organized Linux Dotfiles & Visual Assets
            </p>

            {/* Subtitle Stats */}
            <p className="font-mono text-sm text-[var(--text-dim)] mb-8">
              72+ configs • 160+ wallpapers • 80+ icons • 10 themes
            </p>

            {/* Terminal Block */}
            <div className="max-w-2xl mx-auto mb-8">
              <TerminalBlock
                title="Quick Install"
                lines={[
                  { text: '$ git clone https://github.com/kvn/.files.git', type: 'command' },
                  { text: '$ cd .files && ./install.sh', type: 'command' },
                  { text: '✓ Installing configurations...', type: 'success' },
                ]}
              />
            </div>

            {/* CTA Buttons */}
            <div className="flex flex-wrap justify-center gap-4">
              <Button href="https://github.com/kvn/.files" variant="primary">
                View on GitHub
              </Button>
              <Button href="/themes" variant="secondary">
                Browse Themes
              </Button>
            </div>
          </div>
        </section>

        {/* Stats Bar */}
        <section className="container py-8">
          <div className="flex flex-wrap justify-center gap-4 md:gap-8">
            {stats.map((stat) => (
              <Link
                key={stat.label}
                href={stat.label === 'Configs' ? '#categories' : stat.label === 'Wallpapers' ? '/wallpapers' : stat.label === 'Icons' ? '/icons' : stat.label === 'Themes' ? '/themes' : '#'}
                className="group"
              >
                <CountBadge
                  count={stat.count}
                  label={stat.label}
                  className="group-hover:border-[var(--accent-blue)] transition-colors"
                />
              </Link>
            ))}
          </div>
        </section>

        {/* Feature Highlights */}
        <section className="container py-16">
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-12">
            Why This Setup?
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {featuresHighlights.map((feature) => (
              <GlassCard key={feature.title} hover={false}>
                <feature.icon
                  size={40}
                  className="text-[var(--accent-blue)] mb-4"
                />
                <h3 className="font-mono text-lg font-semibold text-[var(--text-primary)] mb-2">
                  {feature.title}
                </h3>
                <p className="font-mono text-sm text-[var(--text-muted)]">
                  {feature.description}
                </p>
              </GlassCard>
            ))}
          </div>
        </section>

        {/* Categories Grid */}
        <section id="categories" className="container py-16">
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-4">
            Browse Configurations
          </h2>
          <p className="text-center text-[var(--text-muted)] mb-12 max-w-2xl mx-auto">
            Explore organized configuration categories. Each section includes installation commands, feature lists, and detailed documentation.
          </p>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {categories.map((category) => (
              <Link key={category.title} href={category.href}>
                <GlassCard className={category.featured ? 'border-[var(--accent-blue)]/30' : ''}>
                  <div className="flex items-start justify-between mb-4">
                    <category.icon
                      size={32}
                      className={category.featured ? 'text-[var(--accent-purple)]' : 'text-[var(--accent-blue)]'}
                    />
                    <div className="flex gap-1">
                      {category.os.map((os) => (
                        <span
                          key={os}
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                            os === 'linux'
                              ? 'bg-[#D29922]/20 text-[#D29922]'
                              : os === 'macos'
                              ? 'bg-[#8B949E]/20 text-[#8B949E]'
                              : 'bg-[#3FB950]/20 text-[#3FB950]'
                          }`}
                        >
                          {os}
                        </span>
                      ))}
                    </div>
                  </div>
                  <h3 className="font-mono text-base font-semibold text-[var(--text-secondary)] mb-2">
                    {category.title}
                  </h3>
                  <p className="font-mono text-xs text-[var(--text-muted)] mb-4">
                    {category.description}
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-[var(--accent-blue)]">
                      {category.count} files →
                    </span>
                    {category.featured && (
                      <Sparkles size={14} className="text-[var(--accent-purple)]" />
                    )}
                  </div>
                </GlassCard>
              </Link>
            ))}
          </div>
        </section>

        {/* Quick Start Section */}
        <section className="container py-16">
          <div className="max-w-3xl mx-auto">
            <h2 className="text-2xl md:text-3xl font-bold text-center mb-4">
              Quick Start
            </h2>
            <p className="text-center text-[var(--text-muted)] mb-8">
              Get up and running in minutes with the automated installer
            </p>

            <TerminalBlock
              title="install.sh"
              lines={[
                { text: '# Clone the repository', type: 'output' },
                { text: '$ git clone https://github.com/kvn/.files.git ~/.files', type: 'command' },
                { text: '', type: 'output' },
                { text: '# Run the installer', type: 'output' },
                { text: '$ cd ~/.files && ./install.sh', type: 'command' },
                { text: '', type: 'output' },
                { text: '# Or install specific modules', type: 'output' },
                { text: '$ stow -t ~ zsh polybar i3', type: 'command' },
                { text: '', type: 'output' },
                { text: '✓ Configurations installed successfully!', type: 'success' },
              ]}
            />

            <div className="text-center mt-8">
              <Button
                href="https://github.com/kvn/.files#installation"
                variant="secondary"
              >
                View Full Documentation
              </Button>
            </div>
          </div>
        </section>

        {/* Visual Assets Preview */}
        <section className="container py-16">
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-4">
            Visual Assets
          </h2>
          <p className="text-center text-[var(--text-muted)] mb-12">
            Curated wallpapers and custom icons to complete your setup
          </p>

          <div className="grid md:grid-cols-2 gap-8">
            {/* Wallpapers Preview */}
            <Link href="/wallpapers">
              <GlassCard className="h-full">
                <div className="flex items-center gap-3 mb-4">
                  <Image size={24} className="text-[var(--accent-blue)]" />
                  <h3 className="font-mono text-lg font-semibold text-[var(--text-secondary)]">
                    160+ Wallpapers
                  </h3>
                </div>
                <p className="font-mono text-sm text-[var(--text-muted)] mb-4">
                  Curated collection spanning 5 resolutions from 2K to 8K. Categories include space, nature, abstract, gaming, and urban themes.
                </p>
                <div className="flex flex-wrap gap-2">
                  {['2560×1440', '3440×1440', '3840×2160', '7680×4320'].map((res) => (
                    <span
                      key={res}
                      className="px-2 py-1 bg-[var(--bg-tertiary)] rounded text-[10px] font-mono text-[var(--text-muted)]"
                    >
                      {res}
                    </span>
                  ))}
                </div>
              </GlassCard>
            </Link>

            {/* Icons Preview */}
            <Link href="/icons">
              <GlassCard className="h-full">
                <div className="flex items-center gap-3 mb-4">
                  <Sparkles size={24} className="text-[var(--accent-purple)]" />
                  <h3 className="font-mono text-lg font-semibold text-[var(--text-secondary)]">
                    80+ Custom Icons
                  </h3>
                </div>
                <p className="font-mono text-sm text-[var(--text-muted)] mb-4">
                  Custom macOS application icons with consistent design language. Categories span system, productivity, media, and tools.
                </p>
                <div className="flex flex-wrap gap-2">
                  {['System', 'Productivity', 'Media', 'Tools'].map((cat) => (
                    <span
                      key={cat}
                      className="px-2 py-1 bg-[var(--bg-tertiary)] rounded text-[10px] font-mono text-[var(--text-muted)]"
                    >
                      {cat}
                    </span>
                  ))}
                </div>
              </GlassCard>
            </Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
