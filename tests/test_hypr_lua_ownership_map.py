import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "config/hyprland/lua-ownership-map.json"
LIVE_LINK = Path.home() / ".config/hypr/hyprland.conf"
MONITORS_CONF = Path.home() / ".config/hypr/monitors.conf"
ALLOWED_APIS = {
    "hl.config",
    "hl.monitor",
    "hl.workspace_rule",
    "hl.window_rule",
    "hl.layer_rule",
    "hl.bind",
    "hl.on",
    "require",
    "generated Lua artifact",
    "explicit bridge",
}
SCRIPT_COMMAND = re.compile(
    r"""(?x)
    (?:hyprctl|HYPRCTL_BIN|hypr)\s+
    (?:keyword|dispatch)
    |
    ["']hyprctl["']\s*,\s*["'](?:keyword|dispatch)["']
    |
    hypr\(\s*["'](?:keyword|dispatch)["']
    """
)


def _expand(raw: str) -> Path:
    path = os.path.expandvars(os.path.expanduser(raw.strip()))
    resolved = Path(path)
    if not resolved.exists() and path.startswith("/home/kvn/workspace/.files/"):
        resolved = Path("/workspace/.files") / path[len("/home/kvn/workspace/.files/") :]
    return resolved


def _split_comment(raw: str) -> tuple[str, str | None]:
    if "#" not in raw:
        return raw.rstrip(), None
    code, comment = raw.split("#", 1)
    return code.rstrip(), comment.strip()


def walk_hyprlang(entry: Path) -> tuple[list[dict], list[dict], list[str]]:
    lines: list[dict] = []
    comments: list[dict] = []
    sourced: list[str] = []
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        real = path.resolve()
        if real in seen:
            return
        seen.add(real)
        rel = str(real)
        try:
            rel = str(real.relative_to(ROOT))
        except ValueError:
            pass
        text = path.read_text()
        for number, raw in enumerate(text.splitlines(), 1):
            code, comment = _split_comment(raw)
            stripped = code.strip()
            if comment is not None and (not stripped):
                comments.append({"file": rel, "line": number, "text": comment})
                continue
            if comment is not None:
                comments.append({"file": rel, "line": number, "text": comment})
            if not stripped:
                continue
            record = {"file": rel, "line": number, "text": stripped}
            lines.append(record)
            if stripped.startswith("source") and "=" in stripped:
                target = _expand(stripped.split("=", 1)[1])
                sourced.append(str(target))
                if target.exists():
                    visit(target)

    visit(entry)
    return lines, comments, sourced


def live_entry() -> Path:
    return LIVE_LINK.resolve()


def test_ownership_map_artifact_exists_and_is_json():
    assert MAP_PATH.is_file()
    payload = json.loads(MAP_PATH.read_text())
    assert isinstance(payload, dict)
    assert payload["unclassified"] == []


def test_every_recursive_non_comment_line_is_classified_exactly_once():
    payload = json.loads(MAP_PATH.read_text())
    expected, _, _ = walk_hyprlang(live_entry())
    actual = [
        (item["file"], item["line"], item["text"])
        for item in payload["lines"]
        if item.get("origin") != "runtime_bridge"
    ]
    wanted = [(item["file"], item["line"], item["text"]) for item in expected]
    assert actual == wanted
    assert payload["unclassified"] == []
    for item in payload["lines"]:
        assert item["lua_api"] in ALLOWED_APIS, item


def test_comments_are_listed_separately_and_never_as_directives():
    payload = json.loads(MAP_PATH.read_text())
    _, comments, _ = walk_hyprlang(live_entry())
    listed = [(item["file"], item["line"]) for item in payload["comments"]]
    wanted = [(item["file"], item["line"]) for item in comments]
    assert listed == wanted
    directive_keys = {(item["file"], item["line"]) for item in payload["lines"]}
    for item in payload["comments"]:
        if not item.get("inline"):
            assert (item["file"], item["line"]) not in directive_keys


def test_pywal_and_liquid_glass_sources_are_followed_and_owned():
    payload = json.loads(MAP_PATH.read_text())
    _, _, sourced = walk_hyprlang(live_entry())
    joined = " ".join(sourced)
    assert "colors-hyprland.conf" in joined
    assert "liquid-glass.conf" in joined
    by_file = {}
    for item in payload["lines"]:
        by_file.setdefault(item["file"], []).append(item)
    pywal = [item for item in payload["lines"] if item["file"].endswith("colors-hyprland.conf")]
    glass = [item for item in payload["lines"] if item["file"].endswith("liquid-glass.conf")]
    assert pywal, "pywal generated colors were not inventoried"
    assert all(item["lua_api"] == "generated Lua artifact" for item in pywal)
    assert glass, "liquid-glass fragment was not inventoried"
    assert all(item["lua_api"] in {"hl.window_rule", "explicit bridge"} for item in glass)
    source_lines = [item for item in payload["lines"] if item["text"].startswith("source")]
    assert len(source_lines) >= 2
    assert {item["lua_api"] for item in source_lines} <= {"generated Lua artifact", "explicit bridge"}


def test_helper_scripts_that_issue_hyprctl_keyword_or_dispatch_are_explicit_bridges():
    payload = json.loads(MAP_PATH.read_text())
    found: list[tuple[str, int]] = []
    for path in (ROOT / "scripts").rglob("*"):
        if not path.is_file() or path.suffix not in {".sh", ".py"}:
            continue
        try:
            body = path.read_text()
        except UnicodeDecodeError:
            continue
        for number, raw in enumerate(body.splitlines(), 1):
            if SCRIPT_COMMAND.search(raw) and not raw.lstrip().startswith("#"):
                found.append((str(path.relative_to(ROOT)), number))
    bridges = {
        (item["file"], item["line"])
        for item in payload["runtime_bridges"]
    }
    missing = [item for item in found if item not in bridges]
    assert not missing, missing
    required = {
        "scripts/phone-display.sh",
        "scripts/gui-e2e-display.sh",
    }
    present_files = {item["file"] for item in payload["runtime_bridges"]}
    assert required <= present_files
    for item in payload["runtime_bridges"]:
        assert item["lua_api"] == "explicit bridge"


def test_monitors_conf_is_inventoried_as_generated_and_not_hand_edited():
    payload = json.loads(MAP_PATH.read_text())
    generated = payload["generated_not_sourced"]
    assert any(item["path"].endswith("monitors.conf") for item in generated)
    for item in generated:
        if item["path"].endswith("monitors.conf"):
            assert item["lua_api"] == "generated Lua artifact"
            assert "do not hand-edit" in item["note"].lower()
    text = MONITORS_CONF.read_text()
    assert text.startswith("# Generated from the live layout by persist-monitor-layout.py.")


def test_live_startup_symlink_is_unchanged_legacy_hyprlang():
    assert LIVE_LINK.is_symlink()
    assert LIVE_LINK.resolve() == ROOT / "config/hyprland/hyprland.legacy.conf"
    payload = json.loads(MAP_PATH.read_text())
    assert Path(payload["live_target"]).resolve() == LIVE_LINK.resolve()
    assert payload["entry"].endswith("hyprland.legacy.conf")
