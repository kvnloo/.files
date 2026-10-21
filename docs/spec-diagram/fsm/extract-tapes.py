#!/usr/bin/env python3
"""Turn the 2026-10-21 FSM reports into public-safe replay tapes (scenarios.json).

Inputs are the private replay/supervise reports written by kvnloo/z0intelligence
(`python -m z0int.fsm.replay` / `python -m z0int.fsm.supervise`). Only ids,
timestamps, event kinds, short SHAs and finding codes are copied; log paths,
commands, goals and home-directory paths are not. Every step says whether it is
`report` (the event happened as recorded) or `what-if` (an illustrative
continuation). build.mjs replays every tape through the compiled Bend and
records the outcome; this script makes no decisions.

usage: extract-tapes.py REPLAY.json SUPERVISE.json > scenarios.json
"""
import hashlib
import json
import sys
from datetime import datetime


def load(path):
    raw = open(path, "rb").read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def minutes(t0, t):
    def p(s):
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    return max(0, round((p(t) - p(t0)).total_seconds() / 60))


class Ids:
    """Small Nat ids for actors / SHAs, with display labels kept beside the tape."""

    def __init__(self, start=1):
        self.map, self.next = {}, start

    def __call__(self, key):
        if key not in self.map:
            self.map[key] = self.next
            self.next += 1
        return self.map[key]

    def labels(self, short=None):
        return {str(v): (short(k) if short else k) for k, v in self.map.items()}


ROLE = {"opus": "Opus", "sol": "Sol", "ci": "Ci", "owner": "Owner", "free": "Free", "chat": "Chat", "jev": "Jev", "slm": "Slm"}


def work_item_tape(item, actor_ids, sha_ids):
    steps = []
    for e in item["events"]:
        k = e["kind"]
        a = e.get("actor")
        act = {"id": actor_ids(a["id"]), "role": ROLE[a["role"]]} if a else None
        ev = {"tag": k}
        if k in ("Claim", "Start", "Submit", "Accept", "Merge", "Block", "Unblock", "Resume", "Abandon"):
            ev["a"] = act
        elif k == "Push":
            ev.update(a=act, sha=sha_ids(e["sha"]))
        elif k == "Verify":
            ev.update(a=act, r={"sha": sha_ids(e["receipt"]["sha"]), "pass": bool(e["receipt"]["passed"])})
        elif k == "Integrate":
            r = e.get("receipt") or {"sha": None, "passed": False}
            ev.update(a=act, ish=sha_ids(e["sha"]), r={"sha": sha_ids(r["sha"]) if r["sha"] else 0, "pass": bool(r["passed"])})
        elif k == "Deploy":
            ev.update(a=act, served=sha_ids(e["sha"]))
        elif k == "Observe":
            ev["served"] = sha_ids(e["sha"])
        steps.append({"event": ev, "source": "report", "at": e.get("at")})
    return steps


def worker_tape(worker, by_ids):
    events = worker["events"]
    t0 = events[0]["t"]
    steps = []
    for e in events:
        k, t = e["kind"], minutes(t0, e["t"])
        ev = {"tag": k}
        if k == "Start":
            ev.update(h="Groot", t=t)
        elif k in ("Beat", "Interrupt"):
            ev["t"] = t
        elif k == "Tick":
            ev["now"] = t
        elif k == "Resume":
            ev.update(by=by_ids(worker["meta"].get("successor") or "successor"), log=bool(e["log"]))
        steps.append({"event": ev, "source": "report", "at": e["t"]})
    return steps


