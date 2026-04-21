"""
Data cleaning pipeline: Bot_datos.xlsx → clean Parquet files.

Reads three sheets from the raw Excel file, applies cleaning rules,
and writes four parquets to data/processed/ plus a cleaning report.

Output files:
    data/processed/metrics_wide.parquet   — wide format, one row per (zone, metric)
    data/processed/metrics_long.parquet   — long format, one row per (zone, metric, week)
    data/processed/orders_wide.parquet    — wide format, one row per zone
    data/processed/orders_long.parquet    — long format, one row per (zone, week)

Run from project root:
    python scripts/clean_data.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.prompts.metric_dictionary import METRIC_DICTIONARY

logger = logging.getLogger(__name__)

RAW_FILE = Path("data/raw/Bot_datos.xlsx")
OUT_DIR = Path("data/processed")
REPORT_PATH = Path("docs/cleaning_report.md")

METRIC_WEEK_COLS = ["L8W_ROLL", "L7W_ROLL", "L6W_ROLL", "L5W_ROLL",
                    "L4W_ROLL", "L3W_ROLL", "L2W_ROLL", "L1W_ROLL", "L0W_ROLL"]
ORDER_WEEK_COLS = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W"]
METRIC_DIM_COLS = ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"]
ORDER_DIM_COLS = ["COUNTRY", "CITY", "ZONE", "METRIC"]

METRIC_KEY = ["COUNTRY", "CITY", "ZONE", "METRIC"]

# Alias present in raw data → canonical name in METRIC_DICTIONARY
METRIC_RENAMES: dict[str, str] = {
    "Pro Adoption (Last Week Status)": "Pro Adoption",
}

# Lead Penetration values above this threshold get flagged (not dropped)
LEAD_PENETRATION_FLAG_THRESHOLD = 1.5


# ---------------------------------------------------------------------------
# Step 1 — clean metrics sheet
# ---------------------------------------------------------------------------

def clean_metrics(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply all metric cleaning steps. Returns (cleaned_df, stats_dict)."""
    stats: dict = {}
    df = df_raw.copy()
    stats["rows_in"] = len(df)

    # Strip whitespace from all string columns
    for col in METRIC_DIM_COLS:
        df[col] = df[col].str.strip()

    # Rename aliases to canonical metric names
    renamed_mask = df["METRIC"].isin(METRIC_RENAMES)
    stats["rows_renamed"] = int(renamed_mask.sum())
    stats["renames"] = {old: new for old, new in METRIC_RENAMES.items()
                        if (df["METRIC"] == old).any()}
    df["METRIC"] = df["METRIC"].replace(METRIC_RENAMES)

    # Drop exact duplicate rows
    before_dedup = len(df)
    df = df.drop_duplicates()
    stats["duplicates_dropped"] = before_dedup - len(df)

    # Flag Lead Penetration outliers (mark, do NOT drop)
    lp_mask = (df["METRIC"] == "Lead Penetration") & (df["L0W_ROLL"] > LEAD_PENETRATION_FLAG_THRESHOLD)
    df["is_scale_outlier"] = lp_mask
    stats["scale_outliers_flagged"] = int(lp_mask.sum())

    stats["rows_out"] = len(df)
    return df, stats


# ---------------------------------------------------------------------------
# Step 2 — clean orders sheet
# ---------------------------------------------------------------------------

