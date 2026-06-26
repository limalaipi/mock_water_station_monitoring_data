# tests/unit/test_quality.py
"""
Unit tests for pipeline/quality.py — pure functions, no DB required.
"""

import pytest
from pipeline.quality import (
    compute_distinct_percent,
    compute_null_percent,
    compute_unique_percent,
    compute_valid_percent,
)


class TestComputeNullPercent:
    def test_all_non_null(self):
        assert compute_null_percent([1, 2, 3]) == 100.0

    def test_all_null(self):
        assert compute_null_percent([None, None]) == 0.0

    def test_half_null(self):
        assert compute_null_percent([1, None, 2, None]) == 50.0

    def test_empty_list(self):
        assert compute_null_percent([]) == 100.0


class TestComputeDistinctPercent:
    def test_all_distinct(self):
        assert compute_distinct_percent(['a', 'b', 'c']) == 100.0

    def test_all_same(self):
        assert compute_distinct_percent(['a', 'a', 'a']) == pytest.approx(33.33, abs=0.1)

    def test_ignores_nulls(self):
        # None values are excluded from both numerator and denominator
        result = compute_distinct_percent([None, 'a', 'b'])
        assert result == 100.0

    def test_empty(self):
        assert compute_distinct_percent([]) == 100.0


class TestComputeUniquePercent:
    def test_all_unique(self):
        assert compute_unique_percent(['a', 'b', 'c']) == 100.0

    def test_no_unique(self):
        assert compute_unique_percent(['a', 'a', 'b', 'b']) == 0.0

    def test_half_unique(self):
        # 'a' appears twice (not unique), 'b' appears once (unique)
        result = compute_unique_percent(['a', 'a', 'b'])
        assert result == pytest.approx(33.33, abs=0.1)

    def test_empty(self):
        assert compute_unique_percent([]) == 100.0


class TestComputeValidPercent:
    def test_all_valid(self):
        result = compute_valid_percent(['TH', 'TH'], lambda v: v == 'TH')
        assert result == 100.0

    def test_none_valid(self):
        result = compute_valid_percent(['XX', 'YY'], lambda v: v == 'TH')
        assert result == 0.0

    def test_half_valid(self):
        result = compute_valid_percent(['TH', 'XX'], lambda v: v == 'TH')
        assert result == 50.0

    def test_empty(self):
        result = compute_valid_percent([], lambda v: True)
        assert result == 100.0
