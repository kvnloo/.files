"""Round-3 review fixes, offline: settings navigation-only taps, slider swipes, public errors,
idempotency conflicts, gate blocks, pacing without slot burn, chat oracle scope."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_tools  # noqa: E402
import runner  # noqa: E402

P = phone_tools


def settings_with(rows_xml, pkg="com.android.settings"):
    return ET.fromstring(f'<hierarchy><node class="android.widget.FrameLayout" package="{pkg}" '
                         f'bounds="[0,0][1080,2340]">{rows_xml}</node></hierarchy>')


def button(label, y, cls="android.widget.Button", pkg="com.android.settings"):
    return (f'<node class="{cls}" package="{pkg}" text="{label}" clickable="true" '
            f'bounds="[100,{y}][980,{y + 100}]"/>')


def row(title, y, summary=None, pkg="com.android.settings"):
    s = (f'<node class="android.widget.TextView" package="{pkg}" resource-id="android:id/summary" '
         f'text="{summary}" bounds="[60,{y + 60}][900,{y + 100}]"/>') if summary else ""
    return (f'<node class="android.widget.LinearLayout" package="{pkg}" clickable="true" bounds="[0,{y}][1080,{y + 120}]">'
            f'<node class="android.widget.TextView" package="{pkg}" resource-id="android:id/title" text="{title}" '
            f'bounds="[60,{y + 10}][900,{y + 60}]"/>{s}</node>')


class SettingsTapGuard(unittest.TestCase):
    """The reviewer's repro: every one of these Button rows used to be ALLOWED."""

    def phone(self, root, pkg="com.android.settings"):
        ph = P.Phone(None, "s22")
        ph.root, ph.pkg = root, pkg
        return ph

    def test_reviewer_buttons_all_refused_in_settings(self):
        labels = ["Apply", "Restart", "Power off", "Start now", "Connect", "OK", "Delete", "Delete chat",
                  "Remove", "Turn on", "Done", "Pay", "Reset", "Allow"]
        root = settings_with("".join(button(lab, 300 + i * 120) for i, lab in enumerate(labels)))
        ph = self.phone(root)
        for i, lab in enumerate(labels):
            r = {"text": lab, "desc": "", "id": "", "cls": "Button", "flags": ["click"], "x": 540, "y": 350 + i * 120}
            with self.assertRaises(P.Refused, msg=lab):
                ph._check_tap(r)

    def test_textless_row_containers_judged_by_their_title(self):
        # Samsung/AOSP rows: a clickable LinearLayout with no text of its own around a title TextView.
        root = settings_with(row("Reset", 300) + row("Connect wirelessly", 420) + row("Build number", 540)
                             + row("About phone", 660) + row("Display", 780, "Light mode")
                             + row("Battery", 900, "Power saving off") + row("Samsung DeX", 1020))
        ph = self.phone(root)
        def tap_row(y):
            ph._check_tap({"text": "", "desc": "", "id": "", "cls": "LinearLayout", "flags": ["click"], "x": 540, "y": y})
        for y in (360, 480, 600):
            with self.assertRaises(P.Refused):
                tap_row(y)
        for y in (720, 840, 960):  # navigation rows stay allowed
            tap_row(y)
        with self.assertRaises(P.Refused):  # Samsung DeX: leads to Connect wirelessly / scans
            tap_row(1080)

    def test_dex_page_served_by_launcher_is_a_settings_screen(self):
        root = settings_with(row("Connect wirelessly", 300) + button("Start now", 500)
                             + '<node class="android.widget.TextView" package="com.sec.android.app.launcher" '
                               'text="Samsung DeX" bounds="[0,100][1080,200]"/>', pkg="com.sec.android.app.launcher")
        self.assertTrue(P.settings_context("com.sec.android.app.launcher", root))
        for y in (360, 550):
            with self.assertRaises(P.Refused):
                P.check_tap(root, "com.sec.android.app.launcher", 540, y)

    def test_navigate_up_allowed_dialog_refuses_everything(self):
        nav = ('<node class="android.widget.ImageButton" package="com.android.settings" content-desc="Navigate up" '
               'clickable="true" bounds="[0,100][150,250]"/>')
        root = settings_with(nav + row("About phone", 300))
        P.check_tap(root, "com.android.settings", 70, 170)
        dlg = ('<node class="android.widget.FrameLayout" package="com.android.settings" resource-id="android:id/parentPanel" '
               'bounds="[100,800][980,1400]">' + button("Cancel", 1250) + '</node>')
        root = settings_with(nav + row("About phone", 300) + dlg)
        with self.assertRaises(P.Refused):
            P.check_tap(root, "com.android.settings", 540, 360)

    def test_slider_tap_and_systemui_refused_anywhere(self):
        root = ET.fromstring('<hierarchy><node package="com.openai.chatgpt" class="android.widget.FrameLayout" bounds="[0,0][1080,2340]">'
                             '<node class="android.widget.SeekBar" package="com.openai.chatgpt" bounds="[0,1000][1080,1100]"/>'
                             '<node class="android.widget.TextView" package="com.android.systemui" text="9:41" clickable="true" bounds="[0,0][200,80]"/>'
                             '</node></hierarchy>')
        with self.assertRaises(P.Refused):
            P.check_tap(root, "com.openai.chatgpt", 540, 1050)
        with self.assertRaises(P.Refused):
            P.check_tap(root, "com.openai.chatgpt", 50, 40)

    def test_chat_app_buttons_still_work_and_message_text_does_not_block(self):
        long_row = ('<node class="android.widget.LinearLayout" package="com.openai.chatgpt" clickable="true" bounds="[0,300][1080,700]">'
                    + "".join(f'<node class="android.widget.TextView" package="com.openai.chatgpt" text="line {i} how to delete files" '
                              f'bounds="[0,{300 + i * 50}][1080,{350 + i * 50}]"/>' for i in range(6)) + '</node>')
        root = ET.fromstring('<hierarchy><node package="com.openai.chatgpt" class="android.widget.FrameLayout" bounds="[0,0][1080,2340]">'
                             + button("Send", 2000, pkg="com.openai.chatgpt") + button("OK", 1800, pkg="com.openai.chatgpt")
                             + long_row + '</node></hierarchy>')
        self.assertFalse(P.settings_context("com.openai.chatgpt", root))
        P.check_tap(root, "com.openai.chatgpt", 540, 2050)
        P.check_tap(root, "com.openai.chatgpt", 540, 1850)
        with self.assertRaises(P.Refused):  # first line of the row is its title: "...delete..."
            P.check_tap(root, "com.openai.chatgpt", 540, 500)
        root2 = ET.fromstring(ET.tostring(root).decode().replace("how to delete files", "hello"))
        P.check_tap(root2, "com.openai.chatgpt", 540, 500)

    def test_swipes(self):
        bright = settings_with('<node class="android.widget.SeekBar" package="com.android.settings" '
                               'resource-id="com.android.settings:id/seekbar" bounds="[100,1100][980,1240]"/>')
        with self.assertRaises(P.Refused):
            P.check_swipe(bright, "com.android.settings", "left", 0.6, (1080, 2340))
        with self.assertRaises(P.Refused):  # vertical path through the centre crosses the slider
            P.check_swipe(bright, "com.android.settings", "up", 0.6, (1080, 2340))
        plain = settings_with(row("About phone", 300))
        P.check_swipe(plain, "com.android.settings", "up", 0.6, (1080, 2340))
        with self.assertRaises(P.Refused):
            P.check_swipe(plain, "com.android.settings", "right", 0.6, (1080, 2340))


