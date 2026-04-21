"""
Unit tests for backend.tools._caveats.

These are pure-function tests — no DB, no repository, no LLM. We only
verify that each detector fires under the intended statistical condition
and stays silent otherwise.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.tools._caveats import (
    MAX_CAVEATS,
    Caveat,
    detect_high_variance,
    detect_low_denominator,
    detect_narrow_result,
    detect_small_groups,
    detect_small_sample,
    merge,
)


def _assert_caveat_shape(c: Caveat) -> None:
    assert "type" in c and isinstance(c["type"], str) and c["type"]
    assert "detail" in c and isinstance(c["detail"], str) and c["detail"]
    # affected_rows is optional but when present must be a list[int] or None
    if "affected_rows" in c and c["affected_rows"] is not None:
        assert all(isinstance(i, int) for i in c["affected_rows"])


# ---------------------------------------------------------------------------
# detect_low_denominator
# ---------------------------------------------------------------------------

def test_low_denominator_fires_on_small_bases() -> None:
    df = pd.DataFrame(
        {
            "past_orders": [4, 1, 50, 25],   # rows 0, 1 are below default 20
            "growth_pct": [525.0, 400.0, 10.0, 15.0],
        }
    )
    caveats = detect_low_denominator(df, base_col="past_orders")
    assert len(caveats) == 1
    c = caveats[0]
    _assert_caveat_shape(c)
    assert c["type"] == "low_denominator"
    assert c["affected_rows"] == [0, 1]
    assert "4" in c["detail"] and "1" in c["detail"]
    assert "volatile" in c["detail"]


def test_low_denominator_silent_when_all_high() -> None:
    df = pd.DataFrame({"past_orders": [100, 200, 300]})
    assert detect_low_denominator(df, base_col="past_orders") == []


def test_low_denominator_silent_on_empty_or_missing() -> None:
    assert detect_low_denominator(pd.DataFrame(), base_col="past_orders") == []
    assert detect_low_denominator(
        pd.DataFrame({"other": [1, 2]}),
        base_col="past_orders",
    ) == []


def test_low_denominator_threshold_is_configurable() -> None:
    df = pd.DataFrame({"past_orders": [4, 10, 50]})
    # With default threshold=20, rows 0 and 1 trigger.
    assert detect_low_denominator(df, base_col="past_orders")[0]["affected_rows"] == [0, 1]
    # Tighter threshold only flags row 0.
    assert (
        detect_low_denominator(df, base_col="past_orders", threshold=5)[0][
            "affected_rows"
        ]
        == [0]
    )


# ---------------------------------------------------------------------------
# detect_small_sample (whole-response)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,fires", [(0, True), (1, True), (4, True), (5, False), (20, False)])
def test_small_sample_threshold(n: int, fires: bool) -> None:
    result = detect_small_sample(n, threshold=5, scope="global mean")
    assert bool(result) is fires
    if fires:
        _assert_caveat_shape(result[0])
        assert result[0]["type"] == "small_sample"
        assert str(n) in result[0]["detail"]
        assert "global mean" in result[0]["detail"]


# ---------------------------------------------------------------------------
# detect_small_groups (per-row)
# ---------------------------------------------------------------------------

def test_small_groups_flags_thin_groups() -> None:
    df = pd.DataFrame(
        {
            "group_value": ["MX", "BR", "UY"],
            "count": [300, 200, 7],
        }
    )
    # Default threshold=10 catches UY (7) but not MX/BR.
    caveats = detect_small_groups(df, count_col="count")
    assert len(caveats) == 1
    c = caveats[0]
    assert c["type"] == "small_sample_in_group"
    assert c["affected_rows"] == [2]
    assert "UY" in c["detail"]
    assert "n=7" in c["detail"]


def test_small_groups_respects_custom_threshold() -> None:
    df = pd.DataFrame({"group_value": ["a", "b"], "count": [11, 50]})
    # Default threshold=10 — neither triggers.
    assert detect_small_groups(df) == []
    # Raise the bar to 20 — now `a` with n=11 triggers.
    tight = detect_small_groups(df, threshold=20)
    assert tight and tight[0]["affected_rows"] == [0]


def test_small_groups_silent_when_all_large() -> None:
    df = pd.DataFrame({"group_value": ["a", "b"], "count": [100, 100]})
    assert detect_small_groups(df) == []


def test_small_groups_handles_missing_group_value_column() -> None:
    df = pd.DataFrame({"count": [2, 50]})
    caveats = detect_small_groups(df)
    assert caveats
    # Falls back to "row N (n=X)" label when no group_value present
    assert "row 0" in caveats[0]["detail"]


# ---------------------------------------------------------------------------
# detect_high_variance
# ---------------------------------------------------------------------------

def test_high_variance_fires_on_noisy_series() -> None:
    # CV for [1, 10, 1, 10, 1] is ~0.82 (well above 0.3)
    caveats = detect_high_variance([1, 10, 1, 10, 1], threshold=0.3)
    assert len(caveats) == 1
    assert caveats[0]["type"] == "high_variance"
    assert "coefficient of variation" in caveats[0]["detail"]


def test_high_variance_silent_on_stable_series() -> None:
    # CV for [0.50, 0.51, 0.49, 0.50] is tiny.
    assert detect_high_variance([0.50, 0.51, 0.49, 0.50], threshold=0.3) == []


def test_high_variance_silent_below_three_points() -> None:
    assert detect_high_variance([1, 100], threshold=0.3) == []


def test_high_variance_silent_near_zero_mean() -> None:
    # Mean ~ 0 would blow up CV; guard avoids division by tiny number.
    assert detect_high_variance([0.0, 0.0, 0.0], threshold=0.3) == []


def test_high_variance_tolerates_nones() -> None:
    caveats = detect_high_variance([1, None, 10, None, 1, 10], threshold=0.3)
    assert caveats  # only 4 non-None values but enough, noisy


# ---------------------------------------------------------------------------
# detect_narrow_result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,fires", [(0, True), (1, True), (2, True), (3, False), (10, False)])
def test_narrow_result_threshold(n: int, fires: bool) -> None:
    result = detect_narrow_result(n, threshold=3)
    assert bool(result) is fires
    if fires:
        assert result[0]["type"] == "narrow_result"
        assert str(n) in result[0]["detail"]


def test_narrow_result_includes_condition_description() -> None:
    result = detect_narrow_result(1, condition_desc="Perfect Orders < 0.5")
    assert result and "Perfect Orders < 0.5" in result[0]["detail"]


# ---------------------------------------------------------------------------
# merge / cap
# ---------------------------------------------------------------------------

def test_merge_flattens_and_caps() -> None:
    many = [{"type": f"t{i}", "detail": "x"} for i in range(10)]
    merged = merge(many[:3], many[3:6], many[6:])
    assert len(merged) == MAX_CAVEATS
    assert [c["type"] for c in merged] == ["t0", "t1", "t2", "t3", "t4"]


def test_merge_skips_empty_groups() -> None:
    assert merge(None, [], [{"type": "x", "detail": "d"}]) == [
        {"type": "x", "detail": "d"},
    ]


def test_merge_preserves_order() -> None:
    a = [{"type": "a", "detail": "d"}]
    b = [{"type": "b", "detail": "d"}]
    assert [c["type"] for c in merge(b, a)] == ["b", "a"]
