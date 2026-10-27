"""Tests for the Claude Code session guards (run: python3 -m unittest test_guards)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
PANE = HERE / "pane-guard.py"
MODEL = HERE / "model-guard.py"


def run(script, event, env=None):
    out = subprocess.run([sys.executable, "-I", str(script)], input=json.dumps(event),
                         env=env, capture_output=True, text=True, timeout=30)
    return out, (json.loads(out.stdout) if out.stdout.strip() else None)


class Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="z0-guard-test-"))
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.dir / "state"),
                        Z0_GUARD_CONFIG=str(self.dir / "cfg"), HOME=str(self.dir))
        for k in ("Z0_GUARD_ALLOW_KILL", "Z0_EXPECTED_MODEL", "ANTHROPIC_MODEL",
                  "CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK", "Z0_GUARD_PROTECTED"):
            self.env.pop(k, None)


class PaneGuard(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def bash(self, command, **env):
        _, out = run(PANE, {"tool_name": "Bash", "tool_input": {"command": command},
                            "session_id": "t", "cwd": str(self.e.dir)}, {**self.e.env, **env})
        return out["hookSpecificOutput"]["permissionDecision"] if out else "allow"

    def test_denies_pane_and_desktop_kills(self):
        for cmd in ("tern kill 3", "tern close --all", "tmux kill-server", "tmux -L x kill-pane",
                    "pkill waybar", "pkill -f omp", "killall -9 Hyprland", "pkill -9 firefox",
                    "ssh host 'pkill -f tern'", "bash -c 'tmux kill-session -t a'",
                    "sudo systemctl --user restart waybar.service", "hyprctl dispatch exit",
                    "hyprctl kill", "kill $PPID", "kill -9 -1", "pkill -u me",
                    "pgrep noctalia | xargs kill", "x && timeout 5 killall qs", "reboot",
                    "loginctl terminate-user me", f"kill {os.getppid()}"):
            self.assertEqual(self.bash(cmd), "deny", cmd)

    def test_allows_ordinary_commands(self):
        for cmd in ("tern ls", "tmux ls", "echo tmux kill-server", "git commit -m 'tern kill'",
                    "kill -9 999999999", "pkill -f z0-no-such-proc-zzz", "kill -l",
                    "systemctl --user restart some-worker", "hyprctl dispatch workspace 2",
                    "pkill -f omp-bridge-zzz-test", "ls -la"):
            self.assertEqual(self.bash(cmd), "allow", cmd)

    def test_owner_allow_and_self_allow_denied(self):
        self.assertEqual(self.bash("tmux kill-server", Z0_GUARD_ALLOW_KILL="1"), "allow")
        cfg = self.e.dir / "cfg"
        cfg.mkdir()
        allow = cfg / "allow-kill"
        allow.touch()
        self.assertEqual(self.bash("tmux kill-server"), "allow")
        old = time.time() - 3600
        os.utime(allow, (old, old))
        self.assertEqual(self.bash("tmux kill-server"), "deny")
        self.assertEqual(self.bash(f"touch {allow}"), "deny")
        self.assertEqual(self.bash("touch ~/.config/z0-guard/allow-kill"), "deny")
        self.assertEqual(self.bash("echo 1 > ~/.config/z0-guard/allow-kill"), "deny")
        # prose that only mentions the file, in a heredoc or an argument, is fine
        doc = ("cat > notes.md <<'EOF'\nthe owner's override: touch ~/.config/z0-guard/allow-kill"
               " (or tmux kill-server, pkill omp: `don't`)\nEOF\necho done >> idx.md")
        self.assertEqual(self.bash(doc), "allow")
        self.assertEqual(self.bash("grep -n allow-kill ~/.config/z0-guard/README"), "allow")

    def test_receipt_and_non_bash(self):
        self.bash("tern kill 1")
        rows = (self.e.dir / "state/z0-guard/pane-guard.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(rows[-1])["decision"], "deny")
        out, parsed = run(PANE, {"tool_name": "Read", "tool_input": {}}, self.e.env)
        self.assertIsNone(parsed)

    def test_crash_allows(self):
        out = subprocess.run([sys.executable, "-I", str(PANE)], input="{bad",
                             env=self.e.env, capture_output=True, text=True, timeout=30)
        self.assertEqual((out.returncode, out.stdout), (0, ""))


class ModelGuard(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        (self.e.dir / ".claude").mkdir()
        self.settings = self.e.dir / ".claude/settings.json"
        self.settings.write_text(json.dumps({"model": "claude-opus-5-5",
                                             "switchModelsOnFlag": False}))
        self.t = self.e.dir / "t.jsonl"
        self.t.write_text("")

    def reply(self, model, sidechain=False):
        with self.t.open("a") as fh:
            fh.write(json.dumps({"type": "assistant", "isSidechain": sidechain,
                                 "message": {"model": model, "content": []}}) + "\n")

    def fallback(self):
        with self.t.open("a") as fh:
            fh.write(json.dumps({"type": "system", "subtype": "model_refusal_fallback",
                                 "timestamp": "2026-10-26T18:31:10Z", "scope": "session",
                                 "originalModel": "claude-opus-5-5",
                                 "fallbackModel": "claude-opus-4-8",
                                 "apiRefusalCategory": "cyber"}) + "\n")

    def ev(self, name="UserPromptSubmit", **env):
        return run(MODEL, {"hook_event_name": name, "session_id": "s", "cwd": str(self.e.dir),
                           "transcript_path": str(self.t)}, {**self.e.env, **env})[1]

    def test_quiet_when_pinned_and_on_model(self):
        self.assertIsNone(self.ev("SessionStart"))
        self.reply("claude-opus-5-5")
        self.assertIsNone(self.ev())
        self.assertIsNone(self.ev("Stop"))

    def test_warns_on_downgrade_with_receipt(self):
        self.reply("claude-opus-5-5")
        self.fallback()
        self.reply("claude-opus-4-8")
        out = self.ev()
        self.assertIn("claude-opus-4-8", out["systemMessage"])
        self.assertIn("refusal fallback", out["systemMessage"])
        self.assertIn("Tell the owner", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("systemMessage", self.ev("Stop"))
        rows = (self.e.dir / "state/z0-guard/model-guard.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(rows[-1])["active"], "claude-opus-4-8")
        # recovering with /model clears the warning
        self.reply("claude-opus-5-5")
        self.assertIsNone(self.ev())

    def test_sidechain_replies_ignored(self):
        self.reply("claude-opus-5-5")
        self.reply("claude-haiku-4-5", sidechain=True)
        self.assertIsNone(self.ev())

    def test_unpinned_and_switch_flag_warn_at_start(self):
        self.settings.write_text("{}")
        out = self.ev("SessionStart")
        self.assertIn("no model pinned", out["systemMessage"])
        self.assertIn("switchModelsOnFlag", out["systemMessage"])

    def test_env_model_mismatch(self):
        out = self.ev("SessionStart", ANTHROPIC_MODEL="claude-opus-4-8")
        self.assertIn("claude-opus-4-8", out["systemMessage"])

    def test_notify_once(self):
        cfg = self.e.dir / "cfg"
        cfg.mkdir()
        log = self.e.dir / "notified.txt"
        script = self.e.dir / "notify.sh"
        script.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
        script.chmod(0o755)
        (cfg / "notify-cmd").write_text(str(script))
        self.reply("claude-opus-4-8")
        self.ev()
        self.ev()
        time.sleep(0.5)
        self.assertEqual(len(log.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
