# `.files` Immersive Showcase Redesign

**Status:** Approved design
**Date:** 2026-07-28
**Deployment repository:** `kvnloo/.files`
**Development branch:** `dev`
**GitHub Pages branch:** `master`

## 1. Purpose

Transform the existing `.files` showcase into an immersive, elegant, technically credible engineering portfolio while preserving the information already presented by the site.

The website must answer, in order:

1. Why is this desktop distinctive?
2. How do its systems work together?
3. What engineering decisions make it reliable and reproducible?
4. How can a visitor inspect or reuse the parts they care about?
5. Where is the source, and how can a visitor engage with its author?

The cinematic experience earns attention. Search and technical inspection prove depth. Source and references establish credibility. GitHub is the primary conversion.

## 2. Governing Content Contract

The existing showcase content is canonical. The redesign changes presentation, navigation, and interaction—not the underlying story.

Required:

- Preserve current facts, assets, categories, and technical explanations.
- Preserve or intentionally redirect all existing public routes.
- Recompose existing content into a continuous cinematic narrative.
- Redesign `/themes`, `/wallpapers`, `/icons`, and `/audio` rather than replacing their content.
- Keep setup instructions in the repository and link them contextually.
- Add implementation detail only where it clarifies an existing showcase claim.
- Keep search, the explorer, Vim navigation, and terminal mode optional supporting layers.

Prohibited:

- Invented case studies, performance claims, or testimonials.
- A permanent fake IDE shell around the portfolio.
- A documentation portal created merely to justify a docs framework.
- An unrestricted fake Linux shell.
- Replacing current information with generic marketing copy.

## 3. Technical Direction

Use the existing React implementation and static deployment architecture:

- Next.js static export
- React and TypeScript
- Tailwind CSS plus semantic custom properties
- Motion for React for stateful, layout, gesture, and scroll-linked animation
- CSS transitions and Web Animations for simple micro-interactions
- Three.js through a framework-neutral thin-player core
- Pagefind for post-build static full-text search
- xterm.js for the lazy-loaded terminal demonstration
- Shiki for build-time source and diff rendering
- Typed TypeScript registries for content, references, scenes, and actions
- Optional MDX only when a genuine long-form guide warrants it

Do not adopt VitePress, Nextra, Fumadocs, Astro, a CMS, a database, or a runtime server for the initial redesign. Their convenience does not justify duplicating or replacing the current application shell.

### Rendering boundaries

- Narrative content must render to static HTML.
- Client components must be limited to interactive boundaries.
- Three.js, xterm.js, Pagefind UI, and terminal scenario data must remain outside the homepage critical path until invoked.
- The experience must remain navigable when JavaScript is delayed.

## 4. Information Architecture

Primary routes:

- `/` — cinematic showcase journey
- `/themes` — live environmental scenes and palette systems
- `/wallpapers` — immersive wallpaper collection
- `/icons` — curated icon collection
- `/audio` — interactive audio signal-path showcase
- `/explore` — full configuration and architecture explorer
- `/terminal` — browser-native guided tmux demonstration
- `/references` — canonical upstream ecosystem map

The opening route uses a restrained navigation rail after the hero:

```text
.files   system / desktop / terminal / audio / setup   environment: ruins   GitHub
```

Existing routes not listed above must remain available or receive an intentional redirect with no content loss.

## 5. Cinematic Journey

### 5.1 Cold open

- Full-bleed active environment.
- Minimal `.files` identity.
- One concise engineering claim.
- Primary action: “Explore the system.”
- Secondary signals: Hyprland, Noctalia, tmux, PipeWire, agent tooling.
- No gallery grid competing with the opening.

### 5.2 Desktop composition

Present the three-monitor topology as the organizing visual:

- DP-1 — Forgotten Ruins, performance-focused primary display.
- DP-2 — Abstract Landscape, vertical information surface.
- HDMI-A-1 — Hollow Knight, secondary media surface.

Visitors can change environment here; scene and semantic palette transition together.

### 5.3 Control plane

Animate the relationship among Hyprland, Noctalia/Waybar, services, and scripts. Preserve current explanations and add source inspection only on request.

### 5.4 Terminal craft

Present current tmux layouts, fleet dashboard, status widgets, Vim conventions, and terminal workflows. Offer the optional `/terminal` demonstration.

### 5.5 Audio engineering

Recompose current PipeWire and DSP information into an interactive signal path. Preserve AutoEQ, crossfeed, BRIR, movie fold-down, rate handling, and configuration references.

### 5.6 Reproducible setup

Show the interactive terminal and AI-harness onboarding paths. Link to existing repository instructions rather than duplicating a documentation portal.

### 5.7 Open-source close

Restore the full selected environment, summarize the explored system, and present GitHub as the primary action. Clone/install remains visible but secondary.

