"""
Tool: aggregate

Computes aggregate statistics (avg, min, max, sum, count) of a metric
grouped by a dimension. Called for queries like "average Perfect Orders by country"
or "top 5 zones by Turbo Adoption".

Expected arguments:
    metric   : str
    agg_func : "avg" | "min" | "max" | "sum" | "count"
    group_by : str
    top_n    : int | None
    period   : str | None

Returns:
    list[dict] — one row per group: {group_value, agg_func, value, count}.

TODO:
    1. Map agg_func string to SQL aggregate function.
    2. Call MetricsRepository.get_metric_aggregation().
    3. If top_n is set, limit results to top_n rows sorted descending.
    4. Return as list[dict].
"""

from __future__ import annotations

from typing import Any


async def handle(arguments: dict[str, Any]) -> list[dict]:
    """Execute the aggregate tool.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError
