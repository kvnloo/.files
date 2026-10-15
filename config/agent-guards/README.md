# Agent credential guards

These guards steer Claude Code, OMP and Hermes toward approved passd capabilities.
They block direct credential commands, common shell disguises, environment dumps,
and explicit accesses to Proton, keyring, GnuPG, password-store and passd data paths.
The monitor checks Proton access metadata against exported passd approvals.

Same-user hooks are defense-in-depth, not a security boundary. A coding agent can
disable a hook, change its code, execute an uninspected script, encode a path, or
use another tool to reach the same files. The boundary is the separate **passd OS
user**, filesystem ownership, and Proton AGENT grants. Coding agents must not run
as that user or inherit its session, keyring socket or credentials.

Nothing here installs itself. The service and timer are inactive templates.
The commands below are manual installation instructions, not actions performed by
the tests. Keep this checkout available after installation.

## Shared policy

`claude/credential-guard.py` uses Python 3 stdlib only. It reads tool JSON from
stdin. It never executes a submitted command, opens a store, or prints submitted
arguments. It resolves paths with `expanduser`, `normpath` and `realpath`, including
symlinks and `..`. It uses the supplied tool working directory where available.
It does not expand arbitrary environment variables, glob the filesystem or read
shell startup files.

Shell inspection checks command-position tokens after wrappers, assignments,
shell `-c` strings, eval, substitutions and compound-command boundaries. Interpreter
one-liners and OMP/Hermes code tools receive a separate code scan. Any pipe into
a shell is denied because its stdin may be decoded or otherwise opaque code.
Here strings and here documents containing visible blocked commands are denied.

All credential-tool invocations are denied, including `pass-cli --help`.
`man pass-cli` is also denied as a deliberately simple documentation policy.
These remain allowed:

```bash
git commit -m "mention pass-cli in docs"
grep -r pass-cli docs/
rg printenv
echo "$PATH"
env FOO=bar git status
```

Editing source or documentation that mentions a credential command is allowed
when the target file is outside a protected directory. MCP string arguments are
checked more conservatively, including nested values and mentions of blocked
tool names. `printenv` queries and interpreter references to `os.environ`,
`process.env` or Ruby `ENV` are denied even when they select one variable.
Plain `set`, `export`, `export -p`, `declare -x` and `declare -p` are denied.

This is a best-effort shell recognizer, not a shell interpreter or general code
analyzer. It cannot prove arbitrary programs safe. Recursive searches from an
ancestor directory, computed paths, renamed binaries, dynamic code, preexisting
scripts, same-user modifications and races after path checks remain gaps.

On deny the hook exits 0 and prints only:

```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"fixed public reason"}}
```

An allow exits 0 with no output, leaving normal permissions in force. Malformed
JSON is denied only when it identifies Bash and contains a blocked token;
otherwise it is allowed. Adapter process errors, timeouts and invalid output
block calls. The Claude host's handling of a hook that cannot start is separate
from this protocol; the static permission rules add another check.

## Claude Code

