"""
Tool: filter_zones

Filters geographic zones by a threshold on a single metric.
Called by the LLM when the user asks for "problematic zones",
"zones below X%", or similar threshold-based questions.

Expected arguments (from the LLM tool call):
    metric    : str   — metric name (key in METRIC_DICTIONARY)
    operator  : str   — one of "<", "<=", ">", ">=", "=="
    threshold : float — threshold value
    country   : str | None
    period    : str | None

Returns:
    list[dict] — list of zone rows matching the condition,
                 each with at least {zone_id, zone_name, country, metric_value}.

TODO:
    1. Import MetricsRepository and call get_zones_by_metric_filter().
    2. Validate that `metric` exists in METRIC_DICTIONARY.
    3. Convert operator string to a safe SQL comparison (no string injection).
    4. Return results serialized as list[dict] (DataFrame.to_dict("records")).
"""

from __future__ import annotations

from typing import Any


async def handle(arguments: dict[str, Any]) -> list[dict]:
    """Execute the filter_zones tool.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError
