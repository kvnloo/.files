#!/usr/bin/env python3
"""Run ONE admitted phone job (the body of each Kueue-admitted Kubernetes Job).

  runner.py <job-id>

Order, always:
  1. device: the Kueue flavor this Workload was admitted on (z0.dev/phone -> phone-s22|phone-s25)
  2. gate: phone-worker's gate (S25 switch, call state, owner idle) -> else result "blocked"
  3. app pacing (ChatGPT only): shared quota pause + pace.py send budget -> else "blocked"
  4. take the two host UI flocks, in launch_queue.py's order: ~/tmp/<dev>-ui.lock (Dash e2e /
     native test workers) then /tmp/<dev>-ui.lock (tern-queue-loop, phone-worker ui, ds_burst)
  5. re-gate under the lock (+ the ChatGPT driver's owner_busy), record the foreground app
  6. run the harness: chat/script (burst.py / deepseek_burst.py) or fx (goal loop)
  7. oracle on a fresh redacted hierarchy, independent of the agent's "done"
  8. restore the previous foreground app, release the lock, write result.json
Runs under the chatgpt-driver venv python (uiautomator2 3.7.0).
"""
import calendar
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LOCK_WAIT_S = common.LOCK_WAIT_S
PACE_WAIT_S = common.PACE_WAIT_S
REPLY_WAIT_S = common.REPLY_WAIT_S
FX_TIMEOUT_S = common.FX_TIMEOUT_S
LAUNCHERS = {"com.teslacoilsw.launcher", "dev.omalauncher", "com.sec.android.app.launcher"}


class Blocked(Exception):
    pass


class Unavailable(Exception):
    """The requested model cannot be served (error code model_unavailable; no phone time used)."""


def model_preflight(model):
    """None if the shim can serve `model`; raise Unavailable only when the shim says so (404).
    A shim that is down, restarting or whose backend is unreachable is infrastructure trouble,
    not a property of the model: that blocks the job (retried later, no phone time used)."""
    url = common.SHIM_URL + "/phoneq/available?" + urllib.parse.urlencode({"model": model})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            if json.load(r).get("available"):
                return None
            raise Blocked(f"infra: model shim gave no verdict for {model}")
    except urllib.error.HTTPError as e:
        try:
            why = json.loads(e.read()).get("error")
        except ValueError:
            why = None
        if e.code == 404:
            raise Unavailable(why or f"model_unavailable: {model}") from None
        raise Blocked(f"infra: model shim HTTP {e.code}: {why or ''}".strip()) from None
    except OSError as e:
        raise Blocked(f"infra: model shim unreachable at {common.SHIM_URL}: {e}") from None


# ChatGPT chrome that is never part of a reply.
# ChatGPT status lines that render as text between our bubble and the reply. Buttons (Copy,
# Share, Stop, ...) are content-desc only, so a one-word reply such as "Copy" or "Stop" survives.
CHROME = re.compile(r"^(Thinking|Searching.*|Show more|Show less|(Worked|Thought) for .*)$", re.I)


def _left(node):
    m = re.match(r"\[(-?\d+),", node.get("bounds") or "")
    return int(m.group(1)) if m else None


