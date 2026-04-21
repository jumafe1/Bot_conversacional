"""
Unit tests for backend.services.llm_service.LLMService.

We never call the real OpenAI / Anthropic APIs in these tests. Instead we
inject a fake client into ``LLMService(client=...)`` and simulate the
provider responses with ``SimpleNamespace`` objects that mimic the SDK
payload shape.

Coverage:
    - OpenAI: plain text response
    - OpenAI: single tool_call with JSON-parsed arguments
    - OpenAI: multiple tool_calls in one turn
    - OpenAI: malformed JSON arguments surface as LLMProviderError
    - OpenAI: SDK raising is wrapped in LLMProviderError
    - Anthropic: plain text response
    - Anthropic: tool_use block -> ToolCall
    - Anthropic: system prompt extracted from messages; tool results converted
    - Schema conversion: OpenAI function schema -> Anthropic input_schema
    - Unsupported provider raises LLMProviderError
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import LLMProviderError
from backend.services.llm_service import (
    LLMResponse,
    LLMService,
    ToolCall,
    _openai_supports_custom_temperature,
    _openai_tool_to_anthropic,
    _split_system_and_convert_for_anthropic,
)

# ---------------------------------------------------------------------------
# Helpers to build fake provider payloads
# ---------------------------------------------------------------------------

def _openai_completion(
    *,
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    finish_reason: str = "stop",
    model: str = "gpt-test",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    """Fake the shape of ``client.chat.completions.create(...)`` return."""
    message = SimpleNamespace(
        content=content,
        tool_calls=[
            SimpleNamespace(
                id=tc["id"],
                type="function",
                function=SimpleNamespace(
                    name=tc["name"],
                    arguments=tc["arguments"],
                ),
            )
            for tc in (tool_calls or [])
        ] or None,
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


def _fake_openai_client(completion: SimpleNamespace) -> MagicMock:
    """Build a client whose ``chat.completions.create`` is an AsyncMock."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


def _anthropic_response(
    *,
    text_blocks: list[str] | None = None,
    tool_use: list[dict] | None = None,
    stop_reason: str = "end_turn",
    model: str = "claude-test",
    input_tokens: int = 12,
    output_tokens: int = 7,
) -> SimpleNamespace:
    """Fake the shape of ``anthropic.AsyncAnthropic.messages.create``."""
    content: list[SimpleNamespace] = []
    for t in text_blocks or []:
        content.append(SimpleNamespace(type="text", text=t))
    for tu in tool_use or []:
        content.append(
            SimpleNamespace(
                type="tool_use",
                id=tu["id"],
                name=tu["name"],
                input=tu["input"],
            )
        )
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(
        content=content, usage=usage, model=model, stop_reason=stop_reason
    )


