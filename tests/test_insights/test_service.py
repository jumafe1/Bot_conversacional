"""Tests for ``backend.insights.service`` and the HTTP endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from httpx import AsyncClient

from backend.api.v1.insights import get_insights_service
from backend.insights.schemas import (
    AnalysisMetadata,
    InsightsReport,
    InsightsSection,
    NarratorOutput,
    SectionNarrative,
)
from backend.insights.service import CACHE_TTL, InsightsService
from backend.main import app

# ---------------------------------------------------------------------------
# Service-level tests — cache behaviour
# ---------------------------------------------------------------------------


def _fake_report() -> InsightsReport:
    return InsightsReport(
        generated_at=datetime.now(UTC),
        data_snapshot={
            "total_zones": 0,
            "countries": [],
            "n_metrics": 0,
            "week_window": "L0W_ROLL..L8W_ROLL",
        },
        executive_summary="",
        sections=[
            InsightsSection(
                id="anomalies", title="x", narrative="n",
                recommendation="r", chart_png_base64=None,
                findings=[], total_flagged=0,
            )
        ],
    )


@pytest.fixture
def service_with_stubs(monkeypatch: pytest.MonkeyPatch) -> InsightsService:
    """InsightsService with analyze/narrate/charts stubbed — no DB, no LLM."""
    from backend.insights import service as service_module

    # _load_inputs would hit DuckDB — stub it out.
    monkeypatch.setattr(
        service_module,
        "_load_inputs",
        lambda: service_module.AnalyzerInputs(
            metrics_wide=pd.DataFrame(),
            metrics_long=pd.DataFrame(),
            orders_wide=pd.DataFrame(),
        ),
    )

    empty_analysis = service_module.AnalysisResult(
        metadata=AnalysisMetadata(
            total_zones=0, countries=[], n_metrics=0,
            week_window="L0W_ROLL..L8W_ROLL",
        ),
        anomalies=[], trends=[], benchmarks=[],
        correlations=[], opportunities=[],
    )
    monkeypatch.setattr(service_module, "analyze", lambda inputs: empty_analysis)

    fake_narrative = NarratorOutput(
        executive_summary="resumen",
        anomalies=SectionNarrative(narrative="n", recommendation="r"),
        trends=SectionNarrative(narrative="n", recommendation="r"),
        benchmarks=SectionNarrative(narrative="n", recommendation="r"),
        correlations=SectionNarrative(narrative="n", recommendation="r"),
        opportunities=SectionNarrative(narrative="n", recommendation="r"),
    )

    async def fake_narrate(_result):  # noqa: ANN001, RUF029
        return fake_narrative

    monkeypatch.setattr(service_module, "narrate", fake_narrate)
    # Disable chart generation — the default implementations work fine on
    # empty frames (return None) but we short-circuit for speed.
    for fn in (
        "render_anomalies",
        "render_benchmarks",
        "render_opportunities",
        "render_regression",
        "render_trends",
    ):
        monkeypatch.setattr(service_module, fn, lambda *a, **kw: None)

    return InsightsService()


async def test_service_builds_report_with_5_sections(
    service_with_stubs: InsightsService,
) -> None:
    report = await service_with_stubs.generate()
    assert isinstance(report, InsightsReport)
    assert [s.id for s in report.sections] == [
        "anomalies", "trends", "benchmarks", "correlations", "opportunities",
    ]
    assert report.executive_summary == "resumen"


async def test_service_caches_report_within_ttl(
    service_with_stubs: InsightsService,
) -> None:
    r1 = await service_with_stubs.generate()
    r2 = await service_with_stubs.generate()
    assert r1 is r2  # exact same object — cache hit


async def test_service_force_refresh_bypasses_cache(
    service_with_stubs: InsightsService,
) -> None:
    r1 = await service_with_stubs.generate()
    r2 = await service_with_stubs.generate(force_refresh=True)
    assert r1 is not r2


async def test_service_expires_cache_after_ttl(
    service_with_stubs: InsightsService,
) -> None:
    r1 = await service_with_stubs.generate()
    # Manually push the cached timestamp past the TTL.
    assert service_with_stubs._cache is not None
    service_with_stubs._cache = (
        service_with_stubs._cache[0],
        datetime.now(UTC) - CACHE_TTL - timedelta(seconds=1),
    )
    r2 = await service_with_stubs.generate()
    assert r1 is not r2


def test_service_invalidate_drops_cache(
    service_with_stubs: InsightsService,
) -> None:
    service_with_stubs._cache = (_fake_report(), datetime.now(UTC))
    service_with_stubs.invalidate()
    assert service_with_stubs._cache is None


# ---------------------------------------------------------------------------
# Endpoint tests — FastAPI integration with stubbed service
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_insights_service():
    svc = MagicMock()
    svc.generate = AsyncMock(return_value=_fake_report())
    app.dependency_overrides[get_insights_service] = lambda: svc
    yield svc
    app.dependency_overrides.pop(get_insights_service, None)


async def test_endpoint_returns_report(
    client: AsyncClient, stub_insights_service
) -> None:
    response = await client.post("/api/v1/insights/generate")
    assert response.status_code == 200
    body = response.json()
    assert "executive_summary" in body
    assert "sections" in body
    stub_insights_service.generate.assert_awaited_once_with(force_refresh=False)


async def test_endpoint_honours_refresh_flag(
    client: AsyncClient, stub_insights_service
) -> None:
    response = await client.post("/api/v1/insights/generate?refresh=true")
    assert response.status_code == 200
    stub_insights_service.generate.assert_awaited_once_with(force_refresh=True)


async def test_endpoint_502_on_llm_error(
    client: AsyncClient, stub_insights_service
) -> None:
    from backend.core.exceptions import LLMProviderError

    stub_insights_service.generate.side_effect = LLMProviderError("boom")
    response = await client.post("/api/v1/insights/generate")
    assert response.status_code == 502


async def test_endpoint_500_on_unexpected_error(
    client: AsyncClient, stub_insights_service
) -> None:
    stub_insights_service.generate.side_effect = RuntimeError("db gone")
    response = await client.post("/api/v1/insights/generate")
    assert response.status_code == 500
