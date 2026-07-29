"""Chat service — Demo placeholder.

In Phase 2 this will:
- Parse user intent from natural language
- Extract parameters (document name, sample ID, filters, etc.)
- Route to the appropriate business module
- Return structured responses with preview cards
"""
from __future__ import annotations


class ChatService:
    """Placeholder chat service for the Demo phase."""

    def process_message(self, content: str, session_id: int) -> dict:
        """Process a user message and return a placeholder response.

        In Phase 2 this will invoke intent parsing + business routing.
        """
        return {
            "role": "system",
            "message_type": "text",
            "content": {
                "text": (
                    "您好！智能问答功能将在第二阶段完整实现。"
                    "Demo 阶段请使用管理台页面完成文档上传、检索和评测集管理操作。"
                ),
            },
        }