def reply_from_tree(root, tag, sent=""):
    """The assistant reply as rendered text after our tagged user bubble (no clipboard: reading
    it would expose whatever another app or the owner last copied).

    Our own bubble is consumed strictly in order: the tag node, then only nodes that continue
    the sent text exactly where the previous bubble node ended AND sit in the bubble's column
    (ChatGPT right-aligns user bubbles; replies start at the left margin). Everything after the
    bubble is the reply, even when it repeats words of the prompt ('Repeat: hello' -> 'hello')."""
    nodes = [n for n in root.iter("node") if (n.get("text") or "").strip()]
    hit = max((i for i, n in enumerate(nodes) if tag in n.get("text", "")), default=None)
    if hit is None:
        return None
    first = nodes[hit].get("text").strip()
    at = sent.find(first)
    rest = sent[at + len(first):] if at >= 0 else ""
    col = _left(nodes[hit])
    out = []
    app = nodes[hit].get("package")
    in_bubble = True
    for n in nodes[hit + 1:]:
        if (n.get("class") or "").endswith("EditText"):
            break
        if app and n.get("package") not in (None, app):  # status bar clock etc.
            continue
        t = n.get("text").strip()
        if in_bubble:
            left = _left(n)
            same_column = col is None or left is None or left >= col - 8
            if same_column and rest.strip() and rest.lstrip().startswith(t):
                rest = rest.lstrip()[len(t):]
                continue
            in_bubble = False
        if not CHROME.match(t):
            out.append(t)
    return "\n".join(out).strip() or None


def on_term(signum, _frame):
    raise SystemExit(f"terminated by signal {signum}")  # runs finally: restore + unlock


def resolve_device(job):
    if job["device"] in common.DEVICES:
        return job["device"]
    kube = common.Kube()
    deadline = time.time() + 60
    while time.time() < deadline:
        dev = common.workload_flavor(kube.workload_for_job(os.environ["PHONEQ_K8S_JOB"]))
        if dev:
            return dev
        time.sleep(2)
    raise RuntimeError("could not read the Kueue flavor for this job")


def gate(dev):
    return common.phone_worker().gate(dev)


def driver():
    sys.path.insert(0, str(common.DRIVER))
    import burst
    return burst


def launch_queue():
    return common.load_source("launch_queue", common.DRIVER / "tern-01/launch_queue.py")


