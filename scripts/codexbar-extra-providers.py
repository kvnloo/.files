#!/usr/bin/env python3
"""Emit CodexBar-compatible JSON for Linux API-only provider tracking."""

from __future__ import annotations

import json
import os
import re
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


def ok_usage(
    provider: str,
    *,
    source: str = "api",
    label: str,
    used_percent: float | None = 0.0,
    credits: dict[str, Any] | None = None,
    secondary_label: str | None = None,
    secondary_used: float | None = None,
    quota: bool = True,
) -> dict[str, Any]:
    primary: dict[str, Any] = {
        "windowMinutes": 10080,
        "resetDescription": label,
    }
    if used_percent is not None:
        primary["usedPercent"] = used_percent
    if not quota:
        primary["quota"] = False
    payload: dict[str, Any] = {
        "provider": provider,
        "source": source,
        "usage": {
            "updatedAt": now_iso(),
            "primary": primary,
        },
    }
    if secondary_label is not None and secondary_used is not None:
        payload["usage"]["secondary"] = {
            "usedPercent": secondary_used,
            "windowMinutes": 43200,
            "resetDescription": secondary_label,
        }
    if credits is not None:
        payload["credits"] = credits
    return payload


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


def missing_key_message(env_name: str) -> str:
    return (
        f"Missing {env_name}. Add it to ~/.config/codexbar/secrets.env "
        f"or run: scripts/codexbar-sync-credentials.sh"
    )


def fetch_openrouter() -> dict[str, Any]:
    key = env_key("OPENROUTER_API_KEY")
    if not key:
        return err("openrouter", missing_key_message("OPENROUTER_API_KEY"))
    base = os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1").rstrip("/")
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://codexbar.local"),
        "X-Title": os.environ.get("OPENROUTER_X_TITLE", "CodexBar"),
    }
    status, payload = http_json(f"{base}/credits", headers=headers)
    if status != 200 or not isinstance(payload, dict):
        return err("openrouter", f"OpenRouter credits error: HTTP {status}")
    data = payload.get("data")
    if not isinstance(data, dict):
        return err("openrouter", "OpenRouter credits payload missing data object")
    total = float(data.get("total_credits") or 0)
    used = float(data.get("total_usage") or 0)
    balance = max(0.0, total - used)
    used_percent = 0.0 if total <= 0 else min(100.0, max(0.0, (used / total) * 100.0))
    credits = {
        "updatedAt": now_iso(),
        "remaining": f"${balance:.2f}",
        "remainingPercent": round(100.0 - used_percent, 1),
        "events": [],
    }
    return ok_usage(
        "openrouter",
        label=f"${balance:.2f} credits left",
        used_percent=round(used_percent, 1),
        credits=credits,
    )


def fetch_groq() -> dict[str, Any]:
    key = env_key("GROQ_API_KEY")
    if not key:
        return err("groq", missing_key_message("GROQ_API_KEY"))
    headers = {"Authorization": f"Bearer {key}"}
    status, payload = http_json("https://api.groq.com/openai/v1/models", headers=headers)
    if status != 200:
        return err("groq", f"Groq API error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok_usage("groq", label=f"Connected · {count} models", used_percent=None, quota=False)


def fetch_cerebras() -> dict[str, Any]:
    key = env_key("CEREBRAS_API_KEY")
    if not key:
        return err("cerebras", missing_key_message("CEREBRAS_API_KEY"))
    status, payload = http_json(
        "https://api.cerebras.ai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return err("cerebras", f"Cerebras API error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok_usage("cerebras", label=f"Connected · {count} models", used_percent=None, quota=False)


def fetch_vercel_gateway() -> dict[str, Any]:
    key = env_key("VERCEL_AI_GW_KEY") or env_key("VERCEL_API_KEY")
    if not key:
        return err("vercel", missing_key_message("VERCEL_AI_GW_KEY or VERCEL_API_KEY"))
    base = os.environ.get("VERCEL_AI_GW_URL", "https://ai-gateway.vercel.sh/v1").rstrip("/")
    status, payload = http_json(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
    if status != 200:
        return err("vercel", f"Vercel AI Gateway error: HTTP {status}")
    models = payload.get("data") if isinstance(payload, dict) else None
    count = len(models) if isinstance(models, list) else 0
    return ok_usage("vercel", label=f"Connected · {count} models", used_percent=None, quota=False)


def fetch_nous() -> dict[str, Any]:
    key = env_key("NOUS_API_KEY")
    if not key:
        return err("nous", missing_key_message("NOUS_API_KEY"))
    portal = os.environ.get("NOUS_PORTAL_URL", "https://portal.nousresearch.com").rstrip("/")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    status, payload = http_json(f"{portal}/api/oauth/account", headers=headers)
    if status != 200 or not isinstance(payload, dict):
        return err("nous", f"Nous Portal account error: HTTP {status}")
    paid = payload.get("paid_service_access")
    paid = paid if isinstance(paid, dict) else {}
    subscription = payload.get("subscription")
    subscription = subscription if isinstance(subscription, dict) else {}
    total = float(paid.get("total_usable_credits") or 0)
    sub_remaining = float(paid.get("subscription_credits_remaining") or subscription.get("credits_remaining") or 0)
    purchased = float(paid.get("purchased_credits_remaining") or payload.get("purchased_credits_remaining") or 0)
    monthly = float(subscription.get("monthly_credits") or paid.get("subscription_monthly_charge") or 0)
    plan = str(subscription.get("plan") or "Nous Portal").strip()
    used_percent = 0.0
    if monthly > 0:
        used_percent = min(100.0, max(0.0, ((monthly - sub_remaining) / monthly) * 100.0))
    credits = {
        "updatedAt": now_iso(),
        "remaining": f"${total:.2f}",
        "remainingPercent": round(max(0.0, 100.0 - used_percent), 1) if monthly > 0 else None,
        "events": [],
    }
    detail = f"${total:.2f} usable"
    if purchased > 0:
        detail += f" · ${purchased:.2f} purchased"
    return ok_usage(
        "nous",
        label=f"{plan} · {detail}",
        used_percent=round(used_percent, 1),
        credits=credits,
    )


FETCHERS = {
    "openrouter": fetch_openrouter,
    "groq": fetch_groq,
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
            for p in os.environ.get(
                "CODEXBAR_EXTRA_PROVIDERS",
                "openrouter groq cerebras vercel nous",
            ).split()
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
        except Exception as exc:  # noqa: BLE001 - surface provider failures to the bar
            out.append(err(provider, str(exc)))
    json.dump(out, sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
