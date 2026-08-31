"""Small OpenAI-compatible mock provider for the gateway demo."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Response, status


PROVIDER_NAME = os.getenv("PROVIDER_NAME", "mock-provider")
FAIL_ON_TRIGGER = os.getenv("FAIL_ON_TRIGGER", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title=f"{PROVIDER_NAME} OpenAI-compatible mock LLM")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "provider": PROVIDER_NAME}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "mock-fast", "object": "model", "owned_by": PROVIDER_NAME},
            {"id": "mock-smart", "object": "model", "owned_by": PROVIDER_NAME},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict[str, Any], response: Response) -> dict[str, Any]:
    prompt = _last_user_text(payload.get("messages") or [])
    if FAIL_ON_TRIGGER and "trigger provider failure" in prompt.lower():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "error": {
                "message": f"{PROVIDER_NAME} simulated a temporary provider failure",
                "type": "mock_provider_unavailable",
            }
        }

    model = str(payload.get("model") or "mock-fast")
    answer = _answer(prompt)
    now = int(time.time())
    prompt_tokens = max(1, len(prompt.split()))
    completion_tokens = max(1, len(answer.split()))
    return {
        "id": f"chatcmpl-{PROVIDER_NAME}-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(item.get("text", "")) for item in content if isinstance(item, dict)
                )
    return ""


def _answer(prompt: str) -> str:
    lower = prompt.lower()
    if "trigger provider failure" in lower:
        return (
            f"Response from {PROVIDER_NAME}: the primary provider failed, "
            "so SentinelGuard successfully used a backup route."
        )
    if "architecture" in lower or "threat model" in lower:
        return (
            f"Response from {PROVIDER_NAME}: use a gateway boundary with "
            "prompt scanning, output scanning, private routes for sensitive data, "
            "provider failover, Prometheus metrics, and audit events."
        )
    return f"Response from {PROVIDER_NAME}: your request passed through SentinelGuard."