class SetTextByReference(unittest.TestCase):
    def test_from_job_prompt_types_exact_long_text(self):
        long = "Ünïcode ✓ " + "x" * 16330
        with tempfile.TemporaryDirectory() as t:
            Path(t, "job.json").write_text(json.dumps({"prompt": long}))
            typed = {}

            class El:
                exists = True
                def set_text(self, v): typed["v"] = v
                def get_text(self): return typed.get("v")

            class D:
                def __call__(self, **_k): return El()
                def dump_hierarchy(self):
                    return ('<hierarchy><node package="com.openai.chatgpt" class="android.widget.EditText" '
                            'focused="true" clickable="true" bounds="[0,2000][1080,2100]"/></hierarchy>')
            os.environ["PHONEQ_JOB_DIR"] = t
            try:
                ph = P.Phone(D(), "s22")
                ph._settle = lambda s=0: None
                out = ph.set_text({"from_job_prompt": True})
            finally:
                del os.environ["PHONEQ_JOB_DIR"]
        self.assertEqual(typed["v"], long)
        self.assertIn(str(len(long)), out)


class PacePeek(unittest.TestCase):
    def test_peek_never_reserves_reserve_does(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "bin").mkdir()
            src = Path(runner.common.DRIVER / "bin/pace.py")
            if not src.exists():
                self.skipTest("pace.py not on this host")
            (Path(t) / "bin/pace.py").write_text(src.read_text())
            old = runner.common.DRIVER
            runner.common.DRIVER = Path(t)
            try:
                ok, _ = runner.pace_check("chatgpt", peek=True)
                self.assertTrue(ok)
                self.assertFalse((Path(t) / "pace.reserved").exists())
                ok, _ = runner.pace_check("chatgpt", peek=False)
                self.assertTrue(ok)
                self.assertEqual(len((Path(t) / "pace.reserved").read_text().split()), 1)
                ok, _ = runner.pace_check("chatgpt", peek=True)  # 45 s gap now holds
                self.assertFalse(ok)
                self.assertEqual(len((Path(t) / "pace.reserved").read_text().split()), 1)
            finally:
                runner.common.DRIVER = old

    def test_reserve_happens_after_lock_and_regate(self):
        src = Path(runner.__file__).read_text()
        body = src[src.index("def main(job_id):"):]
        self.assertLess(body.index("pace_wait(paced"), body.index("take_lock(dev)"))
        self.assertLess(body.index("owner_busy(serial"), body.index("pace_reserve(paced)"))


