"""
Structured logging configuration.

Call configure_logging() once at application startup (done in main.py).
After that, use stdlib logging as normal — structlog or the stdlib handler
will format output as structured JSON when LOG_LEVEL is INFO or above.

TODO:
    - Configure structlog processors (add timestamp, level, caller info).
    - Set output format: JSON in production, human-readable in development.
    - Optionally integrate with an external sink (DataDog, CloudWatch, etc.).
"""

from __future__ import annotations

import logging


def configure_logging() -> None:
    """Apply logging configuration for the entire application.

    TODO: replace with structlog.configure() for structured JSON output.
    """
    from backend.core.config import settings

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
