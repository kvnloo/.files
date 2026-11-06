#!/usr/bin/env python3
"""Claude Code PreToolUse(Bash) guard: never kill the owner's panes or desktop.

Denies Bash commands that would end tern panes/sessions, tmux sessions, the agent's
own process chain or the owner's interactive desktop programs:

  tern kill|close ...                 tmux kill-server|kill-session|kill-window|kill-pane
  pkill/killall of a protected name   pkill -f PATTERN that matches a protected process
  kill PID of a protected process     kill of an ancestor ($$, $PPID, the claude/tern chain)
  kill -1 / pkill -u USER (no name)   systemctl stop|restart|kill of a protected unit
  hyprctl dispatch exit|killactive|closewindow|...   hyprctl kill
  loginctl terminate-*|kill-*         reboot / poweroff / shutdown / systemctl reboot

Protected names: tern, tmux, Hyprland, waybar, noctalia, quickshell/qs, firefox, zen,
omp, claude, kitty, alacritty (override with Z0_GUARD_PROTECTED, comma-separated).
Commands inside `ssh HOST '...'`, `bash -c '...'`, `sudo`, `env`, `timeout` etc. are
checked too.

Explicit allow (owner only): launch the session with Z0_GUARD_ALLOW_KILL=1, or touch
~/.config/z0-guard/allow-kill (valid for 15 minutes after its mtime). Commands that
mention that allow file are themselves denied, so the agent cannot allow itself.

Every deny appends a receipt to $XDG_STATE_HOME/z0-guard/pane-guard.jsonl.
A crash in this file allows the command (and logs the error to stderr).

  pane-guard.py --check 'COMMAND'   dry run: print the verdict, exit 2 when denied
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

DEFAULT_PROTECTED = ("tern", "tmux", "hyprland", "waybar", "noctalia", "quickshell", "qs",
                     "firefox", "zen", "zen-bin", "zen-browser", "omp", "claude", "kitty",
                     "alacritty")
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "z0-guard"
ALLOW_FILE = Path(os.environ.get("Z0_GUARD_CONFIG") or Path.home() / ".config/z0-guard") / "allow-kill"
ALLOW_TTL = 15 * 60
OPERATORS = {";", "&&", "||", "|", "&", "|&", "\n", "(", ")", "{", "}", "!", "then", "do",
             "else", "elif"}
WRAPPERS = {"sudo", "doas", "env", "command", "exec", "nohup", "nice", "ionice", "setsid",
            "stdbuf", "time", "builtin", "xargs", "flock", "systemd-run", "unbuffer"}
HYPR_KILL = {"exit", "killactive", "forcekillactive", "closewindow", "killwindow",
             "forcekillwindow", "forcerendererreload"}
POWER = {"reboot", "poweroff", "halt", "shutdown", "kexec", "soft-reboot"}


def protected_names() -> tuple[str, ...]:
    raw = os.environ.get("Z0_GUARD_PROTECTED")
    names = [n.strip().lower() for n in raw.split(",")] if raw else list(DEFAULT_PROTECTED)
    return tuple(n for n in names if n)


def name_re():
    alts = "|".join(re.escape(n) for n in sorted(protected_names(), key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])({alts})(?![\w.-])", re.I)


def is_protected_name(name: str) -> bool:
    base = os.path.basename(name.strip().strip("'\"")).lower()
    return base in protected_names() or bool(name_re().search(base))


# ---- process facts ---------------------------------------------------------------

def proc_info(pid: int):
    try:
        comm = Path(f"/proc/{pid}/comm").read_text().strip()
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            errors="replace").strip()
        ppid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        return comm, argv, ppid
    except (OSError, ValueError, IndexError):
        return None


def ancestor_pids() -> set[int]:
    pids, pid = set(), os.getppid()
    for _ in range(64):
        info = proc_info(pid)
        if info is None:
            break
        pids.add(pid)
        if info[2] <= 1:
            break
        pid = info[2]
    return pids


def pid_problem(pid: int, ancestors: set[int]) -> str | None:
    if pid in ancestors:
        return f"pid {pid} is an ancestor of this agent session (its own pane/process chain)"
    info = proc_info(pid)
    if info is None:
        return None
    comm, argv, _ = info
    if is_protected_name(comm) or is_protected_name(argv.split(" ", 1)[0]):
        return f"pid {pid} is a protected process ({comm})"
    return None


def pgrep(args: list[str]) -> list[int]:
    try:
        out = subprocess.run(["pgrep", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(x) for x in out.stdout.split() if x.isdigit() and int(x) != os.getpid()]


# ---- command parsing -----------------------------------------------------------

def tokenize(cmd: str) -> list[str] | None:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        return None


def segments(tokens: list[str]):
    seg: list[str] = []
    for t in tokens:
        if t in OPERATORS or set(t) <= set(";&|()"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def strip_wrappers(seg: list[str]) -> list[str]:
    i = 0
    while i < len(seg):
        t = seg[i]
        base = os.path.basename(t)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
        elif base in WRAPPERS:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1 + (seg[i] in ("-u", "-g", "-n", "-c", "-w", "-E", "-I", "-p", "-s"))
            if base == "flock" and i < len(seg):
                i += 1  # the lock file
        elif base == "timeout":
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1 + (seg[i] in ("-s", "-k", "--signal", "--kill-after"))
            i += 1  # duration
        else:
            break
    return seg[i:]


def check_segment(seg: list[str], ancestors: set[int], remote: bool, depth: int) -> list[str]:
    seg = strip_wrappers(seg)
    if not seg:
        return []
    cmd, args = os.path.basename(seg[0]), seg[1:]
    hits: list[str] = []
    # nested shells and remote commands: check the inner command text too
    if cmd in ("bash", "sh", "zsh", "fish", "dash") and "-c" in args:
        i = args.index("-c")
        if i + 1 < len(args):
            hits += check_command(args[i + 1], ancestors, remote, depth + 1)
        return hits
    if cmd in ("ssh", "mosh") or (cmd == "tern" and args[:1] == ["ssh"]):
        rest = args[1:] if cmd == "tern" else args
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            j += 1 + (len(rest[j]) == 2 and rest[j][1] in "bcDEeFIiJLlmOopQRSWw")
        inner = rest[j + 1:]
        if inner:
            hits += check_command(" ".join(inner), ancestors, True, depth + 1)
        return hits
    if cmd == "tern" and args and args[0] in ("kill", "close"):
        return [f"`tern {args[0]}` ends tern panes/sessions"]
    if cmd == "tmux" and any(a.startswith("kill-") for a in args):
        verb = next(a for a in args if a.startswith("kill-"))
        return [f"`tmux {verb}` ends tmux sessions/panes"]
    if cmd in POWER or (cmd == "systemctl" and any(a in POWER for a in args)):
        return [f"`{' '.join(seg[:3])}` ends every pane and session"]
    if cmd == "systemctl" and any(a in ("stop", "restart", "kill", "try-restart",
                                          "reload-or-restart", "isolate") for a in args):
        units = [a for a in args if not a.startswith("-") and a not in (
            "stop", "restart", "kill", "try-restart", "reload-or-restart", "isolate")]
        bad = [u for u in units if is_protected_name(re.sub(r"[@.].*$", "", u))
               or name_re().search(u)]
        if bad:
            return [f"`systemctl` would stop protected unit(s): {', '.join(bad)}"]
    if cmd == "hyprctl":
        if "kill" in args or (args[:1] == ["dispatch"] and len(args) > 1 and args[1] in HYPR_KILL):
            return [f"`hyprctl {' '.join(args[:2])}` closes owner windows or the desktop"]
    if cmd == "loginctl" and any(a.startswith(("terminate-", "kill-")) for a in args):
        return ["`loginctl` would end the owner's login session"]
    if cmd in ("pkill", "killall", "pgrep-kill"):
        return check_pkill(cmd, args, ancestors, remote)
    if cmd == "kill":
        return check_kill(args, ancestors, remote)
    return hits


def check_pkill(cmd: str, args: list[str], ancestors: set[int], remote: bool) -> list[str]:
    full = "-f" in args or "--full" in args or any(re.match(r"^-[a-zA-Z]*f", a) for a in args
                                                    if not a.startswith("--"))
    takes_value = {"-u", "-U", "-g", "-G", "-P", "-s", "-t", "--signal", "-F", "--pidfile",
                   "--ns", "--nslist", "-o", "-y", "--older-than", "--younger-than"}
    patterns, users, i = [], False, 0
    while i < len(args):
        a = args[i]
        if a in ("-u", "-U", "--user", "--euid", "--uid"):
            users = True
        if a in takes_value:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        patterns.append(a)
        i += 1
    if not patterns:
        return [f"`{cmd}` without a process name would kill every process of the user"] if users \
            else []
    hits = []
    for pat in patterns:
        if name_re().search(pat):
            hits.append(f"`{cmd}` pattern {pat!r} names a protected process")
            continue
        if remote:
            continue
        if cmd == "killall":
            continue
        pids = pgrep((["-f"] if full else []) + [pat])
        for pid in pids:
            why = pid_problem(pid, ancestors)
            if why:
                hits.append(f"`{cmd}` pattern {pat!r} matches {why}")
                break
    return hits


def check_kill(args: list[str], ancestors: set[int], remote: bool) -> list[str]:
    hits, targets, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a in ("-s", "-n", "--signal"):
            i += 2
            continue
        if a == "--":
            targets += args[i + 1:]
            break
        if a in ("-l", "-L", "--list"):
            return []
        if a.startswith("-") and not re.fullmatch(r"-\d+", a):
            i += 1
            continue
        if re.fullmatch(r"-\d+", a) and not targets and i + 1 < len(args):
            i += 1  # numeric signal, e.g. kill -9 PID
            continue
        targets.append(a)
        i += 1
    for t in targets:
        if t in ("-1", "-0", "0"):
            hits.append(f"`kill {t}` signals every process of the user/process group")
        elif t in ("$$", "$PPID", "${PPID}", "$BASHPID") or "$(pgrep" in t or "`pgrep" in t:
            hits.append(f"`kill {t}` targets this session's own process chain")
        elif re.fullmatch(r"\d+", t) and not remote:
            why = pid_problem(int(t), ancestors)
            if why:
                hits.append(f"`kill {t}`: {why}")
    return hits


HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(cmd: str) -> str:
    """Drop here-document bodies: they are data (file contents, prompts), not commands."""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            while i < len(lines) and lines[i].strip() != m.group(2):
                i += 1
            if i < len(lines):
                i += 1
    return "\n".join(out)


WRITERS = {"touch", "cp", "mv", "ln", "install", "tee", "chmod", "rm", "python", "python3",
           "perl", "sed", "dd", "rsync", "printf", "echo"}


def writes_allow_file(seg: list[str]) -> bool:
    """A segment that names the allow file and writes something (writer command or redirect)."""
    if not any(ALLOW_FILE.name in t and ("z0-guard" in t or ALLOW_FILE.parent.name in t)
               for t in seg):
        return False
    core = strip_wrappers(seg)
    return bool(core) and (os.path.basename(core[0]) in WRITERS or ">" in seg or ">>" in seg)


def check_command(cmd: str, ancestors: set[int], remote: bool = False, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    hits: list[str] = []
    cmd = strip_heredocs(cmd)
    # $(...) and backticks: check the inner command text as well
    for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", cmd):
        text = inner[0] or inner[1]
        if text:
            hits += check_command(text, ancestors, remote, depth + 1)
    tokens = tokenize(cmd)
    if tokens is None:  # unbalanced quotes: fall back to a conservative text scan
        if re.search(r"\b(tern\s+(kill|close)|tmux\s+kill-|pkill|killall|hyprctl\s+(kill|dispatch\s+exit))",
                     cmd):
            hits.append("unparseable command that looks like it kills panes or processes")
        if ALLOW_FILE.name in cmd and "z0-guard" in cmd:
            hits.append("only the owner may create or change the z0-guard allow-kill file")
        return hits
    pipeline_kills = []
    for seg in segments(tokens):
        if writes_allow_file(seg):
            hits.append("only the owner may create or change the z0-guard allow-kill file")
        hits += check_segment(seg, ancestors, remote, depth)
        core = strip_wrappers(seg)
        if core:
            pipeline_kills.append(os.path.basename(core[0]))
    # `pgrep omp | xargs kill`, `pidof waybar | xargs kill -9`
    if any(c in ("pgrep", "pidof") for c in pipeline_kills) and "kill" in pipeline_kills:
        for seg in segments(tokens):
            core = strip_wrappers(seg)
            if core and os.path.basename(core[0]) in ("pgrep", "pidof"):
                for a in core[1:]:
                    if not a.startswith("-") and name_re().search(a):
                        hits.append(f"`{core[0]} {a} | ... kill` targets a protected process")
    return hits


# ---- allow + io ------------------------------------------------------------------

def allowed() -> str | None:
    if os.environ.get("Z0_GUARD_ALLOW_KILL") == "1":
        return "Z0_GUARD_ALLOW_KILL=1"
    try:
        age = time.time() - ALLOW_FILE.stat().st_mtime
    except OSError:
        return None
    return f"{ALLOW_FILE} ({int(age)}s old)" if 0 <= age <= ALLOW_TTL else None


def decide(command: str) -> tuple[bool, list[str], str | None]:
    hits = list(dict.fromkeys(check_command(command, ancestor_pids())))
    if not hits:
        return False, [], None
    if any("allow-kill file" in h for h in hits):
        return True, hits, None
    allow = allowed()
    return allow is None, hits, allow


def receipt(event: dict, command: str, hits: list[str], denied: bool, allow) -> None:
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with open(STATE / "pane-guard.jsonl", "a") as fh:
            fh.write(json.dumps({
                "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "session": event.get("session_id"), "cwd": event.get("cwd"),
                "decision": "deny" if denied else "allow-override", "allow": allow,
                "command": command[:500], "why": hits}) + "\n")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--check":
        denied, hits, allow = decide(" ".join(argv[1:]))
        print(json.dumps({"deny": denied, "why": hits, "allow": allow}))
        return 2 if denied else 0
    event = json.loads(sys.stdin.read() or "{}")
    if event.get("tool_name") != "Bash":
        return 0
    command = str((event.get("tool_input") or {}).get("command") or "")
    denied, hits, allow = decide(command)
    if not hits:
        return 0
    receipt(event, command, hits, denied, allow)
    if not denied:
        return 0
    reason = ("z0 pane guard: blocked because " + "; ".join(hits) + ". Never kill the owner's "
              "tern panes, tmux sessions or desktop programs. If this really is needed, ask "
              "the owner; only the owner can allow it (Z0_GUARD_ALLOW_KILL=1 at launch, or "
              "`touch ~/.config/z0-guard/allow-kill` for 15 minutes).")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # a broken guard must not wedge the session
        print(f"pane-guard error (command allowed): {exc}", file=sys.stderr)
        sys.exit(0)