def _fake_anthropic_client(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# OpenAI path
# ---------------------------------------------------------------------------

async def test_openai_plain_text_response() -> None:
    client = _fake_openai_client(_openai_completion(content="Hola mundo"))
    svc = LLMService(provider="openai", model="gpt-test", client=client)

    resp = await svc.chat([{"role": "user", "content": "¿Qué tal?"}])

    assert isinstance(resp, LLMResponse)
    assert resp.content == "Hola mundo"
    assert resp.tool_calls == []
    assert resp.finish_reason == "stop"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5
    assert resp.model == "gpt-test"
    client.chat.completions.create.assert_awaited_once()


async def test_openai_single_tool_call_parsed() -> None:
    client = _fake_openai_client(
        _openai_completion(
            content=None,
            tool_calls=[
                {
                    "id": "call_abc",
                    "name": "filter_zones",
                    "arguments": json.dumps(
                        {"metric": "Perfect Orders", "country": "CO", "limit": 5}
                    ),
                }
            ],
            finish_reason="tool_calls",
        )
    )
    svc = LLMService(provider="openai", client=client)

    resp = await svc.chat(
        [{"role": "user", "content": "top zones"}],
        tools=[{"type": "function", "function": {"name": "filter_zones"}}],
    )

    assert resp.content is None
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.id == "call_abc"
    assert tc.name == "filter_zones"
    assert tc.arguments == {
        "metric": "Perfect Orders",
        "country": "CO",
        "limit": 5,
    }

    # tool_choice + parallel_tool_calls should have been passed through
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == "auto"
    assert call_kwargs["parallel_tool_calls"] is False


async def test_openai_multiple_tool_calls_parsed() -> None:
    client = _fake_openai_client(
        _openai_completion(
            tool_calls=[
                {"id": "a", "name": "filter_zones", "arguments": "{}"},
                {"id": "b", "name": "get_trend", "arguments": "{}"},
            ]
        )
    )
    svc = LLMService(provider="openai", client=client)
    resp = await svc.chat([{"role": "user", "content": "x"}], tools=[{"x": 1}])
    assert [tc.name for tc in resp.tool_calls] == ["filter_zones", "get_trend"]


async def test_openai_malformed_json_arguments_raises() -> None:
    client = _fake_openai_client(
        _openai_completion(
            tool_calls=[
                {"id": "x", "name": "filter_zones", "arguments": "{not valid json"}
            ]
        )
    )
    svc = LLMService(provider="openai", client=client)
    with pytest.raises(LLMProviderError, match="non-JSON arguments"):
        await svc.chat([{"role": "user", "content": "x"}], tools=[{"x": 1}])


async def test_openai_sdk_exception_wrapped() -> None:
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("rate limited"))
    svc = LLMService(provider="openai", client=client)
    with pytest.raises(LLMProviderError, match="rate limited"):
        await svc.chat([{"role": "user", "content": "x"}])


async def test_openai_omits_tool_kwargs_when_no_tools() -> None:
    client = _fake_openai_client(_openai_completion(content="hi"))
    svc = LLMService(provider="openai", client=client)
    await svc.chat([{"role": "user", "content": "x"}], tools=None)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


async def test_openai_uses_max_completion_tokens() -> None:
    client = _fake_openai_client(_openai_completion(content="hi"))
    svc = LLMService(provider="openai", model="gpt-4o", client=client)
    await svc.chat([{"role": "user", "content": "x"}])
    kwargs = client.chat.completions.create.call_args.kwargs
    # The old kwarg must not leak — GPT-5.x / o-series reject it.
    assert "max_tokens" not in kwargs
    assert "max_completion_tokens" in kwargs


async def test_openai_omits_temperature_for_gpt5_family() -> None:
    client = _fake_openai_client(_openai_completion(content="hi"))
    svc = LLMService(provider="openai", model="gpt-5.4-mini", client=client)
    await svc.chat([{"role": "user", "content": "x"}])
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs


async def test_openai_keeps_temperature_for_gpt4_family() -> None:
    client = _fake_openai_client(_openai_completion(content="hi"))
    svc = LLMService(provider="openai", model="gpt-4o", client=client)
    await svc.chat([{"role": "user", "content": "x"}])
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "temperature" in kwargs


# ---------------------------------------------------------------------------
# Anthropic path
# ---------------------------------------------------------------------------

async def test_anthropic_plain_text_response() -> None:
    client = _fake_anthropic_client(_anthropic_response(text_blocks=["buen día"]))
    svc = LLMService(provider="anthropic", model="claude-test", client=client)

    resp = await svc.chat([{"role": "user", "content": "hola"}])

    assert resp.content == "buen día"
    assert resp.tool_calls == []
    assert resp.finish_reason == "end_turn"
    assert resp.input_tokens == 12
    assert resp.output_tokens == 7


