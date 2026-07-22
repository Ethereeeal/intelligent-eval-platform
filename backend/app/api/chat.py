"""Chat API routes — Demo placeholder.

These routes exist to register the chat interface contract.
In the Demo phase, they return static placeholder responses;
actual intent parsing and business routing will be implemented in Phase 2.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/chat")

# ---------------------------------------------------------------------------
# In-memory stub storage for the Demo placeholder
# ---------------------------------------------------------------------------
_stub_sessions: list[dict] = []
_stub_messages: list[dict] = []
_next_session_id = 1
_next_message_id = 1


@router.post("/sessions")
def create_session() -> dict:
    """Create a new chat session (placeholder)."""
    global _next_session_id
    session = {
        "session_id": _next_session_id,
        "corpus_id": None,
        "title": "新对话",
        "status": "active",
        "created_at": "2026-07-22T00:00:00Z",
        "updated_at": "2026-07-22T00:00:00Z",
    }
    _stub_sessions.append(session)
    _next_session_id += 1
    return session


@router.get("/sessions")
def list_sessions() -> list[dict]:
    """List all chat sessions (placeholder)."""
    return _stub_sessions


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    """Get a session with its messages (placeholder)."""
    for s in _stub_sessions:
        if s["session_id"] == session_id:
            msgs = [m for m in _stub_messages if m["session_id"] == session_id]
            return {**s, "messages": msgs}
    return {"error": "session not found", "messages": []}


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: int, payload: dict) -> dict:
    """Send a message and get a placeholder response."""
    global _next_message_id
    user_msg = {
        "message_id": _next_message_id,
        "session_id": session_id,
        "role": "user",
        "message_type": "text",
        "content": {"text": payload.get("content", "")},
        "intent": None,
        "intent_params": None,
        "created_at": "2026-07-22T00:00:00Z",
    }
    _stub_messages.append(user_msg)
    _next_message_id += 1

    # Placeholder system response
    system_msg = {
        "message_id": _next_message_id,
        "session_id": session_id,
        "role": "system",
        "message_type": "text",
        "content": {
            "text": (
                "您好！智能问答功能将在第二阶段完整实现。"
                "Demo 阶段请使用管理台页面完成文档上传、检索和评测集管理操作。"
            )
        },
        "intent": None,
        "intent_params": None,
        "created_at": "2026-07-22T00:00:00Z",
    }
    _stub_messages.append(system_msg)
    _next_message_id += 1

    return system_msg


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int) -> dict:
    """Delete a chat session (placeholder)."""
    global _stub_sessions, _stub_messages
    _stub_sessions = [s for s in _stub_sessions if s["session_id"] != session_id]
    _stub_messages = [m for m in _stub_messages if m["session_id"] != session_id]
    return {"status": "deleted"}
