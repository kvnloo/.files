#!/usr/bin/env python3
"""Average remaining quota across healthy CodexBar providers."""

from __future__ import annotations

from typing import Any


def provider_error(provider: dict[str, Any] | None) -> str:
    if not isinstance(provider, dict) or provider.get("error") is None:
        return ""
    error = provider["error"]
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        return str(
            error.get("message")
            or error.get("description")
            or error.get("kind")
            or "Provider unavailable"
        )
    return "Provider unavailable"


def _credit_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _collect_used(window: Any, used: list[float]) -> None:
    if not isinstance(window, dict) or window.get("usedPercent") is None:
        return
    try:
        used.append(float(window["usedPercent"]))
    except (TypeError, ValueError):
        return


def _is_connectivity_window(window: Any) -> bool:
    if not isinstance(window, dict):
        return False
    if window.get("quota") is False:
        return True
    label = str(window.get("resetDescription") or window.get("label") or "").lower()
    return "connected" in label and "model" in label


def _collect_quota_used(window: Any, used: list[float]) -> None:
    if _is_connectivity_window(window):
        return
    _collect_used(window, used)


def provider_remaining_percent(provider: dict[str, Any] | None) -> float | None:
    if provider_error(provider) or not isinstance(provider, dict):
        return None

    credits = provider.get("credits")
    if not isinstance(credits, dict):
        usage = provider.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("credits"), dict):
            credits = usage["credits"]
        else:
            credits = None

    credit_percent = None
    credit_amount = None
    if isinstance(credits, dict):
        raw_percent = credits.get("remainingPercent")
        if raw_percent is not None:
            try:
                credit_percent = max(0.0, min(100.0, float(raw_percent)))
            except (TypeError, ValueError):
                credit_percent = None
        credit_amount = _credit_amount(credits.get("remaining"))

    usage = provider.get("usage")
    used: list[float] = []
    if isinstance(usage, dict):
        _collect_quota_used(usage.get("primary"), used)
        _collect_quota_used(usage.get("secondary"), used)
        _collect_quota_used(usage.get("tertiary"), used)
        extras = usage.get("extraRateWindows")
        if isinstance(extras, list):
            for extra in extras:
                if isinstance(extra, dict):
                    _collect_quota_used(extra.get("window") or extra, used)
        windows = usage.get("windows")
        if isinstance(windows, list):
            for item in windows:
                if isinstance(item, dict):
                    _collect_quota_used(item.get("window") or item, used)
        for key, value in usage.items():
            if key in {"identity", "credits"} or not isinstance(value, dict):
                continue
            if "usedPercent" in value:
                _collect_quota_used(value, used)

    if credit_percent is not None:
        return credit_percent
    if credit_amount is not None and credit_amount <= 0:
        if used and max(used) > 0:
            return max(0.0, min(100.0, 100.0 - max(used)))
        return 0.0
    if used:
        return max(0.0, min(100.0, 100.0 - max(used)))
    return None


def average_remaining_percent(providers: list[Any] | None) -> int | None:
    values = []
    for provider in providers or []:
        remaining = provider_remaining_percent(provider) if isinstance(provider, dict) else None
        if remaining is not None:
            values.append(remaining)
    if not values:
        return None
    return int(round(sum(values) / len(values)))


def bar_label(remaining: int | float | None) -> str:
    if remaining is None:
        return "AI —"
    return f"{int(round(remaining))}% left"


PROVIDER_FILLS = {
    "codex": "primary",
    "openai": "primary",
    "azureopenai": "primary",
    "claude": "tertiary",
    "gemini": "secondary",
    "copilot": "on_surface/0.8",
    "cursor": "secondary",
    "opencode": "tertiary/0.5",
    "opencodego": "tertiary/0.5",
    "qwencloud": "secondary/0.7",
    "alibaba": "secondary/0.7",
    "alibabatokenplan": "secondary/0.7",
    "antigravity": "tertiary/0.65",
    "kilo": "on_surface/0.65",
    "ollama": "on_surface/0.45",
    "openrouter": "primary/0.55",
    "grok": "on_surface",
    "groq": "tertiary/0.72",
    "cerebras": "secondary/0.55",
    "vercel": "on_surface/0.5",
    "nous": "primary/0.35",
}

_FALLBACK_FILLS = ("secondary", "tertiary", "primary", "on_surface")


def stacked_segments(providers: list[Any] | None) -> list[dict[str, Any]]:
    """One unlabeled progress segment per provider. Widths are equal."""
    segments: list[dict[str, Any]] = []
    rows = [row for row in (providers or []) if isinstance(row, dict)]
    for index, provider in enumerate(rows):
        provider_id = str(provider.get("provider") or provider.get("id") or "unknown")
        issue = provider_error(provider)
        remaining = provider_remaining_percent(provider)
        fill = PROVIDER_FILLS.get(provider_id.lower(), _FALLBACK_FILLS[index % len(_FALLBACK_FILLS)])
        if issue:
            fill = "error"
            progress = 1.0
        elif remaining is None:
            progress = 0.0
        else:
            progress = max(0.0, min(1.0, remaining / 100.0))
        segments.append(
            {
                "id": provider_id,
                "progress": progress,
                "fill": fill,
                "error": bool(issue),
            }
        )
    return segments