class ConnectRetry(unittest.TestCase):
    def test_transient_drop_retried_persistent_drop_blocks(self):
        import http.client
        calls = {"n": 0}

        class PT:
            @staticmethod
            def connect(serial):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise http.client.RemoteDisconnected("Remote end closed connection without response")
                return "d"

        class B:
            @staticmethod
            def healthy(d):
                return None
        sleeps = []
        old = runner.time.sleep
        runner.time.sleep = sleeps.append
        try:
            res = {}
            self.assertEqual(runner.connect_healthy(PT, B, "S", res), "d")
            self.assertEqual(len(res["connect_retries"]), 2)
            calls["n"] = -10
            with self.assertRaises(runner.Blocked) as cm:
                runner.connect_healthy(PT, B, "S", {})
            self.assertTrue(str(cm.exception).startswith("infra: "))
        finally:
            runner.time.sleep = old


class ChatOracle(unittest.TestCase):
    def test_must_contain_is_checked_against_the_reply(self):
        tree = ('<hierarchy><node package="com.openai.chatgpt" class="android.widget.TextView" '
                'text="TASK: say PINEAPPLE" bounds="[0,0][9,9]"/><node package="com.openai.chatgpt" '
                'class="android.widget.TextView" text="no" bounds="[0,0][9,9]"/></hierarchy>')

        class D:
            def dump_hierarchy(self):
                return tree
        job = {"kind": "chat", "oracle": {"must_contain": ["PINEAPPLE"]}}
        res = {"final_output": "no", "chat": {"reply": "no"}}
        self.assertFalse(runner.oracle(job, D(), res))  # the prompt bubble alone no longer passes
        res = {"final_output": "PINEAPPLE", "chat": {"reply": "PINEAPPLE"}}
        self.assertTrue(runner.oracle(job, D(), res))

    def test_final_must_contain_checks_the_reported_value(self):
        class D:
            def dump_hierarchy(self):
                return ('<hierarchy><node package="com.android.settings" class="android.widget.TextView" '
                        'text="Android version" bounds="[0,0][9,9]"/></hierarchy>')
        job = {"kind": "goal", "oracle": {"must_contain": ["Android version"], "final_must_contain": ["16"]}}
        self.assertFalse(runner.oracle(job, D(), {"final_output": "Android version: 15"}))
        self.assertTrue(runner.oracle(job, D(), {"final_output": "Android version: 16"}))


