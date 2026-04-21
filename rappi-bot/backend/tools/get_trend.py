"""
Tool: get_trend

Returns the time-series evolution of a metric for a zone or country.
Called when the user asks "how has Perfect Orders evolved over the last 6 months?"
or "show me the trend for Turbo Adoption in Mexico".

Expected arguments:
    metric       : str
    zone_id      : str | None
    country      : str | None
    start_period : str | None  (YYYY-MM)
    end_period   : str | None  (YYYY-MM)

Returns:
    list[dict] — one row per period: {period, metric_value, zone_id?, country?}.

TODO:
    1. Validate that at least zone_id or country is provided (or return all).
    2. Call MetricsRepository.get_metric_trend().
    3. Sort by period ascending.
    4. Return as list[dict].
"""

from __future__ import annotations

from typing import Any


async def handle(arguments: dict[str, Any]) -> list[dict]:
    """Execute the get_trend tool.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError
