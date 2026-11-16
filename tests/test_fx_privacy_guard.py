# reuse-checked: fx-canon (live ~/.local/bin/fx) -- its PRIV2 privacy-guard test, landed with the live script
"""PRIV2 as it runs since Kevin 2026-11-10 ("personal data can go to paid gpt as long as its not pii or
phi"; "just give it access same as yourself"). fx (GPT) runs through fx-canon, which prepends the
owner canon, refuses briefs carrying PII/PHI (tier T2+) or marked sensitive, fails closed when the
detector cannot load, and masks owner stores in bwrap only when FX_PRIVACY_MASK=1.
Scratch fixture home and a fixture detector only; a fake fx probes what a GPT session could reach."""
import json, os, shutil, subprocess, sys, tempfile, unittest
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

# Stands in for the tier classifier's pcls/detect.py: hit names are what fx-canon keys on.
FAKE_DETECT = """def detect(text):
    hits = {}
    if "@" in text: hits["contact:email"] = 1
    if "my diagnosis" in text: hits["cue:health_self"] = 1
    if "landlord" in text: hits["cue:personal"] = 1
    return {"hits": hits}
"""


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
        det = self.t / "detect" / "pcls"; det.mkdir(parents=True)
        (det / "__init__.py").write_text(""); (det / "detect.py").write_text(FAKE_DETECT)
        self.out = self.t / "probe.json"
        self.env = {**{k: v for k, v in os.environ.items() if k != "FX_PRIVACY_MASK"}, "HOME": str(h), "FX_BIN": str(fx), "OWNER_CANON_BLOCK": str(canon),
                    "CTX_DATA_ROOT": str(self.ctx), "AGENTSVIEW_DATA_DIR": str(self.av),
                    "FX_PRIVACY_OPS": str(self.ops), "FX_PRIVACY_LOG": str(self.t / "refusals.jsonl"),
                    "FX_PRIVACY_DETECT": str(self.t / "detect"),
                    "PATH": f"{bin_}:{os.environ['PATH']}", "PROBE_OUT": str(self.out),
                    "PROBE_PATHS": json.dumps(list(self.secret.values()) + [str(self.code)])}

    def run_fx(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(GUARD), *args], env=self.env, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def probe(self):
        res = json.loads(self.out.read_text())
        return res, {k: v for k, v in res["reads"].items() if "OWNER-SECRET" in v}

    def test_personal_brief_runs_with_canon_and_same_access_as_claude(self):
        r = self.run_fx("ask", "--model", "gpt-6.1-terra", "draft a reply to my landlord about the lease")
        self.assertEqual(r.returncode, 0, r.stderr)
        res, readable = self.probe()
        self.assertTrue(res["canon"])
        self.assertEqual(set(readable), set(self.secret.values()))              # unmasked by default
        self.assertEqual(res["reads"][str(self.code)], "print('ok')")

    def test_pii_phi_and_marked_briefs_are_refused_without_content_in_receipts(self):
        for brief in ["email the summary to someone@example.com",
                      "plan meals around my diagnosis",
                      "[pii] tidy the landlord thread",
                      "privacy: sensitive\nsummarize my week"]:
            with self.subTest(brief=brief):
                r = self.run_fx("ask", brief)
                self.assertEqual(r.returncode, 3, brief)
                self.assertIn("PRIV2", r.stderr)
        self.assertFalse(self.out.exists())
        log = (self.t / "refusals.jsonl").read_text()
        self.assertEqual(len(log.splitlines()), 4)
        self.assertNotIn("example.com", log)
        self.assertNotIn("diagnosis", log)

    def test_stdin_brief_is_checked_too(self):
        r = self.run_fx("ask", stdin="forward this to someone@example.com")
        self.assertEqual(r.returncode, 3); self.assertFalse(self.out.exists())

    def test_missing_detector_refuses_everything(self):
        self.env["FX_PRIVACY_DETECT"] = str(self.t / "nowhere")
        r = self.run_fx("ask", "fix the off-by-one in src/app.py")
        self.assertEqual(r.returncode, 3)
        self.assertIn("detector_unavailable", (self.t / "refusals.jsonl").read_text())

    def test_missing_canon_block_stops_fx(self):
        self.env["OWNER_CANON_BLOCK"] = str(self.t / "none.md")
        self.assertEqual(self.run_fx("ask", "fix src/app.py").returncode, 2)

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap not installed")
    def test_mask_mode_hides_owner_stores_and_shims_tools(self):
        self.env["FX_PRIVACY_MASK"] = "1"
        r = self.run_fx("ask", "fix the off-by-one in src/app.py and add a test")
        self.assertEqual(r.returncode, 0, r.stderr)
        res, readable = self.probe()
        self.assertEqual(readable, {})
        self.assertEqual(res["reads"][str(self.code)], "print('ok')")
        self.assertTrue(all(v not in (0, "missing") for v in res["cmds"].values()), res["cmds"])
        r = self.run_fx("session", "resume", "last")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.probe()[1], {})


if __name__ == "__main__":
    unittest.main()
