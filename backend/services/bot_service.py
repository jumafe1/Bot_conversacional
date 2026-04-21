"""
Bot orchestration service.

Drives the LLM ↔ tool loop for a single user turn:
  1. Retrieve conversation history from memory_service.
  2. Prepend system prompt.
  3. Call llm_service with the full message list and tools registry.
  4. If the LLM returns tool_call(s): execute them, append results, loop.
  5. When the LLM returns a final text response: extract answer + suggestions.
  6. Persist both the user turn and assistant turn to memory_service.
  7. Return a ChatResponse.

Exposes:
    BotService.process_message(session_id, user_message) -> ChatResponse
"""

from __future__ import annotations

import logging

from backend.schemas.chat import ChatResponse

logger = logging.getLogger(__name__)


class BotService:
    """Orchestrates a single conversational turn end-to-end.

    TODO:
        - Inject LLMService and MemoryService (constructor or DI).
        - Implement the tool-use loop (see module docstring step 1–7).
        - Parse the LLM's final response to extract "suggestions" block.
        - Track which tool names were called and include in ChatResponse.
    """

    def __init__(self) -> None:
        # TODO: initialize llm_service, memory_service, tools registry
        pass

    async def process_message(self, session_id: str, user_message: str) -> ChatResponse:
        """Process one user message and return the bot's full response.

        TODO: implement the LLM ↔ tool loop described in the module docstring.
        """
        raise NotImplementedError
