"""Offline tests (no phone, no cluster): python3 -m unittest discover -s services/phone-queue/tests"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phone_tools  # noqa: E402
import runner  # noqa: E402

SETTINGS = """<hierarchy>
 <node class="android.widget.FrameLayout" package="com.android.settings" bounds="[0,0][1080,2340]">
  <node class="android.widget.LinearLayout" clickable="true" bounds="[0,300][1080,450]">
   <node class="android.widget.TextView" text="Wi-Fi" bounds="[40,330][400,420]"/>
   <node class="android.widget.Switch" checkable="true" checked="true" bounds="[900,330][1040,420]"/>
  </node>
  <node class="android.widget.LinearLayout" clickable="true" bounds="[0,450][1080,600]">
   <node class="android.widget.TextView" text="About phone" bounds="[40,480][400,570]"/>
  </node>
  <node class="android.widget.CheckBox" text="Remember" checkable="true" clickable="true" bounds="[40,700][400,780]"/>
 </node>
</hierarchy>"""

CHAT = """<hierarchy>
 <node class="android.widget.TextView" package="com.openai.chatgpt" text="Phone queue (tag PQ-ABC)." bounds="[0,0][9,9]"/>
 <node class="android.widget.TextView" package="com.openai.chatgpt" text="TASK: say hi" bounds="[0,0][9,9]"/>
 <node class="android.widget.TextView" package="com.openai.chatgpt" text="hi there" bounds="[0,0][9,9]"/>
 <node class="android.view.View" content-desc="Copy" bounds="[0,0][9,9]"/>
 <node class="android.widget.TextView" package="com.android.systemui" text="9:37" bounds="[0,0][9,9]"/>
 <node class="android.widget.EditText" text="Ask ChatGPT" bounds="[0,0][9,9]"/>
</hierarchy>"""


class ToggleRefusal(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(SETTINGS)

    def test_tap_on_switch_itself(self):
        self.assertIsNotNone(phone_tools.toggle_under(self.root, 950, 370))

    def test_tap_on_row_label_that_owns_a_switch(self):
        # the whole row is the click receiver and contains the Switch -> refused
        self.assertIn("Wi-Fi", phone_tools.toggle_under(self.root, 100, 370))

    def test_checkbox(self):
        self.assertIsNotNone(phone_tools.toggle_under(self.root, 100, 740))

    def test_plain_navigation_row_allowed(self):
        self.assertIsNone(phone_tools.toggle_under(self.root, 100, 520))

    def test_check_tap_raises(self):
        p = phone_tools.Phone(d=None, device="s22")
        p.root = self.root
        rows = phone_tools.compact(self.root)
        wifi = next(r for r in rows if r["text"] == "Wi-Fi")
        with self.assertRaises(phone_tools.Refused):
            p._check_tap(wifi)
        about = next(r for r in rows if r["text"] == "About phone")
        p._check_tap(about)  # no exception


class ReplyParse(unittest.TestCase):
    def test_reply_after_tagged_bubble(self):
        root = ET.fromstring(CHAT)
        sent = "Phone queue (tag PQ-ABC).\n\nTASK: say hi"
        self.assertEqual(runner.reply_from_tree(root, "PQ-ABC", sent), "hi there")

    def test_no_tag_no_reply(self):
        self.assertIsNone(runner.reply_from_tree(ET.fromstring(CHAT), "PQ-NOPE", ""))


if __name__ == "__main__":
    unittest.main()
