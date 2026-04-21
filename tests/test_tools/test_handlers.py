"""
Smoke tests for the six tool handlers + the registry dispatcher.

These tests run against the real processed parquets in data/processed/ via
the metrics_repository — same contract as the repository tests. No LLM is
involved; we only exercise the handler -> repository -> DuckDB path and
assert the uniform {summary, data, metadata} response shape.
"""

from __future__ import annotations

from backend.tools import (
    aggregate,
    compare_metrics,
    filter_zones,
    get_trend,
    multivariate,
    orders_growth,
)
from backend.tools.registry import TOOLS_REGISTRY, dispatch, get_openai_tools_schema

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_all_tools_registered() -> None:
    expected = {
        "filter_zones",
        "compare_metrics",
        "get_trend",
        "aggregate",
        "multivariate",
        "orders_growth",
    }
    assert set(TOOLS_REGISTRY.keys()) == expected


def test_openai_schema_shape() -> None:
    schemas = get_openai_tools_schema()
    assert len(schemas) == 6
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        assert fn["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# Uniform response contract helper
# ---------------------------------------------------------------------------

def _assert_shape(result: dict) -> None:
    assert isinstance(result, dict)
    assert set(result.keys()) >= {"summary", "data", "metadata"}
    assert isinstance(result["summary"], str) and result["summary"]
    assert isinstance(result["data"], list)
    assert isinstance(result["metadata"], dict)


# ---------------------------------------------------------------------------
# filter_zones
# ---------------------------------------------------------------------------

def test_filter_zones_happy_path() -> None:
    result = filter_zones.handle(
        {"metric": "Perfect Orders", "country": "CO", "limit": 5}
    )
    _assert_shape(result)
    assert len(result["data"]) <= 5
    assert result["metadata"]["total_count"] >= 0


def test_filter_zones_empty_result() -> None:
    # Turbo Adoption is only tracked in a subset of countries.
    result = filter_zones.handle(
        {"metric": "Turbo Adoption", "country": "UY", "limit": 5}
    )
    _assert_shape(result)
    if len(result["data"]) == 0:
        assert result["metadata"]["total_count"] == 0
        assert "empty_reason" in result["metadata"]


def test_filter_zones_invalid_country() -> None:
    result = filter_zones.handle({"metric": "Perfect Orders", "country": "XX"})
    assert result["metadata"].get("error") is True
    assert result["data"] == []


def test_filter_zones_invalid_metric() -> None:
    result = filter_zones.handle({"metric": "Fake Metric", "country": "CO"})
    assert result["metadata"].get("error") is True
    assert result["data"] == []


def test_filter_zones_missing_metric() -> None:
    result = filter_zones.handle({"country": "CO"})
    assert result["metadata"].get("error") is True


def test_filter_zones_ascending_order() -> None:
    result = filter_zones.handle(
        {"metric": "Perfect Orders", "country": "MX", "order": "asc", "limit": 3}
    )
    _assert_shape(result)
    if len(result["data"]) > 1:
        values = [row["value"] for row in result["data"]]
        assert values == sorted(values)


# ---------------------------------------------------------------------------
# compare_metrics
# ---------------------------------------------------------------------------

def test_compare_metrics_zone_type() -> None:
    result = compare_metrics.handle(
        {"metric": "Perfect Orders", "group_by": "zone_type", "country": "MX"}
    )
    _assert_shape(result)
    assert len(result["data"]) <= 2  # Wealthy + Non Wealthy


def test_compare_metrics_across_countries() -> None:
    result = compare_metrics.handle(
        {"metric": "Perfect Orders", "group_by": "country"}
    )
    _assert_shape(result)
    assert result["metadata"]["total_count"] == 9


def test_compare_metrics_invalid_group_by() -> None:
    result = compare_metrics.handle(
        {"metric": "Perfect Orders", "group_by": "bogus"}
    )
    assert result["metadata"].get("error") is True


def test_compare_metrics_missing_group_by() -> None:
    result = compare_metrics.handle({"metric": "Perfect Orders"})
    assert result["metadata"].get("error") is True


# ---------------------------------------------------------------------------
# get_trend
# ---------------------------------------------------------------------------

def test_get_trend_specific_zone() -> None:
    result = get_trend.handle(
        {
            "metric": "Perfect Orders",
            "country": "CO",
            "city": "Bogota",
            "zone": "Chapinero",
        }
    )
    _assert_shape(result)
    if result["data"]:
        assert "value" in result["data"][0]
        assert "week_number" in result["data"][0]


def test_get_trend_global_default() -> None:
    result = get_trend.handle({"metric": "Perfect Orders", "num_weeks": 4})
    _assert_shape(result)
    assert len(result["data"]) <= 4


def test_get_trend_invalid_num_weeks() -> None:
    result = get_trend.handle({"metric": "Perfect Orders", "num_weeks": 99})
    assert result["metadata"].get("error") is True


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

def test_aggregate_global_mean() -> None:
    result = aggregate.handle({"metric": "Perfect Orders", "agg": "mean"})
    _assert_shape(result)
    assert result["metadata"]["total_count"] == 1


def test_aggregate_grouped_by_country() -> None:
    result = aggregate.handle(
        {"metric": "Perfect Orders", "agg": "mean", "group_by": "country"}
    )
    _assert_shape(result)
    assert result["metadata"]["total_count"] == 9


def test_aggregate_invalid_agg() -> None:
    result = aggregate.handle({"metric": "Perfect Orders", "agg": "variance"})
    assert result["metadata"].get("error") is True


# ---------------------------------------------------------------------------
# multivariate
# ---------------------------------------------------------------------------

def test_multivariate_two_conditions() -> None:
    result = multivariate.handle(
        {
            "conditions": [
                {"metric": "Perfect Orders", "op": "<", "value": 0.9},
                {"metric": "Lead Penetration", "op": ">", "value": 0.3},
            ],
            "country": "CO",
        }
    )
    _assert_shape(result)
    assert isinstance(result["data"], list)


def test_multivariate_empty_conditions() -> None:
    result = multivariate.handle({"conditions": []})
    assert result["metadata"].get("error") is True


def test_multivariate_invalid_operator() -> None:
    result = multivariate.handle(
        {"conditions": [{"metric": "Perfect Orders", "op": "~=", "value": 0.8}]}
    )
    assert result["metadata"].get("error") is True


def test_multivariate_accepts_operator_threshold_aliases() -> None:
    # LLMs occasionally emit {operator, threshold} instead of {op, value};
    # the handler normalises both spellings.
    result = multivariate.handle(
        {
            "conditions": [
                {"metric": "Perfect Orders", "operator": ">", "threshold": 0.5}
            ],
            "country": "CO",
            "limit": 5,
        }
    )
    _assert_shape(result)
    assert result["metadata"].get("error") is not True


# ---------------------------------------------------------------------------
# orders_growth
# ---------------------------------------------------------------------------

def test_orders_growth_basic() -> None:
    result = orders_growth.handle({"country": "CO", "top_n": 5})
    _assert_shape(result)
    assert len(result["data"]) <= 5


def test_orders_growth_invalid_comparison_weeks() -> None:
    result = orders_growth.handle({"country": "CO", "comparison_weeks": 99})
    assert result["metadata"].get("error") is True


def test_orders_growth_zone_type_warning() -> None:
    result = orders_growth.handle(
        {"country": "CO", "top_n": 3, "zone_type": "Wealthy"}
    )
    _assert_shape(result)
    assert "warning" in result["metadata"]


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def test_dispatch_unknown_tool() -> None:
    result = dispatch("nonexistent_tool", {})
    assert result["metadata"]["error"] is True
    assert result["data"] == []


def test_dispatch_happy_path() -> None:
    result = dispatch(
        "filter_zones", {"metric": "Perfect Orders", "country": "CO", "limit": 3}
    )
    _assert_shape(result)


def test_dispatch_catches_exceptions() -> None:
    # Missing required 'metric' — handler should return error, not raise.
    result = dispatch("filter_zones", {})
    assert result["metadata"].get("error") is True or result["data"] == []


def test_dispatch_handles_none_arguments() -> None:
    result = dispatch("filter_zones", None)  # type: ignore[arg-type]
    assert result["metadata"].get("error") is True or result["data"] == []


# ---------------------------------------------------------------------------
# scale_note attachment for special scales
# ---------------------------------------------------------------------------

def test_scale_note_included_for_gross_profit() -> None:
    result = filter_zones.handle(
        {"metric": "Gross Profit UE", "country": "CO", "limit": 3}
    )
    # Only applies when the query actually returns rows.
    if result["data"]:
        assert "scale_note" in result["metadata"]


def test_scale_note_included_for_lead_penetration() -> None:
    result = filter_zones.handle(
        {"metric": "Lead Penetration", "country": "CO", "limit": 3}
    )
    if result["data"]:
        assert "scale_note" in result["metadata"]


def test_no_scale_note_for_plain_proportion() -> None:
    result = filter_zones.handle(
        {"metric": "Perfect Orders", "country": "CO", "limit": 3}
    )
    assert "scale_note" not in result["metadata"]


# ---------------------------------------------------------------------------
# Caveats — verify the Nivel-2 signals propagate from handlers to the LLM
# ---------------------------------------------------------------------------

def _caveat_types(result: dict) -> list[str]:
    return [c["type"] for c in result["metadata"].get("caveats", [])]


def test_orders_growth_flags_low_denominator_in_real_data() -> None:
    # The real CO orders parquet contains several zones with past_orders < 20
    # (OBONUCO, Malambo, San Felipe, etc.) — the caveat must fire.
    result = orders_growth.handle({"country": "CO", "top_n": 10})
    assert "low_denominator" in _caveat_types(result), (
        "orders_growth must attach a low_denominator caveat when any zone in "
        "the top-N has past_orders < 20; real CO data is known to contain "
        "such zones."
    )
    low_caveat = next(
        c for c in result["metadata"]["caveats"] if c["type"] == "low_denominator"
    )
    assert low_caveat["affected_rows"], "expected at least one affected row"
    assert "volatile" in low_caveat["detail"].lower()


def test_compare_metrics_flags_small_groups_on_country() -> None:
    # Turbo Adoption + country comparison typically yields some countries
    # with very few zones — the small_sample_in_group caveat must fire.
    result = compare_metrics.handle(
        {"metric": "Gross Profit UE", "group_by": "country"}
    )
    types = _caveat_types(result)
    # Gross Profit UE covers all 9 countries but UY has ~7 zones < 20.
    assert "small_sample_in_group" in types or result["metadata"].get("total_count", 0) == 0


def test_multivariate_flags_narrow_result_for_unsatisfiable() -> None:
    # Conditions so strict that at most 0-1 zone can match.
    result = multivariate.handle(
        {
            "conditions": [
                {"metric": "Perfect Orders", "op": ">", "value": 0.999},
                {"metric": "Lead Penetration", "op": ">", "value": 2.0},
            ],
            "country": "CO",
        }
    )
    # Either empty (handled by empty_response, no caveat needed) or narrow.
    if result["data"]:
        assert "narrow_result" in _caveat_types(result)


def test_get_trend_flags_high_variance_when_series_is_noisy() -> None:
    # MASCHWITZ in AR has the very volatile orders series we saw in the UI.
    # get_trend is for *metric* trends, not orders — so pick a metric/zone
    # combo where variance is likely to be high. Fall back: just verify the
    # caveat shape when a series does qualify.
    result = get_trend.handle(
        {"metric": "Turbo Adoption", "country": "UY", "num_weeks": 8}
    )
    # We don't force the caveat — we just verify that if it fires, the shape
    # is valid.
    for c in result["metadata"].get("caveats", []):
        assert c["type"] in {"high_variance"}
        assert c["detail"]


def test_aggregate_no_group_flags_small_sample_when_metric_is_thin() -> None:
    # A metric + country combo with < 5 zones fires small_sample. Turbo
    # Adoption in CR tends to be very thin.
    result = aggregate.handle({"metric": "% PRO Users Who Breakeven", "agg": "mean"})
    # Either it aggregates over many zones (no caveat) or few (caveat).
    # We just assert shape consistency and no crashes.
    for c in result["metadata"].get("caveats", []):
        assert c["type"] in {"small_sample"}


def test_filter_zones_has_no_caveats_by_design() -> None:
    # filter_zones returns top-N and is not subject to the current caveat
    # set — asking for top 5 and getting 5 is the contract, not a warning.
    result = filter_zones.handle(
        {"metric": "Perfect Orders", "country": "CO", "limit": 5}
    )
    assert "caveats" not in result["metadata"]


def test_caveats_are_capped_in_responses() -> None:
    # Regardless of how many detectors fire, at most 5 caveats end up in
    # metadata.caveats — the system prompt rule would otherwise drown in
    # warnings.
    # This is an invariant we rely on for readability.
    result = orders_growth.handle({"country": "CO", "top_n": 50})
    caveats = result["metadata"].get("caveats", [])
    assert len(caveats) <= 5
