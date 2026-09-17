import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def load_aggregate():
    path = REPO / "scripts" / "codexbar_aggregate.py"
    spec = importlib.util.spec_from_file_location("codexbar_aggregate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_average_skips_errors_and_treats_zero_credits_as_empty():
    agg = load_aggregate()
    providers = [
        {
            "provider": "codex",
            "usage": {
                "secondary": {"usedPercent": 100, "windowMinutes": 10080},
                "extraRateWindows": [
                    {"title": "Codex Spark 5-hour", "window": {"usedPercent": 0, "windowMinutes": 300}},
                ],
            },
        },
        {
            "provider": "claude",
            "error": {"message": "No available fetch strategy for claude."},
        },
        {
            "provider": "grok",
            "usage": {"primary": {"usedPercent": 94}},
        },
        {
            "provider": "nous",
            "usage": {"primary": {"usedPercent": 0, "resetDescription": "Free · $0.00 usable"}},
            "credits": {"remaining": "$0.00", "remainingPercent": None},
        },
        {
            "provider": "openrouter",
            "error": {"message": "Missing OPENROUTER_API_KEY."},
        },
    ]

    remaining = agg.average_remaining_percent(providers)

    # Codex tightest window is 0% left. Grok is 6% left. Nous $0 is 0% left.
    # Errors are excluded. (0 + 6 + 0) / 3 = 2.
    assert remaining == 2
    assert agg.bar_label(remaining) == "2% left"


def test_credits_remaining_percent_wins_over_fake_free_window():
    agg = load_aggregate()
    remaining = agg.provider_remaining_percent(
        {
            "provider": "nous",
            "usage": {"primary": {"usedPercent": 0}},
            "credits": {"remaining": "$12.50", "remainingPercent": 25},
        }
    )
    assert remaining == 25


def test_no_healthy_providers_has_no_average():
    agg = load_aggregate()
    remaining = agg.average_remaining_percent(
        [{"provider": "cursor", "error": {"message": "No Cursor session found."}}]
    )
    assert remaining is None
    assert agg.bar_label(remaining) == "AI —"


def test_zero_addon_credits_do_not_zero_subscription_quota():
    agg = load_aggregate()
    remaining = agg.provider_remaining_percent(
        {
            "provider": "codex",
            "credits": {"remaining": 0, "events": []},
            "usage": {
                "secondary": {"usedPercent": 52, "windowMinutes": 10080},
                "extraRateWindows": [
                    {"title": "Codex Spark 5-hour", "window": {"usedPercent": 0, "windowMinutes": 300}},
                    {"title": "Codex Spark Weekly", "window": {"usedPercent": 4, "windowMinutes": 10080}},
                ],
            },
        }
    )
    assert remaining == 48.0


def test_connectivity_only_payload_is_not_full_quota():
    agg = load_aggregate()
    remaining = agg.provider_remaining_percent(
        {
            "provider": "groq",
            "usage": {
                "primary": {
                    "resetDescription": "Connected · 3 models",
                }
            },
        }
    )
    assert remaining is None
    leftover_zero = agg.provider_remaining_percent(
        {
            "provider": "groq",
            "usage": {
                "primary": {
                    "usedPercent": 0.0,
                    "resetDescription": "Connected · 3 models",
                }
            },
        }
    )
    assert leftover_zero is None


def test_cursor_and_grok_bot_count_toward_all_usage():
    agg = load_aggregate()
    remaining = agg.provider_remaining_percent(
        {
            "provider": "cursor",
            "usage": {
                "primary": {"usedPercent": 9.5, "title": "Included"},
                "secondary": {"usedPercent": 2.8, "title": "Cursor Models"},
                "tertiary": {"usedPercent": 62.9, "title": "Other Models"},
                "extraRateWindows": [
                    {
                        "id": "cursor-grok-bot",
                        "title": "Grok Bot",
                        "window": {"usedPercent": 30.4, "windowMinutes": 10080},
                    }
                ],
            },
        }
    )
    assert round(remaining, 1) == 37.1


def test_stacked_segments_one_color_per_provider_no_names():
    agg = load_aggregate()
    providers = [
        {"provider": "codex", "usage": {"secondary": {"usedPercent": 40}}},
        {"provider": "claude", "error": "missing"},
        {"provider": "cursor", "usage": {"tertiary": {"usedPercent": 60}}},
        {"provider": "grok", "usage": {"primary": {"usedPercent": 90}}},
        {"provider": "groq", "error": "http 403"},
    ]
    segments = agg.stacked_segments(providers)
    assert [row["id"] for row in segments] == ["codex", "claude", "cursor", "grok", "groq"]
    assert segments[0]["progress"] == 0.6
    assert segments[0]["fill"] == "primary"
    assert segments[1]["error"] is True
    assert segments[1]["fill"] == "error"
    assert segments[1]["progress"] == 1.0
    assert segments[2]["progress"] == 0.4
    assert segments[2]["fill"] == "secondary"
    assert segments[3]["progress"] == 0.1
    assert segments[3]["fill"] == "on_surface"
    assert len({row["fill"] for row in segments if not row["error"]}) == 3


def test_qml_bar_widget_is_unnamed_stacked_bar():
    src = (REPO / "config/noctalia/plugins/codexbar/BarWidget.qml").read_text()
    assert "Repeater" in src
    assert "model: root.providers" in src
    assert "chipText(" not in src
    assert "NText" not in src.split("MouseArea")[0]
    assert "stackedBar" in src or "segmentFill" in src
    assert "usedPercent + \"%\"" not in src


def test_bar_widget_is_one_unnamed_stacked_progress():
    src = (REPO / "config/noctalia/overlays/codexbar-meter/bar_widget.luau").read_text()
    assert "Ultra " not in src
    assert '"Bot "' not in src
    assert "cursor-ultra" not in src
    assert "usageChip(" not in src
    assert "compactChip(" not in src
    render = src.split("local function render()", 1)[1]
    render = render.split("local function decodeProviders", 1)[0]
    assert "averageRemainingPercent()" not in render
    assert "segmentedUsage(" not in render
    assert "selectedEntries(" not in render
    assert "barProviderLimit" not in render
    assert "stackedBar(" in render
    assert "ui.progress(" in src
    assert "ui.label(" not in render
    assert "meta.label" not in render
    assert 'barWidget.render(ui.row({ key = "codexbar-all"' in render
    assert 'key = "codexbar-segments"' in src
    assert 'fill = "primary"' in src
    assert 'fill = "tertiary"' in src
    assert "label = \"Codex\"" in src
    assert "label = \"Grok\"" in src
    assert "label = \"Cursor\"" in src
    assert "label = \"Nous\"" in src
    assert "label = \"OpenRouter\"" in src


def test_bar_widget_click_opens_named_panel():
    src = (REPO / "config/noctalia/overlays/codexbar-meter/bar_widget.luau").read_text()
    assert "local function panelEntryIdForCurrentData()" in src
    assert "noctalia.togglePanel(panelEntryIdForCurrentData())" in src
    assert "PANEL_IDS.tall" in src


def test_panel_window_rows_are_nil_safe():
    src = (REPO / "config/noctalia/overlays/codexbar-meter/panel.luau").read_text()
    assert "local function windowRow(item)" in src
    assert 'if type(item) ~= "table" or type(item.window) ~= "table" then return nil end' in src
    assert 'string.find(stage, "risk", 1, true)' in src


def test_live_cache_average_matches_bar_contract():
    cache = Path.home() / ".cache" / "codexbar-waybar" / "full.json"
    if not cache.is_file():
        return
    agg = load_aggregate()
    providers = json.loads(cache.read_text())
    remaining = agg.average_remaining_percent(providers)
    values = [
        agg.provider_remaining_percent(row)
        for row in providers
        if agg.provider_remaining_percent(row) is not None
    ]
    expected = int(round(sum(values) / len(values))) if values else None
    assert remaining == expected
    assert remaining != 0
    assert remaining is None or remaining > 1
    assert agg.bar_label(remaining) == f"{remaining}% left"
