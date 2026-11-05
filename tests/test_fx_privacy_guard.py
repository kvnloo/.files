"""PRIV2 (Kevin 2026-11-05 13:46: personal data goes to Claude or local only). fx (GPT) runs through
fx-canon, which refuses briefs that are marked personal or name owner sources, and runs fx in a
bwrap sandbox where the owner data paths are unreadable and ctx/agentsview/sqlite3 fail closed.
Scratch fixture home only; a fake fx probes what a GPT session could reach."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/fx-canon"

FAKE_FX = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
prompt = sys.argv[-1] if len(sys.argv) > 2 and sys.argv[-2] == "--" else sys.stdin.read()
res = {"argv1": sys.argv[1:2], "canon": "CANON-FIXTURE" in prompt, "reads": {}, "cmds": {}}
for p in json.loads(os.environ["PROBE_PATHS"]):
    try:
        with open(p, "rb") as f: res["reads"][p] = f.read(64).decode(errors="replace")
    except OSError as e: res["reads"][p] = "DENIED"
for c in ("ctx", "agentsview", "sqlite3"):
    try:
        r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=10)
        res["cmds"][c] = r.returncode
    except FileNotFoundError: res["cmds"][c] = "missing"
open(os.environ["PROBE_OUT"], "w").write(json.dumps(res))
'''


class Guard(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        h = self.t / "home"
        self.secret = {}
        def plant(rel, base=h):
            p = base / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("OWNER-SECRET " + rel)
            self.secret[rel] = str(p); return p
        plant(".hermes/state.db"); plant(".hermes/profiles/ayo/state.db"); plant(".hermes/profiles/ayo/state.db-wal")
        plant(".agentsview/sessions.db")
        self.ctx = self.t / "ctxroot"; plant("index.db", self.ctx)
        self.av = self.t / "avdata"; plant("sessions.db", self.av)
        self.ops = self.t / "ops"; plant("unified-memory/OWNER-CANON.md", self.ops)
        plant("owner-message-audit-x/OWNER-MESSAGES.md", self.ops)
        self.code = h / "src/app.py"; self.code.parent.mkdir(parents=True); self.code.write_text("print('ok')")
        bin_ = self.t / "bin"; bin_.mkdir()
        for c in ("ctx", "agentsview", "sqlite3"):  # real-looking tools that would succeed
            (bin_ / c).write_text("#!/bin/sh\necho real\n"); (bin_ / c).chmod(0o755)
        fx = self.t / "fx"; fx.write_text(FAKE_FX); fx.chmod(0o755)
        canon = self.t / "CANON.block.md"; canon.write_text("CANON-FIXTURE")
        self.out = self.t / "probe.json"
        self.env = {**os.environ, "HOME": str(h), "FX_BIN": str(fx), "OWNER_CANON_BLOCK": str(canon),
                    "CTX_DATA_ROOT": str(self.ctx), "AGENTSVIEW_DATA_DIR": str(self.av),
                    "FX_PRIVACY_OPS": str(self.ops), "FX_PRIVACY_LOG": str(self.t / "refusals.jsonl"),
                    "PATH": f"{bin_}:{os.environ['PATH']}", "PROBE_OUT": str(self.out),
                    "PROBE_PATHS": json.dumps(list(self.secret.values()) + [str(self.code)])}

    def run_fx(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(GUARD), *args], env=self.env, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def test_real_coding_brief_runs_sandboxed_and_owner_data_is_unreachable(self):
        r = self.run_fx("ask", "--model", "gpt-6.1-terra", "fix the off-by-one in src/app.py and add a test")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(self.out.read_text())
        self.assertTrue(res["canon"])
        self.assertEqual(res["reads"][str(self.code)], "print('ok')")          # code stays readable
        leaked = {k: v for k, v in res["reads"].items() if "OWNER-SECRET" in v}
        self.assertEqual(leaked, {})                                            # (c) direct reads fail
        self.assertTrue(all(v not in (0, "missing") for v in res["cmds"].values()), res["cmds"])  # (b) shims

    def test_stdin_brief_is_checked_too(self):
        r = self.run_fx("ask", stdin="summarize agentsview session messages --role user")
        self.assertEqual(r.returncode, 3); self.assertFalse(self.out.exists())

    def test_briefs_naming_owner_sources_or_marked_personal_are_refused(self):
        for brief in ["[personal] draft a reply to my landlord",
                      "privacy: personal\nsummarize my week",
                      "read ~/.hermes/profiles/ayo/state.db and list asks",
                      "run ctx search 'phone' and cluster the results",
                      "query the AgentsView sessions.db for user turns",
                      "use $CTX_DATA_ROOT/index.db",
                      "parse operations/unified-memory/OWNER-CANON.md",
                      "replay OWNER-MESSAGES.md into tasks",
                      "label Kevin's owner messages from task-source.json"]:
            with self.subTest(brief=brief):
                r = self.run_fx("ask", brief)
                self.assertEqual(r.returncode, 3, brief)
                self.assertIn("PRIV2", r.stderr)
        self.assertFalse(self.out.exists())
        log = (self.t / "refusals.jsonl").read_text().splitlines()
        self.assertEqual(len(log), 9)
        self.assertNotIn("landlord", "".join(log))                              # receipts carry no content

    def test_interactive_and_resume_sessions_are_sandboxed(self):
        r = self.run_fx("session", "resume", "last")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(self.out.read_text())
        self.assertEqual({k: v for k, v in res["reads"].items() if "OWNER-SECRET" in v}, {})


if __name__ == "__main__":
    unittest.main()
