#!/usr/bin/env python3
"""Claude Code hook: warn loudly when the session is not on the expected model.

Registered for SessionStart, UserPromptSubmit and Stop. It never blocks.

Why: on 2026-10-26 a "model_refusal_fallback" event silently moved a session from
Opus 5.5 to Opus 4.8 for ~11.5h. The settings pin (model + switchModelsOnFlag=false)
prevents most of that; this hook catches whatever still gets through.

Expected model: the claude process's explicit --model flag when it has one (a worker
that asked for Haiku is not a downgrade), else $Z0_EXPECTED_MODEL, else claude-opus-5-5.
Active model: the last main-thread assistant message in the transcript; before the
first reply, the configured model (--model, ANTHROPIC_MODEL, settings "model").

Each detection appends a receipt to $XDG_STATE_HOME/z0-guard/model-guard.jsonl. When
~/.config/z0-guard/notify-cmd exists (one line: a command prefix, private per host),
the first detection per session also runs `<prefix> <tag> <title> <text>`.
A crash in this file never affects the session (exit 0, no output).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

DEFAULT_EXPECTED = "claude-opus-5-5"
TAIL_BYTES = 4 * 1024 * 1024
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "z0-guard"
NOTIFY_CMD = Path(os.environ.get("Z0_GUARD_CONFIG") or Path.home() / ".config/z0-guard") / "notify-cmd"


def norm(model: str | None) -> str:
    m = (model or "").strip().lower()
    if m.endswith("[1m]"):
        m = m[:-4]
    return m


def matches(active: str, expected: str) -> bool:
    a, e = norm(active), norm(expected)
    return bool(a) and (a == e or a.startswith(e + "-"))


def ancestors(pid: int, limit: int = 12):
    for _ in range(limit):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except (OSError, ValueError, IndexError):
            return
        yield pid, [a.decode(errors="replace") for a in argv if a]
        if ppid <= 1:
            return
        pid = ppid


def claude_flag_model() -> str | None:
    """--model value of the nearest claude ancestor process, if any."""
    for _, argv in ancestors(os.getppid()):
        if not argv or "claude" not in os.path.basename(argv[0]):
            continue
        for i, a in enumerate(argv):
            if a == "--model" and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith("--model="):
                return a.split("=", 1)[1]
        return None
    return None


def configured_model(cwd: str) -> tuple[str | None, str]:
    flag = claude_flag_model()
    if flag:
        return flag, "--model flag"
    if os.environ.get("ANTHROPIC_MODEL"):
        return os.environ["ANTHROPIC_MODEL"], "ANTHROPIC_MODEL"
    for path in (Path(cwd) / ".claude/settings.local.json", Path(cwd) / ".claude/settings.json",
                 Path.home() / ".claude/settings.json"):
        try:
            model = json.loads(path.read_text()).get("model")
        except (OSError, ValueError, AttributeError):
            continue
        if model:
            return model, str(path)
    return None, "unpinned (Claude Code default)"


def switch_on_flag_enabled() -> bool:
    if os.environ.get("CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK"):
        return False
    try:
        return json.loads((Path.home() / ".claude/settings.json").read_text()).get(
            "switchModelsOnFlag") is not False
    except (OSError, ValueError, AttributeError):
        return True


def transcript_tail(path) -> list[dict]:
    rows = []
    try:
        with open(os.path.expanduser(str(path)), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read()
    except (OSError, TypeError):
        return rows
    for line in data.splitlines():
        if b'"assistant"' not in line and b"model_refusal_fallback" not in line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def observed(rows: list[dict], expected: str) -> tuple[str | None, list[dict]]:
    """Last main-thread model, and refusal fallbacks not yet recovered from (a later
    reply on the expected model clears them)."""
    model, fallbacks = None, []
    for r in rows:
        if r.get("isSidechain"):
            continue
        if r.get("type") == "system" and r.get("subtype") == "model_refusal_fallback":
            fallbacks.append({k: r.get(k) for k in ("timestamp", "originalModel", "fallbackModel",
                                                    "apiRefusalCategory", "scope")})
        msg = r.get("message")
        if r.get("type") == "assistant" and isinstance(msg, dict):
            m = msg.get("model")
            if m and not m.startswith("<"):
                model = m
                if matches(m, expected):
                    fallbacks = []
    return model, fallbacks


def notify_once(session: str, title: str, text: str) -> None:
    try:
        prefix = shlex.split(NOTIFY_CMD.read_text().strip())
    except OSError:
        return
    if not prefix:
        return
    flag = STATE / "model-guard-notified" / session
    if flag.exists():
        return
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(dt.datetime.now().isoformat())
    args = ["z0-model-guard", title, text]
    if os.path.basename(prefix[0]) == "ssh":  # the remote shell re-splits its arguments
        args = [shlex.quote(a) for a in args]
    try:
        subprocess.Popen(prefix + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def main() -> int:
    event = json.loads(sys.stdin.read() or "{}")
    name = event.get("hook_event_name") or "unknown"
    session = str(event.get("session_id") or "unknown").replace("/", "_")
    cwd = str(event.get("cwd") or os.getcwd())
    flag = claude_flag_model()
    expected = flag or os.environ.get("Z0_EXPECTED_MODEL") or DEFAULT_EXPECTED
    active, fallbacks = observed(transcript_tail(event.get("transcript_path")), expected)
    source = "transcript"
    if active is None:
        active, source = configured_model(cwd)
    problems = []
    if active is None:
        problems.append(f"no model pinned ({source}); expected {expected}")
    elif not matches(active, expected):
        problems.append(f"active model is {active} ({source}), expected {expected}")
    if fallbacks:
        last = fallbacks[-1]
        problems.append(f"{len(fallbacks)} refusal fallback(s) in this session; last at "
                        f"{last['timestamp']}: {last['originalModel']} -> {last['fallbackModel']}"
                        f" ({last['apiRefusalCategory']})")
    if name == "SessionStart" and not flag and switch_on_flag_enabled():
        problems.append("switchModelsOnFlag is not false: a flagged message can switch models "
                        "silently (set it false in ~/.claude/settings.json)")
    if not problems:
        return 0
    receipt = {"at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
               "event": name, "session": session, "cwd": cwd, "active": active,
               "source": source, "expected": expected, "problems": problems,
               "fallbacks": fallbacks[-3:]}
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with open(STATE / "model-guard.jsonl", "a") as fh:
            fh.write(json.dumps(receipt) + "\n")
    except OSError:
        pass
    banner = "MODEL GUARD: " + "; ".join(problems)
    fix = f" Fix: run /model {expected} (or restart claude)."
    downgraded = bool(fallbacks) or (active is not None and not matches(active, expected))
    if downgraded:
        notify_once(session, "Claude model downgrade", banner[:300])
    out: dict = {"systemMessage": banner + fix}
    if name in ("SessionStart", "UserPromptSubmit"):
        out["hookSpecificOutput"] = {
            "hookEventName": name,
            "additionalContext": banner + fix + " Tell the owner about this in your next reply "
            "before doing other work; do not continue silently on a different model."}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken guard must never break the session
        print(f"model-guard error: {exc}", file=sys.stderr)
        sys.exit(0)
