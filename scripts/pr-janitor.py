#!/usr/bin/env python3
"""pr-janitor: close dead PRs on kvnloo's own repos. Deterministic; dry-run by default.

Agents open many PRs, then the work lands another way (cherry-picks, a preview
branch, a newer PR) and the old PR stays open forever. Instructions do not fix
that; this does. A PR is closed only when one rule below proves it is dead:

  landed      every file the PR changes is already byte-identical on its base
              branch (blob SHA match), so the work is in base.
  superseded  another open PR in the same repo has the same head branch or the
              same title and is newer.
  stale-draft draft with no activity for STALE_DAYS (default 14).

Never closed: PRs updated in the last KEEP_DAYS (default 3), approved PRs,
labels keep/hold/pinned/do-not-close, bot PRs, PRs in KEEP (owner-pinned),
repos not owned by OWNER. Closing keeps the branch, so any PR can be reopened.
Every close leaves a comment that names the rule and the evidence.

  scripts/pr-janitor.py plan  [--out plan.jsonl]           classify, change nothing
  scripts/pr-janitor.py apply --plan plan.jsonl [--max N] [--rules landed,superseded]
  scripts/pr-janitor.py keep  --list keep.tsv               add the keep label (repo<TAB>number)
apply re-reads each PR first and skips it if it is no longer open or is protected.
Needs: gh (authenticated).
"""
import argparse, collections, datetime as dt, json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

OWNER = "kvnloo"
STALE_DAYS, KEEP_DAYS = 14, 3
PACE = 4  # seconds between closes; stays under GitHub's content-creation limit
KEEP_LABELS = {"keep", "hold", "pinned", "do-not-close"}
KEEP = {("oss-factory", 109), ("oss-factory", 130), ("oss-factory", 182)}
FIELDS = "number,title,isDraft,updatedAt,headRefName,baseRefName,author,reviewDecision,labels,url"
NOW = dt.datetime.now(dt.timezone.utc)


def gh(*args, check=True):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout


def api(path):
    return json.loads(gh("api", "-H", "Accept: application/vnd.github+json", path))


def days(ts):
    return (NOW - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).days


def list_prs():
    repos = gh("repo", "list", OWNER, "--limit", "1000", "--json", "name,isArchived",
               "-q", ".[] | select(.isArchived|not) | .name").split()
    out = []
    def one(r):
        try:
            prs = json.loads(gh("pr", "list", "-R", f"{OWNER}/{r}", "--state", "open", "--limit", "1000", "--json", FIELDS) or "[]")
        except RuntimeError:
            return []
        for p in prs:
            p["repo"] = r
        return prs
    with ThreadPoolExecutor(8) as ex:
        for prs in ex.map(one, repos):
            out += prs
    return out


_base_cache = {}
def base_blob(repo, base, path):
    """Blob SHA of path on base, or None if absent."""
    key = (repo, base)
    if key not in _base_cache:
        t = api(f"repos/{OWNER}/{repo}/git/trees/{base}?recursive=1")
        _base_cache[key] = None if t.get("truncated") else {e["path"]: e["sha"] for e in t["tree"] if e["type"] == "blob"}
    tree = _base_cache[key]
    if tree is not None:
        return tree.get(path)
    try:
        return api(f"repos/{OWNER}/{repo}/contents/{path}?ref={base}").get("sha")
    except RuntimeError:
        return None


def landed(p):
    """True when every changed file already matches base. Returns (bool, evidence)."""
    files = json.loads(gh("api", "--paginate", "--slurp", f"repos/{OWNER}/{p['repo']}/pulls/{p['number']}/files"))
    files = [f for page in files for f in page]
    if not files or len(files) >= 3000:
        return False, "no file list"
    for f in files:
        want = None if f["status"] == "removed" else f["sha"]
        if base_blob(p["repo"], p["baseRefName"], f["filename"]) != want:
            return False, f"{f['filename']} differs from {p['baseRefName']}"
    return True, f"all {len(files)} changed files are identical on {p['baseRefName']}"


def protected(p):
    if p["author"].get("is_bot") or p["author"]["login"] != OWNER:
        return "not owner-authored"
    if (p["repo"], p["number"]) in KEEP:
        return "owner-pinned"
    if KEEP_LABELS & {l["name"].lower() for l in p["labels"]}:
        return "keep label"
    if p.get("reviewDecision") == "APPROVED":
        return "approved"
    if days(p["updatedAt"]) < KEEP_DAYS:
        return f"active in last {KEEP_DAYS}d"
    return None


