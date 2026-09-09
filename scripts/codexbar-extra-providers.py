#!/usr/bin/env python3
"""Emit CodexBar-compatible JSON for providers not covered by the Linux CLI."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def err(provider: str, message: str, *, source: str = "api") -> dict[str, Any]:
    return {
        "provider": provider,
        "source": source,
        "error": {"kind": "provider", "code": 1, "message": message},
    }


def ok(provider: str, *, source: str = "api", label: str, used_percent: float = 0.0) -> dict[str, Any]:
    return {
        "provider": provider,
        "source": source,
        "usage": {
            "updatedAt": now_iso(),
            "primary": {
                "usedPercent": used_percent,
                "windowMinutes": 10080,
                "resetDescription": label,
            },
        },
    }


def env_key(name: str) -> str:
    return os.environ.get(name, "").strip()


def http_json(url: str, *, headers: dict[str, str], timeout: float = 15.0) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = body
        return exc.code, payload


def fetch_cerebras() -> dict[str, Any]:
    key = env_key("CEREBRAS_API_KEY")
    if not key:
        return err("cerebras", "Missing CEREBRAS_API_KEY. Add it to ~/.config/codexbar/secrets.env")
    status, payload = http_json(
        "https://api.cerebras.ai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return err("cerebras", f"Cerebras API error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok("cerebras", label=f"Connected · {count} models")


def fetch_vercel_gateway() -> dict[str, Any]:
    key = env_key("VERCEL_AI_GW_KEY") or env_key("VERCEL_API_KEY")
    if not key:
        return err("vercel", "Missing VERCEL_AI_GW_KEY. Add it to ~/.config/codexbar/secrets.env")
    base = os.environ.get("VERCEL_AI_GW_URL", "https://ai-gateway.vercel.sh/v1").rstrip("/")
    status, payload = http_json(
        f"{base}/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return err("vercel", f"Vercel AI Gateway error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok("vercel", label=f"Connected · {count} models")


def fetch_nous() -> dict[str, Any]:
    key = env_key("NOUS_API_KEY")
    if not key:
        return err("nous", "Missing NOUS_API_KEY. Add it to ~/.config/codexbar/secrets.env")
    base = os.environ.get("NOUS_API_URL", "https://inference-api.nousresearch.com/v1").rstrip("/")
    status, payload = http_json(
        f"{base}/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return err("nous", f"Nous Portal error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok("nous", label=f"Connected · {count} models")


FETCHERS = {
    "cerebras": fetch_cerebras,
    "vercel": fetch_vercel_gateway,
    "nous": fetch_nous,
    "nousportal": fetch_nous,
}


def main() -> int:
    requested = [p for p in sys.argv[1:] if p]
    if not requested:
        requested = [
            p.strip()
            for p in os.environ.get("CODEXBAR_EXTRA_PROVIDERS", "cerebras vercel nous").split()
            if p.strip()
        ]
    out: list[dict[str, Any]] = []
    for provider in requested:
        fetcher = FETCHERS.get(provider)
        if fetcher is None:
            out.append(err(provider, f"No extra-provider fetcher for {provider}"))
            continue
        try:
            out.append(fetcher())
        except Exception as exc:
            out.append(err(provider, str(exc)))
    json.dump(out, sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
