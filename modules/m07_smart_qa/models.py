"""Chat data models (Demo placeholder)."""
from dataclasses import dataclass


@dataclass
class ChatSessionRecord:
    session_id: int
    title: str
    status: str  # "active" | "archived"
    created_at: str
    updated_at: str


@dataclass
class ChatMessageRecord:
    message_id: int
    session_id: int
    role: str  # "user" | "system"
    message_type: str  # "text" | "document_card" | "preview_card" | "task_progress" | "confirm_card"
    content: str  # JSON string
    intent: str | None
    intent_params: str | None
    created_at: str
