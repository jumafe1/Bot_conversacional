"""
Tests for MetricsRepository.

All tests use an in-memory DuckDB fixture populated with minimal test data
so they run without real parquet files.

TODO (implement once repository methods are ready):
    - test_get_zones_filter_returns_dataframe: result is a pd.DataFrame with expected columns.
    - test_get_zones_filter_threshold: only rows meeting threshold are returned.
    - test_get_metric_by_group_columns: result has group_value, avg, min, max columns.
    - test_get_metric_trend_sorted: trend results are sorted by period ascending.
    - test_get_metric_aggregation_top_n: top_n limits and sorts the result.
    - test_multivariate_and_logic: only rows matching ALL conditions are returned.
    - test_sql_injection_blocked: column name allowlist prevents injection.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="MetricsRepository not yet implemented")
def test_get_zones_filter_returns_dataframe() -> None:
    """get_zones_by_metric_filter returns a pd.DataFrame with expected columns."""
    raise NotImplementedError


@pytest.mark.skip(reason="MetricsRepository not yet implemented")
def test_multivariate_and_logic() -> None:
    """Zones returned satisfy ALL conditions simultaneously."""
    raise NotImplementedError


@pytest.mark.skip(reason="MetricsRepository not yet implemented")
def test_sql_injection_blocked() -> None:
    """Passing an invalid column name raises ValueError before hitting DuckDB."""
    raise NotImplementedError
