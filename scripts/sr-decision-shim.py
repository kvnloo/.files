#!/usr/bin/env python3
"""
Thin OpenAI-compatible shim for vllm-sr/decision.
- Serves d1-3B via llama-server on port 11531
- Mirror mode: also calls Jev (jev-latest) in background, logs both to ~/.z0int/shadow/sr-decision/
- Returns d1 by default; config flag for Jev fallback on low confidence
- Kevin's text never goes to Jev (public/OSS only) unless approved
"""
import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Config
LLAMA_BASE = os.getenv("LLAMA_BASE", "http://127.0.0.1:11531/v1")
JEV_ENDPOINT = os.getenv("JEV_ENDPOINT", "https://api.jev-typesafe.com/v1")
JEV_API_KEY = os.getenv("JEV_API_KEY", "")
SHADOW_LOG_DIR = Path(os.getenv("SHADOW_LOG_DIR", "~/.z0int/shadow/sr-decision")).expanduser()
MODEL_ID = "vllm-sr/decision"
DEFAULT_RETURN = os.getenv("DEFAULT_RETURN", "d1")  # "d1" or "jev"
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
JEV_ALLOWED = os.getenv("JEV_ALLOWED", "false").lower() == "true"  # Kevin's text -> Jev only if true

SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sr-decision")

app = FastAPI(title="sr-decision shim", version="0.1.0")

# --- Models ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.0
    max_tokens: Optional[int] = 512
    stream: bool = False
    extra_body: Optional[Dict[str, Any]] = None

class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

# --- Helpers ---
def extract_question(messages: List[ChatMessage]) -> str:
    """Extract the question from the last user message."""
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""

def is_kevins_text(text: str) -> bool:
    """Heuristic: Kevin's text contains private identifiers, not public/OSS content."""
    # This is a simple heuristic; in production, use a proper classifier
    private_markers = ["@kvnloo", "kevin rajan", "my ", "i ", "my home", "my house", "my phone"]
    text_lower = text.lower()
    return any(m in text_lower for m in private_markers)

async def call_llama(question: str, request: ChatCompletionRequest) -> Dict[str, Any]:
    """Call llama-server for d1-3B decision."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": "d1-3B",
            "messages": [{"role": "user", "content": question}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
            "extra_body": {"systemone": True}  # d1 decision endpoint
        }
        r = await client.post(f"{LLAMA_BASE}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()

async def call_jev(question: str, request: ChatCompletionRequest) -> Dict[str, Any]:
    """Call Jev API for comparison."""
    if not JEV_API_KEY:
        return {"error": "no JEV_API_KEY"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": "jev-latest",
            "messages": [{"role": "user", "content": question}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False
        }
        headers = {"Authorization": f"Bearer {JEV_API_KEY}"}
        r = await client.post(f"{JEV_ENDPOINT}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

def parse_decision_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Parse choice/score/yes-no probabilities from response."""
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    # Try to parse JSON decision output
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "choice" in data:
            return data
        if isinstance(data, dict) and "score" in data:
            return data
    except json.JSONDecodeError:
        pass
    # Fallback: extract from text
    return {"raw": content}

def get_confidence(parsed: Dict[str, Any]) -> float:
    """Extract confidence from parsed decision."""
    if "score" in parsed:
        return float(parsed["score"])
    if "confidence" in parsed:
        return float(parsed["confidence"])
    if "prob" in parsed:
        return float(parsed["prob"])
    return 0.5  # default

async def log_shadow(question: str, d1_resp: Dict, jev_resp: Optional[Dict], 
                     d1_latency: float, jev_latency: Optional[float],
                     returned: str, confidence: float):
    """Log paired responses to shadow log."""
    entry = {
        "timestamp": time.time(),
        "question": question[:500],  # truncate
        "d1": {"response": d1_resp, "latency_ms": d1_latency * 1000},
        "jev": {"response": jev_resp, "latency_ms": jev_latency * 1000} if jev_resp else None,
        "returned": returned,
        "d1_confidence": confidence
    }
    log_file = SHADOW_LOG_DIR / f"sr-decision-{time.strftime('%Y%m%d')}.jsonl"
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")

# --- Routes ---
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{
            "id": MODEL_ID,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "z0intelligence"
        }]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, background_tasks: BackgroundTasks):
    question = extract_question(request.messages)
    if not question:
        raise HTTPException(400, "No question found")

    # Check if Kevin's text would go to Jev
    kevins_text = is_kevins_text(question)
    jev_allowed_this_call = JEV_ALLOWED and not kevins_text

    # Call d1 (llama-server)
    d1_start = time.perf_counter()
    try:
        d1_resp = await call_llama(question, request)
    except Exception as e:
        log.error(f"d1 call failed: {e}")
        d1_resp = {"error": str(e)}
    d1_latency = time.perf_counter() - d1_start

    d1_parsed = parse_decision_response(d1_resp)
    d1_confidence = get_confidence(d1_parsed)

    # Mirror to Jev (background, fire-and-forget)
    jev_resp = None
    jev_latency = None
    returned = DEFAULT_RETURN

    async def mirror_jev():
        nonlocal jev_resp, jev_latency
        if jev_allowed_this_call:
            jev_start = time.perf_counter()
            try:
                jev_resp = await call_jev(question, request)
            except Exception as e:
                log.warning(f"jev mirror failed: {e}")
                jev_resp = {"error": str(e)}
            jev_latency = time.perf_counter() - jev_start

    background_tasks.add_task(mirror_jev)

    # Decide what to return
    if DEFAULT_RETURN == "jev" and jev_allowed_this_call:
        returned = "jev"
        # Wait briefly for Jev (with timeout)
        await asyncio.sleep(0.1)
    elif DEFAULT_RETURN == "d1" and d1_confidence < CONFIDENCE_THRESHOLD and jev_allowed_this_call:
        returned = "jev"
        await asyncio.sleep(0.1)

    # Use d1 response by default
    if returned == "jev" and jev_resp and "error" not in jev_resp:
        response_data = jev_resp
        response_data["model"] = MODEL_ID
    else:
        response_data = d1_resp
        response_data["model"] = MODEL_ID

    # Log shadow (in background after we have both)
    async def delayed_log():
        await asyncio.sleep(0.5)  # give Jev time to complete
        await log_shadow(question, d1_resp, jev_resp, d1_latency, jev_latency, returned, d1_confidence)

    background_tasks.add_task(delayed_log)

    return JSONResponse(response_data)

@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_ID, "llama": LLAMA_BASE}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=11532, log_level="info")