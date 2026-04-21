"""
Pydantic models for the chat API contract.

Request:  ChatRequest   → what the client sends
Response: ChatResponse  → what the API returns
Internal: Message       → single turn in conversation history
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single message in the conversation history."""

    role: Literal["user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat."""

    session_id: str = Field(
        ...,
        description="Unique identifier for the conversation session.",
        examples=["user-123-session-abc"],
    )
    message: str = Field(
        ...,
        description="The user's natural-language question.",
        min_length=1,
        max_length=4096,
        examples=["¿Cuáles son las zonas problemáticas en Colombia este mes?"],
    )


class ChatResponse(BaseModel):
    """Response body for POST /api/v1/chat."""

    session_id: str
    answer: str = Field(description="The bot's natural-language answer.")
    suggestions: list[str] = Field(
        default_factory=list,
        description="2–3 follow-up analysis suggestions.",
    )
    tool_calls_used: list[str] = Field(
        default_factory=list,
        description="Names of tools invoked to answer this query (for observability).",
    )
