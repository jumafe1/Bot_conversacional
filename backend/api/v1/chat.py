"""
Chat endpoint — the primary interface for the conversational bot.

POST /api/v1/chat
    Body: ChatRequest  (session_id, user_message)
    Response: ChatResponse  (assistant_message, suggestions, tool_calls_used)

TODO:
    1. Inject bot_service (via FastAPI dependency injection or direct import).
    2. Call bot_service.process_message(session_id, user_message).
    3. Return the structured ChatResponse.
    4. Handle RappiBotError subclasses with appropriate HTTP status codes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.core.exceptions import DataNotFoundError, InvalidQueryError, LLMProviderError
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.services.bot_service import BotService

router = APIRouter()
logger = logging.getLogger(__name__)

_bot_service = BotService()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a user message and return the bot's response.

    TODO: implement once BotService.process_message is ready.
    """
    try:
        return await _bot_service.process_message(
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
