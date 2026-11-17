#!/usr/bin/env python3
"""Run one public upstream suite at one commit on a fleet node, resumably.

Shipped into the job's source stage by `fleet-backfill`. Every stage writes an
atomic `.backfill/<stage>.json` marker, so a Kueue-preempted bench job resumes
where it stopped instead of rerunning finished slices. The last stdout line is
`BACKFILL_RESULT <json>`; exit 0 means the suite ran (test failures are data),
non-zero means the environment could not run it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(".backfill")
COUNTS = re.compile(r"(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed)")


def done(stage):
    path = STATE / f"{stage}.json"
    return json.loads(path.read_text()) if path.exists() else None


def mark(stage, record):
    tmp = STATE / f".{stage}.tmp"
    tmp.write_text(json.dumps(record))
    tmp.replace(STATE / f"{stage}.json")
    print(f"backfill: {stage} {json.dumps(record)[:400]}", flush=True)
    return record


def run(cmd, log, env=None, timeout=None):
    t0 = time.time()
    with open(STATE / log, "w") as out:
        try:
            rc = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, env=env, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    return rc, round(time.time() - t0, 1)


def tail(log, n=40):
    return (STATE / log).read_text(errors="replace").splitlines()[-n:]


def uv():
    found = shutil.which("uv") or next((p for p in (Path.home() / ".local/bin/uv",) if p.exists()), None)
    if found:
        return str(found)
    subprocess.run(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    found = Path.home() / ".local/bin/uv"
    return str(found) if found.exists() else None


def pytest_slices(cfg, jobs):
    """hermes-agent style: canonical scripts/run_tests.sh, one --slice per stage."""
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(Path(".backfill/venv").resolve()),
           "GIT_AUTHOR_NAME": "backfill", "GIT_AUTHOR_EMAIL": "backfill@example.invalid",
           "GIT_COMMITTER_NAME": "backfill", "GIT_COMMITTER_EMAIL": "backfill@example.invalid"}
    if not done("sync"):
        tool = uv()
        if not tool:
            return mark("sync", {"rc": 127, "error": "no uv"})
        rc = 1
        for extra in cfg.get("sync_variants", [[]]):
            rc, secs = run([tool, "sync", "-q", "--frozen", "--python", cfg.get("python", "3.12"), *extra],
                           "sync.log", env)
            if rc == 0:
                break
        if rc:
            return mark("sync", {"rc": rc, "tail": tail("sync.log", 5)})
        mark("sync", {"rc": 0})
    if done("sync")["rc"]:
        return done("sync")
    env["HERMES_PYTHON"] = str(Path(".backfill/venv/bin/python").resolve())
    total = cfg.get("slices", 8)
    for index in cfg.get("only") or range(1, total + 1):
        stage = f"slice-{index}"
        if done(stage):
            continue
        rc, secs = run(["bash", cfg.get("runner", "scripts/run_tests.sh"), "-j", str(jobs),
                        "--slice", f"{index}/{total}"], stage + ".log", env, cfg.get("slice_timeout", 3600))
        lines = tail(stage + ".log", 400)
        counts = {}
        for line in reversed(lines):
            found = COUNTS.findall(line)
            if found:
                counts = {k.rstrip("s") if k.startswith("error") else k: int(v) for v, k in found}
                break
        failed = sorted({l.split()[1] for l in lines if l.startswith(("FAILED ", "ERROR ")) and len(l.split()) > 1})
        mark(stage, {"rc": rc, "seconds": secs, "counts": counts, "failed": failed[:200]})
    return {"rc": 0}


def cmake_ctest(cfg, jobs):
    """llama.cpp style: configure, build, ctest; the build dir carries the checkpoint."""
    steps = [("configure", ["cmake", "-B", "build", *cfg.get("configure", [])]),
             ("build", ["cmake", "--build", "build", "-j", str(jobs), *cfg.get("build", [])]),
             ("ctest", ["ctest", "--test-dir", "build", "-j", str(jobs), "--output-on-failure",
                        *cfg.get("ctest", [])])]
    for stage, cmd in steps:
        if done(stage):
            continue
        rc, secs = run(cmd, stage + ".log", timeout=cfg.get("stage_timeout", 5400))
        lines = tail(stage + ".log", 200)
        record = {"rc": rc, "seconds": secs}
        if stage == "ctest":
            record["summary"] = next((l for l in reversed(lines) if "tests passed" in l), "")
            record["failed"] = [l.strip() for l in lines if re.search(r"\(Failed|\(SEGFAULT|\(Timeout", l)][:100]
        elif rc:
            record["tail"] = lines[-15:]
        mark(stage, record)
        if rc and stage != "ctest":
            return {"rc": rc}
    return {"rc": 0}


KINDS = {"pytest-slices": pytest_slices, "cmake-ctest": cmake_ctest}


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    STATE.mkdir(exist_ok=True)
    jobs = int(os.environ.get("BACKFILL_JOBS") or cfg.get("jobs") or os.cpu_count() or 2)
    outcome = KINDS[cfg["kind"]](cfg, jobs)
    stages = {p.stem: json.loads(p.read_text()) for p in sorted(STATE.glob("*.json"))}
    result = {"suite": cfg["name"], "head": cfg.get("head"), "host": os.uname().nodename,
              "cpus": os.cpu_count(), "rc": outcome.get("rc", 1), "stages": stages}
    print("BACKFILL_RESULT " + json.dumps(result), flush=True)
    return 0 if result["rc"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
