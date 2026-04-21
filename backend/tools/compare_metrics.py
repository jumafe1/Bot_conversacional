"""
Tool: compare_metrics

Compares a metric across countries, zone types, or cities.
Called when the user asks "how does Colombia compare to Brazil on Perfect Orders?"
or "which country has the best Pro Adoption?".

Expected arguments:
    metric   : str — metric name
    group_by : str — "country" | "zone_type" | "city"
    period   : str | None

Returns:
    list[dict] — one row per group with {group_value, avg, min, max, count}.

TODO:
    1. Call MetricsRepository.get_metric_by_group().
    2. Sort results descending by avg for readability.
    3. Return as list[dict].
"""

from __future__ import annotations

from typing import Any


async def handle(arguments: dict[str, Any]) -> list[dict]:
    """Execute the compare_metrics tool.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError
