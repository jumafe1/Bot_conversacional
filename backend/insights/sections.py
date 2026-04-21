"""
Filter-aware per-section recomputation for the interactive insights UI.

This module exists alongside ``analyzer.py`` (which runs every detector with
default parameters for the initial batch report). Each function here accepts
a focused filter set — metric, week range, peer group, country, etc. — and
returns the (findings, chart_base64) pair for ONE section.

The interactive UI hits these through ``InsightsService.recompute_section``
whenever the user drags a slider or picks a different metric.

Design notes:
    - Pure functions over pandas DataFrames; no DuckDB, no LLM.
    - Reuses the chart renderers in ``charts.py`` (pass-through) and builds
      small wrappers only when a custom title is needed to reflect filters.
    - Top-N caps match ``analyzer.py`` for visual consistency.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from backend.insights import charts
from backend.insights.analyzer import (
    BENCHMARK_MIN_PEERS,
    BENCHMARK_Z_THRESHOLD,
    MAX_SENSIBLE_DELTA,
    MIN_SIGNIFICANT_PREV,
    OPPORTUNITY_DELTA_THRESHOLD,
    OPPORTUNITY_MIN_QUARTILE,
    TOP_N_PER_CATEGORY,
    TREND_P_VALUE_THRESHOLD,
    _safe_delta_pct,
)
from backend.insights.schemas import (
    AnomalyFinding,
    BenchmarkFinding,
    CorrelationFinding,
    OpportunityFinding,
    TrendFinding,
)

logger = logging.getLogger(__name__)

PeerBy = Literal["zone_type", "zone_prioritization"]

# Relaxed threshold for interactive queries: let users see any material
# change, not only swings above 10%. The narrator still gets told the
# threshold so it can frame small moves honestly.
ANOMALY_INTERACTIVE_MIN_DELTA = 0.03  # 3% — filters out pure noise only


# ---------------------------------------------------------------------------
# Section 1 — Anomalies (custom baseline/current week, single metric)
# ---------------------------------------------------------------------------


def recompute_anomalies(
    mw: pd.DataFrame,
    *,
    metric: str,
    start_week_num: int,
    end_week_num: int,
) -> tuple[list[AnomalyFinding], str | None]:
    """Top zones with the largest delta on ``metric`` between two weeks.

    Args:
        mw: ``metrics_wide`` dataframe (scale outliers already excluded).
        metric: canonical metric name to restrict to.
        start_week_num: older week index, 1..8 (e.g. 4 = L4W_ROLL).
        end_week_num: newer week index, 0..7. Must be < start_week_num.

    Returns:
        (findings, chart_png_base64)
    """
    _require_week_pair(start_week_num, end_week_num)

    start_col = f"L{start_week_num}W_ROLL"
    end_col = f"L{end_week_num}W_ROLL"

    df = mw[mw["METRIC"] == metric].dropna(subset=[start_col, end_col]).copy()
    # Near-zero baseline → nonsense percentages. Drop those rows.
    df = df[df[start_col].abs() >= MIN_SIGNIFICANT_PREV]

    df["delta"] = df.apply(
        lambda r: _safe_delta_pct(r[end_col], r[start_col]), axis=1
    )
    df = df.dropna(subset=["delta"])
    df = df[df["delta"].abs() >= ANOMALY_INTERACTIVE_MIN_DELTA]
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
                current=float(row[end_col]),
                previous=float(row[start_col]),
                delta_pct=float(row["delta"]) * 100.0,
                direction="up" if row["delta"] > 0 else "down",
            )
        )

    title = (
        f"Top {len(findings)} anomalías — {metric} "
        f"(Δ entre L{start_week_num}W y L{end_week_num}W)"
    )
    chart = charts.render_anomalies(findings, mw, title=title) if findings else None
    return findings, chart


# ---------------------------------------------------------------------------
# Section 2 — Trends (single metric, adjustable window)
# ---------------------------------------------------------------------------


def recompute_trends(
    ml: pd.DataFrame,
    *,
    metric: str,
    num_weeks: int,
) -> tuple[list[TrendFinding], str | None]:
    """Declining trends restricted to ``metric`` over the last ``num_weeks``.

    Same linear-regression detector as ``_detect_declining_trends`` but
    windowed to the most recent ``num_weeks`` and filtered to one metric.
    """
    _require_num_weeks(num_weeks)

    required_cols = {"value", "week_number", "COUNTRY", "CITY", "ZONE", "METRIC"}
    if ml.empty or not required_cols.issubset(ml.columns):
        return [], None

    df = ml[ml["METRIC"] == metric].dropna(subset=["value"]).copy()
    df = df[df["week_number"].astype(int) < num_weeks]
    df["time"] = (num_weeks - 1) - df["week_number"].astype(int)

    # Reusing TREND_MIN_POINTS (6) would reject most 3- or 4-week windows.
    # Scale it to the window size: at least half of the window must be present.
    min_points = max(3, num_weeks // 2 + 1)

    results: list[tuple[float, TrendFinding]] = []
    for (country, city, zone, _metric), sub in df.groupby(
        ["COUNTRY", "CITY", "ZONE", "METRIC"], dropna=True
    ):
        if len(sub) < min_points:
            continue
        xs = sub["time"].to_numpy(dtype=float)
        ys = sub["value"].to_numpy(dtype=float)
        if np.ptp(xs) == 0 or np.ptp(ys) == 0:
            continue
        res = stats.linregress(xs, ys)
        # For short windows, relax the significance floor slightly — with
        # 3 points you basically can't clear p<0.05 even on steep slopes.
        p_threshold = TREND_P_VALUE_THRESHOLD if num_weeks >= 7 else 0.15
        if res.pvalue >= p_threshold or res.slope >= 0:
            continue

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
                    metric=str(_metric),
                    slope=float(res.slope),
                    p_value=float(res.pvalue),
                    r_squared=float(res.rvalue**2),
                    first_value=first_value,
                    current_value=current_value,
                ),
            )
        )

    results.sort(key=lambda pair: pair[0], reverse=True)
    findings = [r[1] for r in results[:TOP_N_PER_CATEGORY]]

    title = (
        f"Tendencias preocupantes — {metric} "
        f"(últimas {num_weeks} semanas)"
    )
    chart = (
        charts.render_trends(findings, ml, num_weeks=num_weeks, title=title)
        if findings
        else None
    )
    return findings, chart


# ---------------------------------------------------------------------------
# Section 3 — Benchmarks (single metric, configurable peer group)
# ---------------------------------------------------------------------------


def recompute_benchmarks(
    mw: pd.DataFrame,
    *,
    metric: str,
    peer_by: PeerBy,
) -> tuple[list[BenchmarkFinding], str | None]:
    """Zones >1.5σ below their peers on ``metric``, peers grouped by ``peer_by``.

    Peer group is always bucketed within country (otherwise cross-market
    differences dominate the z-score). Passing ``peer_by="zone_type"`` matches
    the default analyzer; ``"zone_prioritization"`` swaps the dimension.
    """
    if peer_by not in ("zone_type", "zone_prioritization"):
        raise ValueError(
            f"Invalid peer_by '{peer_by}'. Must be 'zone_type' or 'zone_prioritization'."
        )

    peer_col = peer_by.upper()
    df = mw[mw["METRIC"] == metric].dropna(
        subset=["L0W_ROLL", peer_col, "COUNTRY"]
    ).copy()

    stats_df = (
        df.groupby(["COUNTRY", peer_col])["L0W_ROLL"]
        .agg(peer_mean="mean", peer_std="std", peer_count="count")
        .reset_index()
    )
    stats_df = stats_df[stats_df["peer_count"] >= BENCHMARK_MIN_PEERS]
    stats_df = stats_df[stats_df["peer_std"] > 0]

    merged = df.merge(stats_df, on=["COUNTRY", peer_col], how="inner")
    merged["z_score"] = (merged["L0W_ROLL"] - merged["peer_mean"]) / merged["peer_std"]
    merged = merged[merged["z_score"] <= BENCHMARK_Z_THRESHOLD]
    merged = merged.sort_values("z_score", ascending=True).head(TOP_N_PER_CATEGORY)

    findings: list[BenchmarkFinding] = []
    for _, row in merged.iterrows():
        # BenchmarkFinding.zone_type field carries whatever peer dimension
        # was used — it's the "group label" for that row.
        findings.append(
            BenchmarkFinding(
                zone=str(row["ZONE"]),
                city=str(row["CITY"]),
                country=str(row["COUNTRY"]),
                zone_type=str(row[peer_col]),
                metric=str(row["METRIC"]),
                value=float(row["L0W_ROLL"]),
                peer_mean=float(row["peer_mean"]),
                peer_std=float(row["peer_std"]),
                z_score=float(row["z_score"]),
                peer_count=int(row["peer_count"]),
            )
        )

    dim_label = "zone_type" if peer_by == "zone_type" else "prioritization"
    title = f"Benchmarking — {metric}, outliers vs peers por {dim_label}"
    chart = (
        charts.render_benchmarks(findings, mw, title=title) if findings else None
    )
    return findings, chart


# ---------------------------------------------------------------------------
# Section 4 — Correlations (user picks both metrics + optional country)
# ---------------------------------------------------------------------------


def recompute_correlations(
    mw: pd.DataFrame,
    *,
    metric_x: str,
    metric_y: str,
    country: str | None,
) -> tuple[list[CorrelationFinding], str | None]:
    """Regression between two user-chosen metrics, optionally scoped to a country.

    Returns ``findings`` as a 0-or-1 list so the response shape matches the
    other sections. When the pair has fewer than 10 paired observations the
    list is empty and the chart is None.
    """
    if metric_x == metric_y:
        raise ValueError("metric_x and metric_y must be different metrics.")

    scoped = mw if not country else mw[mw["COUNTRY"] == country]
    pivot = (
        scoped.dropna(subset=["L0W_ROLL"])
        .pivot_table(
            index=["COUNTRY", "CITY", "ZONE"],
            columns="METRIC",
            values="L0W_ROLL",
            aggfunc="mean",
        )
        .reset_index(drop=True)
    )

    if metric_x not in pivot.columns or metric_y not in pivot.columns:
        return [], None

    paired = pivot[[metric_x, metric_y]].dropna()
    if len(paired) < 10:
        return [], None

    xs = paired[metric_x].to_numpy(dtype=float)
    ys = paired[metric_y].to_numpy(dtype=float)
    if np.ptp(xs) == 0 or np.ptp(ys) == 0:
        return [], None

    r, p_value = stats.pearsonr(xs, ys)
    reg = stats.linregress(xs, ys)

    finding = CorrelationFinding(
        metric_a=metric_x,
        metric_b=metric_y,
        r=float(r),
        n=int(len(paired)),
        p_value=float(p_value),
        intercept=float(reg.intercept),
        slope=float(reg.slope),
        r_squared=float(reg.rvalue**2),
    )

    country_suffix = f" — {country}" if country else " — global"
    title = (
        f"{metric_x[:22]} vs {metric_y[:22]}{country_suffix} "
        f"(r={finding.r:.2f}, n={finding.n})"
    )
    chart = charts.render_regression(finding, scoped, title=title)
    return [finding], chart


# ---------------------------------------------------------------------------
# Section 5 — Opportunities (single metric)
# ---------------------------------------------------------------------------


def recompute_opportunities(
    mw: pd.DataFrame,
    *,
    metric: str,
) -> tuple[list[OpportunityFinding], str | None]:
    """Zones with strong positive WoW momentum on ``metric`` above country p25."""
    df = mw[mw["METRIC"] == metric].dropna(
        subset=["L0W_ROLL", "L1W_ROLL"]
    ).copy()
    df = df[df["L1W_ROLL"].abs() >= MIN_SIGNIFICANT_PREV]
    df["delta"] = df.apply(
        lambda r: _safe_delta_pct(r["L0W_ROLL"], r["L1W_ROLL"]), axis=1
    )
    df = df.dropna(subset=["delta"])
    df = df[df["delta"] >= OPPORTUNITY_DELTA_THRESHOLD]
    df = df[df["delta"] <= MAX_SENSIBLE_DELTA]

    p25 = (
        mw[mw["METRIC"] == metric]
        .dropna(subset=["L0W_ROLL"])
        .groupby("COUNTRY")["L0W_ROLL"]
        .quantile(OPPORTUNITY_MIN_QUARTILE)
        .reset_index()
        .rename(columns={"L0W_ROLL": "country_p25"})
    )
    df = df.merge(p25, on="COUNTRY", how="left")
    df = df[df["L0W_ROLL"] >= df["country_p25"]]
    df = df.sort_values("delta", ascending=False).head(TOP_N_PER_CATEGORY)

    findings: list[OpportunityFinding] = []
    for _, row in df.iterrows():
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

    title = f"Oportunidades — {metric}, momentum positivo vs L1W"
    chart = charts.render_opportunities(findings, title=title) if findings else None
    return findings, chart


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------


def _require_week_pair(start_week_num: int, end_week_num: int) -> None:
    if not 1 <= start_week_num <= 8:
        raise ValueError(
            f"start_week_num must be in 1..8 (got {start_week_num})."
        )
    if not 0 <= end_week_num <= 7:
        raise ValueError(f"end_week_num must be in 0..7 (got {end_week_num}).")
    if end_week_num >= start_week_num:
        raise ValueError(
            f"end_week_num ({end_week_num}) must be strictly less than "
            f"start_week_num ({start_week_num})."
        )


def _require_num_weeks(num_weeks: int) -> None:
    if not 3 <= num_weeks <= 9:
        raise ValueError(f"num_weeks must be in 3..9 (got {num_weeks}).")
