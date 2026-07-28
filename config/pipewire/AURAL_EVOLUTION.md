# Aural Evolution

One persistent PipeWire sink auditions ten parameter variants without restarting
the audio graph or moving streams between variants.

## Use

- Click the waveform button in Noctalia, or run `audio-evolve`.
- Click a variant, or press `Alt+1` through `Alt+9`; `Alt+0` selects variant 10.
- Keep the track, playback level, and listening position fixed.
- Choose **Favorite current** only after revisiting the closest alternatives.
- Native and room modes keep independent histories for each headphone.
- **Calibration Smoke Test** is a permanent listening mode with Spectrum and
  Colors banks. It is deliberately separate from evolutionary training data.

The native lane first calibrates broad bass, body, presence, and 5.2 kHz
clarity axes, then searches locally around each winner. Candidate spacing is
measured in response space, not raw parameter distance. The room lane adds a
quiet, time-aligned R02 BRIR blend whose response is limited to the useful
early field. There is no compressor or limiter. Per-candidate trim matches
pink-noise energy through the active correction with BS.1770 K weighting; the
room matrix is included in the same calculation.

Selections made while playback is paused are valid: the controller briefly
primes the suspended graph with silence, atomically swaps one compact
`param_eq` graph through PipeWire's audio converter, and lets it suspend again.
Whole-graph swaps avoid PipeWire 1.6.7's ineffective filter-chain control-port
updates while keeping the audio stream connected.

## Commands

```text
audio-evolve                         open the popup
audio-evolve select 1               audition variant 1
audio-evolve select 0               audition variant 10
audio-evolve favorite               save the winner and create the next round
audio-evolve calibrate              wider level-matched round; keep current anchor
audio-evolve mode native|room|spectrum|colors|imaging
audio-evolve activate               make the sink default and move Pulse streams
audio-evolve status
audio-evolve doctor
audio-evolve-validate               offline FIR/BRIR/round safety report
```

## Calibration Smoke Test

Spectrum preserves the large-contrast test:

`Reference · Bass ± · Body ± · Presence ± · Clarity ± · Warm`

Colors adds musical combinations:

`Reference · Punch · Deep · Vocal · Smooth · Airy · V-shape · Lush · Attack · Night`

`Alt+1…0` selects within the active bank. Selecting the already-active
non-reference profile again doubles its tonal delta: Bass +6 becomes Bass +12,
for example. Intensity is capped at ×2, resets to ×1 when another profile is
selected, and persists independently per bank. Each intensified response is
K-weight level-matched, then reduced if necessary to enforce a hard modeled
peak ceiling of −3 dBFS. Reference never intensifies.

`activate` persists Aural Evolution as WirePlumber's default and moves existing
Pulse streams without restarting their apps. Audio-stack restart paths notify
three seconds before interrupting streams. Native Spotify and Plex clients
normally reconnect automatically; browsers are never restarted for recovery.

Preferences live in
`~/.local/share/aural-evolution/preferences.db` (SQLite WAL). DSP runs entirely
inside PipeWire's real-time graph; Python, SQLite, and Rofi only touch the
control plane when a button is pressed. Every selection, favorite, mode change,
calibration, and raw listening note is append-only in the `event` table.
Each new round also stores hashes for every correction FIR, the BRIR, PipeWire
graph, controller, optimizer bounds, and level-matching method in
`round_context`, so preferences cannot silently drift away from their DSP.

The database also preserves the original under-spaced HD800S round under
`archive:hd800s-native-gen0-v1` and the accidental Monarch-on-HD800S favorite
under `preset:accidental-monarch-on-hd800s`.

This processed sink is intentionally not called bit-perfect. The original
Topping DX5 sink remains available for an unprocessed reference.

## MAX validation — 2026-07-24

The live graph swap was measured at the Aural output. Predicted and captured
variant deltas agreed within 0.004 dB RMS, and selecting the saved champion
again reproduced the first capture. PipeWire reported no xruns; the active
Aural output used about 66–80 µs of a 5.33 ms quantum.

| Gate | Previous round | Calibrated round |
|---|---:|---:|
| Closest pair, response-shape RMS | 0.306 dB | 0.521 dB |
| Candidate pairs below 0.5 dB RMS | 8 | 0 |
| K-weighted level spread | 1.048 dB | <0.001 dB |
| Worst modeled response peak | -5.93 dBFS | -5.64 dBFS |

Synthetic noisy-listener trials found that the small axis-plus-explorer search
converged faster than a quadratic Bayesian preference model through roughly the
first twelve rounds. The heavier model is therefore deferred until enough
real, level-matched choices exist to train it. This is a designed listening
experiment first and a learned preference model second.

The active correction is preserved as a **liked legacy HD800-family FIR**. Its
bytes and response do not match current upstream AutoEq HD800 or HD800S
artifacts, and the repository does not preserve the source measurement, target,
AutoEq version, or generation command. It must not be described as a
scientifically reproducible HD800S target. A later baseline-screening phase
should compare it blindly with raw DX5 and reproducible, fixture-compatible
HD800S corrections before optimizing smaller tonal changes.
