"""Offline tests for the review-round-2 fixes (no phone, no cluster):
reply harvest, chat verdicts, both UI locks, auth, cancel ownership, reconcile races, shim tokens."""
import fcntl
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
TMP = tempfile.mkdtemp(prefix="phoneq-test-")
os.environ["PHONEQ_STATE"] = TMP + "/state"
os.environ["PHONEQ_AUTH_DIR"] = TMP + "/auth"
import common  # noqa: E402

common = importlib.reload(common)
import runner  # noqa: E402
import server  # noqa: E402


def chat_tree(tag, prompt, reply_lines, realistic=True):
    """A ChatGPT screen: tag bubble, TASK bubble (right column), reply (left margin), composer."""
    b = (lambda l, t: f"[{l},{t}][990,{t + 40}]") if realistic else (lambda l, t: "[0,0][9,9]")
    rows = [f'<node class="android.widget.TextView" package="com.android.systemui" text="9:37" bounds="{b(73, 22)}"/>',
            f'<node class="android.widget.TextView" package="com.openai.chatgpt" text="Phone queue (tag {tag})." '
            f'bounds="{b(303, 318)}"/>',
            f'<node class="android.widget.TextView" package="com.openai.chatgpt" text="TASK: {prompt}" '
            f'bounds="{b(303, 400)}"/>']
    for i, line in enumerate(reply_lines):
        rows.append(f'<node class="android.widget.TextView" package="com.openai.chatgpt" text="{line}" '
                    f'content-desc="{line}" bounds="{b(42, 578 + 60 * i)}"/>')
    rows += ['<node class="android.view.View" package="com.openai.chatgpt" content-desc="Copy" bounds="[22,689][117,784]"/>',
             '<node class="android.widget.EditText" package="com.openai.chatgpt" text="Ask ChatGPT" bounds="[0,2100][9,2200]"/>']
    return ET.fromstring("<hierarchy>" + "".join(rows) + "</hierarchy>")


def sent_text(tag, prompt):
    return f"Phone queue (tag {tag}).\n\nTASK: {prompt}"


class ReplyHarvest(unittest.TestCase):
    CASES = [("Repeat exactly: hello world", "hello world"),
             ("Reply with only the word OK", "OK"),
             ("What is 7 times 6? Answer: 42 or 43", "42"),
             ("Say Copy", "Copy"),
             ("Say Stop", "Stop"),
             ("Reply with one short line: PHONEQ-OK followed by the result of 5 times 9.", "PHONEQ-OK 45")]

    def test_echo_and_short_replies_realistic_bounds(self):
        for prompt, reply in self.CASES:
            with self.subTest(prompt=prompt):
                root = chat_tree("PQ-X", prompt, [reply])
                self.assertEqual(runner.reply_from_tree(root, "PQ-X", sent_text("PQ-X", prompt)), reply)

    def test_echo_and_short_replies_without_geometry(self):
        for prompt, reply in self.CASES:
            with self.subTest(prompt=prompt):
                root = chat_tree("PQ-X", prompt, [reply], realistic=False)
                self.assertEqual(runner.reply_from_tree(root, "PQ-X", sent_text("PQ-X", prompt)), reply)

    def test_prompt_line_and_clock_never_in_reply(self):
        prompt = "Reply with one short line: PHONEQ-OK followed by the result of 7 times 6."
        out = runner.reply_from_tree(chat_tree("PQ-A", prompt, ["PHONEQ-OK 42"]), "PQ-A", sent_text("PQ-A", prompt))
        self.assertEqual(out, "PHONEQ-OK 42")

    def test_multi_paragraph_prompt_and_reply(self):
        prompt = "line one\n\nline two"
        root = ET.fromstring(
            '<hierarchy>'
            '<node class="TextView" package="p" text="Phone queue (tag PQ-M)." bounds="[303,300][700,340]"/>'
            '<node class="TextView" package="p" text="TASK: line one" bounds="[303,360][700,400]"/>'
            '<node class="TextView" package="p" text="line two" bounds="[303,420][700,460]"/>'
            '<node class="TextView" package="p" text="line two" bounds="[42,520][1000,560]"/>'
            '<node class="TextView" package="p" text="and more" bounds="[42,580][1000,620]"/>'
            '</hierarchy>')
        self.assertEqual(runner.reply_from_tree(root, "PQ-M", sent_text("PQ-M", prompt)), "line two\nand more")

    def test_real_redacted_trees(self):
        """The three live trees from round 1 (groot state/jobs/*/reply-tree.xml), when present."""
        jobs = Path("/mnt/zer0models/phone-queue/state/jobs")
        want = {"a9b46fc009af": ("7 times 6", "PHONEQ-OK 42"), "9ba2d89d90c2": ("9 times 8", "PHONEQ-OK 72"),
                "db3af9a018b2": ("5 times 9", "PHONEQ-OK 45")}
        seen = 0
        for jid, (math, reply) in want.items():
            path = jobs / jid / "reply-tree.xml"
            if not path.exists():
                continue
            seen += 1
            tag = "PQ-" + jid[:10].upper()
            prompt = f"Reply with one short line: PHONEQ-OK followed by the result of {math}."
            got = runner.reply_from_tree(ET.parse(path).getroot(), tag, sent_text(tag, prompt))
            self.assertEqual(got, reply, jid)
        if not seen:
            self.skipTest("live trees not on this host")


