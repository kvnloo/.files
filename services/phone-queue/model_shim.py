#!/usr/bin/env python3
"""Local model gateway for fx (vercel-labs/fx >= 0.0.15) inside the phone queue.

fx talks the Vercel AI Gateway language-model protocol (AI SDK spec v3/v4 stream parts).
fx accepts a loopback override: FX_GATEWAY_BASE_URL (catalog) and FX_GATEWAY_CHAT_URL (chat).
This shim answers both and routes by model id:

  openai-codex/<slug>   ChatGPT subscription via Hermes' own OAuth client, exactly like
                        dash-log-watch-model.py: resolve_provider_client("openai-codex",
                        model=slug, raw_codex=True) -> Responses API at chatgpt.com/backend-api/codex
  local/<name>          groot llama router (OpenAI-compatible) at PHONEQ_LLAMA_URL
  ollama/<name>         groot ollama (OpenAI-compatible) at PHONEQ_OLLAMA_URL
  gateway/<id>          real Vercel AI Gateway, only if AI_GATEWAY_API_KEY is set here

Policy (this gateway serves phone jobs only):
  - fx's coding system prompt is replaced by PHONE_SYSTEM (also keeps 8k-context SLMs usable);
  - the model sees ONLY the phone MCP tools (mcp_phone_*); a call to any other tool is dropped;
  - the first step is answered locally with capability_search(server=phone) so fx loads the
    phone MCP schemas (fx defers MCP tools until searched);
  - fx --auto permission reviews of mcp_phone_* actions are answered "clear" here; every other
    action gets "caution". The phone tool layer itself refuses installs/settings/shell.
Per-job model transcripts go to <state>/jobs/<id>/model.jsonl (job id = bearer "phoneq-job-<id>").
"""
import contextlib
import http.server
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