# pace.py decides and reserves in one step (it appends to pace.reserved on a grant). PEEK runs
# the very same pace.py with that one append turned into "would grant" (exit 0, nothing
# written), so the runner can wait for budget OUTSIDE the UI locks and reserve only once it
# holds them and the gate/owner checks passed: a blocked attempt never burns a send slot.
PACE_PEEK = r"""
import builtins, runpy, sys
_open = builtins.open
def _peek_open(f, mode="r", *a, **k):
    if str(f).endswith("pace.reserved") and "a" in mode:
        raise SystemExit(0)
    return _open(f, mode, *a, **k)
builtins.open = _peek_open
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def pace_check(app, peek=True):
    """(granted, message) from pace.py; peek=True never reserves."""
    pace = str(common.DRIVER / "bin/pace.py")
    cmd = [sys.executable, "-c", PACE_PEEK, pace] if peek else [sys.executable, pace]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout.strip() or p.stderr.strip()[-200:] or "gap")


def pace_wait(app, dev):
    """Before the locks: honour the pauses and wait (<= PACE_WAIT_S) until pace.py WOULD grant a
    ChatGPT send slot, without reserving one. Returns ms waited."""
    lq = launch_queue()
    if app != "chatgpt":
        if app == "deepseek" and lq.deepseek_quota_paused():
            raise Blocked("DeepSeek quota pause present (/tmp/deepseek-quota-pause)")
        return 0
    t0 = time.time()
    while True:
        if lq.quota_paused():
            raise Blocked("ChatGPT shared quota pause active (/tmp/chatgpt-quota-pause)")
        ok, msg = pace_check(app, peek=True)
        if ok:
            return int((time.time() - t0) * 1000)
        if time.time() - t0 > PACE_WAIT_S:
            raise Blocked("ChatGPT send budget held by pace.py: " + msg)
        time.sleep(5)


def pace_reserve(app):
    """Under the locks, after the gate/owner re-check: reserve the slot for real (one try; a
    loser of a race with another loop is blocked and retried, nothing reserved)."""
    if app != "chatgpt":
        return None
    if launch_queue().quota_paused():
        raise Blocked("ChatGPT shared quota pause active (/tmp/chatgpt-quota-pause)")
    ok, msg = pace_check(app, peek=False)
    if not ok:
        raise Blocked("ChatGPT send budget taken while waiting for the phone: " + msg)
    return common.now_iso()


def ui_lock_paths(dev):
    """Both host UI mutexes, outer first (tern-01/launch_queue.py order, so no lock-order
    inversion with it): ~/tmp/<dev>-ui.lock is held by Dash e2e/native test workers while they
    drive the screen; /tmp/<dev>-ui.lock by tern-queue-loop, phone-worker ui and ds_burst."""
    return [common.HOME / "tmp" / f"{dev}-ui.lock", Path(f"/tmp/{dev}-ui.lock")]


def paced_app(job):
    """The pacing account a job spends: every chat job (any harness) and any goal aimed at the
    ChatGPT/DeepSeek apps. None for other goals."""
    app = job.get("app")
    if job["kind"] == "chat":
        return "deepseek" if app in ("deepseek", common.APPS["deepseek"]) else (
            "chatgpt" if app in (None, "chatgpt", common.APPS["chatgpt"]) else None)
    return {"chatgpt": "chatgpt", common.APPS["chatgpt"]: "chatgpt",
            "deepseek": "deepseek", common.APPS["deepseek"]: "deepseek"}.get(app)


def fx_chat_aftercare(app, dev, d, job, result):
    """What the script driver does after a send, for fx-driven chats too: stamp the dispatch,
    detect a rate-limit screen and set the same shared quota pause, log the dispatch."""
    tag = tag_for(job)
    try:
        if app == "chatgpt":
            Path(f"/tmp/chatgpt-last-dispatch-{dev}").write_text(str(time.time()) + "\n")
        import phone_tools
        _pkg, root = phone_tools.safe_tree(d)
        low = phone_tools.tree_text(root).lower()
        burst = driver()
        hits = [w for w in burst.RATE_WORDS if w in low and w not in (job.get("prompt") or "").lower()]
        if hits:
            result["rate_words"] = hits
            if app == "chatgpt":
                launch_queue().quota_paused(time.time() + 3 * 3600)
            else:
                launch_queue().deepseek_quota_paused(limited=tag)
        (common.DRIVER / "phoneq-01").mkdir(exist_ok=True)
        with (common.DRIVER / "phoneq-01").joinpath("dispatches.jsonl").open("a") as f:
            f.write(json.dumps({"at": burst.now(), "tag": tag, "status": "fx" if not hits else "rate_limited",
                                "device": dev, "source": "phone-queue", "job": job["id"], "app": app,
                                "harness": "fx"}) + "\n")
    except Exception as e:  # noqa: BLE001 - evidence; never masks the job outcome
        result["aftercare_error"] = f"{type(e).__name__}: {e}"


def take_lock(dev, wait_s=None):
    """Take every UI lock for `dev` within one shared deadline; returns ([files], wait_ms)."""
    wait_s = LOCK_WAIT_S if wait_s is None else wait_s
    held = []
    t0 = time.time()
    try:
        for path in ui_lock_paths(dev):
            path.parent.mkdir(exist_ok=True)
            f = open(path, "a")
            held.append(f)
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() - t0 > wait_s:
                        raise Blocked(f"{path} busy for {wait_s}s") from None
                    time.sleep(0.5)
    except BaseException:
        for f in held:
            f.close()
        raise
    return held, int((time.time() - t0) * 1000)


def release_lock(held):
    for f in reversed(held or []):
        f.close()


def tag_for(job):
    return "PQ-" + job["id"][:10].upper()


# ------------------------------------------------------------------ harnesses
def chat_script(job, dev, serial, d, result, jdir):
    """Reuse the deterministic drivers; the brief text keeps burst's '(tag X)' preamble shape."""
    burst = driver()
    app = job.get("app") or "chatgpt"
    tag = tag_for(job)
    text = f"Phone queue (tag {tag}).\n\nTASK: {job['prompt']}"
    rec = {"tag": tag, "at": burst.now(), "device": dev, "transport": serial, "send_attempted": False}
    chat = {"app": app, "tag": tag}
    if app == "chatgpt":
        box = burst.new_chat(d, dev)
        status = burst.send(d, box, text, rec, device=dev)
        chat["send_status"] = status
        Path(f"/tmp/chatgpt-last-dispatch-{dev}").write_text(str(time.time()) + "\n")
        low = d.dump_hierarchy().lower()
        hits = [w for w in burst.RATE_WORDS if w in low and w not in text.lower()]
        if hits:
            status = chat["send_status"] = "rate_limited"
            launch_queue().quota_paused(time.time() + 3 * 3600)  # same 3 h shared pause as launch_queue
            chat["rate_words"] = hits
        if status == "sent":
            import phone_tools
            # Completion and reply both come from the redacted hierarchy (u2 selectors can match
            # off-screen nodes: a stale "Stop" kept a finished reply "running" for 240 s).
            t0 = time.time()
            pkg = root = reply = prev = None
            running, scrolled = True, False
            stable = 0
            while time.time() - t0 < REPLY_WAIT_S:
                time.sleep(2)
                pkg, root = phone_tools.safe_tree(d)
                descs = [(n.get("content-desc") or "").strip() for n in root.iter("node")
                         if n.get("package") == burst.PKG]
                running = any(x.lower().startswith("stop") for x in descs)
                reply = reply_from_tree(root, tag, text)
                if not running and "Copy" in descs:
                    if reply or scrolled:
                        break
                    d(description="Scroll to the bottom").click_exists(timeout=1)
                    scrolled = True
                # A reply taller than the screen pushes its Copy button below the fold: no Stop
                # button and the same reply text on 3 consecutive polls (~6 s) is finished too.
                stable = stable + 1 if (not running and reply and reply == prev) else 0
                prev = reply
                if stable >= 2:
                    chat["finished_by"] = "stable_text"
                    break
            if root is not None:
                (jdir / "reply-tree.xml").write_bytes(ET.tostring(root))
            durs = [n.get("text") for n in root.iter("node") if re.match(r"(Worked|Thought) for", n.get("text") or "")]
            reply = None if running else reply
            chat.update(duration=durs[-1] if durs else None, still_running=running, reply=reply,
                        reply_source="redacted hierarchy" if reply else None, reply_package=pkg,
                        reply_wait_ms=int((time.time() - t0) * 1000))
    elif app == "deepseek":
        if dev != "s22":
            raise RuntimeError("the DeepSeek driver is S22-only")
        import deepseek_burst as ds
        reason = burst.owner_busy(serial, device=dev)
        if reason:
            raise Blocked(f"owner busy: {reason}")
        snap = burst.activity_snapshot(serial)
        d.screen_on()
        d.app_start(ds.PKG)
        burst.record_agent_open(dev, ds.PKG, snap)
        if not burst.wait_for(lambda: d.app_current().get("package") == ds.PKG, 5):
            raise RuntimeError("DeepSeek did not reach foreground")
        status = ds.dispatch(d, text, rec)
        chat["send_status"] = status
        if status == "rate_limited":
            launch_queue().deepseek_quota_paused(limited=tag)
        chat["reply"] = None
        chat["note"] = "deepseek_burst has no reply harvester; launch receipt only"
    else:
        raise RuntimeError(f"no deterministic chat driver for app {app!r}; use harness=fx")
    for k in ("fresh_composer", "prompt_verified", "user_bubble_verified", "send_attempted", "error"):
        if k in rec:
            chat[k] = rec[k]
    (common.DRIVER / "phoneq-01").mkdir(exist_ok=True)
    with (common.DRIVER / "phoneq-01").joinpath("dispatches.jsonl").open("a") as f:
        f.write(json.dumps({"at": rec["at"], "tag": tag, "status": chat["send_status"], "device": dev,
                            "source": "phone-queue", "job": job["id"], "app": app}) + "\n")
    return chat_outcome(app, tag, chat, result)


