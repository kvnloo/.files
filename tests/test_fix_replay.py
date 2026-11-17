import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fix-replay"


def load(ops):
    os.environ["FIX_OPS"] = str(ops)
    loader = importlib.machinery.SourceFileLoader("fix_replay_under_test", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FixReplayCost(unittest.TestCase):
    def test_every_log_row_records_wall_time_so_heavy_tapes_are_findable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "quick", "tape": "true"},
                {"id": "slow-fail", "tape": "timeout 0.3 tail -f /dev/null; false"},
            ]}))
            load(ops).run()
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertIsInstance(rows["quick"]["ms"], int)
            self.assertGreaterEqual(rows["slow-fail"]["ms"], 250)
            self.assertFalse(rows["slow-fail"]["ok"])

    def test_a_malformed_row_fails_alone_and_the_rest_still_replay(self):
        # 2026-11-16 13:03: one row carried "env" as prose instead of an object; the TypeError aborted the
        # whole replay, so no tape was checked, the board went stale and nobody was paged.
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "prose-env", "tape": "true", "env": "needs XDG_RUNTIME_DIR"},
                {"id": "no-tape"},
                {"id": "fine", "tape": "true", "env": {"A": "1"}},
            ]}))
            load(ops).run()
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertTrue(rows["fine"]["ok"])
            self.assertFalse(rows["prose-env"]["ok"])
            self.assertIn("malformed tape row", rows["prose-env"]["out"])
            self.assertFalse(rows["no-tape"]["ok"])
            self.assertTrue((ops / "BOARD.md").exists())

    def test_use_must_be_a_read_only_counter(self):
        # 2026-11-16: a `use` of `systemctl --user start kvnloo-fork-sync.service` turned a daily GitHub sync
        # into an hourly one (14 starts/24 h, ~150 s each) and prose notes were executed as shell.
        with tempfile.TemporaryDirectory() as tmp:
            ops, stub = Path(tmp) / "ops", Path(tmp) / "bin"
            ops.mkdir(); stub.mkdir()
            marker = Path(tmp) / "started"
            (stub / "systemctl").write_text(f"#!/bin/sh\necho \"$@\" >> {marker}\necho 0\n")
            (stub / "systemctl").chmod(0o755)
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "mutating", "tape": "true", "use": "systemctl --user start some-sync.service"},
                {"id": "placeholder", "tape": "true", "use": "systemctl --user show -P OnFailure <unit>"},
                {"id": "counter", "tape": "true", "use": "echo 3"},
            ]}))
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{stub}:{old}"
            try:
                mod = load(ops)
                mod.run()
            finally:
                os.environ["PATH"] = old
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertFalse(marker.exists(), "a use command must never start or stop units")
            self.assertTrue(rows["mutating"]["use_refused"])
            self.assertTrue(rows["placeholder"]["use_refused"])
            self.assertEqual(rows["counter"]["uses"], 3)
            self.assertNotIn("use_refused", rows["counter"])
            state = json.loads((ops / "fix-state.json").read_text())
            self.assertTrue(state["mutating"]["use_refused"])
            self.assertIn("use refused", mod.board(state, 0))

    def test_a_retired_tape_leaves_the_board(self):
        # 2026-11-16: F12/F10/F21 were retired as superseded, but fix-state.json kept them, so the board
        # listed them "open" forever and the open count never fell.
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-state.json").write_text(json.dumps({"retired": {"since": 0, "ok": False, "uses": 0,
                                                                        "passes": 0, "fails": 9}}))
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [{"id": "kept", "tape": "true"}]}))
            load(ops).run()
            self.assertEqual(list(json.loads((ops / "fix-state.json").read_text())), ["kept"])
            self.assertNotIn("retired", (ops / "BOARD.md").read_text())


