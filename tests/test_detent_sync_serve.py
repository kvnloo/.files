"""detent-sync-serve: the manifest a phone reads, the files it may fetch, and theme choices."""
import importlib.machinery
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "detent-sync-serve"


def load(tmp_path, monkeypatch):
    monkeypatch.setenv("DETENT_COLORS", str(tmp_path / "colors.json"))
    monkeypatch.setenv("DETENT_LIVE_LIST", str(tmp_path / "live.json"))
    monkeypatch.setenv("DETENT_SYNC_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("DETENT_SYNC_HOOK", str(tmp_path / "hook"))
    loader = importlib.machinery.SourceFileLoader("detent_sync_serve", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod._peers = (1e18, ["mbp.tailnet.ts.net"])  # no tailscale in tests
    return mod


@pytest.fixture
def srv(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    store = tmp_path / "mpkg"
    store.mkdir()
    (store / "1.mpkg").write_bytes(b"PKGM scene")
    (tmp_path / "colors.json").write_text(json.dumps({"mSurface": "#181f23", "mOnSurface": "#d1deda", "mPrimary": "#c8be72"}))
    (tmp_path / "live.json").write_text(json.dumps({
        "mobile_store": str(store),
        "wallpapers": [
            {"title": "Scene One", "detent_name": "one", "mobile": {"file": "1.mpkg"},
             "detent": {"bg": "112122", "fg": "dae5e7", "accent": "90d8df"}},
            {"title": "Elsewhere", "detent_name": "two", "mobile": {"file": "2.mpkg"},
             "detent": {"bg": "112122", "fg": "dae5e7", "accent": "90d8df"}},
            {"title": "Escape", "detent_name": "evil", "mobile": {"file": "../secret.mpkg"},
             "detent": {"bg": "112122", "fg": "dae5e7", "accent": "90d8df"}},
        ],
    }))
    httpd = mod.http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield mod, f"http://127.0.0.1:{httpd.server_port}", tmp_path
    httpd.shutdown()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_manifest_offers_colours_and_only_packages_on_this_machine(srv):
    mod, base, _ = srv
    code, body, headers = get(base + "/v1/manifest")
    m = json.loads(body)
    assert code == 200 and m["version"] == 1
    assert m["colors"]["bg"] == "181f23" and m["colors"]["updated"] > 0
    assert [e["name"] for e in m["live"]] == ["one"]
    assert m["live"][0]["sha256"] == __import__("hashlib").sha256(b"PKGM scene").hexdigest()
    assert m["peers"] == ["mbp.tailnet.ts.net"]
    # Unchanged state costs a 304.
    assert get(base + "/v1/manifest", {"If-None-Match": headers["ETag"]})[0] == 304
    # tailscale serve may pass the /detent prefix through.
    assert get(base + "/detent/v1/manifest")[0] == 200


def test_only_listed_packages_can_be_fetched(srv):
    _, base, _ = srv
    assert get(base + "/v1/files/1.mpkg")[:2] == (200, b"PKGM scene")
    assert get(base + "/v1/files/2.mpkg")[0] == 404
    assert get(base + "/v1/files/..%2Fsecret.mpkg")[0] == 404
    assert get(base + "/v1/files/colors.json")[0] == 404


def test_a_newer_theme_choice_is_kept_and_runs_the_hook(srv):
    mod, base, tmp = srv
    hook = tmp / "hook"
    hook.write_text(f"#!/bin/sh\necho \"$1|$2\" > {tmp}/hook.out\n")
    os.chmod(hook, 0o755)
    assert post(base + "/v1/selection", {"theme": "black-hole", "device": "Galaxy S22+", "at": 200}) == (200, {"result": "kept"})
    assert post(base + "/v1/selection", {"theme": "dusk", "device": "S25", "at": 100})[1]["result"] == "older than the kept choice"
    m = json.loads(get(base + "/v1/manifest")[1])
    assert m["selection"] == {"theme": "black-hole", "device": "Galaxy S22+", "at": 200}
    for _ in range(50):
        if (tmp / "hook.out").exists():
            break
        __import__("time").sleep(0.05)
    assert (tmp / "hook.out").read_text().strip() == "black-hole|Galaxy S22+"


def test_bad_choices_are_refused(srv):
    _, base, _ = srv
    assert post(base + "/v1/selection", {"theme": "", "at": 5})[0] == 400
    assert post(base + "/v1/selection", {"theme": "x" * 41, "at": 5})[0] == 400
    assert post(base + "/v1/selection", {"theme": "dusk"})[0] == 400
    assert post(base + "/v1/other", {"theme": "dusk", "at": 1})[0] == 404


def test_a_machine_without_inputs_serves_an_empty_manifest(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    m, files = mod.manifest()
    assert m["version"] == 1 and "colors" not in m and "live" not in m and files == {}
