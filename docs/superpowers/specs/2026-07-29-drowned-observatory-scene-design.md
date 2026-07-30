# Drowned Observatory WebGL Scene

**Status:** Approved visual direction; pending written-spec review
**Date:** 2026-07-29
**Consumer:** `.files` website wallpaper system

## Purpose

Replace the private, Workshop-derived Forgotten Ruins scene package with an original, redistributable environment that preserves only the broad atmospheric appeal: tranquil water, ancient architecture, overgrowth, depth, and restrained motion.

The result must feel inspired by atmospheric fantasy ruins without reproducing Forgotten Ruins' composition, architecture, silhouettes, masks, textures, lighting arrangement, or other recognizable expression.

## Visual Identity

The environment is **Drowned Observatory**: a collapsed astronomical sanctuary overtaken by moss and shallow water.

- Primary structure: a circular stone observatory with a fractured bronze armillary mechanism.
- Focal point: a distant open oculus exposing a pale mineral sky.
- Water: a diagonal reflecting channel crossing the lower third rather than a centered river.
- Foreground: broken instrument plinths, reeds, and oxidized metal fragments.
- Midground: asymmetric terraces and partially submerged stairs.
- Background: tall eroded arches, hanging roots, fog, and an off-center tower silhouette.
- Palette: mineral teal, oxidized bronze, muted gold, deep forest shadow, and pale cyan haze.
- Lighting: diffuse overcast ambient light with localized warm reflections from exposed mineral lamps.

No element may trace or closely reproduce the source wallpaper's layout or identifiable forms.

## Asset Provenance Rules

Workshop-derived files may be inspected only to understand generic runtime roles such as “base image,” “water mask,” or “normal map.” They must not be used as image-generation inputs, traced, transformed, upscaled, recolored, segmented, or shipped.

Every shipped visual asset must be one of:

1. generated from an original text-only prompt describing Drowned Observatory;
2. authored procedurally in this project;
3. created manually for this project; or
4. sourced under an explicit license permitting web redistribution and derivative use.

Each asset records its origin, prompt or procedure, creator/tool, license, and required attribution in a machine-readable manifest. Assets with uncertain provenance are rejected.

## Asset Set

The scene package contains:

- one 4K master base plate and optimized responsive derivatives;
- separate foreground, midground, and background depth layers where available;
- an original water-region mask matching the diagonal channel;
- a procedural or independently generated ripple normal map;
- vegetation and hanging-root overlays with alpha;
- fog and mineral-light overlays;
- particle sprites or procedural particles;
- desktop and portrait focal-point metadata;
- a static poster that remains compositionally complete without WebGL;
- a scene manifest describing assets, effects, quality tiers, fallback, provenance, and attribution.

Lossless masters remain in the authoring workspace when impractical for Git. Optimized distributable derivatives may be committed or deployed through an ordinary CDN only when their provenance permits public delivery.

## Rendering and Composition

The existing thin WebGL runtime remains the initial integration boundary, but scene-specific assumptions must move into the manifest.

### Desktop

- Preserve the wide editorial composition.
- Render the diagonal water channel, fog depth, localized ripple distortion, restrained particles, and subtle pointer perspective.
- Avoid continuous large-amplitude motion.

### Portrait mobile

- Use portrait focal-point and crop metadata rather than center-cropping a landscape canvas.
- Keep the armillary focal structure, water channel, and oculus visible simultaneously.
- Select framebuffer resolution from CSS size, device-pixel ratio, GPU capability, and sustained frame time.
- Do not impose a fixed 1920-pixel ceiling when a capable high-density phone can sustain a sharper buffer.
- Reduce effect count before reducing resolution below acceptable display density.

### Cinema mode

- Retain an optional complete wide-frame presentation over a blurred environmental backdrop.
- Cinema is not the automatic portrait default; full-screen portrait composition is.

## Motion

- Water ripples are localized by the authored channel mask.
- Fog drifts slowly at independent depth rates.
- Hanging roots and reeds use subtle low-frequency displacement.
- Mineral lights breathe within a narrow luminance range.
- Particles remain sparse and pause when hidden or off-screen.
- Pointer and scroll response use small perspective offsets, never scroll hijacking.
- Reduced-motion and Save-Data users receive the complete static poster without degraded content.

## Originality Review

Before shipping:

- compare full compositions side by side and reject matching layouts;
- inspect major silhouettes, architecture, water boundaries, and lighting landmarks;
- reject generated assets containing recognizable source-specific structures;
- run image-similarity checks as screening evidence, not as a legal safe-harbor test;
- retain prompts, provenance records, and review notes.

The standard is independent visual authorship, not merely passing a numerical similarity threshold.

## Failure Behavior

- Missing or failed assets retain the static Drowned Observatory poster.
- WebGL initialization failure never exposes private local assets or broken transparent layers.
- Unsupported effects degrade individually.
- Asset URLs respect the GitHub Pages base path.
- Renderer errors are observable in the wallpaper lab without appearing in the normal interface.

## Verification

The implementation is complete only when:

1. no shipped file derives from the Workshop package;
2. provenance and attribution coverage passes for every asset;
3. the scene renders from a clean checkout with no private local files;
4. desktop, portrait mobile, reduced-motion, Save-Data, and WebGL-failure paths work;
5. portrait mode preserves the intended focal composition and acceptable pixel density;
6. the public dev deployment loads all scene assets without 404s or runtime errors;
7. browser screenshots and interaction recordings confirm visible water, fog, depth, and restrained motion;
8. the public scene remains visually distinct from Forgotten Ruins under human review.

## Non-Goals

- Reconstructing or obfuscating the Workshop package.
- Preserving the original wallpaper's exact composition.
- Shipping its audio.
- Adding DRM or access-control theater.
- Building the other two planned environmental scenes in this scene-specific change.