def main(replay_path, supervise_path):
    rp, rp_sha = load(replay_path)
    sv, sv_sha = load(supervise_path)
    items = {it["id"]: it for it in rp["items"]}
    workers = {w["id"]: w for w in sv["workers"]}
    findings = {}
    for f in sv["findings"]:
        findings.setdefault(f["code"], f)
    short = lambda s: s[:7]
    scenarios = []

    def wi(id_, title, summary, item_id, extra, notes, availability=None):
        actors, shas = Ids(), Ids()
        steps = work_item_tape(items[item_id], actors, shas)
        for step in extra(actors, shas):
            steps.append({**step, "source": "what-if"})
        for i, note in notes.items():
            steps[i]["note"] = note
        for s in steps:
            s.setdefault("note", "")
            s["facts"] = {"availability": (availability or {}).get(steps.index(s), "DeepWork")}
        scenarios.append({"id": id_, "machine": "work-item", "title": title, "summary": summary, "item": item_id,
                          "initial": {"tag": "Proposed"}, "actors": actors.labels(), "shas": shas.labels(short), "steps": steps})

    # 1. Owner-acceptance gate: real self-integration, then the acceptance gate.
    def accept_extra(actors, shas):
        author = {"id": actors("kvnloo"), "role": "Opus"}
        ci = {"id": actors("service-branch-check"), "role": "Ci"}
        kevin = {"id": actors("Kevin (owner, distinct identity)"), "role": "Owner"}
        head = shas("751a8a6c3b575d4a47ba45803d14f8ef57740518")
        return [
            {"event": {"tag": "Integrate", "a": ci, "ish": head, "r": {"sha": head, "pass": True}},
             "note": "What-if: a Ci actor that is not the author lands it with a receipt for that head."},
            {"event": {"tag": "Deploy", "a": ci, "served": head},
             "note": "The service serves exactly the integrated head, so Deployed holds. Now it needs Kevin."},
            {"event": {"tag": "Accept", "a": author},
             "note": "The author (an Opus agent acting as kvnloo) tries to accept its own work."},
            {"event": {"tag": "Accept", "a": kevin},
             "note": "Kevin accepts, but he is off right now: the action is held in the needs-Kevin queue."},
            {"event": {"tag": "Accept", "a": kevin},
             "note": "Next deep-work block: Kevin accepts the deployed result."},
            {"event": {"tag": "Merge", "a": ci}, "note": "Deterministic code merges on his recorded acceptance."},
        ]
    wi("owner-acceptance", "Loop 1 · dash#72: self-approval refused at every gate",
       "Real tape for kvnloo/dash#72: an Opus agent claimed, pushed and then integrated its own PR under the owner's GitHub account. Bend refuses the self-integration (L2). The what-if continuation shows the owner-acceptance gate refusing the author's own Accept and holding Kevin's Accept while he is off (L1, L2, L7).",
       "kvnloo/dash#72", accept_extra,
       {0: "An Opus agent (kvnloo) claims the PR's work: Opus may write code.", 4: "GitHub checks (Ci, not the author) pass on exactly the pushed head: Draft PR.",
        5: "Recorded: the author's own account integrated it. Same actor as the author, so the gate refuses."},
       availability={9: "Off"})

    # 2. Merge without acceptance (L1).
    wi("merge-without-acceptance", "Loop 1 · company-os#4: merged from Verifying",
       "Real tape for kvnloo/company-os#4: merged to main 2 minutes after the claim, from Verifying, with no verification, deployment or owner acceptance. Bend refuses the merge (L1).",
       "kvnloo/company-os#4", lambda a, s: [],
       {4: "Recorded merge by the owner's account while the item was still Verifying."})

    # 3. Stale service (L4).
    def stale_extra(actors, shas):
        ci = {"id": actors("service-branch-check"), "role": "Ci"}
        ig = shas("248126ebc5004e6430d3ebe1cc4c9340770d8dfe")
        old = shas("3d0f6eb3e2495bb46f232f4994a0902541fd0d5a")
        return [
            {"event": {"tag": "Deploy", "a": ci, "served": ig}, "note": "What-if: restart the service on the integrated head."},
            {"event": {"tag": "Observe", "served": old}, "note": "What-if: the service is later seen serving the old head again, so Deployed is taken away."},
        ]
    wi("stale-service", "Loop 1 · company-os-static: stale service",
       "Real tape for the company-os-static service: integrated at 248126e but serving 3d0f6eb, 31 commits behind. Bend refuses \"deployed\" (L4). Receipts in this tape were marked 'assumed' by the replay.",
       "service:company-os-static", stale_extra,
       {6: "Recorded: the service serves 3d0f6eb, not the integrated 248126e."})

    # 4. Interrupted work never dropped (L5, L6).
    def interrupted_extra(actors, shas):
        return [
            {"event": {"tag": "Resume", "a": {"id": actors("free-model"), "role": "Free"}}, "note": "What-if: a free model tries to pick it up. Free models never implement (L6)."},
            {"event": {"tag": "Abandon", "a": {"id": actors("sol-lane"), "role": "Sol"}}, "note": "What-if: the Sol lane tries to drop it. Only the owner or Opus may abandon (L5)."},
            {"event": {"tag": "Resume", "a": {"id": actors("sol-lane"), "role": "Sol"}}, "note": "What-if: the Sol lane resumes it and becomes the author; the pushed head is kept."},
        ]
    wi("interrupted-not-dropped", "Loop 1 · z0live QR pairing: interrupted 35 h",
       "Real tape for worker deleg_14619e78/task-0, interrupted 35 h before the report with no resume, PR or abandon decision (one of 13 such). Interrupted cannot be left silently: only a coder's Resume or an explicit Abandon moves it.",
       "worker:deleg_14619e78/task-0", interrupted_extra, {2: "Recorded interruption."})

    # Loop 2 workers -------------------------------------------------------
    def ws(id_, title, summary, worker_id, w, extra=lambda b: [], notes=None, steps=None):
        by = Ids(2)
        tape = steps if steps is not None else worker_tape(workers[worker_id], by)
        tape += [{**s, "source": "what-if"} for s in extra(by)]
        for i, note in (notes or {}).items():
            tape[i]["note"] = note
        for s in tape:
            s.setdefault("note", "")
            s["facts"] = {"limit": 120}
        scenarios.append({"id": id_, "machine": "worker", "title": title, "summary": summary, "item": worker_id,
                          "initial": {"tag": "Dispatched", "w": w}, "actors": {"1": worker_id, **by.labels()}, "steps": tape})

    light = {"id": 1, "wt": 0, "load": "Light", "exc": "NoExc"}
    ws("worker-resumed", "Loop 2 · interrupted, then resumed from its log",
       "Real tape for deleg_ec0465e5/task-0 (fframestudio hosted demo): interrupted after 24 min; a successor read its log and took over 31 s later. One of 37 resumed workers.",
       "deleg_ec0465e5/task-0", light, notes={4: "Successor deleg_aa6048ca/task-0 resumes from the log.", 5: "Resumed is final for this worker; later ticks change nothing."})
    ws("resume-without-log", "Loop 2 · resumed without reading the log → Overdue",
       "Real tape for deleg_9c151b34/task-1 (E2E tester G02): a successor took over without reading the log (one of 10). Bend refuses that resume (W2), so the worker is still interrupted; three days later the clock makes it Overdue and it lands in Kevin's queue.",
       "deleg_9c151b34/task-1", light, notes={1: "It started one background process...", 3: "...and reaped it.", 6: "Successor deleg_656fb990/task-0 took over without reading the log.", 7: "Report time: 72 h past the interruption."})
    ws("overdue-abandon", "Loop 2 · overdue 6 days → needs Kevin",
       "Real tape for deleg_e07e87da/task-1 (night lane stone-25): interrupted on 15 Oct, no decision for 6 days (one of 26 past the 2 h limit). The report recommends abandon: nothing left to recover.",
       "deleg_e07e87da/task-1", light,
       extra=lambda by: [{"event": {"tag": "Abandon"}, "note": "What-if: Kevin takes the recommended decision. No background process is left, so abandon is allowed."}],
       notes={3: "Report time: 6 days later. Overdue = needs Kevin."})
    heavy = findings["heavy_on_groot"]["evidence"]
    ws("heavy-on-groot", "Loop 2 · heavy build on groot refused",
       f"Shaped from a real finding (job {heavy['job'][:24]}…, {heavy['at'][:10]}): an `npm run build` ran on groot with no GPU or toolchain exception, one of 1,695. Bend refuses the start on groot (W4) and accepts it on the MBP, as fleet-build routes it.",
       heavy["job"], {"id": 1, "wt": 0, "load": "Heavy", "exc": "NoExc"},
       steps=[{"event": {"tag": "Start", "h": "Groot", "t": 0}, "source": "report", "note": "Recorded: heavy build started on groot, no exception declared."},
              {"event": {"tag": "Start", "h": "Mbp", "t": 0}, "source": "what-if", "note": "What-if: fleet-build sends it to the MBP."},
              {"event": {"tag": "Beat", "t": 3}, "source": "what-if"},
              {"event": {"tag": "Finish"}, "source": "what-if"},
              {"event": {"tag": "Integrate"}, "source": "what-if", "note": "No background process left, so it can be integrated."}])
    ws("gpu-exception", "Loop 2 · GPU job on groot allowed",
       "Contrast: 1,291 heavy groot jobs declared a GPU exception (19 a toolchain exception). With the exception declared, Bend lets heavy work start on groot.",
       "gpu-exception", {"id": 1, "wt": 0, "load": "Heavy", "exc": "Gpu"},
       steps=[{"event": {"tag": "Start", "h": "Groot", "t": 0}, "source": "what-if", "note": "Heavy + declared GPU exception on groot."},
              {"event": {"tag": "Finish"}, "source": "what-if"}])
    orphan = findings["orphan_background_process"]["evidence"]
    ws("orphan-background", "Loop 2 · background process must be reaped",
       f"Shaped from the one orphan in the report ({orphan['proc']}, started {orphan['started'][:16]}Z, still alive after its owner session ended). Bend will not integrate or abandon a worker that still has a background process (W3).",
       orphan["proc"], light,
       steps=[{"event": {"tag": "Start", "h": "Groot", "t": 0}, "source": "report"},
              {"event": {"tag": "Spawn"}, "source": "report", "note": "Recorded: it started a background process."},
              {"event": {"tag": "Finish"}, "source": "what-if", "note": "The worker finishes but leaves the process running."},
              {"event": {"tag": "Integrate"}, "source": "what-if", "note": "Integrate is refused: one background process left."},
              {"event": {"tag": "Reap"}, "source": "what-if", "note": "Reap it."},
              {"event": {"tag": "Integrate"}, "source": "what-if"}])

    # Lease (W1) ------------------------------------------------------------
    lease = findings["worktree_two_owners"]["evidence"]
    wt = lease["worktree"].rstrip("/").rsplit("/", 1)[-1]
    holder, intruder = 1, 2
    scenarios.append({"id": "lease-clash", "machine": "lease", "title": f"Loop 2 · lease clash in {wt}",
        "summary": f"Real finding: while a {lease['holder_source']} session held the {wt} worktree, a {lease['intruder_source']} session wrote to it ({lease['first'][:16]}Z). One of 419 such writes across 19 worktrees. Bend refuses every takeover except Reclaim with evidence the holder is dead (W1).",
        "item": wt, "initial": {"tag": "Free"},
        "actors": {"1": f"holder {lease['holder']}", "2": f"intruder {lease['intruder'][:20]}…"},
        "steps": [
            {"event": {"tag": "Acquire", "a": holder}, "source": "report", "note": "The holder session takes the worktree."},
            {"event": {"tag": "Acquire", "a": intruder}, "source": "report", "note": "Recorded: a second session writes while the lease is held."},
            {"event": {"tag": "Release", "a": intruder}, "source": "what-if", "note": "The intruder cannot release someone else's lease."},
            {"event": {"tag": "Reclaim", "a": intruder, "dead": False}, "source": "what-if", "note": "Reclaim without evidence the holder is dead is refused."},
            {"event": {"tag": "Release", "a": holder}, "source": "what-if", "note": "The holder finishes and releases."},
            {"event": {"tag": "Acquire", "a": intruder}, "source": "what-if", "note": "Now the second session may take it."}]})
    for s in scenarios[-1]["steps"]:
        s["facts"] = {}

    # Device (W5, W6) -------------------------------------------------------
    inst = findings["install_without_lock"]["evidence"]
    inp = findings["input_without_foreground_check"]["evidence"]
    scenarios.append({"id": "s25-lock-and-look", "machine": "device", "title": "Loop 2 · S25: install lock and look-before-tap",
        "summary": f"Real findings from session {inst['session']}: a Lawnchair install outside the install lock ({inst['at'][:16]}Z; 7 of 17 installs) and input with no foreground check ({inp['at'][:16]}Z; 11 of 23 inputs). Bend gives neither any effect (W5, W6).",
        "item": inst["session"], "initial": {"lk": {"tag": "Free"}, "fg": {"tag": "Unknown"}},
        "actors": {"1": f"session {inst['session']}", "app 1": "Lawnchair (launcher)"},
        "steps": [
            {"event": {"tag": "Install", "a": 1}, "source": "report", "note": "Recorded: adb install without holding the lock."},
            {"event": {"tag": "Lock", "a": 1}, "source": "what-if", "note": "Take the install lock first."},
            {"event": {"tag": "Install", "a": 1}, "source": "what-if", "note": "Now the install goes through."},
            {"event": {"tag": "Unlock", "a": 1}, "source": "what-if"},
            {"event": {"tag": "Input", "a": 1, "app": 1}, "source": "report", "note": "Recorded: input sent without looking at the screen."},
            {"event": {"tag": "Peek", "app": 1}, "source": "what-if", "note": "Look first: the launcher is in the foreground."},
            {"event": {"tag": "Input", "a": 1, "app": 1}, "source": "what-if", "note": "One input into the app just seen."},
            {"event": {"tag": "Input", "a": 1, "app": 1}, "source": "what-if", "note": "A second input needs a fresh look: the first may have changed the screen."}]})
    for s in scenarios[-1]["steps"]:
        s["facts"] = {}

    out = {"schema": 1,
           "provenance": {"replayReport": {"name": "replay-20261021.json", "sha256": rp_sha, "generatedAt": rp["generated_at"]},
                          "superviseReport": {"name": "worker-supervision-20261021.json", "sha256": sv_sha, "generatedAt": sv["generated_at"]},
                          "privacy": "Only ids, timestamps, event kinds, short SHAs and finding codes are copied; log paths, commands, goals and home paths are not.",
                          "assumptions": "Worker hosts are not in the supervise events; report tapes start on groot with light load (Hermes agent sessions). Times are minutes since the worker's first event; the limit is the report's 2 h."},
           "scenarios": scenarios}
    json.dump(out, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
