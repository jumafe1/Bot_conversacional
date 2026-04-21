"""
High-level data access for zone metrics and orders.

All methods return pandas DataFrames ready for serialization. Tools consume
this repository; they never write SQL directly.

Week semantics (relative offsets, no real dates in the data):
    L0W_ROLL = most recent week  (week_number = 0 in metrics_long)
    L1W_ROLL = 1 week ago        (week_number = 1)
    ...
    L8W_ROLL = 8 weeks ago       (week_number = 8)

SQL safety rules (enforced here):
    - Dynamic identifiers (column names, SQL keywords) come only from
      internal whitelists — never from user input.
    - All user-supplied values (strings, numbers) are passed as ? params.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Literal

import pandas as pd

from backend.prompts.metric_dictionary import METRIC_DICTIONARY
from backend.repositories.database import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelists — only these values may be interpolated into SQL identifiers
# ---------------------------------------------------------------------------

VALID_WEEK_COLS = frozenset({
    "L0W_ROLL", "L1W_ROLL", "L2W_ROLL", "L3W_ROLL",
    "L4W_ROLL", "L5W_ROLL", "L6W_ROLL", "L7W_ROLL", "L8W_ROLL",
})
VALID_COUNTRIES = frozenset({"AR", "BR", "CL", "CO", "CR", "EC", "MX", "PE", "UY"})
VALID_ZONE_TYPES = frozenset({"Wealthy", "Non Wealthy"})
VALID_ZONE_PRIORITIZATIONS = frozenset({"High Priority", "Prioritized", "Not Prioritized"})
VALID_METRICS = frozenset(METRIC_DICTIONARY.keys())

_GROUP_BY_COL_MAP: dict[str, str] = {
    "country":             "COUNTRY",
    "city":                "CITY",
    "zone_type":           "ZONE_TYPE",
    "zone_prioritization": "ZONE_PRIORITIZATION",
}

_AGG_FUNC_MAP: dict[str, str] = {
    "mean":   "AVG",
    "median": "MEDIAN",
    "sum":    "SUM",
    "min":    "MIN",
    "max":    "MAX",
    "count":  "COUNT",
}

_OP_MAP: dict[str, str] = {
    ">": ">", ">=": ">=", "<": "<", "<=": "<=", "==": "=", "!=": "<>",
}

OrderBy = Literal["asc", "desc"]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_metric(metric: str) -> None:
    if metric not in VALID_METRICS:
        raise ValueError(
            f"Unknown metric '{metric}'. "
            f"Call list_available_filters() to see valid metric names."
        )


def _validate_week(week: str) -> None:
    if week not in VALID_WEEK_COLS:
        raise ValueError(
            f"Invalid week column '{week}'. "
            f"Must be one of {sorted(VALID_WEEK_COLS)}."
        )


def _validate_country(country: str) -> None:
    if country not in VALID_COUNTRIES:
        raise ValueError(
            f"Invalid country code '{country}'. "
            f"Must be one of {sorted(VALID_COUNTRIES)}."
        )


def _validate_zone_type(zone_type: str) -> None:
    if zone_type not in VALID_ZONE_TYPES:
        raise ValueError(
            f"Invalid zone_type '{zone_type}'. Must be one of {VALID_ZONE_TYPES}."
        )


def _validate_zone_prioritization(zone_prioritization: str) -> None:
    if zone_prioritization not in VALID_ZONE_PRIORITIZATIONS:
        raise ValueError(
            f"Invalid zone_prioritization '{zone_prioritization}'. "
            f"Must be one of {VALID_ZONE_PRIORITIZATIONS}."
        )

def _normalize_text(value: str) -> str:
    """Lowercase + strip accents to make text filters robust."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_top_zones_by_metric(
    metric: str,
    *,
    week: str = "L0W_ROLL",
    country: str | None = None,
    zone_type: str | None = None,
    zone_prioritization: str | None = None,
    limit: int = 5,
    order: OrderBy = "desc",
    exclude_outliers: bool = True,
) -> pd.DataFrame:
    """Top N zones ranked by a metric value in a given week.

    Args:
        metric: Exact metric name (e.g., "Perfect Orders").
        week: Week column, default "L0W_ROLL" (most recent).
        country: Optional 2-letter ISO code filter.
        zone_type: Optional "Wealthy" | "Non Wealthy" filter.
        zone_prioritization: Optional priority tier filter.
        limit: How many zones to return.
        order: "desc" for highest first (default), "asc" for lowest first.
        exclude_outliers: When True, drop is_scale_outlier=True rows.

    Returns:
        DataFrame with columns: country, city, zone, zone_type,
        zone_prioritization, metric, value.
        Zones with NULL in the requested week are excluded.
    """
    _validate_metric(metric)
    _validate_week(week)
    if country:
        _validate_country(country)
    if zone_type:
        _validate_zone_type(zone_type)
    if zone_prioritization:
        _validate_zone_prioritization(zone_prioritization)

    order_sql = "DESC" if order == "desc" else "ASC"
    where: list[str] = ["METRIC = ?", f"{week} IS NOT NULL"]
    params: list = [metric]

    if exclude_outliers:
        where.append("is_scale_outlier = FALSE")
    if country:
        where.append("COUNTRY = ?")
        params.append(country)
    if zone_type:
        where.append("ZONE_TYPE = ?")
        params.append(zone_type)
    if zone_prioritization:
        where.append("ZONE_PRIORITIZATION = ?")
        params.append(zone_prioritization)

    params.append(limit)

    sql = f"""
        SELECT
            COUNTRY               AS country,
            CITY                  AS city,
            ZONE                  AS zone,
            ZONE_TYPE             AS zone_type,
            ZONE_PRIORITIZATION   AS zone_prioritization,
            METRIC                AS metric,
            {week}                AS value
        FROM metrics_wide
        WHERE {" AND ".join(where)}
        ORDER BY value {order_sql}
        LIMIT ?
    """
    return db.execute(sql, params).fetchdf()


