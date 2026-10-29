#!/usr/bin/env python3
"""Phone tool layer: the ONLY way a queued agent touches a phone.

Verbs: observe, tap, set_text, swipe, back, home, launch, wait. There is no install,
settings, clipboard-read or shell verb, and none can be composed from these:
  - uiautomator2/adbutils install, uninstall, IME setup and send_keys are patched to raise
    (the overnight ds_burst rule); app_clear/app_uninstall too.
  - taps on toggles/checkboxes and on install/uninstall/reset/erase/force-stop style labels
    are refused; Settings is read-only (no checkable taps, no set_text there).
  - launching installers/stores is refused.
  - every screen read goes through phone-screen-safe (redacted hierarchy; sensitive apps blank).
Typing is accessibility set_text only (no IME, no keyevents).

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
    r"delete account|remove account|sign out|log ?out|turn off|disable|deactivate|format|"
    r"allow|grant|permit|enable)\b", re.I)
SETTINGS_PKGS = {"com.android.settings", "com.samsung.android.settings", "com.samsung.android.lool",
                 "com.sec.android.app.personalpage", "com.android.systemui"}
NO_LAUNCH = {"com.android.vending", "com.sec.android.app.samsungapps", "com.google.android.packageinstaller",
             "com.android.packageinstaller", "com.samsung.android.app.updatecenter", "com.android.shell",
             "com.termux", "com.samsung.android.knox.containercore"}
PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
MAX_LINES = 140
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


def safe_tree(d):
    """Redacted hierarchy, same rule as phone-screen-safe.safe_hierarchy (sensitive app ->
    nothing; else redact_xml), with the package read from the dump instead of app_current().
    Returns (package, redacted root element)."""
    raw = d.dump_hierarchy()
    pkg = tree_package(ET.fromstring(raw.encode()))
    if pss().sensitive_package(pkg):
        return pkg, ET.fromstring(f'<hierarchy redacted="sensitive app {pkg}"/>')
    xml = pss().redact_xml(raw)[0]
    return pkg, ET.fromstring(xml.encode() if isinstance(xml, str) else xml)


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
        hit = toggle_under(self.root, row["x"], row["y"]) if getattr(self, "root", None) is not None else None
        if hit:
            raise Refused(f"refused: tapping there could flip the toggle in {hit!r}; the queue never changes settings")
        if label and DENY_LABEL.search(label):
            raise Refused(f"refused: {label!r} looks like an install/reset/permission/settings action")

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
        if not isinstance(text, str) or len(text) > 4000:
            raise Refused("set_text needs text (<= 4000 chars)")
        target = {k: args[k] for k in ("index", "resource_id", "desc") if args.get(k) is not None}
        if args.get("field_text"):
            target["text"] = args["field_text"]
        self._refresh()
        if self.pkg in SETTINGS_PKGS:
            raise Refused("refused: typing inside Settings is not allowed")
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
        return "text set" + ("" if got is None or got.strip()[:40] == text.strip()[:40] else " (field shows different text; observe)")

    def swipe(self, args):
        direction = (args.get("direction") or "").lower()
        if direction not in ("up", "down", "left", "right"):
            raise Refused("direction must be up, down, left or right (finger direction)")
        scale = min(max(float(args.get("scale", 0.6)), 0.2), 0.9)
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
    {"name": "tap", "description": "Tap one element. Prefer index from the latest observe; or give text, desc, resource_id, or x and y. Toggles and install/reset/permission buttons are refused.",
     "inputSchema": {"type": "object", "properties": {
         "index": {"type": "integer"}, "text": {"type": "string"}, "desc": {"type": "string"},
         "resource_id": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
         "additionalProperties": False}},
    {"name": "set_text", "description": "Replace the text of a text field (the focused one, or the one given by index/resource_id/desc/field_text). Not allowed in Settings.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "index": {"type": "integer"}, "resource_id": {"type": "string"},
         "desc": {"type": "string"}, "field_text": {"type": "string"}},
         "required": ["text"], "additionalProperties": False}},
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
