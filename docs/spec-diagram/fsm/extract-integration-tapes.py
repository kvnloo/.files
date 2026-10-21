#!/usr/bin/env python3
"""Allowlist five integration snapshot tapes. Probes are NOT historical actions.

python extract-integration-tapes.py /private/integration-20261021.json
Only ids, timestamps, short SHAs, finding codes and abstract boolean facts leave
the report. No service commands, paths, decision prose or personal traces.
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def extract(report, digest):
    changes = {c["id"]: c for r in report["repos"] for c in r["changes"]}
    services = {s["id"]: s for s in report["services"]}
    def probe(event, note):
        return {"event":event,"facts":{},"note":note,"source":"what-if","at":report["generated_at"]}
    def tape(id, target, state, steps, summary):
        return dict(id=id,machine="integration",title="Loop 3 · "+target,summary=summary,
                    item=target,initial={"tag":state},actors={},steps=steps)
    dash = changes["kvnloo/dash#78"]
    noop = changes["kvnloo/noop#93"]
    company = changes["kvnloo/company-os#7"]
    conflicted = changes["kvnloo/z0evals#105"]
    layered = changes["kvnloo/.files#34"]
    s25 = services["noop-s25"]
    assert dash["stack_consistent"] is False
    assert noop["contained"] is True
    assert s25["checkout_matches_integration"] is False
    assert company["contained"] is False and company["age_hours"] >= 24
    assert conflicted["state"] == "Conflicted"
    tapes = [
        tape("integration-dash-stack", dash["id"], dash["state"], [
            probe({"tag":"Queue"}, "What-if: queue this observed draft."),
            probe({"tag":"Integrate","lease":False,"stack":dash["stack_consistent"],"independent":False},
                  "Guard probe: STACK_BASE_STALE; no recorded lease or independent review. Not an actual integration attempt.")],
             "Snapshot: child recorded base does not contain its parent's current head. All events are probes, not historical actions."),
        tape("integration-noop-stale", noop["id"], "OnIntegrationBranch", [
            probe({"tag":"Deploy","equal":False}, "Guard probe: NOOP checkout differs from remote integration head; installed build SHA remains unknown."),
            probe({"tag":"Accept","owner":False}, "What-if agent acceptance: refused, and not eligible before deployed evidence."),
            probe({"tag":"Merge"}, "What-if merge without owner acceptance: refused.")],
             "Observed containment of PR #93 is separate from stale S25-build checkout. No phone action or claim about installed source revision."),
        tape("integration-company-park", company["id"], company["state"], [
            probe({"tag":"Park","reason":False,"future":False}, "Guard probe: there is no explicit reason/expiry parking decision."),
            probe({"tag":"Park","reason":True,"future":True}, "What-if Kevin explicitly parks this exact head with reason + expiry; not a real decision."),
            probe({"tag":"Expire","expired":True}, "What-if expiry: requeue, never silently forget the change.")],
             "Observed overdue, uncontained draft. Parking and expiry are illustrative continuations, never recorded owner consent."),
        tape("integration-evals-conflict", conflicted["id"], "Conflicted", [
            probe({"tag":"Merge"}, "What-if shortcut: a conflict cannot bypass OwnerAccepted."),
            probe({"tag":"Resume"}, "What-if independently repaired and re-tested: requeue."),
            probe({"tag":"Integrate","lease":False,"stack":True,"independent":False}, "Guard probe: no recorded integration lease/reviewer; still refused.")],
             "Snapshot: GitHub reports CONFLICTING. Repair/resume are hypothetical; no conflict was changed by this checker."),
        tape("integration-files-owner-gate", layered["id"], layered["state"], [
            probe({"tag":"Queue"}, "What-if: queue the observed visualization draft."),
            probe({"tag":"Integrate","lease":True,"stack":True,"independent":True}, "What-if: designated branch, valid lease and independent reviewer. None are asserted by this snapshot."),
            probe({"tag":"Deploy","equal":False}, "Guard probe: running artifact revision is not attested by checkout HEAD."),
            probe({"tag":"Deploy","equal":True}, "What-if exact build/runtime evidence becomes available."),
            probe({"tag":"Accept","owner":False}, "What-if author self-approval: refused."),
            probe({"tag":"Accept","owner":True}, "What-if Kevin later accepts. Not recorded consent."),
            probe({"tag":"Merge"}, "What-if merge only after that explicit acceptance. This tool never merges.")],
             "Observed .files draft; the remainder teaches the acceptance gate. Hypothetical positive facts are not operational authorization.")]
    return {"schema":1,"provenance":{"report":"integration-20261021.json","sha256":digest,
            "generatedAt":report["generated_at"],"privacy":"Allowlisted ids, times, short SHAs, finding codes only.",
            "scope":"Observed snapshot initial states; ALL event steps are explicitly what-if guard probes. Not historical deployment/action logs."},
            "observations":[{"id":c["id"],"head":c["headRefOid"][:12],"state":c["state"],"codes":c["violations"]}
                            for c in [dash,noop,company,conflicted,layered]],"scenarios":tapes}


if __name__ == "__main__":
    data = Path(sys.argv[1]).read_bytes()
    result = extract(json.loads(data), hashlib.sha256(data).hexdigest())
    (HERE/"integration-tapes.json").write_text(json.dumps(result, indent=1)+"\n")
    print(f"wrote {len(result['scenarios'])} snapshot tapes; all probes labelled what-if")
