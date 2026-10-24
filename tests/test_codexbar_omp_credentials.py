import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WRAPPER = Path.home() / ".local" / "bin" / "codexbar"
OMP_DB = Path.home() / ".omp" / "agent" / "agent.db"
OMP_MODELS = Path.home() / ".omp" / "agent" / "models.db"
CREDENTIALS = REPO / "scripts" / "codexbar_credentials.py"


def load_credentials():
    spec = importlib.util.spec_from_file_location("codexbar_credentials", CREDENTIALS)
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


def test_omp_stores_openrouter_key_but_not_cerebras_or_groq():
    con = sqlite3.connect(f"file:{OMP_DB}?mode=ro", uri=True)
    rows = {
        provider: credential_type
        for provider, credential_type in con.execute(
            "SELECT provider, credential_type FROM auth_credentials"
        )
    }
    assert rows.get("openrouter") == "api_key"
    assert "cerebras" not in rows
    assert "groq" not in rows


def test_omp_catalog_lists_cerebras_models_without_a_login():
    con = sqlite3.connect(f"file:{OMP_MODELS}?mode=ro", uri=True)
    blob = con.execute(
        "SELECT models FROM model_cache WHERE provider_id = 'cerebras'"
    ).fetchone()
    assert blob is not None
    models = json.loads(blob[0])
    ids = {item["id"] for item in models if isinstance(item, dict)}
    assert "qwen-3.8-27b" in ids
    assert "gpt-oss-120b" in ids


def test_loader_exports_omp_openrouter_and_skips_missing_cerebras():
    creds = load_credentials()
    exported = creds.omp_api_keys(OMP_DB)
    assert exported["OPENROUTER_API_KEY"].startswith("sk-or-")
    assert "CEREBRAS_API_KEY" not in exported
    assert "GROQ_API_KEY" not in exported


def test_env_sh_loads_omp_openrouter_key():
    env_script = REPO / "scripts" / "codexbar-env.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'unset OPENROUTER_API_KEY; source "$1"; '
            '[[ ${#OPENROUTER_API_KEY} -gt 8 && $OPENROUTER_API_KEY == sk-or-* ]] && echo loaded',
            "env-check",
            str(env_script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "loaded"


def test_live_wrapper_openrouter_uses_omp_key():
    row = wrapper_usage("openrouter")[0]
    assert row["provider"] == "openrouter"
    assert "error" not in row
    remaining = row["credits"]["remaining"]
    assert remaining.startswith("$")
    assert float(remaining[1:]) > 0
    used = row["usage"]["primary"]["usedPercent"]
    left = row["credits"]["remainingPercent"]
    assert 0 <= used <= 100
    assert 0 <= left <= 100


def test_live_wrapper_cerebras_and_groq_still_missing_keys():
    for provider, env_name in (
        ("cerebras", "CEREBRAS_API_KEY"),
        ("groq", "GROQ_API_KEY"),
    ):
        row = wrapper_usage(provider)[0]
        assert row["provider"] == provider
        assert env_name in row["error"]["message"]
