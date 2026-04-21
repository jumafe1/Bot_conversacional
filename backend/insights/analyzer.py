"""
Deterministic statistical analyser for the automatic insights report.

This module does **all the number crunching**. The LLM narrator downstream
only receives pre-computed findings and writes prose — it never sees raw
DataFrames and it never does arithmetic.

Five detectors, one per insight category defined in the brief:

    1. Anomalies           — WoW delta > ±10%
    2. Declining trends    — linear regression (9 weeks), slope<0, p<0.05
    3. Benchmark outliers  — z-score < -1.5 vs (country, zone_type) peers
    4. Correlations        — Pearson |r| > 0.5 between the 13 metrics
    5. Opportunities       — positive WoW momentum on a non-noisy base

Inputs are pandas DataFrames so the analyser is pure-ish — completely
testable with synthetic data, no DuckDB dependency. The ``service.py`` layer
is the one that pulls the frames from DuckDB before calling us.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from backend.insights.schemas import (
    AnalysisMetadata,
    AnalysisResult,
    AnomalyFinding,
    BenchmarkFinding,
    CorrelationFinding,
    OpportunityFinding,
    TrendFinding,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration knobs — exposed as module constants so tests can override
# ---------------------------------------------------------------------------

ANOMALY_DELTA_THRESHOLD = 0.10  # ±10% WoW
TREND_P_VALUE_THRESHOLD = 0.05
TREND_MIN_POINTS = 6  # out of 9 weeks; below this the regression isn't reliable
BENCHMARK_Z_THRESHOLD = -1.5
BENCHMARK_MIN_PEERS = 5
CORRELATION_R_THRESHOLD = 0.5
OPPORTUNITY_DELTA_THRESHOLD = 0.10
OPPORTUNITY_MIN_QUARTILE = 0.25  # must be above country p25 so we ignore pure noise

# Two filters shared by anomaly-style detectors. Without these, percentages
# can explode against near-zero bases (Gross Profit UE crossing zero, or
# very small Lead Penetration) and produce nonsense rankings.
MIN_SIGNIFICANT_PREV = 0.01  # ignore rows where |previous| < this
MAX_SENSIBLE_DELTA = 5.0  # cap |delta| at 500% — anything higher is noise

TOP_N_PER_CATEGORY = 10
TOP_N_CORRELATIONS = 5

WEEK_COLS = [f"L{i}W_ROLL" for i in range(9)]  # L0W_ROLL .. L8W_ROLL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class AnalyzerInputs:
    """Bundle the three DataFrames the analyser needs."""

    metrics_wide: pd.DataFrame
    """Columns: COUNTRY, CITY, ZONE, ZONE_TYPE, ZONE_PRIORITIZATION, METRIC,
    L0W_ROLL..L8W_ROLL, is_scale_outlier."""

    metrics_long: pd.DataFrame
    """Columns: COUNTRY, CITY, ZONE, METRIC, week_number (0..8), week_offset,
    value. ``week_number`` is 0 for the most recent week."""

    orders_wide: pd.DataFrame | None = None
    """Optional — not used by the current detectors but reserved for
    extensions (e.g. orders-growth insights)."""


def _safe_delta_pct(current: float, previous: float) -> float | None:
    """Relative change with guards against zero / NaN denominators."""
    if previous is None or np.isnan(previous) or np.isnan(current):
        return None
    if abs(previous) < 1e-9:
        return None
    return (current - previous) / previous


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def analyze(inputs: AnalyzerInputs) -> AnalysisResult:
    """Run every detector and return a structured report.

    The detectors are independent; no shared state between them.
    """
    mw = inputs.metrics_wide
    ml = inputs.metrics_long

    # Exclude scale outliers from every detector. They're noise by definition
    # (see scripts/clean_data.py) and would dominate the top-N rankings.
    if "is_scale_outlier" in mw.columns:
        mw = mw[~mw["is_scale_outlier"].fillna(False)].copy()

    metadata = _build_metadata(mw, ml)
    anomalies = _detect_anomalies(mw)
    trends = _detect_declining_trends(ml)
    benchmarks = _detect_benchmark_outliers(mw)
    correlations = _detect_correlations(mw)
    opportunities = _detect_opportunities(mw)

    logger.info(
        "insights_analyze counts: anomalies=%d trends=%d benchmarks=%d correlations=%d opportunities=%d",
        len(anomalies),
        len(trends),
        len(benchmarks),
        len(correlations),
        len(opportunities),
    )

    return AnalysisResult(
        metadata=metadata,
        anomalies=anomalies,
        trends=trends,
        benchmarks=benchmarks,
        correlations=correlations,
        opportunities=opportunities,
    )


def _build_metadata(mw: pd.DataFrame, ml: pd.DataFrame) -> AnalysisMetadata:
    return AnalysisMetadata(
        total_zones=int(mw[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0]),
        countries=sorted(mw["COUNTRY"].dropna().unique().tolist()),
        n_metrics=int(mw["METRIC"].nunique()),
        week_window="L0W_ROLL..L8W_ROLL",
    )


# ---------------------------------------------------------------------------
# Detector 1 — Anomalies (WoW delta > ±10%)
# ---------------------------------------------------------------------------


def _detect_anomalies(mw: pd.DataFrame) -> list[AnomalyFinding]:
    """Zones whose L0W value shifted by more than ±10% vs L1W for a metric."""
    df = mw.dropna(subset=["L0W_ROLL", "L1W_ROLL"]).copy()

    # Drop near-zero previous values — their % change is mathematically
    # unstable (Gross Profit UE crossing zero is the worst case).
    df = df[df["L1W_ROLL"].abs() >= MIN_SIGNIFICANT_PREV]

    df["delta"] = df.apply(
        lambda r: _safe_delta_pct(r["L0W_ROLL"], r["L1W_ROLL"]), axis=1
    )
    df = df.dropna(subset=["delta"])
    df = df[df["delta"].abs() >= ANOMALY_DELTA_THRESHOLD]
    # Cap at the sensible range; anything past that is numeric noise.
    df = df[df["delta"].abs() <= MAX_SENSIBLE_DELTA]

    df = df.reindex(df["delta"].abs().sort_values(ascending=False).index)
    top = df.head(TOP_N_PER_CATEGORY)

    findings: list[AnomalyFinding] = []
    for _, row in top.iterrows():
        findings.append(
            AnomalyFinding(
                zone=str(row["ZONE"]),
                city=str(row["CITY"]),
                country=str(row["COUNTRY"]),
                metric=str(row["METRIC"]),
                current=float(row["L0W_ROLL"]),
                previous=float(row["L1W_ROLL"]),
                delta_pct=float(row["delta"]) * 100.0,
                direction="up" if row["delta"] > 0 else "down",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Detector 2 — Declining trends (linear regression over 9 weeks)
# ---------------------------------------------------------------------------


def _detect_declining_trends(ml: pd.DataFrame) -> list[TrendFinding]:
    """Series with a statistically significant negative slope.

    ``week_number`` goes 0 (most recent) to 8 (oldest). We flip the axis so
    ``time = 8 - week_number`` increases with time — then a positive slope
    means improvement and a negative slope means deterioration, which is
    the convention users expect.
    """
    required_cols = {"value", "week_number", "COUNTRY", "CITY", "ZONE", "METRIC"}
    if ml.empty or not required_cols.issubset(ml.columns):
        return []

    df = ml.dropna(subset=["value"]).copy()
    df["time"] = 8 - df["week_number"].astype(int)

    results: list[tuple[float, TrendFinding]] = []

    # Group by the full zone+metric identity.
    grouped = df.groupby(["COUNTRY", "CITY", "ZONE", "METRIC"], dropna=True)
    for (country, city, zone, metric), sub in grouped:
        if len(sub) < TREND_MIN_POINTS:
            continue
        xs = sub["time"].to_numpy(dtype=float)
        ys = sub["value"].to_numpy(dtype=float)
        # A degenerate x (all same) or constant y breaks linregress.
        if np.ptp(xs) == 0 or np.ptp(ys) == 0:
            continue
        res = stats.linregress(xs, ys)
        if res.pvalue >= TREND_P_VALUE_THRESHOLD:
            continue
        if res.slope >= 0:
            continue

        # Rank criterion: bigger |t-statistic| ≈ stronger negative trend.
        t_stat = res.slope / res.stderr if res.stderr > 0 else 0.0

        first_value = float(sub.loc[sub["time"].idxmin(), "value"])
        current_value = float(sub.loc[sub["time"].idxmax(), "value"])

        results.append(
            (
                abs(t_stat),
                TrendFinding(
                    zone=str(zone),
                    city=str(city),
                    country=str(country),
                    metric=str(metric),
                    slope=float(res.slope),
                    p_value=float(res.pvalue),
                    r_squared=float(res.rvalue**2),
                    first_value=first_value,
                    current_value=current_value,
                ),
            )
        )

    results.sort(key=lambda pair: pair[0], reverse=True)
    return [r[1] for r in results[:TOP_N_PER_CATEGORY]]


# ---------------------------------------------------------------------------
# Detector 3 — Benchmark outliers (z-score vs peers)
# ---------------------------------------------------------------------------


def _detect_benchmark_outliers(mw: pd.DataFrame) -> list[BenchmarkFinding]:
    """Zones that are >1.5σ below their (country, zone_type, metric) peers."""
    df = mw.dropna(subset=["L0W_ROLL", "ZONE_TYPE", "COUNTRY", "METRIC"]).copy()

    # Compute peer stats per (country, zone_type, metric).
    stats_df = (
        df.groupby(["COUNTRY", "ZONE_TYPE", "METRIC"])["L0W_ROLL"]
        .agg(peer_mean="mean", peer_std="std", peer_count="count")
        .reset_index()
    )
    stats_df = stats_df[stats_df["peer_count"] >= BENCHMARK_MIN_PEERS]
    stats_df = stats_df[stats_df["peer_std"] > 0]

    merged = df.merge(stats_df, on=["COUNTRY", "ZONE_TYPE", "METRIC"], how="inner")
    merged["z_score"] = (merged["L0W_ROLL"] - merged["peer_mean"]) / merged["peer_std"]
    merged = merged[merged["z_score"] <= BENCHMARK_Z_THRESHOLD]

    merged = merged.sort_values("z_score", ascending=True)
    top = merged.head(TOP_N_PER_CATEGORY)

    findings: list[BenchmarkFinding] = []
    for _, row in top.iterrows():
        findings.append(
            BenchmarkFinding(
                zone=str(row["ZONE"]),
                city=str(row["CITY"]),
                country=str(row["COUNTRY"]),
                zone_type=str(row["ZONE_TYPE"]),
                metric=str(row["METRIC"]),
                value=float(row["L0W_ROLL"]),
                peer_mean=float(row["peer_mean"]),
                peer_std=float(row["peer_std"]),
                z_score=float(row["z_score"]),
                peer_count=int(row["peer_count"]),
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Detector 4 — Correlations between metrics (Pearson)
# ---------------------------------------------------------------------------


def _detect_correlations(mw: pd.DataFrame) -> list[CorrelationFinding]:
    """Top pairs of metrics with strongest Pearson correlation across zones.

    Pivots the long-ish representation of ``metrics_wide`` so each row is a
    zone and each column is a metric, then computes pairwise correlations
    on zones that have L0W_ROLL values for BOTH metrics in a pair.
    """
    pivot = (
        mw.dropna(subset=["L0W_ROLL"])
        .pivot_table(
            index=["COUNTRY", "CITY", "ZONE"],
            columns="METRIC",
            values="L0W_ROLL",
            aggfunc="mean",  # should be 1:1 but be defensive
        )
        .reset_index(drop=True)
    )
    if pivot.shape[1] < 2 or pivot.shape[0] < 10:
        return []

    metric_cols = list(pivot.columns)
    pairs: list[tuple[float, CorrelationFinding]] = []

    for i in range(len(metric_cols)):
        for j in range(i + 1, len(metric_cols)):
            a, b = metric_cols[i], metric_cols[j]
            paired = pivot[[a, b]].dropna()
            if len(paired) < 10:
                continue
            xs = paired[a].to_numpy(dtype=float)
            ys = paired[b].to_numpy(dtype=float)
            if np.ptp(xs) == 0 or np.ptp(ys) == 0:
                continue
            r, p_value = stats.pearsonr(xs, ys)
            if abs(r) < CORRELATION_R_THRESHOLD:
                continue

            # Regression metric_b ~ α + β · metric_a for the headline chart.
            reg = stats.linregress(xs, ys)
            finding = CorrelationFinding(
                metric_a=str(a),
                metric_b=str(b),
                r=float(r),
                n=int(len(paired)),
                p_value=float(p_value),
                intercept=float(reg.intercept),
                slope=float(reg.slope),
                r_squared=float(reg.rvalue**2),
            )
            pairs.append((abs(r), finding))

    pairs.sort(key=lambda p: p[0], reverse=True)
    return [p[1] for p in pairs[:TOP_N_CORRELATIONS]]


# ---------------------------------------------------------------------------
# Detector 5 — Opportunities (positive momentum on non-noisy base)
# ---------------------------------------------------------------------------


def _detect_opportunities(mw: pd.DataFrame) -> list[OpportunityFinding]:
    """Zones with a strong positive WoW delta AND a current value above the
    25th percentile of their country on that metric.

    The p25 floor filters out the "grew from 1 to 5 orders" class of
    apparent momentum — real opportunities are zones already above noise.
    """
    df = mw.dropna(subset=["L0W_ROLL", "L1W_ROLL"]).copy()
    df = df[df["L1W_ROLL"].abs() >= MIN_SIGNIFICANT_PREV]
    df["delta"] = df.apply(
        lambda r: _safe_delta_pct(r["L0W_ROLL"], r["L1W_ROLL"]), axis=1
    )
    df = df.dropna(subset=["delta"])
    df = df[df["delta"] >= OPPORTUNITY_DELTA_THRESHOLD]
    df = df[df["delta"] <= MAX_SENSIBLE_DELTA]

    # Country-level p25 per metric. Compute on the FULL (pre-filtered) frame
    # so the floor isn't biased upward by already-momentum zones.
    p25 = (
        mw.dropna(subset=["L0W_ROLL"])
        .groupby(["COUNTRY", "METRIC"])["L0W_ROLL"]
        .quantile(OPPORTUNITY_MIN_QUARTILE)
        .reset_index()
        .rename(columns={"L0W_ROLL": "country_p25"})
    )
    df = df.merge(p25, on=["COUNTRY", "METRIC"], how="left")
    df = df[df["L0W_ROLL"] >= df["country_p25"]]

    df = df.sort_values("delta", ascending=False)
    top = df.head(TOP_N_PER_CATEGORY)

    findings: list[OpportunityFinding] = []
    for _, row in top.iterrows():
        findings.append(
            OpportunityFinding(
                zone=str(row["ZONE"]),
                city=str(row["CITY"]),
                country=str(row["COUNTRY"]),
                metric=str(row["METRIC"]),
                current=float(row["L0W_ROLL"]),
                previous=float(row["L1W_ROLL"]),
                delta_pct=float(row["delta"]) * 100.0,
                country_p25=float(row["country_p25"]),
            )
        )
    return findings