async def test_anthropic_tool_use_block_mapped() -> None:
    client = _fake_anthropic_client(
        _anthropic_response(
            text_blocks=["let me look that up"],
            tool_use=[
                {
                    "id": "toolu_01",
                    "name": "filter_zones",
                    "input": {"metric": "Lead Penetration", "country": "CO"},
                }
            ],
            stop_reason="tool_use",
        )
    )
    svc = LLMService(provider="anthropic", client=client)

    resp = await svc.chat(
        [{"role": "user", "content": "top zones"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "filter_zones",
                    "description": "d",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    assert resp.content == "let me look that up"
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.id == "toolu_01"
    assert tc.name == "filter_zones"
    assert tc.arguments == {"metric": "Lead Penetration", "country": "CO"}

    # The OpenAI-style schema should have been rewritten before hitting the SDK.
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tools"][0]["name"] == "filter_zones"
    assert "input_schema" in kwargs["tools"][0]
    assert "function" not in kwargs["tools"][0]


async def test_anthropic_system_prompt_extracted() -> None:
    client = _fake_anthropic_client(_anthropic_response(text_blocks=["ok"]))
    svc = LLMService(provider="anthropic", client=client)

    await svc.chat(
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
        ]
    )

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "You are helpful."
    assert all(m["role"] != "system" for m in kwargs["messages"])
    assert kwargs["messages"][0]["role"] == "user"


async def test_anthropic_tool_result_conversion() -> None:
    client = _fake_anthropic_client(_anthropic_response(text_blocks=["done"]))
    svc = LLMService(provider="anthropic", client=client)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hola"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "filter_zones",
                        "arguments": json.dumps({"metric": "Perfect Orders"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": json.dumps({"summary": "ok", "data": [], "metadata": {}}),
        },
    ]

    await svc.chat(messages)

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "sys"
    # assistant turn becomes a tool_use block; tool turn becomes a user
    # message holding a tool_result block pointing to that id.
    assistant_blocks = kwargs["messages"][1]["content"]
    assert any(b["type"] == "tool_use" and b["id"] == "call_1" for b in assistant_blocks)
    tool_user_turn = kwargs["messages"][2]
    assert tool_user_turn["role"] == "user"
    assert tool_user_turn["content"][0]["type"] == "tool_result"
    assert tool_user_turn["content"][0]["tool_use_id"] == "call_1"


# ---------------------------------------------------------------------------
# Pure converters
# ---------------------------------------------------------------------------

def test_openai_tool_to_anthropic_shape() -> None:
    openai_schema = {
        "type": "function",
        "function": {
            "name": "filter_zones",
            "description": "rank zones",
            "parameters": {"type": "object", "properties": {"metric": {"type": "string"}}},
        },
    }
    out = _openai_tool_to_anthropic(openai_schema)
    assert out == {
        "name": "filter_zones",
        "description": "rank zones",
        "input_schema": {"type": "object", "properties": {"metric": {"type": "string"}}},
    }


@pytest.mark.parametrize(
    "model, expected",
    [
        ("gpt-4o", True),
        ("gpt-4o-mini", True),
        ("gpt-4.1", True),
        ("gpt-5", False),
        ("gpt-5.4-mini", False),
        ("gpt-5.2", False),
        ("o1-preview", False),
        ("o3-mini", False),
        ("o4", False),
        ("custom-model", True),  # unknown defaults to "assume supported"
    ],
)
def test_openai_supports_custom_temperature(model: str, expected: bool) -> None:
    assert _openai_supports_custom_temperature(model) is expected


def test_split_system_handles_multiple_system_messages() -> None:
    messages = [
        {"role": "system", "content": "one"},
        {"role": "system", "content": "two"},
        {"role": "user", "content": "hi"},
    ]
    system, out = _split_system_and_convert_for_anthropic(messages)
    assert system == "one\n\ntwo"
    assert len(out) == 1 and out[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

async def test_unsupported_provider_raises() -> None:
    svc = LLMService(provider="openai", client=MagicMock())  # build ok
    # Force invalid provider post-init so we don't trigger the build path.
    svc.provider = "mistral"  # type: ignore[assignment]
    with pytest.raises(LLMProviderError, match="Unsupported provider"):
        await svc.chat([{"role": "user", "content": "x"}])
