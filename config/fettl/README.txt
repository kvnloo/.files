Fettl local agent checks

Install from this checkout:
  python3 scripts/setup-fettl.py
  python3 scripts/setup-fettl-hooks.py

Linux prerequisites: Python >=3.11, PyYAML (Arch: python-yaml), git,
bubblewrap, util-linux (ionice), and the fleet.toml-pinned Fettl binary.
The hook runner uses /usr/bin/python3 and Python standard-library modules.
The OMP extension uses the installed host runtime; no npm install is needed.

Desired state
- hooks.json selects exactly Claude PreToolUse, PostToolUse and Stop;
  Hermes post_tool_call for write_file|patch; OMP successful write/edit/
  apply_patch/notebook tool_result events.
- targets.json lists the default Hermes home and the three confirmed served
  profiles chiefstaff, clean and intake. Missing homes are skipped. No other
  profiles are swept. Override explicitly with repeated --hermes-home PATH.
- setup-fettl-hooks.py stages native `fettl hook install --agent ... --global`
  output, retains its executable identity and ownership markers, then merges
  only Fettl entries. It backs up changed local files privately under
  ~/.config/fettl/backups before writing them. Other settings and hooks remain.
- Existing ~/.omp/agent/config.yml is not changed. The supported auto-discovery
  directory ~/.omp/agent/extensions/fettl/index.ts contains the extension link.

Read-only/offline enforcement
- No fix, agent, login, account, diagnostics-submit or upload command is used.
- bubblewrap gives each scanner invocation a private network/PID namespace,
  read-only root and source mounts, private /proc and /dev, and hidden host
  /run and /tmp sockets. Only ~/.cache/fettl-hooks is writable. There is no
  unsandboxed fallback. The PID namespace tears down supervisor descendants.
- Scanners run in a systemd user scope with MemoryMax=1G, on one CPU at
  nice 19 / ionice idle, with 1 GiB address space, 15 CPU seconds and 20 wall
  seconds. One scanner runs at a time; busy events log as unchecked.
- Repository stores and the canonical supervisor journal are initialized under
  ~/.cache/fettl-hooks, never in source worktrees. No baseline/config is written
  into a scanned repository. Shadow scans use local_only privacy mode to
  retain rule, file and message in private local JSONL; no egress is possible.
  Full scans include unstaged edits. JSON capture is bounded to 8 MiB.
- mode.json is the single shared switch: {"mode":"shadow"} by default.
  Hooks reread it for every response. Missing/invalid config fails silent.
  Shadow writes ~/.local/state/fettl-shadow/<agent>.jsonl, returns no output,
  and exits zero even on scanner errors. No enforcement is enabled.
  {"mode":"enforce"} restores native responses; only Kevin may authorize it.
  Claude PreToolUse previously preserved native blocking responses/exit codes.
  Hook environments omit API credentials.

Shadow summary (no source scan or model call):
  python3 config/fettl/shadow-summary.py --since 2026-10-24T17:19:15+00:00 --output /path/to/summary.json
The summary deduplicates scan latency, groups findings by agent/rule, and
excludes explicit evaluation fixture directories and old unattributed rows.
window_complete stays false until 24 hours have actually elapsed; an empty
agent table does not prove that any hook ran. A one-shot user-systemd timer
can call this command after the observation window without a paid agent.

Hermes compatibility and activation
Fettl 0.19.78 emits a YAML hooks LIST with when.tools, but the installed Hermes
shell-hook parser requires an event-to-list MAPPING with matcher. Its actual
payload has tool_name, tool_input and extra terminal status/call/result metadata;
Fettl requires session_id, sequence, tool and success. The narrow bridge adapts
these contracts, verifies required fields, derives success from actual outcome
and error fields, and assigns stable monotonic sequences per session/call. It
uses absolute mutation result paths, not the gateway's unrelated process cwd.
Ambiguous relative paths are reported unchecked. Native post-action review is
observational, not a claim that an edit was prevented or a fix was applied.

The exact supported shell command is approved in each home's existing
shell-hooks-allowlist.json. This does not enable hooks_auto_accept or approve
unrelated commands. Hermes hot-syncs config and consent; the four homes' logs
recorded registration without restarting the gateway. No Fettl Python plugin
or Hermes core code is changed. Generic Hermes plugin discovery is cached but
supports an explicit force rescan; no rescan/reload is performed here.

OMP extension source changes require a fresh session/reload to replace an
already imported handler. Existing handlers may continue adding their old
constant banner even when the bridge returns empty output; restart/reload
that OMP session to remove it. New handlers silently skip internal URI writes
and paths outside a git worktree. Shadow returns no additionalContext.
No Hermes gateway restart is required: its bridge reads mode on each call.

Native status limitation
Fettl's Claude installer additionally generates UserPromptSubmit. The requested
three-event installation deliberately omits that extra trigger, so native
`fettl hook status --agent claude --global` reports STALE/incomplete. This is not
an executable-integrity failure. Its Hermes status also cannot describe the
installed runtime's corrected mapping schema. Do not raw-reinstall over these
sandboxed commands to silence the status; rerun setup-fettl-hooks.py instead.

Evidence
The initial local setup's hooks-install.json, hooks-activation.json and
hooks-summary.txt are under data/operations/fettl-20261023 in the zer0 workspace.
They distinguish config presence, native handler probes, real Hermes shell-hook
parsing/dispatch, live registration logs, and OMP's next-session import boundary.
Safety probes observed EROFS for source writes, ENETUNREACH for network access,
resource limits and cleanup of an owned long-running namespace descendant.
No build, lint, formatter, test suite, provider turn or gateway restart was run.

Local links reference the checkout from which this installer is run. Before
removing a temporary worktree, rerun the installer from the permanent checkout
(after intentionally updating/removing the owned links), or keep that worktree.
