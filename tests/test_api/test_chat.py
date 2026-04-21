"""
Integration tests for POST /api/v1/chat.

Uses httpx AsyncClient with the FastAPI app and a mocked BotService
so tests run without a real LLM API key or DuckDB data.

TODO (implement once BotService is ready):
    - test_chat_returns_200: valid request returns 200 with ChatResponse shape.
    - test_chat_missing_session_id: request without session_id returns 422.
    - test_chat_empty_message: empty message string returns 422.
    - test_chat_llm_provider_error: when LLMService raises, endpoint returns 502.
    - test_chat_preserves_session: two sequential requests with same session_id
      result in the second response being aware of the first message.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.skip(reason="BotService not yet implemented")
async def test_chat_returns_200(client: AsyncClient) -> None:
    """Valid chat request returns 200 with expected response structure."""
    response = await client.post(
        "/api/v1/chat",
        json={"session_id": "test-session", "message": "Hello"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


@pytest.mark.skip(reason="BotService not yet implemented")
async def test_chat_missing_session_id(client: AsyncClient) -> None:
    """Request missing session_id returns HTTP 422."""
    response = await client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 422


async def test_health_check(client: AsyncClient) -> None:
    """Health endpoint always returns 200 — no stubs needed."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