def clean_orders(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply all order cleaning steps. Returns (cleaned_df, stats_dict)."""
    stats: dict = {}
    df = df_raw.copy()
    stats["rows_in"] = len(df)

    for col in ORDER_DIM_COLS:
        df[col] = df[col].str.strip()

    before_dedup = len(df)
    df = df.drop_duplicates()
    stats["duplicates_dropped"] = before_dedup - len(df)

    # Record null counts per week column (preserved, not imputed)
    stats["nulls_per_week"] = {col: int(df[col].isna().sum()) for col in ORDER_WEEK_COLS}

    stats["rows_out"] = len(df)
    return df, stats


# ---------------------------------------------------------------------------
# Step 3 — melt to long format
# ---------------------------------------------------------------------------

def to_long(df_wide: pd.DataFrame, week_cols: list[str], dim_cols: list[str]) -> pd.DataFrame:
    """Melt wide df to long format with an integer week_number column.

    week_number: 0 = most recent (L0W), 8 = oldest (L8W).
    Null values are preserved (not dropped).
    """
    df_long = df_wide.melt(
        id_vars=dim_cols,
        value_vars=week_cols,
        var_name="week_offset",
        value_name="value",
    )
    df_long["week_number"] = (
        df_long["week_offset"].str.extract(r"L(\d)W")[0].astype(int)
    )
    return df_long.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 4 — validations (fail fast)
# ---------------------------------------------------------------------------

def validate_metrics(df: pd.DataFrame) -> list[str]:
    """Validate cleaned metrics df against METRIC_DICTIONARY.

    Returns list of passed check descriptions.
    Raises ValueError on any failure.
    """
    passed: list[str] = []

    # No duplicates on primary key
    dups = df.duplicated(subset=METRIC_KEY, keep=False).sum()
    if dups > 0:
        raise ValueError(
            f"VALIDATION FAILED: {dups} duplicate rows remain on key {METRIC_KEY}. "
            "Check the deduplication step."
        )
    passed.append("No duplicate rows on primary key (COUNTRY, CITY, ZONE, METRIC)")

    known_metrics = set(METRIC_DICTIONARY.keys())
    data_metrics = set(df["METRIC"].unique())

    # All known metrics are present in the data
    missing_from_data = known_metrics - data_metrics
    if missing_from_data:
        logger.warning("Metrics in dictionary but NOT in data: %s", missing_from_data)
    else:
        passed.append("All 13 dictionary metrics are present in the data")

    # No unknown metrics in the data
    unknown_in_data = data_metrics - known_metrics
    if unknown_in_data:
        raise ValueError(
            f"VALIDATION FAILED: Unknown metrics found in data that are NOT in "
            f"METRIC_DICTIONARY: {unknown_in_data}. Update the dictionary or the rename map."
        )
    passed.append("No unknown metrics in data (all metrics are in METRIC_DICTIONARY)")

    return passed


def validate_orders(df: pd.DataFrame) -> list[str]:
    """Validate cleaned orders df."""
    passed: list[str] = []

    unexpected = set(df["METRIC"].unique()) - {"Orders"}
    if unexpected:
        raise ValueError(f"VALIDATION FAILED: Unexpected METRIC values in orders: {unexpected}")
    passed.append("METRIC column contains only 'Orders'")

    return passed


# ---------------------------------------------------------------------------
# Step 5 — report writer
# ---------------------------------------------------------------------------

def write_report(
    metrics_stats: dict,
    orders_stats: dict,
    validations_passed: list[str],
    output_files: list[tuple[str, int]],
) -> None:
    """Write docs/cleaning_report.md summarizing what was cleaned."""
    lines: list[str] = [
        "# Cleaning Report\n",
        "_Generated by `scripts/clean_data.py`. Do not edit manually._\n",
        "---\n",
        "## RAW_INPUT_METRICS\n",
        "| | Rows |",
        "|---|---|",
        f"| Input | {metrics_stats['rows_in']:,} |",
        f"| Duplicates dropped | {metrics_stats['duplicates_dropped']:,} |",
        f"| Output | {metrics_stats['rows_out']:,} |",
        "",
        "### Renames applied\n",
    ]

    if metrics_stats["renames"]:
        lines.append("| Old name | New name | Rows affected |")
        lines.append("|---|---|---|")
        for old, new in metrics_stats["renames"].items():
            lines.append(f"| `{old}` | `{new}` | {metrics_stats['rows_renamed']:,} |")
    else:
        lines.append("_(none)_")

    lines += [
        "",
        "### Scale outliers flagged (`is_scale_outlier = True`)\n",
        f"Lead Penetration rows where L0W_ROLL > {LEAD_PENETRATION_FLAG_THRESHOLD}: "
        f"**{metrics_stats['scale_outliers_flagged']}** rows flagged (not dropped).\n",
        "",
        "---\n",
        "## RAW_ORDERS\n",
        "| | Rows |",
        "|---|---|",
        f"| Input | {orders_stats['rows_in']:,} |",
        f"| Duplicates dropped | {orders_stats['duplicates_dropped']:,} |",
        f"| Output | {orders_stats['rows_out']:,} |",
        "",
        "### Weekly nulls preserved (not imputed)\n",
        "| Week | Nulls |",
        "|---|---|",
    ]
    for col, n in orders_stats["nulls_per_week"].items():
        lines.append(f"| `{col}` | {n} |")

    lines += [
        "",
        "---\n",
        "## Validations passed\n",
    ]
    for check in validations_passed:
        lines.append(f"- ✓ {check}")

    lines += [
        "",
        "---\n",
        "## Output files\n",
        "| File | Rows |",
        "|---|---|",
    ]
    for path, rows in output_files:
        lines.append(f"| `{path}` | {rows:,} |")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Cleaning report written to %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run() -> None:
    """Load → clean → validate → melt → save parquets → write report."""
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Raw file not found: {RAW_FILE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading %s ...", RAW_FILE)
    raw_metrics = pd.read_excel(RAW_FILE, sheet_name="RAW_INPUT_METRICS", engine="openpyxl")
    raw_orders = pd.read_excel(RAW_FILE, sheet_name="RAW_ORDERS", engine="openpyxl")
    logger.info("Loaded: metrics=%d rows, orders=%d rows", len(raw_metrics), len(raw_orders))

    # --- Clean ---
    logger.info("Cleaning metrics sheet ...")
    metrics_wide, metrics_stats = clean_metrics(raw_metrics)
    logger.info(
        "Metrics: %d → %d rows (%d dups dropped, %d renamed, %d outliers flagged)",
        metrics_stats["rows_in"], metrics_stats["rows_out"],
        metrics_stats["duplicates_dropped"], metrics_stats["rows_renamed"],
        metrics_stats["scale_outliers_flagged"],
    )

    logger.info("Cleaning orders sheet ...")
    orders_wide, orders_stats = clean_orders(raw_orders)
    logger.info(
        "Orders: %d → %d rows (%d dups dropped)",
        orders_stats["rows_in"], orders_stats["rows_out"], orders_stats["duplicates_dropped"],
    )

    # --- Validate ---
    logger.info("Running validations ...")
    all_validations: list[str] = []
    all_validations += validate_metrics(metrics_wide)
    all_validations += validate_orders(orders_wide)
    logger.info("All validations passed ✓")

    # --- Melt to long ---
    logger.info("Melting metrics to long format ...")
    metrics_long_dim = METRIC_DIM_COLS + ["is_scale_outlier"]
    metrics_long = to_long(metrics_wide, METRIC_WEEK_COLS, metrics_long_dim)

    logger.info("Melting orders to long format ...")
    orders_long = to_long(orders_wide, ORDER_WEEK_COLS, ORDER_DIM_COLS)

    # --- Save parquets ---
    output_files: list[tuple[str, int]] = []

    def save(df: pd.DataFrame, name: str) -> None:
        path = OUT_DIR / name
        df.to_parquet(path, engine="pyarrow", index=False)
        output_files.append((str(path), len(df)))
        logger.info("Saved %s (%d rows)", path, len(df))

    save(metrics_wide, "metrics_wide.parquet")
    save(metrics_long, "metrics_long.parquet")
    save(orders_wide, "orders_wide.parquet")
    save(orders_long, "orders_long.parquet")

    # --- Report ---
    write_report(metrics_stats, orders_stats, all_validations, output_files)

    logger.info("Pipeline complete. Files in %s/", OUT_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run()
