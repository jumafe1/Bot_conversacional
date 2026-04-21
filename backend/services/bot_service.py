"""
Bot orchestration service.

Drives the LLM ↔ tool loop for a single user turn:

    1. Retrieve conversation history from MemoryService.
    2. Prepend the system prompt and append the new user message.
    3. Call LLMService with the full message list + tool schemas.
    4. If the LLM returns tool_calls: dispatch each, append assistant +
       tool messages, loop (up to MAX_TOOL_ITERATIONS).
    5. When the LLM returns a final text response, extract the
       "Suggested next analyses" block and return a ChatResponse.
    6. Persist the user + final assistant turns to memory.

Design choices:
    - Memory stores ONLY user-visible turns. Tool calls and tool results
      are ephemeral — they only exist in the messages list during the loop.
      This keeps memory cheap and readable and prevents tool-result JSON
      from polluting future prompts.
    - The loop has a hard iteration cap to bound cost and latency when the
      LLM gets stuck calling tools in circles.
    - Tool-call argument parse errors are reported back to the LLM as a
      structured "tool" message so it can self-correct on the next turn.
    - Suggestion extraction is permissive: it accepts both the Spanish and
      English labels with or without markdown decoration.
"""

from __future__ import annotations

import json
import logging
import re

from backend.prompts.system_prompt import build_system_prompt
from backend.schemas.chat import ChatResponse
from backend.services.llm_service import LLMResponse, LLMService, ToolCall
from backend.services.memory_service import MemoryService
from backend.tools.registry import dispatch, get_openai_tools_schema

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

_FALLBACK_MESSAGE = (
    "No logré completar el análisis en el presupuesto de llamadas a herramientas. "
    "Por favor formulá la pregunta de forma más específica (por ejemplo, acotando "
    "país, métrica o período)."
)

# Label of the suggestions block in Spanish / English, with or without
# markdown decoration around it.
_SUGGESTIONS_LABEL = (
    r"\*{0,2}\s*"
    r"(?:An[aá]lisis\s+sugerid[oa]s?|Suggested\s+(?:next\s+)?analyses)"
    r"\s*:\s*\*{0,2}"
)

# Match the label followed by its body (up to the next heading or EOF).
_SUGGESTIONS_PATTERN = re.compile(
    rf"{_SUGGESTIONS_LABEL}\s*(.+?)(?=\n\s*#{{1,6}}\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Bullet / numbered list item — captures the text after the marker.
_BULLET_PATTERN = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$",
    re.MULTILINE,
)


class BotService:
    """Orchestrates a single conversational turn end-to-end."""

    def __init__(
        self,
        *,
        llm: LLMService | None = None,
        memory: MemoryService | None = None,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self.llm = llm or LLMService()
        self.memory = memory or MemoryService()
        self.max_iterations = max_iterations
        self._tools_schema = get_openai_tools_schema()
        self._system_prompt = build_system_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_message(
        self, session_id: str, user_message: str
    ) -> ChatResponse:
        """Handle one user turn and return the bot's structured reply.

        Raises:
            LLMProviderError: the provider failed past its internal retries.
                The API layer maps this to HTTP 502.
        """
        history = self.memory.get_history(session_id)
        messages = self._build_messages(history, user_message)

        final_response, tools_used = await self._run_tool_loop(messages)

        answer_text = final_response.content or _FALLBACK_MESSAGE
        clean_answer, suggestions = _split_answer_and_suggestions(answer_text)

        # Persist user + final assistant turns only.
        self.memory.append(session_id, "user", user_message)
        self.memory.append(session_id, "assistant", clean_answer)

        logger.info(
            "bot_turn session_id=%s tools=%s iterations=%d in_tokens~=%d out_tokens~=%d",
            session_id,
            tools_used,
            len(tools_used),
            final_response.input_tokens,
            final_response.output_tokens,
        )

        return ChatResponse(
            session_id=session_id,
            answer=clean_answer,
            suggestions=suggestions,
            tool_calls_used=tools_used,
        )

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    def _build_messages(
        self, history: list[dict], user_message: str
    ) -> list[dict]:
        """Compose system prompt + prior turns + the new user message."""
        return [
            {"role": "system", "content": self._system_prompt},
            *history,
            {"role": "user", "content": user_message},
        ]

    async def _run_tool_loop(
        self, messages: list[dict]
    ) -> tuple[LLMResponse, list[str]]:
        """Run the LLM ↔ tool exchange until we get a text answer.

        Returns the final ``LLMResponse`` plus the ordered list of tool
        names that were dispatched during the loop.
        """
        tools_used: list[str] = []

        for iteration in range(self.max_iterations):
            # LLMProviderError propagates — the API layer maps it to HTTP 502.
            response = await self.llm.chat(messages, tools=self._tools_schema)

            if not response.tool_calls:
                return response, tools_used

            # Record the assistant turn (with its tool_calls) in the transcript
            # so the LLM sees the same state on its next call.
            messages.append(_assistant_tool_call_message(response))

            for tc in response.tool_calls:
                tools_used.append(tc.name)
                tool_result = _execute_tool(tc)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result, default=str),
                    }
                )
            logger.debug(
                "bot_tool_loop iter=%d dispatched=%s",
                iteration,
                [tc.name for tc in response.tool_calls],
            )

        # Budget exhausted — ask the LLM one last time WITHOUT tools so it
        # has to produce a text summary of what it already found.
        logger.warning(
            "bot_tool_loop budget exhausted after %d iterations; forcing text reply",
            self.max_iterations,
        )
        final = await self.llm.chat(messages, tools=None)
        return final, tools_used