def classify(prs):
    groups = collections.defaultdict(list)
    for p in prs:
        groups[(p["repo"], "head", p["headRefName"])].append(p)
        groups[(p["repo"], "title", p["title"].strip().lower())].append(p)
    newer = {}
    for (repo, kind, _), ps in groups.items():
        if len(ps) > 1:
            ps.sort(key=lambda x: x["updatedAt"], reverse=True)
            for old in ps[1:]:
                newer.setdefault((repo, old["number"]), (kind, ps[0]["number"]))

    def decide(p):
        row = {k: p[k] for k in ("repo", "number", "title", "url", "isDraft", "updatedAt", "baseRefName", "headRefName")}
        why = protected(p)
        if why:
            return {**row, "action": "keep", "rule": why}
        if (p["repo"], p["number"]) in newer:
            kind, n = newer[(p["repo"], p["number"])]
            return {**row, "action": "close", "rule": "superseded", "evidence": f"same {kind} as newer #{n}"}
        try:
            ok, ev = landed(p)
        except RuntimeError as e:
            ok, ev = False, f"check failed: {e}"
        if ok:
            return {**row, "action": "close", "rule": "landed", "evidence": ev}
        if p["isDraft"] and days(p["updatedAt"]) >= STALE_DAYS:
            return {**row, "action": "close", "rule": "stale-draft", "evidence": f"draft, idle {days(p['updatedAt'])}d; {ev}"}
        return {**row, "action": "keep", "rule": "live", "evidence": ev}

    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(decide, prs))


COMMENT = ("Closed by pr-janitor (rule: **{rule}**). Evidence: {evidence}.\n\n"
           "The branch is kept; reopen this PR if this is wrong. "
           "Policy: https://github.com/kvnloo/.files/blob/master/scripts/pr-janitor.py")


def apply(plan_path, limit, rules=None):
    rows = [json.loads(l) for l in open(plan_path) if l.strip()]
    todo = [r for r in rows if r["action"] == "close" and (not rules or r["rule"] in rules)][:limit]
    done = 0
    for r in todo:
        try:
            cur = json.loads(gh("pr", "view", str(r["number"]), "-R", f"{OWNER}/{r['repo']}",
                                "--json", "state,author,labels,reviewDecision,updatedAt"))
            cur["repo"], cur["number"] = r["repo"], r["number"]
            why = "not open" if cur["state"] != "OPEN" else protected(cur)
            if why:
                print(f"skip {r['repo']}#{r['number']} ({why})", flush=True)
                continue
            time.sleep(PACE)
            gh("pr", "close", str(r["number"]), "-R", f"{OWNER}/{r['repo']}", "--comment",
               COMMENT.format(rule=r["rule"], evidence=r["evidence"]))
            done += 1
            print(f"closed {r['repo']}#{r['number']} ({r['rule']})", flush=True)
        except RuntimeError as e:
            print(f"FAILED {r['repo']}#{r['number']}: {e}", file=sys.stderr, flush=True)
    print(f"closed {done}/{len(todo)}")


def keep(list_path):
    rows = [l.split("\t") for l in open(list_path) if l.strip()]
    for repo in sorted({r for r, _ in rows}):
        gh("label", "create", "keep", "-R", f"{OWNER}/{repo}", "--color", "0E8A16",
           "--description", "pr-janitor: never auto-close", "--force")
    done = 0
    for repo, n in rows:
        try:
            gh("pr", "edit", n.strip(), "-R", f"{OWNER}/{repo}", "--add-label", "keep")
            done += 1
        except RuntimeError as e:
            print(f"FAILED {repo}#{n.strip()}: {e}", file=sys.stderr, flush=True)
        time.sleep(1)
    print(f"labelled {done}/{len(rows)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan"); pl.add_argument("--out", default="pr-janitor-plan.jsonl")
    ay = sub.add_parser("apply"); ay.add_argument("--plan", required=True); ay.add_argument("--max", type=int, default=10**6)
    ay.add_argument("--rules", help="comma list; only close rows with these rules")
    kp = sub.add_parser("keep"); kp.add_argument("--list", required=True)
    a = ap.parse_args()
    if a.cmd == "keep":
        keep(a.list)
    elif a.cmd == "plan":
        rows = classify(list_prs())
        with open(a.out, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        c = collections.Counter((r["action"], r["rule"] if r["action"] == "close" else r["rule"].split(" ")[0]) for r in rows)
        for k, v in sorted(c.items()):
            print(f"{k[0]:6} {k[1]:22} {v}")
        print(f"plan written: {a.out}")
    else:
        apply(a.plan, a.max, set(a.rules.split(",")) if a.rules else None)


if __name__ == "__main__":
    main()
