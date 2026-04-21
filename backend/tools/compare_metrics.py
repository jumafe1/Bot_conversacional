"""
Tool: compare_metrics

Thin wrapper around ``metrics_repository.compare_metric_across_groups``.
Use when the user wants a **side-by-side comparison** of a single metric
across a categorical dimension (zone_type, zone_prioritization, or country),
e.g. "Wealthy vs Non Wealthy Perfect Orders in Mexico", "Compare Lead
Penetration across countries", "Which zone_type has better Pro Adoption?".
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import compare_metric_across_groups
from backend.tools._caveats import detect_small_groups, merge
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Compare a metric across groups (zone_type, country, or zone_prioritization).

    Expected arguments:
        metric: str    (required)
        group_by: "zone_type" | "zone_prioritization" | "country"  (required)
        country: str | None
        week: str = "L0W_ROLL"
    """
    metric = arguments.get("metric")
    group_by = arguments.get("group_by")
    if not metric:
        return error_response("Missing required argument 'metric'.")
    if not group_by:
        return error_response("Missing required argument 'group_by'.")

    country = arguments.get("country")
    week = arguments.get("week", "L0W_ROLL")

    try:
        df = compare_metric_across_groups(
            metric,
            group_by=group_by,
            country=country,
            week=week,
        )
    except ValueError as exc:
        return error_response(exc)

    filter_str = f" (country={country})" if country else ""

    if df.empty:
        reason = (
            f"No data to compare {metric} by {group_by}{filter_str} in {week}. "
            f"The metric may not be tracked in those groups."
        )
        return empty_response(reason, metric=metric)

    top = df.iloc[0]
    bottom = df.iloc[-1]
    diff = float(top["mean"]) - float(bottom["mean"])

    if len(df) == 1:
        summary = (
            f"Only one group available for {metric} by {group_by}{filter_str} "
            f"({week}): {top['group_value']}={float(top['mean']):.3f}."
        )
    else:
        summary = (
            f"Comparison of {metric} by {group_by}{filter_str} ({week}): "
            f"{top['group_value']}={float(top['mean']):.3f} (highest), "
            f"{bottom['group_value']}={float(bottom['mean']):.3f} (lowest). "
            f"Difference: {diff:+.3f}."
        )

    # Flag groups with too few zones to generalise — e.g. UY (7 zones) vs
    # MX (300+). The bot must communicate that asymmetry. Uses the detector's
    # default threshold (see ``_caveats.detect_small_groups``).
    caveats = merge(detect_small_groups(df, count_col="count"))

    return format_response(df, summary=summary, metric=metric, caveats=caveats)
