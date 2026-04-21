"""
Provider-agnostic LLM service.

Abstracts over OpenAI and Anthropic so the rest of the app never
imports the provider SDK directly. Switching providers is a
single env-var change (LLM_PROVIDER).

Exposes:
    LLMService.chat(messages, tools) -> LLMResponse
    LLMResponse                      (dataclass wrapping the provider response)

TODO:
    1. Implement _chat_openai() using the openai SDK:
       - Use client.chat.completions.create() with tools=tools parameter.
       - Parse response.choices[0].message for content and tool_calls.
    2. Implement _chat_anthropic() using the anthropic SDK:
       - Use client.messages.create() with tools=tools parameter.
       - Map Anthropic's tool_use blocks to the same LLMResponse shape.
    3. Dispatch to the correct implementation based on settings.LLM_PROVIDER.
    4. Wrap all provider errors in LLMProviderError.
    5. Log token usage (prompt_tokens, completion_tokens) for cost tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a single tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: str | None                     # final text, None if tool calls present
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class LLMService:
    """Provider-agnostic wrapper for LLM chat completions with tool use.

    TODO: implement as described in the module docstring.
    """

    def __init__(self) -> None:
        # TODO: instantiate openai.OpenAI() or anthropic.Anthropic() based on settings
        pass

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and return a normalized response.

        Args:
            messages: Full conversation history in OpenAI message format.
            tools: List of tool schemas in OpenAI function-calling format.

        Returns:
            LLMResponse with either content or tool_calls populated.

        TODO: dispatch to _chat_openai or _chat_anthropic based on settings.
        """
        raise NotImplementedError
