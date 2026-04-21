"""
Central tool registry.

Maps each tool name to its OpenAI-compatible JSON schema **and** its Python
handler. The LLMService consumes ``get_openai_tools_schema()`` to populate
the ``tools`` argument sent to the provider. The BotService dispatches
``tool_call`` responses to the correct handler via ``dispatch()``.

Handlers are synchronous and return the uniform dict:

    { "summary": str, "data": list[dict], "metadata": dict }

``dispatch`` never raises: unknown tools and internal exceptions are
packaged into a structured error response so the LLM can recover on its
next turn.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.prompts.metric_dictionary import METRIC_DICTIONARY
from backend.repositories.metrics_repository import (
    VALID_COUNTRIES,
    VALID_WEEK_COLS,
    VALID_ZONE_PRIORITIZATIONS,
    VALID_ZONE_TYPES,
)
from backend.tools import (
    aggregate,
    compare_metrics,
    filter_zones,
    get_trend,
    multivariate,
    orders_growth,
)

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], dict]

# ---------------------------------------------------------------------------
# Shared enums — single source of truth for schemas + runtime validation
# ---------------------------------------------------------------------------

_METRICS = sorted(METRIC_DICTIONARY.keys())
_COUNTRIES = sorted(VALID_COUNTRIES)
_ZONE_TYPES = sorted(VALID_ZONE_TYPES)
_ZONE_PRIORITIZATIONS = sorted(VALID_ZONE_PRIORITIZATIONS)
_WEEKS = sorted(VALID_WEEK_COLS)
_OPERATORS = [">", ">=", "<", "<=", "==", "!="]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOLS_REGISTRY: dict[str, dict] = {
    "filter_zones": {
        "schema": {
            "type": "function",
            "function": {
                "name": "filter_zones",
                "description": (
                    "Rank zones by a single metric (top-N or bottom-N). "
                    "Use for queries like: 'top 5 zones by Lead Penetration in CO', "
                    "'worst Perfect Orders in Mexico', 'highest Gross Profit UE in "
                    "wealthy zones', 'lowest Turbo Adoption'. Returns up to `limit` "
                    "zones sorted asc or desc by the metric value for the chosen week."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": _METRICS,
                            "description": "Metric to rank by. Must be one of the canonical names in METRIC_DICTIONARY.",
                        },
                        "country": {
                            "type": "string",
                            "enum": _COUNTRIES,
                            "description": "Optional 2-letter ISO country code.",
                        },
                        "zone_type": {
                            "type": "string",
                            "enum": _ZONE_TYPES,
                            "description": "Optional zone type filter.",
                        },
                        "zone_prioritization": {
                            "type": "string",
                            "enum": _ZONE_PRIORITIZATIONS,
                            "description": "Optional strategic prioritization tier.",
                        },
                        "week": {
                            "type": "string",
                            "enum": _WEEKS,
                            "description": (
                                "Week offset column. L0W_ROLL = most recent, "
                                "L8W_ROLL = 8 weeks ago. Defaults to L0W_ROLL."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "How many zones to return (default 5).",
                        },
                        "order": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "description": "'desc' for highest first (default), 'asc' for lowest first.",
                        },
                    },
                    "required": ["metric"],
                },
            },
        },
        "handler": filter_zones.handle,
    },
    "compare_metrics": {
        "schema": {
            "type": "function",
            "function": {
                "name": "compare_metrics",
                "description": (
                    "Compare a single metric across groups (zone_type, country, or "
                    "zone_prioritization). Use for side-by-side queries like: "
                    "'Wealthy vs Non Wealthy Perfect Orders in Mexico', 'Pro Adoption "
                    "across countries', 'High Priority vs Not Prioritized zones for "
                    "Lead Penetration'. Returns aggregate stats (mean, median, min, "
                    "max, std) per group."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": _METRICS,
                            "description": "Metric to compare across groups.",
                        },
                        "group_by": {
                            "type": "string",
                            "enum": ["zone_type", "zone_prioritization", "country"],
                            "description": (
                                "Dimension to group by. Use 'country' for cross-market "
                                "comparisons, 'zone_type' for Wealthy vs Non Wealthy, "
                                "'zone_prioritization' for priority-tier analysis."
                            ),
                        },
                        "country": {
                            "type": "string",
                            "enum": _COUNTRIES,
                            "description": (
                                "Optional country filter. Leave empty when group_by='country'."
                            ),
                        },
                        "week": {
                            "type": "string",
                            "enum": _WEEKS,
                            "description": "Week offset column (default L0W_ROLL).",
                        },
                    },
                    "required": ["metric", "group_by"],
                },
            },
        },
        "handler": compare_metrics.handle,
    },
    "get_trend": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_trend",
                "description": (
                    "Return the week-by-week evolution of a metric over the last "
                    "N weeks (up to 9). Use for queries like: 'Perfect Orders trend "
                    "in Chapinero', 'Turbo Adoption over the last 6 weeks in MX', "
                    "'Lead Penetration trend globally', 'how has Gross Profit UE "
                    "evolved?'. Without geographic filters, returns a weekly average "
                    "across all matching zones."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": _METRICS,
                            "description": "Metric to track over time.",
                        },
                        "country": {
                            "type": "string",
                            "enum": _COUNTRIES,
                            "description": "Optional country filter.",
                        },
                        "city": {
                            "type": "string",
                            "description": "Optional city name (exact match).",
                        },
                        "zone": {
                            "type": "string",
                            "description": (
                                "Optional zone name (exact match). Combine with "
                                "country + city for uniqueness."
                            ),
                        },
                        "num_weeks": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 9,
                            "description": "Number of most-recent weeks to return (default 8, max 9).",
                        },
                    },
                    "required": ["metric"],
                },
            },
        },
        "handler": get_trend.handle,
    },
    "aggregate": {
        "schema": {
            "type": "function",
            "function": {
                "name": "aggregate",
                "description": (
                    "Compute a summary statistic (mean, median, sum, min, max, "
                    "count) of a metric, optionally grouped by a dimension. "
                    "Use for queries like: 'average Perfect Orders across all "
                    "zones', 'median Turbo Adoption by country', 'max Gross Profit "
                    "UE by city', 'how many zones track Pro Adoption'. Without "
                    "`group_by`, returns a single global aggregate row."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": _METRICS,
                            "description": "Metric to aggregate.",
                        },
                        "agg": {
                            "type": "string",
                            "enum": ["mean", "median", "sum", "min", "max", "count"],
                            "description": "Aggregation function (default 'mean').",
                        },
                        "group_by": {
                            "type": "string",
                            "enum": ["country", "city", "zone_type", "zone_prioritization"],
                            "description": (
                                "Optional grouping dimension. Omit for a single global value."
                            ),
                        },
                        "week": {
                            "type": "string",
                            "enum": _WEEKS,
                            "description": "Week offset column (default L0W_ROLL).",
                        },
                    },
                    "required": ["metric"],
                },
            },
        },
        "handler": aggregate.handle,
    },
    "multivariate": {
        "schema": {
            "type": "function",
            "function": {
                "name": "multivariate",
                "description": (
                    "Find zones satisfying multiple metric conditions simultaneously "
                    "(AND logic). Use for complex multi-criteria queries like: "
                    "'zones where Lead Penetration > 0.5 AND Perfect Orders < 0.85 "
                    "in CO', 'low Pro Adoption (<0.05) and high Gross Profit UE (>5)'. "
                    "Returns one row per matching zone with all requested metric "
                    "values pivoted into columns."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conditions": {
                            "type": "array",
                            "minItems": 1,
                            "description": (
                                "List of metric conditions; all are ANDed together."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "metric": {
                                        "type": "string",
                                        "enum": _METRICS,
                                        "description": "Metric name.",
                                    },
                                    "op": {
                                        "type": "string",
                                        "enum": _OPERATORS,
                                        "description": "Comparison operator.",
                                    },
                                    "value": {
                                        "type": "number",
                                        "description": "Numeric threshold to compare against.",
                                    },
                                },
                                "required": ["metric", "op", "value"],
                            },
                        },
                        "country": {
                            "type": "string",
                            "enum": _COUNTRIES,
                            "description": "Optional country filter.",
                        },
                        "week": {
                            "type": "string",
                            "enum": _WEEKS,
                            "description": "Week offset column (default L0W_ROLL).",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Max zones to return (default 20).",
                        },
                    },
                    "required": ["conditions"],
                },
            },
        },
        "handler": multivariate.handle,
    },
    "orders_growth": {
        "schema": {
            "type": "function",
            "function": {
                "name": "orders_growth",
                "description": (
                    "Rank zones by order volume growth between the most recent week "
                    "(L0W) and a past week (L{comparison_weeks}W). Use for queries "
                    "like: 'fastest-growing zones in Colombia', 'top 10 zones by "
                    "order growth over 5 weeks', 'which zones are expanding demand?'. "
                    "Returns zones sorted by growth_pct DESC. NOTE: this tool uses "
                    "raw order counts, not metrics — it does not accept a `metric` "
                    "argument."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "enum": _COUNTRIES,
                            "description": "Optional country filter.",
                        },
                        "zone_type": {
                            "type": "string",
                            "enum": _ZONE_TYPES,
                            "description": (
                                "Accepted but IGNORED: orders data has no ZONE_TYPE column."
                            ),
                        },
                        "top_n": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Number of top-growing zones to return (default 10).",
                        },
                        "comparison_weeks": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "description": (
                                "Which past week to compare L0W against (1–8). Default 5."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        },
        "handler": orders_growth.handle,
    },
}


# ---------------------------------------------------------------------------
# Public API consumed by LLMService / BotService
# ---------------------------------------------------------------------------

def get_openai_tools_schema() -> list[dict]:
    """Return the list of tool schemas in OpenAI function-calling format."""
    return [entry["schema"] for entry in TOOLS_REGISTRY.values()]


def dispatch(tool_name: str, arguments: dict[str, Any]) -> dict:
    """Look up ``tool_name`` and invoke its handler.

    Never raises. Unknown tools and unexpected handler errors are converted
    into the standard structured error response so the LLM can self-correct.
    """
    entry = TOOLS_REGISTRY.get(tool_name)
    if entry is None:
        return {
            "summary": f"Unknown tool: {tool_name}",
            "data": [],
            "metadata": {
                "error": True,
                "reason": f"Tool '{tool_name}' is not registered.",
                "total_count": 0,
                "truncated": False,
            },
        }
    handler: ToolHandler = entry["handler"]
    try:
        return handler(arguments or {})
    except Exception as exc:  # noqa: BLE001 — convert to structured response
        logger.exception("Tool '%s' raised an unexpected error", tool_name)
        return {
            "summary": f"Tool error in '{tool_name}': {exc}",
            "data": [],
            "metadata": {
                "error": True,
                "reason": str(exc),
                "total_count": 0,
                "truncated": False,
            },
        }