def chat_outcome(app, tag, chat, result):
    """Job verdict for a script chat. Success means the caller got what it queued for: a
    ChatGPT chat succeeds only with a harvested, finished reply. Sent-but-no-reply is a
    failure whose error says not to resend (send_status stays 'sent' in result.chat)."""
    chat["reply_harvested"] = bool(chat.get("reply"))
    result["chat"] = chat
    result["final_output"] = chat.get("reply") or ""
    result["steps"] = 1
    if chat["send_status"] != "sent":
        result["error_code"] = "send_failed" if chat["send_status"] != "rate_limited" else "rate_limited"
        result["error"] = f"chat send status {chat['send_status']}"
        return False
    if app == "deepseek":
        # Dispatch-only driver (no reply harvester exists): success means "sent and verified",
        # stated explicitly so no caller mistakes it for an answer.
        result["final_output"] = f"deepseek chat {tag}: sent (dispatch only; no reply harvester)"
        return True
    if chat.get("still_running"):
        result["error_code"] = "reply_timeout"
        result["error"] = f"sent, but the reply was still generating after {REPLY_WAIT_S}s (do not resend)"
        return False
    if not chat.get("reply"):
        result["error_code"] = "reply_not_harvested"
        result["error"] = "sent and finished, but no reply text was found after the tagged bubble (do not resend)"
        return False
    return True


