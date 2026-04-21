"""
Custom exception hierarchy for the Rappi bot.

Raising domain-specific exceptions lets the API layer return
meaningful HTTP status codes without coupling business logic to HTTP.

Hierarchy:
    RappiBotError              (base)
    ├── DataNotFoundError      (404)
    ├── InvalidQueryError      (422)
    └── LLMProviderError       (502)

Note: tool-handler failures are intentionally NOT exceptions. ``dispatch``
in ``backend.tools.registry`` converts any handler error into a structured
response (``metadata.error = True``) so the LLM can self-correct instead of
crashing the turn.
"""

from __future__ import annotations


class RappiBotError(Exception):
    """Base exception for all application errors."""


class DataNotFoundError(RappiBotError):
    """Raised when a requested zone, country, or metric does not exist in the data."""


class InvalidQueryError(RappiBotError):
    """Raised when the user's request cannot be translated to a valid tool call."""


class LLMProviderError(RappiBotError):
    """Raised when the LLM API returns an error or unexpected response."""
