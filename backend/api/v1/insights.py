"""
Insights endpoints — the automatically-generated executive report plus the
interactive per-section filtering surface.

Routes:
    POST /api/v1/insights/generate
        Build (or return cached) full report with default filters.
        Query: refresh: bool — bypass the service cache.

    POST /api/v1/insights/sections/{section_id}/recompute
        Re-run ONE detector with user-chosen filters. Returns findings +
        chart only (narrative stays unchanged on the client).

    POST /api/v1/insights/sections/{section_id}/refresh-narrative
        Re-run the narrator for ONE section with the user's current
        filters + on-screen findings. Does NOT recompute the analysis.

    GET  /api/v1/insights/filter-options
        Canonical lists (metrics, countries, peer groups) so the UI can
        populate its selects from a single source of truth.

The heavy lifting lives in ``backend.insights.service``; this module is the
thin HTTP boundary.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from backend.core.exceptions import LLMProviderError
from backend.insights.schemas import (
    AnomaliesFilters,
    BenchmarksFilters,
    CorrelationsFilters,
    FilterOptions,
    InsightsReport,
    OpportunitiesFilters,
    SectionNarrative,
    SectionNarrativeRefreshRequest,
    SectionRecomputeResponse,
    TrendsFilters,
)
from backend.insights.service import InsightsService
from backend.prompts.metric_dictionary import METRIC_DICTIONARY
from backend.repositories.metrics_repository import VALID_COUNTRIES

router = APIRouter()
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_insights_service() -> InsightsService:
    """Process-wide singleton InsightsService.

    Overridable via ``app.dependency_overrides`` in tests.
    """
    return InsightsService()


ServiceDep = Annotated[InsightsService, Depends(get_insights_service)]


_ERROR_RESPONSES: dict[int | str, dict] = {
    400: {"description": "Invalid filter values."},
    404: {"description": "Unknown section id."},
    500: {"description": "Unexpected internal error while building the report."},
    502: {"description": "LLM provider failed to narrate the findings."},
}

_VALID_SECTION_IDS: set[str] = {
    "anomalies",
    "trends",
    "benchmarks",
    "correlations",
    "opportunities",
}

# Per-section filter model so we can validate request bodies strictly.
_SECTION_FILTER_TYPES = {
    "anomalies": AnomaliesFilters,
    "trends": TrendsFilters,
    "benchmarks": BenchmarksFilters,
    "correlations": CorrelationsFilters,
    "opportunities": OpportunitiesFilters,
}


# ---------------------------------------------------------------------------
# Full report (existing behaviour, unchanged)
# ---------------------------------------------------------------------------


@router.post("/insights/generate", responses=_ERROR_RESPONSES)
async def generate_insights(
    svc: ServiceDep,
    refresh: bool = False,
) -> InsightsReport:
    """Generate (or return cached) executive insights report."""
    try:
        return await svc.generate(force_refresh=refresh)
    except LLMProviderError as exc:
        logger.error("Insights narrator failed", exc_info=exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Insights generation failed")
        raise HTTPException(
            status_code=500, detail="Internal error while building insights report"
        ) from exc


# ---------------------------------------------------------------------------
# Interactive per-section endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/insights/sections/{section_id}/recompute",
    responses=_ERROR_RESPONSES,
)
def recompute_section(
    svc: ServiceDep,
    section_id: Annotated[str, Path(pattern="^(anomalies|trends|benchmarks|correlations|opportunities)$")],
    filters: Annotated[dict, Body(...)],
) -> SectionRecomputeResponse:
    """Re-run ONE detector with user-chosen filters.

    The request body is the section-appropriate filter dict (validated
    against the matching pydantic model — bad inputs return HTTP 400).
    """
    filter_model = _SECTION_FILTER_TYPES.get(section_id)
    if filter_model is None:
        # Should never happen given the Path pattern, but defensive.
        raise HTTPException(status_code=404, detail=f"Unknown section '{section_id}'")

    try:
        parsed = filter_model(**filters)
    except Exception as exc:  # pydantic ValidationError included
        raise HTTPException(status_code=400, detail=f"Invalid filters: {exc}") from exc

    try:
        return svc.recompute_section(section_id, parsed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Section recompute failed for '%s'", section_id)
        raise HTTPException(
            status_code=500, detail=f"Section '{section_id}' recompute failed"
        ) from exc


@router.post(
    "/insights/sections/{section_id}/refresh-narrative",
    responses=_ERROR_RESPONSES,
)
async def refresh_section_narrative(
    svc: ServiceDep,
    section_id: Annotated[str, Path(pattern="^(anomalies|trends|benchmarks|correlations|opportunities)$")],
    body: SectionNarrativeRefreshRequest,
) -> SectionNarrative:
    """Re-narrate ONE section given current filters + on-screen findings."""
    if section_id not in _VALID_SECTION_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown section '{section_id}'")

    try:
        return await svc.refresh_section_narrative(
            section_id=section_id,
            filters=body.filters,
            findings=body.findings,
        )
    except LLMProviderError as exc:
        logger.error("Narrator refresh failed for '%s'", section_id, exc_info=exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Narrator refresh unexpected error for '%s'", section_id)
        raise HTTPException(
            status_code=500, detail=f"Narrator refresh failed for '{section_id}'"
        ) from exc


# ---------------------------------------------------------------------------
# Static filter options for the UI controls
# ---------------------------------------------------------------------------


@router.get("/insights/filter-options")
def get_filter_options() -> FilterOptions:
    """Return the canonical lists the frontend uses to build its selects."""
    return FilterOptions(
        metrics=sorted(METRIC_DICTIONARY.keys()),
        countries=sorted(VALID_COUNTRIES),
        peer_groups=["zone_type", "zone_prioritization"],
    )