class ServerRound3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_round2 import ServerAuthAndRaces as Server  # reuse its temp state + auth fixture
        Server.setUpClass()
        import server
        cls.server = server
        cls.Fake = __import__("test_round2").FakeKube

    def setUp(self):
        self.server.KUBE = self.Fake()

    def test_unauthenticated_error_never_carries_agent_text(self):
        s = self.server
        code, out = s.submit({"kind": "goal", "device": "s22", "goal": "g", "submitter": "r3/a"}, "agents")
        jid = out["id"]
        s.q("UPDATE jobs SET state='failed', error=?, result=? WHERE id=?",
            ("fx exit 1: Build number is SECRET123 and the phone says hello",
             json.dumps({"error_code": "step_limit", "steps": 30}), jid))
        row = s.q("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        pub = s.row_to_job(row, full=False)
        self.assertNotIn("SECRET123", json.dumps(pub))
        self.assertEqual(pub["error"], "step_limit (details need a token)")
        self.assertIn("SECRET123", s.row_to_job(row)["error"])
        s.q("UPDATE jobs SET error=? WHERE id=?", ("gate closed — s25: s25-worker-off present", jid))
        row = s.q("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        self.assertEqual(s.row_to_job(row, full=False)["error"], "gate closed — s25: s25-worker-off present")
        s.q("UPDATE jobs SET info=? WHERE id=?", ("reconcile error: KeyError: 'screen text'", jid))
        row = s.q("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        self.assertEqual(s.row_to_job(row, full=False)["info"], "(details need a token)")

    def test_idempotent_replay_with_a_different_body_conflicts(self):
        s = self.server
        b = {"kind": "goal", "device": "s22", "goal": "g1", "submitter": "r3/b", "idempotency_key": "K"}
        self.assertEqual(s.submit(b, "agents")[0], 202)
        self.assertEqual(s.submit(dict(b), "agents")[0], 200)
        code, out = s.submit({**b, "goal": "zzz different body"}, "agents")
        self.assertEqual(code, 409)
        self.assertIn("different job body", out["error"])

    def test_gate_blocks_never_fail_other_blocks_count(self):
        s = self.server
        _, out = s.submit({"kind": "goal", "device": "s25", "goal": "g", "submitter": "r3/c"}, "agents")
        jid = out["id"]
        jdir = s.common.job_dir(jid)
        s.q("UPDATE jobs SET attempts=?, state='running', k8s_job='x' WHERE id=?", (s.MAX_ATTEMPTS, jid))
        s.common.write_json(jdir / f"result-{s.MAX_ATTEMPTS}.json", {"state": "blocked", "error": "gate s25 (under lock): owner active"})
        s.finish_from_result(s.q("SELECT * FROM jobs WHERE id=?", (jid,))[0], None, None)
        self.assertEqual(s.q("SELECT state FROM jobs WHERE id=?", (jid,))[0]["state"], "blocked")
        # 1 gate block so far: attempt MAX counts as MAX-1 -> still retried; MAX+1 counts MAX -> fails
        for n, want in ((s.MAX_ATTEMPTS, "blocked"), (s.MAX_ATTEMPTS + 1, "failed")):
            s.q("UPDATE jobs SET attempts=?, state='running', k8s_job='x' WHERE id=?", (n, jid))
            s.common.write_json(jdir / f"result-{n}.json", {"state": "blocked", "error": "/tmp/s25-ui.lock busy for 900s"})
            s.finish_from_result(s.q("SELECT * FROM jobs WHERE id=?", (jid,))[0], None, None)
            self.assertEqual(s.q("SELECT state FROM jobs WHERE id=?", (jid,))[0]["state"], want)

    def test_unknown_oracle_keys_rejected(self):
        with self.assertRaises(self.server.Bad):
            self.server.validate({"kind": "goal", "goal": "g", "submitter": "x", "oracle": {"must_contian": ["a"]}})


if __name__ == "__main__":
    unittest.main()
