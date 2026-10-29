#!/usr/bin/env python3
"""Phone tool layer: the ONLY way a queued agent touches a phone.

Verbs: observe, tap, set_text, swipe, back, home, launch, wait. There is no install,
settings, clipboard-read or shell verb, and none can be composed from these:
  - uiautomator2/adbutils install, uninstall, IME setup and send_keys are patched to raise
    (the overnight ds_burst rule); app_clear/app_uninstall too.
  - every tap is judged by what RECEIVES it (the smallest clickable element under the point)
    and that element's whole label (its subtree's text + content-desc), never by the index
    row alone (Settings rows are text-less clickable layouts around a title TextView):
      * anywhere: toggles/checkboxes/sliders, System UI (status bar, quick settings,
        notifications) and labels matching DENY_LABEL (install, reset, power off, restart,
        turn on/off, delete, pay, allow, ...) are refused;
      * on settings screens (settings_context: Settings, Device care, System UI, DeX/desktop
        mode panels) the guard is an allowlist: only navigation is allowed, i.e. "Navigate up"
        / "Back" / "Search" chrome, or a list row that is not a button, has no button inside,
        and whose title does not start with an action verb (SETTINGS_ACTION: "Start now",
        "Connect wirelessly", "Download and install", "OK", "Done", ...). Any dialog on a
        settings screen refuses every tap (use back). No set_text, no sideways swipes there.
  - swipes whose path crosses a slider (SeekBar/Slider: brightness, volume, font size) are
    refused everywhere.
  - launching installers/stores is refused.
  - every screen read goes through phone-screen-safe (redacted hierarchy; sensitive apps blank).
Typing is accessibility set_text only (no IME, no keyevents); set_text can type the job's own
prompt verbatim by reference (from_job_prompt) so a model never has to recopy long text.

Run as `phone_tools.py mcp` for fx: a stdio MCP server (newline-delimited JSON-RPC).
Requires PHONEQ_DEVICE / PHONEQ_SERIAL and that an ancestor process holds /tmp/<dev>-ui.lock.
"""
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

DENY_LABEL = re.compile(
    r"\b(install|uninstall|update now|reset|erase|factory|wipe|force stop|clear (data|storage|cache)|"
    r"delete|remove|sign out|log ?out|turn (off|on)|disable|deactivate|format|"
    r"allow|grant|permit|enable|power off|shut ?down|restart|reboot|start now|"
    r"pay|buy|purchase|subscribe|upgrade|unlock|factory data)\b", re.I)
# Settings screens: a row/button whose title STARTS with one of these is an action, not navigation.
SETTINGS_ACTION = re.compile(
    r"^\s*(start|stop|connect|disconnect|pair|unpair|forget|scan|restart|reboot|power|shut|turn|apply|"
    r"reset|delete|remove|clear|erase|install|uninstall|update|download|upgrade|sync|back ?up|restore|"
    r"transfer|optimi[sz]e|clean|fix|free up|save|done|ok|okay|yes|confirm|accept|agree|continue|allow|"
    r"deny|block|unblock|enable|disable|activate|deactivate|add|set|change|use|switch|send|share|sign|"
    r"log|pay|buy|subscribe|retry|try|check for|join|leave|register|end|close all|force|uninstall)\b", re.I)
# Rows that ACT when tapped although they look like plain rows: Build number (7 taps turn on
# Developer options), Google Play system update (starts a check/download), the rest start
# scans, resets or account flows on One UI.
SETTINGS_ROW_DENY = re.compile(
    r"^\s*(build number|google play system update|software update|download and install|"
    r"auto update|reset|general management|backup and restore|smart switch|find my mobile|"
    r"developer options|samsung dex|dex|wireless dex|smart view|quick share|link to windows|"
    r"nearby device scanning|safety and emergency|emergency sos|sim manager|mobile networks|"
    r"wi-?fi calling|airplane mode|flight mode)\s*$", re.I)
NAV_OK = re.compile(r"^(navigate up|back|search|collapse|expand|more options|show more|see more)$", re.I)
SLIDER_CLASSES = ("SeekBar", "AbsSeekBar", "SeslSeekBar", "SeslAbsSeekBar", "Slider", "RangeSlider", "RatingBar")
BUTTON_CLASSES = ("Button", "ImageButton", "MaterialButton", "AppCompatButton", "FloatingActionButton",
                  "ExtendedFloatingActionButton", "SeslButton")
