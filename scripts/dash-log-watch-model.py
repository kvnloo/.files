#!/usr/bin/env python3
"""Exact OAuth transport; stdin contains ONLY finite diagnostic facts, never logs."""
import contextlib
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

MODEL = "gpt-6-luna"


def main():
    try:
        if "--native" not in sys.argv:
            runtime = json.loads(subprocess.check_output(
                ["hermes", "--print-runtime-command"], text=True,
                stderr=subprocess.DEVNULL, timeout=5))
            os.execv(runtime[0], [runtime[0], "-I", str(Path(__file__).resolve()), "--native"])
        sys.path.insert(0, "/workspace/hermes-home/hermes-agent")
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(sys.stderr):
            import hermes_bootstrap  # noqa: F401
            request = json.loads(sys.stdin.read(20000))
            helper = Path(request["helper"])
            if hashlib.sha256(helper.read_bytes()).hexdigest() != request["helper_sha256"]:
                raise ValueError("helper identity")
            spec = importlib.util.spec_from_file_location("dash_summary_oauth", helper)
            if spec is None or spec.loader is None:
                raise ValueError("helper import")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            catalog = None
            if request.get("qualify"):
                from agent.auxiliary_client import resolve_provider_client
                from agent.codex_headers import codex_account_headers
                from agent.model_metadata import fetch_codex_catalog_entries
                import requests
                client, resolved = resolve_provider_client("openai-codex", model=MODEL, raw_codex=True)
                if client is None:
                    raise ValueError("credentials unavailable")
                try:
                    if resolved != MODEL or str(client.base_url).rstrip("/") != "https://chatgpt.com/backend-api/codex":
                        raise ValueError("route mismatch")
                    entries, status = fetch_codex_catalog_entries(lambda url: requests.get(
                        url, headers={"Authorization": "Bearer " + client.api_key,
                                      **codex_account_headers(client.api_key)}, timeout=12))
                    match = [e for e in entries if e.get("slug") == MODEL]
                    if status != 200 or not match:
                        raise ValueError("model absent")
                    catalog = {"http_status": status, "slug": match[0]["slug"], "fresh": True}
                finally:
                    client.close()
            facts = request["facts"]
            if len(json.dumps(facts)) > 6000:
                raise ValueError("bounded context exceeded")
            # The caller supplies only finite enums/hash/cursor/count data, not arbitrary text.
            prompt = ("Report-only incident reviewer. No tools, actions or fixes executed. "
                      "These are synthetic facts if fixture=true, otherwise allowlisted log classifications. "
                      "Do not infer hidden details. Return JSON only with severity (info/warning/critical), "
                      "summary, hypothesis, recommendation, confidence (low/medium/high). "
                      "Keep every string under 250 characters. Facts: " + json.dumps(facts))
            result = module.complete({"model": "openai-codex/" + MODEL, "prompt": prompt})
            text = result["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            incident = json.loads(text)
            if set(incident) != {"severity", "summary", "hypothesis", "recommendation", "confidence"}:
                raise ValueError("schema")
            if incident["severity"] not in ("info", "warning", "critical") or incident["confidence"] not in ("low", "medium", "high"):
                raise ValueError("enum")
            if any(not isinstance(v, str) or len(v) > 500 for v in incident.values()):
                raise ValueError("size")
            output = {"ok": True, "provider": "openai-codex", "requested_model": MODEL,
                      "returned_model": result["model"].removeprefix("openai-codex/"),
                      "incident": incident, "catalog": catalog}
    except Exception:
        # Raw provider diagnostics can include credentials or input; never relay them.
        output = {"ok": False, "code": "provider_refusal_timeout_or_invalid_response"}
    print(json.dumps(output), flush=True)


if __name__ == "__main__":
    main()
