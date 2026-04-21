"""
Smoke tests for the metrics repository.

Tests run against the real processed parquets in data/processed/.
No mocks — we're validating that the SQL is correct and the data
looks reasonable, not just that the code runs.

Run from project root:
    PYTHONPATH=. pytest tests/test_repositories/ -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.repositories.metrics_repository import (
    aggregate_metric,
    compare_metric_across_groups,
    find_zones_multivariate,
    get_metric_trend,
    get_orders_growth,
    get_top_zones_by_metric,
    list_available_filters,
)

# ---------------------------------------------------------------------------
# get_top_zones_by_metric
# ---------------------------------------------------------------------------

def test_top_zones_returns_dataframe() -> None:
    df = get_top_zones_by_metric("Lead Penetration", country="CO", limit=5)
    assert isinstance(df, pd.DataFrame)
    assert len(df) <= 5
    assert "value" in df.columns
    # Default order is desc — values should be monotonically non-increasing
    assert df["value"].is_monotonic_decreasing or len(df) <= 1


def test_top_zones_asc_order() -> None:
    df = get_top_zones_by_metric("Perfect Orders", country="MX", limit=5, order="asc")
    assert isinstance(df, pd.DataFrame)
    assert df["value"].is_monotonic_increasing or len(df) <= 1


def test_top_zones_required_columns() -> None:
    df = get_top_zones_by_metric("Perfect Orders", country="CO", limit=3)
    for col in ("country", "city", "zone", "zone_type", "zone_prioritization", "metric", "value"):
        assert col in df.columns, f"Missing column: {col}"


def test_top_zones_rejects_invalid_country() -> None:
    with pytest.raises(ValueError, match="Invalid country"):
        get_top_zones_by_metric("Lead Penetration", country="XX")


def test_top_zones_rejects_invalid_week() -> None:
    with pytest.raises(ValueError, match="Invalid week"):
        get_top_zones_by_metric("Lead Penetration", week="L9W_ROLL")


def test_top_zones_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="Unknown metric"):
        get_top_zones_by_metric("Fake Metric")


# ---------------------------------------------------------------------------
# compare_metric_across_groups
# ---------------------------------------------------------------------------

def test_compare_across_zone_types() -> None:
    df = compare_metric_across_groups("Perfect Orders", group_by="zone_type", country="MX")
    assert isinstance(df, pd.DataFrame)
    assert "mean" in df.columns
    assert "group_value" in df.columns
    assert len(df) <= 2  # Wealthy + Non Wealthy


def test_compare_across_countries_no_filter() -> None:
    # Not all metrics exist in all 9 countries — use a metric with broad coverage
    df = compare_metric_across_groups("Perfect Orders", group_by="country")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 9  # Perfect Orders covers all 9 LATAM countries


def test_compare_rejects_invalid_group_by() -> None:
    with pytest.raises(ValueError, match="Invalid group_by"):
        compare_metric_across_groups("Perfect Orders", group_by="invalid_dim")


# ---------------------------------------------------------------------------
# get_metric_trend
# ---------------------------------------------------------------------------

def test_trend_specific_zone() -> None:
    df = get_metric_trend("Gross Profit UE", country="CO", city="Bogota", zone="Chapinero")
    assert isinstance(df, pd.DataFrame)
    assert "week_number" in df.columns
    assert "value" in df.columns
    assert len(df) <= 9  # at most 9 data points (L0W through L8W)


def test_trend_zone_filter_ignores_accents() -> None:
    df_plain = get_metric_trend(
        "Perfect Orders", country="CO", city="Bogota", zone="Chapinero"
    )
    df_accented = get_metric_trend(
        "Perfect Orders", country="CO", city="Bogotá", zone="Chapinero"
    )

    assert isinstance(df_plain, pd.DataFrame)
    assert isinstance(df_accented, pd.DataFrame)
    assert len(df_plain) > 0
    assert len(df_accented) > 0
    pd.testing.assert_series_equal(
        df_plain["value"].reset_index(drop=True),
        df_accented["value"].reset_index(drop=True),
        check_names=False,
    )


def test_trend_country_aggregate() -> None:
    df = get_metric_trend("Perfect Orders", country="CO", num_weeks=4)
    assert isinstance(df, pd.DataFrame)
    assert "zone_count" in df.columns
    assert len(df) <= 4


def test_trend_sorted_oldest_first() -> None:
    df = get_metric_trend("Turbo Adoption", country="MX", num_weeks=5)
    if len(df) > 1:
        # week_number DESC = 4, 3, 2, 1, 0 (oldest first)
        assert df["week_number"].iloc[0] >= df["week_number"].iloc[-1]


def test_trend_rejects_invalid_num_weeks() -> None:
    with pytest.raises(ValueError, match="num_weeks"):
        get_metric_trend("Perfect Orders", num_weeks=10)


# ---------------------------------------------------------------------------
# aggregate_metric
# ---------------------------------------------------------------------------

def test_aggregate_global_mean() -> None:
    df = aggregate_metric("Perfect Orders")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert "value" in df.columns
    # Perfect Orders is a proportion — mean should be between 0 and 1
    assert 0.0 <= float(df["value"].iloc[0]) <= 1.0


def test_aggregate_grouped_by_country() -> None:
    df = aggregate_metric("Perfect Orders", agg="mean", group_by="country")
    assert isinstance(df, pd.DataFrame)
    assert "group_value" in df.columns
    assert len(df) == 9  # Perfect Orders covers all 9 LATAM countries


def test_aggregate_rejects_invalid_agg() -> None:
    with pytest.raises(ValueError, match="Invalid agg"):
        aggregate_metric("Perfect Orders", agg="variance")


# ---------------------------------------------------------------------------
# find_zones_multivariate
# ---------------------------------------------------------------------------

def test_multivariate_find() -> None:
    conditions = [
        {"metric": "Lead Penetration", "op": ">", "value": 0.3},
        {"metric": "Perfect Orders", "op": "<", "value": 0.9},
    ]
    df = find_zones_multivariate(conditions, country="CO")
    assert isinstance(df, pd.DataFrame)
    # All returned zones must satisfy both conditions
    if len(df) > 0:
        assert (df["Lead Penetration"] > 0.3).all()
        assert (df["Perfect Orders"] < 0.9).all()


def test_multivariate_empty_conditions_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        find_zones_multivariate([])


def test_multivariate_invalid_op_raises() -> None:
    with pytest.raises(ValueError, match="Invalid operator"):
        find_zones_multivariate([{"metric": "Perfect Orders", "op": "~=", "value": 0.8}])


def test_multivariate_invalid_metric_raises() -> None:
    with pytest.raises(ValueError, match="Unknown metric"):
        find_zones_multivariate([{"metric": "Ghost Metric", "op": ">", "value": 0.5}])


# ---------------------------------------------------------------------------
# get_orders_growth
# ---------------------------------------------------------------------------

def test_orders_growth_returns_ranked_zones() -> None:
    df = get_orders_growth(country="CO", top_n=5, comparison_weeks=5)
    assert isinstance(df, pd.DataFrame)
    assert len(df) <= 5
    assert "growth_pct" in df.columns
    assert "current_orders" in df.columns
    # Sorted descending by growth_pct
    if len(df) > 1:
        assert df["growth_pct"].is_monotonic_decreasing or df["growth_pct"].iloc[0] >= df["growth_pct"].iloc[-1]


def test_orders_growth_rejects_invalid_comparison_weeks() -> None:
    with pytest.raises(ValueError, match="comparison_weeks"):
        get_orders_growth(comparison_weeks=9)


# ---------------------------------------------------------------------------
# list_available_filters
# ---------------------------------------------------------------------------

def test_available_filters_structure() -> None:
    filters = list_available_filters()
    assert "countries" in filters
    assert "zone_types" in filters
    assert "zone_prioritizations" in filters
    assert "metrics" in filters


def test_available_filters_9_countries() -> None:
    filters = list_available_filters()
    assert len(filters["countries"]) == 9


def test_available_filters_13_metrics() -> None:
    filters = list_available_filters()
    assert len(filters["metrics"]) == 13
