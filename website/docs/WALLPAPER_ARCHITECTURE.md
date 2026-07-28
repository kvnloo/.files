# Near‑native Forgotten Ruins wallpaper for ALL site visitors

Research + architecture decision for `website/` (static GitHub Pages export).
Scope: reproduce Wallpaper Engine scene **Forgotten Ruins (2133182232)** in the
browser for every visitor, no Wallpaper Engine / Workshop install required.

---

## TL;DR verdict

**Ship a hybrid: a thin WebGL "Forgotten Ruins player" as the best path on capable
devices, with an adaptive video/poster ladder as the universal fallback. Do NOT use
WASM.**

Local inspection of `scene.pkg` proves this wallpaper is almost the ideal case for a
tiny custom renderer:

> **1 static 4K base plate → 11 fullscreen fragment passes that distort the previous
> pass's framebuffer by `sin()` or a scrolling normal map, gated by a grayscale mask →
> a few additive particle sprites (light shafts + snow).**

Every effect shader is ~15–30 lines of trivial GLSL with zero data dependencies that
would need WASM. The "engine" is literally *textured quad + N ping‑pong distortion
passes + cheap instanced sprites*. A ~300–500 LOC WebGL1 renderer + compressed textures
hits 60fps on phones. WASM buys nothing here.

---

## What the pkg actually contains (verified locally)

`scene.pkg` = 28 MB, `PKGV0007`, 33 files. Decoded header + extracted text assets:

| Group | Files | Notes |
|---|---|---|
| Base image | `materials/MAIN.tex` (17.8 MB) | 4K plate, `TEXV0005`, DXT/BC + mips, container 4096² for a 3840×2160 scene |
| Ripple normal | `materials/effects/waterripplenormal.tex` (256 KB) | tiled scrolling normal map |
| Masks | 11 × `waterwaves_mask_*` / `waterripple_mask_*` (`.tex`, 11 KB–182 KB) | grayscale, gate where each effect applies |
| Effect shaders | `waterripple.{vert,frag}`, `waterwaves.{vert,frag}` | the entire "engine" — see below |
| Particles | `light_shafts_1`, `snowperspective`, `snowflat` presets | additive sprites |
| Audio | 3 × mp3 (Celtic music, brook, birds) ~9 MB total | loops, user‑adjustable volume |

Scene globals (`scene.json`): **orthographic 3840×2160, bloom OFF, parallax OFF,
camera shake OFF, camera fade on**. This is a flat 2D composite — no 3D, no lighting
model, no bloom pass. That removes the hardest parts of a WE port.

### The two effect shaders (this is the whole renderer)

**Water waves** (`waterwaves.frag`) — 9 instances, each a directional sine ripple:

```glsl
float mask = texture(g_Texture1, v_TexCoord.zw).r;
vec2 tc = v_TexCoord.xy;
float pos = abs(dot(tc - 0.5, v_Direction));
float dist = g_Time*g_Speed + dot(tc, v_Direction)*(g_Scale + g_Perspective*pos);
vec2 offset = vec2(v_Direction.y, -v_Direction.x);
tc += sin(dist) * offset * (g_Strength*g_Strength + g_Perspective*pos) * mask;
gl_FragColor = texture(g_Texture0, tc);   // g_Texture0 = previous framebuffer
```

**Water ripple** (`waterripple.frag`) — 2 instances, scrolling dual normal map:

```glsl
float mask = texture(g_Texture1, v_TexCoord.zw).r;
vec3 n1 = texture(g_Texture2, v_TexCoordRipple.xy).xyz*2.-1.;
vec3 n2 = texture(g_Texture2, v_TexCoordRipple.zw).xyz*2.-1.;
vec3 n  = normalize(vec3(n1.xy+n2.xy, n1.z));
tc.xy  += n.xy * g_Strength*g_Strength * mask;
gl_FragColor = texture(g_Texture0, tc);
// SPECULAR combo is OFF in this scene → the #if block never compiles
```

Both read `g_Texture0` = the framebuffer of the previous pass. So the render loop is a
**ping‑pong chain**: draw base plate → pass 1 samples it into buffer A → pass 2 samples
A into buffer B → … → final pass to screen. Each pass carries per‑instance constants
already dumped from `scene.json` (direction, scale, speed, strength, mask id). No CPU
simulation, no state between frames beyond `g_Time`. Fully GPU, fully stateless.

Particles are standard emitters (rate, lifetime, size/velocity/color random, alphafade,
oscillate). 3 systems, ≤ ~360 + 16×2 sprites. Trivial as instanced quads or a baked
sprite sheet.

---

## Does "near native" favor a custom renderer or video?

"Near native" in a browser has two very different meanings:

- **Motion fidelity** — the water actually reacts every frame. Only a real‑time shader
  gives this. A video is a fixed loop; a sharp eye sees the seam and the lack of
  variation. Custom WebGL wins.
- **Frame cost / battery / universality** — the browser compositor decoding an
  AV1/H264 `<video>` on the hardware decoder is often *cheaper* than 13 fullscreen 4K
  texture passes, especially on low‑end mobile. Video wins on the weakest devices.

