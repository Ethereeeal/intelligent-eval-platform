"""Deterministic OpenAI-compatible and target-agent services for integration tests.

This app is only started by ``deploy/docker-compose.integration.yml``. It keeps
external failure scenarios reproducible without weakening the production API.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(title="EvalForge integration stub", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _last_user_message(payload: dict[str, Any]) -> str:
    messages = payload.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _completion_content(prompt: str) -> str:
    if '"checks"' in prompt and "check_type" in prompt:
        checks = [
            {"check_type": name, "passed": True, "reason": "联调桩：结构与证据检查通过"}
            for name in (
                "answerability",
                "faithfulness",
                "uniqueness",
                "evidence_sufficiency",
                "question_relevance",
            )
        ]
        return json.dumps({"checks": checks}, ensure_ascii=False)

    if "待出题陈述（EIU）" in prompt:
        statement_match = re.search(r"待出题陈述（EIU）：([^\n]+)", prompt)
        type_match = re.search(r"目标题型：([^\n]+)", prompt)
        statement = (statement_match.group(1).strip() if statement_match else "请依据原文回答")[:500]
        question_type = type_match.group(1).strip() if type_match else "rule"
        result = {
            "question": f"请说明以下规定的具体要求：{statement}",
            "question_type": question_type,
            "difficulty": "L2",
            "gold_answer": statement,
            "must_have_points": [statement],
            "acceptable_answers": [statement],
            "evidence_bindings": [],
            "is_unanswerable": False,
        }
        return json.dumps(result, ensure_ascii=False)

    # M02 uses deterministic extraction for rule-shaped paragraphs. Returning
    # an empty structured list makes any genuinely unclassified paragraph fail
    # closed instead of fabricating knowledge points.
    return json.dumps({"items": []}, ensure_ascii=False)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    payload = await request.json()
    content = _completion_content(_last_user_message(payload))
    return JSONResponse(
        {
            "id": "chatcmpl-integration",
            "object": "chat.completion",
            "model": payload.get("model") or "integration-stub",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
    )


@app.api_route(
    "/agent",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    response_model=None,
)
async def target_agent(
    request: Request,
    mode: str = Query(default="ok"),
) -> Any:
    if mode == "timeout":
        await asyncio.sleep(3)
    if mode == "error":
        raise HTTPException(status_code=500, detail="integration target failure")
    if mode == "invalid-json":
        return PlainTextResponse("not-json", media_type="application/json")

    payload: dict[str, Any] = {}
    if request.method != "GET":
        try:
            parsed = await request.json()
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:  # noqa: BLE001 - malformed payload is an intentional test input
            payload = {}
    question = str(payload.get("question") or request.query_params.get("question") or "")
    return JSONResponse({"answer": question, "trace_id": "integration-agent"})
