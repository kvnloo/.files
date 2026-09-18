#!/usr/bin/env python3
"""Routine Suggestion Miner + shortcut compiler for workspace-copilot.

Reuses the existing suggestions / decide / apply / undo substrate.
Does not invent a second automation framework.

P3a: semantic action_source (keyboard|mouse|voice|flow|agent|unknown)
P3b: mine 1–4 step sequences from context_episodes
P3c: install reversible hypr/tmux binds after explicit accept+apply
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

ACTION_SOURCES = frozenset(
    {"keyboard", "mouse", "voice", "flow", "agent", "unknown"}
)

# Only these compile into OS shortcuts (ladder rungs 1–4).
REVERSIBLE_FAMILIES = frozenset(
    {
        "switch_app",
        "switch_workspace",
        "switch_pane",
        "resume_previous",
        "open_context",
        "focus_app",
        "focus_workspace",
        "select_tmux_pane",
    }
)

# Families that start computation / side effects — never auto-install.
EXPLICIT_ONLY_FAMILIES = frozenset(
    {"run_test", "delegate", "harness", "task"}
)

MIN_SUPPORT = 5
MIN_SESSIONS = 2          # independent day-buckets as session proxy (raise to 3 when denser)
MIN_SAME_RATIO = 0.75
MAX_NGRAM = 4
GAP_S = 45.0              # max gap between steps in a sequence chain
LOOKBACK_DAYS = 21
SUGGEST_KIND = "routine-shortcut"
SCHEMA_CANDIDATE = "os.routine_candidate.v0"
FLOW_BINDS_NAME = "flow-routines.conf"


def _now() -> float:
    return time.time()


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _state_dir() -> Path:
    override = os.environ.get("WORKSPACE_COPILOT_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "workspace-copilot"


def flow_binds_path() -> Path:
    # Live hypr can source this; also re-applied via hyprctl on install.
    cfg = Path.home() / ".config" / "hypr" / FLOW_BINDS_NAME
    return cfg


def ensure_routine_schema(db: Any) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_actions (
            id INTEGER PRIMARY KEY,
            ts REAL NOT NULL,
            action_family TEXT NOT NULL,
            action_target TEXT NOT NULL DEFAULT '',
            action_source TEXT NOT NULL DEFAULT 'unknown',
            context_id TEXT NOT NULL DEFAULT '',
            project TEXT NOT NULL DEFAULT '',
            episode_id INTEGER,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS semantic_actions_ts ON semantic_actions(ts);
        CREATE INDEX IF NOT EXISTS semantic_actions_src ON semantic_actions(action_source, ts);

        CREATE TABLE IF NOT EXISTS routine_candidates (
            fingerprint TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            ngram_n INTEGER NOT NULL,
            sequence_json TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT '',
            support INTEGER NOT NULL,
            sessions INTEGER NOT NULL,
            same_ratio REAL NOT NULL,
            median_duration_ms REAL,
            source_mix_json TEXT NOT NULL DEFAULT '{}',
            existing_shortcut TEXT NOT NULL DEFAULT '',
            reversible INTEGER NOT NULL DEFAULT 1,
            automation_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'candidate',
            evidence_json TEXT NOT NULL,
            proposal_json TEXT NOT NULL,
            suggestion_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS routine_candidates_score
            ON routine_candidates(automation_score DESC, updated_at DESC);
        """
    )
    cols = {row[1] for row in db.execute("PRAGMA table_info(context_episodes)")}
    if "action_source" not in cols:
        db.execute(
            "ALTER TABLE context_episodes ADD COLUMN action_source TEXT NOT NULL DEFAULT 'unknown'"
        )


def normalize_source(source: str | None) -> str:
    s = (source or "unknown").strip().lower()
    return s if s in ACTION_SOURCES else "unknown"


def token_of(family: str, target: str) -> str:
    fam = (family or "").strip()
    tgt = re.sub(r"\s+", "", (target or "").strip())[:64]
    # Collapse pane ids that are unstable hashes into role-ish labels when possible
    if fam in {"switch_pane", "select_tmux_pane"} and tgt.startswith("%"):
        tgt = "pane"
    if fam in {"switch_pane", "select_tmux_pane"} and ":" in tgt:
        # keep last segment only
        tgt = tgt.rsplit(":", 1)[-1][:32]
    return f"{fam}:{tgt}"


