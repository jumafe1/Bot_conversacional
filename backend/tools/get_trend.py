"""
Tool: get_trend

Thin wrapper around ``metrics_repository.get_metric_trend``.

Use when the user asks for the **temporal evolution** of a metric over the
last N weeks (max 9), e.g. "How has Perfect Orders evolved in Chapinero?",
"Turbo Adoption trend in Mexico last 6 weeks", or just "trend for Lead
Penetration" (returns a global weekly average).

Week semantics: relative offsets (L0W_ROLL = most recent, L8W_ROLL = 8 weeks ago).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.repositories.metrics_repository import get_metric_trend
from backend.tools._caveats import detect_high_variance, merge
from backend.tools._utils import empty_response, error_response, format_response

logger = logging.getLogger(__name__)


def handle(arguments: dict[str, Any]) -> dict:
    """Temporal trend of a metric over the last N weeks (max 9).

    Expected arguments:
        metric: str    (required)
        country: str | None
        city: str | None
        zone: str | None
        num_weeks: int = 8
    """
    metric = arguments.get("metric")
    if not metric:
        return error_response("Missing required argument 'metric'.")

    country = arguments.get("country")
    city = arguments.get("city")
    zone = arguments.get("zone")
    num_weeks = int(arguments.get("num_weeks", 8))

    try:
        df = get_metric_trend(
            metric,
            country=country,
            city=city,
            zone=zone,
            num_weeks=num_weeks,
        )
    except ValueError as exc:
        return error_response(exc)

    location = _describe_location(country, city, zone)

    if df.empty:
        reason = (
            f"No trend data for {metric} in {location} over the last "
            f"{num_weeks} weeks."
        )
        return empty_response(reason, metric=metric)

    # Results are ordered by week_number DESC (oldest first -> most recent last).
    first_value = float(df["value"].iloc[0])
    last_value = float(df["value"].iloc[-1])

    if first_value != 0:
        change_pct = (last_value - first_value) / abs(first_value)
        change_str = f"{change_pct:+.1%}"
    else:
        change_str = f"{last_value - first_value:+.3f} abs"

    summary = (
        f"{metric} trend for {location} over last {len(df)} weeks: "
        f"{first_value:.3f} (oldest) → {last_value:.3f} (most recent) "
        f"({change_str})."
    )

    # Flag volatile series so the bot doesn't claim a "trend" where there
    # isn't one. Threshold 0.3 is conservative — it fires when stdev is
    # at least 30% of the mean.
    caveats = merge(
        detect_high_variance(df["value"], threshold=0.3, label="weekly series"),
    )

    return format_response(df, summary=summary, metric=metric, caveats=caveats)


def _describe_location(
    country: str | None, city: str | None, zone: str | None
) -> str:
    parts = [p for p in (zone, city, country) if p]
    return ", ".join(parts) if parts else "global weekly average"