def goal_prompt(job, dev):
    if job["kind"] == "goal":
        goal = job["goal"]
    else:
        goal = (f"Open the {job.get('app') or 'chatgpt'} app, start a NEW chat, put this job's message in "
                "the composer with set_text(from_job_prompt=true) (it types the message exactly; do not "
                "retype it), send it, wait for the reply to finish and report the reply text verbatim. "
                f"The message begins: {job['prompt'][:200]!r}")
    if job["kind"] == "goal" and job.get("prompt"):
        goal += ("\nThis job carries a text attachment; type it with set_text(from_job_prompt=true) "
                 "wherever the goal says to enter it (never retype it).")
    phone = {"s22": "Samsung Galaxy S22+ (Android 16, One UI 8)", "s25": "Samsung Galaxy S25 Ultra (Android 17)"}[dev]
    return (f"Phone: {phone}. Goal: {goal}\n"
            "Use only the mcp_phone_* tools. Observe first. When done, answer with the result.")


def run_fx(job, dev, serial, jdir, result):
    home = jdir / "fxhome"
    work = jdir / "work"
    # fx keeps credentials as files when no keyring exists (pods) and refuses a non-private
    # state dir (PrivateStatePermissionsUnsupported): ~/.fx must be 0700, files 0600.
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / ".fx").mkdir(mode=0o700, exist_ok=True)
    os.chmod(home, 0o700)
    os.chmod(home / ".fx", 0o700)
    work.mkdir(exist_ok=True)
    env_mcp = {"PHONEQ_DEVICE": dev, "PHONEQ_SERIAL": serial, "PHONEQ_JOB_DIR": str(jdir),
               "PHONEQ_STATE": str(common.STATE), "HOME": str(common.HOME)}
    common.write_json(home / ".fx/mcp.json", {"mcpServers": {"phone": {
        "command": str(common.DRIVER_PY), "args": [str(common.APP_DIR / "phone_tools.py"), "mcp"], "env": env_mcp}}})
    os.chmod(home / ".fx/mcp.json", 0o600)
    env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
           "FX_SKIP_ONBOARDING": "1", "FX_AUTO_UPGRADE": "0", "FX_NO_OPEN_BROWSER": "1",
           "FX_MAX_AGENT_STEPS": str(job.get("max_steps") or 30),
           "FX_GATEWAY_BASE_URL": common.SHIM_URL, "FX_GATEWAY_CHAT_URL": common.SHIM_URL + "/v4/ai/language-model",
           "AI_GATEWAY_API_KEY": common.job_token(job["id"], int(os.environ.get("PHONEQ_ATTEMPT", "1"))),
           "FX_TRACE_LOG": str(jdir / "fx.trace.log"),
           **{k: v for k, v in env_mcp.items() if k != "HOME"}}  # fx keeps its isolated HOME
    assert env["HOME"] == str(home)
    cmd = [str(common.FX), "ask", "--json", "--no-save", "--auto", "--model", job["model"], "--", goal_prompt(job, dev)]
    t0 = time.time()
    with open(jdir / "fx.stderr.log", "w") as err:
        p = subprocess.run(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=err, text=True, timeout=FX_TIMEOUT_S)
    (jdir / "fx.json").write_text(p.stdout)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {"exit_code": p.returncode, "error": "fx printed no JSON"}
    usage = out.get("usage") or {}
    result.update(final_output=out.get("final_output") or out.get("output") or "", steps=out.get("steps"),
                  tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
                  fx={"exit_code": out.get("exit_code", p.returncode), "ms": int((time.time() - t0) * 1000),
                      "tool_calls": [t.get("name") for t in out.get("tool_calls") or []],
                      "error": out.get("error") or out.get("auth_failure")})
    rows = [r for r in (json.loads(x) for x in _lines(jdir / "model.jsonl")) if isinstance(r, dict)]
    steps = [r for r in rows if r.get("kind") == "step"]
    if result.get("tokens_in") is None and steps:
        result["tokens_in"] = sum(r.get("tokens_in") or 0 for r in steps)
        result["tokens_out"] = sum(r.get("tokens_out") or 0 for r in steps)
    if out.get("exit_code", p.returncode) != 0:
        unavail = [r["error"] for r in rows if r.get("kind") == "error" and "model_unavailable" in str(r.get("error"))]
        if unavail and not steps:
            result["error_code"] = "model_unavailable"
            result["error"] = unavail[0]
        else:
            try:
                tail = (jdir / "fx.stderr.log").read_text()[-2000:]
            except OSError:
                tail = ""
            why = out.get("error") or (out.get("output") or "")[:300]
            if "step limit reached" in tail.lower():
                result["error_code"] = "step_limit"
                why = why or f"agent step limit reached (max_steps={job.get('max_steps') or 30})"
            result["error"] = f"fx exit {out.get('exit_code', p.returncode)}: {why or tail.strip().splitlines()[-1:] or ''}"
        return False
    return True


