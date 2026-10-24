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
- Scanners run on one CPU at nice 19 / ionice idle, with 1 GiB address space,
  15 CPU seconds and 20 wall seconds. One hook scanner runs at a time; a busy
  scanner reports that the new event was unchecked instead of queueing work.
- Repository stores and the canonical supervisor journal are initialized under
  ~/.cache/fettl-hooks, never in source worktrees. No baseline/config is written
  into a scanned repository. OMP output uses metadata_only privacy mode.
  OMP explicitly scans the full repository after mutations, so unstaged edits
  are not missed when a repository has a staged-change baseline configured.
- Native Claude stdin/stdout and exit status are preserved. Errors are visible;
  there is no success-shaped fallback. Hook environments omit API credentials.

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

OMP newly discovered modules require a new session/restart to import; installing
this file does not inject it into an already-running session. tool_result returns
supported additionalContext without rewriting the original tool result or asking
an agent to run fixes. Claude handlers were exercised with synthetic native
payloads; a live Claude session's refresh behavior is not assumed.

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
