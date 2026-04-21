"""Shared helpers for tool handlers.

All tool handlers return a uniform dict:

    {
        "summary":  str,          # one or two sentences, LLM-readable
        "data":     list[dict],   # max MAX_ROWS records, JSON-ready
        "metadata": dict,         # total_count, truncated, scale_note, caveats, errors...
    }

This module centralises the construction of that shape so handlers stay thin.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from backend.prompts.metric_dictionary import get_metric_info
from backend.tools._caveats import Caveat

logger = logging.getLogger(__name__)

MAX_ROWS = 50


def format_response(
    data: pd.DataFrame | list[dict],
    *,
    summary: str,
    metric: str | None = None,
    caveats: list[Caveat] | None = None,
    extra_metadata: dict | None = None,
) -> dict:
    """Build the standard tool response dict, truncating to MAX_ROWS.

    Args:
        data: DataFrame or list of records returned by the repository.
        summary: One-/two-sentence LLM-readable summary.
        metric: Optional metric name, used to attach ``scale_note`` for
            non-proportion scales.
        caveats: Optional list of :class:`Caveat` dicts produced by the
            detectors in :mod:`backend.tools._caveats`. When non-empty,
            attached as ``metadata.caveats`` — the system prompt forces the
            LLM to surface each caveat before giving a conclusion.
        extra_metadata: Merged into the final metadata dict (wins over
            auto-populated keys).
    """
    if isinstance(data, pd.DataFrame):
        total_count = len(data)
        truncated = total_count > MAX_ROWS
        records = data.head(MAX_ROWS).to_dict(orient="records")
    else:
        total_count = len(data)
        truncated = total_count > MAX_ROWS
        records = list(data[:MAX_ROWS])

    metadata: dict[str, Any] = {"total_count": total_count, "truncated": truncated}
    _maybe_attach_scale_note(metadata, metric)
    if caveats:
        metadata["caveats"] = caveats
    if extra_metadata:
        metadata.update(extra_metadata)

    return {"summary": summary, "data": records, "metadata": metadata}


def error_response(error: Exception | str) -> dict:
    """Structured error response for invalid inputs.

    The LLM receives a readable `summary` and `metadata.error=True` so it can
    apologise / retry rather than crash the turn.
    """
    msg = str(error)
    return {
        "summary": f"Invalid input: {msg}",
        "data": [],
        "metadata": {"error": True, "reason": msg, "total_count": 0, "truncated": False},
    }


def empty_response(reason: str, *, metric: str | None = None) -> dict:
    """Response for a successful query that returned zero rows."""
    metadata: dict[str, Any] = {
        "total_count": 0,
        "truncated": False,
        "empty_reason": reason,
    }
    _maybe_attach_scale_note(metadata, metric)
    return {"summary": reason, "data": [], "metadata": metadata}


def _maybe_attach_scale_note(metadata: dict, metric: str | None) -> None:
    """Add a scale hint when the metric is monetary or an unbounded ratio."""
    if not metric:
        return
    info = get_metric_info(metric)
    if info and info["scale"] != "proportion":
        metadata["scale_note"] = info["scale_note"]