Because the effects here are so cheap (13 dependent texture reads per pixel, no math
beyond a `sin` and a normalize), the WebGL path is realistically 60fps even at 1080p on
mid mobile if we **render at device resolution, not 4K**, and cap DPR. So we can offer
the "reactive" version broadly and only drop to video on genuinely weak/again‑restricted
clients.

---

## Role of WASM: **skip it**

WASM helps when there is heavy CPU work: parsing large binaries at runtime, physics/FFT
sim, audio DSP, image transcoding. None applies:

- **Parsing** happens **offline** in the asset pipeline (Python already does it — see
  below). The browser only loads plain PNG/KTX2/JSON. Zero runtime parsing.
- **Simulation** is zero — every effect is a stateless GPU function of `g_Time`.
- **Texture decode** — use browser‑native formats (WebP/PNG) or KTX2 via the tiny
  `basis_transcoder` (that transcoder *is* WASM, but it's an optional ~200 KB dep only
  if we ship GPU‑compressed textures; PNG/WebP need nothing).

Adding an Emscripten GL emulation layer (option C: WASM port of
`linux-wallpaperengine`) would mean a multi‑MB binary, poor mobile behavior, a GL→WebGL
shim, and it still can't legally ship the assets. It violates every hard constraint
(thin, all‑devices). **Verdict: no WASM now.** Revisit only if a future scene needs
runtime `scene.pkg` parsing or real fluid sim — then WASM parses, GLSL still renders.

---

## Minimal WebGL engine scope (the "Forgotten Ruins player")

Target: **WebGL1** (universal; WebGL2/WebGPU optional fast paths later). One file,
~300–500 LOC, no framework.

**Offline (build step), produces a static `scene.gen.json` + textures:**

1. `unpack.py` reads `scene.pkg`, decodes `.tex` → PNG (base, ripple normal, 11 masks).
2. Emit `scene.gen.json`: ordered list of passes with `{type, mask, direction, scale,
   speed, strength, ratio, animationspeed, scrollspeed}` copied from `scene.json`
   `constantshadervalues`, plus particle emitter params.
3. Compress: base plate → **KTX2/Basis** (or 2048‑wide WebP for the no‑WASM tier);
   masks → single‑channel WebP or packed into a few RGBA atlases; normal map → WebP.

**Runtime passes (exact chain from `scene.json` object 13, in order):**

| # | Effect | Mask | Key constants |
|---|---|---|---|
| base | draw `MAIN` plate | — | — |
| 1 | waterripple id18 | waterripple_mask_ee0d… | scale 2.97, ripplestrength .06, scroll .21 |
| 2 | waterripple id50 | waterripple_mask_8433… | scale 2.36, strength .07, ratio 3.08 |
| 3–13 | waterwaves ×9 (+1 grass toggle) | waterwaves_mask_* | direction/scale/speed/strength per instance |
| overlay | particles: light shafts ×2, snow perspective, snow flat | additive sprites | rate/size/color from presets |

Ping‑pong 2 framebuffers; each pass = 1 fullscreen triangle. 13 passes + particle draw
= well within budget. Uniforms are constants → can even bake sequential same‑type passes
into a loop in one shader later (optimization, not required).

**Size budget (no‑WASM tier, 1440‑wide targets):**

| Asset | Format | Budget |
|---|---|---|
| Base plate | WebP q80, 2048×1152 | ~250–400 KB |
| Ripple normal | WebP, 256² tiled | ~30 KB |
| 11 masks | WebP, packed/downscaled to ≤1024 | ~120–200 KB total |
| Engine JS | minified+gzip | ~6–10 KB |
| **Total wallpaper** | | **~0.5–0.7 MB** |

Audio (optional, muted‑by‑default, click‑to‑enable) adds the 3 mp3s — lazy‑load only on
user opt‑in to protect LCP and autoplay policy.

---

## Adaptive strategy (progressive enhancement, ALL visitors)

Decide once at load, cheaply, then never block first paint:

```
1. Always render <img> poster first (current WallpaperBackground) → instant LCP.
2. Detect capability:
   - prefers-reduced-motion / Save-Data / deviceMemory<=4 / hardwareConcurrency<=4
     / no WebGL → STAY on poster (or fade in the existing webm on desktop).
   - Network Information downlink low → poster.
   - WebGL ok + not reduced-motion → lazy-load the player after 'load'/idle.
3. Player mounts behind the poster, renders at DPR-capped device res (cap ~1.5),
   crossfades in when first frame is ready. Pause via IntersectionObserver /
   visibilitychange to save battery.
```

Tiers:

| Tier | Trigger | What runs |
|---|---|---|
| **A – Reactive** | desktop / capable mobile, motion allowed, WebGL | thin WebGL player @ device res |
| **B – Baked motion** | capable but constrained, or WebGL fails | existing `forgotten-ruins.webm` (AV1/H264) loop |
| **C – Static** | reduced‑motion, Save‑Data, no‑JS, weak GPU | current WebP/JPG poster (already shipped) |

