"""
Conversational memory service.

Stores per-session message history so the LLM has context across turns.

Current implementation: in-process Python dict. Sessions are lost on server
restart. The interface is intentionally narrow so a Redis or database-backed
implementation can be swapped in without touching callers.

Only **user-visible** turns are persisted — never the intermediate tool
calls / tool results of a single user turn. That keeps the history readable
and token-cheap: the LLM re-derives tool calls every turn from the system
prompt, not from past exchanges.

Exposed API:
    MemoryService().get_history(session_id)        -> list[dict]
    MemoryService().append(session_id, role, content)
    MemoryService().clear(session_id)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Literal

logger = logging.getLogger(__name__)

Role = Literal["user", "assistant"]

MAX_HISTORY_MESSAGES = 20  # sliding window; oldest drops out


class MemoryService:
    """In-process conversation history store.

    The backing dict is an instance attribute (not module-level) so test
    instances are isolated from each other and from production singletons.
    """

    def __init__(self, *, max_messages: int = MAX_HISTORY_MESSAGES) -> None:
        self._store: dict[str, list[dict]] = defaultdict(list)
        self._max_messages = max_messages

    def get_history(self, session_id: str) -> list[dict]:
        """Return a shallow copy of the session's message history.

        The copy prevents callers from mutating the store in place (e.g. by
        extending the list during the tool-use loop, which would leak
        intermediate reasoning into the persisted memory).
        """
        return list(self._store.get(session_id, []))

    def append(self, session_id: str, role: Role, content: str) -> None:
        """Append a single user-visible message to the session history.

        Only ``user`` and ``assistant`` roles are accepted; tool turns are
        scoped to a single LLM loop and must not live in memory.
        """
        if role not in ("user", "assistant"):
            raise ValueError(
                f"MemoryService only stores user/assistant turns, got {role!r}."
            )
        history = self._store[session_id]
        history.append({"role": role, "content": content})
        # Trim oldest messages beyond the window — cheap bounded memory.
        if len(history) > self._max_messages:
            drop = len(history) - self._max_messages
            del history[:drop]

    def clear(self, session_id: str) -> None:
        """Drop all history for a session."""
        self._store.pop(session_id, None)