The snippet uses both legacy `:*` and current space-wildcard Bash forms, plus
exact bare rules and path-qualified tool rules. Claude documents these forms as
equivalent trailing wildcards in its [permission reference](https://code.claude.com/docs/en/permissions).
Absolute file rules use `//var/...` and `//proc/...`; a single `/` is relative
to the settings source. `Read` and `Edit` are the effective built-in file rules.
The requested `Grep` and `Glob` entries are also included for compatibility, but
current Claude warns that `Glob(path)` rules are not consulted. Do not rely on
them; the `Read` rules and hook cover explicit search targets. See the same
reference and the [PreToolUse protocol](https://code.claude.com/docs/en/hooks).

The static `Bash(env *)` and `Bash(set *)` rules are intentionally broader than
the hook and may block benign wrapper/option forms. They provide a fallback
when shell parsing or hook loading fails. The example hook command assumes
`~/.files`; this merge replaces it with the actual checkout path.

Run from the dotfiles checkout, after reviewing the snippet:

```bash
GUARDS="$(realpath config/agent-guards)"
mkdir -p "$HOME/.claude"
test -e "$HOME/.claude/settings.json" || printf '{}\n' > "$HOME/.claude/settings.json"
backup="$HOME/.claude/settings.json.before-credential-guards"
test ! -e "$backup" || { echo "Backup already exists; stop and review it."; exit 1; }
cp -p "$HOME/.claude/settings.json" "$backup"
jq --slurpfile guard "$GUARDS/claude/settings.deny.json" \
   --arg script "$GUARDS/claude/credential-guard.py" '
  ($guard[0] | .hooks.PreToolUse[0].hooks[0].command = ("python3 " + ($script | @sh))) as $g
  | .permissions = (.permissions // {})
  | .permissions.deny = (((.permissions.deny // []) + $g.permissions.deny) | unique)
  | .hooks = (.hooks // {})
  | .hooks.PreToolUse = (((.hooks.PreToolUse // []) + $g.hooks.PreToolUse) | unique)
' "$HOME/.claude/settings.json" > "$HOME/.claude/settings.json.credential-guard.new" &&
chmod --reference="$HOME/.claude/settings.json" "$HOME/.claude/settings.json.credential-guard.new" &&
mv "$HOME/.claude/settings.json.credential-guard.new" "$HOME/.claude/settings.json"
```

The merge preserves other permissions and hook events and deduplicates repeated
entries. Restart Claude Code and inspect `/permissions` and `/hooks`. A safe
installation probe sends inert JSON directly to Python, without running a
credential command:

```bash
printf '%s\n' '{"tool_name":"Bash","tool_input":{"command":"pass-cli --help"}}' |
  python3 "$GUARDS/claude/credential-guard.py"
```

Rollback, then restart Claude:

```bash
cp -p "$HOME/.claude/settings.json.before-credential-guards" "$HOME/.claude/settings.json"
```

Restoring that backup also removes later settings edits. If settings have changed,
remove only this hook entry and this snippet's deny entries manually instead.

## OMP and Hermes

Both have pre-tool veto mechanisms in the inspected local checkouts. The OMP
extension and Hermes plugin invoke the same Python hook and map its denial to
the host's blocking result. They inspect shell, file, code and named MCP calls.
See [OMP installation and source evidence](omp/README.md) and
[Hermes installation and source evidence](hermes/README.md) for exact steps,
limitations and rollback. No live profile/config directories were changed.

## Custody-side monitor

Run `monitor/passd-agent-alert.py` **as the separate passd user**, with its Proton
AGENT session. Never give a coding-agent user access to that session to make
monitoring work. The monitor sets `PROTON_PASS_SESSION_DIR` for this exact argv:

```text
<configured pass-cli binary> agent monitor <agent> --output json --limit N
```

The local passd checkout has no top-level `audit --json` command. Its
[`cli.py:150`](/home/kvn/workspace/oss/passd/passd/cli.py:150) defines `agent monitor`,
and [`cli.py:340`](/home/kvn/workspace/oss/passd/passd/cli.py:340) calls `audit.list`.
Consequently this monitor requires `--audit-jsonl`, a custody-maintained metadata
export. It never opens the passd database or automatically invokes the passd CLI.
No live export was created during development.

Each JSONL approval record has this shape:

```json
{"lease_id":"lease-1","status":"approved","capability_id":"cap-1","item_id":"proton-item-id","proton_agent":"broker","approved_at":"2026-10-15T12:00:00Z","expires_at":"2026-10-15T12:01:00Z"}
```

Keep the export under passd ownership with mode 0600. Export approvals and
revocations covering the entire retained Proton event window, including expired
leases. Replace it atomically. Missing or invalid metadata raises an alert.
`lease_id`, approved status and both times are required. `item_id`,
`capability_id` and `proton_agent` add exact checks when present. Export
`revoked_at` for early revocations. Numeric Unix seconds/milliseconds and ISO
timestamps with a timezone are accepted. No clock skew grace is applied.

The parser also accepts native passd audit rows enriched with exact `approved_at`
and `expires_at` from the approved lease. It recognizes `operation` equal to
`access.approve`, `allowed: true`, and `detail.request_id`. Raw audit `ts` plus
`detail.ttl` is insufficient: audit emission may follow approval, so deriving
expiry from those fields could accept access after expiry. Unenriched approval
rows fail closed. Native `access.revoke` rows shorten validity. Fields come from
[`service.py:917`](/home/kvn/workspace/oss/passd/passd/service.py:917),
[`service.py:966`](/home/kvn/workspace/oss/passd/passd/service.py:966) and the audit
serializer at [`service.py:1225`](/home/kvn/workspace/oss/passd/passd/service.py:1225).
Passd machine-agent IDs differ from Proton AGENT IDs. Native `agent_id` is
therefore not treated as `proton_agent`. Native stored-item IDs may also differ
from Proton IDs; normalize them in the export before enabling item matching.
For live Proton-backed capabilities, enrich the export with the Proton item ID
from the approved reference. Never put item content or secrets in this export.

**Monitor field names must be verified against real `agent monitor --output json`
output by the custody operator.** The fixtures use an invented plausible schema.
The parser accepts lists or lists wrapped in `events`, `data`, `results`, `logs`
or `items`. Keys are case/underscore insensitive. It recognizes `reason/Reason`,
`time/create_time/timestamp/created_at/ts`, `item/item_id`, `agent/agent_id/agent_name`,
and `action/event/type`; item and agent may be objects with `id`. Unrecognized
containers fail closed. Missing event metadata is flagged, not silently skipped.

A structured reason must start `passd capability=<id> lease=<id>` and may have
additional context. Every event is checked against an approved lease by ID and
the half-open interval `approved_at <= event_time < expires_at`. Checks flag
unstructured/missing reasons, absent approvals, unknown agents, invalid times,
access outside validity, and optional capability/item/agent mismatches.

Stdout contains counts only. Item keys are SHA-256 hashes of opaque item IDs;
actions use fixed labels, with unknown values grouped as `other`.
`event_flag_counts` has one count dictionary per input event in input order,
so each flagged event remains distinguishable without printing its metadata.
Reasons, titles, raw IDs, timestamps, item content and subprocess diagnostics
are never emitted. Stderr alerts use fixed text. Alerts and collection failures
exit 1. Success exits 0. `--notify` uses `notify-send`; `--alert-command 'program arg'`
passes a static message as the final argv element without a shell.

This is stateless polling. Counts repeat across overlapping polls. It does not
prove use-budget compliance or fill gaps in audit retention. A full `--limit`
window raises `possibly_truncated_window` rather than silently claiming complete
coverage. Size the export and poll window appropriately; repeated saturation
requires operator review. Monitoring one AGENT cannot discover other AGENTs whose
events the Proton command does not return.

To install templates, log into the passd user's own session first. Set `GUARDS`
to that user's reviewed checkout. The paths in ExecStart are placeholders:

```bash
GUARDS="$HOME/.files/config/agent-guards"
test ! -e "$HOME/.config/systemd/user/passd-agent-alert.service" || { echo "Service already exists; stop and review."; exit 1; }
test ! -e "$HOME/.config/systemd/user/passd-agent-alert.timer" || { echo "Timer already exists; stop and review."; exit 1; }
install -Dm644 "$GUARDS/monitor/passd-agent-alert.service" "$HOME/.config/systemd/user/passd-agent-alert.service"
install -Dm644 "$GUARDS/monitor/passd-agent-alert.timer" "$HOME/.config/systemd/user/passd-agent-alert.timer"
systemctl --user edit --full passd-agent-alert.service
# Replace REPLACE_* values, binary and checkout paths; verify AGENT/export schemas.
systemctl --user daemon-reload
systemctl --user enable --now passd-agent-alert.timer
journalctl --user -u passd-agent-alert.service
```

The unit makes the home directory read-only. If the verified CLI needs to update
session metadata, add only its session directory to `ReadWritePaths=`. Ensure the
CLI uses the AGENT session, not a full personal session. If user namespaces are
unavailable, systemd's filesystem isolation directives may need host-specific
adjustment; diagnose in that user's journal before enabling the timer.

Rollback, as the same passd user:

```bash
systemctl --user disable --now passd-agent-alert.timer
systemctl --user stop passd-agent-alert.service
rm -- "$HOME/.config/systemd/user/passd-agent-alert.service" "$HOME/.config/systemd/user/passd-agent-alert.timer"
systemctl --user daemon-reload
```

## Tests

All submitted commands are inert strings. The monitor tests use only a fake
executable and canned JSON/JSONL. Adapter tests call the actual Python guard,
plus simulated process errors. Nothing invokes real credential tools or reads
credential stores. Run all tests from the worktree without pytest or scratch dirs:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s config/agent-guards/claude -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s config/agent-guards/hermes -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s config/agent-guards/monitor -v
PYTHONDONTWRITEBYTECODE=1 node config/agent-guards/omp/test-adapter.mjs
```

Do not run the repository's unrelated live credential tests as part of this
suite. No temporary files, live installations, network or credentials are needed.