DIALOG_IDS = ("android:id/button1", "android:id/button2", "android:id/button3", "android:id/alertTitle",
              "android:id/parentPanel", "android:id/buttonPanel")
DEX_MARKERS = re.compile(r"\b(samsung dex|dex for pc|desktop mode|connect wirelessly|wireless dex)\b", re.I)
SETTINGS_PKGS = {"com.android.settings", "com.samsung.android.settings", "com.samsung.android.lool",
                 "com.sec.android.app.personalpage", "com.android.systemui"}
NO_LAUNCH = {"com.android.vending", "com.sec.android.app.samsungapps", "com.google.android.packageinstaller",
             "com.android.packageinstaller", "com.samsung.android.app.updatecenter", "com.android.shell",
             "com.termux", "com.samsung.android.knox.containercore"}
PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
MAX_LINES = 140
MAX_TEXT = 20000  # the API's prompt limit
TOGGLE_CLASSES = ("Switch", "SwitchCompat", "SwitchMaterial", "CheckBox", "MaterialCheckBox", "ToggleButton",
                  "RadioButton", "CompoundButton", "CheckedTextView", "SeslSwitchBar")


def is_toggle(node):
    cls = (node.get("class") or "").split(".")[-1]
    return node.get("checkable") == "true" or cls in TOGGLE_CLASSES


def toggle_under(root, x, y):
    """A checkable control the tap at (x, y) could flip: any toggle whose bounds contain the
    point, or a toggle inside the smallest clickable element that receives the tap (a Settings
    row whose whole surface flips its Switch). Returns a label, or None."""
    receivers = []
    for n in root.iter("node"):
        b = bounds(n)
        if not b or not (b[0] <= x <= b[2] and b[1] <= y <= b[3]):
            continue
        if is_toggle(n):
            return (n.get("text") or n.get("content-desc") or n.get("class") or "toggle").strip()
        if n.get("clickable") == "true":
            receivers.append(((b[2] - b[0]) * (b[3] - b[1]), n))
    if receivers:
        receiver = min(receivers, key=lambda t: t[0])[1]
        for n in receiver.iter("node"):
            if is_toggle(n):
                label = " ".join(v for v in ((m.get("text") or "").strip() for m in receiver.iter("node")) if v)
                return (label or n.get("class") or "toggle")[:80]
    return None


def _cls(node):
    return (node.get("class") or "").split(".")[-1]


def is_slider(node):
    rid = (node.get("resource-id") or "").lower()
    return _cls(node) in SLIDER_CLASSES or "seekbar" in rid or "slider" in rid


def receiver_at(root, x, y):
    """The element a tap at (x, y) lands on: the smallest clickable node containing the point
    (else the smallest node of any kind)."""
    clickable, anyn = [], []
    for n in root.iter("node"):
        b = bounds(n)
        if not b or not (b[0] <= x <= b[2] and b[1] <= y <= b[3]):
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        anyn.append((area, n))
        if n.get("clickable") == "true" or n.get("long-clickable") == "true":
            clickable.append((area, n))
    pool = clickable or anyn
    return min(pool, key=lambda t: t[0])[1] if pool else None


def label_of(node):
    """Every text and content-desc in node's subtree, in order."""
    out = []
    for m in node.iter("node"):
        for a in ("text", "content-desc"):
            v = (m.get(a) or "").strip()
            if v and v not in out:
                out.append(v)
    return out


def title_of(node):
    """A row's title: its resource-id .../title child, else its first text."""
    for m in node.iter("node"):
        if (m.get("resource-id") or "").endswith("/title") and (m.get("text") or "").strip():
            return m.get("text").strip()
    labels = label_of(node)
    return labels[0] if labels else ""


def settings_context(pkg, root):
    """True on screens where taps change the device: Settings and friends, and DeX/desktop
    mode panels (served by the launcher / dexservice on One UI)."""
    if pkg in SETTINGS_PKGS or "dexservice" in (pkg or "") or "desktopmode" in (pkg or ""):
        return True
    for n in root.iter("node"):
        if (n.get("package") or "") in SETTINGS_PKGS - {"com.android.systemui"}:
            return True
        if DEX_MARKERS.search(n.get("text") or "") or DEX_MARKERS.search(n.get("content-desc") or ""):
            return True
    return False


def dialog_open(root):
    return any((n.get("resource-id") or "") in DIALOG_IDS or "Dialog" in (n.get("class") or "")
               for n in root.iter("node"))


