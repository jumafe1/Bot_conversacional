"""
Shared pytest fixtures for the test suite.

TODO:
    1. Add a DuckDB fixture that creates an in-memory database
       and populates it with minimal test data (a few rows per table).
       This avoids reading from real parquet files in unit tests.
    2. Add an httpx AsyncClient fixture for API integration tests.
    3. Add a mock LLM fixture that returns deterministic responses
       without calling the real OpenAI/Anthropic API.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_zone_rows() -> list[dict]:
    """Minimal zone metric rows for tool tests.

    TODO: expand with representative data covering edge cases.
    """
    return [
        {
            "zone_id": "CO-BOG-001",
            "zone_name": "Chapinero",
            "country": "CO",
            "metric_name": "perfect_orders",
            "metric_value": 0.72,
            "period": "2024-03",
        },
        {
            "zone_id": "MX-CDMX-001",
            "zone_name": "Polanco",
            "country": "MX",
            "metric_name": "perfect_orders",
            "metric_value": 0.88,
            "period": "2024-03",
        },
    ]