STATE = Path(os.environ.get("PHONEQ_STATE", "/mnt/zer0models/phone-queue/state"))
BIND = os.environ.get("PHONEQ_SHIM_BIND", "127.0.0.1")
PORT = int(os.environ.get("PHONEQ_SHIM_PORT", "8795"))
LLAMA = os.environ.get("PHONEQ_LLAMA_URL", "http://100.113.138.100:11530")
OLLAMA = os.environ.get("PHONEQ_OLLAMA_URL", "http://127.0.0.1:11434")
GATEWAY = os.environ.get("PHONEQ_GATEWAY_URL", "https://ai-gateway.vercel.sh/v4/ai/language-model")
HERMES_SOURCE = os.environ.get("PHONEQ_HERMES_SOURCE", "/workspace/hermes-home/hermes-agent")
EFFORT = os.environ.get("PHONEQ_EFFORT", "low")
CODEX_MODELS = ("gpt-6-luna", "gpt-6-terra", "gpt-6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
TOOL_PREFIX = "mcp_phone_"
JOB_RE = re.compile(r"^phoneq-job-([a-f0-9]{12})$")

PHONE_SYSTEM = """You operate a real Android phone through tools named mcp_phone_*.
Work in short steps: observe, decide one action, act, observe again.
- observe returns 'app: <package>' and rows '[index] label class flags @x,y'. Prefer tap(index=N) using the latest observe.
- swipe direction is the finger direction ('up' reveals content further down).
- Use launch(package) to open apps (com.android.settings is Settings). Never install, uninstall or change any setting or toggle; read only. Never type passwords, codes or payment data.
- When the goal is done, or clearly impossible, stop calling tools and give a short final answer that states the result and quotes the requested facts exactly as shown on screen."""


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ prompt utilities
def job_of(headers):
    m = JOB_RE.match((headers.get("authorization") or "").removeprefix("Bearer ").strip())
    return m.group(1) if m else None


def transcript(job, row):
    if not job:
        return
    path = STATE / "jobs" / job / "model.jsonl"
    try:
        with path.open("a") as f:
            f.write(json.dumps(row)[:200000] + "\n")
    except OSError:
        pass


def tool_output_text(output):
    kind = (output or {}).get("type")
    value = (output or {}).get("value")
    if kind in ("text", "error-text"):
        return str(value)
    if kind in ("json", "error-json"):
        return json.dumps(value)
    if kind == "execution-denied":
        return "DENIED: " + str((output or {}).get("reason") or "")
    if kind == "content":
        return "\n".join(p.get("text", "") for p in value or [] if p.get("type") == "text")
    return json.dumps(output)


def as_args(value):
    return value if isinstance(value, str) else json.dumps(value or {})


def phone_tools(req):
    return [t for t in req.get("tools") or [] if t.get("name", "").startswith(TOOL_PREFIX)]


def is_review(req):
    return [t.get("name") for t in req.get("tools") or []] == ["permission_decision"]


PHONE_TOOLS = tuple(TOOL_PREFIX + v for v in ("observe", "tap", "set_text", "swipe", "back", "home", "launch", "wait"))


def called(req, name):
    return sum(1 for m in req.get("prompt", []) if m.get("role") == "assistant"
               for p in m.get("content") or [] if p.get("type") == "tool-call" and p.get("toolName") == name)


def searched(req):
    return called(req, "capability_search") > 0


def missing_tools(req):
    have = {t.get("name") for t in phone_tools(req)}
    return [t for t in PHONE_TOOLS if t not in have]


def pending_review_tool(req):
    names = [p.get("toolName") for m in req.get("prompt", []) if m.get("role") == "assistant"
             for p in m.get("content") or [] if p.get("type") == "tool-call"]
    return names[-1] if names else None


def to_responses_input(prompt):
    items = []
    for m in prompt:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            continue  # replaced by PHONE_SYSTEM
        if role == "user":
            parts = []
            for p in content if isinstance(content, list) else [{"type": "text", "text": str(content)}]:
                if p.get("type") == "text":
                    parts.append({"type": "input_text", "text": p.get("text", "")})
                elif p.get("type") == "file" and str(p.get("mediaType", "")).startswith("image/"):
                    data = p.get("data")
                    if isinstance(data, str) and not data.startswith(("http", "data:")):
                        data = f"data:{p['mediaType']};base64,{data}"
                    parts.append({"type": "input_image", "image_url": data})
            if parts:
                items.append({"role": "user", "content": parts})
        elif role == "assistant":
            for p in content if isinstance(content, list) else [{"type": "text", "text": str(content)}]:
                if p.get("type") == "text" and p.get("text"):
                    items.append({"role": "assistant", "content": [{"type": "output_text", "text": p["text"]}]})
                elif p.get("type") == "tool-call":
                    items.append({"type": "function_call", "call_id": p["toolCallId"], "name": p["toolName"],
                                  "arguments": as_args(p.get("input"))})
        elif role == "tool":
            for p in content or []:
                if p.get("type") == "tool-result":
                    items.append({"type": "function_call_output", "call_id": p["toolCallId"],
                                  "output": tool_output_text(p.get("output"))[:20000]})
    return items


def to_chat_messages(prompt):
    msgs = [{"role": "system", "content": PHONE_SYSTEM}]
    for m in prompt:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            continue
        if role == "user":
            text = "\n".join(p.get("text", "") for p in content if p.get("type") == "text") \
                if isinstance(content, list) else str(content)
            msgs.append({"role": "user", "content": text})
        elif role == "assistant":
            text, calls = [], []
            for p in content if isinstance(content, list) else []:
                if p.get("type") == "text":
                    text.append(p.get("text", ""))
                elif p.get("type") == "tool-call":
                    calls.append({"id": p["toolCallId"], "type": "function",
                                  "function": {"name": p["toolName"], "arguments": as_args(p.get("input"))}})
            msg = {"role": "assistant", "content": "\n".join(text) or None}
            if calls:
                msg["tool_calls"] = calls
            msgs.append(msg)
        elif role == "tool":
            for p in content or []:
                if p.get("type") == "tool-result":
                    msgs.append({"role": "tool", "tool_call_id": p["toolCallId"],
                                 "content": tool_output_text(p.get("output"))[:12000]})
    return msgs


def tool_choice(req, flavor):
    tc = (req.get("toolChoice") or {}).get("type", "auto")
    if tc == "tool":
        name = req["toolChoice"].get("toolName")
        return {"type": "function", "name": name} if flavor == "responses" else \
            {"type": "function", "function": {"name": name}}
    return tc if tc in ("auto", "none", "required") else "auto"


# ------------------------------------------------------------------ backends
_hermes_lock = threading.Lock()
_hermes_ready = False


def hermes_client(slug):
    global _hermes_ready
    with _hermes_lock:
        if not _hermes_ready:
            sys.path.insert(0, HERMES_SOURCE)
            logging.disable(logging.CRITICAL)
            with contextlib.redirect_stdout(sys.stderr):
                import hermes_bootstrap  # noqa: F401
            _hermes_ready = True
        from agent.auxiliary_client import resolve_provider_client
        client, resolved = resolve_provider_client("openai-codex", model=slug, raw_codex=True)
    if client is None:
        raise Backend(503, "openai-codex credentials unavailable (Hermes profile)")
    if resolved != slug or str(client.base_url).rstrip("/") != "https://chatgpt.com/backend-api/codex":
        client.close()
        raise Backend(502, "openai-codex route mismatch")
    return client


class Backend(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def call_codex(slug, req, tools):
    if slug not in CODEX_MODELS:
        raise Backend(400, f"unknown openai-codex model {slug}")
    client = hermes_client(slug)
    try:
        kwargs = dict(model=slug, instructions=PHONE_SYSTEM, input=to_responses_input(req["prompt"]),
                      store=False, stream=True, reasoning={"effort": EFFORT})
        if tools:
            kwargs.update(tools=[{"type": "function", "name": t["name"], "description": t.get("description", ""),
                                  "parameters": t.get("inputSchema") or {"type": "object"}, "strict": False}
                                 for t in tools],
                          tool_choice=tool_choice(req, "responses"), parallel_tool_calls=False)
        texts, calls, usage, model = [], [], (None, None), None
        stream = client.with_options(max_retries=1, timeout=120).responses.create(**kwargs)
        with stream:
            for ev in stream:
                if ev.type == "response.output_item.done":
                    item = ev.item
                    if item.type == "message":
                        texts.extend(c.text for c in item.content if c.type == "output_text")
                    elif item.type == "function_call":
                        calls.append((item.call_id, item.name, item.arguments or "{}"))
                elif ev.type == "response.completed":
                    u = ev.response.usage
                    usage = (getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
                    model = ev.response.model
                elif ev.type in ("error", "response.failed", "response.incomplete"):
                    raise Backend(502, f"codex stream {ev.type}")
        return "\n".join(texts).strip(), calls, usage, "openai-codex/" + (model or slug)
    finally:
        client.close()


_local_models = {"at": 0, "llama": set(), "ollama": set()}


def local_catalog():
    if time.time() - _local_models["at"] > 60:
        try:
            with urllib.request.urlopen(LLAMA + "/v1/models", timeout=3) as r:
                _local_models["llama"] = {m["id"] for m in json.load(r).get("data", [])}
        except (OSError, ValueError):
            pass
        try:
            with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
                _local_models["ollama"] = {m["name"] for m in json.load(r).get("models", [])}
        except (OSError, ValueError):
            pass
        _local_models["at"] = time.time()
    return _local_models


def call_openai_compatible(base, name, req, tools):
    body = {"model": name, "messages": to_chat_messages(req["prompt"]), "stream": False,
            "max_tokens": min(int(req.get("maxOutputTokens") or 2048), 2048), "temperature": 0}
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                           "parameters": t.get("inputSchema") or {"type": "object"}}}
                         for t in tools]
        body["tool_choice"] = tool_choice(req, "chat")
    request = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise Backend(502, f"{base} HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except OSError as e:
        raise Backend(503, f"{base} unreachable: {e}") from None
    msg = (out.get("choices") or [{}])[0].get("message") or {}
    calls = [(c.get("id") or "call_" + uuid.uuid4().hex[:12], c["function"]["name"], c["function"].get("arguments") or "{}")
             for c in msg.get("tool_calls") or []]
    u = out.get("usage") or {}
    text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
    return text, calls, (u.get("prompt_tokens"), u.get("completion_tokens")), out.get("model") or name


# ------------------------------------------------------------------ v3 stream parts
def usage_v3(inp, out):
    return {"inputTokens": {"total": inp, "noCache": inp, "cacheRead": 0, "cacheWrite": 0},
            "outputTokens": {"total": out, "text": out, "reasoning": 0}}


def parts_for(text, calls, usage, model):
    parts = [{"type": "stream-start", "warnings": []},
             {"type": "response-metadata", "id": "resp_" + uuid.uuid4().hex[:16], "modelId": model}]
    if text:
        parts += [{"type": "text-start", "id": "t0"}, {"type": "text-delta", "id": "t0", "delta": text},
                  {"type": "text-end", "id": "t0"}]
    for cid, name, args in calls:
        parts.append({"type": "tool-call", "toolCallId": cid, "toolName": name, "input": args})
    reason = "tool-calls" if calls else "stop"
    parts.append({"type": "finish", "finishReason": {"unified": reason, "raw": reason},
                  "usage": usage_v3(*usage)})
    return parts


def bootstrap_parts(req):
    """fx defers MCP tools: search the phone server once, then exact-select whatever the
    search's schema budget left out, so the model always sees all eight phone verbs."""
    if not searched(req):
        calls = [("call_bootstrap_" + uuid.uuid4().hex[:8], "capability_search",
                  json.dumps({"query": "control the android phone screen: observe tap set_text swipe back home launch wait",
                              "server": "phone"}))]
    else:
        calls = [("call_select_" + uuid.uuid4().hex[:8], "mcp_select_tool", json.dumps({"name": name}))
                 for name in missing_tools(req)]
    return parts_for("", calls, (0, 0), "phoneq/bootstrap")


def needs_bootstrap(req):
    """Search first; then one exact-select round for missing verbs (never loop)."""
    if not searched(req):
        return True
    return bool(missing_tools(req)) and called(req, "mcp_select_tool") == 0


def review_parts(req):
    tool = pending_review_tool(req) or ""
    ok = tool.startswith(TOOL_PREFIX) or tool in ("capability_search", "mcp_select_tool")  # metadata-only
    args = {"decision": "clear" if ok else "caution",
            "rationale": "phone-queue tool layer (no install/settings/shell)" if ok
            else f"{tool or 'this action'} is outside the phone-queue tool whitelist"}
    return parts_for("", [("call_review_" + uuid.uuid4().hex[:8], "permission_decision", json.dumps(args))],
                     (0, 0), "phoneq/review")


def complete(req, model_id, job):
    """Return v3 parts for one fx model step (or raise Backend)."""
    t0 = time.time()
    if is_review(req):
        parts = review_parts(req)
        transcript(job, {"at": time.time(), "kind": "review", "tool": pending_review_tool(req),
                         "decision": json.loads(parts[2]["input"])["decision"]})
        return parts
    tools = phone_tools(req)
    if needs_bootstrap(req):
        transcript(job, {"at": time.time(), "kind": "bootstrap", "missing": missing_tools(req)})
        return bootstrap_parts(req)
    allowed = {t["name"] for t in tools}
    provider, _, name = model_id.partition("/")
    if provider == "openai-codex":
        text, calls, usage, model = call_codex(name, req, tools)
    elif provider == "local":
        cat = local_catalog()
        base = LLAMA if name in cat["llama"] or name not in cat["ollama"] else OLLAMA
        text, calls, usage, model = call_openai_compatible(base, name, req, tools)
    elif provider == "ollama":
        text, calls, usage, model = call_openai_compatible(OLLAMA, name, req, tools)
    else:
        raise Backend(400, f"unroutable model {model_id}")
    dropped = [c[1] for c in calls if c[1] not in allowed]
    calls = [c for c in calls if c[1] in allowed][:1]  # one action per step
    if dropped and not calls and not text:
        text = f"(blocked non-phone tools: {', '.join(dropped)})"
    transcript(job, {"at": time.time(), "kind": "step", "model": model, "ms": int((time.time() - t0) * 1000),
                     "tools": sorted(allowed),
                     "tokens_in": usage[0], "tokens_out": usage[1], "text": text[:4000],
                     "calls": [{"name": c[1], "args": c[2][:2000]} for c in calls], "dropped": dropped})
    return parts_for(text, calls, usage, model)


def catalog():
    data = [{"id": f"openai-codex/{m}", "name": m} for m in CODEX_MODELS]
    cat = local_catalog()
    data += [{"id": f"local/{m}", "name": m} for m in sorted(cat["llama"])]
    data += [{"id": f"ollama/{m}", "name": m} for m in sorted(cat["ollama"])]
    for d in data:
        d.update(object="model", created=0, owned_by="phone-queue", type="language",
                 context_window=8192 if d["id"].startswith(("local/", "ollama/")) else 200000,
                 max_tokens=2048 if d["id"].startswith(("local/", "ollama/")) else 32000, tags=["tool-use"])
    return {"object": "list", "data": data}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] in ("/healthz", "/"):
            return self._json(200, {"ok": True, "routes": ["openai-codex", "local", "ollama"] +
                                    (["gateway"] if os.environ.get("AI_GATEWAY_API_KEY") else [])})
        if self.path.split("?")[0].endswith("/models"):
            return self._json(200, catalog())
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n)
        job = job_of(self.headers)
        model_id = self.headers.get("ai-language-model-id") or ""
        try:
            req = json.loads(raw)
        except ValueError:
            return self._json(400, {"error": "invalid json"})
        if model_id.startswith("gateway/"):
            return self._gateway(req, model_id.removeprefix("gateway/"), job)
        try:
            parts = complete(req, model_id, job)
        except Backend as e:
            log("backend", model_id, e.status, e)
            transcript(job, {"at": time.time(), "kind": "error", "model": model_id, "status": e.status, "error": str(e)})
            return self._json(e.status, {"error": {"message": str(e), "type": "phoneq_backend"}})
        except Exception as e:  # noqa: BLE001
            log("error", model_id, type(e).__name__, e)
            transcript(job, {"at": time.time(), "kind": "error", "model": model_id, "error": f"{type(e).__name__}"})
            return self._json(502, {"error": {"message": f"{type(e).__name__}", "type": "phoneq_backend"}})
        self._stream(parts)

    def _stream(self, parts):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()
        for p in parts + ["[DONE]"]:
            data = ("data: " + (p if isinstance(p, str) else json.dumps(p)) + "\n\n").encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _gateway(self, req, real_id, job):
        key = os.environ.get("AI_GATEWAY_API_KEY")
        if not key:
            return self._json(503, {"error": {"message": "gateway route unavailable: no AI_GATEWAY_API_KEY on the shim"}})
        if is_review(req):
            return self._stream(review_parts(req))
        tools = phone_tools(req)
        if needs_bootstrap(req):
            return self._stream(bootstrap_parts(req))
        req = dict(req, tools=tools, prompt=[{"role": "system", "content": PHONE_SYSTEM}] +
                   [m for m in req["prompt"] if m.get("role") != "system"])
        headers = {k: v for k, v in self.headers.items() if k.lower().startswith(("ai-", "x-vercel"))}
        headers.update({"authorization": f"Bearer {key}", "content-type": "application/json",
                        "ai-language-model-id": real_id})
        request = urllib.request.Request(GATEWAY, data=json.dumps(req).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=300) as r:
                self.send_response(r.status)
                self.send_header("content-type", r.headers.get("content-type", "text/event-stream"))
                self.send_header("transfer-encoding", "chunked")
                self.end_headers()
                while chunk := r.read(8192):
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.write(b"0\r\n\r\n")
        except urllib.error.HTTPError as e:
            return self._json(e.code, {"error": {"message": e.read()[:500].decode(errors="replace")}})
        transcript(job, {"at": time.time(), "kind": "gateway", "model": real_id})


def main():
    srv = http.server.ThreadingHTTPServer((BIND, PORT), Handler)
    srv.daemon_threads = True
    log(f"phone-queue model shim on http://{BIND}:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