def check_tap(root, pkg, x, y):
    """Raise Refused unless a tap at (x, y) on this (redacted) screen is safe; see module doc."""
    hit = toggle_under(root, x, y)
    if hit:
        raise Refused(f"refused: tapping there could flip the toggle in {hit!r}; the queue never changes settings")
    rec = receiver_at(root, x, y)
    if rec is None:
        if settings_context(pkg, root):
            raise Refused("refused: nothing identifiable under that point on a settings screen")
        return
    for n in rec.iter("node"):
        if is_slider(n):
            raise Refused("refused: that is a slider; the queue never changes settings")
    if (rec.get("package") or "") == "com.android.systemui":
        raise Refused("refused: System UI (status bar, quick settings, notifications) is off limits")
    labels = label_of(rec)
    label = " | ".join(labels)[:160]
    # A control's own words: the whole label for a button/row (<= 4 strings); for a large
    # clickable container (a chat-list row with a preview, a card) its title and own attributes,
    # so message text that merely mentions "delete" does not block a tap on it.
    own = labels if len(labels) <= 4 else [title_of(rec), rec.get("text") or "", rec.get("content-desc") or ""]
    if DENY_LABEL.search(" ".join(own)) or DENY_LABEL.search(rec.get("resource-id") or ""):
        raise Refused(f"refused: {label!r} looks like an install/reset/power/permission/purchase action")
    if not settings_context(pkg, root):
        return
    # settings screens: navigation only
    if dialog_open(root):
        raise Refused("refused: a dialog is open on a settings screen; use back to dismiss it")
    if any(NAV_OK.match(v) for v in labels) and len(labels) == 1:
        return
    if _cls(rec) in BUTTON_CLASSES or any(_cls(m) in BUTTON_CLASSES for m in rec.iter("node")):
        raise Refused(f"refused: {label or _cls(rec)!r} is a button on a settings screen (navigation only)")
    title = title_of(rec)
    if not title:
        raise Refused("refused: unlabelled control on a settings screen (navigation only)")
    if SETTINGS_ACTION.match(title):
        raise Refused(f"refused: {title!r} is an action on a settings screen (navigation only)")
    if SETTINGS_ROW_DENY.match(title):
        raise Refused(f"refused: {title!r} acts when tapped or leads to device-changing flows (not navigable)")


def check_swipe(root, pkg, direction, scale, size):
    """Refuse a swipe whose finger path crosses a slider, and sideways swipes on settings screens."""
    w, h = size
    if direction in ("left", "right") and settings_context(pkg, root):
        raise Refused("refused: sideways swipes are not allowed on settings screens (sliders)")
    # uiautomator2 swipe_ext: the path runs through the screen centre, scale of the screen long.
    if direction in ("up", "down"):
        x0 = x1 = w / 2
        y0, y1 = h * (0.5 - scale / 2), h * (0.5 + scale / 2)
    else:
        y0 = y1 = h / 2
        x0, x1 = w * (0.5 - scale / 2), w * (0.5 + scale / 2)
    for n in root.iter("node"):
        if not is_slider(n):
            continue
        b = bounds(n)
        if b and min(x0, x1) <= b[2] and max(x0, x1) >= b[0] and min(y0, y1) <= b[3] and max(y0, y1) >= b[1]:
            raise Refused("refused: the swipe would drag a slider; the queue never changes settings")


class Refused(RuntimeError):
    pass


def _blocked(*_a, **_k):
    raise Refused("phone-queue: installs, IME setup, send_keys and app data changes are prohibited")


def guard_u2():
    import adbutils
    import uiautomator2 as u2
    import uiautomator2._input as u2_input
    for name in ("install", "install_remote", "uninstall"):
        setattr(adbutils.AdbDevice, name, _blocked)
    u2_input.InputMethodMixIn._setup_ime = _blocked
    for name in ("send_keys", "app_install", "app_uninstall", "app_uninstall_all", "app_clear",
                 "set_input_ime", "set_fastinput_ime"):
        setattr(u2.Device, name, _blocked)
    return u2


def connect(serial):
    u2 = guard_u2()
    return u2.connect(serial)


_pss = None


def pss():
    global _pss
    if _pss is None:
        _pss = common.load_source("phone_screen_safe", common.PHONE_SCREEN_SAFE)
    return _pss


