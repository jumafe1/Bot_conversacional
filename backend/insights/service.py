"""
Orchestrator for the insights report.

Wires the three pure layers (analyzer → charts → narrator) into a single
:class:`InsightsReport` ready for the HTTP endpoint.

Also owns the in-process TTL cache: the report is expensive (matplotlib +
an LLM call, ~10-30s) so we reuse the same report within a short window
rather than regenerating on every hit.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.insights import sections as section_ops
from backend.insights.analyzer import AnalyzerInputs, analyze
from backend.insights.charts import (
    render_anomalies,
    render_benchmarks,
    render_opportunities,
    render_regression,
    render_trends,
)
from backend.insights.narrator import narrate, narrate_single_section
from backend.insights.schemas import (
    AnalysisResult,
    AnomaliesFilters,
    BenchmarksFilters,
    CorrelationsFilters,
    InsightsReport,
    InsightsSection,
    NarratorOutput,
    OpportunitiesFilters,
    SectionNarrative,
    SectionRecomputeResponse,
    TrendsFilters,
)
from backend.repositories.database import db

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=10)

SECTION_TITLES: dict[str, str] = {
    "anomalies": "Anomalías (cambios semana a semana)",
    "trends": "Tendencias preocupantes",
    "benchmarks": "Benchmarking vs. peer group",
    "correlations": "Correlaciones entre métricas",
    "opportunities": "Oportunidades",
}


class InsightsService:
    """High-level API consumed by ``api/v1/insights.py``."""

    def __init__(self) -> None:
        self._cache: tuple[InsightsReport, datetime] | None = None

    async def generate(self, *, force_refresh: bool = False) -> InsightsReport:
        """Return the report, using cache when available.

        Args:
            force_refresh: bypass the cache and rebuild from scratch.
        """
        if not force_refresh:
            cached = self._cached_report()
            if cached is not None:
                logger.info("insights_service: served cached report")
                return cached

        logger.info("insights_service: generating fresh report")
        inputs = _load_inputs()
        analysis = analyze(inputs)
        narrative = await narrate(analysis)
        report = _assemble_report(analysis, narrative, inputs)

        self._cache = (report, datetime.now(UTC))
        return report

    def invalidate(self) -> None:
        """Drop the cached report (hook for admin endpoints / tests)."""
        self._cache = None

    # ------------------------------------------------------------------
    # Interactive per-section recompute
    # ------------------------------------------------------------------

    def recompute_section(
        self,
        section_id: str,
        filters: AnomaliesFilters
        | TrendsFilters
        | BenchmarksFilters
        | CorrelationsFilters
        | OpportunitiesFilters,
    ) -> SectionRecomputeResponse:
        """Run ONE section's detector + chart renderer with user filters.

        Does NOT touch the narrative cache — the UI keeps showing the old
        narrative until the user explicitly requests a refresh.
        """
        inputs = _load_inputs()
        mw = inputs.metrics_wide
        # Mirror analyze()'s scale-outlier exclusion so filtered results
        # don't drag the noise that the batch report already filters out.
        if "is_scale_outlier" in mw.columns:
            mw = mw[~mw["is_scale_outlier"].fillna(False)].copy()
        ml = inputs.metrics_long

        if section_id == "anomalies":
            assert isinstance(filters, AnomaliesFilters)
            findings, chart = section_ops.recompute_anomalies(
                mw,
                metric=filters.metric,
                start_week_num=filters.start_week_num,
                end_week_num=filters.end_week_num,
            )
        elif section_id == "trends":
            assert isinstance(filters, TrendsFilters)
            findings, chart = section_ops.recompute_trends(
                ml, metric=filters.metric, num_weeks=filters.num_weeks
            )
        elif section_id == "benchmarks":
            assert isinstance(filters, BenchmarksFilters)
            findings, chart = section_ops.recompute_benchmarks(
                mw, metric=filters.metric, peer_by=filters.peer_by
            )
        elif section_id == "correlations":
            assert isinstance(filters, CorrelationsFilters)
            findings, chart = section_ops.recompute_correlations(
                mw,
                metric_x=filters.metric_x,
                metric_y=filters.metric_y,
                country=filters.country,
            )
        elif section_id == "opportunities":
            assert isinstance(filters, OpportunitiesFilters)
            findings, chart = section_ops.recompute_opportunities(
                mw, metric=filters.metric
            )
        else:
            raise ValueError(f"Unknown section_id '{section_id}'")

        return SectionRecomputeResponse(
            section_id=section_id,  # type: ignore[arg-type]
            findings=[f.model_dump() for f in findings],
            chart_png_base64=chart,
            total_flagged=len(findings),
        )

    async def refresh_section_narrative(
        self,
        section_id: str,
        filters: dict,
        findings: list[dict],
    ) -> SectionNarrative:
        """Re-narrate one section with the user's current filters + findings.

        Delegates to ``narrator.narrate_single_section``. The service does
        not cache these refreshes — each click re-hits the LLM so the user
        sees narration grounded in whatever slice is on screen.
        """
        return await narrate_single_section(
            section_id=section_id,
            filters=filters,
            findings=findings,
        )

    # ------------------------------------------------------------------

    def _cached_report(self) -> InsightsReport | None:
        if self._cache is None:
            return None
        report, generated_at = self._cache
        if datetime.now(UTC) - generated_at > CACHE_TTL:
            return None
        return report


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _load_inputs() -> AnalyzerInputs:
    """Pull the three tables from DuckDB into pandas. Side-effect free."""
    db.connect()
    return AnalyzerInputs(
        metrics_wide=db.execute("SELECT * FROM metrics_wide").fetchdf(),
        metrics_long=db.execute("SELECT * FROM metrics_long").fetchdf(),
        orders_wide=db.execute("SELECT * FROM orders_wide").fetchdf(),
    )


def _assemble_report(
    analysis: AnalysisResult,
    narrative: NarratorOutput,
    inputs: AnalyzerInputs,
) -> InsightsReport:
    """Combine deterministic findings + charts + LLM narrative into the DTO."""
    sections: list[InsightsSection] = [
        _make_section(
            "anomalies",
            narrative.anomalies.narrative,
            narrative.anomalies.recommendation,
            findings=analysis.anomalies,
            chart=render_anomalies(analysis.anomalies, inputs.metrics_wide),
        ),
        _make_section(
            "trends",
            narrative.trends.narrative,
            narrative.trends.recommendation,
            findings=analysis.trends,
            chart=render_trends(analysis.trends, inputs.metrics_long),
        ),
        _make_section(
            "benchmarks",
            narrative.benchmarks.narrative,
            narrative.benchmarks.recommendation,
            findings=analysis.benchmarks,
            chart=render_benchmarks(analysis.benchmarks, inputs.metrics_wide),
        ),
        _make_section(
            "correlations",
            narrative.correlations.narrative,
            narrative.correlations.recommendation,
            findings=analysis.correlations,
            # Use the regression scatter for the headline; heatmap is the
            # complementary view — we return the regression since it's more
            # legible for non-analysts.
            chart=render_regression(
                analysis.correlations[0] if analysis.correlations else None,
                inputs.metrics_wide,
            ),
        ),
        _make_section(
            "opportunities",
            narrative.opportunities.narrative,
            narrative.opportunities.recommendation,
            findings=analysis.opportunities,
            chart=render_opportunities(analysis.opportunities),
        ),
    ]

    return InsightsReport(
        generated_at=datetime.now(UTC),
        data_snapshot={
            "total_zones": analysis.metadata.total_zones,
            "countries": analysis.metadata.countries,
            "n_metrics": analysis.metadata.n_metrics,
            "week_window": analysis.metadata.week_window,
        },
        executive_summary=narrative.executive_summary,
        sections=sections,
    )


def _make_section(
    section_id: str,
    narrative: str,
    recommendation: str,
    *,
    findings: list[Any],
    chart: str | None,
) -> InsightsSection:
    return InsightsSection(
        id=section_id,  # type: ignore[arg-type]  — validated by SectionId literal
        title=SECTION_TITLES[section_id],
        narrative=narrative,
        recommendation=recommendation,
        chart_png_base64=chart,
        findings=[f.model_dump() for f in findings],
        total_flagged=len(findings),
    )
