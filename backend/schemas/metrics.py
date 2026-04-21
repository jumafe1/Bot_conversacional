"""
Pydantic models representing metric data returned by the repository layer.

These are used by tool handlers to type-check results before passing them
back to the LLM as structured tool responses.

TODO:
    - Align field names with actual column names in the parquet files
      once clean_data.py is implemented and schema is finalized.
    - Add validators for percentage fields (0.0–1.0 or 0–100 range).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ZoneMetricRow(BaseModel):
    """One row of metric data for a single zone at a point in time."""

    country: str
    zone_id: str
    zone_name: str
    metric_name: str
    metric_value: float
    period: date | None = None


class MetricSummary(BaseModel):
    """Aggregated metric result (output of aggregate or compare tools)."""

    metric_name: str
    group_by: str = Field(description="Dimension used for grouping (e.g., 'country').")
    group_value: str
    avg_value: float
    min_value: float
    max_value: float
    count: int


class TrendPoint(BaseModel):
    """Single data point in a time-series trend."""

    period: date
    metric_value: float
    zone_id: str | None = None
    country: str | None = None
