"""
DuckDB connection manager.

Uses an in-memory DuckDB instance with views pointing to the processed parquet
files. The views let queries use clean table names (metrics_wide, metrics_long,
orders_wide, orders_long) instead of file paths.

Exposes a module-level `db` singleton:
    from backend.repositories.database import db
    df = db.execute("SELECT * FROM metrics_wide WHERE COUNTRY = ?", ["CO"]).fetchdf()
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from backend.core.config import settings

logger = logging.getLogger(__name__)


class Database:
    """DuckDB in-memory connection with parquet-backed views."""

    _VIEW_DEFINITIONS: dict[str, str] = {
        "metrics_wide": "metrics_wide.parquet",
        "metrics_long": "metrics_long.parquet",
        "orders_wide":  "orders_wide.parquet",
        "orders_long":  "orders_long.parquet",
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or settings.DATA_DIR
        self._conn: duckdb.DuckDBPyConnection | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the connection and register all parquet views. Idempotent."""
        if self._conn is not None:
            return
        logger.info("Opening DuckDB in-memory connection")
        self._conn = duckdb.connect(":memory:")
        try:
            self._register_views()
        except Exception:
            # Reset so the next call to execute() retries connect()
            self._conn.close()
            self._conn = None
            raise

    def execute(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyConnection:
        """Execute a parameterized SQL query.

        Lazy-connects on first call so tests and scripts don't need explicit
        connect() calls.

        Returns the DuckDB connection (supports .fetchdf(), .fetchall(), .fetchone()).
        """
        if self._conn is None:
            self.connect()
        logger.debug("SQL: %s | params: %s", sql.strip()[:200], params)
        return self._conn.execute(sql, params or [])  # type: ignore[union-attr]

    def close(self) -> None:
        """Close the connection and reset state."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("DuckDB connection closed")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _register_views(self) -> None:
        """Register one SQL view per processed parquet.

        The path is interpolated directly (not via ? param) because DuckDB
        does not support prepared parameters in CREATE VIEW statements.
        The path comes from settings (our code, not user input) so this is safe.
        """
        assert self._conn is not None
        for view_name, filename in self._VIEW_DEFINITIONS.items():
            path = self._data_dir / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Parquet file not found: {path}. "
                    "Run `python scripts/clean_data.py` (or `make clean-data`) first."
                )
            # Resolve to absolute path; escape single quotes for SQL safety.
            path_sql = str(path.resolve()).replace("'", "''")
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS "
                f"SELECT * FROM read_parquet('{path_sql}')"
            )
            logger.info("Registered view '%s' → %s", view_name, path.name)


# Module-level singleton — import this everywhere
db = Database()
