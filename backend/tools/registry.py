"""
Central tool registry.

Maps tool names to their OpenAI-compatible JSON schema and Python handler.
The LLMService reads TOOLS_REGISTRY to build the `tools` list sent to the provider.
The BotService dispatches tool_call responses to the correct handler via this registry.

Structure of each entry:
    {
        "schema": { ... },   # OpenAI function-calling schema (name, description, parameters)
        "handler": Callable  # async function(arguments: dict) -> dict | list
    }

TODO:
    - Import all handler functions once they are implemented.
    - Add complete JSON schemas for each tool's parameters.
    - Add a dispatch() helper that looks up a tool by name and calls its handler.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.tools import (
    aggregate,
    compare_metrics,
    filter_zones,
    get_trend,
    multivariate,
    orders_growth,
)

# ---------------------------------------------------------------------------
# Type alias for a handler function
# ---------------------------------------------------------------------------

ToolHandler = Callable[[dict[str, Any]], Any]

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
                    "Filter geographic zones by one or more metric thresholds. "
                    "Returns zones that meet the specified conditions. "
                    "Use this when the user asks for 'problematic zones', "
                    "'zones below X%', or similar threshold-based queries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric name to filter on (from METRIC_DICTIONARY).",
                        },
                        "operator": {
                            "type": "string",
                            "enum": ["<", "<=", ">", ">=", "=="],
                            "description": "Comparison operator.",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Threshold value for the filter.",
                        },
                        "country": {
                            "type": "string",
                            "description": "Optional ISO country code to restrict results.",
                        },
                        "period": {
                            "type": "string",
                            "description": "Optional period filter (e.g., '2024-03', 'last_30d').",
                        },
                    },
                    "required": ["metric", "operator", "threshold"],
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
                    "Compare one or more metrics across countries, zone types, "
                    "or any categorical dimension. Returns a side-by-side summary."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric name to compare.",
                        },
                        "group_by": {
                            "type": "string",
                            "enum": ["country", "zone_type", "city"],
                            "description": "Dimension to group and compare by.",
                        },
                        "period": {
                            "type": "string",
                            "description": "Optional period filter.",
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
                    "Return the time-series evolution of a metric for a given "
                    "zone or country. Use for trend, growth, or 'over time' queries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric name.",
                        },
                        "zone_id": {
                            "type": "string",
                            "description": "Zone identifier (optional if country is provided).",
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code (optional if zone_id is provided).",
                        },
                        "start_period": {
                            "type": "string",
                            "description": "Start of date range (YYYY-MM).",
                        },
                        "end_period": {
                            "type": "string",
                            "description": "End of date range (YYYY-MM).",
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
                    "Compute average, min, max, or sum of a metric grouped by a dimension. "
                    "Use for 'average X by country', 'top 5 zones by Y', etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric name to aggregate.",
                        },
                        "agg_func": {
                            "type": "string",
                            "enum": ["avg", "min", "max", "sum", "count"],
                            "description": "Aggregation function.",
                        },
                        "group_by": {
                            "type": "string",
                            "description": "Dimension to group by.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Return only the top N results (sorted descending).",
                        },
                        "period": {
                            "type": "string",
                            "description": "Optional period filter.",
                        },
                    },
                    "required": ["metric", "agg_func", "group_by"],
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
                    "Query zones using multiple simultaneous metric conditions. "
                    "Use when the user asks about zones that satisfy more than one "
                    "criteria at the same time."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conditions": {
                            "type": "array",
                            "description": "List of filter conditions to apply (AND logic).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "metric": {"type": "string"},
                                    "operator": {
                                        "type": "string",
                                        "enum": ["<", "<=", ">", ">=", "=="],
                                    },
                                    "threshold": {"type": "number"},
                                },
                                "required": ["metric", "operator", "threshold"],
                            },
                        },
                        "country": {
                            "type": "string",
                            "description": "Optional country filter.",
                        },
                        "period": {
                            "type": "string",
                            "description": "Optional period filter.",
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
                    "Calculate order volume and growth rates (MoM, YoY) for a "
                    "given zone or country. Use for 'order growth', 'order trends', "
                    "or 'GMV evolution' queries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country code filter.",
                        },
                        "zone_id": {
                            "type": "string",
                            "description": "Zone identifier filter.",
                        },
                        "period": {
                            "type": "string",
                            "description": "Period filter.",
                        },
                        "growth_type": {
                            "type": "string",
                            "enum": ["mom", "yoy", "absolute"],
                            "description": "Type of growth calculation.",
                        },
                    },
                    "required": [],
                },
            },
        },
        "handler": orders_growth.handle,
    },
}


def get_tool_schemas() -> list[dict]:
    """Return the list of tool schemas in OpenAI function-calling format."""
    return [entry["schema"] for entry in TOOLS_REGISTRY.values()]


async def dispatch(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Look up a tool by name and call its handler with the given arguments.

    TODO: add error handling for unknown tool names (raise ToolExecutionError).
    """
    entry = TOOLS_REGISTRY.get(tool_name)
    if entry is None:
        raise KeyError(f"Unknown tool: {tool_name}")
    return await entry["handler"](arguments)
