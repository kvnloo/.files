import importlib.machinery
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pr-media"
_loader = importlib.machinery.SourceFileLoader("pr_media", str(SCRIPT))
_spec = importlib.util.spec_from_loader("pr_media", _loader)
assert _spec is not None
pm = importlib.util.module_from_spec(_spec)
_loader.exec_module(pm)


def test_splice_prepends_when_no_markers():
    out = pm.splice("old body", pm.block("cap", ["A"]), append=False)
    assert out.startswith(pm.START + "\ncap\n\nA\n" + pm.END)
    assert out.endswith("old body")


def test_splice_replaces_and_appends_idempotently():
    body = "head\n" + pm.block(None, ["A"]) + "\ntail"
    assert pm.splice(body, pm.block(None, ["B"]), append=False) == "head\n" + pm.block(None, ["B"]) + "\ntail"
    appended = pm.splice(body, pm.block(None, ["B"]), append=True)
    assert "A\nB" in appended and appended.count(pm.START) == 1 and appended.endswith("\ntail")


def test_template_markers_are_filled_in_place():
    tpl = "**You now see:** x\n\n<!-- pr-media:start -->\n<!-- hint -->\n<!-- pr-media:end -->\n\nrest"
    out = pm.splice(tpl, pm.block(None, ["IMG"]), append=False)
    assert out.startswith("**You now see:** x") and "IMG" in out and "hint" not in out


def test_privacy_hits_catch_paths_tailnet_and_lan():
    text = "see /home/kvn/x and 100.101.7.3 on groot.tail1234.ts.net, lan 192.168.1.9; ok 100.20.1.1"
    hits = pm.privacy_hits(text, pm.PRIVATE)
    assert "/home/kvn" in hits and "100.101.7.3" in hits and "groot.tail1234.ts.net" in hits
    assert "192.168.1.9" in hits and "100.20.1.1" not in hits


def test_video_embed_uses_gif_preview_linking_mp4():
    lines = pm.embed_lines([("demo.mp4", "video", "U/demo.mp4"), ("demo.gif", "preview", "U/demo.gif")])
    assert lines[0] == '<a href="U/demo.mp4"><img src="U/demo.gif" alt="demo (click for mp4)" width="640"></a>'
