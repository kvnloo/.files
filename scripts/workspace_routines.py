#!/usr/bin/env python3
"""Routine Suggestion Miner + shortcut compiler for workspace-copilot.

Reuses the existing suggestions / decide / apply / undo substrate.
Does not invent a second automation framework.

P3a: semantic action_source (keyboard|mouse|voice|flow|agent|unknown)
P3b: mine 1–4 step sequences from context_episodes
P3c: install reversible hypr/tmux binds after explicit accept+apply
P3d: automation utility receipts (suggested→…→invoked→completed / unused)
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
SCHEMA_UTILITY = "os.automation_utility.v0"
SCHEMA_RECEIPT = "os.automation_receipt.v0"
UNUSED_AFTER_OPPORTUNITIES = 12
MANUAL_MATCH_WINDOW_S = 90.0
REVERSAL_WINDOW_S = 8.0
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
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS automation_receipts (
            id INTEGER PRIMARY KEY,
            ts REAL NOT NULL,
            fingerprint TEXT NOT NULL,
            phase TEXT NOT NULL,
            suggestion_id INTEGER,
            ok INTEGER,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS automation_receipts_fp_ts
            ON automation_receipts(fingerprint, ts DESC);
        CREATE INDEX IF NOT EXISTS automation_receipts_phase
            ON automation_receipts(phase, ts DESC);

        CREATE TABLE IF NOT EXISTS automation_utility (
            fingerprint TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            suggested_at REAL,
            accepted_at REAL,
            rejected_at REAL,
            installed_at REAL,
            uninstalled_at REAL,
            last_invoked_at REAL,
            last_completed_at REAL,
            last_failed_at REAL,
            last_manual_at REAL,
            last_opportunity_at REAL,
            n_suggested INTEGER NOT NULL DEFAULT 0,
            n_accepted INTEGER NOT NULL DEFAULT 0,
            n_rejected INTEGER NOT NULL DEFAULT 0,
            n_installed INTEGER NOT NULL DEFAULT 0,
            n_uninstalled INTEGER NOT NULL DEFAULT 0,
            n_invoked INTEGER NOT NULL DEFAULT 0,
            n_completed INTEGER NOT NULL DEFAULT 0,
            n_failed INTEGER NOT NULL DEFAULT 0,
            n_manual_equivalent INTEGER NOT NULL DEFAULT 0,
            n_opportunities INTEGER NOT NULL DEFAULT 0,
            n_immediate_reversal INTEGER NOT NULL DEFAULT 0,
            unused_after_n INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'none',
            notes_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS automation_utility_status
            ON automation_utility(status, updated_at DESC);
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



def _ensure_utility_row(db: Any, fingerprint: str) -> None:
    ensure_routine_schema(db)
    fp = (fingerprint or "").strip()
    if not fp:
        return
    row = db.execute(
        "SELECT fingerprint FROM automation_utility WHERE fingerprint=?", (fp,)
    ).fetchone()
    if row:
        return
    stamp = _now()
    db.execute(
        """INSERT INTO automation_utility(fingerprint, created_at, updated_at, status)
           VALUES (?,?,?,?)""",
        (fp, stamp, stamp, "none"),
    )


def note_automation_receipt(
    db: Any,
    *,
    fingerprint: str,
    phase: str,
    suggestion_id: int | None = None,
    ok: bool | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """P3d: append one lifecycle receipt and update utility rollup.

    Phases: suggested|accepted|rejected|installed|uninstalled|
            invoked|completed|failed|manual_equivalent|opportunity|immediate_reversal
    Observed facts only — no invented seconds-saved.
    """
    ensure_routine_schema(db)
    fp = (fingerprint or "").strip()
    if not fp:
        return {"ok": False, "error": "missing fingerprint"}
    phase = (phase or "").strip().lower()
    allowed = {
        "suggested",
        "accepted",
        "rejected",
        "installed",
        "uninstalled",
        "invoked",
        "completed",
        "failed",
        "manual_equivalent",
        "opportunity",
        "immediate_reversal",
    }
    if phase not in allowed:
        return {"ok": False, "error": f"bad phase {phase}"}
    stamp = _now()
    _ensure_utility_row(db, fp)
    cur = db.execute(
        """INSERT INTO automation_receipts(
               ts, fingerprint, phase, suggestion_id, ok, details_json
           ) VALUES (?,?,?,?,?,?)""",
        (
            stamp,
            fp,
            phase,
            suggestion_id,
            None if ok is None else (1 if ok else 0),
            _json(details or {}),
        ),
    )
    receipt_id = int(cur.lastrowid)

    # Counter + timestamp map
    counter_col = {
        "suggested": "n_suggested",
        "accepted": "n_accepted",
        "rejected": "n_rejected",
        "installed": "n_installed",
        "uninstalled": "n_uninstalled",
        "invoked": "n_invoked",
        "completed": "n_completed",
        "failed": "n_failed",
        "manual_equivalent": "n_manual_equivalent",
        "opportunity": "n_opportunities",
        "immediate_reversal": "n_immediate_reversal",
    }[phase]
    ts_col = {
        "suggested": "suggested_at",
        "accepted": "accepted_at",
        "rejected": "rejected_at",
        "installed": "installed_at",
        "uninstalled": "uninstalled_at",
        "invoked": "last_invoked_at",
        "completed": "last_completed_at",
        "failed": "last_failed_at",
        "manual_equivalent": "last_manual_at",
        "opportunity": "last_opportunity_at",
        "immediate_reversal": None,
    }[phase]

    sets = [f"{counter_col}={counter_col}+1", "updated_at=?"]
    params: list[Any] = [stamp]
    if ts_col:
        sets.append(f"{ts_col}=?")
        params.append(stamp)

    # status transitions (observed lifecycle, not marketing)
    if phase == "suggested":
        sets.append("status=CASE WHEN status IN ('installed','earning','unused') THEN status ELSE 'suggested' END")
    elif phase == "accepted":
        sets.append("status=CASE WHEN status='installed' THEN status ELSE 'accepted' END")
    elif phase == "rejected":
        sets.append("status='rejected'")
    elif phase == "installed":
        sets.append("status='installed'")
    elif phase == "uninstalled":
        sets.append("status='uninstalled'")
    elif phase in {"invoked", "completed"}:
        sets.append("status='earning'")
    elif phase == "opportunity":
        # mark unused when enough opportunities and zero invokes
        sets.append(
            f"""unused_after_n=CASE
                  WHEN n_invoked=0 AND (n_opportunities+1)>={UNUSED_AFTER_OPPORTUNITIES}
                  THEN {UNUSED_AFTER_OPPORTUNITIES} ELSE unused_after_n END"""
        )
        sets.append(
            f"""status=CASE
                  WHEN n_invoked=0 AND (n_opportunities+1)>={UNUSED_AFTER_OPPORTUNITIES}
                  THEN 'unused'
                  WHEN status IN ('installed','earning','unused') THEN status
                  ELSE status END"""
        )

    params.append(fp)
    db.execute(
        f"UPDATE automation_utility SET {', '.join(sets)} WHERE fingerprint=?",
        tuple(params),
    )
    return {
        "ok": True,
        "receipt_id": receipt_id,
        "fingerprint": fp,
        "phase": phase,
        "ts": stamp,
        "schema": SCHEMA_RECEIPT,
    }


def note_routine_decision(
    db: Any,
    *,
    suggestion_id: int,
    decision: str,
    kind: str | None = None,
    proposal: dict[str, Any] | None = None,
) -> None:
    """Hook from decide() for routine-shortcut lifecycle."""
    if kind and kind != SUGGEST_KIND:
        return
    fp = ""
    if proposal:
        fp = str(proposal.get("fingerprint") or "")
    if not fp:
        row = db.execute(
            "SELECT kind, proposal_json FROM suggestions WHERE id=?", (suggestion_id,)
        ).fetchone()
        if not row or row["kind"] != SUGGEST_KIND:
            return
        try:
            prop = json.loads(row["proposal_json"] or "{}")
        except json.JSONDecodeError:
            prop = {}
        fp = str(prop.get("fingerprint") or "")
    if not fp:
        return
    phase = "accepted" if decision == "accept" else "rejected"
    note_automation_receipt(
        db, fingerprint=fp, phase=phase, suggestion_id=suggestion_id, ok=True,
        details={"decision": decision},
    )
    if phase == "rejected":
        db.execute(
            "UPDATE routine_candidates SET status='rejected', updated_at=? WHERE fingerprint=?",
            (_now(), fp),
        )


def observe_manual_equivalents(db: Any, *, lookback_s: float = 3600.0) -> dict[str, Any]:
    """When an installed routine's sequence still happens via non-automation path.

    Marks opportunity + manual_equivalent. No keylogging — uses closed episodes /
    semantic_actions already recorded.
    """
    ensure_routine_schema(db)
    stamp = _now()
    installed = list(
        db.execute(
            """SELECT fingerprint, sequence_json
               FROM routine_candidates WHERE status='installed'"""
        )
    )
    if not installed:
        return {"checked": 0, "manual": 0, "opportunities": 0}

    # Recent closed episode tokens ordered by ts
    eps = list(
        db.execute(
            """SELECT id, ts_after AS ts, action_family, action_target, action_source
               FROM context_episodes
               WHERE closed=1 AND ts_after>=?
               ORDER BY ts_after ASC""",
            (stamp - lookback_s,),
        )
    )
    tokens = [
        {
            "id": r["id"],
            "ts": float(r["ts"]),
            "token": token_of(r["action_family"] or "", r["action_target"] or ""),
            "source": r["action_source"] or "unknown",
        }
        for r in eps
    ]

    # Recent automation invokes (to avoid double-counting automation as manual)
    invokes = {
        r["fingerprint"]: float(r["ts"])
        for r in db.execute(
            """SELECT fingerprint, MAX(ts) AS ts FROM automation_receipts
               WHERE phase='invoked' AND ts>=? GROUP BY fingerprint""",
            (stamp - lookback_s,),
        )
    }

    # Last opportunity receipt per fp so we don't spam
    last_opp = {
        r["fingerprint"]: float(r["ts"])
        for r in db.execute(
            """SELECT fingerprint, MAX(ts) AS ts FROM automation_receipts
               WHERE phase IN ('opportunity','manual_equivalent') AND ts>=?
               GROUP BY fingerprint""",
            (stamp - lookback_s,),
        )
    }

    n_manual = 0
    n_opp = 0
    checked = 0
    for row in installed:
        checked += 1
        fp = row["fingerprint"]
        try:
            seq = tuple(json.loads(row["sequence_json"] or "[]"))
        except json.JSONDecodeError:
            continue
        if not seq:
            continue
        n = len(seq)
        # Scan for exact n-gram matches not covered by a nearby invoke
        for i in range(0, len(tokens) - n + 1):
            window = tokens[i : i + n]
            if tuple(w["token"] for w in window) != seq:
                continue
            end_ts = window[-1]["ts"]
            # skip if invoke within window of this match
            inv_ts = invokes.get(fp)
            if inv_ts is not None and abs(inv_ts - end_ts) <= MANUAL_MATCH_WINDOW_S:
                continue
            # skip if all steps already tagged via run-routine keyboard details
            # (source=keyboard alone is not enough — natural binds also keyboard)
            # We treat as manual when no invoke receipt nearby.
            last = last_opp.get(fp, 0.0)
            if end_ts - last < 30.0:
                continue  # debounce
            # opportunity always when installed sequence reappears
            note_automation_receipt(
                db,
                fingerprint=fp,
                phase="opportunity",
                ok=True,
                details={
                    "match_ts": end_ts,
                    "episode_ids": [w["id"] for w in window],
                    "sources": [w["source"] for w in window],
                },
            )
            note_automation_receipt(
                db,
                fingerprint=fp,
                phase="manual_equivalent",
                ok=True,
                details={
                    "match_ts": end_ts,
                    "episode_ids": [w["id"] for w in window],
                    "sources": [w["source"] for w in window],
                },
            )
            last_opp[fp] = end_ts
            n_opp += 1
            n_manual += 1
            break  # one match per fingerprint per call
    return {"checked": checked, "manual": n_manual, "opportunities": n_opp}


def utility_stats(db: Any) -> dict[str, Any]:
    """Observed automation utility — no fake seconds saved."""
    ensure_routine_schema(db)
    rows = []
    for r in db.execute(
        """SELECT u.*, c.sequence_json, c.automation_score, c.status AS candidate_status,
                  c.proposal_json
           FROM automation_utility u
           LEFT JOIN routine_candidates c ON c.fingerprint=u.fingerprint
           ORDER BY u.updated_at DESC LIMIT 50"""
    ):
        d = dict(r)
        seq = []
        label = None
        try:
            seq = json.loads(d.pop("sequence_json", None) or "[]")
        except json.JSONDecodeError:
            seq = []
        try:
            label = (json.loads(d.pop("proposal_json", None) or "{}") or {}).get("label")
        except json.JSONDecodeError:
            label = None
        n_inv = int(d.get("n_invoked") or 0)
        n_opp = int(d.get("n_opportunities") or 0)
        n_man = int(d.get("n_manual_equivalent") or 0)
        n_comp = int(d.get("n_completed") or 0)
        invoke_rate = round(n_inv / n_opp, 4) if n_opp else None
        complete_rate = round(n_comp / n_inv, 4) if n_inv else None
        rows.append(
            {
                "fingerprint": d["fingerprint"],
                "label": label,
                "sequence": seq,
                "status": d["status"],
                "candidate_status": d.get("candidate_status"),
                "automation_score": d.get("automation_score"),
                "n_suggested": d["n_suggested"],
                "n_accepted": d["n_accepted"],
                "n_rejected": d["n_rejected"],
                "n_installed": d["n_installed"],
                "n_uninstalled": d["n_uninstalled"],
                "n_invoked": n_inv,
                "n_completed": n_comp,
                "n_failed": d["n_failed"],
                "n_manual_equivalent": n_man,
                "n_opportunities": n_opp,
                "n_immediate_reversal": d["n_immediate_reversal"],
                "unused_after_n": d["unused_after_n"],
                "invoke_rate_given_opportunity": invoke_rate,
                "complete_rate_given_invoke": complete_rate,
                "suggested_at": d["suggested_at"],
                "accepted_at": d["accepted_at"],
                "installed_at": d["installed_at"],
                "last_invoked_at": d["last_invoked_at"],
                "last_manual_at": d["last_manual_at"],
            }
        )
    phases = [
        dict(r)
        for r in db.execute(
            """SELECT phase, COUNT(*) AS n FROM automation_receipts
               GROUP BY phase ORDER BY n DESC"""
        )
    ]
    unused = [r for r in rows if r["status"] == "unused"]
    earning = [r for r in rows if r["status"] == "earning"]
    return {
        "schema": SCHEMA_UTILITY,
        "receipt_schema": SCHEMA_RECEIPT,
        "gates": {
            "unused_after_opportunities": UNUSED_AFTER_OPPORTUNITIES,
            "manual_match_window_s": MANUAL_MATCH_WINDOW_S,
            "reversal_window_s": REVERSAL_WINDOW_S,
        },
        "phase_counts": phases,
        "n_tracked": len(rows),
        "n_earning": len(earning),
        "n_unused": len(unused),
        "automations": rows,
    }


def export_utility_jsonl(db: Any, dest: Path) -> dict[str, Any]:
    ensure_routine_schema(db)
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", encoding="utf-8") as fh:
        for r in db.execute(
            "SELECT * FROM automation_receipts ORDER BY id ASC"
        ):
            rec = {
                "schema": SCHEMA_RECEIPT,
                "id": r["id"],
                "ts": r["ts"],
                "fingerprint": r["fingerprint"],
                "phase": r["phase"],
                "suggestion_id": r["suggestion_id"],
                "ok": None if r["ok"] is None else bool(r["ok"]),
                "details": json.loads(r["details_json"] or "{}"),
            }
            fh.write(_json(rec) + "\n")
            n += 1
    util_dest = dest.with_name("os_automation_utility.jsonl")
    n_u = 0
    stats = utility_stats(db)
    with util_dest.open("w", encoding="utf-8") as fh:
        for row in stats["automations"]:
            fh.write(_json({"schema": SCHEMA_UTILITY, **row}) + "\n")
            n_u += 1
    return {
        "receipts": {"path": str(dest), "n": n, "schema": SCHEMA_RECEIPT},
        "utility": {"path": str(util_dest), "n": n_u, "schema": SCHEMA_UTILITY},
    }


def detect_immediate_reversal(
    db: Any,
    *,
    fingerprint: str,
    completed_ts: float | None = None,
) -> bool:
    """If user undoes the automation effect within REVERSAL_WINDOW_S, note it."""
    ensure_routine_schema(db)
    row = db.execute(
        "SELECT sequence_json FROM routine_candidates WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    if not row:
        return False
    try:
        seq = json.loads(row["sequence_json"] or "[]")
    except json.JSONDecodeError:
        return False
    if not seq:
        return False
    # For single-step switch_app:X completed, reversal = switch away from X quickly
    fam, tgt = parse_token(seq[0])
    if fam not in {"switch_app", "focus_app"} or not tgt:
        return False
    t0 = completed_ts or _now()
    # look for a different switch_app soon after
    later = db.execute(
        """SELECT action_target, ts_after FROM context_episodes
           WHERE closed=1 AND action_family='switch_app'
             AND ts_after>? AND ts_after<=?
           ORDER BY ts_after ASC LIMIT 1""",
        (t0, t0 + REVERSAL_WINDOW_S),
    ).fetchone()
    if later and (later["action_target"] or "") != tgt:
        note_automation_receipt(
            db,
            fingerprint=fingerprint,
            phase="immediate_reversal",
            ok=True,
            details={
                "from": tgt,
                "to": later["action_target"],
                "delta_s": float(later["ts_after"]) - t0,
            },
        )
        return True
    return False


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
        # First-time utility "suggested" even if suggestion row already existed
        util = db.execute(
            "SELECT n_suggested FROM automation_utility WHERE fingerprint=?",
            (c["fingerprint"],),
        ).fetchone()
        first_suggest = (not util) or int(util["n_suggested"] or 0) == 0
        if new:
            created += 1
        if new or first_suggest:
            note_automation_receipt(
                db,
                fingerprint=c["fingerprint"],
                phase="suggested",
                ok=True,
                details={
                    "score": c["automation_score"],
                    "support": c["support"],
                    "sessions": c["sessions"],
                    "fresh_suggestion_row": bool(new),
                },
            )
        # Link suggestion id regardless of insert/update
        sid = db.execute(
            """SELECT id FROM suggestions WHERE kind=? AND status IN ('pending','accepted')
               AND proposal_json LIKE ? ORDER BY id DESC LIMIT 1""",
            (SUGGEST_KIND, f'%{c["fingerprint"]}%'),
        ).fetchone()
        if sid:
            db.execute(
                "UPDATE routine_candidates SET suggestion_id=? WHERE fingerprint=?",
                (sid["id"], c["fingerprint"]),
            )
            if new or first_suggest:
                db.execute(
                    """UPDATE automation_receipts SET suggestion_id=?
                       WHERE id=(
                         SELECT id FROM automation_receipts
                         WHERE fingerprint=? AND phase='suggested'
                         ORDER BY id DESC LIMIT 1
                       )""",
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
        return {"ok": False, "error": f"unknown routine {fingerprint}"}  # no invoke yet
    try:
        proposal = json.loads(row["proposal_json"] or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad proposal"}
    steps = proposal.get("steps") or []
    note_automation_receipt(
        db,
        fingerprint=fingerprint,
        phase="invoked",
        ok=True,
        details={"via": "run-routine", "n_steps": len(steps)},
    )
    results = []
    for step in steps:
        action = step.get("action")
        if action == "focus_workspace":
            ws = str(step.get("workspace") or "")
            if not ws:
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "missing workspace", "done": results},
                )
                return {"ok": False, "error": "missing workspace", "done": results}
            r = run_fn(["hyprctl", "dispatch", "workspace", ws])
            if getattr(r, "returncode", 1) != 0:
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "hyprctl workspace failed", "done": results},
                )
                return {"ok": False, "error": "hyprctl workspace failed", "done": results}
            results.append(f"workspace {ws}")
            record_semantic_action(
                db, family="switch_workspace", target=ws, source="keyboard",
                details={"via": "run-routine", "fingerprint": fingerprint},
            )
        elif action == "focus_app":
            app = str(step.get("app") or "")
            if not app:
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "missing app", "done": results},
                )
                return {"ok": False, "error": "missing app", "done": results}
            r = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:^{re.escape(app)}$"])
            if getattr(r, "returncode", 1) != 0:
                # soft: try without anchors
                r = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:{app}"])
            if getattr(r, "returncode", 1) != 0:
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": f"focuswindow {app} failed", "done": results},
                )
                return {"ok": False, "error": f"focuswindow {app} failed", "done": results}
            results.append(f"app {app}")
            record_semantic_action(
                db, family="switch_app", target=app, source="keyboard",
                details={"via": "run-routine", "fingerprint": fingerprint},
            )
        elif action == "select_tmux_pane":
            pane = str(step.get("pane_id") or "")
            if not pane or pane == "pane":
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "pane id unstable/missing", "done": results},
                )
                return {"ok": False, "error": "pane id unstable/missing", "done": results}
            r = run_fn(tmux_args_fn("select-pane", "-t", pane))
            if getattr(r, "returncode", 1) != 0:
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "tmux select-pane failed", "done": results},
                )
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
                note_automation_receipt(
                    db, fingerprint=fingerprint, phase="failed", ok=False,
                    details={"error": "no previous context", "done": results},
                )
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
            note_automation_receipt(
                db, fingerprint=fingerprint, phase="failed", ok=False,
                details={"error": f"step not allowlisted: {action}", "done": results},
            )
            return {"ok": False, "error": f"step not allowlisted: {action}", "done": results}
    note_automation_receipt(
        db,
        fingerprint=fingerprint,
        phase="completed",
        ok=True,
        details={"results": results, "source": "keyboard"},
    )
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
    note_automation_receipt(
        db,
        fingerprint=fp,
        phase="installed",
        ok=True,
        details={
            "chord": chord,
            "label": proposal.get("label"),
            "live_bind": live_ok,
            "path": str(path),
        },
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
    note_automation_receipt(
        db,
        fingerprint=fingerprint,
        phase="uninstalled",
        ok=True,
        details={"hypr_chord": hypr_chord},
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
    util = utility_stats(db)
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
        "utility": {
            "schema": util["schema"],
            "n_tracked": util["n_tracked"],
            "n_earning": util["n_earning"],
            "n_unused": util["n_unused"],
            "phase_counts": util["phase_counts"],
            "automations": util["automations"][:10],
        },
    }
