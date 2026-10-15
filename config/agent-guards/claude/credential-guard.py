#!/usr/bin/env python3
"""Text-only credential policy. Never execute input or open credential files."""

import fnmatch
import io
import json
import os
import re
import shlex
import sys


DENIED = frozenset("pass-cli proton-pass secret-tool gnome-keyring-daemon gnome-keyring seahorse kwallet-query kwalletcli lssecret keyring bws bw op gopass pass".split())
ROOTS = (
    "~/.local/share/proton-pass*", "~/.config/proton-pass*", "~/.cache/proton-pass*",
    "~/.local/share/keyrings", "~/.gnupg", "~/.password-store",
    "~/.local/share/passd", "/var/lib/passd",
)
SHELLS = frozenset("bash sh zsh fish dash ksh".split())
READERS = frozenset("cat less more head tail cp mv tar rsync grep rg find sqlite3 strings xxd od sed awk dd tee install".split())
EXEC_RE = re.compile(r"subprocess|exec|spawn|system|os\.popen|Bun\.\$|terminal\s*\(", re.I)
TOKEN_RE = re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, DENIED)) + r")(?![\w-])")
ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=(.*)$", re.S)
DENY_TOOL = "Direct credential tool invocation is blocked; request a passd capability."
DENY_PATH = "Credential store access is blocked; request a passd capability."
DENY_ENV = "Environment dumps are blocked."


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def expand_home(path):
    # Only expand HOME, never arbitrary environment variables or shell code.
    return os.path.expanduser(path.replace("${HOME}", os.path.expanduser("~")).replace("$HOME", os.path.expanduser("~")))


def protected(path, cwd=None):
    if not isinstance(path, str) or not path:
        return False
    path = expand_home(path)
    if not os.path.isabs(path):
        path = os.path.join(expand_home(cwd or os.getcwd()), path)
    candidates = (os.path.normpath(path), os.path.realpath(path))
    for candidate in candidates:
        if re.match(r"^/proc/[^/]+/environ(?:/|$)", candidate):
            return True
        for root in ROOTS:
            root = expand_home(root)
            for base in (os.path.normpath(root), os.path.realpath(root)):
                if fnmatch.fnmatchcase(candidate, base) or fnmatch.fnmatchcase(candidate, base + "/*"):
                    return True
    return False


def protected_text(text, cwd=None):
    # Extract literal paths from code/MCP arguments without evaluating them.
    return any(protected(match.group(), cwd) for match in re.finditer(
        r"(?:\$\{HOME\}|\$HOME|~|/)[^\s\"'`;|<>()\[\]{},]*", text))


def tool_name(word):
    return os.path.basename(word.rstrip("/"))


def code_reason(code, cwd=None):
    literals = (match.group(2) for match in re.finditer(r"(['\"])(.*?)\1", code, re.S))
    if protected_text(code, cwd) or any(protected(value, cwd) for value in literals):
        return DENY_PATH
    if re.search(r"\bos\.environ\b|\bprocess\.env\b|\bENV\b", code):
        return DENY_ENV
    if EXEC_RE.search(code) and TOKEN_RE.search(code):
        return DENY_TOOL
    if EXEC_RE.search(code) and re.search(r"['\"](?:env|printenv)(?:\s|['\"])", code):
        return DENY_ENV
    # Direct keyring module access does not need a child process.
    if re.search(r"(?:import\s+keyring|from\s+keyring\s+import|__import__\(['\"]keyring)", code):
        return DENY_TOOL
    return None


def substitutions(command):
    # Best effort, including nested substitutions. No shell is ever invoked.
    for match in re.finditer(r"`([^`]*)`", command, re.S):
        yield match.group(1)
    for match in re.finditer(r"\$\(", command):
        start = match.end()
        depth = 1
        for i in range(start, len(command)):
            if command[i] == "(":
                depth += 1
            elif command[i] == ")":
                depth -= 1
                if depth == 0:
                    yield command[start:i]
                    break


