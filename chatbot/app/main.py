"""Chatbot demo that routes all LLM traffic through SentinelGuard."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"

SENTINELGUARD_BASE_URL = os.getenv("SENTINELGUARD_BASE_URL", "http://localhost:8080/v1")
SENTINELGUARD_API_KEY = os.getenv("SENTINELGUARD_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "sentinel-auto")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))

CHATBOT_REQUESTS = Counter(
    "chatbot_requests_total",
    "Total chatbot requests by outcome.",
    ["outcome"],
)
CHATBOT_GATEWAY_LATENCY = Histogram(
    "chatbot_gateway_latency_seconds",
    "Latency of chatbot calls to SentinelGuard.",
    ["outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None


app = FastAPI(title="SentinelGuard Chatbot PoC", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "sentinelguard_base_url": SENTINELGUARD_BASE_URL,
        "chat_model": CHAT_MODEL,
    }


@app.get("/api/config")
async def config() -> dict[str, Any]:
    return {
        "sentinelguard_base_url": SENTINELGUARD_BASE_URL,
        "chat_model": CHAT_MODEL,
    }


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    model = request.model or CHAT_MODEL
    payload = {
        "model": model,
        "messages": [message.model_dump() for message in request.messages],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    headers = {"Content-Type": "application/json"}
    if SENTINELGUARD_API_KEY:
        headers["Authorization"] = f"Bearer {SENTINELGUARD_API_KEY}"

    started = time.perf_counter()
    outcome = "error"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{SENTINELGUARD_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        CHATBOT_REQUESTS.labels(outcome="gateway_unreachable").inc()
        CHATBOT_GATEWAY_LATENCY.labels(outcome="gateway_unreachable").observe(
            time.perf_counter() - started
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Could not reach SentinelGuard gateway",
                "error": str(exc),
            },
        ) from exc

    try:
        data = response.json()
    except ValueError:
        data = {"error": {"message": response.text[:500], "type": "non_json_response"}}

    if response.status_code < 400:
        outcome = "passed"
    else:
        error_type = str(data.get("error", {}).get("type", "gateway_error"))
        if "blocked" in error_type:
            outcome = "blocked"
        elif response.status_code == 401:
            outcome = "auth_error"
        else:
            outcome = "gateway_error"

    CHATBOT_REQUESTS.labels(outcome=outcome).inc()
    CHATBOT_GATEWAY_LATENCY.labels(outcome=outcome).observe(time.perf_counter() - started)

    if response.status_code >= 400:
        return {
            "ok": False,
            "status": response.status_code,
            "model": model,
            "gateway": data,
        }

    message = _assistant_message(data)
    return {
        "ok": True,
        "status": response.status_code,
        "model": data.get("model", model),
        "provider_response": data,
        "message": message,
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _assistant_message(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0] or {}
    message = first.get("message") or {}
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(first.get("text") or "")
