# External reference evidence gate (Agent Reach)

Applies whenever an agent is asked to explain, implement, compare, or file an issue/PR **based on a linked post** (especially `x.com` / `twitter.com`, image/video demonstrations).

## Mandatory steps for linked X/Twitter posts

1. **Start with Agent Reach**, not the generic webpage fetcher. Load the installed `agent-reach` SKILL.md for the active harness, if available. Check capability with `agent-reach doctor`; follow its reported Twitter backend (currently twitter-cli → OpenCLI → bird). `.files/scripts/setup-agent-tools.sh` provisions the CLI and harness skills, but availability must be checked on the **actual machine**, not inferred from the installer.
2. When the configured skill allows, retrieve the *exact* post and referenced thread (for current Twitter backend, typically `twitter tweet 'https://x.com/.../status/...'`). If the post has media, obtain its video/photo evidence separately, and actually review it before describing animations, UI layout, timings, gesture sequences, or implementation details. Use an available authorized tool such as `yt-dlp` for video metadata/downloads where supported, only with permitted access.
3. If Agent Reach is absent, broken, or the X backend cannot access the post, use a clearly identified **fallback**: supported authenticated browser/Grok route when available, Jina Reader (`https://r.jina.ai/https://x.com/USER/status/ID`), a public embed mirror such as FxTwitter, and then public search/indexed evidence. Do not equate a generic X 403 with the post being inaccessible through Agent Reach. Keep a clear distinction between verified post text and **unseen** video/media.
4. Log an evidence capsule in the task/issue **body**, not only in transient chat:
   - original creator/URL; date checked; retrieval route and whether post/text/thread/media were *actually* read
   - directly observed behavior (with timestamps/frame references for video where helpful) and separately labeled inferred/desired behavior
   - unverified specifics and the next read-only diagnostic needed
5. **Hard gate:** if the external reference is still inaccessible, do not state that the demo implements an inferred feature, claim pixel-perfect parity, or mark reference-dependent implementation **ready**. You may file a provisional proposal, but label source parity **BLOCKED / UNVERIFIED**, link the exact URL, and hand reference inspection to a harness with Agent Reach. Continue independent work that does not require the reference.
6. Respect original creator/OSS attribution and license; never add X cookies, tokens, photos/videos, transcriptions, private screenshots, browser profile data, or `~/.agent-reach` state to Git or CI. Reading X does not authorize posting/replying.

## Regression spot checks

- **Video post:** a linked X demo is used for an implementation issue. Agent locates a working Agent Reach backend and inspects the video before describing pixels or motion; a verified evidence capsule appears in the issue body.
- **X 403 / bad backend:** generic fetch fails; agent checks `agent-reach doctor` and authorized alternatives before claiming inaccessible.
- **No video access:** agent retrieves post text but not video; issue says `POST TEXT VERIFIED / VIDEO UNVERIFIED` and visual fidelity remains blocked.
- **No local CLI:** agent says Agent Reach is not available *in its current runtime*, routes a factual local handoff and refrains from fabricated findings.
- **No credential leakage:** issue and logs contain neither personal cookies nor private media.

## Known regression (2026-10-19)

[Kit Langton's X reference](https://x.com/kitlangton/status/2111955962781384846) was cited in [Ripple #2](https://github.com/kvnloo/ripple/issues/2) without inspecting the post/media; [z0live #29](https://github.com/kvnloo/z0live/issues/29) and [.files #26](https://github.com/kvnloo/.files/issues/26) were filed as cross-repo proposals. A harness with Agent Reach must inspect the linked content and update those issue **bodies** before using it as feature evidence. Track the prevention work in [.files #27](https://github.com/kvnloo/.files/issues/27).

## Sources

- [Agent Reach upstream](https://github.com/Panniantong/Agent-Reach) / [English documentation](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md)
- [This repo's tooling bootstrap](../scripts/setup-agent-tools.sh)
