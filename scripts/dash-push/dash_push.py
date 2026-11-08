#!/usr/bin/env python3
"""Dash push fallback.

Dash notices reach the phone only over a live WebSocket to dash-bridge (:4747). This watcher
polls ~/.dash/notices.json; for each NEW notice it checks whether a Dash client socket is
connected. If not, it posts a native Android notification on the owner's S25 through the
tailnet ADB connection (`cmd notification post`), so it shows with Dash closed. The notice
stays in Dash's ring too, so it is still there when the app reopens.

Limits: shell-posted notifications cannot carry a tap intent into Dash (Android refuses
getIntentSender for uid 2000), so the body says where to look. Dedupe: same title within
30 min is dropped; at most 12 pushes per hour.
State: state.json (seen ids, push log). Log: push.jsonl.
"""
import json, os, subprocess, time, re, pathlib, datetime as dt

HERE = pathlib.Path(__file__).resolve().parent
NOTICES = pathlib.Path.home() / ".dash/notices.json"
STATE = HERE / "state.json"
LOG = HERE / "push.jsonl"
PHONE_IP_ENV = "DASH_PHONE_IP"                    # env override
PHONE_IP_CONFIG = pathlib.Path.home() / ".dash/phone.env"  # local config, outside git
DEDUPE_S, HOURLY_MAX = 30 * 60, 12


def phone_ip():
    """S25 tailnet address: $DASH_PHONE_IP, else PHONE_IP=... in ~/.dash/phone.env.

    Never hard-coded: the tailnet address is private and this repo is public.
    Returns "" (fail closed) when nothing is configured.
    """
    ip = os.environ.get(PHONE_IP_ENV, "").strip()
    if ip:
        return ip
    if PHONE_IP_CONFIG.exists():
        for raw in PHONE_IP_CONFIG.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "PHONE_IP":
                val = val.strip().strip('"').strip("'").strip()
                if val:
                    return val
    return ""


def log(**k):
    k["at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG.open("a") as f:
        f.write(json.dumps(k) + "\n")


def sh(*a, t=20):
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def dash_connected():
    _, out = sh("ss", "-tnH", "state", "established", "( sport = :4747 )")
    return bool(out.strip())


def phone_serial():
    ip = phone_ip()
    if not ip:
        return None
    _, out = sh("adb", "devices")
    for ln in out.splitlines():
        if ln.startswith(ip + ":") and ln.endswith("\tdevice"):
            return ln.split("\t")[0]
    # wireless debugging port changes after reboots; mDNS discovery reconnects it
    _, out = sh("adb", "mdns", "services")
    for m in re.finditer(rf"{re.escape(ip)}:(\d+)", out):
        sh("adb", "connect", f"{ip}:{m.group(1)}")
        return f"{ip}:{m.group(1)}"
    return None


def clean(s, n):
    s = re.sub(r"[^\x20-\x7e\n]", "", s or "")[:n]
    return s.replace("'", "\u2019").replace("'", "")


def push(serial, nid, title, body):
    t = clean(title, 80) or "Dash"
    b = clean(body, 560) + "\n(open Dash for details)"
    cmd = (f"cmd notification post -S bigtext -t '{t} dash-{nid[:8]} "
           f"'{b}'")
    return sh("adb", "-s", serial, "shell", cmd)


def notice_items(data):
    """Return notice dicts from a notices.json payload. Bare-string items, legacy
    items keyed by id, and non-dict payloads never crash the watcher; they are
    silently skipped. A payload that is itself a list is treated as the item list."""
    if isinstance(data, dict):
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data
    else:
        return []
    if isinstance(items, dict):
        items = list(items.values())
    out = []
    for x in items:
        if isinstance(x, dict) and x.get("id"):
            out.append(x)
    return out


def main():
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    first = "seen" not in st
    seen = set(st.get("seen", []))
    pushes = st.get("pushes", [])  # [[t, title]]
    while True:
        try:
            data = json.loads(NOTICES.read_text())
            items = notice_items(data)
        except Exception:
            items = []
        new = [x for x in items if x.get("id") and x["id"] not in seen]
        if first:  # don't replay the existing ring on first start
            seen |= {x["id"] for x in new}
            new, first = [], False
        now = time.time()
        pushes = [p for p in pushes if now - p[0] < 3600]
        for x in new:
            seen.add(x["id"])
            title = x.get("title", "")
            if dash_connected():
                log(id=x["id"], title=title, result="skip_dash_connected")
                continue
            if any(p[1] == title and now - p[0] < DEDUPE_S for p in pushes):
                log(id=x["id"], title=title, result="skip_duplicate")
                continue
            if len(pushes) >= HOURLY_MAX:
                log(id=x["id"], title=title, result="skip_hourly_cap")
                continue
            serial = phone_serial()
            if not serial:
                log(id=x["id"], title=title, result="no_adb_phone")
                continue
            rc, out = push(serial, x["id"], title, x.get("body", ""))
            ok = rc == 0 and "Error" not in out
            if ok:
                pushes.append([now, title])
            log(id=x["id"], title=title, result="pushed" if ok else "push_failed",
                out=out[-200:])
        st = {"seen": sorted(seen)[-500:], "pushes": pushes}
        STATE.write_text(json.dumps(st))
        time.sleep(10)


if __name__ == "__main__":
    main()
