"""
Tool: filter_zones

Thin wrapper around ``metrics_repository.get_top_zones_by_metric``.

Use when the user asks for a **ranking** or **filter** of zones by a single
metric, e.g. "top 5 zones by Lead Penetration", "worst Perfect Orders in
Mexico", or "5 wealthy zones with highest Gross Profit UE".
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import get_top_zones_by_metric
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Filter and rank zones by a single metric.

    Expected arguments:
        metric: str                (required)
        country: str | None
        zone_type: str | None                ("Wealthy" | "Non Wealthy")
        zone_prioritization: str | None      ("High Priority" | "Prioritized" | "Not Prioritized")
        week: str = "L0W_ROLL"
        limit: int = 5
        order: "asc" | "desc" = "desc"
    """
    metric = arguments.get("metric")
    if not metric:
        return error_response("Missing required argument 'metric'.")

    country = arguments.get("country")
    zone_type = arguments.get("zone_type")
    zone_prioritization = arguments.get("zone_prioritization")
    week = arguments.get("week", "L0W_ROLL")
    limit = int(arguments.get("limit", 5))
    order = arguments.get("order", "desc")

    if order not in ("asc", "desc"):
        return error_response(f"Invalid order '{order}'. Must be 'asc' or 'desc'.")

    try:
        df = get_top_zones_by_metric(
            metric,
            country=country,
            zone_type=zone_type,
            zone_prioritization=zone_prioritization,
            week=week,
            limit=limit,
            order=order,
        )
    except ValueError as exc:
        return error_response(exc)

    filters = _describe_filters(country, zone_type, zone_prioritization)

    if df.empty:
        reason = (
            f"No zones found for '{metric}' ({week}){filters}. "
            f"This metric may not be tracked in the selected filters."
        )
        return empty_response(reason, metric=metric)

    n = len(df)
    direction = "highest" if order == "desc" else "lowest"
    top_row = df.iloc[0]
    vmin = float(df["value"].min())
    vmax = float(df["value"].max())
    summary = (
        f"Top {n} zones by {direction} {metric} ({week}){filters}: "
        f"leader is {top_row['city']}/{top_row['zone']} "
        f"({top_row['country']}) at {float(top_row['value']):.3f}. "
        f"Range: {vmin:.3f}–{vmax:.3f}."
    )

    return format_response(df, summary=summary, metric=metric)


def _describe_filters(
    country: str | None,
    zone_type: str | None,
    zone_prioritization: str | None,
) -> str:
    parts: list[str] = []
    if country:
        parts.append(f"country={country}")
    if zone_type:
        parts.append(f"zone_type={zone_type}")
    if zone_prioritization:
        parts.append(f"priority={zone_prioritization}")
    return f" [{', '.join(parts)}]" if parts else ""
