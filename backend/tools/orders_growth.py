"""
Tool: orders_growth

Thin wrapper around ``metrics_repository.get_orders_growth``.

Use for ranking zones by **order volume growth** between the most recent
week (L0W) and a past week (L{N}W). Examples:
    - "Fastest-growing zones in Colombia"
    - "Top 10 zones by order growth over 5 weeks"
    - "Which zones are declining in orders?"  (agent may set order/limit differently)

Note: orders data has no ZONE_TYPE column; the ``zone_type`` argument is
accepted for LLM ergonomics but silently ignored by the repository.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import get_orders_growth
from backend.tools._caveats import detect_low_denominator, merge
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Rank zones by order volume growth over the last N weeks.

    Expected arguments:
        country: str | None
        zone_type: str | None        (ignored — no ZONE_TYPE column in orders)
        top_n: int = 10
        comparison_weeks: int = 5    (1–8, which past week to compare L0W against)
    """
    country = arguments.get("country")
    zone_type = arguments.get("zone_type")
    top_n = int(arguments.get("top_n", 10))
    comparison_weeks = int(arguments.get("comparison_weeks", 5))

    try:
        df = get_orders_growth(
            country=country,
            zone_type=zone_type,
            top_n=top_n,
            comparison_weeks=comparison_weeks,
        )
    except ValueError as exc:
        return error_response(exc)

    filter_str = f" in {country}" if country else ""

    extra: dict[str, Any] = {}
    if zone_type:
        extra["warning"] = (
            "zone_type filter ignored: orders data has no ZONE_TYPE column."
        )

    if df.empty:
        reason = (
            f"No zones with comparable order volumes{filter_str} over a "
            f"{comparison_weeks}-week window."
        )
        return empty_response(reason)

    top = df.iloc[0]
    top_growth_pct = float(top["growth_pct"]) / 100.0
    summary = (
        f"Top {len(df)} zones by order growth ({comparison_weeks}W comparison)"
        f"{filter_str}: fastest-growing is {top['city']}/{top['zone']} "
        f"({top['country']}) at {top_growth_pct:+.1%} "
        f"({int(top['past_orders'])} → {int(top['current_orders'])} orders)."
    )

    # Flag zones whose baseline volume is so low that the percentage is
    # arithmetic noise. This is *the* classic misread of orders_growth.
    caveats = merge(
        detect_low_denominator(
            df,
            base_col="past_orders",
            threshold=20,
            label=f"orders at L{comparison_weeks}W",
        ),
    )

    return format_response(
        df,
        summary=summary,
        caveats=caveats,
        extra_metadata=extra or None,
    )
