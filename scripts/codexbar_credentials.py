#!/usr/bin/env python3
"""Resolve CodexBar extra-provider keys from local stores. Never print secrets."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


PROVIDER_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "vercel": "VERCEL_AI_GW_KEY",
    "nous": "NOUS_API_KEY",
}


def default_omp_db() -> Path:
    override = os.environ.get("CODEXBAR_OMP_DB", "").strip()
    if override:
        return Path(override)
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    # OMP keeps auth in ~/.omp/agent/agent.db, not XDG_DATA_HOME.
    return Path.home() / ".omp" / "agent" / "agent.db"


def _credential_key(data: Any) -> str:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return data.strip()
    if isinstance(data, dict):
        for field in ("key", "api_key", "apiKey", "access_token", "token"):
            value = str(data.get(field) or "").strip()
            if value:
                return value
    return ""


def omp_api_keys(db_path: Path | str | None = None) -> dict[str, str]:
    path = Path(db_path) if db_path is not None else default_omp_db()
    if not path.is_file():
        return {}
    exported: dict[str, str] = {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT provider, credential_type, data FROM auth_credentials"
        )
        for provider, credential_type, data in rows:
            pid = str(provider or "").lower()
            env_name = next((env for token, env in PROVIDER_ENV.items() if token in pid), None)
            if env_name is None or env_name in exported:
                continue
            if str(credential_type or "") not in {"api_key", "oauth", "token"}:
                continue
            key = _credential_key(data)
            if key and not key.startswith("$"):
                exported[env_name] = key
    finally:
        con.close()
    return exported


def emit_exports() -> None:
    for name, value in omp_api_keys().items():
        if os.environ.get(name, "").strip():
            continue
        print(f"{name}={value}")


if __name__ == "__main__":
    emit_exports()