def tree_package(root):
    """Foreground app from the hierarchy itself (u2 app_current() costs ~5 s on One UI)."""
    for n in root.iter("node"):
        pkg = n.get("package") or ""
        if pkg and pkg != "com.android.systemui":
            return pkg
    return ""


def foreground(d):
    try:
        return tree_package(ET.fromstring(d.dump_hierarchy().encode()))
    except Exception:  # noqa: BLE001
        return ""


def bounds(node):
    m = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", node.get("bounds", ""))
    return tuple(map(int, m.groups())) if m else None


# Settings > About phone > Software information rows whose values are public firmware ids
# (they trip phone-screen-safe's high-entropy rule). Only these titles, only in Settings, only
# when the high-entropy rule is the sole hit and the value looks like a firmware id. IMEI,
# serial, phone number, MAC/IP addresses and everything else stay redacted.
FIRMWARE_TITLES = {"build number", "baseband version", "kernel version", "service provider software version",
                   "software version", "hardware version", "one ui version", "android version",
                   "google play system update", "knox version", "security software version"}
FIRMWARE_VALUE = re.compile(r"[A-Za-z0-9 _.,:/#()+\-\n]{1,300}")


def restore_firmware_ids(raw_root, red_root):
    """Un-redact public firmware ids (see FIRMWARE_TITLES) in a redacted copy of raw_root."""
    redacted = pss().REDACTED
    parent = {c: p for p in red_root.iter() for c in p}
    restored = 0
    for raw_n, red_n in zip(raw_root.iter("node"), red_root.iter("node")):
        val, now = raw_n.get("text") or "", red_n.get("text") or ""
        if redacted not in now or val == now:
            continue
        if (red_n.get("resource-id") or "").endswith("/title"):
            continue
        # The row = the smallest ancestor holding exactly one other text node that is a title
        # (Samsung nests the title in title_frame, the summary beside it; AOSP has siblings).
        title, p = None, parent.get(red_n)
        for _ in range(3):
            if p is None:
                break
            texts = [c for c in p.iter("node") if c is not red_n and (c.get("text") or "").strip()]
            if texts:
                title = texts[0].get("text").strip().lower() if len(texts) == 1 else None
                break
            p = parent.get(p)
        if title not in FIRMWARE_TITLES or not FIRMWARE_VALUE.fullmatch(val):
            continue
        if {rule for _s, _e, rule in pss().find_spans(val)} - {"high_entropy"}:
            continue
        red_n.set("text", val)
        if red_n.get("content-desc") and redacted in red_n.get("content-desc"):
            red_n.set("content-desc", raw_n.get("content-desc") or "")
        restored += 1
    return restored


def safe_tree(d):
    """Redacted hierarchy, same rule as phone-screen-safe.safe_hierarchy (sensitive app ->
    nothing; else redact_xml), with the package read from the dump instead of app_current().
    Returns (package, redacted root element)."""
    raw = d.dump_hierarchy()
    raw_root = ET.fromstring(raw.encode())
    pkg = tree_package(raw_root)
    if pss().sensitive_package(pkg):
        return pkg, ET.fromstring(f'<hierarchy redacted="sensitive app {pkg}"/>')
    xml = pss().redact_xml(raw)[0]
    root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    if pkg in SETTINGS_PKGS:
        restore_firmware_ids(raw_root, root)
    return pkg, root


def tree_text(root):
    """All visible text + content-desc of a (redacted) tree, one per line (the oracle's view)."""
    out = []
    for n in root.iter("node"):
        for attr in ("text", "content-desc"):
            v = (n.get(attr) or "").strip()
            if v:
                out.append(v)
    return "\n".join(out)


