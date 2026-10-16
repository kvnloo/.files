# .files specification in the real Hapsland dashboard

This model visualizes `kvnloo/.files`, not the Hapsland repository itself. The
frontend runs in the isolated checkout at
`/root/workspace/hapsland-dotfiles-reference-20261016`, based on
`dearlordylord/hapsland@a0773f79ffa4babdba219c773832fa3a61cc803c`.

## Open and run

Open **http://127.0.0.1:4183/dotfiles.html** on this workstation/phone.

From the existing Hapsland checkout:

```sh
mise exec node@24 -- ./node_modules/.bin/vite \
  --config packages/agent-flow-viz/vite.dotfiles.config.ts
```

The local checkout includes uncommitted shared-component refactors and the
`.files` entrypoint. Cloning the upstream commit alone does **not** include this
integration; preserve both repositories using the recovery checkpoint.
Dependencies are already installed. The app uses the existing Foldkit and Vite
stack, not a replacement standalone frontend.

## What is shared with Hapsland

The original dashboard and this entrypoint use the same production components:
header and four-card navigation; node/route/SVG topology renderer; CSS-3D planes;
camera sliders, rotation and zoom gestures; inspector frame; retained-history
rows and seek control; event-lane chart geometry. The original Hapsland consumers
were migrated to these shared owners rather than copied into a second UI.

`.files` supplies four architectural regions, 14 concepts and 20 source-cited
directed relationships. The complete connected 2D architecture remains below
the 3D view. Select a region, concept or relationship to inspect its source.
Use **Focus selected region**, camera controls or the full 2D diagram for detail.

The existing adapter remains the only transition owner. Play/Step consumes the
compiled Bend decisions; seeking retains previously checked future results;
playback pauses at scenario end. The timeline axis is checked event position,
not elapsed time or a performance measurement.

## Model, provenance and validation

- `Flow.bend`: executable state model; compiled with pinned **Bend 2.0.37**.
- `adapter.mjs`: numeric ABI boundary for the compiled model.
- `model.json`, `architecture.json`: state metadata and cited architecture.
- `scenarios.json`: nine supplied-fact scenarios, including refusal paths.
- `Flow.generated.mjs`, `projection.json`, `receipt.json`: generated artifacts
  and hashes binding them to the cited source bytes and compiler.

Check the current artifacts from `.files` without recompiling:

```sh
node docs/spec-diagram/build.mjs --check
```

Rebuilding requires `BEND` pointing to the existing 2.0.37 compiler. Hapsland's
own workspace producers separately pin 2.0.36; do not change either pin to make
the other producer pass. The Vite entrypoint fails closed on stale artifacts or
changed cited sources, and exposes only its package, dependencies and diagram
assets—not the rest of the dotfiles tree.

## Evidence is not deployment

The native-status badge is independent of replay. Fresh 16 October preflight
found an externally installed K3s service active on Groot, without the `.files`
ownership marker; the managed deployment remains **UNVERIFIED**. Its health,
network policy, quota, CPU Job and TTL acceptance are not established.
Supplied facts do not prove host readiness or installation. This browser sends
no shell commands or Kubernetes requests, and synthetic accepted transitions
never upgrade real deployment status.

Physical Android Chrome receipts and screenshots live in
`/root/.local/state/omp/work-recovery-20261016/verification/`. They include
1280×900 desktop and 411×850 phone surfaces plus all nine replay scenarios.
The separate `/root/workspace/bend-adreno-phone-20261016` experiment proves a
checked Adreno OpenCL dispatch through a Bend foreign-C effect. It does not
make this browser model or native Bend `!` evaluation run on Adreno.
