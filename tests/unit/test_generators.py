# tests/unit/test_generators.py
"""
Unit tests for pipeline/generators.py.
Verifies row generation, UUID assignment, and corruption strategies.
No DB connection needed.
"""

import uuid
import pytest
from pipeline.generators import WaterStationRowGenerator, DataQualityBatchGenerator
from pipeline.models import (
    ColumnQualityConfig, ColumnQualityRule, ColumnStrategy,
    CorruptionType, DataQualityConfig, QualityCheckType,
)


@pytest.fixture
def gen(sample_quality_config):
    return WaterStationRowGenerator(sample_quality_config)


class TestRowGeneration:

    def test_station_id_is_uuid(self, gen):
        row = gen.generate_valid_row(1)
        # Should parse as a valid UUID without raising
        uuid.UUID(row['station_id'])

    def test_station_id_unique_per_row(self, gen):
        ids = [gen.generate_valid_row(i)['station_id'] for i in range(100)]
        assert len(set(ids)) == 100

    def test_country_code_is_valid(self, gen, sample_quality_config):
        row = gen.generate_valid_row(1)
        assert row['country_code'] in sample_quality_config.valid_country_codes

    def test_row_validates(self, gen):
        row = gen.generate_valid_row(1)
        assert gen.validate_row(row) is True

    def test_insert_date_is_not_none(self, gen):
        row = gen.generate_valid_row(1)
        assert row['insert_date'] is not None


class TestCorruption:

    def test_null_corruption_sets_none(self, gen):
        rows = [gen.generate_valid_row(i) for i in range(10)]
        gen.corrupt_for_null_percent(rows, 'province_code', target_non_null=0.0)
        assert all(r['province_code'] is None for r in rows)

    def test_null_corruption_100_percent_leaves_intact(self, gen):
        rows = [gen.generate_valid_row(i) for i in range(10)]
        gen.corrupt_for_null_percent(rows, 'province_code', target_non_null=100.0)
        assert all(r['province_code'] is not None for r in rows)

    def test_valid_percent_corruption(self, gen, sample_quality_config):
        from pipeline.models import ColumnQualityRule
        rule = ColumnQualityRule(
            column_name='province_code',
            strategy=ColumnStrategy.FIXED,
            corruption_type=CorruptionType.INVALID_MARKER,
        )
        rows = [gen.generate_valid_row(i) for i in range(100)]
        gen.corrupt_for_valid_percent(rows, 'province_code', target=50.0, rule=rule)
        valid = sum(1 for r in rows
                    if r['province_code'] in sample_quality_config.valid_province_codes)
        # Allow ±5 rows tolerance
        assert 45 <= valid <= 55


class TestBatchGenerator:

    def test_generates_correct_row_count(self, sample_quality_config, sample_column_config):
        row_gen = WaterStationRowGenerator(sample_quality_config)
        batch_gen = DataQualityBatchGenerator(row_gen, sample_column_config)
        rows, report = batch_gen.generate(num_rows=50, day=1)
        assert len(rows) == 50
        assert report['total_rows'] == 50

    def test_report_has_column_quality_keys(self, sample_quality_config, sample_column_config):
        row_gen = WaterStationRowGenerator(sample_quality_config)
        batch_gen = DataQualityBatchGenerator(row_gen, sample_column_config)
        _, report = batch_gen.generate(num_rows=50, day=1)
        assert 'column_quality' in report
        assert 'province_code' in report['column_quality']

    def test_skip_day_nulls_column(self, sample_quality_config, sample_column_config):
        # insert_date has skip_days=[3] in sample_column_config
        row_gen = WaterStationRowGenerator(sample_quality_config)
        batch_gen = DataQualityBatchGenerator(row_gen, sample_column_config)
        rows, report = batch_gen.generate(num_rows=20, day=3)
        assert all(r['insert_date'] is None for r in rows)
        assert 'insert_date' in report['columns_skipped']