def compact(root):
    """Index -> node rows for the model; only labelled, clickable or editable nodes."""
    rows = []
    for n in root.iter("node"):
        b = bounds(n)
        if not b or b[2] <= b[0] or b[3] <= b[1]:
            continue
        text = (n.get("text") or "").strip()
        desc = (n.get("content-desc") or "").strip()
        rid = (n.get("resource-id") or "").split("/")[-1]
        cls = (n.get("class") or "").split(".")[-1]
        flags = [f for f, a in (("click", "clickable"), ("check", "checkable"), ("scroll", "scrollable"),
                                ("focus", "focused")) if n.get(a) == "true"]
        if cls == "EditText":
            flags.append("edit")
        if not (text or desc or "click" in flags or "edit" in flags or "scroll" in flags):
            continue
        rows.append({"i": len(rows), "text": text[:80], "desc": desc[:60], "id": rid, "cls": cls,
                     "flags": flags, "checked": n.get("checked") == "true",
                     "x": (b[0] + b[2]) // 2, "y": (b[1] + b[3]) // 2, "bounds": b})
    return rows


def render(pkg, rows):
    lines = [f"app: {pkg or 'unknown'}"]
    for r in rows[:MAX_LINES]:
        label = r["text"] or r["desc"] or ""
        bits = [f"[{r['i']}]", repr(label) if label else "-", r["cls"]]
        if r["desc"] and r["text"]:
            bits.append(f"desc={r['desc']!r}")
        if r["id"]:
            bits.append(f"id={r['id']}")
        if r["flags"]:
            bits.append(",".join(r["flags"]) + (" on" if r["checked"] else ""))
        bits.append(f"@{r['x']},{r['y']}")
        lines.append(" ".join(bits))
    if len(rows) > MAX_LINES:
        lines.append(f"... {len(rows) - MAX_LINES} more rows (scroll or narrow down)")
    return "\n".join(lines)


class Phone:
    def __init__(self, d, device, state_file=None, log=None):
        self.d = d
        self.device = device
        self.state_file = Path(state_file) if state_file else None
        self.log = Path(log) if log else None
        self.rows = []
        self.pkg = ""
        self.actions = 0

    # ------------------------------------------------------------ helpers
    def _record(self, tool, args, ok, result, ms):
        if self.log:
            with self.log.open("a") as f:
                f.write(json.dumps({"at": common.now_iso(), "t": time.time(), "tool": tool, "args": args, "ok": ok,
                                    "ms": ms, "result": result[:4000]}) + "\n")

    def _refresh(self):
        self.pkg, root = safe_tree(self.d)
        self.rows = compact(root)
        self.root = root
        return root

    def _find(self, args):
        """Resolve a target (index | text | desc | resource_id | x,y) to a fresh row or point."""
        root = self._refresh()
        if args.get("index") is not None:
            # Indexes refer to the latest observe; re-resolve against a fresh dump by identity.
            want = self._last_rows().get(int(args["index"]))
            if want is None:
                raise Refused(f"no row [{args['index']}] in the last observe; call observe again")
            for r in self.rows:
                if (r["text"], r["desc"], r["id"], r["cls"]) == (want["text"], want["desc"], want["id"], want["cls"]):
                    return r
            raise Refused(f"row [{args['index']}] is no longer on screen; call observe again")
        for key, field in (("text", "text"), ("desc", "desc"), ("resource_id", "id")):
            value = (args.get(key) or "").strip()
            if not value:
                continue
            exact = [r for r in self.rows if r[field] == value]
            loose = [r for r in self.rows if value.lower() in r[field].lower()]
            hits = exact or loose
            if not hits and field == "text":  # labels live in either attribute
                hits = [r for r in self.rows if r["desc"] == value] or \
                       [r for r in self.rows if value.lower() in r["desc"].lower()]
            if hits:
                return hits[0]
            raise Refused(f"nothing on screen matches {key}={value!r}; call observe")
        if args.get("x") is not None and args.get("y") is not None:
            x, y = int(args["x"]), int(args["y"])
            inside = [r for r in self.rows if r["bounds"][0] <= x <= r["bounds"][2] and r["bounds"][1] <= y <= r["bounds"][3]]
            inside.sort(key=lambda r: (r["bounds"][2] - r["bounds"][0]) * (r["bounds"][3] - r["bounds"][1]))
            hit = dict(inside[0]) if inside else {"text": "", "desc": "", "id": "", "cls": "", "flags": [], "checked": False}
            hit.update(x=x, y=y)
            return hit
        raise Refused("give one of: index, text, desc, resource_id, or x and y")

    def _last_rows(self):
        if not self.state_file or not self.state_file.exists():
            return {r["i"]: r for r in self.rows}
        return {r["i"]: r for r in json.loads(self.state_file.read_text())}

    def _save_rows(self):
        if self.state_file:
            common.write_json(self.state_file, self.rows)

    def _check_tap(self, row):
        label = " ".join(x for x in (row.get("text"), row.get("desc"), row.get("id")) if x)
        if "check" in row.get("flags", []) or row.get("cls") in TOGGLE_CLASSES:
            raise Refused(f"refused: {label or 'that control'} is a toggle; the queue never changes settings")
        if row.get("cls") in SLIDER_CLASSES:
            raise Refused("refused: that is a slider; the queue never changes settings")
        if label and DENY_LABEL.search(label):
            raise Refused(f"refused: {label!r} looks like an install/reset/power/permission/purchase action")
        root = getattr(self, "root", None)
        if root is None:
            raise Refused("observe first")
        check_tap(root, self.pkg, row["x"], row["y"])

    def _settle(self, s=0.6):
        time.sleep(s)

    # ------------------------------------------------------------ verbs
    def observe(self, _args=None):
        self._refresh()
        self._save_rows()
        return render(self.pkg, self.rows)

    def tap(self, args):
        row = self._find(args)
        self._check_tap(row)
        self.d.click(row["x"], row["y"])
        self.actions += 1
        self._settle(0.8)
        label = row.get("text") or row.get("desc") or row.get("id") or ""
        return f"tapped {label!r} @{row['x']},{row['y']}; call observe to see the result"

    def set_text(self, args):
        text = args.get("text")
        if args.get("from_job_prompt"):
            job = common.read_json(Path(os.environ["PHONEQ_JOB_DIR"]) / "job.json") if os.environ.get("PHONEQ_JOB_DIR") else None
            text = (job or {}).get("prompt")
            if not isinstance(text, str) or not text:
                raise Refused("this job has no prompt to type (from_job_prompt)")
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            raise Refused(f"set_text needs text (<= {MAX_TEXT} chars) or from_job_prompt=true")
        target = {k: args[k] for k in ("index", "resource_id", "desc") if args.get(k) is not None}
        if args.get("field_text"):
            target["text"] = args["field_text"]
        root = self._refresh()
        if settings_context(self.pkg, root):
            raise Refused("refused: typing on settings screens is not allowed")
        if target:
            row = self._find(target)
            if "edit" not in row["flags"]:
                raise Refused("target is not a text field")
            self.d.click(row["x"], row["y"])  # focus the chosen field
            time.sleep(0.4)
        el = self.d(className="android.widget.EditText", focused=True)
        if not el.exists:
            el = self.d(className="android.widget.EditText")
        if not el.exists:
            raise Refused("no text field on screen")
        el.set_text(text)  # accessibility ACTION_SET_TEXT; no IME, no keyevents
        self.actions += 1
        self._settle(0.4)
        got = el.get_text() if el.exists else None
        note = "" if got is None or got.strip()[:40] == text.strip()[:40] else " (field shows different text; observe)"
        return f"text set ({len(text)} chars)" + note

    def swipe(self, args):
        direction = (args.get("direction") or "").lower()
        if direction not in ("up", "down", "left", "right"):
            raise Refused("direction must be up, down, left or right (finger direction)")
        scale = min(max(float(args.get("scale", 0.6)), 0.2), 0.9)
        root = self._refresh()
        check_swipe(root, self.pkg, direction, scale, self.d.window_size())
        self.d.swipe_ext(direction, scale=scale)
        self.actions += 1
        self._settle(0.7)
        return f"swiped {direction}"

    def back(self, _args=None):
        self.d.press("back")
        self.actions += 1
        self._settle()
        return "pressed back"

    def home(self, _args=None):
        self.d.press("home")
        self.actions += 1
        self._settle()
        return "pressed home"

    def launch(self, args):
        pkg = (args.get("package") or "").strip()
        pkg = common.APPS.get(pkg, pkg)
        if pkg == "settings":
            pkg = "com.android.settings"
        if not PKG_RE.match(pkg) or pkg in NO_LAUNCH:
            raise Refused(f"refused to launch {pkg!r}")
        installed = self.d.shell(["pm", "path", pkg]).output.strip()
        if not installed.startswith("package:"):
            raise Refused(f"{pkg} is not installed (the queue never installs apps)")
        record_agent_open(self.device, self.d.serial, pkg)
        self.d.app_start(pkg)
        self.actions += 1
        self._settle(1.5)
        return f"launched {pkg}; foreground is now {foreground(self.d) or 'unknown'}"

    def wait(self, args):
        s = min(max(float(args.get("seconds", 1)), 0.2), 10)
        time.sleep(s)
        return f"waited {s:g}s"

    VERBS = ("observe", "tap", "set_text", "swipe", "back", "home", "launch", "wait")

    def call(self, tool, args):
        if tool not in self.VERBS:
            raise Refused(f"unknown tool {tool}")
        t0 = time.time()
        try:
            out = getattr(self, tool)(args or {})
            self._record(tool, args, True, out, int((time.time() - t0) * 1000))
            return out
        except Exception as e:  # noqa: BLE001 - every failure goes back to the model as text
            msg = f"{type(e).__name__}: {e}"
            self._record(tool, args, False, msg, int((time.time() - t0) * 1000))
            raise


def record_agent_open(device, serial, pkg):
    """Same ledger the ChatGPT driver keeps: an app an agent opened is not owner use."""
    try:
        sys.path.insert(0, str(common.DRIVER))
        import burst
        burst.record_agent_open(device, pkg, burst.activity_snapshot(serial))
    except Exception:  # noqa: BLE001 - ledger write is evidence only
        pass


TOOLS = [
    {"name": "observe", "description": "Read the current phone screen (redacted). Returns 'app: <package>' then one row per element: [index] 'label' class id=... flags @x,y. Call this first and after every action.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "tap", "description": "Tap one element. Prefer index from the latest observe; or give text, desc, resource_id, or x and y. Refused: toggles, sliders, System UI, install/reset/power/delete/permission/purchase buttons; on settings screens only navigation (rows, Navigate up) is allowed.",
     "inputSchema": {"type": "object", "properties": {
         "index": {"type": "integer"}, "text": {"type": "string"}, "desc": {"type": "string"},
         "resource_id": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
         "additionalProperties": False}},
    {"name": "set_text", "description": "Replace the text of a text field (the focused one, or the one given by index/resource_id/desc/field_text). Give text (<= 20000 chars), or from_job_prompt=true to type this job's prompt exactly as submitted (use it for long messages instead of copying them). Not allowed on settings screens.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "from_job_prompt": {"type": "boolean"}, "index": {"type": "integer"},
         "resource_id": {"type": "string"}, "desc": {"type": "string"}, "field_text": {"type": "string"}},
         "additionalProperties": False}},
    {"name": "swipe", "description": "Swipe the screen. direction is the finger direction: 'up' scrolls content down to reveal more below.",
     "inputSchema": {"type": "object", "properties": {
         "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
         "scale": {"type": "number", "minimum": 0.2, "maximum": 0.9}},
         "required": ["direction"], "additionalProperties": False}},
    {"name": "back", "description": "Press Back.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "home", "description": "Press Home.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "launch", "description": "Open an installed app by Android package name (e.g. com.android.settings, com.openai.chatgpt). Never installs anything.",
     "inputSchema": {"type": "object", "properties": {"package": {"type": "string"}},
                     "required": ["package"], "additionalProperties": False}},
    {"name": "wait", "description": "Wait 0.2-10 seconds for the screen to settle or load.",
     "inputSchema": {"type": "object", "properties": {"seconds": {"type": "number", "minimum": 0.2, "maximum": 10}},
                     "additionalProperties": False}},
]


def mcp_main():
    device = os.environ["PHONEQ_DEVICE"]
    serial = os.environ["PHONEQ_SERIAL"]
    jdir = Path(os.environ["PHONEQ_JOB_DIR"])
    sys.path.insert(0, str(common.DRIVER))
    import burst
    burst.require_ui_lock(device)  # an ancestor (the runner) must hold /tmp/<dev>-ui.lock
    phone = Phone(connect(serial), device, jdir / "last-observe.json", jdir / "tools.jsonl")
    out = sys.stdout
    sys.stdout = sys.stderr  # nothing but JSON-RPC on the real stdout

    def reply(i, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": i}
        msg["error" if error else "result"] = error or result
        out.write(json.dumps(msg) + "\n")
        out.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except ValueError:
            continue
        i, meth = m.get("id"), m.get("method")
        if i is None:
            continue  # notifications
        if meth == "initialize":
            reply(i, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "phone", "version": "1.0"}})
        elif meth == "tools/list":
            reply(i, {"tools": TOOLS})
        elif meth == "tools/call":
            p = m.get("params") or {}
            try:
                text = phone.call(p.get("name"), p.get("arguments") or {})
                reply(i, {"content": [{"type": "text", "text": text}], "isError": False})
            except Exception as e:  # noqa: BLE001
                reply(i, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True})
        elif meth == "ping":
            reply(i, {})
        else:
            reply(i, error={"code": -32601, "message": f"method not found: {meth}"})


if __name__ == "__main__":
    if sys.argv[1:2] == ["mcp"]:
        mcp_main()
    else:
        sys.exit(__doc__)
