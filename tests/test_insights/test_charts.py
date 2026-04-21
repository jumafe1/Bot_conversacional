"""
Smoke tests for backend.insights.charts.

We don't visually compare images — we just verify each renderer produces a
non-empty, valid-looking base64 PNG when fed real data, and returns None
gracefully when the inputs are empty or malformed.
"""

from __future__ import annotations

import base64

import pandas as pd
import pytest

from backend.insights.analyzer import AnalyzerInputs, analyze
from backend.insights.charts import (
    render_anomalies,
    render_benchmarks,
    render_correlation_heatmap,
    render_opportunities,
    render_regression,
    render_trends,
)
from backend.insights.schemas import CorrelationFinding


@pytest.fixture(scope="module")
def real_inputs() -> AnalyzerInputs:
    from backend.repositories.database import db

    db.connect()
    return AnalyzerInputs(
        metrics_wide=db.execute("SELECT * FROM metrics_wide").fetchdf(),
        metrics_long=db.execute("SELECT * FROM metrics_long").fetchdf(),
        orders_wide=db.execute("SELECT * FROM orders_wide").fetchdf(),
    )


@pytest.fixture(scope="module")
def analysis(real_inputs: AnalyzerInputs):
    return analyze(real_inputs)


def _assert_png_base64(s: str | None) -> None:
    assert s is not None and len(s) > 1000, "PNG base64 should be non-trivial"
    raw = base64.b64decode(s)
    # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
    assert raw.startswith(b"\x89PNG\r\n\x1a\n"), "not a valid PNG"


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------


def test_render_anomalies_real_data(real_inputs: AnalyzerInputs, analysis) -> None:
    png = render_anomalies(analysis.anomalies, real_inputs.metrics_wide)
    _assert_png_base64(png)


def test_render_anomalies_returns_none_on_empty() -> None:
    assert render_anomalies([], pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def test_render_trends_real_data(real_inputs: AnalyzerInputs, analysis) -> None:
    png = render_trends(analysis.trends, real_inputs.metrics_long)
    # May be None if no significant trends found; else must be a valid PNG.
    if analysis.trends:
        _assert_png_base64(png)
    else:
        assert png is None


def test_render_trends_empty() -> None:
    assert render_trends([], pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def test_render_benchmarks_real_data(real_inputs: AnalyzerInputs, analysis) -> None:
    png = render_benchmarks(analysis.benchmarks, real_inputs.metrics_wide)
    if analysis.benchmarks:
        _assert_png_base64(png)
    else:
        assert png is None


# ---------------------------------------------------------------------------
# Correlation heatmap
# ---------------------------------------------------------------------------


def test_render_correlation_heatmap_real_data(
    real_inputs: AnalyzerInputs,
) -> None:
    png = render_correlation_heatmap(real_inputs.metrics_wide)
    _assert_png_base64(png)


def test_render_correlation_heatmap_empty() -> None:
    assert render_correlation_heatmap(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Regression of top correlation
# ---------------------------------------------------------------------------


def test_render_regression_real_data(
    real_inputs: AnalyzerInputs, analysis
) -> None:
    top = analysis.correlations[0] if analysis.correlations else None
    png = render_regression(top, real_inputs.metrics_wide)
    if top is not None:
        _assert_png_base64(png)
    else:
        assert png is None


def test_render_regression_none_safe() -> None:
    assert render_regression(None, pd.DataFrame()) is None


def test_render_regression_unknown_metrics() -> None:
    """If the CorrelationFinding references metrics not in the pivot, return None."""
    fake = CorrelationFinding(
        metric_a="MetricX", metric_b="MetricY",
        r=0.8, n=50, p_value=0.001,
        intercept=0.0, slope=0.5, r_squared=0.64,
    )
    # Empty-ish frame (no L0W_ROLL column triggers the first guard anyway).
    assert render_regression(fake, pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


def test_render_opportunities_real_data(analysis) -> None:
    png = render_opportunities(analysis.opportunities)
    if analysis.opportunities:
        _assert_png_base64(png)
    else:
        assert png is None


def test_render_opportunities_empty() -> None:
    assert render_opportunities([]) is None
