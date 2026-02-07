# Dotfiles Showcase - Design System Patterns

This document defines the standardized design patterns for the dotfiles showcase website. Use this as the source of truth for consistent visual design across all pages.

---

## Table of Contents

1. [Color Palette](#color-palette)
2. [Typography](#typography)
3. [Spacing](#spacing)
4. [Components](#components)
5. [Navigation](#navigation)
6. [Responsive Behavior](#responsive-behavior)
7. [Animation Guidelines](#animation-guidelines)

---

## Color Palette

### Background Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0D1117` | Main page background |
| `--bg-secondary` | `#161B22` | Secondary surfaces, cards |
| `--bg-elevated` | `#1C2128` | Elevated elements, modals |

```css
:root {
  --bg-primary: #0D1117;
  --bg-secondary: #161B22;
  --bg-elevated: #1C2128;
}
```

### Text Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--text-primary` | `#E6EDF3` | Main text, headings |
| `--text-secondary` | `#8B949E` | Secondary text, descriptions |
| `--text-muted` | `#6E7681` | Disabled text, hints |

```css
:root {
  --text-primary: #E6EDF3;
  --text-secondary: #8B949E;
  --text-muted: #6E7681;
}
```

### Accent Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--accent-blue` | `#58A6FF` | Links, primary actions, active states |
| `--accent-purple` | `#A371F7` | Decorative, gradients |
| `--accent-green` | `#3FB950` | Success states, status indicators |
| `--accent-amber` | `#F59E0B` | Warnings, caution indicators |
| `--accent-red` | `#F85149` | Errors, destructive actions |

```css
:root {
  --accent-blue: #58A6FF;
  --accent-purple: #A371F7;
  --accent-green: #3FB950;
  --accent-amber: #F59E0B;
  --accent-red: #F85149;
}
```

### Border Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--border-default` | `#21262D` | Standard borders |
| `--border-muted` | `#30363D` | Subtle borders, dividers |

```css
:root {
  --border-default: #21262D;
  --border-muted: #30363D;
}
```

### Glass Effect Fills

| Token | Value | Usage |
|-------|-------|-------|
| `--glass-light` | `rgba(255, 255, 255, 0.05)` | Glass card backgrounds |
| `--glass-dark` | `rgba(13, 17, 23, 0.8)` | Overlay backgrounds |
| `--glass-hover` | `rgba(255, 255, 255, 0.08)` | Hover state for glass elements |

```css
:root {
  --glass-light: rgba(255, 255, 255, 0.05);
  --glass-dark: rgba(13, 17, 23, 0.8);
  --glass-hover: rgba(255, 255, 255, 0.08);
}
```

### Gradient Definitions

```css
/* Hero title gradient */
.gradient-title {
  background: linear-gradient(135deg, #E6EDF3 0%, #58A6FF 50%, #A371F7 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Page background gradient */
.gradient-bg {
  background: linear-gradient(180deg, #0D1117 0%, #161B22 100%);
}

/* Accent glow */
.glow-blue {
  box-shadow: 0 0 20px rgba(88, 166, 255, 0.3);
}

.glow-purple {
  box-shadow: 0 0 20px rgba(163, 113, 247, 0.3);
}
```

---

## Typography

### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `--font-heading` | `'JetBrains Mono', monospace` | All headings, code, terminal |
| `--font-body` | `'Inter', sans-serif` | Body text, descriptions |

```css
:root {
  --font-heading: 'JetBrains Mono', monospace;
  --font-body: 'Inter', sans-serif;
}
```

### Font Import

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

### Font Sizes

| Token | Size | Line Height | Usage |
|-------|------|-------------|-------|
| `--text-hero` | `72px` | `1.1` | Hero section main title |
| `--text-page-title` | `48px` | `1.2` | Page titles |
| `--text-large` | `36px` | `1.2` | Section headings |
| `--text-stats` | `24px` | `1.2` | Statistics, numbers |
| `--text-body-lg` | `18px` | `1.6` | Large body text |
| `--text-body` | `16px` | `1.6` | Standard body text |
| `--text-nav` | `14px` | `1.5` | Navigation, small text |
| `--text-caption` | `12px` | `1.5` | Captions, labels |

```css
:root {
  --text-hero: 72px;
  --text-page-title: 48px;
  --text-large: 36px;
  --text-stats: 24px;
  --text-body-lg: 18px;
  --text-body: 16px;
  --text-nav: 14px;
  --text-caption: 12px;
}
```

### Font Weights

| Token | Value | Usage |
|-------|-------|-------|
| `--font-bold` | `700` | Headlines, emphasis |
| `--font-semibold` | `600` | Subheadings, active nav |
| `--font-medium` | `500` | Buttons, labels |
| `--font-normal` | `400` | Body text |

```css
:root {
  --font-bold: 700;
  --font-semibold: 600;
  --font-medium: 500;
  --font-normal: 400;
}
```

### Typography Examples

```html
<!-- Hero Title -->
<h1 style="
  font-family: var(--font-heading);
  font-size: var(--text-hero);
  font-weight: var(--font-bold);
  line-height: 1.1;
  color: var(--text-primary);
">.files</h1>

<!-- Page Title -->
<h2 style="
  font-family: var(--font-heading);
  font-size: var(--text-page-title);
  font-weight: var(--font-bold);
  line-height: 1.2;
  color: var(--text-primary);
">Theme Gallery</h2>

<!-- Section Heading -->
<h3 style="
  font-family: var(--font-heading);
  font-size: var(--text-large);
  font-weight: var(--font-semibold);
  line-height: 1.2;
  color: var(--text-primary);
">Feature Highlights</h3>

<!-- Body Text -->
<p style="
  font-family: var(--font-body);
  font-size: var(--text-body);
  font-weight: var(--font-normal);
  line-height: 1.6;
  color: var(--text-secondary);
">Meticulously organized Linux dotfiles and visual assets.</p>
```

---

## Spacing

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` | Minimal spacing |
| `--space-sm` | `8px` | Tight spacing |
| `--space-md` | `16px` | Standard spacing |
| `--space-lg` | `24px` | Loose spacing |
| `--space-xl` | `32px` | Section gaps |
| `--space-2xl` | `48px` | Large section padding |
| `--space-3xl` | `64px` | Page section vertical padding |
| `--space-4xl` | `120px` | Horizontal page margins |

```css
:root {
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;
  --space-4xl: 120px;
}
```

### Gap Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--gap-tight` | `8px` | Compact element groups |
| `--gap-normal` | `16px` | Standard element groups |
| `--gap-loose` | `24px` | Relaxed element groups |
| `--gap-section` | `32px` | Between major sections |

```css
:root {
  --gap-tight: 8px;
  --gap-normal: 16px;
  --gap-loose: 24px;
  --gap-section: 32px;
}
```

### Layout Spacing

```css
/* Section container */
.section {
  padding: var(--space-3xl) var(--space-4xl);  /* 64px 120px */
}

/* Card padding */
.card {
  padding: var(--space-lg);  /* 24px */
}

/* Header */
.header {
  height: 72px;
  padding: 0 var(--space-2xl);  /* 0 48px */
}

/* Footer */
.footer {
  padding: var(--space-2xl) var(--space-4xl);  /* 48px 120px */
}
```

---

## Components

### Header

The header is a sticky, glassmorphic navigation bar.

```html
<header class="header">
  <div class="header-logo">
    <span class="logo-text">.files</span>
  </div>
  <nav class="header-nav">
    <a href="/" class="nav-item">Home</a>
    <a href="/themes" class="nav-item">Themes</a>
    <a href="/audio" class="nav-item">Audio</a>
    <a href="/wallpapers" class="nav-item">Wallpapers</a>
    <a href="/icons" class="nav-item">Icons</a>
  </nav>
  <a href="https://github.com/..." class="github-button">
    <svg><!-- GitHub icon --></svg>
    GitHub
  </a>
</header>
```

```css
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 72px;
  padding: 0 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--glass-dark);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-default);
}

.logo-text {
  font-family: var(--font-heading);
  font-size: var(--text-stats);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.nav-item {
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-normal);
  color: var(--text-secondary);
  text-decoration: none;
  transition: color 0.2s ease;
}

.nav-item:hover,
.nav-item.active {
  color: var(--text-primary);
  font-weight: var(--font-semibold);
}

.github-button {
  display: flex;
  align-items: center;
  gap: var(--gap-tight);
  padding: 8px 16px;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  background: var(--glass-light);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  text-decoration: none;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.github-button:hover {
  background: var(--glass-hover);
  border-color: var(--border-muted);
}
```

### Buttons

#### Primary Button

```html
<button class="btn btn-primary">Explore Themes</button>
```

```css
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-tight);
  padding: 12px 24px;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-medium);
  color: #0D1117;
  background: var(--accent-blue);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.1s ease;
}

.btn-primary:hover {
  background: #79B8FF;
}

.btn-primary:active {
  transform: scale(0.98);
}
```

#### Secondary Button

```html
<button class="btn btn-secondary">View Gallery</button>
```

```css
.btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-tight);
  padding: 12px 24px;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  background: transparent;
  border: 1px solid var(--border-muted);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.btn-secondary:hover {
  background: var(--glass-light);
  border-color: var(--text-secondary);
}
```

#### Ghost Button

```html
<button class="btn btn-ghost">Learn More</button>
```

```css
.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-tight);
  padding: 8px 16px;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-medium);
  color: var(--accent-blue);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 0.2s ease;
}

.btn-ghost:hover {
  color: #79B8FF;
  text-decoration: underline;
}
```

### Cards

#### Feature Card

Used for highlighting key features on the landing page.

```html
<div class="card card-feature">
  <div class="card-icon">
    <svg><!-- Icon --></svg>
  </div>
  <h3 class="card-title">Modular Structure</h3>
  <p class="card-description">Clean hierarchy with symlink management for easy configuration.</p>
  <a href="#" class="card-link">Learn More</a>
</div>
```

```css
.card-feature {
  padding: var(--space-lg);
  background: var(--glass-light);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.card-feature:hover {
  transform: translateY(-4px);
  border-color: var(--accent-blue);
}

.card-icon {
  width: 48px;
  height: 48px;
  margin-bottom: var(--space-md);
  color: var(--accent-blue);
}

.card-title {
  font-family: var(--font-heading);
  font-size: var(--text-body-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-sm);
}

.card-description {
  font-family: var(--font-body);
  font-size: var(--text-nav);
  font-weight: var(--font-normal);
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: var(--space-md);
}

.card-link {
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-medium);
  color: var(--accent-blue);
  text-decoration: none;
}

.card-link:hover {
  text-decoration: underline;
}
```

#### Preview Card

Used for theme, wallpaper, and icon galleries.

```html
<div class="card card-preview">
  <div class="card-image">
    <img src="preview.jpg" alt="Theme preview">
  </div>
  <div class="card-content">
    <h4 class="card-name">Blocks Theme</h4>
    <span class="card-meta">Minimal</span>
  </div>
  <button class="btn btn-secondary">Apply Theme</button>
</div>
```

```css
.card-preview {
  background: var(--glass-light);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card-preview:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.card-image {
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--bg-secondary);
  overflow: hidden;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-content {
  padding: var(--space-md);
}

.card-name {
  font-family: var(--font-heading);
  font-size: var(--text-body);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}

.card-meta {
  font-family: var(--font-body);
  font-size: var(--text-caption);
  color: var(--text-muted);
}
```

#### Icon Card

Compact card for icon grids.

```html
<div class="card card-icon">
  <div class="icon-preview">
    <img src="icon.png" alt="App Store">
  </div>
  <span class="icon-name">App Store</span>
</div>
```

```css
.card-icon {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-md);
  background: var(--glass-light);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: background 0.2s ease;
}

.card-icon:hover {
  background: var(--glass-hover);
}

.icon-preview {
  width: 64px;
  height: 64px;
  margin-bottom: var(--space-sm);
}

.icon-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.icon-name {
  font-family: var(--font-heading);
  font-size: var(--text-caption);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  text-align: center;
}
```

### Badges

#### Status Badge

```html
<span class="badge badge-success">Active</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-error">Error</span>
```

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  font-family: var(--font-heading);
  font-size: var(--text-caption);
  font-weight: var(--font-medium);
  border-radius: 4px;
}

.badge-success {
  color: var(--accent-green);
  background: rgba(63, 185, 80, 0.15);
}

.badge-warning {
  color: var(--accent-amber);
  background: rgba(245, 158, 11, 0.15);
}

.badge-error {
  color: var(--accent-red);
  background: rgba(248, 81, 73, 0.15);
}
```

#### Category Badge

```html
<span class="badge badge-category">Linux</span>
<span class="badge badge-category">macOS</span>
```

```css
.badge-category {
  color: var(--text-secondary);
  background: var(--glass-light);
  border: 1px solid var(--border-default);
}
```

#### Count Badge

```html
<span class="badge badge-count">72+</span>
```

```css
.badge-count {
  color: var(--accent-blue);
  background: rgba(88, 166, 255, 0.15);
}
```

### Terminal Block

```html
<div class="terminal">
  <div class="terminal-header">
    <div class="terminal-lights">
      <span class="light light-red"></span>
      <span class="light light-yellow"></span>
      <span class="light light-green"></span>
    </div>
    <span class="terminal-title">Terminal</span>
  </div>
  <div class="terminal-body">
    <div class="terminal-line">
      <span class="terminal-prompt">$</span>
      <span class="terminal-command">git clone https://github.com/user/.files.git</span>
      <button class="terminal-copy" title="Copy">
        <svg><!-- Copy icon --></svg>
      </button>
    </div>
  </div>
</div>
```

```css
.terminal {
  background: var(--glass-dark);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  gap: var(--gap-normal);
  padding: 12px 16px;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid var(--border-default);
}

.terminal-lights {
  display: flex;
  gap: 6px;
}

.light {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.light-red {
  background: #FF5F56;
}

.light-yellow {
  background: #FFBD2E;
}

.light-green {
  background: #27C93F;
}

.terminal-title {
  font-family: var(--font-heading);
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.terminal-body {
  padding: var(--space-md);
}

.terminal-line {
  display: flex;
  align-items: center;
  gap: var(--gap-tight);
}

.terminal-prompt {
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  color: var(--accent-green);
}

.terminal-command {
  flex: 1;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  color: var(--text-primary);
}

.terminal-copy {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s ease;
}

.terminal-copy:hover {
  color: var(--text-primary);
}
```

### Filter Buttons

```html
<div class="filter-group">
  <button class="filter-btn active">All</button>
  <button class="filter-btn">Minimal</button>
  <button class="filter-btn">Colorful</button>
  <button class="filter-btn">Modern</button>
</div>
```

```css
.filter-group {
  display: flex;
  gap: var(--gap-tight);
  flex-wrap: wrap;
}

.filter-btn {
  padding: 8px 16px;
  font-family: var(--font-heading);
  font-size: var(--text-nav);
  font-weight: var(--font-normal);
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.filter-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-muted);
}

.filter-btn.active {
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  background: var(--glass-light);
  border-color: var(--accent-blue);
}
```

### Tables

```html
<table class="table">
  <thead>
    <tr>
      <th>Component</th>
      <th>Value</th>
      <th>Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>DAC</td>
      <td>Topping DX5 (32-bit, 768kHz)</td>
      <td><span class="badge badge-success">Excellent</span></td>
    </tr>
  </tbody>
</table>
```

```css
.table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-body);
  font-size: var(--text-nav);
}

.table th,
.table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-default);
}

.table th {
  font-family: var(--font-heading);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  background: var(--glass-light);
}

.table td {
  color: var(--text-secondary);
}

.table tbody tr:hover {
  background: var(--glass-light);
}

.table tbody tr:last-child td {
  border-bottom: none;
}
```

### Glass Effects

Glass effects use backdrop-filter with varying blur radii based on component size.

| Size | Blur Radius | Usage |
|------|-------------|-------|
| Small | `8px` | Badges, small elements |
| Medium | `12px` | Cards, buttons |
| Large | `16px` | Feature cards, modals |
| Extra Large | `20px` | Header, hero sections |

```css
.glass-sm {
  background: var(--glass-light);
  backdrop-filter: blur(8px);
}

.glass-md {
  background: var(--glass-light);
  backdrop-filter: blur(12px);
}

.glass-lg {
  background: var(--glass-light);
  backdrop-filter: blur(16px);
}

.glass-xl {
  background: var(--glass-dark);
  backdrop-filter: blur(20px);
}
```

---

## Navigation

### Required Navigation Items

| Item | Path | Description |
|------|------|-------------|
| Home | `/` | Landing page |
| Themes | `/themes` | Polybar theme gallery |
| Audio | `/audio` | Audiophile setup documentation |
| Wallpapers | `/wallpapers` | Wallpaper collection |
| Icons | `/icons` | macOS icon replacements |
| GitHub | `https://github.com/...` | External link |

### Navigation States

```css
/* Default state */
.nav-item {
  color: var(--text-secondary);  /* #8B949E */
  font-weight: var(--font-normal);  /* 400 */
}

/* Hover state */
.nav-item:hover {
  color: var(--text-primary);  /* #E6EDF3 */
}

/* Active/Current page */
.nav-item.active {
  color: var(--text-primary);  /* #E6EDF3 */
  font-weight: var(--font-semibold);  /* 600 */
}
```

---

## Responsive Behavior

### Breakpoints

| Token | Value | Usage |
|-------|-------|-------|
| `--bp-sm` | `640px` | Mobile landscape |
| `--bp-md` | `768px` | Tablet |
| `--bp-lg` | `1024px` | Small desktop |
| `--bp-xl` | `1280px` | Desktop |
| `--bp-2xl` | `1536px` | Large desktop |

```css
@media (max-width: 1280px) {
  .section {
    padding: var(--space-2xl) var(--space-xl);  /* 48px 32px */
  }
}

@media (max-width: 768px) {
  .section {
    padding: var(--space-xl) var(--space-md);  /* 32px 16px */
  }

  .header {
    padding: 0 var(--space-md);
  }
}
```

### Grid Behavior

```css
/* Card grid - responsive columns */
.card-grid {
  display: grid;
  gap: var(--gap-loose);
  grid-template-columns: repeat(3, 1fr);
}

@media (max-width: 1024px) {
  .card-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}
```

---

## Animation Guidelines

### Timing Functions

```css
:root {
  --ease-default: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-bounce: cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
```

### Duration Scale

| Duration | Value | Usage |
|----------|-------|-------|
| Fast | `100ms` | Button press, micro-interactions |
| Normal | `200ms` | Hover states, color changes |
| Slow | `300ms` | Card transforms, modal transitions |
| Slower | `400ms` | Page transitions |

### Standard Transitions

```css
/* Hover transform */
.card:hover {
  transform: translateY(-4px);
  transition: transform 0.2s var(--ease-out);
}

/* Color change */
.link:hover {
  color: var(--text-primary);
  transition: color 0.2s var(--ease-default);
}

/* Scale on press */
.button:active {
  transform: scale(0.98);
  transition: transform 0.1s var(--ease-in);
}
```

---

## Complete CSS Variables Reference

```css
:root {
  /* Colors - Backgrounds */
  --bg-primary: #0D1117;
  --bg-secondary: #161B22;
  --bg-elevated: #1C2128;

  /* Colors - Text */
  --text-primary: #E6EDF3;
  --text-secondary: #8B949E;
  --text-muted: #6E7681;

  /* Colors - Accents */
  --accent-blue: #58A6FF;
  --accent-purple: #A371F7;
  --accent-green: #3FB950;
  --accent-amber: #F59E0B;
  --accent-red: #F85149;

  /* Colors - Borders */
  --border-default: #21262D;
  --border-muted: #30363D;

  /* Colors - Glass */
  --glass-light: rgba(255, 255, 255, 0.05);
  --glass-dark: rgba(13, 17, 23, 0.8);
  --glass-hover: rgba(255, 255, 255, 0.08);

  /* Typography - Fonts */
  --font-heading: 'JetBrains Mono', monospace;
  --font-body: 'Inter', sans-serif;

  /* Typography - Sizes */
  --text-hero: 72px;
  --text-page-title: 48px;
  --text-large: 36px;
  --text-stats: 24px;
  --text-body-lg: 18px;
  --text-body: 16px;
  --text-nav: 14px;
  --text-caption: 12px;

  /* Typography - Weights */
  --font-bold: 700;
  --font-semibold: 600;
  --font-medium: 500;
  --font-normal: 400;

  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;
  --space-4xl: 120px;

  /* Gaps */
  --gap-tight: 8px;
  --gap-normal: 16px;
  --gap-loose: 24px;
  --gap-section: 32px;

  /* Animation */
  --ease-default: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-bounce: cubic-bezier(0.68, -0.55, 0.265, 1.55);

  /* Breakpoints (for reference - use in media queries) */
  --bp-sm: 640px;
  --bp-md: 768px;
  --bp-lg: 1024px;
  --bp-xl: 1280px;
  --bp-2xl: 1536px;
}
```

---

## Usage Notes

1. **Consistency**: Always use CSS variables instead of hardcoded values.
2. **Glass effects**: Apply appropriate blur radius based on component size.
3. **Typography**: Use JetBrains Mono for headings and code, Inter for body text.
4. **Spacing**: Follow the spacing scale for consistent visual rhythm.
5. **Accessibility**: Ensure sufficient color contrast (WCAG AA minimum).
6. **Transitions**: Keep animations subtle and purposeful.

---

*Last updated: February 2026*
