"""
Deterministic statistical caveats attached to tool responses.

The LLM does not reliably notice statistical pitfalls on its own — small
denominators, thin samples, volatile series, etc. — so we detect them
mechanically in Python and hand them to the LLM via `metadata.caveats`.

A rule in ``system_prompt`` forces the bot to surface each caveat to the
user before giving a conclusion, which turns an analytical judgement
("this 525% is noise") into a structured signal ("`low_denominator` fired").

Every caveat has the same shape::

    {
        "type": str,                       # stable machine id
        "detail": str,                     # one sentence for the user
        "affected_rows": list[int] | None, # indices in `data`, or None when scoped to the whole response
    }

Guidelines for adding a new detector:

    - Must be **deterministic**: the same DataFrame → the same caveats.
    - Keep thresholds conservative. False positives erode user trust as
      much as false negatives.
    - Return one caveat per *type*, not per affected row — the LLM reads
      better prose than it reads 50 identical warnings.
    - Stay cheap (O(n) over the result).
"""

from __future__ import annotations

import statistics
from typing import TypedDict

import pandas as pd

MAX_CAVEATS = 5
"""Hard cap on total caveats attached to a single response."""

MAX_AFFECTED_ROWS_LISTED = 10
"""Cap on the number of row indices enumerated inside one caveat's
``affected_rows`` list. Keeps response size bounded when a filter matches
every row."""


class Caveat(TypedDict, total=False):
    """Shape of a single caveat dict (see module docstring)."""

    type: str
    detail: str
    affected_rows: list[int] | None


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_low_denominator(
    df: pd.DataFrame,
    base_col: str,
    *,
    threshold: int = 20,
    label: str = "past orders",
) -> list[Caveat]:
    """Flag rows where the denominator of a ratio is too small to be stable.

    Motivation: a 525% growth from 4 → 25 orders has a base so thin that a
    single extra order shifts the percentage by 25 points. The percentage is
    arithmetically correct but analytically meaningless.

    Returns at most one caveat (aggregated across all affected rows).
    """
    if base_col not in df.columns or df.empty:
        return []
    series = pd.to_numeric(df[base_col], errors="coerce")
    mask = series.lt(threshold)
    affected = [i for i, flag in enumerate(mask.tolist()) if bool(flag)]
    if not affected:
        return []

    preview = [int(df[base_col].iloc[i]) for i in affected[:MAX_AFFECTED_ROWS_LISTED]]
    detail = (
        f"{len(affected)} of {len(df)} rows have {label} below {threshold} "
        f"(observed: {preview}). Percentages computed on such small bases are "
        f"volatile — a single extra unit can shift them by tens of points. "
        f"Treat these as anecdotes, not trends."
    )
    return [
        {
            "type": "low_denominator",
            "detail": detail,
            "affected_rows": affected[:MAX_AFFECTED_ROWS_LISTED],
        }
    ]


def detect_small_sample(
    n: int,
    *,
    threshold: int = 5,
    scope: str = "aggregate",
) -> list[Caveat]:
    """Flag a whole-response aggregate computed over too few observations."""
    if n >= threshold:
        return []
    return [
        {
            "type": "small_sample",
            "detail": (
                f"This {scope} is computed over only {n} observations — too few "
                f"to be statistically representative. Treat the value as a data "
                f"point, not a generalisable result."
            ),
            "affected_rows": None,
        }
    ]


def detect_small_groups(
    df: pd.DataFrame,
    *,
    count_col: str = "count",
    threshold: int = 10,
) -> list[Caveat]:
    """Flag individual groups whose sample size is below ``threshold``.

    Used on ``compare_metric_across_groups`` and grouped ``aggregate``
    results — e.g. Uruguay has 7 zones while Mexico has 300+, so UY's mean
    is more volatile and should be presented with that context.

    Default threshold is 10 — the conventional "just barely defensible" size
    for a mean. Below that we consider the group too thin to generalise.
    """
    if count_col not in df.columns or df.empty:
        return []
    counts = pd.to_numeric(df[count_col], errors="coerce")
    mask = counts.lt(threshold)
    affected = [i for i, flag in enumerate(mask.tolist()) if bool(flag)]
    if not affected:
        return []

    group_labels: list[str] = []
    if "group_value" in df.columns:
        group_labels = [
            f"{df['group_value'].iloc[i]} (n={int(df[count_col].iloc[i])})"
            for i in affected[:MAX_AFFECTED_ROWS_LISTED]
        ]
    else:
        group_labels = [
            f"row {i} (n={int(df[count_col].iloc[i])})"
            for i in affected[:MAX_AFFECTED_ROWS_LISTED]
        ]

    detail = (
        f"{len(affected)} group(s) have fewer than {threshold} observations: "
        f"{', '.join(group_labels)}. Their averages are less reliable than "
        f"groups with larger samples and should be presented with that caveat."
    )
    return [
        {
            "type": "small_sample_in_group",
            "detail": detail,
            "affected_rows": affected[:MAX_AFFECTED_ROWS_LISTED],
        }
    ]


def detect_high_variance(
    values: list[float] | pd.Series,
    *,
    threshold: float = 0.3,
    label: str = "series",
) -> list[Caveat]:
    """Flag a time series / sample whose coefficient of variation is high.

    ``CV = stdev / |mean|``. A CV >= 0.3 means the signal is noisy enough
    that claiming a "trend" is optimistic. Only fires with ≥3 points.
    """
    clean: list[float] = []
    iterator = values.tolist() if isinstance(values, pd.Series) else list(values)
    for v in iterator:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if pd.isna(f):
            continue
        clean.append(f)

    if len(clean) < 3:
        return []
    mean = statistics.mean(clean)
    if abs(mean) < 1e-9:
        return []
    stdev = statistics.pstdev(clean)
    cv = stdev / abs(mean)
    if cv < threshold:
        return []

    return [
        {
            "type": "high_variance",
            "detail": (
                f"The {label} is volatile (coefficient of variation = {cv:.2f}; "
                f"values range from {min(clean):.3f} to {max(clean):.3f}). "
                f"A directional trend is not yet well-supported — the swings "
                f"dominate the signal."
            ),
            "affected_rows": None,
        }
    ]


def detect_narrow_result(
    n: int,
    *,
    threshold: int = 3,
    condition_desc: str | None = None,
) -> list[Caveat]:
    """Flag when a multi-condition query returns too few rows to generalise.

    Multivariate queries that match only 0-2 zones are "suggestive" cuts —
    they rarely reveal a repeatable pattern, so the bot should not talk
    about them as if they were generalisable findings.
    """
    if n >= threshold:
        return []
    msg = f"Only {n} zones matched"
    if condition_desc:
        msg += f" the requested conditions ({condition_desc})"
    msg += (
        ". Conclusions drawn from such a narrow result are suggestive, not "
        "representative — prefer to frame the finding as 'here are the few "
        "cases' rather than 'this is a pattern'."
    )
    return [{"type": "narrow_result", "detail": msg, "affected_rows": None}]


# ---------------------------------------------------------------------------
# Merging / capping
# ---------------------------------------------------------------------------

def merge(
    *caveat_groups: list[Caveat] | None,
    cap: int = MAX_CAVEATS,
) -> list[Caveat]:
    """Flatten several lists of caveats and truncate to ``cap``."""
    out: list[Caveat] = []
    for group in caveat_groups:
        if not group:
            continue
        out.extend(group)
        if len(out) >= cap:
            break
    return out[:cap]
