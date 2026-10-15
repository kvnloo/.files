# Hermes credential guard

Hermes supports a general plugin `pre_tool_call` veto. This plugin returns
`{"action":"block","message":"fixed public reason"}` when the shared Python
hook denies a call, or when the guard process fails. No approval UI interaction
or approval observer hook is needed.

Local source evidence, inspected 2026-10-15, checkout HEAD `88c817faf7`:

| Mechanism | Evidence |
| --- | --- |
| User plugins, manifest, `register(ctx)` | [hermes_cli/plugins.py:3](/home/kvn/workspace/hermes-agent/hermes_cli/plugins.py:3) |
| `pre_tool_call` receives `tool_name` and `args` | [docs/observability/README.md:175](/home/kvn/workspace/hermes-agent/docs/observability/README.md:175) |
| Dispatcher interprets block directives | [hermes_cli/plugins.py:1786](/home/kvn/workspace/hermes-agent/hermes_cli/plugins.py:1786) |
| Existing plugin returns the same block shape | [plugins/security-guidance/__init__.py:104](/home/kvn/workspace/hermes-agent/plugins/security-guidance/__init__.py:104) |
| Plugins are opt-in via enabled list | [hermes_cli/plugins_discovery.py:213](/home/kvn/workspace/hermes-agent/hermes_cli/plugins_discovery.py:213) |
| Policy callback timeouts block | [hermes_cli/plugins.py:1684](/home/kvn/workspace/hermes-agent/hermes_cli/plugins.py:1684) |
| Approval observers cannot veto | [docs/observability/README.md:206](/home/kvn/workspace/hermes-agent/docs/observability/README.md:206) |
| File/code tool names used by the adapter | [tools/file_tools.py:1250](/home/kvn/workspace/hermes-agent/tools/file_tools.py:1250), [tools/code_execution_tool.py:863](/home/kvn/workspace/hermes-agent/tools/code_execution_tool.py:863) |

This dotfiles repo has Hermes systemd service definitions but no existing Hermes
tool-policy plugin. This plugin covers `terminal`, `read_file`, `write_file`,
`search_files`, `patch` paths and V4A patch headers, `execute_code`, and `mcp__*`
arguments through the shared policy. Hermes does not supply a `cwd` in its
documented hook payload; relative file targets use the process cwd, and terminal
calls with `workdir` override it. Remote/container filesystem resolution can
differ, so the custody OS user separation remains necessary.

Manual installation, from this dotfiles checkout:

```bash
GUARDS="$(realpath config/agent-guards)"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_ROOT/plugins"
test ! -e "$HERMES_ROOT/plugins/credential-guard" && test ! -L "$HERMES_ROOT/plugins/credential-guard" || { echo "Plugin path exists; stop and review."; exit 1; }
ln -s "$GUARDS/hermes" "$HERMES_ROOT/plugins/credential-guard"
hermes plugins enable credential-guard
```

Use a symlink rather than copying just this directory. The plugin resolves its
own real path to find the adjacent `claude/credential-guard.py`. Keep the whole
`agent-guards` tree. Restart Hermes CLI/gateway processes and verify that
`credential-guard` is enabled. Safe mode or a disabled plugin removes this check.

Tests call `register` with a fixture context, then exercise the real subprocess
protocol and simulated failures. They do not start Hermes or load its provider
credentials. No third-party Python packages are required.

Rollback, then restart Hermes:

```bash
hermes plugins disable credential-guard
rm -- "${HERMES_HOME:-$HOME/.hermes}/plugins/credential-guard"
```

This removes only the symlink created above. Existing profile settings and
credentials are untouched by the plugin itself.