class ChatVerdict(unittest.TestCase):
    def verdict(self, **chat):
        result = {}
        ok = runner.chat_outcome(chat.pop("app", "chatgpt"), "PQ-T", {"app": "chatgpt", **chat}, result)
        return ok, result

    def test_sent_with_reply_succeeds(self):
        ok, res = self.verdict(send_status="sent", reply="OK", still_running=False)
        self.assertTrue(ok)
        self.assertEqual(res["final_output"], "OK")

    def test_sent_still_running_fails(self):
        ok, res = self.verdict(send_status="sent", reply=None, still_running=True)
        self.assertFalse(ok)
        self.assertEqual(res["error_code"], "reply_timeout")
        self.assertIn("do not resend", res["error"])

    def test_sent_no_reply_fails(self):
        ok, res = self.verdict(send_status="sent", reply=None, still_running=False)
        self.assertFalse(ok)
        self.assertEqual(res["error_code"], "reply_not_harvested")

    def test_rate_limited_fails(self):
        ok, res = self.verdict(send_status="rate_limited")
        self.assertFalse(ok)
        self.assertEqual(res["error_code"], "rate_limited")

    def test_deepseek_dispatch_only_is_explicit(self):
        ok, res = self.verdict(app="deepseek", send_status="sent", reply=None)
        self.assertTrue(ok)
        self.assertIn("dispatch only", res["final_output"])
        self.assertFalse(res["chat"]["reply_harvested"])


