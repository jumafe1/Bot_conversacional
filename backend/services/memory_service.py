"""
Conversational memory service.

Stores and retrieves per-session message history so the LLM has
context across multiple turns of a conversation.

Current implementation: in-process Python dict (no persistence).
Sessions are lost on server restart. For production, swap the storage
backend to Redis or a database without changing the interface.

Exposes:
    MemoryService.get_history(session_id)         -> list[dict]
    MemoryService.append(session_id, role, content)
    MemoryService.clear(session_id)

TODO:
    1. Implement get_history — return messages list for a session.
    2. Implement append — add a message dict {role, content} to the session.
    3. Implement clear — reset a session's history.
    4. Add a max_turns parameter: truncate oldest messages when history exceeds it
       to prevent unbounded context growth and runaway token costs.
    5. (Future) Replace the dict store with Redis for multi-process/multi-instance support.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# session_id -> list of message dicts {role: str, content: str}
_store: dict[str, list[dict]] = defaultdict(list)

MAX_HISTORY_TURNS = 20  # TODO: make configurable via settings


class MemoryService:
    """In-process conversation history store.

    TODO: implement methods described in the module docstring.
    """

    def get_history(self, session_id: str) -> list[dict]:
        """Return the full message history for a session.

        TODO: implement retrieval from _store, truncating to MAX_HISTORY_TURNS.
        """
        raise NotImplementedError

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append a single message to a session's history.

        TODO: add {role, content} dict to _store[session_id].
        """
        raise NotImplementedError

    def clear(self, session_id: str) -> None:
        """Clear all history for a session.

        TODO: delete _store[session_id].
        """
        raise NotImplementedError
