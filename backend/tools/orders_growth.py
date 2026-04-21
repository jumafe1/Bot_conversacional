"""
Tool: orders_growth

Calculates order volume and growth rates (Month-over-Month or Year-over-Year)
for a given zone or country. Called when the user asks about order trends,
GMV evolution, or demand growth.

Expected arguments:
    country     : str | None
    zone_id     : str | None
    period      : str | None
    growth_type : "mom" | "yoy" | "absolute"

Returns:
    list[dict] — one row per period: {period, orders, previous_period_orders, growth_rate}.

TODO:
    1. Call MetricsRepository.get_orders_with_growth().
    2. Compute growth_rate = (current - previous) / previous if growth_type != "absolute".
    3. Return as list[dict].
"""

from __future__ import annotations

from typing import Any


async def handle(arguments: dict[str, Any]) -> list[dict]:
    """Execute the orders_growth tool.

    TODO: implement as described in the module docstring.
    """
    raise NotImplementedError