def compare_metric_across_groups(
    metric: str,
    group_by: Literal["zone_type", "zone_prioritization", "country"],
    *,
    week: str = "L0W_ROLL",
    country: str | None = None,
    exclude_outliers: bool = True,
) -> pd.DataFrame:
    """Aggregated stats for a metric broken down by a categorical dimension.

    Useful for comparisons like "Wealthy vs Non Wealthy zones in Mexico".

    Args:
        metric: Metric to aggregate.
        group_by: Dimension to group by.
        week: Week column to use.
        country: Optional country filter.
        exclude_outliers: Exclude flagged outlier rows.

    Returns:
        DataFrame with columns: group_value, count, mean, median, min, max, std.
        Sorted by mean descending.
    """
    _validate_metric(metric)
    _validate_week(week)
    if country:
        _validate_country(country)
    if group_by not in _GROUP_BY_COL_MAP:
        raise ValueError(
            f"Invalid group_by '{group_by}'. Must be one of {list(_GROUP_BY_COL_MAP)}."
        )

    col = _GROUP_BY_COL_MAP[group_by]
    where: list[str] = ["METRIC = ?", f"{week} IS NOT NULL"]
    params: list = [metric]

    if exclude_outliers:
        where.append("is_scale_outlier = FALSE")
    if country:
        where.append("COUNTRY = ?")
        params.append(country)

    sql = f"""
        SELECT
            {col}          AS group_value,
            COUNT(*)       AS count,
            AVG({week})    AS mean,
            MEDIAN({week}) AS median,
            MIN({week})    AS min,
            MAX({week})    AS max,
            STDDEV({week}) AS std
        FROM metrics_wide
        WHERE {" AND ".join(where)}
        GROUP BY {col}
        ORDER BY mean DESC
    """
    return db.execute(sql, params).fetchdf()


def get_metric_trend(
    metric: str,
    *,
    country: str | None = None,
    city: str | None = None,
    zone: str | None = None,
    num_weeks: int = 8,
) -> pd.DataFrame:
    """Temporal evolution of a metric over the last N weeks.

    Uses metrics_long for clean SQL without pivoting.

    If a specific zone is provided, returns that zone's week-by-week values.
    Otherwise, returns weekly averages across all matching zones.

    Args:
        metric: Metric to retrieve.
        country: Country filter (2-letter code).
        city: City name filter.
        zone: Zone name filter (requires country + city for uniqueness).
        num_weeks: Number of most-recent weeks to return (1–9).

    Returns:
        DataFrame sorted by week_number DESC (oldest first, i.e. 7, 6, ..., 0).
        For a specific zone: columns [week_number, week_offset, value].
        For an aggregate: columns [week_number, week_offset, value, zone_count].
        Rows with NULL value are excluded.
    """
    _validate_metric(metric)
    if country:
        _validate_country(country)
    if num_weeks < 1 or num_weeks > 9:
        raise ValueError("num_weeks must be between 1 and 9.")

    params: list = [metric, num_weeks]
    where: list[str] = ["METRIC = ?", "week_number < ?"]

    if country:
        where.append("COUNTRY = ?")
        params.append(country)
    if city:
        where.append("lower(strip_accents(CITY)) = ?")
        params.append(_normalize_text(city))

    if zone:
        where.append("lower(strip_accents(ZONE)) = ?")
        params.append(_normalize_text(zone))
        sql = f"""
            SELECT week_number, week_offset, value
            FROM metrics_long
            WHERE {" AND ".join(where)}
              AND value IS NOT NULL
            ORDER BY week_number DESC
        """
    else:
        sql = f"""
            SELECT
                week_number,
                week_offset,
                AVG(value)   AS value,
                COUNT(*)     AS zone_count
            FROM metrics_long
            WHERE {" AND ".join(where)}
              AND value IS NOT NULL
            GROUP BY week_number, week_offset
            ORDER BY week_number DESC
        """
    return db.execute(sql, params).fetchdf()


