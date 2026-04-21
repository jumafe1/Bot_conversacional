"""
Unit tests for ``backend.insights.analyzer``.

Every detector is tested with **synthetic DataFrames** so the assertions
are exact — there's no dependency on DuckDB or the real parquets. A couple
of integration-style tests at the bottom run against the actual parquets
just to ensure the shapes line up end to end.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.insights.analyzer import (
    ANOMALY_DELTA_THRESHOLD,
    AnalyzerInputs,
    _detect_anomalies,
    _detect_benchmark_outliers,
    _detect_correlations,
    _detect_declining_trends,
    _detect_opportunities,
    analyze,
)
from backend.insights.schemas import (
    AnomalyFinding,
    BenchmarkFinding,
    CorrelationFinding,
    OpportunityFinding,
    TrendFinding,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------


def _wide_row(
    country: str = "CO",
    city: str = "Bogota",
    zone: str = "Chapinero",
    zone_type: str = "Wealthy",
    zone_prioritization: str = "Prioritized",
    metric: str = "Perfect Orders",
    values: list[float] | None = None,
    is_outlier: bool = False,
) -> dict:
    vals = values or [0.9] * 9
    row = {
        "COUNTRY": country,
        "CITY": city,
        "ZONE": zone,
        "ZONE_TYPE": zone_type,
        "ZONE_PRIORITIZATION": zone_prioritization,
        "METRIC": metric,
        "is_scale_outlier": is_outlier,
    }
    for i, v in enumerate(vals):
        row[f"L{i}W_ROLL"] = v
    return row


def _long_series(
    country: str,
    city: str,
    zone: str,
    metric: str,
    values: list[float | None],
) -> pd.DataFrame:
    """Build a metrics_long-style frame for one (zone, metric) series."""
    rows = []
    for week, v in enumerate(values):
        if v is None:
            continue
        rows.append(
            {
                "COUNTRY": country,
                "CITY": city,
                "ZONE": zone,
                "METRIC": metric,
                "week_number": week,
                "week_offset": -week,
                "value": v,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Detector 1 — Anomalies
# ---------------------------------------------------------------------------


def test_anomalies_flags_large_wow_delta() -> None:
    mw = pd.DataFrame(
        [
            _wide_row(zone="A", values=[0.70, 0.90] + [0.90] * 7),  # -22% WoW
            _wide_row(zone="B", values=[0.91, 0.90] + [0.90] * 7),  # +1% (not flagged)
            _wide_row(zone="C", values=[1.20, 1.00] + [1.00] * 7),  # +20% WoW
        ]
    )
    findings = _detect_anomalies(mw)
    assert len(findings) == 2
    assert [f.zone for f in findings] == ["A", "C"]  # sorted by |delta|
    assert findings[0].direction == "down"
    assert findings[1].direction == "up"
    assert all(isinstance(f, AnomalyFinding) for f in findings)


def test_anomalies_handles_zero_previous_safely() -> None:
    mw = pd.DataFrame(
        [
            _wide_row(zone="A", values=[0.5, 0.0] + [0.0] * 7),  # division by zero
            _wide_row(zone="B", values=[0.8, 0.5] + [0.5] * 7),  # +60% normal flag
        ]
    )
    findings = _detect_anomalies(mw)
    assert [f.zone for f in findings] == ["B"]


def test_anomalies_ignores_nans() -> None:
    import numpy as np

    mw = pd.DataFrame(
        [
            _wide_row(zone="A", values=[np.nan, 0.9] + [0.9] * 7),
            _wide_row(zone="B", values=[1.2, np.nan] + [0.9] * 7),
            _wide_row(zone="C", values=[0.7, 0.9] + [0.9] * 7),
        ]
    )
    findings = _detect_anomalies(mw)
    assert [f.zone for f in findings] == ["C"]


def test_anomalies_excludes_scale_outliers_via_analyze() -> None:
    """The ``analyze`` entry point drops is_scale_outlier rows before any detector."""
    mw = pd.DataFrame(
        [
            _wide_row(zone="A", values=[0.7, 0.9] + [0.9] * 7, is_outlier=True),
            _wide_row(zone="B", values=[0.7, 0.9] + [0.9] * 7, is_outlier=False),
        ]
    )
    # Empty metrics_long is fine — trends detector will return [].
    result = analyze(AnalyzerInputs(metrics_wide=mw, metrics_long=pd.DataFrame()))
    zones = {f.zone for f in result.anomalies}
    assert zones == {"B"}


def test_anomalies_delta_matches_threshold_constant() -> None:
    # Just above and just below the threshold.
    eps = 0.001
    above = 1 + ANOMALY_DELTA_THRESHOLD + eps
    below = 1 + ANOMALY_DELTA_THRESHOLD - eps
    mw = pd.DataFrame(
        [
            _wide_row(zone="A", values=[above, 1.0] + [1.0] * 7),
            _wide_row(zone="B", values=[below, 1.0] + [1.0] * 7),
        ]
    )
    findings = _detect_anomalies(mw)
    assert [f.zone for f in findings] == ["A"]


# ---------------------------------------------------------------------------
# Detector 2 — Declining trends
# ---------------------------------------------------------------------------


def test_trend_flags_significant_decline() -> None:
    # Monotonically decreasing (newest is lowest).
    # week_number=0 is most recent. In reverse-chronological values list:
    values = [0.70, 0.73, 0.77, 0.80, 0.82, 0.85, 0.88, 0.91, 0.94]
    ml = _long_series("CO", "Bogota", "Chapinero", "Perfect Orders", values)
    findings = _detect_declining_trends(ml)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, TrendFinding)
    assert f.slope < 0
    assert f.p_value < 0.05
    assert f.r_squared > 0.9  # nearly linear
    assert f.current_value == 0.70
    assert f.first_value == 0.94


def test_trend_ignores_stable_series() -> None:
    values = [0.80] * 9
    ml = _long_series("CO", "Bogota", "Chapinero", "Perfect Orders", values)
    assert _detect_declining_trends(ml) == []


def test_trend_ignores_improving_series() -> None:
    values = [0.94, 0.91, 0.88, 0.85, 0.82, 0.80, 0.77, 0.73, 0.70]
    ml = _long_series("CO", "Bogota", "Chapinero", "Perfect Orders", values)
    assert _detect_declining_trends(ml) == []


def test_trend_ignores_series_with_too_few_points() -> None:
    # Only 5 non-null points — below TREND_MIN_POINTS=6.
    values = [0.70, 0.80, 0.85, 0.90, 0.95, None, None, None, None]
    ml = _long_series("CO", "Bogota", "Chapinero", "Perfect Orders", values)
    assert _detect_declining_trends(ml) == []


# ---------------------------------------------------------------------------
# Detector 3 — Benchmark outliers
# ---------------------------------------------------------------------------


def test_benchmark_flags_zones_below_peers() -> None:
    # Six Wealthy zones in CO: five near 0.90, one at 0.40 (~ -3σ below).
    rows = [
        _wide_row(zone=f"Z{i}", values=[0.90 + i * 0.005] + [0.9] * 8)
        for i in range(5)
    ]
    rows.append(_wide_row(zone="OUTLIER", values=[0.40] + [0.9] * 8))
    mw = pd.DataFrame(rows)

    findings = _detect_benchmark_outliers(mw)
    assert len(findings) == 1
    assert findings[0].zone == "OUTLIER"
    assert findings[0].z_score <= -1.5
    assert findings[0].peer_count >= 5
    assert isinstance(findings[0], BenchmarkFinding)


def test_benchmark_silent_when_peer_group_too_small() -> None:
    # Only 4 peers — below BENCHMARK_MIN_PEERS=5.
    rows = [
        _wide_row(zone=f"Z{i}", values=[0.90] + [0.9] * 8) for i in range(3)
    ]
    rows.append(_wide_row(zone="OUTLIER", values=[0.40] + [0.9] * 8))
    mw = pd.DataFrame(rows)
    assert _detect_benchmark_outliers(mw) == []


# ---------------------------------------------------------------------------
# Detector 4 — Correlations
# ---------------------------------------------------------------------------


def test_correlations_flags_strong_pair() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 50
    base = rng.normal(0.5, 0.1, n)
    noise = rng.normal(0, 0.02, n)
    rows = []
    for i in range(n):
        rows.append(
            _wide_row(zone=f"Z{i}", metric="MetricA", values=[base[i]] + [0.9] * 8)
        )
        rows.append(
            _wide_row(
                zone=f"Z{i}",
                metric="MetricB",
                values=[base[i] * 0.8 + noise[i]] + [0.9] * 8,
            )
        )
    mw = pd.DataFrame(rows)

    findings = _detect_correlations(mw)
    assert len(findings) >= 1
    top = findings[0]
    assert isinstance(top, CorrelationFinding)
    assert abs(top.r) >= 0.5
    assert top.n >= 10
    assert 0 <= top.r_squared <= 1.0


def test_correlations_ignores_uncorrelated_pairs() -> None:
    import numpy as np

    rng = np.random.default_rng(1)
    n = 30
    rows = []
    for i in range(n):
        rows.append(
            _wide_row(
                zone=f"Z{i}", metric="A", values=[float(rng.normal())] + [0.9] * 8
            )
        )
        rows.append(
            _wide_row(
                zone=f"Z{i}", metric="B", values=[float(rng.normal())] + [0.9] * 8
            )
        )
    mw = pd.DataFrame(rows)
    assert _detect_correlations(mw) == []


# ---------------------------------------------------------------------------
# Detector 5 — Opportunities
# ---------------------------------------------------------------------------


def test_opportunities_flags_positive_momentum_above_p25() -> None:
    # One zone at 0.90 with +20% WoW (above p25 floor); three control zones.
    rows = [
        _wide_row(zone="WINNER", values=[0.90, 0.75] + [0.75] * 7),
        _wide_row(zone="A", values=[0.60, 0.60] + [0.60] * 7),
        _wide_row(zone="B", values=[0.70, 0.70] + [0.70] * 7),
        _wide_row(zone="C", values=[0.80, 0.80] + [0.80] * 7),
    ]
    mw = pd.DataFrame(rows)
    findings = _detect_opportunities(mw)
    zones = {f.zone for f in findings}
    assert "WINNER" in zones
    assert all(isinstance(f, OpportunityFinding) for f in findings)
    assert findings[0].delta_pct > 0


def test_opportunities_skips_noisy_small_base() -> None:
    # Zone with +400% momentum but current value BELOW country p25 → skipped.
    rows = [
        _wide_row(zone="NOISY", values=[0.05, 0.01] + [0.01] * 7),
        _wide_row(zone="A", values=[0.60, 0.60] + [0.60] * 7),
        _wide_row(zone="B", values=[0.70, 0.70] + [0.70] * 7),
        _wide_row(zone="C", values=[0.80, 0.80] + [0.80] * 7),
        _wide_row(zone="D", values=[0.90, 0.90] + [0.90] * 7),
    ]
    mw = pd.DataFrame(rows)
    findings = _detect_opportunities(mw)
    assert "NOISY" not in {f.zone for f in findings}


# ---------------------------------------------------------------------------
# End-to-end integration — uses the real parquets
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_inputs() -> AnalyzerInputs:
    """Pull the processed parquets via DuckDB — same source the service uses."""
    from backend.repositories.database import db

    db.connect()
    metrics_wide = db.execute("SELECT * FROM metrics_wide").fetchdf()
    metrics_long = db.execute("SELECT * FROM metrics_long").fetchdf()
    orders_wide = db.execute("SELECT * FROM orders_wide").fetchdf()
    return AnalyzerInputs(
        metrics_wide=metrics_wide,
        metrics_long=metrics_long,
        orders_wide=orders_wide,
    )


def test_analyze_real_data_returns_reasonable_counts(
    real_inputs: AnalyzerInputs,
) -> None:
    result = analyze(real_inputs)
    assert result.metadata.total_zones > 100
    assert len(result.metadata.countries) == 9
    assert result.metadata.n_metrics == 13
    # We expect the real dataset to produce SOMETHING in each category,
    # otherwise the analyser is either too strict or broken.
    assert len(result.anomalies) > 0
    assert len(result.benchmarks) > 0
    assert len(result.correlations) > 0
    # Trends and opportunities are more selective (need significance + quartile
    # floor). They may be empty in edge cases but usually aren't.


def test_analyze_respects_top_n_caps(real_inputs: AnalyzerInputs) -> None:
    result = analyze(real_inputs)
    assert len(result.anomalies) <= 10
    assert len(result.trends) <= 10
    assert len(result.benchmarks) <= 10
    assert len(result.correlations) <= 5
    assert len(result.opportunities) <= 10
