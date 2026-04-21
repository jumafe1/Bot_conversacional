"""
Exploratory Data Analysis script for the raw Bot_datos.xlsx.

Profiles all three sheets and writes a markdown report to
docs/data_quality_report.md so cleaning decisions are documented
before implementing clean_data.py.

Run from project root:
    python scripts/explore_data.py
    python scripts/explore_data.py 2>/dev/null  # suppress log noise

Exposes:
    profile_metrics(df)  -> list[str]   markdown lines
    profile_orders(df)   -> list[str]   markdown lines
    profile_summary(df)  -> list[str]   markdown lines
    run()                -> None
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
EXCEL_FILE = RAW_DIR / "Bot_datos.xlsx"
REPORT_PATH = Path("docs/data_quality_report.md")

WEEK_COLS_METRICS = ["L8W_ROLL", "L7W_ROLL", "L6W_ROLL", "L5W_ROLL",
                     "L4W_ROLL", "L3W_ROLL", "L2W_ROLL", "L1W_ROLL", "L0W_ROLL"]
WEEK_COLS_ORDERS  = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W"]
DIM_COLS_METRICS  = ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"]
DIM_COLS_ORDERS   = ["COUNTRY", "CITY", "ZONE", "METRIC"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _null_table(df: pd.DataFrame, cols: list[str]) -> list[str]:
    lines = ["| Column | Nulls | % |", "|---|---|---|"]
    for col in cols:
        n = int(df[col].isna().sum())
        pct = n / len(df) * 100
        lines.append(f"| `{col}` | {n} | {pct:.1f}% |")
    return lines


def _value_counts_table(series: pd.Series, top: int = 15) -> list[str]:
    vc = series.value_counts().head(top)
    lines = ["| Value | Count |", "|---|---|"]
    for val, cnt in vc.items():
        lines.append(f"| {val} | {cnt} |")
    return lines


def _metric_stats_table(df: pd.DataFrame, value_col: str) -> list[str]:
    lines = ["| Metric | Min | Max | Mean | Median | Nulls |", "|---|---|---|---|---|---|"]
    for m in sorted(df["METRIC"].unique()):
        sub = df[df["METRIC"] == m][value_col]
        n_null = int(sub.isna().sum())
        lines.append(
            f"| {m} | {sub.min():.4f} | {sub.max():.4f} "
            f"| {sub.mean():.4f} | {sub.median():.4f} | {n_null} |"
        )
    return lines


# ---------------------------------------------------------------------------
# Sheet profilers
# ---------------------------------------------------------------------------

def profile_metrics(df: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    lines.append("## Sheet: RAW_INPUT_METRICS\n")
    lines.append(f"**Shape:** {df.shape[0]:,} rows × {df.shape[1]} columns\n")

    # --- Dimension columns ---
    lines.append("### Dimension columns\n")
    lines += _null_table(df, DIM_COLS_METRICS)
    lines.append("")

    # --- Cardinality ---
    lines.append("### Cardinality\n")
    lines.append("| Column | Unique values |")
    lines.append("|---|---|")
    for col in DIM_COLS_METRICS:
        lines.append(f"| `{col}` | {df[col].nunique()} |")
    lines.append("")

    # --- Value counts for low-cardinality dims ---
    lines.append("### COUNTRY distribution\n")
    lines += _value_counts_table(df["COUNTRY"])
    lines.append("")

    lines.append("### ZONE_TYPE distribution\n")
    lines += _value_counts_table(df["ZONE_TYPE"])
    lines.append("")

    lines.append("### ZONE_PRIORITIZATION distribution\n")
    lines += _value_counts_table(df["ZONE_PRIORITIZATION"])
    lines.append("")

    # --- Duplicate check ---
    dup_key = ["COUNTRY", "CITY", "ZONE", "METRIC"]
    n_dups = int(df.duplicated(subset=dup_key, keep=False).sum())
    lines.append(f"### Duplicates on `{dup_key}`\n")
    lines.append(f"> **{n_dups} rows** share the same (COUNTRY, CITY, ZONE, METRIC) key.\n")
    if n_dups > 0:
        sample = (
            df[df.duplicated(subset=dup_key, keep=False)]
            .sort_values(dup_key)
            .head(6)[dup_key + ["L0W_ROLL"]]
        )
        lines.append("Sample duplicated rows:\n")
        lines.append("```")
        lines.append(sample.to_string(index=False))
        lines.append("```\n")
    lines.append("")

    # --- Week column nulls ---
    lines.append("### Weekly value columns — null counts\n")
    lines += _null_table(df, WEEK_COLS_METRICS)
    lines.append("")

    # --- Per-metric value ranges on L0W_ROLL (most recent) ---
    lines.append("### Per-metric value ranges (L0W_ROLL = most recent week)\n")
    lines += _metric_stats_table(df, "L0W_ROLL")
    lines.append("")

    # --- Data quality flags ---
    lines.append("### Data quality flags\n")

    # Gross Profit UE — not a proportion
    gp = df[df["METRIC"] == "Gross Profit UE"]["L0W_ROLL"]
    lines.append(f"- **Gross Profit UE** range: [{gp.min():.2f}, {gp.max():.2f}] "
                 f"— monetary/unit metric, NOT a 0–1 proportion. Can be negative.\n")

    # Lead Penetration — can exceed 1
    lp = df[df["METRIC"] == "Lead Penetration"]["L0W_ROLL"]
    lines.append(f"- **Lead Penetration** range: [{lp.min():.4f}, {lp.max():.2f}] "
                 f"— ratio that can exceed 1.0 (max={lp.max():.2f}).\n")

    # Metric name mismatch with dictionary
    lines.append("- **Pro Adoption** is stored as `'Pro Adoption (Last Week Status)'` "
                 "in the data — differs from the spec name `'Pro Adoption'`.\n")

    return lines


def profile_orders(df: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    lines.append("## Sheet: RAW_ORDERS\n")
    lines.append(f"**Shape:** {df.shape[0]:,} rows × {df.shape[1]} columns\n")

    lines.append("### Dimension columns\n")
    lines += _null_table(df, DIM_COLS_ORDERS)
    lines.append("")

    lines.append("### METRIC values\n")
    lines += _value_counts_table(df["METRIC"])
    lines.append("")

    lines.append("### COUNTRY distribution\n")
    lines += _value_counts_table(df["COUNTRY"])
    lines.append("")

    lines.append("### Cardinality\n")
    lines.append("| Column | Unique values |")
    lines.append("|---|---|")
    for col in DIM_COLS_ORDERS:
        lines.append(f"| `{col}` | {df[col].nunique()} |")
    lines.append("")

    lines.append("### Weekly order volume — null counts\n")
    lines += _null_table(df, WEEK_COLS_ORDERS)
    lines.append("")

    lines.append("### L0W (most recent week) — order volume stats\n")
    l0 = df["L0W"].dropna()
    lines.append("| Stat | Value |")
    lines.append("|---|---|")
    lines.append(f"| Min | {l0.min():,.0f} |")
    lines.append(f"| Max | {l0.max():,.0f} |")
    lines.append(f"| Mean | {l0.mean():,.0f} |")
    lines.append(f"| Median | {l0.median():,.0f} |")
    lines.append(f"| p25 | {l0.quantile(0.25):,.0f} |")
    lines.append(f"| p75 | {l0.quantile(0.75):,.0f} |")
    lines.append("")

    # Zones in orders but not in metrics
    lines.append("### Data quality flags\n")
    lines.append(f"- **{int(df['L0W'].isna().sum())} nulls in L0W** ({df['L0W'].isna().mean()*100:.1f}%) "
                 f"— zones with no orders in the most recent week.\n")

    return lines


def profile_summary(df: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    lines.append("## Sheet: RAW_SUMMARY\n")
    lines.append(
        "> This sheet is a **data dictionary** (metadata), not analytical data. "
        "It documents the column schema of the other sheets.\n"
    )
    lines.append(f"**Shape:** {df.shape[0]} rows × {df.shape[1]} columns\n")
    lines.append("### Full contents\n")
    lines.append("```")
    lines.append(df.to_string(index=False))
    lines.append("```\n")
    return lines


def profile_cross_sheet(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> list[str]:
    """Compare zone coverage between sheets."""
    lines: list[str] = []
    lines.append("## Cross-sheet analysis\n")

    metrics_zones = set(zip(metrics_df["COUNTRY"], metrics_df["CITY"], metrics_df["ZONE"]))
    orders_zones  = set(zip(orders_df["COUNTRY"],  orders_df["CITY"],  orders_df["ZONE"]))

    only_metrics = metrics_zones - orders_zones
    only_orders  = orders_zones  - metrics_zones
    both         = metrics_zones & orders_zones

    lines.append("| | Unique (COUNTRY, CITY, ZONE) tuples |")
    lines.append("|---|---|")
    lines.append(f"| RAW_INPUT_METRICS | {len(metrics_zones):,} |")
    lines.append(f"| RAW_ORDERS | {len(orders_zones):,} |")
    lines.append(f"| In both sheets | {len(both):,} |")
    lines.append(f"| Only in METRICS (no orders data) | {len(only_metrics):,} |")
    lines.append(f"| Only in ORDERS (no metric data) | {len(only_orders):,} |")
    lines.append("")

    if only_orders:
        sample = list(only_orders)[:5]
        lines.append(f"Sample zones in ORDERS but not in METRICS: `{sample}`\n")

    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("Loading %s ...", EXCEL_FILE)
    if not EXCEL_FILE.exists():
        logger.error("File not found: %s", EXCEL_FILE)
        sys.exit(1)

    metrics_df = pd.read_excel(EXCEL_FILE, sheet_name="RAW_INPUT_METRICS", engine="openpyxl")
    orders_df  = pd.read_excel(EXCEL_FILE, sheet_name="RAW_ORDERS",        engine="openpyxl")
    summary_df = pd.read_excel(EXCEL_FILE, sheet_name="RAW_SUMMARY",       engine="openpyxl")

    logger.info("Sheets loaded. Building report ...")

    report_lines: list[str] = [
        "# Data Quality Report\n",
        "_Generated by `scripts/explore_data.py`. Do not edit manually._\n",
        "---\n",
    ]
    report_lines += profile_metrics(metrics_df)
    report_lines += ["---\n"]
    report_lines += profile_orders(orders_df)
    report_lines += ["---\n"]
    report_lines += profile_summary(summary_df)
    report_lines += ["---\n"]
    report_lines += profile_cross_sheet(metrics_df, orders_df)

    report = "\n".join(report_lines)

    # Write to file
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info("Report written to %s", REPORT_PATH)

    # Also print to stdout for quick inspection
    print(report)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run()