def simple_reason(words, cwd, depth):
    while words:
        assignment = ASSIGN_RE.match(words[0])
        if assignment:
            if tool_name(assignment.group(1)) in DENIED:
                return DENY_TOOL
            words = words[1:]
            continue
        name, args = tool_name(words[0]), words[1:]
        if name in {"if", "then", "elif", "else", "while", "until", "do", "!", "time", "{"}:
            words = args
            continue
        if name in DENIED:
            return DENY_TOOL
        if name in {"env", "printenv"}:
            if name == "printenv":
                # Even named-variable queries can disclose credentials.
                return DENY_ENV
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--split-string="):
                    return bash_reason(shlex.join(shlex.split(arg.split("=", 1)[1]) + args[i + 1:]), cwd, depth + 1)
                if arg.startswith("--chdir="):
                    cwd = os.path.join(cwd, expand_home(arg.split("=", 1)[1]))
                if arg in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}:
                    if i + 1 >= len(args):
                        return DENY_ENV
                    if arg in {"-C", "--chdir"}:
                        cwd = os.path.join(cwd, expand_home(args[i + 1]))
                    if arg in {"-S", "--split-string"}:
                        return bash_reason(shlex.join(shlex.split(args[i + 1]) + args[i + 2:]), cwd, depth + 1)
                    i += 2
                elif arg.startswith("-") or ASSIGN_RE.match(arg):
                    assignment = ASSIGN_RE.match(arg)
                    if assignment and tool_name(assignment.group(1)) in DENIED:
                        return DENY_TOOL
                    i += 1
                else:
                    break
            words = args[i:]
            if not words:
                return DENY_ENV
            continue
        if name in {"sudo", "doas", "nohup", "command", "builtin", "exec", "xargs", "timeout"}:
            i = 0
            value_options = {
                "sudo": {"-u", "-g", "-h", "-p", "-C", "-T", "--user", "--group", "--host", "--prompt", "--chdir", "-D"},
                "doas": {"-u", "-C"}, "exec": {"-a"},
                "xargs": {"-I", "-n", "-s", "-P", "-L", "-E", "-d", "--max-args", "--replace", "--delimiter"},
                "timeout": {"-s", "-k", "--signal", "--kill-after"},
            }.get(name, set())
            while i < len(args) and args[i].startswith("-"):
                i += 2 if args[i] in value_options else 1
            if name == "timeout" and i < len(args):
                i += 1
            words = args[i:]
            continue
        if name == "eval":
            return bash_reason(" ".join(args), cwd, depth + 1)
        if name in SHELLS:
            for i, arg in enumerate(args):
                if arg.startswith("-") and "c" in arg and i + 1 < len(args):
                    return bash_reason(args[i + 1], cwd, depth + 1)
            # Here strings and here docs are treated as shell source.
            if any(arg in {"<<<", "<<", "<<-"} for arg in args):
                i = next(i for i, arg in enumerate(args) if arg in {"<<<", "<<", "<<-"})
                return bash_reason(" ".join(args[i + 1:]), cwd, depth + 1)
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?|node|perl|ruby|deno|bun", name):
            if name.startswith("python") and "-m" in args and "keyring" in args:
                return DENY_TOOL
            for i, arg in enumerate(args):
                if arg in {"-c", "-e", "--eval", "eval"} and i + 1 < len(args):
                    reason = code_reason(args[i + 1], cwd)
                    if reason:
                        return reason
        if name == "set" and (not args or args == ["-o"]):
            return DENY_ENV
        if name == "export" and (not args or "-p" in args):
            return DENY_ENV
        if name in {"declare", "typeset"} and any(arg.startswith("-") and ("x" in arg or "p" in arg) for arg in args):
            return DENY_ENV
        if name == "man" and any(tool_name(arg) in DENIED for arg in args):
            return DENY_TOOL
        if name in {"export", "declare", "typeset", "alias"} and any(
            (match := ASSIGN_RE.match(arg)) and tool_name(match.group(1)) in DENIED for arg in args
        ):
            return DENY_TOOL
        if name in READERS and any(protected(arg.split("=", 1)[-1], cwd) for arg in args if not arg.startswith("-") or "=" in arg):
            return DENY_PATH
        return None
    return None