def _lines(path):
    try:
        return [x for x in Path(path).read_text().splitlines() if x.strip().startswith("{")]
    except OSError:
        return []


def write_transcript(jdir, result):
    """transcript.jsonl: one row per model decision (choose_ms) and per phone action (tool_ms),
    in time order. Sources: the shim's model.jsonl and the tool layer's tools.jsonl."""
    rows = []
    for x in _lines(jdir / "model.jsonl"):
        r = json.loads(x)
        if r.get("kind") == "step":
            rows.append({"t": r["at"], "type": "decision", "model": r.get("model"), "choose_ms": r.get("choose_ms", r.get("ms")),
                         "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out"),
                         "calls": r.get("calls"), "text": r.get("text"), "dropped": r.get("dropped")})
        elif r.get("kind") == "error":
            rows.append({"t": r["at"], "type": "model_error", "error": r.get("error"), "status": r.get("status")})
    for x in _lines(jdir / "tools.jsonl"):
        r = json.loads(x)
        rows.append({"t": r.get("t") or calendar.timegm(time.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ")),
                     "type": "action", "tool": r.get("tool"), "args": r.get("args"), "ok": r.get("ok"),
                     "tool_ms": r.get("ms"), "result": (r.get("result") or "")[:500]})
    if result.get("oracle"):
        rows.append({"t": time.time(), "type": "oracle", "oracle": result["oracle"]})
    rows.sort(key=lambda r: r["t"])
    path = jdir / "transcript.jsonl"
    with path.open("w") as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({"i": i, **r}) + "\n")
    return str(path)


