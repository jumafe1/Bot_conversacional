"""
FastAPI application entry point.

Wires together middleware, routers, and lifecycle events.
Run directly with:  uvicorn backend.main:app --reload
Or via Makefile:    make run
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.router import api_router
from backend.core.config import settings
from backend.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Rappi Conversational Data Bot",
    description=(
        "Natural-language interface for querying operational metrics "
        "across Rappi's 9 LATAM markets."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize DuckDB and register parquet views."""
    from backend.repositories.database import db

    db.connect()
    logger.info(
        "Rappi Bot API started",
        extra={"provider": settings.LLM_PROVIDER, "model": settings.LLM_MODEL},
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Close DuckDB connection gracefully."""
    from backend.repositories.database import db

    db.close()
    logger.info("Rappi Bot API shut down")


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
