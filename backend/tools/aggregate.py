"""
Tool: aggregate

Thin wrapper around ``metrics_repository.aggregate_metric``.

Use for **summary statistics** on a single metric, optionally grouped by a
dimension. Examples: "Average Perfect Orders across all zones", "Median
Turbo Adoption by country", "Max Gross Profit UE by city".

If no ``group_by`` is supplied, returns a single global aggregate row.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import aggregate_metric
from backend.tools._caveats import (
    detect_small_groups,
    detect_small_sample,
    merge,
)
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Aggregate (mean, median, sum, min, max, count) a metric with optional grouping.

    Expected arguments:
        metric: str                                                   (required)
        agg: "mean" | "median" | "sum" | "min" | "max" | "count" = "mean"
        group_by: "country" | "city" | "zone_type" | "zone_prioritization" | None
        week: str = "L0W_ROLL"
    """
    metric = arguments.get("metric")
    if not metric:
        return error_response("Missing required argument 'metric'.")

    agg = arguments.get("agg", "mean")
    group_by = arguments.get("group_by")  # None => global aggregate
    week = arguments.get("week", "L0W_ROLL")

    try:
        df = aggregate_metric(
            metric,
            agg=agg,
            group_by=group_by,
            week=week,
        )
    except ValueError as exc:
        return error_response(exc)

    if df.empty:
        reason = f"No data to aggregate for {metric} ({week})."
        return empty_response(reason, metric=metric)

    if group_by is None:
        value = float(df["value"].iloc[0])
        n = int(df["count"].iloc[0])
        summary = (
            f"{agg.capitalize()} {metric} ({week}): {value:.3f} across {n} zones."
        )
        caveats = merge(detect_small_sample(n, threshold=5, scope=f"global {agg}"))
    else:
        top = df.iloc[0]
        bottom = df.iloc[-1]
        if len(df) == 1:
            summary = (
                f"{agg.capitalize()} {metric} by {group_by} ({week}): "
                f"{top['group_value']}={float(top['value']):.3f}."
            )
        else:
            summary = (
                f"{agg.capitalize()} {metric} by {group_by} ({week}): "
                f"top={top['group_value']} ({float(top['value']):.3f}), "
                f"bottom={bottom['group_value']} ({float(bottom['value']):.3f})."
            )
        # Flag groups whose n is too small to generalise (e.g. Uruguay vs
        # Mexico — very different sample sizes hidden behind the same
        # aggregate).
        caveats = merge(detect_small_groups(df, count_col="count"))

    return format_response(df, summary=summary, metric=metric, caveats=caveats)
