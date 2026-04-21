"""
Tool: multivariate

Thin wrapper around ``metrics_repository.find_zones_multivariate``.

Use when the user wants zones satisfying **multiple simultaneous conditions
on different metrics** (AND logic). Examples:

    - "Zones with Lead Penetration > 0.5 AND Perfect Orders < 0.85 in CO"
    - "Low Pro Adoption (<0.05) and high Gross Profit UE (>5)"
    - "High-priority zones where Turbo Adoption < 0.2 and GMV markdowns > 0.1"
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import find_zones_multivariate
from backend.tools._caveats import detect_narrow_result, merge
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Find zones matching multiple metric conditions simultaneously (AND).

    Expected arguments:
        conditions: list[dict]  (required)
            Each dict: {"metric": str, "op": "<|<=|>|>=|==|!=", "value": float}
        country: str | None
        week: str = "L0W_ROLL"
        limit: int = 20
    """
    conditions = arguments.get("conditions")
    if not conditions or not isinstance(conditions, list):
        return error_response(
            "Missing or empty 'conditions'. Provide a non-empty list of "
            "{metric, op, value} dicts."
        )

    # Normalise: tolerate LLMs that send {metric, operator, threshold}
    # instead of {metric, op, value} by rewriting on the fly.
    normalised: list[dict] = []
    for c in conditions:
        if not isinstance(c, dict):
            return error_response("Each condition must be a dict.")
        metric = c.get("metric")
        op = c.get("op", c.get("operator"))
        value = c.get("value", c.get("threshold"))
        if metric is None or op is None or value is None:
            return error_response(
                "Each condition requires 'metric', 'op', and 'value'."
            )
        try:
            value = float(value)
        except (TypeError, ValueError):
            return error_response(
                f"Condition value for metric '{metric}' must be numeric."
            )
        normalised.append({"metric": metric, "op": op, "value": value})

    country = arguments.get("country")
    week = arguments.get("week", "L0W_ROLL")
    limit = int(arguments.get("limit", 20))

    try:
        df = find_zones_multivariate(
            normalised,
            country=country,
            week=week,
            limit=limit,
        )
    except ValueError as exc:
        return error_response(exc)

    cond_strs = " AND ".join(
        f"{c['metric']} {c['op']} {c['value']}" for c in normalised
    )
    filter_str = f" in {country}" if country else ""

    if df.empty:
        reason = (
            f"No zones{filter_str} satisfy all conditions: {cond_strs}. "
            f"Loosen a threshold or drop a condition and retry."
        )
        return empty_response(reason)

    summary = (
        f"Found {len(df)} zones matching {len(normalised)} "
        f"condition{'s' if len(normalised) != 1 else ''}{filter_str}. "
        f"Conditions: {cond_strs}."
    )

    # If only 1-2 zones matched, the bot should not talk about "patterns".
    caveats = merge(
        detect_narrow_result(len(df), threshold=3, condition_desc=cond_strs),
    )

    metric_for_scale = normalised[0]["metric"]
    return format_response(
        df,
        summary=summary,
        metric=metric_for_scale,
        caveats=caveats,
        extra_metadata={"conditions_applied": cond_strs},
    )
