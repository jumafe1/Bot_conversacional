"""
Unit tests for the BotService orchestration loop.

The LLMService is stubbed with a scripted fake that returns a predetermined
sequence of LLMResponse objects. The real tool registry is used, so we
actually hit DuckDB for the tool-call branches — this catches integration
bugs between the bot loop and the handlers.

Covered scenarios:
    - Plain answer (no tool calls) + suggestion parsing
    - Single tool call cycle -> final answer
    - Multiple sequential tool cycles
    - Budget exhaustion triggers forced-text fallback
    - Tool invocation errors are delivered back as tool messages, not raised
    - Memory is populated with only user + final assistant turns
    - Unknown tool names flow through dispatch's structured error path
    - Pure helper: _split_answer_and_suggestions (several formats)
    - Pure helper: _assistant_tool_call_message shape
"""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.schemas.chat import ChatResponse
from backend.services.bot_service import (
    BotService,
    _assistant_tool_call_message,
    _split_answer_and_suggestions,
)
from backend.services.llm_service import LLMResponse, ToolCall
from backend.services.memory_service import MemoryService

# ---------------------------------------------------------------------------
# Scripted LLM stub
# ---------------------------------------------------------------------------

def _make_llm_stub(responses: list[LLMResponse]) -> MagicMock:
    """Return a mock LLMService whose ``chat`` yields ``responses`` in order."""
    stub = MagicMock()
    stub.chat = AsyncMock(side_effect=list(responses))
    return stub


def _make_bot(llm: MagicMock, memory: MemoryService | None = None) -> BotService:
    return BotService(llm=llm, memory=memory or MemoryService(), max_iterations=3)


def _text_response(content: str) -> LLMResponse:
    return LLMResponse(content=content, finish_reason="stop", model="test")


def _tool_call_response(name: str, arguments: dict, call_id: str = "c1") -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        finish_reason="tool_calls",
        model="test",
    )


# ---------------------------------------------------------------------------
# process_message — core flows
# ---------------------------------------------------------------------------

async def test_plain_answer_no_tool_calls() -> None:
    llm = _make_llm_stub(
        [
            _text_response(
                "El último valor de Perfect Orders en Colombia es 84.2%.\n\n"
                "**Análisis sugerido:**\n"
                "- Ver tendencia de Perfect Orders en CO\n"
                "- Comparar CO vs MX\n"
            )
        ]
    )
    bot = _make_bot(llm)

    resp = await bot.process_message("sess-1", "¿Cómo está Perfect Orders en CO?")

    assert isinstance(resp, ChatResponse)
    assert resp.session_id == "sess-1"
    assert "84.2%" in resp.answer
    assert "Análisis sugerido" not in resp.answer
    assert resp.suggestions == [
        "Ver tendencia de Perfect Orders en CO",
        "Comparar CO vs MX",
    ]
    assert resp.tool_calls_used == []
    llm.chat.assert_awaited_once()


async def test_single_tool_cycle_flows_to_final_answer() -> None:
    llm = _make_llm_stub(
        [
            _tool_call_response(
                "filter_zones",
                {"metric": "Perfect Orders", "country": "CO", "limit": 3},
            ),
            _text_response(
                "Top 3 zonas en CO por Perfect Orders: Chapinero, Zona T, Cedritos.\n\n"
                "**Análisis sugerido:**\n"
                "- Ver tendencia de Chapinero\n"
            ),
        ]
    )
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "Top 3 zonas en CO")

    assert resp.tool_calls_used == ["filter_zones"]
    assert llm.chat.await_count == 2

    # Second call must have included the tool result in messages.
    second_call_messages = llm.chat.await_args_list[1].args[0]
    roles = [m["role"] for m in second_call_messages]
    assert "assistant" in roles and "tool" in roles
    tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1"
    parsed = json.loads(tool_msg["content"])
    assert "summary" in parsed and "data" in parsed and "metadata" in parsed


async def test_multiple_tool_cycles() -> None:
    llm = _make_llm_stub(
        [
            _tool_call_response(
                "filter_zones",
                {"metric": "Perfect Orders", "country": "CO", "limit": 2},
                call_id="c1",
            ),
            _tool_call_response(
                "get_trend",
                {"metric": "Perfect Orders", "country": "CO", "num_weeks": 4},
                call_id="c2",
            ),
            _text_response("Respuesta final sintetizando ambos tools."),
        ]
    )
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "ranking y tendencia")

    assert resp.tool_calls_used == ["filter_zones", "get_trend"]
    assert llm.chat.await_count == 3
    assert resp.suggestions == []


async def test_budget_exhaustion_forces_text_reply() -> None:
    # Every call returns another tool_call — the loop must break after
    # max_iterations=3 and issue one final text-only call.
    spam = _tool_call_response("filter_zones", {"metric": "Perfect Orders"})
    final = _text_response("No pude terminar, acá lo que encontré hasta ahora.")
    llm = _make_llm_stub([spam, spam, spam, final])
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "loop forever")

    assert len(resp.tool_calls_used) == 3
    # Last call should be tools=None (forced text-only)
    last_kwargs = llm.chat.await_args_list[-1].kwargs
    assert last_kwargs.get("tools") is None
    assert "No pude terminar" in resp.answer


