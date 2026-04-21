"""
Exploratory Data Analysis script for the raw Bot_datos.xlsx.

Prints summary statistics, null rates, and value distributions to stdout
so we can make informed cleaning decisions before implementing clean_data.py.

Exposes:
    profile_sheet(df, name)  -> None   (prints stats for one sheet)
    run()                    -> None   (main entry point)

TODO:
    1. Read all three sheets from EXCEL_FILE.
    2. For each sheet:
       - Shape (rows, cols).
       - Column dtypes.
       - Null count and % per column.
       - Number of duplicate rows.
       - Descriptive stats for numeric columns (min, max, mean, p25, p75).
       - Value counts for low-cardinality string columns (country, zone_type, etc.).
       - Date range for date columns.
    3. Print a markdown-formatted report to stdout (can be piped to a file).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
EXCEL_FILE = RAW_DIR / "Bot_datos.xlsx"


def profile_sheet(df: "pd.DataFrame", name: str) -> None:
    """Print EDA summary for a single DataFrame sheet.

    TODO: implement profiling logic described in module docstring.
    """
    raise NotImplementedError


def run() -> None:
    """Load all sheets and profile each one."""
    # TODO: read EXCEL_FILE, call profile_sheet for each sheet
    raise NotImplementedError


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