def parse_token(token: str) -> tuple[str, str]:
    if ":" not in token:
        return token, ""
    fam, tgt = token.split(":", 1)
    return fam, tgt


def record_semantic_action(
    db: Any,
    *,
    family: str,
    target: str = "",
    source: str = "unknown",
    context_id: str = "",
    project: str = "",
    episode_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """P3a: semantic action with modality source — never raw keys."""
    src = normalize_source(source)
    fam = (family or "").strip()[:64]
    tgt = (target or "").strip()[:96]
    stamp = _now()
    cur = db.execute(
        """INSERT INTO semantic_actions(
               ts, action_family, action_target, action_source,
               context_id, project, episode_id, details_json
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            stamp,
            fam,
            tgt,
            src,
            context_id or "",
            project or "",
            episode_id,
            _json(details or {}),
        ),
    )
    return {
        "id": int(cur.lastrowid),
        "ts": stamp,
        "family": fam,
        "target": tgt,
        "source": src,
        "token": token_of(fam, tgt),
    }


def tag_episode_source(db: Any, episode_id: int, source: str) -> None:
    db.execute(
        "UPDATE context_episodes SET action_source=? WHERE id=?",
        (normalize_source(source), episode_id),
    )


def _day_bucket(ts: float) -> str:
    """Independent-session proxy: 4-hour buckets (not calendar day)."""
    lt = time.localtime(ts)
    block = lt.tm_hour // 4
    return time.strftime(f"%Y-%m-%d-b{block}", lt)


def _existing_shortcut(db: Any, sequence: list[str]) -> str | None:
    """Return catalog chord if a single-step sequence already has a keybind."""
    if len(sequence) != 1:
        return None
    fam, tgt = parse_token(sequence[0])
    # Map semantic families onto catalog action patterns.
    patterns: list[str] = []
    if fam in {"switch_workspace", "focus_workspace"} and tgt:
        patterns += [f"workspace:{tgt}", f"workspace {tgt}"]
    if fam in {"switch_app", "focus_app"} and tgt:
        # class-focus binds are rare; match exec:app or focuswindow patterns loosely
        patterns += [f"exec:{tgt}", f"focuswindow:{tgt}"]
    if not patterns:
        return None
    for pat in patterns:
        row = db.execute(
            """SELECT chord, action FROM keybind_catalog
               WHERE action=? OR action LIKE ? LIMIT 1""",
            (pat, f"%{tgt}%"),
        ).fetchone()
        if row:
            return f"{row['chord']} → {row['action']}"
    return None


def _source_friction(mix: dict[str, int]) -> float:
    """Higher friction → better automation candidate.

    keyboard-dominated short actions → low value
    unknown/mouse multi-step → high value
    flow-dominated → already automated
    """
    total = sum(mix.values()) or 1
    kb = mix.get("keyboard", 0) / total
    flow = mix.get("flow", 0) / total
    mouse = mix.get("mouse", 0) / total
    unk = mix.get("unknown", 0) / total
    voice = mix.get("voice", 0) / total
    # keyboard-optimal → suppress
    if kb >= 0.8:
        return 0.15
    if flow >= 0.7:
        return 0.25
    return 0.35 * unk + 0.45 * mouse + 0.5 * voice + 0.2 * (1.0 - kb) + 0.1


def _automation_score(
    *,
    support: int,
    sessions: int,
    same_ratio: float,
    n: int,
    median_ms: float | None,
    source_mix: dict[str, int],
    has_shortcut: bool,
    reversible: bool,
) -> float:
    if not reversible or has_shortcut:
        return 0.0
    if support < MIN_SUPPORT or sessions < MIN_SESSIONS or same_ratio < MIN_SAME_RATIO:
        return 0.0
    repeat = min(1.0, support / 30.0)
    sess = min(1.0, sessions / 8.0)
    consistency = same_ratio
    complexity = min(1.0, (n - 1) / 3.0) * 0.6 + min(1.0, (median_ms or 0) / 5000.0) * 0.4
    friction = _source_friction(source_mix)
    return round(
        100.0
        * (
            0.25 * repeat
            + 0.20 * sess
            + 0.20 * consistency
            + 0.20 * complexity
            + 0.15 * friction
        ),
        2,
    )


def _chain_episodes(rows: list[Any]) -> list[list[dict[str, Any]]]:
    """Split closed episodes into contiguous chains by time gap + project."""
    chains: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    prev_ts = 0.0
    prev_proj = ""
    for row in rows:
        ts = float(row["ts_after"] or row["ts_before"] or 0.0)
        try:
            before = json.loads(row["state_before_json"] or "{}")
        except json.JSONDecodeError:
            before = {}
        proj = str(before.get("project") or "")
        item = {
            "id": row["id"],
            "ts": ts,
            "family": row["action_family"] or "",
            "target": row["action_target"] or "",
            "source": (row["action_source"] if "action_source" in row.keys() else "unknown")
            or "unknown",
            "project": proj,
            "token": token_of(row["action_family"] or "", row["action_target"] or ""),
            "horizon_ms": float(row["horizon_ms"] or 0.0),
            "day": _day_bucket(ts),
        }
        if item["family"] in {"", "stay", "noop"}:
            continue
        if cur and (ts - prev_ts > GAP_S or (proj and prev_proj and proj != prev_proj)):
            chains.append(cur)
            cur = []
        cur.append(item)
        prev_ts = ts
        prev_proj = proj or prev_proj
    if cur:
        chains.append(cur)
    return chains


def mine_routine_candidates(
    db: Any,
    *,
    lookback_days: float = LOOKBACK_DAYS,
    min_support: int = MIN_SUPPORT,
    min_sessions: int = MIN_SESSIONS,
) -> list[dict[str, Any]]:
    """Mine 1–4 gram semantic sequences. Observed facts only — no fake seconds saved."""
    ensure_routine_schema(db)
    cutoff = _now() - lookback_days * 86400.0
    rows = db.execute(
        """SELECT id, ts_before, ts_after, action_family, action_target,
                  state_before_json, horizon_ms, action_source
           FROM context_episodes
           WHERE closed=1 AND ts_after>=?
           ORDER BY ts_after ASC""",
        (cutoff,),
    ).fetchall()
    chains = _chain_episodes(list(rows))

    # occurrences keyed by (project, tuple sequence)
    occ: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)

    for chain_i, chain in enumerate(chains):
        for n in range(1, min(MAX_NGRAM, len(chain)) + 1):
            for i in range(0, len(chain) - n + 1):
                window = chain[i : i + n]
                seq = tuple(step["token"] for step in window)
                # skip pure stay/noop
                if all(t.startswith(("stay:", "noop:")) for t in seq):
                    continue
                families = [parse_token(t)[0] for t in seq]
                if any(f in EXPLICIT_ONLY_FAMILIES for f in families):
                    continue
                proj = window[0]["project"] or ""
                duration_ms = max(
                    0.0,
                    (window[-1]["ts"] - window[0]["ts"]) * 1000.0,
                )
                # prefer sum of per-step horizons when available
                hz = sum(float(s.get("horizon_ms") or 0.0) for s in window)
                if hz > 0:
                    duration_ms = hz
                occ[(proj, seq)].append(
                    {
                        "day": window[0]["day"],
                        "chain_id": chain_i,
                        "duration_ms": duration_ms,
                        "sources": [s["source"] for s in window],
                        "ids": [s["id"] for s in window],
                    }
                )

    candidates: list[dict[str, Any]] = []
    for (proj, seq), hits in occ.items():
        support = len(hits)
        # Independent bouts: distinct activity chains (falls back to time buckets).
        sessions = len({h.get("chain_id", h["day"]) for h in hits})
        if support < min_support or sessions < min_sessions:
            continue
        # Exact n-gram support is already a pure sequence count.
        # Prefix-completion rate for multi-step: how often the full seq follows the prefix.
        if len(seq) == 1:
            same_ratio = 1.0
            same_family_hits = support
        else:
            prefix = seq[:-1]
            prefix_hits = sum(
                len(hs)
                for (p2, s2), hs in occ.items()
                if p2 == proj and len(s2) >= len(prefix) and s2[: len(prefix)] == prefix
            )
            # Count times this exact full sequence ran vs any continuation of prefix
            same_family_hits = max(support, prefix_hits)
            same_ratio = support / max(1, same_family_hits)
        durations = [h["duration_ms"] for h in hits if h["duration_ms"] > 0]
        median_ms = float(statistics.median(durations)) if durations else None
        mix: Counter[str] = Counter()
        for h in hits:
            for s in h["sources"]:
                mix[normalize_source(s)] += 1
        sequence = list(seq)
        reversible = all(parse_token(t)[0] in REVERSIBLE_FAMILIES for t in sequence)
        existing = _existing_shortcut(db, sequence) if len(sequence) == 1 else None
        # Multi-step never collides with single chord equivalent the same way
        score = _automation_score(
            support=support,
            sessions=sessions,
            same_ratio=same_ratio,
            n=len(sequence),
            median_ms=median_ms,
            source_mix=dict(mix),
            has_shortcut=bool(existing),
            reversible=reversible,
        )
        if score <= 0:
            continue
        fingerprint = hashlib.sha256(
            f"{proj}|{'|'.join(sequence)}".encode()
        ).hexdigest()[:24]
        chord = propose_chord(db, sequence)
        steps = [_step_dispatch(t) for t in sequence]
        evidence = {
            "observed_n": support,
            "sessions_n": sessions,
            "session_proxy": "activity_chain",
            "median_sequence_duration_ms": None if median_ms is None else round(median_ms, 1),
            "same_action_sequence": f"{support}/{same_family_hits}",
            "same_ratio": round(same_ratio, 4),
            "existing_equivalent_shortcut": existing or "none",
            "all_actions_reversible": reversible,
            "source_mix": dict(mix),
            "project": proj or "(any)",
            "sequence": sequence,
            "lookback_days": lookback_days,
            "automation_score": score,
        }
        proposal = {
            "action": "install_flow_bind",
            "kind": SUGGEST_KIND,
            "fingerprint": fingerprint,
            "chord": chord,
            "bind_source": "hypr",
            "steps": steps,
            "sequence": sequence,
            "label": _label_for(sequence),
            "dispatcher": f"exec, workspace-copilot run-routine {fingerprint}",
        }
        cand = {
            "schema": SCHEMA_CANDIDATE,
            "fingerprint": fingerprint,
            "ngram_n": len(sequence),
            "sequence": sequence,
            "project": proj,
            "support": support,
            "sessions": sessions,
            "same_ratio": round(same_ratio, 4),
            "median_duration_ms": None if median_ms is None else round(median_ms, 1),
            "source_mix": dict(mix),
            "existing_shortcut": existing or "",
            "reversible": reversible,
            "automation_score": score,
            "evidence": evidence,
            "proposal": proposal,
            "status": "candidate",
        }
        candidates.append(cand)

    candidates.sort(key=lambda c: (-c["automation_score"], -c["support"], c["fingerprint"]))
    return candidates


def _label_for(sequence: list[str]) -> str:
    if len(sequence) == 1:
        fam, tgt = parse_token(sequence[0])
        if fam in {"switch_app", "focus_app"}:
            return f"Focus {tgt}"
        if fam in {"switch_workspace", "focus_workspace"}:
            return f"Workspace {tgt}"
        if fam in {"switch_pane", "select_tmux_pane"}:
            return f"Select pane {tgt}"
        if fam == "resume_previous":
            return "Resume previous context"
        return f"{fam} {tgt}".strip()
    if len(sequence) == 2:
        a = parse_token(sequence[0])[1] or parse_token(sequence[0])[0]
        b = parse_token(sequence[1])[1] or parse_token(sequence[1])[0]
        return f"{a} → {b}"
    return " → ".join(
        (parse_token(t)[1] or parse_token(t)[0]) for t in sequence
    )


def _step_dispatch(token: str) -> dict[str, Any]:
    fam, tgt = parse_token(token)
    if fam in {"switch_app", "focus_app", "open_context"}:
        return {"action": "focus_app", "app": tgt}
    if fam in {"switch_workspace", "focus_workspace"}:
        return {"action": "focus_workspace", "workspace": tgt}
    if fam in {"switch_pane", "select_tmux_pane"}:
        return {"action": "select_tmux_pane", "pane_id": tgt}
    if fam == "resume_previous":
        return {"action": "resume_previous"}
    return {"action": "noop", "token": token}


def propose_chord(db: Any, sequence: list[str]) -> dict[str, str]:
    """Pick a free Super+Alt+letter chord; collision-check catalog."""
    taken = {
        row["chord"].upper().replace(" ", "")
        for row in db.execute("SELECT chord FROM keybind_catalog WHERE source='hypr'")
    }
    # Also taken by already-installed flow binds
    for row in db.execute(
        "SELECT proposal_json FROM routine_candidates WHERE status IN ('installed','accepted')"
    ):
        try:
            prop = json.loads(row["proposal_json"] or "{}")
        except json.JSONDecodeError:
            continue
        ch = prop.get("chord") or {}
        key = f"{ch.get('mods','')}+{ch.get('key','')}".upper().replace(" ", "")
        if key.strip("+"):
            taken.add(key)

    # mnemonic from first target letter
    letters = []
    for t in sequence:
        _, tgt = parse_token(t)
        if tgt and tgt[0].isalpha():
            letters.append(tgt[0].upper())
    letters += list("RABCDEFGHJKLMNPQSTUVWXYZ")
    mods = "SUPER_ALT"
    for letter in letters:
        cand = f"{mods}+{letter}"
        # catalog stores various forms
        collisions = [
            cand,
            f"SUPER+ALT+{letter}",
            f"ALT+SUPER+{letter}",
            f"$mod ALT+{letter}",
        ]
        if any(c.upper().replace(" ", "") in taken or c in taken for c in collisions):
            continue
        # check substring in catalog chords
        hit = db.execute(
            """SELECT chord FROM keybind_catalog
               WHERE upper(replace(chord,' ','')) LIKE ? LIMIT 1""",
            (f"%ALT+{letter}%",),
        ).fetchone()
        if hit and "SUPER" in hit["chord"].upper():
            continue
        return {"mods": "SUPER ALT", "key": letter, "hypr": f"SUPER_ALT,{letter}"}
    return {"mods": "SUPER ALT SHIFT", "key": "R", "hypr": "SUPER_ALT_SHIFT,R"}


def persist_candidates(db: Any, candidates: list[dict[str, Any]]) -> int:
    """Upsert mined candidates into routine_candidates table."""
    ensure_routine_schema(db)
    n = 0
    stamp = _now()
    for c in candidates:
        fp = c["fingerprint"]
        existing = db.execute(
            "SELECT status FROM routine_candidates WHERE fingerprint=?", (fp,)
        ).fetchone()
        if existing and existing["status"] in {"installed", "rejected", "dismissed"}:
            continue
        db.execute(
            """INSERT INTO routine_candidates(
                   fingerprint, created_at, updated_at, ngram_n, sequence_json, project,
                   support, sessions, same_ratio, median_duration_ms, source_mix_json,
                   existing_shortcut, reversible, automation_score, status,
                   evidence_json, proposal_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                   updated_at=excluded.updated_at,
                   support=excluded.support,
                   sessions=excluded.sessions,
                   same_ratio=excluded.same_ratio,
                   median_duration_ms=excluded.median_duration_ms,
                   source_mix_json=excluded.source_mix_json,
                   automation_score=excluded.automation_score,
                   evidence_json=excluded.evidence_json,
                   proposal_json=excluded.proposal_json
                   WHERE routine_candidates.status='candidate'
            """,
            (
                fp,
                stamp,
                stamp,
                c["ngram_n"],
                _json(c["sequence"]),
                c.get("project") or "",
                c["support"],
                c["sessions"],
                c["same_ratio"],
                c.get("median_duration_ms"),
                _json(c.get("source_mix") or {}),
                c.get("existing_shortcut") or "",
                1 if c.get("reversible") else 0,
                c["automation_score"],
                "candidate",
                _json(c["evidence"]),
                _json(c["proposal"]),
            ),
        )
        n += 1
    return n


def export_candidates_jsonl(db: Any, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", encoding="utf-8") as fh:
        for row in db.execute(
            """SELECT * FROM routine_candidates
               ORDER BY automation_score DESC, support DESC"""
        ):
            rec = {
                "schema": SCHEMA_CANDIDATE,
                "fingerprint": row["fingerprint"],
                "ngram_n": row["ngram_n"],
                "sequence": json.loads(row["sequence_json"]),
                "project": row["project"],
                "support": row["support"],
                "sessions": row["sessions"],
                "same_ratio": row["same_ratio"],
                "median_duration_ms": row["median_duration_ms"],
                "source_mix": json.loads(row["source_mix_json"] or "{}"),
                "existing_shortcut": row["existing_shortcut"],
                "reversible": bool(row["reversible"]),
                "automation_score": row["automation_score"],
                "status": row["status"],
                "evidence": json.loads(row["evidence_json"] or "{}"),
                "proposal": json.loads(row["proposal_json"] or "{}"),
                "suggestion_id": row["suggestion_id"],
            }
            fh.write(_json(rec) + "\n")
            n += 1
    return {"path": str(dest), "n": n, "schema": SCHEMA_CANDIDATE}


def suggest_routines(
    db: Any,
    *,
    upsert_suggestion: Callable[..., bool],
    limit: int = 8,
) -> int:
    """Turn top candidates into pending suggestions (Create / Dismiss via decide)."""
    candidates = mine_routine_candidates(db)
    persist_candidates(db, candidates)
    created = 0
    for c in candidates[:limit]:
        if c["automation_score"] < 12:
            continue
        ev = c["evidence"]
        chord = c["proposal"]["chord"]
        chord_s = f"{chord.get('mods','')}+{chord.get('key','')}".replace("SUPER ", "Super+")
        summary = f"Create shortcut “{c['proposal']['label']}” ({chord_s})"
        rationale = (
            f"Observed {ev['observed_n']} times across {ev['sessions_n']} sessions. "
            f"Median sequence duration: {ev['median_sequence_duration_ms']} ms. "
            f"Same action sequence: {ev['same_action_sequence']}. "
            f"Existing equivalent shortcut: {ev['existing_equivalent_shortcut']}. "
            f"All actions reversible: {'yes' if ev['all_actions_reversible'] else 'no'}."
        )
        new = upsert_suggestion(
            db,
            SUGGEST_KIND,
            c["fingerprint"],
            summary,
            rationale,
            ev,
            c["proposal"],
        )
        if new:
            created += 1
        # Link suggestion id regardless of insert/update
        sid = db.execute(
            """SELECT id FROM suggestions WHERE kind=? AND status='pending'
               AND proposal_json LIKE ? ORDER BY id DESC LIMIT 1""",
            (SUGGEST_KIND, f'%{c["fingerprint"]}%'),
        ).fetchone()
        if sid:
            db.execute(
                "UPDATE routine_candidates SET suggestion_id=? WHERE fingerprint=?",
                (sid["id"], c["fingerprint"]),
            )
    return created


def suggestion_fingerprint_compat(kind: str, identity: str) -> str:
    return hashlib.sha256(f"{kind}:{identity}".encode()).hexdigest()


def run_routine(
    db: Any,
    fingerprint: str,
    *,
    run_fn: Callable[[list[str]], Any],
    tmux_args_fn: Callable[..., list[str]],
) -> dict[str, Any]:
    """Execute allowlisted routine steps. Logs source=keyboard (binding invoked)."""
    row = db.execute(
        "SELECT proposal_json, sequence_json FROM routine_candidates WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    if not row:
        return {"ok": False, "error": f"unknown routine {fingerprint}"}
    try:
        proposal = json.loads(row["proposal_json"] or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad proposal"}
    steps = proposal.get("steps") or []
    results = []
    for step in steps:
        action = step.get("action")
        if action == "focus_workspace":
            ws = str(step.get("workspace") or "")
            if not ws:
                return {"ok": False, "error": "missing workspace", "done": results}
            r = run_fn(["hyprctl", "dispatch", "workspace", ws])
            if getattr(r, "returncode", 1) != 0:
                return {"ok": False, "error": "hyprctl workspace failed", "done": results}
            results.append(f"workspace {ws}")
            record_semantic_action(
                db, family="switch_workspace", target=ws, source="keyboard",
                details={"via": "run-routine", "fingerprint": fingerprint},
            )
        elif action == "focus_app":
            app = str(step.get("app") or "")
            if not app:
                return {"ok": False, "error": "missing app", "done": results}
            r = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:^{re.escape(app)}$"])
            if getattr(r, "returncode", 1) != 0:
                # soft: try without anchors
                r = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:{app}"])
            if getattr(r, "returncode", 1) != 0:
                return {"ok": False, "error": f"focuswindow {app} failed", "done": results}
            results.append(f"app {app}")
            record_semantic_action(
                db, family="switch_app", target=app, source="keyboard",
                details={"via": "run-routine", "fingerprint": fingerprint},
            )
        elif action == "select_tmux_pane":
            pane = str(step.get("pane_id") or "")
            if not pane or pane == "pane":
                return {"ok": False, "error": "pane id unstable/missing", "done": results}
            r = run_fn(tmux_args_fn("select-pane", "-t", pane))
            if getattr(r, "returncode", 1) != 0:
                return {"ok": False, "error": "tmux select-pane failed", "done": results}
            results.append(f"pane {pane}")
            record_semantic_action(
                db, family="switch_pane", target=pane, source="keyboard",
                details={"via": "run-routine", "fingerprint": fingerprint},
            )
        elif action == "resume_previous":
            # Use last closed episode's previous context app
            prev = db.execute(
                """SELECT state_before_json FROM context_episodes
                   WHERE closed=1 ORDER BY id DESC LIMIT 1"""
            ).fetchone()
            if not prev:
                return {"ok": False, "error": "no previous context", "done": results}
            try:
                st = json.loads(prev["state_before_json"])
            except json.JSONDecodeError:
                st = {}
            app = st.get("app") or ""
            if app:
                run_fn(["hyprctl", "dispatch", "focuswindow", f"class:^{re.escape(app)}$"])
                results.append(f"resume {app}")
                record_semantic_action(
                    db, family="resume_previous", target=app, source="keyboard",
                    details={"via": "run-routine", "fingerprint": fingerprint},
                )
        else:
            return {"ok": False, "error": f"step not allowlisted: {action}", "done": results}
    return {"ok": True, "fingerprint": fingerprint, "results": results, "source": "keyboard"}


def _hypr_bind_line(chord_hypr: str, fingerprint: str) -> str:
    # chord_hypr like "SUPER_ALT,R"
    return (
        f"bind = {chord_hypr.replace(',', ', ')}, exec, "
        f"workspace-copilot run-routine {fingerprint}"
    )


def install_flow_bind(
    db: Any,
    *,
    proposal: dict[str, Any],
    run_fn: Callable[[list[str]], Any],
) -> dict[str, Any]:
    """P3c: install hypr bind after accept. Collision-checked. Undo removes exactly this bind."""
    ensure_routine_schema(db)
    fp = proposal.get("fingerprint") or ""
    chord = proposal.get("chord") or {}
    hypr_chord = chord.get("hypr") or ""
    if not fp or not hypr_chord:
        return {"ok": False, "error": "missing fingerprint/chord"}

    # Collision check against live catalog
    key = chord.get("key") or ""
    hit = db.execute(
        """SELECT chord, action FROM keybind_catalog
           WHERE source='hypr' AND (
               upper(chord) LIKE ? OR upper(chord) LIKE ?
           ) LIMIT 1""",
        (f"%ALT+{key}%", f"%{hypr_chord.upper()}%"),
    ).fetchone()
    if hit:
        # allow if it's already our bind
        if fp not in (hit["action"] or ""):
            return {
                "ok": False,
                "error": f"chord collision with {hit['chord']} → {hit['action']}",
            }

    line = _hypr_bind_line(hypr_chord, fp)
    path = flow_binds_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = f"# flow-routine:{fp}"
    if marker not in existing:
        block = f"{marker}\n{line}\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(block)

    # Live bind via hyprctl (mods,key,dispatcher,arg)
    # hyprctl keyword bind "SUPER_ALT,R,exec,workspace-copilot run-routine fp"
    mods_key = hypr_chord  # SUPER_ALT,R
    bind_arg = f"{mods_key},exec,workspace-copilot run-routine {fp}"
    result = run_fn(["hyprctl", "keyword", "bind", bind_arg])
    live_ok = getattr(result, "returncode", 1) == 0

    db.execute(
        """UPDATE routine_candidates SET status='installed', updated_at=?
           WHERE fingerprint=?""",
        (_now(), fp),
    )
    # Register in catalog so future collision checks see it
    chord_display = f"{chord.get('mods','')}+{chord.get('key','')}".strip("+")
    db.execute(
        """INSERT INTO keybind_catalog(source,chord,action,first_seen,last_seen)
           VALUES(?,?,?,?,?)
           ON CONFLICT(source,chord,action) DO UPDATE SET last_seen=excluded.last_seen""",
        ("hypr-flow", chord_display, f"run-routine:{fp}", _now(), _now()),
    )
    return {
        "ok": True,
        "fingerprint": fp,
        "bind_line": line,
        "path": str(path),
        "live_bind": live_ok,
        "chord": chord,
        "label": proposal.get("label"),
        "undo": {"action": "uninstall_flow_bind", "fingerprint": fp, "hypr_chord": hypr_chord},
    }


def uninstall_flow_bind(
    db: Any,
    *,
    fingerprint: str,
    hypr_chord: str,
    run_fn: Callable[[list[str]], Any],
) -> dict[str, Any]:
    path = flow_binds_path()
    if path.exists():
        text = path.read_text(encoding="utf-8")
        marker = f"# flow-routine:{fingerprint}"
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        skip = 0
        for i, line in enumerate(lines):
            if skip:
                skip -= 1
                continue
            if line.startswith(marker):
                # drop marker + next bind line
                skip = 1
                continue
            if fingerprint in line and line.strip().startswith("bind"):
                continue
            out.append(line)
        path.write_text("".join(out), encoding="utf-8")

    # hyprctl unbind MODS,key
    if hypr_chord:
        run_fn(["hyprctl", "keyword", "unbind", hypr_chord.replace(",", ", ")])
        # try without space too
        run_fn(["hyprctl", "keyword", "unbind", hypr_chord])

    db.execute(
        """UPDATE routine_candidates SET status='candidate', updated_at=?
           WHERE fingerprint=?""",
        (_now(), fingerprint),
    )
    db.execute(
        "DELETE FROM keybind_catalog WHERE source='hypr-flow' AND action=?",
        (f"run-routine:{fingerprint}",),
    )
    return {"ok": True, "fingerprint": fingerprint, "removed": True}


def routine_stats(db: Any) -> dict[str, Any]:
    ensure_routine_schema(db)
    rows = [
        dict(r)
        for r in db.execute(
            """SELECT status, COUNT(*) AS n FROM routine_candidates GROUP BY status"""
        )
    ]
    top = [
        {
            "fingerprint": r["fingerprint"],
            "score": r["automation_score"],
            "support": r["support"],
            "sessions": r["sessions"],
            "sequence": json.loads(r["sequence_json"]),
            "status": r["status"],
            "label": (json.loads(r["proposal_json"] or "{}") or {}).get("label"),
        }
        for r in db.execute(
            """SELECT fingerprint, automation_score, support, sessions,
                      sequence_json, status, proposal_json
               FROM routine_candidates
               ORDER BY automation_score DESC LIMIT 10"""
        )
    ]
    sources = [
        dict(r)
        for r in db.execute(
            """SELECT action_source AS source, COUNT(*) AS n
               FROM semantic_actions GROUP BY action_source ORDER BY n DESC"""
        )
    ]
    return {
        "schema": SCHEMA_CANDIDATE,
        "by_status": rows,
        "top": top,
        "semantic_action_sources": sources,
        "binds_path": str(flow_binds_path()),
        "gates": {
            "min_support": MIN_SUPPORT,
            "min_sessions": MIN_SESSIONS,
            "min_same_ratio": MIN_SAME_RATIO,
            "max_ngram": MAX_NGRAM,
        },
    }
