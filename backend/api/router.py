"""
Main API router — aggregates all versioned sub-routers.

Import `api_router` and include it in the FastAPI app:

    app.include_router(api_router, prefix="/api/v1")
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.v1 import chat, health

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, tags=["chat"])