## 6. Visual System

### 6.1 Visual thesis

The desktop becomes an editorial product:

- atmospheric full-bleed environment;
- precise typography;
- restrained translucent surfaces;
- terminal and system-detail motifs;
- motion that explains state and relationships;
- no generic dashboard grid;
- no indiscriminate glass treatment.

Glass is reserved for floating controls, explorer overlays, and terminal surfaces. Dense technical content uses opaque or near-opaque surfaces.

### 6.2 Environmental themes

Three complete semantic environments:

1. **Ruins** — Forgotten Ruins; moss, mineral teal, parchment, muted gold. Default.
2. **Signal** — Abstract Landscape; cyan, electric mint, violet, deep navy.
3. **Crystal** — Hollow Knight / Crystal Peak; blue-green crystal, indigo, pale cyan.

Each environment defines:

```text
canvas
surface
surface-raised
glass-tint
text-primary
text-secondary
border
accent-primary
accent-secondary
success
warning
danger
code-keyword
code-string
code-comment
selection
focus-ring
shadow-color
```

Components consume semantic tokens only. Environment selection persists locally across routes.

### 6.3 Environment transition

1. Freeze the outgoing renderer.
2. Load the incoming scene’s minimum assets.
3. Crossfade poster and renderer layers.
4. Interpolate semantic CSS colors.
5. Update the browser theme color.
6. Resume the incoming renderer.
7. Persist selection.

The chooser shows scene name, palette, motion status, renderer mode, source, attribution, and reduced-motion alternative.

## 7. WebGL Scene System

Recreate the three selected scenes with permissioned assets and explicit attribution:

- **Ruins:** depth layers, water ripple distortion, mask-driven vegetation, particles, restrained parallax.
- **Signal:** procedural terrain/gradient field, glow, color shift, particles, pointer perspective.
- **Crystal:** layered planes, fog, crystal bloom, subtle articulated motion, volumetric depth.

All scenes share one runtime:

```text
manifest → asset loader → layer/effect graph → adaptive renderer → interaction policy → diagnostics
```

Required runtime policy:

- Static poster paints first.
- Renderer loads after initial content paint.
- Device-pixel ratio is capped.
- Quality degrades under sustained frame pressure.
- Hidden and off-screen canvases pause.
- Save-Data and reduced-motion preferences receive complete static behavior.
- Only selected-scene assets load.
- Failure retains the current palette and static fallback.

## 8. Motion Grammar

- Hover/focus: 120–180 ms.
- Button/pill response: small spring displacement; avoid large scaling.
- Drawer/panel: 280–420 ms.
- Chapter reveal: 450–700 ms controlled stagger.
- Environment transition: 700–1100 ms crossfade and palette interpolation.
- Scroll-linked motion: transforms and opacity only on the hot path.

Rules:

- No scroll hijacking.
- No custom cursor requirement.
- No animated layout measurement loops.
- Pause effects outside the viewport.
- Reduced motion uses immediate states and short fades.
- Pointer, touch, and keyboard receive equivalent feedback.

## 9. Global Search and Commands

Pagefind indexes rendered static pages after `next build`. The search bundle loads only when invoked.

Entry points:

- `/` — content search.
- `:` — actions and navigation.

Result groups:

- Pages
- Systems
- Configuration
- References
- Terminal scenarios
- Actions

The local action registry supports environment changes, terminal launch, clone command copy, route navigation, and Vim-mode preference. Search supports fuzzy matching, matched-term emphasis, pointer and keyboard parity, deep links, `j/k` and arrow selection, `Enter`, and `Esc`.

## 10. Configuration Explorer

The explorer starts with concepts, not raw repository topology:

- Desktop: Hyprland, Noctalia, displays, input, idle/lock.
- Terminal: tmux, shell, Neovim, agent fleet, terminal emulator.
- Audio: PipeWire, EasyEffects, AutoEQ, routing profiles.
- Automation: onboarding, services, performance modes, wallpaper control.

An entry may display:

1. what it accomplishes;
2. why it is designed this way;
3. relationships to current showcased systems;
4. a relevant source excerpt;
5. implementing paths and symbols;
6. official upstream references;
7. source and copy actions.

On the homepage this is a focused drawer. `/explore` expands it into a two-pane workspace with filtering, relationships, and shareable URLs. It remains secondary to the immersive showcase.

## 11. Optional Vim Navigation

Vim navigation is opt-in and persisted locally. It is available from the command palette, shortcut help, and preferences.

Outside editable controls:

- `j` / `k` — next/previous chapter or result.
- `h` / `l` — collapse/expand or move explorer pane.
- `g g` — beginning.
- `G` — end.
- `/` — search.
- `:` — commands.
- `t` — environment chooser.
- `Enter` — open/select.
- `Esc` — close/back.
- `?` — shortcut help.

