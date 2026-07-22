"""Chat schemas for smart Q&A interaction (Demo placeholder)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """A user message sent to the chat."""
    content: str = Field(..., min_length=1, description="用户输入的自然语言消息")


class ChatMessageResponse(BaseModel):
    """A single message in the chat history."""
    message_id: int
    session_id: int
    role: str  # "user" | "system"
    message_type: str  # "text" | "document_card" | "preview_card" | "task_progress" | "confirm_card"
    content: dict[str, Any] = Field(default_factory=dict)
    intent: str | None = None
    intent_params: dict[str, Any] | None = None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    """A chat session summary."""
    session_id: int
    corpus_id: int | None = None
    title: str
    status: str  # "active" | "archived"
    created_at: datetime
    updated_at: datetime


class ChatSessionDetailResponse(ChatSessionResponse):
    """Chat session detail with message list."""
    messages: list[ChatMessageResponse] = Field(default_factory=list)
