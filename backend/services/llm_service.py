"""
Provider-agnostic LLM service.

Wraps OpenAI and Anthropic behind a single ``chat()`` method so the rest of
the application never imports a provider SDK directly. Selecting the
provider is a one-env-var change (``LLM_PROVIDER``).

Design notes:
    - The canonical message format used by callers is OpenAI's shape:
        {"role": "system"|"user"|"assistant"|"tool", "content": str,
         "tool_calls": [...], "tool_call_id": str}
      For Anthropic, messages are translated at the boundary (the system
      prompt becomes a top-level ``system`` argument, and assistant tool
      calls / tool results are emitted as content blocks).
    - Tool schemas are expected in the OpenAI function-calling format (what
      ``tools/registry.get_openai_tools_schema()`` already produces). The
      Anthropic path converts them on the way in.
    - Both SDKs already retry transient errors (429, 5xx) internally. We
      surface only the final failure, wrapped in ``LLMProviderError`` so the
      API layer can map it to HTTP 502.
    - The service is ``async``: FastAPI endpoints await directly, and the
      bot orchestration loop can issue multiple ``chat()`` calls per user
      turn without blocking the event loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.core.config import settings
from backend.core.exceptions import LLMProviderError

logger = logging.getLogger(__name__)

Provider = Literal["openai", "anthropic"]


# ---------------------------------------------------------------------------
# Normalised response shape
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM.

    ``arguments`` is already JSON-decoded so handlers can consume it
    directly. If the provider returned malformed JSON for the arguments the
    service raises ``LLMProviderError`` rather than silently passing junk
    downstream.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider.

    Exactly one of ``content`` / ``tool_calls`` is typically populated per
    assistant turn:
      - ``content`` is set when the model answers in plain text
        (``finish_reason == "stop"`` on OpenAI, ``end_turn`` on Anthropic).
      - ``tool_calls`` is non-empty when the model chose to call tools.
    In rare cases both may be present (brief commentary plus a tool call);
    callers should handle tool calls first and treat content as preamble.
    """

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LLMService:
    """Async wrapper over OpenAI / Anthropic chat completions with tool use.

    The concrete provider client can be injected for testability — pass a
    mock in unit tests to avoid network calls. In production, the client is
    created once from the global ``settings`` singleton.
    """

    def __init__(
        self,
        *,
        provider: Provider | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.provider: Provider = provider or settings.LLM_PROVIDER
        self.model: str = model or settings.LLM_MODEL
        self.max_tokens: int = settings.LLM_MAX_TOKENS
        self.temperature: float = settings.LLM_TEMPERATURE
        self._client = client or self._build_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send a conversation to the configured provider and return the reply.

        Args:
            messages: OpenAI-formatted message list (system + user + tool
                turns mixed). The first message may be ``role="system"``.
            tools: Optional list of OpenAI function-calling schemas (what
                ``tools/registry.get_openai_tools_schema()`` returns). Pass
                ``None`` or ``[]`` when tool use is not desired this turn.

        Returns:
            LLMResponse with either content or tool_calls populated.

        Raises:
            LLMProviderError: the provider returned an error, malformed
                payload, or the LLM emitted non-JSON tool arguments.
        """
        try:
            if self.provider == "openai":
                return await self._chat_openai(messages, tools)
            if self.provider == "anthropic":
                return await self._chat_anthropic(messages, tools)
            raise LLMProviderError(f"Unsupported provider: {self.provider!r}")
        except LLMProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap any SDK error
            logger.exception("LLM provider call failed")
            raise LLMProviderError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _build_client(self) -> Any:
        if self.provider == "openai":
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        if self.provider == "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise LLMProviderError(
                    "ANTHROPIC_API_KEY is required when LLM_PROVIDER='anthropic'."
                )
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        raise LLMProviderError(f"Unsupported provider: {self.provider!r}")

    # ------------------------------------------------------------------
    # OpenAI path
    # ------------------------------------------------------------------

    async def _chat_openai(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> LLMResponse:
        # Newer OpenAI model families (GPT-5.x, o-series, reasoning models)
        # renamed ``max_tokens`` to ``max_completion_tokens`` and reject the
        # old parameter outright. Use the new name unconditionally — it's
        # accepted by 4o / 4.1 / 5.x alike.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
        }
        # Most GPT-5 / o-series models only accept the default temperature
        # (1.0) and error out on anything else. Send the user's temperature
        # only for model families that we know support it.
        if _openai_supports_custom_temperature(self.model):
            kwargs["temperature"] = self.temperature

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            # Serialize tool calls: one at a time is easier for the bot loop
            # to reason about and debug. If a workload needs parallelism we
            # can flip this via settings later.
            kwargs["parallel_tool_calls"] = False

        completion = await self._client.chat.completions.create(**kwargs)

        choice = completion.choices[0]
        message = choice.message
        usage = getattr(completion, "usage", None)

        tool_calls: list[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                raise LLMProviderError(
                    f"LLM emitted non-JSON arguments for tool {tc.function.name!r}: "
                    f"{raw_args[:200]}"
                ) from exc
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=args)
            )

        response = LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            model=getattr(completion, "model", self.model),
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        _log_usage("openai", response)
        return response

    # ------------------------------------------------------------------
    # Anthropic path
    # ------------------------------------------------------------------

    async def _chat_anthropic(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> LLMResponse:
        system_prompt, converted = _split_system_and_convert_for_anthropic(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": converted,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [_openai_tool_to_anthropic(t) for t in tools]

        response = await self._client.messages.create(**kwargs)

        content_text: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                content_text.append(block.text)
            elif btype == "tool_use":
                # Anthropic already delivers input as a dict — no JSON parse needed.
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input or {}),
                    )
                )

        usage = getattr(response, "usage", None)
        llm_response = LLMResponse(
            content="\n".join(content_text) if content_text else None,
            tool_calls=tool_calls,
            finish_reason=getattr(response, "stop_reason", None),
            model=getattr(response, "model", self.model),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
        _log_usage("anthropic", llm_response)
        return llm_response


# ---------------------------------------------------------------------------
# Model capability probes
# ---------------------------------------------------------------------------

# Model families that reject non-default ``temperature``. The check is
# conservative by design — an unknown model is assumed to support
# temperature (the API will tell us otherwise).
_NO_TEMPERATURE_PREFIXES: tuple[str, ...] = (
    "gpt-5",
    "o1",
    "o3",
    "o4",
)


def _openai_supports_custom_temperature(model: str) -> bool:
    """Return False for OpenAI families known to reject custom temperature."""
    name = model.lower()
    return not any(name.startswith(p) for p in _NO_TEMPERATURE_PREFIXES)


# ---------------------------------------------------------------------------
# Schema / message conversion helpers
# ---------------------------------------------------------------------------

def _openai_tool_to_anthropic(tool: dict) -> dict:
    """Translate one OpenAI function-call schema into Anthropic's format.

    OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
    Anthropic: {"name", "description", "input_schema"}
    """
    fn = tool.get("function", tool)
    return {
        "name": fn["name"],
        "description": fn.get("description", ""),
        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
    }


def _split_system_and_convert_for_anthropic(
    messages: list[dict],
) -> tuple[str | None, list[dict]]:
    """Extract the system prompt and convert the rest for Anthropic.

    Returns ``(system_prompt, converted_messages)`` where ``converted_messages``
    uses Anthropic's content-block format.
    """
    system_prompt: str | None = None
    out: list[dict] = []

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_prompt = _accumulate_system(system_prompt, msg.get("content"))
        elif role == "tool":
            out.append(_tool_result_turn(msg))
        elif role == "assistant":
            out.append(_assistant_turn(msg))
        else:
            out.append({"role": role or "user", "content": msg.get("content")})

    return system_prompt, out


def _accumulate_system(current: str | None, new_content: Any) -> str | None:
    """Join consecutive system messages with a blank line."""
    if not new_content:
        return current
    return new_content if current is None else f"{current}\n\n{new_content}"


def _tool_result_turn(msg: dict) -> dict:
    """Rewrite an OpenAI tool-role message as an Anthropic user turn.

    Anthropic expects tool results as a user message whose content is a
    single ``tool_result`` block referencing the original ``tool_use_id``.
    """
    content = msg.get("content")
    payload = content if isinstance(content, str) else json.dumps(content)
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": payload,
            }
        ],
    }


def _assistant_turn(msg: dict) -> dict:
    """Convert an OpenAI assistant message (text + tool_calls) to Anthropic blocks."""
    blocks: list[dict] = []
    if msg.get("content"):
        blocks.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        blocks.append(_tool_use_block(tc))
    if not blocks:
        blocks = [{"type": "text", "text": ""}]
    return {"role": "assistant", "content": blocks}


def _tool_use_block(tool_call: dict) -> dict:
    """Build one Anthropic ``tool_use`` block from an OpenAI tool_call dict."""
    fn = tool_call.get("function", {})
    raw_args = fn.get("arguments") or "{}"
    if isinstance(raw_args, dict):
        parsed = raw_args
    else:
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = {}
    return {
        "type": "tool_use",
        "id": tool_call.get("id", ""),
        "name": fn.get("name", ""),
        "input": parsed,
    }


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_usage(provider: str, response: LLMResponse) -> None:
    logger.info(
        "llm_call provider=%s model=%s in_tokens=%d out_tokens=%d "
        "finish=%s tools=%s",
        provider,
        response.model,
        response.input_tokens,
        response.output_tokens,
        response.finish_reason,
        [tc.name for tc in response.tool_calls] or None,
    )
