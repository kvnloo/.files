#!/usr/bin/env python3
"""Check tree_text oracles in tasks.json against REDACTED hierarchy dumps (phone-screen-safe output).

  check_oracles.py tasks.json DUMP_DIR [DUMP_DIR...] [--json OUT]

For every task: the oracle must PASS on its evidence screen and must FAIL on the home screen.
It also counts how many other probed screens it would (wrongly) accept, i.e. how discriminative it is.
Matching rule (same as the queue contract's tree_text oracle as this suite reads it): every
must_contain string is a substring of some node's text or content-desc, no must_not_contain string
is, and the foreground package equals oracle.package when given."""
import json, sys, glob, os, xml.etree.ElementTree as ET

def screen(path):
    root = ET.parse(path).getroot()
    vals, pkgs = [], set()
    for n in root.iter("node"):
        if n.get("package"): pkgs.add(n.get("package"))
        for k in ("text", "content-desc"):
            v = (n.get(k) or "").strip()
            if v: vals.append(v)
    return vals, pkgs

def oracle_pass(o, vals, pkgs):
    has = lambda s: any(s in v for v in vals)
    if o.get("package") and o["package"] not in pkgs: return False
    return all(has(s) for s in o.get("must_contain", [])) and not any(has(s) for s in o.get("must_not_contain", []))

def main(argv):
    out = None
    if "--json" in argv: i = argv.index("--json"); out = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    suite = json.load(open(argv[0])); screens = {}
    for d in argv[1:]:
        for p in sorted(glob.glob(os.path.join(d, "*.xml"))):
            try: screens.setdefault(os.path.basename(p)[:-4], screen(p))
            except ET.ParseError: pass
    rows, bad = [], 0
    for t in suite["tasks"]:
        ev = t.get("evidence"); o = t["oracle"]
        ev_ok = ev in screens and oracle_pass(o, *screens[ev])
        home_ok = "home" in screens and not oracle_pass(o, *screens["home"])
        accepts = sorted(n for n, s in screens.items() if oracle_pass(o, *s))
        ok = ev_ok and home_ok
        bad += not ok
        rows.append({"task": t["id"], "evidence": ev, "pass_on_evidence": ev_ok, "fail_on_home": home_ok, "accepted_screens": accepts, "ok": ok})
        print(f"{'OK ' if ok else 'BAD'} {t['id']:<24} evidence={ev} accepts={accepts}")
    print(f"{len(rows) - bad}/{len(rows)} oracles verified on {len(screens)} redacted screens")
    if out: json.dump({"screens": sorted(screens), "rows": rows}, open(out, "w"), indent=1)
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
