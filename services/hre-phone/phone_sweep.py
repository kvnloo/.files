#!/usr/bin/env python3
"""Exhaustive HRE labelling sweep: workers (one per phone SLM) claim fixed chunks of owner-msgs.jsonl
and label them through phone_label.label(). Work-stealing, so a fast phone takes more chunks.

Layout under --root (MBP ~/hre-phone, chmod 700; mounted into the k3s pods):
  owner-msgs.jsonl                  corpus (id, source, profile, ts, iso, text)
  sweep/<job>/chunks/<NNNN>.claim   claim file: "<worker> <unix ts>" (atomic O_EXCL create)
  sweep/<job>/out/<NNNN>.jsonl      labels for chunk NNNN (one row per id)
A chunk is DONE only when its out file holds a row for every id in the chunk (rows exist = done).
A claim older than --stale seconds whose out file stopped growing is taken over (resume, not redo).
Owner text goes only to --url (a phone llama-server on the tailnet)."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone_label  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True); ap.add_argument("--job", required=True)
ap.add_argument("--url", required=True); ap.add_argument("--key-file")
ap.add_argument("--mode", default="full", choices=["full", "flag", "d1"])
ap.add_argument("--model-tag", required=True); ap.add_argument("--worker", required=True)
ap.add_argument("--chunk", type=int, default=100); ap.add_argument("--stale", type=int, default=900)
ap.add_argument("--max-chars", type=int, default=6000)
ap.add_argument("--gate", choices=["none", "s22", "s25"], default="none",
                help="phone-worker's owner gate, checked over adb every --gate-every rows: "
                     "s22 = not in a call; s25 = not in a call and owner idle >= 120 s")
ap.add_argument("--gate-serial", default=""); ap.add_argument("--gate-every", type=int, default=10)
a = ap.parse_args()
key = open(a.key_file).read().strip() if a.key_file else ""
base = os.path.join(a.root, "sweep", a.job)
os.makedirs(os.path.join(base, "chunks"), exist_ok=True); os.makedirs(os.path.join(base, "out"), exist_ok=True)
os.umask(0o077)
corpus = [json.loads(l) for l in open(os.path.join(a.root, "owner-msgs.jsonl"))]
chunks = [corpus[i:i + a.chunk] for i in range(0, len(corpus), a.chunk)]


IDLE_S = 120   # phone-worker IDLE_S


def gate_reason():
    """Same policy as phone-worker gate(): None = may work. Fails closed. Telemetry is never a gate.
    (The S25 off switch ~/.local/state/s25-worker-off lives on groot; `phone-worker off` winds down by
    killing every llama-server on the S25, so this sweep stops with it and never restarts a server.)"""
    if a.gate == "none":
        return None
    import re, subprocess
    try:
        out = subprocess.run(["adb", "-s", a.gate_serial, "shell",
                              "cat /proc/uptime; dumpsys telephony.registry | grep mCallState=; "
                              "dumpsys power | grep -E 'mLastUserActivityTime'"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as e:  # noqa: BLE001
        return f"presence unavailable: {type(e).__name__}"
    calls = re.findall(r"mCallState=(\d)", out)
    if not calls:
        return "call state unavailable"
    if any(c != "0" for c in calls):
        return "phone is in a call"
    if a.gate == "s25":
        act = re.search(r"mLastUserActivityTime(?:\(excludingAttention\))?=(\d+)", out)
        try:
            idle = float(out.split()[0]) - int(act[1]) / 1000
        except Exception:  # noqa: BLE001
            return "owner activity clock unavailable"
        if idle < IDLE_S:
            return f"owner used the phone {idle:.0f}s ago (< {IDLE_S}s)"
    return None


def wait_gate(claim):
    last = None
    while True:
        r = gate_reason()
        if r is None:
            if last:
                print(json.dumps({"worker": a.worker, "gate": "open"}), flush=True)
            return
        if r != last:
            print(json.dumps({"worker": a.worker, "gate": "closed", "reason": r}), flush=True)
        last = r
        os.utime(claim)          # keep the claim fresh while we wait for the owner
        time.sleep(60)


def out_ids(n):
    p = os.path.join(base, "out", f"{n:04d}.jsonl")
    if not os.path.exists(p):
        return set()
    s = set()
    for l in open(p):
        try:
            s.add(json.loads(l)["id"])
        except Exception:
            pass
    return s


def try_claim(n):
    c = os.path.join(base, "chunks", f"{n:04d}.claim")
    try:
        fd = os.open(c, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, f"{a.worker} {int(time.time())}".encode()); os.close(fd)
        return True
    except FileExistsError:
        pass
    o = os.path.join(base, "out", f"{n:04d}.jsonl")
    last = max(os.path.getmtime(c), os.path.getmtime(o) if os.path.exists(o) else 0)
    if time.time() - last > a.stale:      # holder died: take it over
        tmp = c + f".{a.worker}"
        open(tmp, "w").write(f"{a.worker} {int(time.time())}")
        os.replace(tmp, c)
        return True
    return False


def run_chunk(n):
    have = out_ids(n)
    p = os.path.join(base, "out", f"{n:04d}.jsonl")
    t0, done = time.time(), 0
    claim = os.path.join(base, "chunks", f"{n:04d}.claim")
    with open(p, "a") as fo:
        for r in chunks[n]:
            if r["id"] in have:
                continue
            if done % a.gate_every == 0:
                wait_gate(claim)
            o = None
            for attempt in range(4):
                try:
                    o = phone_label.label(a.url, key, r["text"], a.mode, a.max_chars)
                    break
                except Exception as e:  # noqa: BLE001
                    print(json.dumps({"chunk": n, "id": r["id"], "err": f"{type(e).__name__}: {e}"[:200]}), flush=True)
                    time.sleep(15 * (attempt + 1))
            if o is None:
                return False            # server down: leave the claim, it goes stale and is retried
            fo.write(json.dumps({"id": r["id"], "source": r.get("source"), "profile": r.get("profile"),
                                 "model": a.model_tag, "mode": a.mode, "worker": a.worker,
                                 "ts": round(time.time(), 1), **o}, ensure_ascii=False) + "\n")
            fo.flush(); done += 1
    print(json.dumps({"chunk": n, "worker": a.worker, "rows": done, "s": round(time.time() - t0)}), flush=True)
    return True


print(json.dumps({"worker": a.worker, "url": a.url, "model": a.model_tag, "chunks": len(chunks),
                  "corpus": len(corpus)}), flush=True)
while True:
    pending = [n for n in range(len(chunks)) if len(out_ids(n)) < len(chunks[n])]
    if not pending:
        print(json.dumps({"worker": a.worker, "all_done": True}), flush=True)
        break
    got = next((n for n in pending if try_claim(n)), None)
    if got is None:
        time.sleep(60); continue   # everything left is claimed by live workers
    if not run_chunk(got):
        time.sleep(60)
# idle (Deployment keeps the pod; nothing to do)
while True:
    time.sleep(3600)