class FixReplayAtomicState(unittest.TestCase):
    def test_enospc_mid_write_keeps_the_previous_state_and_board(self):
        # 2026-11-16 17:12: /mnt/zer0models hit ENOSPC. Path.write_text truncates first, so a failed write left
        # fix-state.json empty/partial and the next hourly run's json.loads would crash every tape silently.
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [{"id": "a", "tape": "true"}]}))
            mod = load(ops)
            mod.run()
            state, board = (ops / "fix-state.json").read_text(), (ops / "BOARD.md").read_text()
            real = Path.write_text

            def full(self, data, *a, **k):
                real(self, data[: len(data) // 2], *a, **k)
                raise OSError(28, "No space left on device")

            Path.write_text = full
            try:
                with self.assertRaises(OSError):
                    mod.run()
            finally:
                Path.write_text = real
            self.assertEqual((ops / "fix-state.json").read_text(), state)
            self.assertEqual((ops / "BOARD.md").read_text(), board)
            self.assertEqual(sorted(f.name for f in ops.iterdir() if ".tmp" in f.name), [])

class FixReplayRegressionReopen(unittest.TestCase):
    """2026-11-16 sanity class 1 (fix-did-not-stick, ~103 owner re-explains in 30 d): a fix tape that had passed
    flipped red (unit-dash-turbo-follow, tier-mounted-after-kernel-upgrade) and no task ever reopened it."""

    def replay(self, tapes, outcomes, tmp):
        ops, stub = Path(tmp) / "ops", Path(tmp) / "bin"
        ops.mkdir(); stub.mkdir()
        calls = Path(tmp) / "calls"
        (stub / "hermes").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {calls}.$$\ncat > {calls}.$$.body\n"
                                     "echo 'Command helper: chatter'; printf '{\\n  \"id\": \"t_stub\",\\n  \"status\": \"ready\"\\n}\\n'\n")
        (stub / "hermes").chmod(0o755)
        flag = Path(tmp) / "ok"
        os.environ["FIX_REOPEN_HERMES"] = str(stub / "hermes")
        try:
            for ok in outcomes:
                flag.write_text("0" if ok else "1")
                (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                    t | {"tape": f"echo boom; exit $(cat {flag})"} for t in tapes]}))
                load(ops).run()
        finally:
            del os.environ["FIX_REOPEN_HERMES"]
        made = sorted(p for p in Path(tmp).glob("calls.*") if not p.name.endswith(".body"))
        return [(p.read_text().splitlines(), Path(f"{p}.body").read_text()) for p in made], ops

    def test_two_consecutive_fails_after_a_pass_open_exactly_one_task_for_the_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            made, ops = self.replay([{"id": "unit-x", "lane": "network", "what": "x stops failing"}],
                                    [True, True, False, False, False, False], tmp)
            self.assertEqual(len(made), 1, "one task per regression streak, not one per failing hour")
            argv, body = made[0]
            self.assertEqual(argv[argv.index("--assignee") + 1], "network")
            self.assertTrue(argv[argv.index("--idempotency-key") + 1].startswith("fix-replay-regression:unit-x:"))
            self.assertIn("unit-x", argv[argv.index("create") + 1])
            for want in ("last pass", "first fail", "boom", "pacman.log"):
                self.assertIn(want, body)
            self.assertEqual(json.loads((ops / "fix-state.json").read_text())["unit-x"]["reopened"], "t_stub")

    def test_a_single_flaky_fail_and_a_born_red_tape_open_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            made, _ = self.replay([{"id": "flaky"}], [True, False, True, False, True], tmp)
            self.assertEqual(made, [])
        with tempfile.TemporaryDirectory() as tmp:
            made, _ = self.replay([{"id": "born-red"}], [False, False, False], tmp)
            self.assertEqual(made, [], "a tape that never passed is unfixed, not a regression")

    def test_default_lane_is_reliability_and_a_second_regression_opens_a_new_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            made, _ = self.replay([{"id": "y"}], [True, False, False, True, False, False], tmp)
            self.assertEqual([a[a.index("--assignee") + 1] for a, _ in made], ["reliability", "reliability"])
            keys = {a[a.index("--idempotency-key") + 1] for a, _ in made}
            self.assertEqual(len(keys), 2, "a done reopen task must not swallow the next regression")


if __name__ == "__main__":
    unittest.main()
