#!/usr/bin/env python3
"""Capture Hyprland workspaces into a private, pan-and-zoom localhost atlas."""

from __future__ import annotations

import html
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = 41739
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "workspace-atlas"
SHOTS = CACHE / "shots"
INDEX = CACHE / "index.html"
ROOT_URL = f"http://{HOST}:{PORT}/"
CAPTURE_LOCK = threading.Lock()


def run(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def hypr_json(command: str) -> list[dict]:
    result = run("hyprctl", "-j", command, capture=True)
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        raise RuntimeError(f"hyprctl {command} returned an unexpected value")
    return value


def hypr(*args: str) -> None:
    run("hyprctl", *args)


def capture_atlas() -> list[dict]:
    with CAPTURE_LOCK:
        CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(CACHE, 0o700)
        monitors = hypr_json("monitors")
        workspaces = [
            workspace
            for workspace in hypr_json("workspaces")
            if int(workspace.get("id", 0)) > 0 and workspace.get("monitor")
        ]
        monitor_by_name = {monitor["name"]: monitor for monitor in monitors}
        workspaces = [workspace for workspace in workspaces if workspace["monitor"] in monitor_by_name]
        workspaces.sort(key=lambda workspace: (int(workspace["id"]), workspace["monitor"]))

        originals = {
            monitor["name"]: int((monitor.get("activeWorkspace") or {}).get("id", 0))
            for monitor in monitors
        }
        focused_monitor = next(
            (monitor["name"] for monitor in monitors if monitor.get("focused")),
            monitors[0]["name"] if monitors else "",
        )

        staging = Path(tempfile.mkdtemp(prefix="shots-", dir=CACHE))
        captured: list[dict] = []
        try:
            for workspace in workspaces:
                workspace_id = int(workspace["id"])
                monitor_name = str(workspace["monitor"])
                monitor = monitor_by_name[monitor_name]
                hypr("dispatch", "focusmonitor", monitor_name)
                hypr("dispatch", "workspace", str(workspace_id))
                time.sleep(0.10)

                raw_path = staging / f"ws-{workspace_id}.png"
                thumb_path = staging / f"ws-{workspace_id}.jpg"
                run("grim", "-l", "1", "-o", monitor_name, str(raw_path))
                run(
                    "magick",
                    str(raw_path),
                    "-thumbnail",
                    "960x600>",
                    "-strip",
                    "-quality",
                    "84",
                    str(thumb_path),
                )
                raw_path.unlink(missing_ok=True)
                captured.append(
                    {
                        "id": workspace_id,
                        "name": str(workspace.get("name") or workspace_id),
                        "monitor": monitor_name,
                        "windows": int(workspace.get("windows", 0)),
                        "current": originals.get(monitor_name) == workspace_id,
                        "image": f"shots/{thumb_path.name}",
                        "width": int(monitor.get("width", 0)),
                        "height": int(monitor.get("height", 0)),
                    }
                )
        finally:
            for monitor_name, workspace_id in originals.items():
                if workspace_id > 0:
                    hypr("dispatch", "focusmonitor", monitor_name)
                    hypr("dispatch", "workspace", str(workspace_id))
            if focused_monitor:
                hypr("dispatch", "focusmonitor", focused_monitor)

        old_shots = CACHE / "shots.old"
        shutil.rmtree(old_shots, ignore_errors=True)
        if SHOTS.exists():
            SHOTS.rename(old_shots)
        staging.rename(SHOTS)
        shutil.rmtree(old_shots, ignore_errors=True)
        render_index(captured, monitors)
        return captured


def render_index(workspaces: list[dict], monitors: list[dict]) -> None:
    monitor_order = [
        monitor["name"]
        for monitor in sorted(monitors, key=lambda monitor: (int(monitor.get("x", 0)), int(monitor.get("y", 0))))
    ]
    grouped: dict[str, list[dict]] = {name: [] for name in monitor_order}
    for workspace in workspaces:
        grouped.setdefault(workspace["monitor"], []).append(workspace)

    card_width = 520
    card_height = 350
    gap = 70
    positioned: list[dict] = []
    for column, monitor_name in enumerate(monitor_order):
        for row, workspace in enumerate(grouped.get(monitor_name, [])):
            positioned.append(
                workspace
                | {
                    "x": column * (card_width + gap),
                    "y": row * (card_height + gap),
                    "cardWidth": card_width,
                    "cardHeight": card_height,
                }
            )

    generated = time.strftime("%Y-%m-%d %H:%M:%S")
    data = json.dumps(positioned, separators=(",", ":")).replace("</", "<\\/")
    document = ATLAS_HTML.replace("__ATLAS_DATA__", data).replace("__GENERATED__", html.escape(generated))
    temp_index = CACHE / "index.html.tmp"
    temp_index.write_text(document, encoding="utf-8")
    temp_index.replace(INDEX)


def open_atlas() -> None:
    url = f"{ROOT_URL}?t={int(time.time())}"
    browser = shutil.which("zen-browser") or shutil.which("google-chrome-stable")
    if browser:
        subprocess.Popen(
            [browser, "--new-window", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    else:
        webbrowser.open(url)


def notify(message: str) -> None:
    notifier = shutil.which("notify-send")
    if notifier:
        subprocess.Popen(
            [notifier, "-a", "Workspace atlas", message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "WorkspaceAtlas/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_bytes(INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
            return
        if path.startswith("/shots/"):
            candidate = SHOTS / Path(path).name
            if candidate.parent == SHOTS and candidate.is_file():
                self.send_bytes(candidate.read_bytes(), "image/jpeg")
                return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/refresh":
            try:
                captured = capture_atlas()
            except Exception as error:
                self.send_bytes(str(error).encode(), "text/plain; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            notify(f"Refreshed {len(captured)} workspaces")
            self.send_bytes(json.dumps({"workspaces": len(captured)}).encode(), "application/json")
            return
        if path.startswith("/switch/"):
            value = path.removeprefix("/switch/")
            if not value.isdigit() or int(value) <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            try:
                hypr("dispatch", "workspace", value)
            except subprocess.CalledProcessError:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self.send_bytes(b"{}", "application/json")
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def refresh_existing_server() -> bool:
    request = urllib.request.Request(f"{ROOT_URL}refresh", method="POST", data=b"")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == HTTPStatus.OK
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> int:
    if refresh_existing_server():
        open_atlas()
        return 0

    CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), AtlasHandler)
    captured = capture_atlas()
    notify(f"Captured {len(captured)} workspaces")
    open_atlas()

    def stop(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever(poll_interval=0.5)
    server.server_close()
    return 0


ATLAS_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workspace Atlas</title>
<style>
:root { color-scheme: dark; --cyan:#7dcfff; --purple:#bb9af7; --green:#9ece6a; --panel:rgba(24,27,38,.86); }
* { box-sizing: border-box; }
html, body { width:100%; height:100%; margin:0; overflow:hidden; background:#0b0e14; color:#c0caf5; font:14px/1.4 Inter, system-ui, sans-serif; }
body::before { content:""; position:fixed; inset:0; background:radial-gradient(circle at 30% 20%,rgba(125,207,255,.10),transparent 35%),radial-gradient(circle at 75% 70%,rgba(187,154,247,.09),transparent 32%); pointer-events:none; }
#grid { position:fixed; inset:0; background-image:linear-gradient(rgba(125,207,255,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(125,207,255,.045) 1px,transparent 1px); background-size:42px 42px; transform-origin:0 0; }
#world { position:absolute; left:0; top:0; transform-origin:0 0; will-change:transform; }
.card { position:absolute; padding:12px; border:1px solid rgba(125,207,255,.26); border-radius:18px; background:var(--panel); box-shadow:0 20px 55px rgba(0,0,0,.42),inset 0 1px rgba(255,255,255,.05); backdrop-filter:blur(18px); transition:border-color .15s,box-shadow .15s; user-select:none; }
.card:hover { border-color:var(--cyan); box-shadow:0 24px 70px rgba(0,0,0,.55),0 0 30px rgba(125,207,255,.12); }
.card.current { border-color:rgba(158,206,106,.72); }
.card img { display:block; width:100%; height:286px; object-fit:contain; border-radius:11px; background:#080a10; pointer-events:none; }
.meta { height:38px; display:flex; align-items:center; gap:10px; padding:8px 3px 0; }
.workspace { font-weight:800; color:#fff; letter-spacing:.02em; }
.monitor { color:var(--cyan); }
.windows { margin-left:auto; color:#7f849c; }
.dot { width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 10px var(--green); }
#hud { position:fixed; z-index:10; left:20px; top:20px; padding:13px 16px; border:1px solid rgba(125,207,255,.25); border-radius:14px; background:rgba(12,15,23,.84); backdrop-filter:blur(16px); box-shadow:0 16px 42px rgba(0,0,0,.35); pointer-events:none; }
#hud strong { display:block; color:#fff; font-size:16px; }
#hud span { color:#7f849c; font-size:12px; }
#toast { position:fixed; z-index:11; left:50%; bottom:24px; translate:-50% 20px; opacity:0; padding:10px 15px; border-radius:999px; background:rgba(20,24,35,.94); border:1px solid rgba(125,207,255,.3); transition:.18s; }
#toast.show { translate:-50% 0; opacity:1; }
</style>
</head>
<body>
<div id="grid"></div><div id="world"></div>
<div id="hud"><strong>Workspace Atlas</strong><span>drag to pan · wheel to zoom · double-click to open · R refresh · 0 fit</span><span>captured __GENERATED__</span></div>
<div id="toast"></div>
<script>
const atlas = __ATLAS_DATA__;
const world = document.querySelector('#world');
const grid = document.querySelector('#grid');
const toast = document.querySelector('#toast');
let x=80, y=100, scale=1, dragging=false, moved=false, sx=0, sy=0, ox=0, oy=0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function apply(){ world.style.transform=`translate(${x}px,${y}px) scale(${scale})`; grid.style.transform=`translate(${x%42}px,${y%42}px) scale(${scale})`; }
function message(text){ toast.textContent=text; toast.classList.add('show'); clearTimeout(message.timer); message.timer=setTimeout(()=>toast.classList.remove('show'),1300); }
for(const item of atlas){
  const card=document.createElement('article'); card.className='card'+(item.current?' current':'');
  card.style.cssText=`left:${item.x}px;top:${item.y}px;width:${item.cardWidth}px;height:${item.cardHeight}px`;
  const image=document.createElement('img'); image.src=item.image+'?t='+Date.now(); image.alt=`Workspace ${item.name}`;
  const meta=document.createElement('div'); meta.className='meta';
  if(item.current){ const dot=document.createElement('i'); dot.className='dot'; meta.append(dot); }
  const ws=document.createElement('span'); ws.className='workspace'; ws.textContent=`Workspace ${item.name}`;
  const monitor=document.createElement('span'); monitor.className='monitor'; monitor.textContent=item.monitor;
  const windows=document.createElement('span'); windows.className='windows'; windows.textContent=`${item.windows} window${item.windows===1?'':'s'}`;
  meta.append(ws,monitor,windows); card.append(image,meta);
  card.addEventListener('dblclick',async event=>{ event.stopPropagation(); await fetch(`/switch/${item.id}`,{method:'POST'}); message(`Opened workspace ${item.name}`); });
  world.append(card);
}
function fit(){
  if(!atlas.length){ x=80;y=100;scale=1;apply();return; }
  const minX=Math.min(...atlas.map(v=>v.x)), minY=Math.min(...atlas.map(v=>v.y));
  const maxX=Math.max(...atlas.map(v=>v.x+v.cardWidth)), maxY=Math.max(...atlas.map(v=>v.y+v.cardHeight));
  scale=clamp(Math.min((innerWidth-120)/(maxX-minX),(innerHeight-120)/(maxY-minY)),.18,1);
  x=(innerWidth-(maxX-minX)*scale)/2-minX*scale; y=(innerHeight-(maxY-minY)*scale)/2-minY*scale; apply();
}
addEventListener('pointerdown',event=>{ if(event.button!==0)return; dragging=true;moved=false;sx=event.clientX;sy=event.clientY;ox=x;oy=y;document.body.setPointerCapture?.(event.pointerId); });
addEventListener('pointermove',event=>{ if(!dragging)return; const dx=event.clientX-sx,dy=event.clientY-sy;moved ||= Math.abs(dx)+Math.abs(dy)>3;x=ox+dx;y=oy+dy;apply(); });
addEventListener('pointerup',()=>dragging=false);
addEventListener('wheel',event=>{ event.preventDefault();const beforeX=(event.clientX-x)/scale,beforeY=(event.clientY-y)/scale;scale=clamp(scale*Math.exp(-event.deltaY*.0012),.16,2.5);x=event.clientX-beforeX*scale;y=event.clientY-beforeY*scale;apply(); },{passive:false});
addEventListener('keydown',async event=>{ if(event.key==='0')fit(); if(event.key.toLowerCase()==='r'){message('Refreshing workspaces…');await fetch('/refresh',{method:'POST'});location.reload();} });
addEventListener('resize',fit); fit();
</script>
</body>
</html>'''


if __name__ == "__main__":
    raise SystemExit(main())
