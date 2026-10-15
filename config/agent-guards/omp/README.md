# OMP credential guard

OMP has both declarative tool policies and a blocking extension hook. This
extension uses the latter so bash wrappers, explicit paths, `eval` code and MCP
arguments receive the shared Python inspection.

Local source evidence, inspected 2026-10-15, checkout HEAD `1771ad4c26`:

| Mechanism | Evidence |
| --- | --- |
| `tool_call` may block before execution | [docs/extensions.md:307](/home/kvn/workspace/oh-my-pi/docs/extensions.md:307) |
| Return `{ block: true, reason }` | [docs/extensions.md:81](/home/kvn/workspace/oh-my-pi/docs/extensions.md:81) |
| All registered tools are intercepted | [docs/extensions.md:420](/home/kvn/workspace/oh-my-pi/docs/extensions.md:420) |
| Handler errors block execution | [docs/extensions.md:735](/home/kvn/workspace/oh-my-pi/docs/extensions.md:735) |
| User discovery is `~/.omp/agent/extensions`, profiles have separate roots | [docs/extension-loading.md:35](/home/kvn/workspace/oh-my-pi/docs/extension-loading.md:35) |
| Explicit `--extension/-e` paths, including `.mjs` | [docs/extension-loading.md:3](/home/kvn/workspace/oh-my-pi/docs/extension-loading.md:3), [line 65](/home/kvn/workspace/oh-my-pi/docs/extension-loading.md:65) |
| `bash.patterns` cannot guard shells spawned by `eval` | [docs/bash-tool-runtime.md:38](/home/kvn/workspace/oh-my-pi/docs/bash-tool-runtime.md:38) |
| Per-tool `tools.approval` policy | [docs/approval-mode.md:28](/home/kvn/workspace/oh-my-pi/docs/approval-mode.md:28) |
| Restricted subagents can load no extensions of their own | [docs/extensions.md:541](/home/kvn/workspace/oh-my-pi/docs/extensions.md:541) |

The repo's existing `config/omp/extensions/z0-continuity/index.ts` also uses
`pi.on` and child processes. The new guard requires Python 3 and OMP's existing
Node-compatible extension runtime, with no npm packages.

From this dotfiles checkout, launch a guarded session explicitly:

```bash
GUARDS="$(realpath config/agent-guards)"
omp --extension "$GUARDS/omp/credential-guard.mjs"
```

This explicit path avoids copying code or relying on `.mjs` auto-discovery.
For persistence, back up the active profile's `config.yml` or `config.yaml`,
then append the absolute `.mjs` path to its existing `extensions:` list. Do not
replace other entries. The default global YAML location is documented at
[docs/settings.md:16](/home/kvn/workspace/oh-my-pi/docs/settings.md:16).
Restart OMP after changing configuration.

The callback forwards `event.toolName`, `event.input` and `ctx.cwd`. It blocks
on an unavailable Python process, timeout, excessive output or invalid protocol.
It never executes the model's command itself. The runnable adapter tests use a
small event-registration fixture and the real shared hook, without importing
OMP's providers or loading credentials. They do not constitute a live OMP test.

Do not assume a parent extension covers every restricted subagent or code path.
Explicit extensions survive `--no-extensions`, while ambient configured ones
are excluded, per [docs/extension-loading.md:107](/home/kvn/workspace/oh-my-pi/docs/extension-loading.md:107).
For more restrictive sessions, `tools.approval.eval: deny` disables the entire
code tool, but it is not a filesystem boundary. Run coding agents under an OS
user that cannot access the stores, and constrain subagents there too.

Rollback: launch without `--extension`, or remove this entry from the profile's
`extensions:` list and restart. No files need to be removed for explicit loading.
