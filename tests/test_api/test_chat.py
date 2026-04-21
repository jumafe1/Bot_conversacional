"""
Integration tests for POST /api/v1/chat.

The BotService is replaced via FastAPI's dependency override, so no real
LLM calls are made. The stub mimics the bot contract: given a session and a
message, return a ``ChatResponse``.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from backend.api.v1.chat import get_bot_service
from backend.main import app
from backend.schemas.chat import ChatResponse


@pytest.fixture
def stub_bot() -> Generator[AsyncMock, None, None]:
    """Register a stub BotService for the duration of one test."""
    bot = AsyncMock()
    bot.process_message = AsyncMock(
        return_value=ChatResponse(
            session_id="test-session",
            answer="Hola, respuesta de prueba.",
            suggestions=["Sugerencia 1", "Sugerencia 2"],
            tool_calls_used=["filter_zones"],
        )
    )
    app.dependency_overrides[get_bot_service] = lambda: bot
    yield bot
    app.dependency_overrides.pop(get_bot_service, None)


async def test_health_check(client: AsyncClient) -> None:
    """Health endpoint is always live."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_chat_returns_200(client: AsyncClient, stub_bot: AsyncMock) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"session_id": "test-session", "message": "¿Cómo está Perfect Orders?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Hola, respuesta de prueba."
    assert body["suggestions"] == ["Sugerencia 1", "Sugerencia 2"]
    assert body["tool_calls_used"] == ["filter_zones"]
    assert body["session_id"] == "test-session"
    stub_bot.process_message.assert_awaited_once_with(
        session_id="test-session",
        user_message="¿Cómo está Perfect Orders?",
    )


async def test_chat_missing_session_id_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"message": "hola"})
    assert response.status_code == 422


async def test_chat_empty_message_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"session_id": "s", "message": ""},
    )
    assert response.status_code == 422


async def test_chat_llm_provider_error_returns_502(
    client: AsyncClient, stub_bot: AsyncMock
) -> None:
    from backend.core.exceptions import LLMProviderError

    stub_bot.process_message.side_effect = LLMProviderError("boom")
    response = await client.post(
        "/api/v1/chat",
        json={"session_id": "s", "message": "hola"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "LLM provider unavailable"


async def test_chat_unexpected_error_returns_500(
    client: AsyncClient, stub_bot: AsyncMock
) -> None:
    stub_bot.process_message.side_effect = RuntimeError("database gone")
    response = await client.post(
        "/api/v1/chat",
        json={"session_id": "s", "message": "hola"},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
