"""Offline contract test: run the real runner against a fake phone-queue API (no phone, no models).

python3 -m unittest discover -s services/phone-queue/evals/tests
"""
import json, os, sys, tempfile, threading, unittest, itertools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import run_suite, summarize  # noqa: E402

JOBS, SEEN_KEYS = {}, {}
ids = itertools.count(1)

def outcome(body):
    """Deterministic fake outcomes keyed by model, to exercise every row status."""
    m = body["model"]
    if m.endswith("terra"):
        return "failed", None, {"code": "model_unavailable", "message": "unknown model"}
    if m.endswith("sol"):
        return "succeeded", {"final_output": "done", "steps": 3, "oracle_pass": True, "ms": 9000, "cold_ms": 0,
                             "tokens_in": 1200, "tokens_out": 80, "transcript_path": None}, None
    # luna: passes clock tasks, false "done" elsewhere, abstains on files
    if "files" in body["oracle"].get("package", ""):
        return "failed", {"final_output": "ABSTAIN: not sure", "steps": 1, "oracle_pass": False, "ms": 3000}, {"code": "abstained"}
    ok = "clock" in body["oracle"].get("package", "")
    return "succeeded", {"final_output": "done", "steps": 2, "oracle_pass": ok, "ms": 5000, "cold_ms": 1500 if not JOBS else 0}, None

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/healthz": return self.send(200, {"ok": True})
        if self.path == "/v1/devices": return self.send(200, [{"id": "s22", "online": True, "gate": {"allowed": True}}])
        jid = self.path.rsplit("/", 1)[-1]
        return self.send(200, JOBS[jid]) if jid in JOBS else self.send(404, {"error": "not found"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])) or b"{}")
        if self.path.endswith("/cancel"): return self.send(200, {})
        for k in ("kind", "device", "goal", "submitter", "oracle", "model", "reset"):
            assert k in body, k
        assert body["kind"] == "goal" and body["reset"] == "home" and "Read-only task" in body["goal"]
        key = body["idempotency_key"]
        if key in SEEN_KEYS: return self.send(202, {"id": SEEN_KEYS[key], "state": JOBS[SEEN_KEYS[key]]["state"]})
        jid = f"j{next(ids)}"; st, res, err = outcome(body)
        JOBS[jid] = {"id": jid, "kind": "goal", "device": body["device"], "state": st, "submitter": body["submitter"],
                     "model": body["model"], "created_at": "t", "started_at": "t", "finished_at": "t", "result": res, "error": err}
        SEEN_KEYS[key] = jid
        return self.send(202, {"id": jid, "state": "queued"})

class RunnerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.srv.server_address[1]}"
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()

    def test_run_and_summarize(self):
        out = tempfile.mkdtemp()
        args = ["run", "--api", self.api, "--out", out, "--models", "luna,terra,sol,gateway-small",
                "--tasks", "clock-open,clock-timer,about-legal,files-dcim", "--reps", "2", "--no-drift", "--run-id", "T"]
        os.environ.pop("AI_GATEWAY_API_KEY", None)
        self.assertEqual(run_suite.main(args), 0)
        rows = [json.loads(l) for l in open(f"{out}/rows.jsonl")]
        self.assertEqual(len(rows), 4 * 4 * 2)
        n_jobs = len(JOBS)
        self.assertEqual(run_suite.main(args), 0)  # resume: nothing resubmitted
        self.assertEqual(len(JOBS), n_jobs)
        self.assertEqual(len(open(f"{out}/rows.jsonl").read().splitlines()), 32)
        s = summarize.summarize(rows)["models"]
        self.assertEqual(s["terra"]["status"], "unavailable")          # not a 0
        self.assertNotIn("oracle_success", s["terra"])
        self.assertEqual(s["gateway-small"]["status"], "unavailable")  # preflight: no key
        self.assertEqual(s["sol"]["oracle_success"], 1.0)
        luna = s["luna"]
        self.assertEqual(luna["oracle_success"], 0.5)                  # 2 clock tasks of 4
        self.assertEqual(luna["abstain_rate"], 0.25)                   # files task
        self.assertEqual(luna["false_done_rate"], 0.25)                # about-legal claimed done, oracle false
        self.assertEqual(luna["cold_rows"], 1)

    def test_classify(self):
        self.assertEqual(run_suite.classify(None, True), "timeout")
        self.assertEqual(run_suite.classify({"state": "blocked"}, False), "blocked")
        self.assertEqual(run_suite.classify({"state": "failed", "error": "401 Unauthorized"}, False), "unavailable")

    def test_drift_ignores_volatile(self):
        self.assertEqual(run_suite.drift({"system/a": "1"}, {"system/a": "2"}), ["system/a"])
        self.assertIsNone(run_suite.drift(None, {}))

if __name__ == "__main__":
    unittest.main()
