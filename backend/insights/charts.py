"""
matplotlib → base64 PNG rendering for each insight category.

Every function takes the raw data (DataFrames + findings) and returns a
base64-encoded PNG as a string. The endpoint embeds these in the response
so the frontend can render them with ``<img src="data:image/png;base64,...">``
without any additional file-serving setup.

Design notes:
    - Use the ``Agg`` backend so rendering works headless in a server.
    - All figures are 800×450 px at 100 dpi and saved with ``bbox_inches="tight"``.
    - Keep palettes restrained — no seaborn dependency, plain matplotlib.
    - Return ``None`` when a chart can't be generated (e.g. empty findings)
      so the service can skip the image in that section.
"""

from __future__ import annotations

import base64
import io
import logging

import matplotlib

matplotlib.use("Agg")  # headless / server-safe; must be set before pyplot import

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backend.insights.schemas import (
    AnomalyFinding,
    BenchmarkFinding,
    CorrelationFinding,
    OpportunityFinding,
    TrendFinding,
)

logger = logging.getLogger(__name__)

# Rappi-ish palette (matches the frontend brand-* tokens).
BRAND_ORANGE = "#ff5a34"
INK_700 = "#2e3340"
INK_400 = "#8c94a3"
INK_200 = "#dcdfe6"
EMERALD = "#059669"