This reuses what's already in `public/media/` (poster + webm) as tiers B/C, so the
fallback is done today; the WebGL player is purely additive.

---

## Asset & legal pipeline (do NOT ship `scene.pkg`)

The base plate and masks are the workshop author's copyrighted art. **Do not commit raw
`scene.pkg` / `.tex` / extracted originals to the public repo.** Options, in order of
safety:

1. **Re‑authored / owned capture (recommended default).** You own a running copy via
   Wallpaper Engine; treat the rendered output as *your capture* only for private use.
   For the public site, **re‑author** the base plate (repaint/generate a "forgotten
   ruins"‑style scene you own, or commission/license one) and hand‑author masks. The
   engine is generic; the art is swappable. This makes the public repo fully clean.
2. **Licensed bake.** Get explicit permission from the author (contact links are in the
   project description) to redistribute a derived, downscaled bake. Keep a `LICENSE`/
   `CREDITS` note. Only then commit the derived WebP/KTX2.
3. **Keep assets out of git entirely.** `.gitignore` the generated textures; fetch them
   at deploy time from a private bucket you control, or keep the site on the poster/webm
   tiers publicly and enable the reactive tier only on a private/authenticated build.

Pipeline mechanics regardless of choice: `scripts/` gets an `unpack-wallpaper.py`
(offline, references the local Steam path, never vendored) that outputs
`scene.gen.json` + textures into a git‑ignored `public/media/fr/` unless the license
path (1/2) is cleared. The website build consumes whatever is present and silently
falls back to poster/webm if the reactive assets are absent — so the public repo builds
and deploys cleanly with or without them.

---

## 2–3 day spike plan with success metrics

**Day 1 — offline pipeline + single pass.**
- `unpack-wallpaper.py`: pkg → PNG for base + ripple normal + masks; emit
  `scene.gen.json` from `scene.json` constants. (Reuse the parser in this doc.)
- Minimal WebGL1 harness: fullscreen triangle, draw base plate, one `waterwaves` pass
  reading one mask. Verify distortion matches WE visually.
- ✅ Success: one wave pass animating at 60fps in a `<canvas>`, base plate correct.

**Day 2 — full pass chain + particles + adaptive mount.**
- Ping‑pong all 13 passes in scene order; wire per‑pass constants + ripple normal map.
- Add particles (start with baked sprite sheet for light shafts + snow; instancing later).
- Integrate into `WallpaperBackground.tsx` as additive tier A behind the poster;
  capability gate + crossfade + visibility pause.
- ✅ Success: full scene visually matches WE; crossfades over poster; pauses off‑screen.

**Day 3 — perf, compression, budget, fallback QA.**
- KTX2/Basis for base plate (WASM transcoder optional path) vs WebP no‑WASM path; pick.
- DPR cap tuning; measure on a real mid phone (throttled) and desktop.
- Verify tiers B/C fallbacks and reduced‑motion/Save‑Data.

**Success metrics (gates):**

| Metric | Target |
|---|---|
| FPS desktop @1440p, tier A | ≥ 60 sustained |
| FPS mid mobile @device res, tier A | ≥ 50, else auto‑drop to tier B |
| Wallpaper bundle (JS+textures, tier A, no‑WASM) | ≤ 0.7 MB gzip |
| Engine JS only | ≤ 10 KB gzip |
| LCP impact (poster paints first, player lazy) | no regression vs current poster |
| CLS | 0 (fixed backdrop) |
| Battery: pauses when tab hidden / off‑screen | yes |
| Public repo contains no raw Steam assets | enforced by `.gitignore` + review |

---

## Comparison of approaches

| Approach | Fidelity | Perf (mobile) | Universality | Build cost | Legal | Verdict |
|---|---|---|---|---|---|---|
| **A. Adaptive video/poster ladder** | Med‑High (fixed loop) | ★★★★ | ★★★★★ | Low (mostly done) | Same asset issue; baked | **Fallback tiers B/C — keep** |
| **B. Thin WebGL player** (this scene) | High (reactive) | ★★★★ (@device res) | ★★★★ (WebGL1 ~everywhere) | Medium (2–3 days) | Needs owned/licensed base art | **Primary tier A — build** |
| C. WASM port of linux‑wallpaperengine | High | ★ (heavy) | ★★ (poor mobile) | High | Worst (ships pipeline+assets) | **Reject** |
| D. WebGPU compute water | High | ★★★ (modern only) | ★★ (needs fallback) | High | same as B | Later, optional fast path |
| E. CSS/liquid‑glass over static | Low (not the scene) | ★★★★★ | ★★★★★ | Low | Fine | Not a wallpaper reproduction |

**Bottom line:** build the thin WebGL player (option B) as tier A, reuse the existing
webm + poster as tiers B/C, skip WASM, and gate the public repo on an owned/licensed
base plate. This delivers reactive near‑native motion on capable devices and graceful,
already‑working fallbacks everywhere else, for well under 1 MB.
