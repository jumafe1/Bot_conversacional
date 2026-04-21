"""
DuckDB connection wrapper.

Manages a single in-process DuckDB connection and registers
the processed parquet files as SQL views on startup.

Views registered:
    metrics  → data/processed/metrics.parquet
    orders   → data/processed/orders.parquet
    summary  → data/processed/summary.parquet

Exposes:
    get_connection() -> duckdb.DuckDBPyConnection
    initialize()     -> None  (call once at startup)

TODO:
    1. Implement initialize(): open DuckDB connection, register parquet views.
    2. Validate that each parquet file exists before registering; raise
       DataNotFoundError with a helpful message if not.
    3. Implement get_connection(): return the module-level connection instance.
    4. Consider thread-safety: DuckDB connections are not thread-safe by default.
       Either use connection-per-request or a connection pool.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.core.config import settings
from backend.core.exceptions import DataNotFoundError

logger = logging.getLogger(__name__)

_connection = None  # module-level singleton


PARQUET_VIEWS: dict[str, str] = {
    "metrics": "metrics.parquet",
    "orders": "orders.parquet",
    "summary": "summary.parquet",
}


def initialize() -> None:
    """Open DuckDB and register parquet files as views.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError


def get_connection():
    """Return the active DuckDB connection.

    TODO: raise RuntimeError if initialize() has not been called.
    """
    raise NotImplementedError