FIG_SIZE = (8.0, 4.5)  # inches
DPI = 100


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _encode_fig(fig: plt.Figure) -> str:
    """Save ``fig`` to a PNG byte buffer and return a base64 string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _new_fig() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fafafa")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(INK_200)
    ax.spines["bottom"].set_color(INK_200)
    ax.tick_params(colors=INK_700, labelsize=9)
    return fig, ax


# ---------------------------------------------------------------------------
# Chart 1 — Anomalies: scatter of zones (current value × delta%)
# ---------------------------------------------------------------------------


def render_anomalies(
    findings: list[AnomalyFinding],
    _all_metrics_wide: pd.DataFrame,
    *,
    title: str | None = None,
) -> str | None:
    """Horizontal bar chart of the top N anomalies ranked by |delta|.

    A scatter mixing all 13 metrics is useless visually — each metric has
    a different scale (proportion 0-1, monetary -100..15, ratio > 1). A
    bar chart sidesteps that problem because each row has its own row;
    scale clashes never compete on a single axis.

    Up-moves are rendered in emerald, down-moves in brand orange. The
    ``_all_metrics_wide`` parameter is kept on the signature for API
    symmetry with the other renderers (and in case we later add a
    density sparkline), but it's unused by this implementation.
    """
    if not findings:
        return None

    # Bars are drawn bottom-up; reverse so the biggest anomaly ends up
    # on top, which matches how users read the narrative.
    items = list(reversed(findings))

    labels = [
        f"{f.zone[:18]} · {f.metric[:22]}  ({f.country})" for f in items
    ]
    deltas = [f.delta_pct for f in items]
    colors = [EMERALD if d > 0 else BRAND_ORANGE for d in deltas]

    fig, ax = _new_fig()
    # Taller figure so 10 horizontal bars have breathing room.
    fig.set_size_inches(8.5, max(4.0, 0.45 * len(items) + 1.2))

    y_positions = range(len(items))
    ax.barh(y_positions, deltas, color=colors, edgecolor="white", linewidth=0.8)
    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(labels, fontsize=8.5, color=INK_700)

    # Value labels at the end of each bar, placed outside or inside
    # depending on the sign so they never overlap the axis.
    x_max = max(abs(d) for d in deltas)
    pad = x_max * 0.02
    for y, d in zip(y_positions, deltas, strict=True):
        ha = "left" if d >= 0 else "right"
        x = d + pad if d >= 0 else d - pad
        ax.text(
            x, y,
            f"{d:+.1f}%",
            ha=ha, va="center",
            fontsize=8, color=INK_700,
            fontweight="semibold",
        )

    ax.axvline(0, color=INK_400, linewidth=0.8)
    ax.set_xlabel("Cambio semana a semana (%)", fontsize=9, color=INK_700)
    ax.set_title(
        title or f"Top {len(findings)} anomalías — zonas con mayor cambio WoW",
        fontsize=11, color=INK_700, pad=12, loc="left",
    )
    ax.grid(True, axis="x", alpha=0.3)
    # Widen x-range slightly so the text labels fit.
    ax.set_xlim(min(0, min(deltas)) - x_max * 0.15, max(0, max(deltas)) + x_max * 0.15)

    return _encode_fig(fig)


# ---------------------------------------------------------------------------
# Chart 2 — Declining trends: 3 series with strongest decline
# ---------------------------------------------------------------------------


def render_trends(
    findings: list[TrendFinding],
    metrics_long: pd.DataFrame,
    *,
    num_weeks: int = 9,
    title: str | None = None,
) -> str | None:
    """Overlay the weekly series of the top 3 declining (zone, metric) lines.

    ``num_weeks`` controls both the x-axis (weeks 0..num_weeks-1, rendered
    oldest→newest) and the data window — points older than ``num_weeks``
    weeks ago are skipped.
    """
    if not findings or metrics_long.empty:
        return None

    fig, ax = _new_fig()
    colors = [BRAND_ORANGE, "#c23c10", "#8b2b0c"]
    latest_x = num_weeks - 1

    for finding, color in zip(findings[:3], colors, strict=False):
        mask = (
            (metrics_long["COUNTRY"] == finding.country)
            & (metrics_long["CITY"] == finding.city)
            & (metrics_long["ZONE"] == finding.zone)
            & (metrics_long["METRIC"] == finding.metric)
            & (metrics_long["week_number"].astype(int) < num_weeks)
        )
        series = metrics_long[mask].dropna(subset=["value"]).sort_values("week_number")
        if series.empty:
            continue
        xs = latest_x - series["week_number"].to_numpy()
        ys = series["value"].to_numpy()
        label = f"{finding.zone[:18]} · {finding.metric[:18]} ({finding.country})"
        ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.8, color=color, label=label)

    ax.set_xticks(range(num_weeks))
    ax.set_xticklabels(
        [f"L{i}W" for i in range(num_weeks - 1, -1, -1)],
        fontsize=8,
        color=INK_700,
    )
    ax.set_xlabel("Semana (oldest → most recent)", fontsize=9, color=INK_700)
    ax.set_ylabel("Valor de la métrica", fontsize=9, color=INK_700)
    ax.set_title(
        title or "Tendencias preocupantes: top 3 series con deterioro significativo",
        fontsize=11, color=INK_700, pad=12, loc="left",
    )
    ax.legend(fontsize=8, loc="best", frameon=False)
    ax.grid(True, alpha=0.3)
    return _encode_fig(fig)


# ---------------------------------------------------------------------------
# Chart 3 — Benchmarking: boxplot per country for the most-affected metric
# ---------------------------------------------------------------------------


def render_benchmarks(
    findings: list[BenchmarkFinding],
    metrics_wide: pd.DataFrame,
    *,
    title: str | None = None,
) -> str | None:
    """Boxplot distribution per country for the metric most frequently flagged.

    Highlights each benchmark outlier as a red dot labelled with its zone
    name so the divergence is legible.
    """
    if not findings or metrics_wide.empty:
        return None

    # Focus on the metric with the most flagged outliers.
    top_metric = pd.Series([f.metric for f in findings]).value_counts().idxmax()
    df = metrics_wide.dropna(subset=["L0W_ROLL"])
    df = df[df["METRIC"] == top_metric]

    countries = sorted(df["COUNTRY"].unique())
    data_per_country = [
        df[df["COUNTRY"] == c]["L0W_ROLL"].to_numpy() for c in countries
    ]

    fig, ax = _new_fig()
    bp = ax.boxplot(
        data_per_country,
        labels=countries,
        patch_artist=True,
        widths=0.5,
        showfliers=False,
        medianprops=dict(color=INK_700, linewidth=1.5),
    )
    for patch in bp["boxes"]:
        patch.set_facecolor("#eef0f4")
        patch.set_edgecolor(INK_400)

    # Overlay outliers as red dots with labels.
    for f in findings:
        if f.metric != top_metric:
            continue
        if f.country not in countries:
            continue
        x = countries.index(f.country) + 1  # boxplot positions are 1-indexed
        ax.scatter(x, f.value, color=BRAND_ORANGE, edgecolor="white",
                   linewidth=1.0, s=60, zorder=3)
        ax.annotate(
            f.zone[:16],
            xy=(x, f.value),
            xytext=(5, -3),
            textcoords="offset points",
            fontsize=7.5,
            color=INK_700,
        )

    ax.set_ylabel(f"{top_metric}", fontsize=9, color=INK_700)
    ax.set_xlabel("País", fontsize=9, color=INK_700)
    ax.set_title(
        title or f"Benchmarking: outliers de {top_metric} por país",
        fontsize=11, color=INK_700, pad=12, loc="left",
    )
    ax.grid(True, axis="y", alpha=0.3)
    return _encode_fig(fig)


# ---------------------------------------------------------------------------
# Chart 4 — Correlations: heatmap of the 13×13 matrix
# ---------------------------------------------------------------------------


def render_correlation_heatmap(metrics_wide: pd.DataFrame) -> str | None:
    """Heatmap of the pairwise Pearson correlations between all metrics."""
    if metrics_wide.empty:
        return None
    pivot = (
        metrics_wide.dropna(subset=["L0W_ROLL"])
        .pivot_table(
            index=["COUNTRY", "CITY", "ZONE"],
            columns="METRIC",
            values="L0W_ROLL",
            aggfunc="mean",
        )
    )
    if pivot.shape[1] < 2:
        return None
    corr = pivot.corr(method="pearson")

    fig, ax = _new_fig()
    # Slightly wider figure for readable labels.
    fig.set_size_inches(8.5, 6.0)

    im = ax.imshow(
        corr.to_numpy(),
        cmap="RdBu_r",
        vmin=-1, vmax=1,
        aspect="auto",
    )
    labels = [m[:22] for m in corr.columns]
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7.5, color=INK_700)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7.5, color=INK_700)

    # Annotate cells with |r| ≥ 0.3 for readability.
    values = corr.to_numpy()
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = values[i, j]
            if np.isnan(v) or i == j:
                continue
            if abs(v) >= 0.3:
                ax.text(
                    j, i, f"{v:.2f}",
                    ha="center", va="center",
                    fontsize=6.5,
                    color="white" if abs(v) >= 0.55 else INK_700,
                )

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.tick_params(labelsize=7.5, colors=INK_700)
    cbar.set_label("Pearson r", fontsize=9, color=INK_700)

    ax.set_title(
        "Correlaciones entre métricas (L0W_ROLL, n=zonas)",
        fontsize=11, color=INK_700, pad=12, loc="left",
    )
    return _encode_fig(fig)


# ---------------------------------------------------------------------------
# Chart 5 — Regression for the top correlation pair
# ---------------------------------------------------------------------------


def render_regression(
    finding: CorrelationFinding | None,
    metrics_wide: pd.DataFrame,
    *,
    title: str | None = None,
) -> str | None:
    """Scatter + fitted line for the strongest metric pair, with R²."""
    if finding is None or metrics_wide.empty:
        return None
    pivot = (
        metrics_wide.dropna(subset=["L0W_ROLL"])
        .pivot_table(
            index=["COUNTRY", "CITY", "ZONE"],
            columns="METRIC",
            values="L0W_ROLL",
            aggfunc="mean",
        )
    )
    if finding.metric_a not in pivot.columns or finding.metric_b not in pivot.columns:
        return None
    paired = pivot[[finding.metric_a, finding.metric_b]].dropna()
    if paired.empty:
        return None

    fig, ax = _new_fig()
    ax.scatter(
        paired[finding.metric_a],
        paired[finding.metric_b],
        s=14, color=INK_400, alpha=0.55,
    )
    x_line = np.linspace(
        paired[finding.metric_a].min(), paired[finding.metric_a].max(), 100
    )
    y_line = finding.intercept + finding.slope * x_line
    ax.plot(x_line, y_line, color=BRAND_ORANGE, linewidth=2.0,
            label=f"y = {finding.intercept:.3f} + {finding.slope:.3f}·x")

    ax.set_xlabel(finding.metric_a[:40], fontsize=9, color=INK_700)
    ax.set_ylabel(finding.metric_b[:40], fontsize=9, color=INK_700)
    ax.set_title(
        title
        or (
            f"Correlación más fuerte: {finding.metric_a[:20]} vs {finding.metric_b[:20]} "
            f"(r={finding.r:.2f}, R²={finding.r_squared:.2f}, n={finding.n})"
        ),
        fontsize=10, color=INK_700, pad=12, loc="left",
    )
    ax.legend(fontsize=8, loc="best", frameon=False)
    ax.grid(True, alpha=0.3)
    return _encode_fig(fig)


# ---------------------------------------------------------------------------
# Chart 6 — Opportunities (mirrors the anomalies bar chart)
# ---------------------------------------------------------------------------


def render_opportunities(
    findings: list[OpportunityFinding],
    *,
    title: str | None = None,
) -> str | None:
    """Horizontal bar chart for opportunities. Mirrors the anomalies chart
    but restricted to positive momentum (always emerald)."""
    if not findings:
        return None

    items = list(reversed(findings))
    labels = [
        f"{f.zone[:18]} · {f.metric[:22]}  ({f.country})" for f in items
    ]
    deltas = [f.delta_pct for f in items]

    fig, ax = _new_fig()
    fig.set_size_inches(8.5, max(4.0, 0.45 * len(items) + 1.2))

    y_positions = range(len(items))
    ax.barh(y_positions, deltas, color=EMERALD, edgecolor="white", linewidth=0.8)
    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(labels, fontsize=8.5, color=INK_700)

    x_max = max(deltas)
    pad = x_max * 0.02
    for y, d in zip(y_positions, deltas, strict=True):
        ax.text(
            d + pad, y,
            f"+{d:.1f}%",
            ha="left", va="center",
            fontsize=8, color=INK_700,
            fontweight="semibold",
        )

    ax.set_xlabel("Crecimiento semana a semana (%)", fontsize=9, color=INK_700)
    ax.set_title(
        title or f"Top {len(findings)} oportunidades — momentum positivo sostenido",
        fontsize=11, color=INK_700, pad=12, loc="left",
    )
    ax.grid(True, axis="x", alpha=0.3)
    ax.set_xlim(0, x_max * 1.15)

    return _encode_fig(fig)
