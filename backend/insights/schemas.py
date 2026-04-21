"""
Pydantic models for the insights pipeline.

Contains two families of types:

1. **Findings** — the atomic results of the deterministic analyser.
   There is one subclass per insight category so the fields each
   contains are naturally self-documenting (no option-bags).

2. **Report** — the thing the HTTP endpoint returns: an executive
   summary + one section per category with the LLM-generated narrative,
   a base64 chart, and the raw findings (for the UI to render tables).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Individual finding types
# ---------------------------------------------------------------------------


class AnomalyFinding(BaseModel):
    """A zone whose L0W value jumped by more than ±10% vs L1W for a metric."""

    zone: str
    city: str
    country: str
    metric: str
    current: float
    previous: float
    delta_pct: float  # signed — positive means improvement, negative means deterioration
    direction: Literal["up", "down"]


class TrendFinding(BaseModel):
    """A (zone, metric) series whose 9-week linear trend is significantly declining."""

    zone: str
    city: str
    country: str
    metric: str
    slope: float  # value change per week; < 0 means declining
    p_value: float
    r_squared: float
    first_value: float  # oldest non-null in the window (~8 weeks ago)
    current_value: float  # L0W


class BenchmarkFinding(BaseModel):
    """A zone that is >1.5σ below its (country, zone_type) peer group mean."""

    zone: str
    city: str
    country: str
    zone_type: str
    metric: str
    value: float
    peer_mean: float
    peer_std: float
    z_score: float  # negative
    peer_count: int


class CorrelationFinding(BaseModel):
    """A strong pairwise Pearson correlation between two metrics across zones."""

    metric_a: str
    metric_b: str
    r: float  # in [-1, 1]
    n: int
    p_value: float

    # Simple linear regression metric_b ~ a + b·metric_a, for the headline chart.
    intercept: float
    slope: float
    r_squared: float


class OpportunityFinding(BaseModel):
    """A zone with strong positive WoW momentum on a non-noisy baseline."""

    zone: str
    city: str
    country: str
    metric: str
    current: float
    previous: float
    delta_pct: float  # always positive
    country_p25: float  # quartile threshold used to filter out noise


# ---------------------------------------------------------------------------
# Aggregated analyser output (fed to the narrator + charts)
# ---------------------------------------------------------------------------


class AnalysisMetadata(BaseModel):
    total_zones: int
    countries: list[str]
    n_metrics: int
    week_window: str  # e.g. "L0W_ROLL..L8W_ROLL"


class AnalysisResult(BaseModel):
    metadata: AnalysisMetadata
    anomalies: list[AnomalyFinding]
    trends: list[TrendFinding]
    benchmarks: list[BenchmarkFinding]
    correlations: list[CorrelationFinding]
    opportunities: list[OpportunityFinding]


# ---------------------------------------------------------------------------
# Narrator output (intermediate — not returned directly to the client)
# ---------------------------------------------------------------------------


class SectionNarrative(BaseModel):
    narrative: str
    recommendation: str


class NarratorOutput(BaseModel):
    executive_summary: str
    anomalies: SectionNarrative
    trends: SectionNarrative
    benchmarks: SectionNarrative
    correlations: SectionNarrative
    opportunities: SectionNarrative


# ---------------------------------------------------------------------------
# Report returned by the HTTP endpoint
# ---------------------------------------------------------------------------

SectionId = Literal[
    "anomalies",
    "trends",
    "benchmarks",
    "correlations",
    "opportunities",
]


class InsightsSection(BaseModel):
    """One section of the final report, ready for the UI to render."""

    id: SectionId
    title: str
    narrative: str  # LLM-generated markdown
    recommendation: str  # LLM-generated markdown
    chart_png_base64: str | None = None  # data-URI friendly
    findings: list[dict] = Field(default_factory=list)  # raw top-N rows
    total_flagged: int = 0  # full count before top-N truncation


class InsightsReport(BaseModel):
    """Top-level payload returned by POST /api/v1/insights/generate."""

    model_config = ConfigDict(json_schema_extra={"example_only": True})

    generated_at: datetime
    data_snapshot: dict  # total_zones, n_countries, etc.
    executive_summary: str
    sections: list[InsightsSection]


# ---------------------------------------------------------------------------
# Interactive per-section recompute
# ---------------------------------------------------------------------------


class AnomaliesFilters(BaseModel):
    metric: str
    start_week_num: int = Field(ge=1, le=8)
    end_week_num: int = Field(ge=0, le=7)


class TrendsFilters(BaseModel):
    metric: str
    num_weeks: int = Field(ge=3, le=9)


class BenchmarksFilters(BaseModel):
    metric: str
    peer_by: Literal["zone_type", "zone_prioritization"]


class CorrelationsFilters(BaseModel):
    metric_x: str
    metric_y: str
    country: str | None = None


class OpportunitiesFilters(BaseModel):
    metric: str


class SectionRecomputeResponse(BaseModel):
    """Payload returned by the per-section recompute endpoint."""

    section_id: SectionId
    findings: list[dict] = Field(default_factory=list)
    chart_png_base64: str | None = None
    total_flagged: int = 0


class SectionNarrativeRefreshRequest(BaseModel):
    """Body of the refresh-narrative endpoint.

    The frontend sends the filters + findings currently on screen, and the
    backend re-narrates that exact slice (no recomputation).
    """

    filters: dict
    findings: list[dict] = Field(default_factory=list)


class FilterOptions(BaseModel):
    """Static filter options the frontend needs to build its controls."""

    metrics: list[str]
    countries: list[str]
    peer_groups: list[str]
