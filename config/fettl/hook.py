#!/usr/bin/env python3
"""Read-only, network-isolated Fettl hook runner; no repair command is accepted."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "hooks.json").read_text())
HOME = Path.home()
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "fettl-hooks"
STATE = HOME / ".config/fettl/hooks-state.json"
MAX_INPUT = 1024 * 1024


def limits() -> None:
    os.nice(19)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    cpu = POLICY["cpu_seconds"]
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    memory = POLICY["memory_bytes"]
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))


def read_input() -> dict:
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("hook payload exceeds 1 MiB")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("hook payload must be an object")
    return value


def required_text(value: dict, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"missing non-empty {key}")
    return item


def run_scanner(args: list[str], payload: bytes | None, cwd: Path) -> tuple[int, bytes, bytes]:
    state = json.loads(STATE.read_text())
    binary = state["executable"]
    scanner = [state["ionice"], "-c", "3", binary]
    repository = subprocess.run(
        ["/usr/bin/git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True, timeout=3, check=False,
    )
    if repository.returncode:
        raise ValueError("Fettl hooks require a git worktree")
    root = Path(os.fsdecode(repository.stdout).strip()).resolve()
    key = hashlib.sha256(os.fsencode(root)).hexdigest()[:24]
    store = CACHE / "repositories" / key
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (CACHE / "scanner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another local Fettl hook is running; this event was not checked") from exc
        env = {
            "HOME": str(HOME), "USER": os.environ.get("USER", ""),
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
            "XDG_CACHE_HOME": str(CACHE / "runtime"),
            "XDG_RUNTIME_DIR": str(CACHE / "run"), "TMPDIR": str(CACHE / "tmp"),
        }
        # Only cache is writable. Hide host sockets in /run and /tmp and give the
        # scanner a private network/PID namespace. Never fall back without bwrap.
        sandbox = [
            state["bwrap"], "--die-with-parent", "--new-session", "--unshare-net",
            "--unshare-pid", "--unshare-ipc", "--ro-bind", "/", "/",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/tmp",
            "--ro-bind", str(root), str(root), "--bind", str(CACHE), str(CACHE),
            "--chdir", str(cwd),
        ]
        # Initialization and checking share the same per-repository external store.
        if not (store / "store.redb").exists():
            initialized = subprocess.run(
                sandbox + scanner + ["local-store", "init", "--root", str(store)],
                env=env, capture_output=True, timeout=10, preexec_fn=limits, check=False,
            )
            if initialized.returncode:
                raise ValueError("Fettl repository local-store initialization failed")
        command = sandbox + scanner + ["--timeout", str(POLICY["wall_seconds"] - 2),
                                      "--cache-dir", str(store), *args]
        # A regular file bounds output independently of subprocess pipe buffering.
        import tempfile
        with tempfile.TemporaryFile(dir=CACHE / "tmp") as out, tempfile.TemporaryFile(dir=CACHE / "tmp") as err:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                    env=env, start_new_session=True, preexec_fn=limits)
            try:
                proc.communicate(input=payload, timeout=POLICY["wall_seconds"])
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                raise ValueError("Fettl hook exceeded its wall-time limit") from None
            cap = POLICY["output_bytes"]
            out.seek(0)
            stdout = out.read(cap + 1)
            err.seek(0)
            stderr = err.read(cap + 1)
            if len(stdout) > cap or len(stderr) > cap:
                raise ValueError("Fettl hook output exceeded its protocol limit")
            return proc.returncode, stdout, stderr


def hermes_payload(event: dict) -> dict:
    if event.get("hook_event_name") != "post_tool_call":
        raise ValueError("expected Hermes post_tool_call event")
    session = required_text(event, "session_id")
    tool = required_text(event, "tool_name")
    extra = event.get("extra")
    if not isinstance(extra, dict):
        raise ValueError("missing Hermes extra outcome object")
    call = required_text(extra, "tool_call_id")
    status = extra.get("status")
    if status not in {"ok", "error", "blocked", "cancelled", "timeout"}:
        raise ValueError("missing or unknown Hermes terminal status")
    success = status == "ok" and not extra.get("error_type") and not extra.get("error_message")
    args = event.get("tool_input")
    if not isinstance(args, dict):
        raise ValueError("missing Hermes tool_input object")
    result = extra.get("result")
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, dict):
        raise ValueError("missing Hermes file-tool result object")
    success = success and not bool(result.get("error"))
    # Persist only call identity -> monotonic sequence, never raw input/output.
    # Replayed tool calls reuse their sequence; simultaneous callbacks serialize.
    sequence_path = CACHE / "sequences.json"
    with (CACHE / "sequences.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sequences = json.loads(sequence_path.read_text()) if sequence_path.exists() else {}
        identity = hashlib.sha256((session + "\0" + call).encode()).hexdigest()
        counter = sequences.setdefault(hashlib.sha256(session.encode()).hexdigest(), {"next": 1, "calls": {}})
        if identity not in counter["calls"]:
            counter["calls"][identity] = counter["next"]
            counter["next"] += 1
            temporary = sequence_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(sequences))
            temporary.chmod(0o600)
            temporary.replace(sequence_path)
        sequence = counter["calls"][identity]
    return {"schema_version": 1, "session_id": session, "sequence": sequence,
            "tool": tool, "success": success, "tool_input": args,
            "tool_result": result, "cwd": required_text(event, "cwd")}


def hermes_directories(payload: dict) -> list[Path]:
    result = payload["tool_result"]
    paths = result.get("files_modified") or [result.get("resolved_path") or payload["tool_input"].get("path")]
    if not payload["success"]:
        return [Path(payload["cwd"]).resolve()]
    if not isinstance(paths, list) or not paths:
        raise ValueError("successful Hermes mutation did not report affected paths")
    directories = set()
    for raw_path in paths:
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ValueError("Hermes affected path is not absolute; refusing to scan the gateway's unrelated cwd")
        directory = Path(raw_path).parent
        while not directory.is_dir() and directory != directory.parent:
            directory = directory.parent
        directories.add(directory.resolve())
    return sorted(directories)


def main() -> int:
    os.umask(0o077)
    mode = sys.argv[1:]
    if len(mode) == 2 and mode[0] == "claude" and mode[1] in {"pre-tool", "post-tool", "stop"}:
        raw = read_input()
        code, stdout, stderr = run_scanner(["hook", "claude", mode[1]], json.dumps(raw).encode(), Path(raw.get("cwd") or os.getcwd()).resolve())
        # Native Claude response/exit status is preserved byte-for-byte.
        sys.stdout.buffer.write(stdout)
        sys.stderr.buffer.write(stderr)
        return code
    if mode == ["hermes"]:
        event = read_input()
        payload = hermes_payload(event)
        responses = []
        for directory in hermes_directories(payload):
            canonical = {**payload, "cwd": str(directory)}
            code, stdout, stderr = run_scanner(["hook", "hermes", "post-tool-call"], json.dumps(canonical).encode(), directory)
            sys.stderr.buffer.write(stderr)
            if code not in {0, 1}:
                raise ValueError(f"Fettl Hermes hook failed with exit {code}")
            response = json.loads(stdout) if stdout.strip() else {}
            if response:
                responses.append(response)
        # Post-tool observers cannot prevent an already completed mutation.
        if responses:
            print(json.dumps({"context": "Fettl local post-action review (no fixes applied): " + json.dumps(responses, separators=(",", ":"))}))
        return 0
    if mode == ["omp"]:
        code, stdout, stderr = run_scanner(
            ["check", "--full", "--format", "text", "--display", "summary", "--privacy-mode", POLICY["privacy_mode"]],
            None, Path.cwd().resolve(),
        )
        sys.stdout.buffer.write(stdout)
        sys.stderr.buffer.write(stderr)
        return code
    raise ValueError("only claude pre-tool/post-tool/stop, hermes, or omp checks are permitted")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Fettl hook not completed: {exc}", file=sys.stderr)
        raise SystemExit(3)