Arrow keys and standard browser behavior always remain available. A temporary mode indicator may show current context and position. The main site does not emulate Vim insert/normal modes.

## 12. Browser Terminal Mode

`/terminal` lazy-loads xterm.js and a deterministic local state machine. It is explicitly described as a guided browser model, not a remote shell.

Guided scenarios:

1. navigate the tmux workspace;
2. open the agent fleet dashboard;
3. launch and switch harness sessions;
4. inspect a Hyprland configuration in Neovim;
5. change wallpaper and palette modes;
6. trace the audio processing path.

Sandbox vocabulary:

```text
help ls cat cd tmux nvim theme fleet clear exit
```

Unsupported input explains the boundary and suggests `help`. State is local and resettable. Scenario URLs are shareable. Mobile uses a scenario-first transcript/control surface rather than a cramped desktop terminal.

## 13. Thin-player Repository Boundary

Create a standalone public repository with a small framework-neutral TypeScript package and demonstration:

```text
thin-player
├── src/core/
├── src/three/
├── src/react/
├── scenes/
├── demo/
└── references/
```

Small public API:

```ts
const player = createPlayer(container, options)
await player.load(sceneManifest)
player.play()
player.pause()
player.resize()
player.setQuality('auto')
player.destroy()
```

A versioned scene manifest defines dimensions, focal point, assets, layers, blend modes, effects, interactions, quality tiers, fallback, and attribution.

The package must not contain portfolio navigation, `.files` content, or site-specific theme policy. The React adapter maps component lifecycle onto the core. The portfolio consumes the package rather than a duplicated internal renderer.

## 14. Canonical References

One typed registry covers:

- operating systems;
- desktop and display;
- shell and terminal;
- editors;
- audio and media;
- networking and remote access;
- automation and services;
- agent tooling;
- web platform and libraries;
- protocols and specifications;
- creative sources and attribution.

Entry shape:

```ts
{
  id,
  name,
  category,
  description,
  officialDocs,
  sourceRepository,
  projectPage,
  kind,
  usedBy
}
```

Only applicable URLs are required. `/references`, contextual links, search, explorer metadata, attribution, and repository documentation consume the same registry.

Coverage checks detect unknown IDs, duplicate/malformed URLs, missing scene attribution, named packages lacking entries, and stale internal source paths. External availability checks are separate from the normal build.

## 15. Failure and Accessibility Behavior

- WebGL unavailable: responsive poster and full content.
- Slow GPU: automatic quality reduction.
- Reduced motion: immediate chapter states and short fades.
- Save-Data: posters until explicit enablement.
- Search unavailable: normal navigation and visible filters.
- JavaScript delayed: static narrative and links.
- Small terminal viewport: guided transcript and visible controls.
- Asset failure: current palette and previous scene remain stable.

Keyboard focus must remain visible. Dialog focus must be trapped and restored. Semantic headings, landmarks, descriptions, and alt text must exist independently of animation.

## 16. Performance Budgets

Target observable budgets:

- LCP below 2.5 seconds at mobile p75.
- INP below 200 ms.
- CLS below 0.1.
- Three.js and xterm.js excluded from the initial critical path.
- Stable 60 fps desktop animation with adaptive degradation.
- Complete reduced-motion and WebGL-failure paths.

Do not claim these targets as achieved until measured against a deployed or production-equivalent build.

## 17. Deployment and Delivery

- Work in scoped commits on `dev`.
- Preserve unrelated working-tree changes and secrets.
- Build and browser-smoke-test each integrated phase.
- Push `dev` and open a pull request to `master`.
- Review and merge only after the full static export and interaction verification pass.
- Verify the public GitHub Pages deployment after merge.
- Confirm that all three public scenes render on the live site.

The local development server may use port 3001 because Docker container `frontend__open-wearables` currently publishes port 3000.

## 18. Acceptance Criteria

The redesign is complete only when:

1. Existing showcase information is preserved and visibly re-presented.
2. Existing public routes remain or redirect intentionally.
3. The cinematic route works with pointer, touch, keyboard, and reduced motion.
4. Three environment choices update scene and full semantic palette.
5. WebGL, static-poster fallback, persistence, and adaptive policy work in a real browser.
6. Pagefind indexes intended static content and integrates with the command surface.
7. Vim navigation is optional, discoverable, and non-interfering in editable controls.
8. Terminal scenarios are honest, deterministic, resettable, and source-linked.
9. The thin-player core is consumed from its standalone repository/package boundary.
10. `/references` and contextual links use one canonical registry.
11. Reference, attribution, and internal-path coverage checks pass.
12. Static export succeeds.
13. Performance and accessibility checks produce recorded evidence.
14. The deployment pull request is merged to `master`.
15. The public GitHub Pages site is visually verified after deployment.
