#!/usr/bin/env python3
"""N11: auto-handoff capsule stays ~4k tokens; detail spills to <HERMES_HOME>/handoffs/<session>.md.

Run with the Hermes venv: PYTHONPATH=/workspace/hermes-home/hermes-agent <hermes venv python> -m unittest tests.test_handoff_compactor_capsule
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("handoff_compactor", ROOT / "config/hermes/plugins/handoff_capsule/__init__.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)
from agent.context_compressor import ContextCompressor  # noqa: E402
from agent.model_metadata import estimate_tokens_rough  # noqa: E402


def big_summary():
    sec = lambda h, n: f"## {h}\n" + "".join(f"- {h} line {i} " + "x" * 120 + "\n" for i in range(n))
    return "\n".join([
        sec("Goal", 10), sec("Constraints & Preferences", 60), sec("Completed Actions", 400),
        sec("Active State", 60), sec("Blocked", 40), sec("Key Decisions", 80), sec("Open Asks", 60),
        sec("Next", 8), sec("User Messages (verbatim, newest first)", 3),
        "> Remember for this whole chat: codeword PLUM-7731. My open ask: 'write a haiku'\n",
        sec("Detailed Session Log (oldest first)", 300), "## Pruned Skills\n[SKILL_PRUNED: content lost in compression; reload with skill_view(name='demo')]\n",
        "## Context Recovery\nsession_search(query='<keywords>', session_id='S-OLD')\n",
    ])


class Capsule(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["HERMES_HOME"] = self.home
        self.eng = hc.build()
        self.eng._session_id = "S-OLD"

    def run_gen(self, body):
        with mock.patch.object(ContextCompressor, "_generate_summary", return_value=ContextCompressor._with_summary_prefix(body)):
            return self.eng._generate_summary([{"role": "user", "content": "hi"}])

    def test_capsule_is_capped_near_4k_tokens(self):
        body = big_summary()
        self.assertGreater(estimate_tokens_rough(body), 20000)
        out = self.run_gen(body)
        self.assertLessEqual(estimate_tokens_rough(out), hc.CAPSULE_TOKENS + 300)
        self.assertTrue(out.startswith(hc.HANDOFF_PREFIX))

    def test_capsule_keeps_the_owner_sections_and_drops_history(self):
        out = self.run_gen(big_summary())
        for h in ("## Goal", "## Open Asks", "## Constraints & Preferences", "## Next"):
            self.assertIn(h, out)
        self.assertIn("Open Asks line 0 ", out)
        self.assertIn("Constraints & Preferences line 0 ", out)
        self.assertNotIn("Completed Actions line 5 ", out)
        self.assertIn("[SKILL_PRUNED:", out)  # ghost-skill markers survive the cap

    def test_owner_words_survive_verbatim(self):
        # Scratch proof 14:56: the summarizer put the ask only in the verbatim user section,
        # the capsule dropped it, and the next turn could not quote the owner's ask.
        out = self.run_gen(big_summary())
        self.assertIn("## User Messages (verbatim, newest first)", out)
        self.assertIn("My open ask: 'write a haiku'", out)
        self.assertNotIn("Detailed Session Log line 5 ", out)

    def test_full_detail_spills_to_the_profile_handoffs_dir(self):
        body = big_summary()
        out = self.run_gen(body)
        spill = Path(self.home) / "handoffs" / "S-OLD.md"
        self.assertTrue(spill.exists())
        self.assertIn("Completed Actions line 399 ", spill.read_text())
        self.assertEqual(spill.stat().st_mode & 0o777, 0o600)
        self.assertIn(str(spill), out)

    def test_failed_summary_stays_none(self):
        with mock.patch.object(ContextCompressor, "_generate_summary", return_value=None):
            self.assertIsNone(self.eng._generate_summary([]))

    def test_handoff_threshold_defaults_and_override(self):
        self.assertEqual(hc._cap_for("claude-opus-5-5", None), 150_000)
        self.assertEqual(hc._cap_for("gpt-5.5", None), 100_000)
        self.assertEqual(hc._cap_for("claude-opus-5-5", 90_000), 90_000)
        with mock.patch.object(hc, "_config", return_value={"context": {"handoff_tokens": 123_000}}):
            self.assertEqual(hc.build().threshold_tokens_cap, 123_000)

    def test_hermes_discovers_it_as_a_context_engine(self):
        # Hermes only scans the first 8 KiB of __init__.py for the engine contract.
        from plugins.context_engine import _is_context_engine_dir
        self.assertTrue(_is_context_engine_dir(ROOT / "config/hermes/plugins/handoff_capsule"))

    def test_lean_tail(self):
        self.assertEqual(self.eng.protect_last_n, 2)
        self.assertEqual(self.eng.min_tail_user_messages, 1)

    def test_autohandoff_command(self):
        calls = []
        with mock.patch.object(hc, "_set_engine", side_effect=lambda v: calls.append(v)), \
             mock.patch.object(hc, "_config", return_value={"context": {"engine": "handoff_capsule"}}):
            self.assertIn("off", hc.autohandoff_command("off"))
            hc.autohandoff_command("on")
            self.assertIn("handoff_capsule", hc.autohandoff_command("status"))
            self.assertIn("usage", hc.autohandoff_command("bogus").lower())
        self.assertEqual(calls, ["compressor", "handoff_capsule"])
        self.assertEqual(self.eng.name, "handoff_capsule")


if __name__ == "__main__":
    unittest.main()