def oracle(job, d, result):
    """Independent check on a fresh redacted hierarchy (never the agent's say-so).
      must_contain      - substrings of the screen; for chat jobs, of the REPLY only (the screen
                          also shows our own prompt bubble, which would pass trivially)
      must_not_contain  - substrings that must appear nowhere on the screen or in the reply
      final_must_contain- substrings the agent's/harvested final_output must contain (checks the
                          reported VALUE, not just a label on screen)
      package           - the foreground package at the end"""
    spec = job.get("oracle")
    if not spec:
        return None
    import phone_tools
    pkg, root = phone_tools.safe_tree(d)
    text = phone_tools.tree_text(root)
    final = result.get("final_output") or ""
    if job["kind"] == "chat":
        reply = (result.get("chat") or {}).get("reply") or final
        scope, scope_name = reply.lower(), "reply"
    else:
        scope, scope_name = text.lower(), "screen"
    missing = [s for s in spec.get("must_contain") or [] if s.lower() not in scope]
    present = [s for s in spec.get("must_not_contain") or [] if s.lower() in text.lower() or s.lower() in final.lower()]
    final_missing = [s for s in spec.get("final_must_contain") or [] if s.lower() not in final.lower()]
    pkg_ok = not spec.get("package") or spec["package"] == pkg
    ok = not missing and not present and not final_missing and pkg_ok
    result["oracle"] = {"type": spec.get("type", "tree_text"), "package": pkg, "pass": ok, "missing": missing,
                        "must_contain_scope": scope_name, "final_missing": final_missing,
                        "forbidden_present": present, "package_ok": pkg_ok, "tree_chars": len(text)}
    return ok


def restore(d, dev, serial, before, result):
    """Bring back what the owner/other agents had in front (phone-worker ui semantics)."""
    burst = driver()
    current = lambda: burst.activity_snapshot(serial)["package"]  # noqa: E731 - dumpsys, as before
    try:
        after = current()
    except Exception:  # noqa: BLE001
        after = None
    result["foreground_after_job"] = after
    if not before or after == before:
        result["restored"] = True
        return
    try:
        if before in LAUNCHERS:
            d.press("home")
        else:
            d.shell(["monkey", "-p", before, "-c", "android.intent.category.LAUNCHER", "1"])
        time.sleep(1.5)
        now = current()
        result["foreground_restored_to"] = now
        result["restored"] = now == before
    except Exception as e:  # noqa: BLE001
        result["restored"] = False
        result["restore_error"] = f"{type(e).__name__}: {e}"


def connect_healthy(phone_tools, burst, serial, result, tries=3):
    """u2 connect + the driver's health check. The u2 HTTP link to the on-phone server drops
    now and then (another driver just released the phone): retry, and if it stays down block
    the job as infrastructure (retried in 30 s) instead of failing it."""
    last = None
    for i in range(tries):
        try:
            d = phone_tools.connect(serial)
            burst.healthy(d)
            return d
        except (ConnectionError, OSError, TimeoutError) as e:  # RemoteDisconnected is a ConnectionError
            last = e
            result.setdefault("connect_retries", []).append(f"{type(e).__name__}: {e}"[:120])
            time.sleep(3 * (i + 1))
        except Exception as e:  # noqa: BLE001 - requests/u2 wrap the same drop
            if "RemoteDisconnected" not in repr(e) and "Connection" not in type(e).__name__:
                raise
            last = e
            result.setdefault("connect_retries", []).append(f"{type(e).__name__}: {e}"[:120])
            time.sleep(3 * (i + 1))
    raise Blocked(f"infra: uiautomator2 link to {serial} kept dropping: {type(last).__name__}: {last}"[:300])


