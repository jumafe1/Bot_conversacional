"""
Health check endpoint.

GET /api/v1/health → 200 OK with basic status information.
Used by load balancers and monitoring systems.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health status."""
    return HealthResponse(status="ok", version="0.1.0")