class UiLocks(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="home-"))
        self._home, common.HOME = common.HOME, self.home
        self.dev = "t" + os.urandom(3).hex()

    def tearDown(self):
        common.HOME = self._home

    def test_both_locks_order(self):
        paths = runner.ui_lock_paths(self.dev)
        self.assertEqual(paths[0], self.home / "tmp" / f"{self.dev}-ui.lock")
        self.assertEqual(str(paths[1]), f"/tmp/{self.dev}-ui.lock")

    def test_dash_test_lock_blocks_the_job(self):
        outer = runner.ui_lock_paths(self.dev)[0]
        outer.parent.mkdir(exist_ok=True)
        with open(outer, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            with self.assertRaises(runner.Blocked) as cm:
                runner.take_lock(self.dev, wait_s=1)
            self.assertIn(str(outer), str(cm.exception))

    def test_takes_and_releases_both(self):
        held, _ = runner.take_lock(self.dev, wait_s=1)
        for path in runner.ui_lock_paths(self.dev):
            with open(path, "a") as f, self.assertRaises(BlockingIOError):
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runner.release_lock(held)
        held, _ = runner.take_lock(self.dev, wait_s=1)  # free again
        runner.release_lock(held)


class FakeKube:
    def __init__(self):
        self.created, self.deleted, self.conflict = [], [], False
        self.existing = {}

    def jobs_path(self, name=""):
        return "/jobs/" + name

    def req(self, method, path, body=None, params=None):
        if method == "POST":
            if self.conflict:
                raise RuntimeError(f"k8s POST {path}: HTTP 409: AlreadyExists")
            self.created.append(body["metadata"]["name"])
            if self.on_post:
                self.on_post()
            return body
        if method == "DELETE":
            self.deleted.append(path.rsplit("/", 1)[1])
            return {}
        if method == "GET":
            return self.existing.get(path.rsplit("/", 1)[1])
        return None

    on_post = None


class ServerAuthAndRaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        auth = Path(os.environ["PHONEQ_AUTH_DIR"])
        auth.mkdir(parents=True, exist_ok=True)
        import hashlib
        (auth / "tokens.json").write_text(json.dumps({
            hashlib.sha256(b"agent-tok").hexdigest(): {"principal": "agents", "admin": False},
            hashlib.sha256(b"other-tok").hexdigest(): {"principal": "other", "admin": False},
            hashlib.sha256(b"owner-tok").hexdigest(): {"principal": "owner", "admin": True}}))
        server.CONN = server.db()
        server.gate = lambda dev: None
        server.model_check = lambda m: (None, None)

    def setUp(self):
        server.KUBE = self.kube = FakeKube()

    def submit(self, submitter="a/x", principal="agents"):
        code, out = server.submit({"kind": "goal", "device": "s22", "goal": "g", "submitter": submitter}, principal)
        self.assertEqual(code, 202)
        return out["id"]

    def row(self, jid):
        return server.q("SELECT * FROM jobs WHERE id=?", (jid,))[0]

    def test_who(self):
        self.assertIsNone(server.who({}))
        self.assertIsNone(server.who({"authorization": "Bearer nope"}))
        self.assertEqual(server.who({"authorization": "Bearer agent-tok"})["principal"], "agents")
        self.assertTrue(server.who({"authorization": "Bearer owner-tok"})["admin"])

    def test_cancel_needs_owner(self):
        jid = self.submit("a/x")
        agents = {"principal": "agents", "admin": False}
        self.assertEqual(server.cancel(jid, {"principal": "other", "admin": False}, {"submitter": "a/x"})[0], 403)
        self.assertEqual(server.cancel(jid, agents, {"submitter": "a/y"})[0], 403)
        self.assertEqual(server.cancel(jid, agents, {})[0], 403)
        self.assertEqual(server.cancel(jid, agents, {"submitter": "a/x"})[0], 200)
        jid2 = self.submit("b/z")
        self.assertEqual(server.cancel(jid2, {"principal": "owner", "admin": True}, None)[0], 200)

    def test_unauthenticated_read_has_no_result(self):
        jid = self.submit()
        server.q("UPDATE jobs SET state='succeeded', result=? WHERE id=?",
                 (json.dumps({"final_output": "secret screen text", "steps": 3, "oracle_pass": True,
                              "chat": {"reply": "r"}}), jid))
        pub = server.row_to_job(self.row(jid), full=False)
        self.assertEqual(pub["result"], {"steps": 3, "oracle_pass": True})
        self.assertTrue(pub["result_redacted"])
        self.assertEqual(server.row_to_job(self.row(jid))["result"]["final_output"], "secret screen text")

    def test_cancel_during_create_wins(self):
        jid = self.submit()
        snapshot = self.row(jid)
        # the cancel lands between the reconciler's snapshot and its UPDATE (inside the POST)
        self.kube.on_post = lambda: server.cancel(jid, {"principal": "owner", "admin": True}, None)
        server.create_k8s_job(snapshot)
        self.assertEqual(self.row(jid)["state"], "cancelled")
        self.assertEqual(self.kube.deleted, self.kube.created)  # the just-created Job was removed

    def test_terminal_rows_never_overwritten(self):
        jid = self.submit()
        server.q("UPDATE jobs SET state='cancelled' WHERE id=?", (jid,))
        self.assertEqual(server.qlive("UPDATE jobs SET state='running' WHERE id=?", (jid,)), 0)
        self.assertEqual(self.row(jid)["state"], "cancelled")

    def test_409_adopts_own_orphan(self):
        jid = self.submit()
        r = self.row(jid)
        name = f"pq-{jid}-1"
        self.kube.conflict = True
        self.kube.existing[name] = {"metadata": {"name": name, "labels": {"z0.dev/phoneq-id": jid}}}
        server.create_k8s_job(r)
        row = self.row(jid)
        self.assertEqual(row["k8s_job"], name)
        self.assertEqual(row["attempts"], 1)
        self.assertIn("adopted", row["info"])

    def test_409_foreign_job_raises(self):
        jid = self.submit()
        self.kube.conflict = True
        self.kube.existing[f"pq-{jid}-1"] = {"metadata": {"labels": {"z0.dev/phoneq-id": "ffffffffffff"}}}
        with self.assertRaises(RuntimeError):
            server.create_k8s_job(self.row(jid))

    def test_infra_trouble_blocks_without_a_k8s_job(self):
        jid = self.submit()
        old = server.model_check
        try:
            server.model_check = lambda m: ("blocked", "infra: model shim HTTP 503: infra_unavailable: x")
            server.create_k8s_job(self.row(jid))
        finally:
            server.model_check = old
        row = self.row(jid)
        self.assertEqual((row["state"], row["k8s_job"]), ("blocked", None))
        self.assertEqual(self.kube.created, [])

    def test_deadline_covers_runner_budget(self):
        m = server.k8s_job_manifest(self.row(self.submit()), ["s22"])
        budget = runner.LOCK_WAIT_S + runner.PACE_WAIT_S + runner.REPLY_WAIT_S + runner.FX_TIMEOUT_S + 60
        self.assertGreater(m["spec"]["activeDeadlineSeconds"], budget)
        vols = {v["name"]: v for v in m["spec"]["template"]["spec"]["volumes"]}
        self.assertEqual([i["key"] for i in vols["auth"]["secret"]["items"]], ["shim-key"])


class ShimTokens(unittest.TestCase):
    def setUp(self):
        sys.argv = sys.argv[:1]
        import model_shim
        self.shim = model_shim
        self.shim.STATE = Path(TMP) / "shimstate"
        self.shim.AUTH_DIR = Path(TMP) / "shimauth"
        self.shim.AUTH_DIR.mkdir(exist_ok=True)
        (self.shim.AUTH_DIR / "shim-key").write_text("k" * 64)
        self.jid = "abcabcabcabc"
        (self.shim.STATE / "jobs" / self.jid).mkdir(parents=True, exist_ok=True)
        (self.shim.STATE / "jobs" / self.jid / "job.json").write_text("{}")

    def hdr(self, tok):
        return {"authorization": f"Bearer {tok}"}

    def test_valid_job_token(self):
        tok = common.job_token(self.jid, 2, b"k" * 64)
        self.assertEqual(self.shim.job_of(self.hdr(tok)), self.jid)

    def test_rejects_forged_old_and_finished(self):
        self.assertIsNone(self.shim.job_of({}))
        self.assertIsNone(self.shim.job_of(self.hdr("phoneq-job-" + self.jid)))  # round-1 format
        self.assertIsNone(self.shim.job_of(self.hdr(common.job_token(self.jid, 2, b"wrong"))))
        tok = common.job_token(self.jid, 3, b"k" * 64)
        (self.shim.STATE / "jobs" / self.jid / "result-3.json").write_text("{}")
        self.assertIsNone(self.shim.job_of(self.hdr(tok)))

    def test_catalog_outage_is_infra_not_unavailable(self):
        self.shim._local_models.update(llama=set(), llama_ok=False, llama_at=0)
        self.shim.LLAMA = "http://127.0.0.1:9"  # nothing listens
        err = self.shim.available("groot-router/qwen3-0.6b-q8")
        self.assertEqual(err.status, 503)
        self.assertIn("infra_unavailable", str(err))


class FirmwareIds(unittest.TestCase):
    RAW = """<hierarchy><node package="com.android.settings" class="FrameLayout">
      <node class="LinearLayout"><node class="TextView" text="Build number"/>
        <node class="TextView" text="BP2A.250605.031.S906U1UES9FZB4"/></node>
      <node class="LinearLayout"><node class="TextView" text="IMEI"/>
        <node class="TextView" text="352099001761481"/></node>
      <node class="LinearLayout"><node class="TextView" text="Device name token"/>
        <node class="TextView" text="Zk3mQ9vLx2Pq7RtY8wBn4Hs"/></node>
    </node></hierarchy>"""

    def test_build_number_restored_secrets_stay(self):
        if not common.PHONE_SCREEN_SAFE.exists():
            self.skipTest("phone-screen-safe not on this host")
        import phone_tools
        raw = ET.fromstring(self.RAW)
        red = ET.fromstring(phone_tools.pss().redact_xml(self.RAW)[0])
        phone_tools.restore_firmware_ids(raw, red)
        texts = [n.get("text") for n in red.iter("node") if n.get("text")]
        self.assertIn("BP2A.250605.031.S906U1UES9FZB4", texts)
        self.assertNotIn("352099001761481", texts)          # IMEI (Luhn) stays redacted
        self.assertNotIn("Zk3mQ9vLx2Pq7RtY8wBn4Hs", texts)  # not a firmware title

    SAMSUNG = """<hierarchy><node package="com.android.settings" class="FrameLayout">
      <node class="RelativeLayout"><node class="RelativeLayout" resource-id="com.android.settings:id/title_frame">
          <node class="TextView" resource-id="android:id/title" text="Build number"/></node>
        <node class="TextView" resource-id="android:id/summary" text="BP2A.250605.031.S906U1UES9FZB4"/></node>
      <node class="RelativeLayout"><node class="RelativeLayout" resource-id="com.android.settings:id/title_frame">
          <node class="TextView" resource-id="android:id/title" text="Device token"/></node>
        <node class="TextView" resource-id="android:id/summary" text="BP2A.250605.031.S906U1UES9FZB5"/></node>
    </node></hierarchy>"""

    def test_samsung_nested_title_frame(self):
        if not common.PHONE_SCREEN_SAFE.exists():
            self.skipTest("phone-screen-safe not on this host")
        import phone_tools
        raw = ET.fromstring(self.SAMSUNG)
        red = ET.fromstring(phone_tools.pss().redact_xml(self.SAMSUNG)[0])
        self.assertEqual(phone_tools.restore_firmware_ids(raw, red), 1)
        texts = [n.get("text") for n in red.iter("node") if n.get("text")]
        self.assertIn("BP2A.250605.031.S906U1UES9FZB4", texts)
        self.assertNotIn("BP2A.250605.031.S906U1UES9FZB5", texts)  # same shape, wrong title


class Pacing(unittest.TestCase):
    def test_every_chat_harness_is_paced(self):
        P = runner.paced_app
        self.assertEqual(P({"kind": "chat", "harness": "fx", "app": None}), "chatgpt")
        self.assertEqual(P({"kind": "chat", "harness": "fx", "app": "chatgpt"}), "chatgpt")
        self.assertEqual(P({"kind": "chat", "harness": "script", "app": "deepseek"}), "deepseek")
        self.assertEqual(P({"kind": "goal", "app": "com.openai.chatgpt"}), "chatgpt")
        self.assertIsNone(P({"kind": "goal", "app": None}))
        self.assertIsNone(P({"kind": "chat", "harness": "fx", "app": "org.telegram.messenger"}))


if __name__ == "__main__":
    unittest.main()
