"""
Tests for the compare_metrics tool.

TODO (implement once handler is ready):
    - test_compare_by_country: returns one row per country with avg/min/max.
    - test_compare_sorted_descending: results ordered by avg descending.
    - test_compare_invalid_group_by: unsupported group_by raises ValueError.
    - test_compare_with_period_filter: period filter correctly scopes results.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="compare_metrics.handle not yet implemented")
async def test_compare_by_country() -> None:
    """Returns one aggregated row per country."""
    raise NotImplementedError


@pytest.mark.skip(reason="compare_metrics.handle not yet implemented")
async def test_compare_invalid_group_by() -> None:
    """Unsupported group_by dimension raises an error."""
    raise NotImplementedError
