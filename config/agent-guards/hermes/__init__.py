"""Hermes pre_tool_call veto using the shared Claude hook protocol."""
import json
from pathlib import Path
import subprocess


GUARD = Path(__file__).resolve().parents[1] / "claude" / "credential-guard.py"
BLOCK = {"action": "block", "message": "Credential access blocked; request a passd capability."}
FAILURE = {"action": "block", "message": "Credential guard unavailable; tool call blocked."}


def pre_tool_call(tool_name="", args=None, **kwargs):
    try:
        result = subprocess.run(["python3", str(GUARD)],
            input=json.dumps({"tool_name": tool_name, "tool_input": args,
                              "cwd": kwargs.get("cwd") or str(Path.cwd())}),
            text=True, capture_output=True, timeout=5, check=False)
        if result.returncode:
            return dict(FAILURE)
        if not result.stdout.strip():
            return None
        output = json.loads(result.stdout)
        if output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
            return dict(BLOCK)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        pass
    return dict(FAILURE)


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)
