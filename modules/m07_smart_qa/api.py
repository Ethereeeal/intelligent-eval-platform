"""Chat API routes — Demo placeholder.

These routes exist to register the chat interface contract.
In the Demo phase, they return static placeholder responses;
actual intent parsing and business routing will be implemented in Phase 2.

说明：原实现使用模块级可变全局变量（list + 自增 id）配合 ``global`` 声明，
在多 worker / 并发请求下存在竞态丢数据风险。现收敛为带锁的
:class:`_StubStore` 单例，保证自增 id 与读写操作的线程安全。
"""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter

from modules.shared.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat")

_STUB_CREATED_AT = "2026-07-22T00:00:00Z"


class _StubStore:
    """线程安全的 Demo 会话/消息内存存储。

    并发处理规约：共享可变状态必须加锁。自增 id 与列表读写均在同一把锁内完成，
    避免多请求交错导致的 id 冲突与会话丢失。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: list[dict] = []
        self._messages: list[dict] = []
        self._next_session_id = 1
        self._next_message_id = 1

    def create_session(self) -> dict:
        with self._lock:
            session = {
                "session_id": self._next_session_id,
                "corpus_id": None,
                "title": "新对话",
                "status": "active",
                "created_at": _STUB_CREATED_AT,
                "updated_at": _STUB_CREATED_AT,
            }
            self._sessions.append(session)
            self._next_session_id += 1
            return session

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return list(self._sessions)

    def get_session(self, session_id: int) -> dict:
        with self._lock:
            for session in self._sessions:
                if session["session_id"] == session_id:
                    messages = [m for m in self._messages if m["session_id"] == session_id]
                    return {**session, "messages": messages}
            return {"error": "session not found", "messages": []}

    def append_messages(self, session_id: int, messages: list[dict]) -> None:
        with self._lock:
            for message in messages:
                message["message_id"] = self._next_message_id
                message["session_id"] = session_id
                message["created_at"] = _STUB_CREATED_AT
                self._messages.append(message)
                self._next_message_id += 1

    def delete_session(self, session_id: int) -> None:
        with self._lock:
            self._sessions = [s for s in self._sessions if s["session_id"] != session_id]
            self._messages = [m for m in self._messages if m["session_id"] != session_id]


# 模块级单例：进程内唯一存储实例，避免多实例各自维护状态
_store = _StubStore()


@router.post("/sessions")
def create_session() -> dict:
    """Create a new chat session (placeholder)."""
    logger.debug("create_session")
    return _store.create_session()


@router.get("/sessions")
def list_sessions() -> list[dict]:
    """List all chat sessions (placeholder)."""
    return _store.list_sessions()


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    """Get a session with its messages (placeholder)."""
    return _store.get_session(session_id)


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: int, payload: dict[str, Any]) -> dict:
    """Send a message and get a placeholder response."""
    user_msg: dict[str, Any] = {
        "role": "user",
        "message_type": "text",
        "content": {"text": payload.get("content", "")},
        "intent": None,
        "intent_params": None,
    }
    system_msg: dict[str, Any] = {
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
    }
    _store.append_messages(session_id, [user_msg, system_msg])

    # 返回最后一条（系统回复）给用户
    messages = _store.get_session(session_id).get("messages", [])
    return messages[-1] if messages else system_msg


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int) -> dict:
    """Delete a chat session (placeholder)."""
    _store.delete_session(session_id)
    return {"status": "deleted"}
