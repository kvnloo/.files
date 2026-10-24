import importlib.util
import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WRAPPER = Path.home() / ".local" / "bin" / "codexbar"
EXTRA = REPO / "scripts" / "codexbar-extra-providers.py"


def load_extra():
    spec = importlib.util.spec_from_file_location("codexbar_extra_providers", EXTRA)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def wrapper_usage(provider: str) -> list[dict]:
    result = subprocess.run(
        [str(WRAPPER), "usage", "--provider", provider, "--format", "json", "--json-only"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and payload
    return payload


def test_live_groq_and_cerebras_are_missing_keys():
    for provider, env_name in (
        ("groq", "GROQ_API_KEY"),
        ("cerebras", "CEREBRAS_API_KEY"),
    ):
        row = wrapper_usage(provider)[0]
        assert row["provider"] == provider
        assert row["source"] == "api"
        assert "error" in row
        assert env_name in row["error"]["message"]
        assert "usage" not in row
        assert "credits" not in row


def test_live_nous_is_free_plan_with_zero_credits():
    row = wrapper_usage("nous")[0]
    assert row["provider"] == "nous"
    assert row["source"] == "api"
    assert "error" not in row
    assert row["usage"]["primary"]["usedPercent"] == 0.0
    assert "Free" in row["usage"]["primary"]["resetDescription"]
    assert "$0.00" in row["usage"]["primary"]["resetDescription"]
    assert row["credits"]["remaining"] == "$0.00"
    assert row["credits"]["remainingPercent"] is None


def test_openrouter_success_shape_from_credits_api():
    extra = load_extra()
    extra.env_key = lambda name: "test-key" if name == "OPENROUTER_API_KEY" else ""
    extra.http_json = lambda url, headers, timeout=15.0: (
        200,
        {"data": {"total_credits": 20.0, "total_usage": 5.0}},
    )
    row = extra.fetch_openrouter()
    assert row["provider"] == "openrouter"
    assert row["usage"]["primary"]["usedPercent"] == 25.0
    assert row["credits"]["remaining"] == "$15.00"
    assert row["credits"]["remainingPercent"] == 75.0


def test_groq_and_cerebras_success_are_connectivity_not_quota():
    extra = load_extra()
    extra.env_key = lambda name: "test-key"
    extra.http_json = lambda url, headers, timeout=15.0: (
        200,
        {"data": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
    )
    groq = extra.fetch_groq()
    cerebras = extra.fetch_cerebras()
    assert "usedPercent" not in groq["usage"]["primary"]
    assert groq["usage"]["primary"]["resetDescription"] == "Connected · 3 models"
    assert groq["usage"]["primary"].get("quota") is False
    assert "credits" not in groq
    assert cerebras["usage"]["primary"]["resetDescription"] == "Connected · 3 models"
    assert "usedPercent" not in cerebras["usage"]["primary"]
    assert "credits" not in cerebras


def test_nous_account_payload_maps_free_zero_credits():
    extra = load_extra()
    extra.env_key = lambda name: "test-key" if name == "NOUS_API_KEY" else ""
    extra.http_json = lambda url, headers, timeout=15.0: (
        200,
        {
            "subscription": {
                "plan": "Free",
                "monthly_credits": 0,
                "credits_remaining": 0,
            },
            "paid_service_access": {
                "total_usable_credits": 0,
                "subscription_credits_remaining": 0,
                "purchased_credits_remaining": 0,
            },
        },
    )
    row = extra.fetch_nous()
    assert row["credits"]["remaining"] == "$0.00"
    assert row["credits"]["remainingPercent"] is None
    assert row["usage"]["primary"]["usedPercent"] == 0.0
    assert row["usage"]["primary"]["resetDescription"] == "Free · $0.00 usable"
