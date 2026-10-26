"""Engine-choice helper: given a job class, pick the engine + the ONE existing
control-plane path, and (for the one unlocked path) build the launch argv.

This REUSES existing units -- it invents no scheduler and no transport
(spec section 3, D8). Each class maps to exactly one plane:

  build/test          -> remote-exec (ssh / tern-remote.service) to groot, -j nproc/2
  batch-inference     -> llama.cpp farm OpenAI endpoint (exllama for EXL2)   [plan only in WP1]
  fine-tune           -> unsloth uv venv on /mnt/zer0models via Kueue        [deferred: GPU not advertised]
  eval                -> lm-eval-harness against the llama-server endpoint   [plan only]
  generic-agent-task  -> Hermes kanban (codex gpt-6.1-sol), never bare codex [plan only]
  bounded-subtask     -> route_worker (z0intelligence MCP), posture-gated    [plan only]

Only build/test actually EXECS in WP1 (section 3 / R9-B). Everything else
returns a launch plan plus a one-line reason it is deferred, so the caller
(or the owner) sees the correct engine without the optimizer reaching into a
plane that is still blocked (GPU device-plugin, kueue restart-storm).

No tailnet IPs/host literals: the inference endpoint is read from the
environment (Z0_LLAMA_ENDPOINT), never embedded.
"""

from __future__ import annotations

import os

PEER_DEFAULT = os.environ.get("NETOPT_PEER_HOST", "mbp")
GROOT = os.environ.get("NETOPT_SELF_HOST", "groot")


def _nproc_half(nproc: int) -> int:
    return max(1, nproc // 2)


def plan(job_class: str, *, command: list[str] | None = None,
         target: str = GROOT, groot_nproc: int = 20) -> dict:
    """Return {engine, plane, exec (bool), argv|endpoint, reason}."""
    jc = job_class

    if jc == "build/test":
        if not command:
            return {"engine": "native-toolchain", "plane": "remote-exec",
                    "exec": False, "reason": "no command given"}
        # tern-remote.service is the remote-exec plane; ssh is its transport.
        # Cap parallelism to nproc/2 on the TARGET (groot has 20 -> 10).
        j = _nproc_half(groot_nproc)
        argv = ["ssh", "-o", "BatchMode=yes", target,
                _bash_lc(command, parallel=j)]
        return {"engine": "native-toolchain", "plane": "remote-exec",
                "exec": True, "argv": argv, "parallelism": j,
                "reason": f"route build to {target} via remote-exec (-j {j})"}

    if jc == "batch-inference":
        endpoint = os.environ.get("Z0_LLAMA_ENDPOINT", "http://127.0.0.1:11530")
        return {"engine": "llama.cpp (CUDA b11270); exllamav2 for EXL2",
                "plane": "llama-server OpenAI endpoint (farm at /workspace/z0-farm)",
                "exec": False, "endpoint": endpoint,
                "reason": "hit the running farm endpoint; --sleep-idle unloads idle weights"}

    if jc == "fine-tune":
        return {"engine": "unsloth (uv venv on /mnt/zer0models)",
                "plane": "k3s + kueue Job (GPU), groot only",
                "exec": False,
                "reason": "DEFERRED: nvidia.com/gpu not advertised + kueue restart-storm"}

    if jc == "eval":
        endpoint = os.environ.get("Z0_LLAMA_ENDPOINT", "http://127.0.0.1:11530")
        return {"engine": "lm-eval-harness (no torch; targets the API)",
                "plane": "llama-server OpenAI endpoint", "exec": False,
                "endpoint": endpoint, "reason": "cheapest high-value add; targets API not GPU"}

    if jc == "generic-agent-task":
        return {"engine": "Codex gpt-6.1-sol / gpt-6-astra",
                "plane": "Hermes kanban (hermes kanban create --provider openai-codex)",
                "exec": False,
                "reason": "offload to ChatGPT sub, no local HW cost; never bare codex exec"}

    if jc in ("bounded-subtask", "generic-subtask"):
        return {"engine": "cheap/local worker",
                "plane": "route_worker (z0intelligence MCP), posture-gated",
                "exec": False, "reason": "bounded summarize/extract/classify -> route_worker"}

    return {"engine": "unknown", "plane": None, "exec": False,
            "reason": f"no engine mapping for class '{jc}'"}


def _bash_lc(command: list[str], parallel: int) -> str:
    """Wrap the command for groot's login shell (zsh) via bash -lc, injecting a
    parallelism cap and forcing build scratch onto /mnt/zer0models (groot / is
    91% full). Idempotent, side-effect-contained."""
    import shlex
    inner = " ".join(shlex.quote(c) for c in command)
    # Expose the cap as env the build command can honour; also export a scratch
    # TMPDIR on the big disk so nothing lands on the 91%-full root.
    prelude = (f"export NETOPT_PARALLEL={parallel}; "
               f"export TMPDIR=/mnt/zer0models/.netopt-tmp; "
               f"mkdir -p \"$TMPDIR\"; "
               f"echo \"[netopt] running on $(hostname) -j {parallel}\"; ")
    return f"bash -lc {shlex.quote(prelude + inner)}"


if __name__ == "__main__":
    import json
    import sys
    cls = sys.argv[1] if len(sys.argv) > 1 else "build/test"
    cmd = sys.argv[2:] or ["echo", "hello-build"]
    print(json.dumps(plan(cls, command=cmd), indent=2))
