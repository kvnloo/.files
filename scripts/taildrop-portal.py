#!/usr/bin/env python3
"""Tailnet-only upload/download portal for Android clients with broken Taildrop receiving."""

from __future__ import annotations

import argparse
from datetime import datetime
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import shutil
from urllib.parse import parse_qs, quote, unquote, urlsplit

INBOX = Path.home() / "Downloads" / "Taildrop"
OUTBOX = INBOX / "To Phone"
CHUNK_SIZE = 1024 * 1024
MIN_FREE_BYTES = 1024 * 1024 * 1024


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1000
    return f"{value:.1f} TB"


def unique_destination(name: str) -> tuple[Path, int]:
    clean = Path(name).name.strip() or "upload"
    stem = Path(clean).stem
    suffix = Path(clean).suffix
    candidate = INBOX / clean
    index = 1
    while True:
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            return candidate, descriptor
        except FileExistsError:
            candidate = INBOX / f"{stem} ({index}){suffix}"
            index += 1


class PortalHandler(BaseHTTPRequestHandler):
    server_version = "TaildropPortal/1"

    def normalized_path(self) -> str:
        path = urlsplit(self.path).path
        if path == "/drop":
            return "/"
        if path.startswith("/drop/"):
            return path[5:]
        return path

    def do_GET(self) -> None:
        path = self.normalized_path()
        if path == "/" or path == "/index.html":
            self.send_index()
        elif path == "/health":
            self.send_text(HTTPStatus.OK, "ok\n", "text/plain; charset=utf-8")
        elif path.startswith("/download/"):
            self.send_download(unquote(path.removeprefix("/download/")), head_only=False)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:
        path = self.normalized_path()
        if path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "3")
            self.end_headers()
        elif path.startswith("/download/"):
            self.send_download(unquote(path.removeprefix("/download/")), head_only=True)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        path = self.normalized_path()
        if path != "/upload":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(HTTPStatus.LENGTH_REQUIRED)
            return
        if length < 0:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        free = shutil.disk_usage(INBOX).free
        if length + MIN_FREE_BYTES > free:
            self.send_error(HTTPStatus.INSUFFICIENT_STORAGE, "Not enough free space")
            return

        query = parse_qs(urlsplit(self.path).query)
        requested_name = query.get("name", [""])[0]
        destination, descriptor = unique_destination(requested_name)
        remaining = length
        try:
            with os.fdopen(descriptor, "wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("upload ended early")
                    output.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionError, OSError):
            destination.unlink(missing_ok=True)
            self.close_connection = True
            return

        payload = {"name": destination.name, "bytes": length}
        self.send_text(HTTPStatus.CREATED, f"{payload['name']}\n", "text/plain; charset=utf-8")

    def send_index(self) -> None:
        rows: list[str] = []
        for path in sorted(OUTBOX.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
            except OSError:
                continue
            name = html.escape(path.name)
            href = "download/" + quote(path.name)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %H:%M")
            rows.append(
                f'<a class="file" href="{href}" download><span>{name}</span>'
                f'<small>{human_size(stat.st_size)} · {modified}</small></a>'
            )
        files = "".join(rows) or '<p class="empty">No files staged from the PC.</p>'
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Groot Drop</title><style>
:root {{ color-scheme: dark; font-family: system-ui, sans-serif; background:#10111a; color:#e6e7f0; }}
body {{ max-width:720px; margin:auto; padding:24px 18px 64px; }}
h1 {{ margin-bottom:4px; }} .sub,.empty {{ color:#a7abc0; }}
.card {{ background:#1a1c29; border:1px solid #34384f; border-radius:18px; padding:18px; margin-top:18px; }}
label.upload {{ display:block; padding:22px; border:2px dashed #7aa2f7; border-radius:14px; text-align:center; color:#b4d0ff; cursor:pointer; }}
input {{ display:none; }} progress {{ width:100%; margin-top:12px; accent-color:#9ece6a; }}
#status {{ min-height:24px; color:#9ece6a; }}
.file {{ display:flex; justify-content:space-between; gap:12px; padding:14px 4px; color:#c0caf5; text-decoration:none; border-bottom:1px solid #2b2e40; }}
.file:last-child {{ border:0; }} .file span {{ overflow-wrap:anywhere; }} .file small {{ color:#9095aa; white-space:nowrap; }}
button {{ border:0; border-radius:10px; background:#7aa2f7; color:#10111a; padding:11px 16px; font-weight:700; }}
</style></head><body>
<h1>Groot Drop</h1><div class="sub">Private to your Tailscale network.</div>
<section class="card"><h2>Phone → PC</h2><label class="upload">Choose files to upload<input id="picker" type="file" multiple></label>
<progress id="progress" value="0" max="1"></progress><p id="status"></p></section>
<section class="card"><h2>PC → Phone</h2>{files}</section>
<script>
const picker=document.querySelector('#picker'), progress=document.querySelector('#progress'), status=document.querySelector('#status');
picker.addEventListener('change', async () => {{
  const files=[...picker.files]; let completed=0; progress.max=files.reduce((n,f)=>n+f.size,0)||1; progress.value=0;
  for (const file of files) {{
    status.textContent=`Uploading ${{file.name}}…`;
    await new Promise((resolve,reject)=>{{
      const request=new XMLHttpRequest(); request.open('PUT',`upload?name=${{encodeURIComponent(file.name)}}`);
      request.upload.onprogress=e=>{{ if(e.lengthComputable) progress.value=completed+e.loaded; }};
      request.onload=()=>request.status===201?resolve():reject(new Error(request.statusText||`HTTP ${{request.status}}`));
      request.onerror=()=>reject(new Error('Network error')); request.send(file);
    }});
    completed+=file.size; progress.value=completed;
  }}
  status.textContent=`Uploaded ${{files.length}} file${{files.length===1?'':'s'}} to Downloads/Taildrop.`; picker.value='';
}}).catch(error=>{{ status.textContent=`Upload failed: ${{error.message}}`; }});
</script></body></html>"""
        self.send_text(HTTPStatus.OK, page, "text/html; charset=utf-8")

    def send_download(self, name: str, head_only: bool) -> None:
        clean = Path(name).name
        path = OUTBOX / clean
        try:
            if clean != name or not path.is_file():
                raise FileNotFoundError
            size = path.stat().st_size
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        start = 0
        end = size - 1
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            try:
                first, last = range_header[6:].split("-", 1)
                start = int(first) if first else 0
                end = int(last) if last else end
                if start < 0 or end < start or start >= size:
                    raise ValueError
                end = min(end, size - 1)
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return

        content_length = max(0, end - start + 1)
        self.send_response(HTTPStatus.PARTIAL_CONTENT if range_header else HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = content_length
                while remaining:
                    chunk = source.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_text(self, status: HTTPStatus, text: str, content_type: str) -> None:
        payload = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        # Do not leak file names or URLs into the journal.
        print(f"{self.client_address[0]} {self.command} {args[1] if len(args) > 1 else '-'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    INBOX.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), PortalHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
