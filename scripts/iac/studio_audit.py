#!/usr/bin/env python3
"""Read-only macOS host migration audit.

Inventories what lives on this Mac and whether it is already captured in code
(IaC roots such as .files and kvnloo/home), then writes a Markdown report with
one row per item: category, item, size, in IaC (yes/no), class, how to move it.

Read-only by construction:
  * never writes anywhere except the --out report file;
  * never runs git fetch/push or any network command;
  * never prints file contents. Secret-bearing files (auth.json, .env, keys,
    tokens) are listed by path and size only. LaunchAgent plists are parsed for
    Label and the program path only (EnvironmentVariables and arguments are
    never emitted because they can carry tokens).

Usage:
  python3 -I scripts/iac/studio_audit.py --out STUDIO-MIGRATION.md \
      [--iac-root ~/workspace/.files --iac-root /workspace/repos/home]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import plistlib
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()

SECRET_NAME = re.compile(
    r"(^auth\.json$|^\.env|token|secret|credential|password|\.pem$|\.key$|^id_[a-z0-9]+$|keychain|cookies)",
    re.I,
)
# Top-level dotfiles/dirs that are caches or OS-managed: reproducible, no action.
CACHE_DOTS = {
    ".Trash", ".cache", ".npm", ".bun", ".cargo", ".rustup", ".gradle", ".m2",
    ".pnpm-store", ".yarn", ".node-gyp", ".pyenv", ".nvm", ".local", ".zsh_sessions",
    ".DS_Store", ".CFUserTextEncoding", ".lesshst", ".viminfo", ".python_history",
    ".zsh_history", ".bash_history", ".zcompdump", ".wget-hsts", ".sqlite_history",
    ".node_repl_history", ".cups", ".swiftpm", ".expo", ".android", ".gem", ".go",
    ".vscode", ".cursor", ".docker", ".colima", ".ollama", ".hermes", ".config",
    ".dartServer", ".dart-tool", ".pub-cache", ".flutter", ".package-manager", ".matplotlib",
}
# Agent harness homes: sessions + OAuth tokens. Re-login; copy history only if wanted.
AGENT_STATE = re.compile(r"^\.(claude|codex|gemini|t3|agent-reach|agents|agentsview|omp|cua-driver|mcporter)", re.I)
REPO_PRUNE = {
    "node_modules", ".venv", "venv", ".uv-cache", ".hf", ".lake", "__pycache__",
    "pytest-of-kvn", "tmp", ".git", "target", "dist", "build", "uv",
}


@dataclass
class Row:
    category: str
    item: str
    size_kb: int | None
    in_iac: bool
    klass: str  # keep | secret | reproducible
    how: str


# Never let git reach the network: partial (blob:none) clones would otherwise
# lazy-fetch blobs during status/grep. No optional locks: status won't rewrite the index.
GIT_ENV = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}


def run(cmd: list[str], timeout: int = 60, cwd: str | None = None) -> str:
    try:
        env = GIT_ENV if cmd and cmd[0] == "git" else None
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def du_kb(path: Path, timeout: int = 60) -> int | None:
    out = run(["du", "-sk", str(path)], timeout=timeout)
    try:
        return int(out.split()[0])
    except (IndexError, ValueError):
        return None


def human(kb: int | None) -> str:
    if kb is None:
        return "?"
    size = float(kb)
    for unit in ("K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{size:.0f}{unit}" if unit == "K" else f"{size:.1f}{unit}"
        size /= 1024
    return "?"


def short(p: Path | str) -> str:
    s = str(p)
    h = str(HOME)
    return "~" + s[len(h):] if s.startswith(h) else s


class IacIndex:
    """Text search over the IaC roots (tracked files only, via git grep)."""

    def __init__(self, roots: list[Path]):
        self.roots = [r for r in roots if (r / ".git").exists()]

    def mentions(self, needle: str) -> bool:
        if not needle:
            return False
        for root in self.roots:
            out = run(["git", "-C", str(root), "grep", "-l", "-F", "-e", needle, "HEAD", "--"], timeout=30)
            if out.strip():
                return True
        return False

    def owns_path(self, path: Path) -> bool:
        try:
            real = path.resolve()
        except OSError:
            return False
        for root in self.roots:
            try:
                real.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False


# --------------------------------------------------------------------------- brew

def audit_brew(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    brew = shutil.which("brew")
    if not brew:
        return [Row("brew", "homebrew", None, False, "keep", "Install Homebrew first (bootstrap step).")]
    brewfiles = [p for r in idx.roots for p in r.rglob("Brewfile*") if ".git" not in p.parts]
    how = "Add to a Brewfile in .files (`brew bundle dump --file=...`), restore with `brew bundle`."
    for kind, cmd in (("formula", ["leaves"]), ("cask", ["list", "--cask"]), ("tap", ["tap"])):
        for name in run([brew, *cmd]).split():
            in_iac = any(re.search(rf'^\s*{kind if kind != "formula" else "brew"}\s+"{re.escape(name)}"', b.read_text(errors="ignore"), re.M) for b in brewfiles)
            rows.append(Row("brew " + kind, name, None, in_iac, "reproducible" if in_iac else "keep", how))
    if not shutil.which("mas"):
        rows.append(Row("mas", "mas CLI not installed", None, False, "keep",
                        "App Store apps are not enumerable; `brew install mas` then `mas list` and add `mas` lines to the Brewfile."))
    else:
        for line in run(["mas", "list"]).splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                rows.append(Row("mas", parts[1].strip(), None, idx.mentions(parts[0]), "keep", how))
    return rows


def audit_apps(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    casks = set(run(["brew", "list", "--cask"]).split()) if shutil.which("brew") else set()
    for base in (Path("/Applications"), HOME / "Applications"):
        if not base.is_dir():
            continue
        for app in sorted(base.glob("*.app")):
            # Apple-bundled apps ship with macOS.
            info = app / "Contents" / "Info.plist"
            bundle = ""
            try:
                with info.open("rb") as fh:
                    bundle = plistlib.load(fh).get("CFBundleIdentifier", "")
            except (OSError, plistlib.InvalidFileException, ValueError):
                pass
            if bundle.startswith("com.apple.") and app.name != "Xcode.app":
                rows.append(Row("app", f"{app.name} ({bundle})", None, False, "reproducible",
                                "Ships with macOS or Apple ID purchase; sign in to the App Store."))
                continue
            rows.append(Row("app", f"{app.name} ({bundle or 'no bundle id'})", du_kb(app, 30), False,
                            "keep", "Find the cask/mas id and add it to the Brewfile; app data, if any, is listed under app-support."))
    return rows


# ---------------------------------------------------------------------- launchd

def audit_launch_agents(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    for d in (HOME / "Library" / "LaunchAgents",):
        if not d.is_dir():
            continue
        for plist in sorted(d.glob("*.plist")):
            label, program = plist.stem, ""
            try:
                with plist.open("rb") as fh:
                    data = plistlib.load(fh)
                label = data.get("Label", label)
                program = data.get("Program") or (data.get("ProgramArguments") or [""])[0]
            except (OSError, plistlib.InvalidFileException, ValueError):
                pass
            plist_in_code = idx.owns_path(plist) or idx.mentions(plist.name) or idx.mentions(label)
            prog_in_code = bool(program) and idx.owns_path(Path(program))
            note = f"program {short(program)}" + (" (in IaC repo)" if prog_in_code else "") if program else "program ?"
            rows.append(Row("launchagent", f"{label} -> {note}", du_kb(plist, 10), plist_in_code, "keep",
                            "Template the plist into .files (config/macos/launchagents/) with an installer that runs "
                            "`launchctl bootstrap gui/$UID`; move the program into a repo if it is not already."))
    return rows


# --------------------------------------------------------------------- dotfiles

def audit_dotfiles(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    for p in sorted(HOME.iterdir()):
        if not p.name.startswith(".") or p.name in {".", ".."}:
            continue
        if p.is_symlink():
            in_iac = idx.owns_path(p)
            rows.append(Row("dotfile", f"{short(p)} -> {short(os.readlink(p))}", None, in_iac,
                            "reproducible" if in_iac else "keep",
                            "Recreated by `./scripts/onboard run core-links`." if in_iac else "Move the target into .files and link it."))
            continue
        if p.name in CACHE_DOTS:
            continue
        if ".bak" in p.name or p.name.endswith("-pre-onboard"):
            rows.append(Row("dotfile", short(p), du_kb(p, 30), False, "reproducible",
                            "Stale backup of a file now managed elsewhere; do not carry."))
            continue
        if AGENT_STATE.match(p.name):
            rows.append(Row("dotfile", short(p), du_kb(p, 60), False, "secret",
                            "Agent harness home (sessions + OAuth tokens): re-login on the new Mac; copy only settings/skills "
                            "(commit those to .files) and session history if wanted."))
            continue
        secret = bool(SECRET_NAME.search(p.name)) or p.name in {".ssh", ".gnupg", ".netrc", ".aws", ".kube", ".pypirc", ".npmrc"}
        rows.append(Row("dotfile", short(p), du_kb(p, 30), False, "secret" if secret else "keep",
                        "Secret: re-issue or carry via Bitwarden Secrets Manager (BWS); never commit." if secret
                        else "Review; move config into .files/config and link via core-links."))
    cfg = HOME / ".config"
    if cfg.is_dir():
        for p in sorted(cfg.iterdir()):
            if p.name.startswith("."):
                continue
            in_iac = p.is_symlink() and idx.owns_path(p)
            same_name = (idx.roots and any((r / "config" / p.name).exists() for r in idx.roots))
            secret = bool(SECRET_NAME.search(p.name)) or p.name in {"gh", "rclone"}
            how = ("Linked from .files." if in_iac else
                   f"Exists as .files/config/{p.name} but is not linked here; add a macOS link to core-links." if same_name else
                   "Review; move into .files/config and link via core-links.")
            if secret:
                how += " Holds credentials: re-auth (`gh auth login`, `rclone config`) or carry via BWS."
            rows.append(Row("xdg-config", short(p), None if in_iac else du_kb(p, 30), in_iac,
                            "secret" if secret else ("reproducible" if in_iac else "keep"), how))
    return rows


# ----------------------------------------------------------------------- hermes

def audit_hermes(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    root = HOME / ".hermes"
    if not root.is_dir():
        return rows
    agent = root / "hermes-agent"
    if agent.is_dir():
        rows.extend(audit_repo(agent, idx, category="hermes code"))
    homes = [("default", root)] + [(p.name, p) for p in sorted((root / "profiles").glob("*")) if p.is_dir()]
    for name, home in homes:
        for rel, klass, how in (
            ("config.yaml", "keep", "Not in IaC (only config/hermes/presets/small-host.yaml is). Commit a redacted profile preset to .files, or copy with `hermes profile export`."),
            ("SOUL.md", "keep", "Copy file; candidate for kvnloo/home canon."),
            ("memories", "keep", "Copy directory (rsync over Tailscale)."),
            ("cron", "keep", "Copy jobs.json; re-arm via cfg bot."),
            ("state.db", "keep", "Session history; copy with sqlite3 `.backup` while the gateway is stopped (Kevin step)."),
            ("kanban.db", "keep", "Board DB; `.backup` copy while dispatcher is idle (Kevin step)."),
            ("plugins", "keep", "Re-install from plugin repos; copy local-only plugins."),
            ("skills", "keep", "Link to kvnloo/home skills if not already."),
            ("auth.json", "secret", "Secret: do not copy in clear; re-run provider logins on the new Mac."),
            (".env", "secret", "Secret: carry via BWS (`scripts/install-bws-secrets`), never commit."),
        ):
            p = home / rel
            if not p.exists() and not p.is_symlink():
                continue
            in_iac = idx.owns_path(p)
            if rel == "skills" and p.is_symlink():
                rows.append(Row("hermes", f"{name}: {short(p)} -> {short(os.readlink(p))}", None, in_iac,
                                "reproducible" if in_iac else "keep", how))
                continue
            rows.append(Row("hermes", f"{name}: {short(p)}", du_kb(p, 120), in_iac, klass, how))
    return rows


# ------------------------------------------------------------------------- git

def find_repos(roots: list[Path], max_depth: int = 4) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        base_depth = len(root.resolve().parts)
        for dirpath, dirnames, filenames in os.walk(root.resolve(), followlinks=False):
            depth = len(Path(dirpath).parts) - base_depth
            if ".git" in dirnames or ".git" in filenames:
                real = os.path.realpath(dirpath)
                if real not in seen:
                    seen.add(real)
                    found.append(Path(dirpath))
                dirnames[:] = []  # do not descend into a repo (submodules/nested scratch)
                continue
            if depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in REPO_PRUNE and not d.startswith("pytest")]
    return sorted(found)


SEEN_COMMON: dict[str, Path] = {}


def audit_repo(repo: Path, idx: IacIndex, category: str = "repo") -> list[Row]:
    g = ["git", "-C", str(repo)]
    remote = run(g + ["remote", "get-url", "origin"], timeout=10).strip()
    remote = re.sub(r"https://[^@/]+@", "https://", remote)  # strip any embedded credentials
    dirty = len([l for l in run(g + ["status", "--porcelain", "--untracked-files=normal"], timeout=60).splitlines() if l.strip()])
    # Branches and stashes live in the shared common dir: report them once per
    # clone, not again for every linked worktree.
    common = os.path.realpath(os.path.join(str(repo), run(g + ["rev-parse", "--git-common-dir"], timeout=10).strip() or ".git"))
    first = SEEN_COMMON.setdefault(common, repo)
    shared_refs = first == repo
    stashes = len(run(g + ["stash", "list"], timeout=10).splitlines()) if shared_refs else 0
    unpushed_branches = []
    for line in ([] if not shared_refs else run(g + ["for-each-ref", "--format=%(refname:short)\t%(upstream:short)\t%(upstream:track)", "refs/heads"], timeout=30).splitlines()):
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        branch, upstream, track = parts
        if not upstream:
            # No upstream: unpushed only if it carries commits no remote ref has.
            n = run(g + ["rev-list", "--count", branch, "--not", "--remotes"], timeout=30).strip()
            if n and n != "0":
                unpushed_branches.append(f"{branch}(+{n}, no upstream)")
        elif "ahead" in track:
            unpushed_branches.append(f"{branch}{track}")
    is_worktree = (repo / ".git").is_file()
    clean = dirty == 0 and stashes == 0 and not unpushed_branches and bool(remote)
    bits = []
    if not remote:
        bits.append("no origin remote")
    if dirty:
        bits.append(f"{dirty} dirty/untracked paths")
    if stashes:
        bits.append(f"{stashes} stashes")
    if unpushed_branches:
        shown = ", ".join(unpushed_branches[:4]) + (f" +{len(unpushed_branches) - 4} more" if len(unpushed_branches) > 4 else "")
        bits.append(f"unpushed: {shown}")
    label = f"{short(repo)}{' [worktree]' if is_worktree else ''} ({remote or 'local only'})"
    if not shared_refs:
        label += f" [refs reported under {short(first)}]"
    if clean:
        return [Row(category, label, None, True, "reproducible", "Clean and pushed: re-clone from origin.")]
    return [Row(category, label + " - " + "; ".join(bits), du_kb(repo, 60) if not is_worktree else None, False, "keep",
                "Push branches / commit or stash-to-branch, then re-clone; a remote-less repo needs a private GitHub repo or `git bundle` copy.")]


# ------------------------------------------------------------------ app settings

def audit_app_support(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    base = HOME / "Library" / "Application Support"
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if p.name.startswith(".") or p.name.startswith("com.apple."):
                continue
            kb = du_kb(p, 30)
            rows.append(Row("app-support", short(p), kb, False, "secret" if SECRET_NAME.search(p.name) else "keep",
                            "App state: prefer the app's own sync/export; otherwise copy the folder (check size first)."))
    prefs = HOME / "Library" / "Preferences"
    if prefs.is_dir():
        mine = [p for p in prefs.glob("*.plist") if not p.name.startswith(("com.apple.", "loginwindow", ".GlobalPreferences"))]
        rows.append(Row("macos-defaults", f"{short(prefs)} ({len(mine)} third-party plists)", du_kb(prefs, 30), False, "keep",
                        "No `defaults write` script exists in IaC. Capture the few settings that matter in config/macos/defaults.sh."))
    rows.append(Row("macos-defaults", "system defaults (Dock, Finder, keyboard, trackpad)", None, False, "keep",
                    "Add a config/macos/defaults.sh of `defaults write` lines; Apple Migration Assistant is the fallback."))
    return rows


# ------------------------------------------------------------------- big data

def audit_bulk(idx: IacIndex) -> list[Row]:
    rows: list[Row] = []
    for p, how in (
        (HOME / ".ollama", "Model cache: re-pull models (`ollama pull`)."),
        (HOME / ".cache" / "huggingface", "Model cache: re-download."),
        (HOME / "workspace" / "cache", "Cache: regenerable."),
        (HOME / "workspace" / "data", "Data: check for unique files before moving (>5 GB copy needs Kevin)."),
        (HOME / "workspace" / "distill", "Data: check for unique files before moving (>5 GB copy needs Kevin)."),
        (HOME / "Library" / "Containers", "Sandboxed app data; mostly regenerable or iCloud-synced."),
    ):
        if p.exists():
            unique = "Data:" in how
            rows.append(Row("bulk", short(p), du_kb(p, 120), False, "keep" if unique else "reproducible", how))
    return rows


# ---------------------------------------------------------------------- report

def render(rows: list[Row], roots: list[Path], out: Path) -> str:
    host = socket.gethostname()
    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    yes = sum(r.in_iac for r in rows)
    no = len(rows) - yes
    no_keep = sum((not r.in_iac) and r.klass == "keep" for r in rows)
    no_secret = sum((not r.in_iac) and r.klass == "secret" for r in rows)
    no_repro = sum((not r.in_iac) and r.klass == "reproducible" for r in rows)
    cats: dict[str, list[Row]] = {}
    for r in rows:
        cats.setdefault(r.category, []).append(r)
    lines = [
        "# STUDIO-MIGRATION",
        "",
        f"Read-only audit of `{host}`, generated {now} by `.files/scripts/iac/studio_audit.py`.",
        f"IaC roots searched (tracked files at HEAD): {', '.join('`' + short(r) + '`' for r in roots) or 'none'}.",
        "No secret values are included: secret-bearing paths are listed by path and size only.",
        "",
        "`in IaC = yes` means the item is reproducible from code: a path owned by (symlinked into) an IaC root, "
        "a name referenced by tracked files there, a Brewfile entry, or a git clone that is clean and fully pushed. "
        "`class`: keep = unique state to move or codify; secret = re-auth or carry via BWS; reproducible = no action.",
        "Regenerate: `python3 -I ~/workspace/.files/scripts/iac/studio_audit.py --out STUDIO-MIGRATION.md` (read-only, ~3 min).",
        "",
        "## Counts",
        "",
        f"- Items: **{len(rows)}**",
        f"- In IaC: **{yes}**",
        f"- Not in IaC: **{no}** (keep/move: {no_keep}, secret/re-auth: {no_secret}, reproducible: {no_repro})",
        "",
        "| category | items | in IaC | not in IaC |",
        "|---|---:|---:|---:|",
    ]
    for c, rs in cats.items():
        y = sum(r.in_iac for r in rs)
        lines.append(f"| {c} | {len(rs)} | {y} | {len(rs) - y} |")
    lines += ["", "## Items", ""]
    for c, rs in cats.items():
        lines += [f"### {c}", "", "| item | size | in IaC | class | how to move |", "|---|---:|:---:|---|---|"]
        for r in rs:
            item = r.item.replace("|", "\\|")
            lines.append(f"| `{item}` | {human(r.size_kb) if r.size_kb is not None else ''} | {'yes' if r.in_iac else 'no'} | {r.klass} | {r.how} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="STUDIO-MIGRATION.md")
    ap.add_argument("--iac-root", action="append", default=None,
                    help="IaC repo to search (repeatable). Default: ~/workspace/.files and /workspace/repos/home")
    ap.add_argument("--repo-root", action="append", default=None,
                    help="Where to look for git repos. Default: ~/workspace")
    args = ap.parse_args()
    roots = [Path(os.path.expanduser(r)) for r in (args.iac_root or ["~/workspace/.files", "/workspace/repos/home"])]
    idx = IacIndex(roots)
    repo_roots = [Path(os.path.expanduser(r)) for r in (args.repo_root or ["~/workspace"])]

    rows: list[Row] = []
    rows += audit_brew(idx)
    rows += audit_apps(idx)
    rows += audit_launch_agents(idx)
    rows += audit_dotfiles(idx)
    rows += audit_hermes(idx)
    for repo in find_repos(repo_roots):
        rows += audit_repo(repo, idx)
    rows += audit_app_support(idx)
    rows += audit_bulk(idx)

    out = Path(args.out)
    out.write_text(render(rows, idx.roots, out))
    yes = sum(r.in_iac for r in rows)
    print(f"wrote {out} items={len(rows)} in_iac={yes} not_in_iac={len(rows) - yes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
