#!/usr/bin/env python3
"""Name Cursor Ultra windows and attach weekly Grok Bot usage.

The Linux CodexBar CLI emits primary/secondary/tertiary percents with no
dashboard titles and no extraRateWindows. Official mapping:

  primary   included total (monthly)
  secondary Cursor Models / Auto + Composer (monthly)
  tertiary  Other Models / API (monthly)
  extra     Grok Bot weekly from /api/dashboard/get-sand-usage-status
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CURSOR_CONFIG = Path(
    os.environ.get(
        "CODEXBAR_CONFIG_PATH",
        Path.home() / ".config" / "codexbar" / "config.json",
    )
)
SAND_URL = "https://cursor.com/api/dashboard/get-sand-usage-status"
GROK_BOT_ID = "cursor-grok-bot"


def cookie_header() -> str:
    env = os.environ.get("CODEXBAR_CURSOR_COOKIE", "").strip()
    if env:
        return env
    if not CURSOR_CONFIG.is_file():
        return ""
    try:
        data = json.loads(CURSOR_CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    for provider in data.get("providers") or []:
        if isinstance(provider, dict) and provider.get("id") == "cursor":
            return str(provider.get("cookieHeader") or "").strip()
    return ""


def format_reset(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    raw = iso_value.replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone()
    return f"Resets {local.strftime('%b %-d')}"


def window_minutes(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    minutes = int(round((b - a).total_seconds() / 60))
    return minutes if minutes > 0 else None


def fetch_grok_bot(cookie: str) -> dict[str, Any] | None:
    if not cookie:
        return None
    request = urllib.request.Request(
        SAND_URL,
        data=b"{}",
        method="POST",
        headers={
            "Cookie": cookie,
            "Origin": "https://cursor.com",
            "Referer": "https://cursor.com/dashboard",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "codexbar-annotate-cursor",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("hasNonZeroIncludedLimit") is not True:
        return None
    used = payload.get("usagePercent")
    if used is None:
        return None
    try:
        used_percent = max(0.0, min(100.0, float(used)))
    except (TypeError, ValueError):
        return None
    resets_at = payload.get("nextResetTimestampUtc")
    start = payload.get("currentPeriodStart")
    window = {
        "usedPercent": used_percent,
        "windowMinutes": window_minutes(start, resets_at) or 10080,
        "resetDescription": format_reset(resets_at) or "Resets weekly",
    }
    if isinstance(resets_at, str) and resets_at:
        window["resetsAt"] = resets_at.replace("+00:00", "Z")
    return {
        "id": GROK_BOT_ID,
        "title": "Grok Bot",
        "name": "Grok Bot",
        "window": window,
    }


def name_window(window: Any, title: str) -> Any:
    if not isinstance(window, dict):
        return window
    named = dict(window)
    named["title"] = title
    named["name"] = title
    named["label"] = title
    return named


def annotate_cursor(entry: dict[str, Any], cookie: str) -> dict[str, Any]:
    usage = entry.get("usage")
    if not isinstance(usage, dict):
        return entry
    updated = dict(entry)
    named_usage = dict(usage)
    named_usage["primary"] = name_window(usage.get("primary"), "Included")
    named_usage["secondary"] = name_window(usage.get("secondary"), "Cursor Models")
    named_usage["tertiary"] = name_window(usage.get("tertiary"), "Other Models")

    extras = [
        extra
        for extra in (named_usage.get("extraRateWindows") or [])
        if isinstance(extra, dict) and extra.get("id") != GROK_BOT_ID
    ]
    grok = fetch_grok_bot(cookie)
    if grok is not None:
        extras.append(grok)
    if extras:
        named_usage["extraRateWindows"] = extras
    updated["usage"] = named_usage
    return updated


def annotate(payload: list[Any]) -> list[Any]:
    cookie = cookie_header()
    out: list[Any] = []
    for entry in payload:
        if isinstance(entry, dict) and str(entry.get("provider") or "").lower() == "cursor":
            out.append(annotate_cursor(entry, cookie))
        else:
            out.append(entry)
    return out


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("[]")
        return 0
    data = json.loads(raw)
    if not isinstance(data, list):
        print(raw, end="")
        return 0
    json.dump(annotate(data), sys.stdout, separators=(",", ":"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
