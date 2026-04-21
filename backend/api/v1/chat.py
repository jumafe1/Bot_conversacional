"""
Chat endpoint — the primary interface for the conversational bot.

POST /api/v1/chat
    Body: ChatRequest   (session_id, message)
    Response: ChatResponse  (answer, suggestions, tool_calls_used, session_id)

The concrete ``BotService`` is wired via a FastAPI dependency so tests can
override it with a lightweight stub (``app.dependency_overrides[...]``) and
never touch a real LLM.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.core.exceptions import (
    DataNotFoundError,
    InvalidQueryError,
    LLMProviderError,
)
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.services.bot_service import BotService

router = APIRouter()
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_bot_service() -> BotService:
    """Return the process-wide singleton BotService.

    ``lru_cache`` guarantees the heavy initialisation (system prompt build,
    LLM client creation) happens exactly once per process. In tests, override
    this dependency via ``app.dependency_overrides[get_bot_service]``.
    """
    return BotService()


BotDep = Annotated[BotService, Depends(get_bot_service)]

# Status codes this endpoint can return in addition to 200. FastAPI uses this
# to enrich the OpenAPI schema so clients know what to expect.
_ERROR_RESPONSES: dict[int | str, dict] = {
    404: {"description": "Requested data does not exist in the dataset."},
    422: {"description": "Request body failed validation."},
    500: {"description": "Unexpected internal error."},
    502: {"description": "Upstream LLM provider is unavailable or failed."},
}


@router.post("/chat", responses=_ERROR_RESPONSES)
async def chat(request: ChatRequest, bot: BotDep) -> ChatResponse:
    """Process one user message and return the bot's structured answer."""
    try:
        return await bot.process_message(
            session_id=request.session_id,
            user_message=request.message,
        )
    except DataNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMProviderError as exc:
        logger.error("LLM provider error", exc_info=exc)
        raise HTTPException(status_code=502, detail="LLM provider unavailable") from exc
    except Exception as exc:
        logger.error("Unexpected error in chat endpoint", exc_info=exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