def bash_reason(command, cwd=None, depth=0):
    if depth > 16:
        return "Shell nesting exceeds credential guard inspection limit."
    cwd = cwd or os.getcwd()
    command = command.replace("\\\n", "")
    for source in substitutions(command):
        reason = bash_reason(source, cwd, depth + 1)
        if reason:
            return reason
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.wordchars += "\n"  # Newlines are converted below; quoted ones stay inside words.
    lexer.whitespace += "\n"
    # Insert semicolons for unquoted newlines using a quote-aware pass.
    quote = None
    escaped = False
    chars = []
    for char in command:
        if not escaped and char in "\"'":
            quote = None if quote == char else char if quote is None else quote
        chars.append(";" if char == "\n" and quote is None else char)
        escaped = char == "\\" and not escaped
    lexer.instream = io.StringIO("".join(chars))
    try:
        tokens = list(lexer)
    except ValueError:
        return DENY_TOOL if TOKEN_RE.search(command.replace("\\", "")) else None
    segments, segment = [], []
    for token in tokens:
        if token and all(c in ";&|()" for c in token):
            segments.append((segment, token))
            segment = []
        else:
            segment.append(token)
    segments.append((segment, ""))
    piped = False
    for words, separator in segments:
        if piped and words:
            # Opaque stdin code, including decoded content, cannot be inspected.
            unwrapped = [w for w in words if not ASSIGN_RE.match(w)]
            if any(tool_name(w) in SHELLS for w in unwrapped):
                return "Piped shell source is blocked by the credential guard."
        reason = simple_reason(words, cwd, depth)
        if reason:
            return reason
        # Inspect redirection targets even for otherwise benign commands.
        for i, word in enumerate(words[:-1]):
            if word and all(c in "<>" for c in word) and protected(words[i + 1], cwd):
                return DENY_PATH
        if words and tool_name(words[0]) == "cd" and len(words) > 1:
            cwd = os.path.normpath(os.path.join(cwd, expand_home(words[1])))
        piped = separator in {"|", "|&"}
    return None


def check(tool, args, cwd=None):
    """Return a fixed public denial reason or None. Also used by adapters."""
    if not isinstance(args, dict):
        return DENY_TOOL if tool.lower() in {"bash", "terminal"} and TOKEN_RE.search(str(args)) else None
    name = tool.lower()
    base = cwd if isinstance(cwd, str) else os.getcwd()
    override = args.get("cwd", args.get("workdir"))
    cwd = os.path.abspath(os.path.join(expand_home(base), expand_home(override))) if isinstance(override, str) else base
    if name in {"bash", "terminal"}:
        command = args.get("command")
        if not isinstance(command, str):
            return DENY_TOOL if any(TOKEN_RE.search(value) for value in strings(args)) else None
        return bash_reason(command, cwd)
    if name in {"eval", "execute_code"}:
        return next((reason for value in strings(args) if (reason := code_reason(value, cwd))), None)
    if name in {"read", "grep", "glob", "edit", "write", "notebookedit", "read_file", "write_file", "search_files", "patch"}:
        for key in ("file_path", "path", "paths", "pattern", "notebook_path", "file_glob", "target_file"):
            if any(protected(value, cwd) for value in strings(args.get(key))):
                return DENY_PATH
        if name == "patch" and isinstance(args.get("patch"), str):
            for path in re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", args["patch"], re.M):
                if any(protected(value, cwd) for value in path if value):
                    return DENY_PATH
    if name.startswith("mcp__"):
        for value in strings(args):
            if protected_text(value, cwd):
                return DENY_PATH
            if TOKEN_RE.search(value) or code_reason(value, cwd) or bash_reason(value, cwd):
                return DENY_TOOL
    return None


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        reason = check(str(data.get("tool_name", "")), data.get("tool_input", {}), data.get("cwd"))
    except (ValueError, TypeError, OSError, RecursionError):
        # Malformed Bash envelopes with a denied token fail closed, without echoing input.
        reason = DENY_TOOL if re.search(r"\b(?:Bash|bash|terminal)\b", raw) and TOKEN_RE.search(raw.replace("\\", "")) else None
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