def main(job_id):
    signal.signal(signal.SIGTERM, on_term)
    jdir = common.job_dir(job_id)
    job = common.read_json(jdir / "job.json")
    attempt = int(os.environ.get("PHONEQ_ATTEMPT", "1"))
    t0 = time.time()
    result = {"id": job_id, "attempt": attempt, "started_at": common.now_iso(t0), "kind": job["kind"],
              "harness": job["harness"], "model": job["model"], "transcript_dir": str(jdir),
              "transcript_path": str(jdir / "transcript.jsonl")}
    state = "failed"
    lock = d = before = None
    try:
        dev = resolve_device(job)
        result["device"] = dev
        if job["harness"] == "fx":
            model_preflight(job["model"])
        reason = gate(dev)
        if reason:
            raise Blocked(f"gate {dev}: {reason}")
        pw = common.phone_worker()
        serial = pw.device(dev).serial
        result["serial"] = serial
        paced = paced_app(job)
        if paced:
            # one ChatGPT account across both phones and every harness: script and fx chats
            # alike need a pace.py send slot and honour the shared quota pauses. Wait for budget
            # without reserving; reserve only under the locks once every check passed.
            result["pace_wait_ms"] = pace_wait(paced, dev)
        lock, result["lock_wait_ms"] = take_lock(dev)
        reason = gate(dev)
        burst = driver()
        reason = reason or burst.owner_busy(serial, device=dev)
        if reason:
            raise Blocked(f"gate {dev} (under lock): {reason}")
        if paced:
            result["pace_reserved_at"] = pace_reserve(paced)
        import phone_tools
        c0 = time.time()
        d = connect_healthy(phone_tools, burst, serial, result)
        result["cold_ms"] = int((time.time() - c0) * 1000)
        before = burst.activity_snapshot(serial)["package"]
        result["foreground_before"] = before
        if job.get("reset", "home") == "home" and job["kind"] == "goal":
            d.press("home")
            time.sleep(0.8)
        if job["kind"] == "chat" and job["harness"] == "script":
            ok = chat_script(job, dev, serial, d, result, jdir)
        else:
            ok = run_fx(job, dev, serial, jdir, result)
            if paced:
                fx_chat_aftercare(paced, dev, d, job, result)
            if ok and job["kind"] == "chat" and not (result.get("final_output") or "").strip():
                ok = False  # a chat succeeds only with a reply, whatever the harness
                result["error_code"] = "reply_not_harvested"
                result["error"] = "fx finished but reported no reply (do not resend)"
        verdict = oracle(job, d, result)
        if verdict is not None:
            result["oracle_pass"] = verdict
        state = "succeeded" if ok and verdict is not False else "failed"
        if ok and verdict is False:
            result["error"] = "oracle failed: " + json.dumps(result["oracle"])
    except Blocked as e:
        state = "blocked"
        result["error"] = str(e)
        if str(e).startswith("infra:"):
            result["error_code"] = "infra_unavailable"
    except Unavailable as e:
        result["error_code"] = "model_unavailable"
        result["error"] = str(e) if "model_unavailable" in str(e) else f"model_unavailable: {e}"
    except SystemExit as e:
        state = "cancelled"
        result["error"] = str(e)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if d is not None:
            restore(d, result.get("device"), result.get("serial"), before, result)
        release_lock(lock)
        result["state"] = state
        try:
            result["transcript_path"] = write_transcript(jdir, result)
        except Exception as e:  # noqa: BLE001 - evidence only
            result["transcript_error"] = f"{type(e).__name__}: {e}"
        result["finished_at"] = common.now_iso()
        result["ms"] = int((time.time() - t0) * 1000)
        common.write_json(jdir / f"result-{attempt}.json", result)
        common.write_json(jdir / "result.json", result)
        print(json.dumps({k: result.get(k) for k in ("id", "state", "device", "error", "oracle_pass", "ms")}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