async def test_tool_dispatch_errors_are_not_raised() -> None:
    # An invalid country code returns an error tool-result, not an exception.
    llm = _make_llm_stub(
        [
            _tool_call_response(
                "filter_zones",
                {"metric": "Perfect Orders", "country": "XX"},
            ),
            _text_response("Corrijo el país."),
        ]
    )
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "boom")

    assert resp.answer == "Corrijo el país."
    tool_msg = next(
        m for m in llm.chat.await_args_list[1].args[0] if m["role"] == "tool"
    )
    parsed = json.loads(tool_msg["content"])
    assert parsed["metadata"]["error"] is True


async def test_unknown_tool_name_flows_as_error() -> None:
    llm = _make_llm_stub(
        [
            _tool_call_response("ghost_tool", {"x": 1}),
            _text_response("Retrying with a real tool name."),
        ]
    )
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "try unknown tool")

    assert resp.tool_calls_used == ["ghost_tool"]
    tool_msg = next(
        m for m in llm.chat.await_args_list[1].args[0] if m["role"] == "tool"
    )
    parsed = json.loads(tool_msg["content"])
    assert parsed["metadata"]["error"] is True


async def test_memory_only_holds_user_and_assistant_turns() -> None:
    mem = MemoryService()
    llm = _make_llm_stub(
        [
            _tool_call_response("filter_zones", {"metric": "Perfect Orders"}),
            _text_response("Listo.\n\n**Suggested next analyses:**\n- More\n"),
        ]
    )
    bot = _make_bot(llm, memory=mem)

    await bot.process_message("s-mem", "una pregunta")

    history = mem.get_history("s-mem")
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "una pregunta"
    assert "Listo." in history[1]["content"]
    assert "Suggested next analyses" not in history[1]["content"]


async def test_history_is_replayed_on_next_turn() -> None:
    mem = MemoryService()
    llm = _make_llm_stub(
        [
            _text_response("Hola."),                # turn 1
            _text_response("Seguimos conversando."),  # turn 2
        ]
    )
    bot = _make_bot(llm, memory=mem)

    await bot.process_message("s", "¿hola?")
    await bot.process_message("s", "seguimos")

    second_msgs = llm.chat.await_args_list[1].args[0]
    # The second call must see both prior user+assistant turns plus the new
    # user turn (3 non-system messages in total).
    non_system = [m for m in second_msgs if m["role"] != "system"]
    assert len(non_system) == 3
    assert non_system[0] == {"role": "user", "content": "¿hola?"}
    assert non_system[1]["role"] == "assistant"
    assert non_system[2] == {"role": "user", "content": "seguimos"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected_len",
    [
        ("Answer.\n\n**Suggested next analyses:**\n- a\n- b", 2),
        ("Answer.\n\nAnálisis sugerido:\n- uno\n- dos\n- tres", 3),
        ("Answer.\n\n**Análisis sugeridos:**\n* item1\n* item2", 2),
        ("Answer with no suggestion block.", 0),
        (
            "Answer.\n\nSuggested next analyses:\n1. primero\n2. segundo",
            2,
        ),
    ],
)
def test_split_answer_and_suggestions_variants(text: str, expected_len: int) -> None:
    clean, suggestions = _split_answer_and_suggestions(text)
    assert len(suggestions) == expected_len
    assert "Answer" in clean
    # The label must not survive in the cleaned answer
    assert "Análisis sugerido" not in clean
    assert "Suggested next analyses" not in clean


def test_suggestions_capped_at_five() -> None:
    text = (
        "Answer.\n\n**Suggested next analyses:**\n"
        + "\n".join(f"- item {i}" for i in range(10))
    )
    _, suggestions = _split_answer_and_suggestions(text)
    assert len(suggestions) == 5


def test_assistant_tool_call_message_shape() -> None:
    response = LLMResponse(
        content="thinking...",
        tool_calls=[
            ToolCall(id="c1", name="filter_zones", arguments={"metric": "X"})
        ],
    )
    msg = _assistant_tool_call_message(response)
    assert msg["role"] == "assistant"
    assert msg["content"] == "thinking..."
    assert len(msg["tool_calls"]) == 1
    tc = msg["tool_calls"][0]
    assert tc["id"] == "c1"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "filter_zones"
    assert json.loads(tc["function"]["arguments"]) == {"metric": "X"}


def test_assistant_tool_call_message_empty_content() -> None:
    # content=None should serialise as empty string, not literal "None".
    response = LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="aggregate", arguments={})],
    )
    msg = _assistant_tool_call_message(response)
    assert msg["content"] == ""


# ---------------------------------------------------------------------------
# Fallback when LLM returns empty content on final turn
# ---------------------------------------------------------------------------

async def test_empty_final_response_gets_fallback_message() -> None:
    empty_final = replace(_text_response(""), content=None)
    llm = _make_llm_stub([empty_final])
    bot = _make_bot(llm)

    resp = await bot.process_message("sess", "x")
    assert resp.answer  # non-empty fallback
    assert "presupuesto" in resp.answer or "specific" in resp.answer.lower()