def aggregate_metric(
    metric: str,
    *,
    agg: Literal["mean", "median", "sum", "min", "max", "count"] = "mean",
    group_by: Literal["country", "city", "zone_type", "zone_prioritization"] | None = None,
    week: str = "L0W_ROLL",
    exclude_outliers: bool = True,
) -> pd.DataFrame:
    """Compute a scalar or grouped aggregate for a metric.

    Args:
        metric: Metric to aggregate.
        agg: Aggregation function.
        group_by: Dimension to group by; None returns a single global row.
        week: Week column.
        exclude_outliers: Exclude flagged outlier rows.

    Returns:
        DataFrame. No group_by → columns [value, count].
        With group_by → columns [group_value, value, count], sorted by value DESC.
    """
    _validate_metric(metric)
    _validate_week(week)
    if group_by and group_by not in _GROUP_BY_COL_MAP:
        raise ValueError(
            f"Invalid group_by '{group_by}'. Must be one of {list(_GROUP_BY_COL_MAP)}."
        )
    if agg not in _AGG_FUNC_MAP:
        raise ValueError(f"Invalid agg '{agg}'. Must be one of {list(_AGG_FUNC_MAP)}.")

    agg_func = _AGG_FUNC_MAP[agg]
    where: list[str] = ["METRIC = ?", f"{week} IS NOT NULL"]
    params: list = [metric]

    if exclude_outliers:
        where.append("is_scale_outlier = FALSE")

    where_str = " AND ".join(where)

    if group_by is None:
        sql = f"""
            SELECT {agg_func}({week}) AS value, COUNT(*) AS count
            FROM metrics_wide
            WHERE {where_str}
        """
    else:
        col = _GROUP_BY_COL_MAP[group_by]
        sql = f"""
            SELECT
                {col}            AS group_value,
                {agg_func}({week}) AS value,
                COUNT(*)         AS count
            FROM metrics_wide
            WHERE {where_str}
            GROUP BY {col}
            ORDER BY value DESC
        """
    return db.execute(sql, params).fetchdf()


def find_zones_multivariate(
    conditions: list[dict],
    *,
    week: str = "L0W_ROLL",
    country: str | None = None,
    limit: int = 20,
) -> pd.DataFrame:
    """Find zones satisfying multiple metric conditions simultaneously (AND logic).

    Each condition dict: {"metric": str, "op": str, "value": float}
    Valid ops: ">", ">=", "<", "<=", "==", "!="

    Implementation: CASE WHEN pivot + GROUP BY + HAVING.
    Zones missing any of the requested metrics are automatically excluded
    (NULL comparisons in HAVING evaluate to NULL = not matched).

    Args:
        conditions: List of filter conditions, all applied with AND.
        week: Week column to evaluate conditions on.
        country: Optional country filter.
        limit: Max zones to return.

    Returns:
        DataFrame with columns: country, city, zone, zone_type,
        zone_prioritization, plus one column per unique metric in conditions.
    """
    _validate_week(week)
    if country:
        _validate_country(country)
    if not conditions:
        raise ValueError("conditions must be a non-empty list.")

    for cond in conditions:
        _validate_metric(cond["metric"])
        if cond["op"] not in _OP_MAP:
            raise ValueError(
                f"Invalid operator '{cond['op']}'. Must be one of {list(_OP_MAP)}."
            )

    # Deduplicated ordered list of metrics for SELECT CASE expressions
    unique_metrics: list[str] = list(dict.fromkeys(c["metric"] for c in conditions))
    in_placeholders = ", ".join("?" * len(unique_metrics))

    params: list = []

    # 1. SELECT CASE WHEN params (appear first in SQL string)
    for m in unique_metrics:
        params.append(m)

    # 2. WHERE IN params
    params.extend(unique_metrics)

    # 3. Optional country param (WHERE clause)
    if country:
        params.append(country)

    # 4. HAVING params (metric name + threshold per condition)
    for cond in conditions:
        params.append(cond["metric"])
        params.append(float(cond["value"]))

    # 5. LIMIT
    params.append(limit)

    case_select = ",\n            ".join(
        f'MAX(CASE WHEN METRIC = ? THEN {week} END) AS "{m}"'
        for m in unique_metrics
    )
    having_clauses = [
        f'MAX(CASE WHEN METRIC = ? THEN {week} END) {_OP_MAP[c["op"]]} ?'
        for c in conditions
    ]
    extra_where: list[str] = [f"METRIC IN ({in_placeholders})", "is_scale_outlier = FALSE"]
    if country:
        extra_where.append("COUNTRY = ?")

    sql = f"""
        SELECT
            COUNTRY             AS country,
            CITY                AS city,
            ZONE                AS zone,
            ZONE_TYPE           AS zone_type,
            ZONE_PRIORITIZATION AS zone_prioritization,
            {case_select}
        FROM metrics_wide
        WHERE {" AND ".join(extra_where)}
        GROUP BY COUNTRY, CITY, ZONE, ZONE_TYPE, ZONE_PRIORITIZATION
        HAVING {" AND ".join(having_clauses)}
        LIMIT ?
    """
    return db.execute(sql, params).fetchdf()


