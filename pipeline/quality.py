# pipeline/quality.py
"""
Quality Assessment Functions
=============================
Pure Python functions — no database dependencies, no side effects.
Each function mirrors the SQL equivalent so pipeline results match
what a data quality tool would compute directly in the database.

These functions are independently unit-testable with a plain list of values.
"""

from __future__ import annotations
from collections import Counter
from typing import Any, List
import numpy as np


def compute_distinct_percent(values: List[Any]) -> float:
    """
    % of non-null values that are distinct.

    SQL equivalent:
        CASE WHEN COUNT(col) = 0 THEN 100.0
             ELSE 100.0 * COUNT(DISTINCT col::text) / COUNT(col)
        END
    """
    non_null = [v for v in values if v is not None and not _is_nan(v)]
    if not non_null:
        return 100.0
    return 100.0 * len(set(str(v) for v in non_null)) / len(non_null)


def compute_unique_percent(values: List[Any]) -> float:
    """
    % of non-null values that appear exactly once.

    SQL equivalent:
        SUM(CASE WHEN cnt = 1 THEN 1 ELSE 0 END) / COUNT(col) * 100
        (where cnt is the frequency of each value)
    """
    non_null = [str(v) for v in values if v is not None and not _is_nan(v)]
    if not non_null:
        return 100.0
    counts = Counter(non_null)
    unique_count = sum(1 for c in counts.values() if c == 1)
    return 100.0 * unique_count / len(non_null)


def compute_null_percent(values: List[Any]) -> float:
    """
    Non-null rate: % of values that are NOT null.

    SQL equivalent:
        100.0 * COUNT(col) / COUNT(*) -- where COUNT(col) ignores nulls
    """
    total = len(values)
    if total == 0:
        return 100.0
    non_null = sum(1 for v in values if v is not None and not _is_nan(v))
    return 100.0 * non_null / total


def compute_null_placeholder_percent(values: List[Any],
                                      placeholders: List[str]) -> float:
    """
    Non-placeholder rate: % of values that are NOT a NULL-text placeholder.

    A value counts as a NULL placeholder when it is a real NULL (None / NaN)
    or when its trimmed, lower-cased string equals one of the configured
    placeholder tokens (e.g. '', 'na', 'n/a', 'null', 'missing').

    SQL equivalent:
        100.0 * SUM(CASE WHEN col IS NOT NULL
                          AND LOWER(TRIM(col)) NOT IN (<placeholders>)
                         THEN 1 ELSE 0 END) / COUNT(*)
    """
    total = len(values)
    if total == 0:
        return 100.0
    placeholder_set = {str(p).strip().lower() for p in placeholders}
    non_placeholder = sum(
        1 for v in values
        if v is not None and not _is_nan(v)
        and str(v).strip().lower() not in placeholder_set
    )
    return 100.0 * non_placeholder / total


def compute_valid_percent(values: List[Any], valid_fn) -> float:
    """
    % of values that pass a caller-supplied validation function.

    Args:
        values:   List of column values.
        valid_fn: Callable(value) → bool.  Called for each value.
    """
    total = len(values)
    if total == 0:
        return 100.0
    valid_count = sum(1 for v in values if valid_fn(v))
    return 100.0 * valid_count / total


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_nan(value: Any) -> bool:
    """Return True if value is a float NaN."""
    return isinstance(value, float) and np.isnan(value)
