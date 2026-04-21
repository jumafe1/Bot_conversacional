"""
Metrics repository — all SQL queries against DuckDB.

Each method corresponds to the data need of one or more tools.
Returns pandas DataFrames; tools serialize them to list[dict].

Exposes:
    MetricsRepository.get_zones_by_metric_filter(...)      -> pd.DataFrame
    MetricsRepository.get_metric_by_group(...)             -> pd.DataFrame
    MetricsRepository.get_metric_trend(...)                -> pd.DataFrame
    MetricsRepository.get_metric_aggregation(...)          -> pd.DataFrame
    MetricsRepository.get_zones_multivariate(...)          -> pd.DataFrame
    MetricsRepository.get_orders_with_growth(...)          -> pd.DataFrame

IMPORTANT — SQL safety:
    All user-influenced values (thresholds, dates) MUST be passed as
    DuckDB parameters, never interpolated into query strings.
    Column/table names (metric names, group_by fields) must be validated
    against an allowlist before use.

TODO:
    1. Implement each method using database.get_connection().execute(sql, params).
    2. Align column names in SQL with actual parquet schema (finalized after clean_data.py).
    3. Add column allowlists for metric names and group_by dimensions.
    4. Return pd.DataFrame from cursor.df() or equivalent.
"""

from __future__ import annotations

import logging

import pandas as pd

from backend.repositories.database import get_connection

logger = logging.getLogger(__name__)

ALLOWED_METRICS: set[str] = {
    "pct_pro_users_breakeven",
    "pct_restaurants_sessions_optimal_assortment",
    "gross_profit_ue",
    "lead_penetration",
    "mltv_top_verticals_adoption",
    "non_pro_ptc_op",
    "perfect_orders",
    "pro_adoption",
    "restaurants_markdowns_gmv",
    "restaurants_ss_atc_cvr",
    "restaurants_sst_ss_cvr",
    "retail_sst_ss_cvr",
    "turbo_adoption",
}

ALLOWED_GROUP_BY: set[str] = {"country", "zone_type", "city", "zone_id"}
ALLOWED_AGG_FUNCS: set[str] = {"avg", "min", "max", "sum", "count"}


class MetricsRepository:
    """DuckDB-backed repository for all analytical metric queries."""

    def get_zones_by_metric_filter(
        self,
        metric: str,
        operator: str,
        threshold: float,
        country: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        """Return zones where metric satisfies the threshold condition.

        TODO: implement SQL query with parameterized threshold.
        """
        raise NotImplementedError

    def get_metric_by_group(
        self,
        metric: str,
        group_by: str,
        period: str | None = None,
    ) -> pd.DataFrame:
        """Return avg/min/max of a metric grouped by a dimension.

        TODO: validate group_by in ALLOWED_GROUP_BY before use in SQL.
        """
        raise NotImplementedError

    def get_metric_trend(
        self,
        metric: str,
        zone_id: str | None = None,
        country: str | None = None,
        start_period: str | None = None,
        end_period: str | None = None,
    ) -> pd.DataFrame:
        """Return time-series of a metric sorted by period ascending.

        TODO: implement date range filtering with parameterized SQL.
        """
        raise NotImplementedError

    def get_metric_aggregation(
        self,
        metric: str,
        agg_func: str,
        group_by: str,
        top_n: int | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        """Return aggregated metric per group, optionally limited to top_n.

        TODO: validate agg_func in ALLOWED_AGG_FUNCS.
        """
        raise NotImplementedError

    def get_zones_multivariate(
        self,
        conditions: list[dict],
        country: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        """Return zones satisfying all conditions simultaneously (AND logic).

        TODO: build compound query; validate each metric in ALLOWED_METRICS.
        """
        raise NotImplementedError

    def get_orders_with_growth(
        self,
        country: str | None = None,
        zone_id: str | None = None,
        period: str | None = None,
        growth_type: str = "absolute",
    ) -> pd.DataFrame:
        """Return orders per period with optional growth rate calculation.

        TODO: use LAG() window function for MoM/YoY growth.
        """
        raise NotImplementedError