def get_orders_growth(
    *,
    country: str | None = None,
    zone_type: str | None = None,
    top_n: int = 10,
    comparison_weeks: int = 5,
) -> pd.DataFrame:
    """Rank zones by order volume change between the current and a past week.

    Growth is computed as: (L0W - L{n}W) / L{n}W * 100  (percentage points).
    Zones with NULL in either week, or with zero past orders, are excluded.

    Note: orders_wide has no ZONE_TYPE column, so zone_type filter is unavailable
    and will be silently ignored if provided.

    Args:
        country: Optional country filter.
        zone_type: Ignored (column not present in orders data).
        top_n: Number of top-growing zones to return.
        comparison_weeks: Which past week to compare against (1–8).

    Returns:
        DataFrame with columns: country, city, zone, current_orders,
        past_orders, growth_pct. Sorted by growth_pct DESC.
    """
    if country:
        _validate_country(country)
    if comparison_weeks < 1 or comparison_weeks > 8:
        raise ValueError("comparison_weeks must be between 1 and 8.")
    if zone_type:
        logger.warning(
            "zone_type filter requested but orders_wide has no ZONE_TYPE column — ignoring."
        )

    past_col = f"L{comparison_weeks}W"  # safe: comparison_weeks validated as int 1-8

    where: list[str] = ["L0W IS NOT NULL", f"{past_col} IS NOT NULL", f"{past_col} > 0"]
    params: list = []

    if country:
        where.append("COUNTRY = ?")
        params.append(country)

    params.append(top_n)

    sql = f"""
        SELECT
            COUNTRY  AS country,
            CITY     AS city,
            ZONE     AS zone,
            L0W      AS current_orders,
            {past_col} AS past_orders,
            ROUND((L0W - {past_col}) / {past_col} * 100, 2) AS growth_pct
        FROM orders_wide
        WHERE {" AND ".join(where)}
        ORDER BY growth_pct DESC
        LIMIT ?
    """
    return db.execute(sql, params).fetchdf()


def list_available_filters() -> dict:
    """Return the valid values for each filter dimension.

    Queries the live parquet data, so new countries or metrics added after
    cleaning are reflected automatically.

    Returns:
        {
            "countries": [...],
            "zone_types": [...],
            "zone_prioritizations": [...],
            "metrics": [...],
        }
    """
    countries = (
        db.execute("SELECT DISTINCT COUNTRY FROM metrics_wide ORDER BY COUNTRY")
        .fetchdf()["COUNTRY"]
        .tolist()
    )
    zone_types = (
        db.execute("SELECT DISTINCT ZONE_TYPE FROM metrics_wide ORDER BY ZONE_TYPE")
        .fetchdf()["ZONE_TYPE"]
        .tolist()
    )
    zone_prioritizations = (
        db.execute(
            "SELECT DISTINCT ZONE_PRIORITIZATION FROM metrics_wide ORDER BY ZONE_PRIORITIZATION"
        )
        .fetchdf()["ZONE_PRIORITIZATION"]
        .tolist()
    )
    metrics = (
        db.execute("SELECT DISTINCT METRIC FROM metrics_wide ORDER BY METRIC")
        .fetchdf()["METRIC"]
        .tolist()
    )
    return {
        "countries": countries,
        "zone_types": zone_types,
        "zone_prioritizations": zone_prioritizations,
        "metrics": metrics,
    }