# ---------------------------------------------------------------------------
# Pure helpers — stateless, unit-testable in isolation
# ---------------------------------------------------------------------------

def _execute_tool(tc: ToolCall) -> dict:
    """Dispatch a single tool call, capturing internal failures as tool errors.

    ``dispatch`` already wraps handler exceptions, but we add an outer guard
    so that unexpected failures at the registry layer are still delivered
    to the LLM as structured data rather than surfacing as 500s.
    """
    try:
        return dispatch(tc.name, tc.arguments)
    except Exception as exc:  # noqa: BLE001 — belt + suspenders
        logger.exception("Unexpected failure dispatching tool %s", tc.name)
        return {
            "summary": f"Tool '{tc.name}' failed unexpectedly: {exc}",
            "data": [],
            "metadata": {
                "error": True,
                "reason": str(exc),
                "total_count": 0,
                "truncated": False,
            },
        }


def _assistant_tool_call_message(response: LLMResponse) -> dict:
    """Format an LLMResponse with tool_calls as an OpenAI-style assistant message.

    This is the message shape the next ``llm.chat()`` call needs to see so
    the provider can correlate tool results back to their originating call.
    """
    return {
        "role": "assistant",
        "content": response.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in response.tool_calls
        ],
    }


def _split_answer_and_suggestions(text: str) -> tuple[str, list[str]]:
    """Separate the assistant answer from its trailing suggestions block.

    Returns ``(cleaned_answer, suggestions)``. If no recognisable
    suggestions block is found, returns the original text and an empty list.
    The answer still contains all data / prose — only the suggestion block
    is peeled off so it doesn't appear twice in the response.
    """
    match = _SUGGESTIONS_PATTERN.search(text)
    if not match:
        return text.strip(), []

    block = match.group(1).strip()
    suggestions = _extract_bullets(block)

    cleaned = (text[: match.start()] + text[match.end():]).rstrip()
    return cleaned, suggestions


def _extract_bullets(block: str) -> list[str]:
    """Pull each bullet / numbered line into a clean suggestion string."""
    bullets = [b.strip() for b in _BULLET_PATTERN.findall(block) if b.strip()]
    if bullets:
        return bullets[:5]  # hard cap against runaway lists

    # Fallback: no bullet markers — treat non-empty lines as suggestions.
    lines = [ln.strip(" -*•\t") for ln in block.splitlines() if ln.strip()]
    return [ln for ln in lines if ln][:5]


# Exported for unit-testing the pure helpers without constructing a service.
__all__ = [
    "BotService",
    "_split_answer_and_suggestions",
    "_assistant_tool_call_message",
]
