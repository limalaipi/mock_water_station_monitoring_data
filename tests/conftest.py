# tests/conftest.py
"""
Shared pytest fixtures for unit and integration tests.
"""

import pytest
from pathlib import Path

from pipeline.models import (
    ColumnQualityConfig,
    ColumnQualityRule,
    ColumnStrategy,
    CorruptionType,
    DataQualityConfig,
    PipelineSettings,
    QualityCheckType,
)


# ---------------------------------------------------------------------------
# Shared domain config (used by unit tests — no DB needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_quality_config() -> DataQualityConfig:
    return DataQualityConfig(
        valid_country_codes  = ['TH'],
        valid_province_codes = ['10'],
        valid_amphoe_codes   = ['1001', '1003'],
        valid_tambon_codes   = ['100101', '100108', '100301'],
        wrong_data_markers   = ['No', 'Invalid'],
    )


@pytest.fixture
def sample_column_config() -> ColumnQualityConfig:
    return ColumnQualityConfig(
        column_rules={
            'province_code': ColumnQualityRule(
                column_name='province_code',
                strategy=ColumnStrategy.FIXED,
                quality_check=QualityCheckType.VALID_PERCENT,
                corruption_type=CorruptionType.INVALID_MARKER,
                fixed_targets=[80, 70, 60],
                is_skippable=False,
            ),
            'insert_date': ColumnQualityRule(
                column_name='insert_date',
                strategy=ColumnStrategy.RANDOM,
                quality_check=QualityCheckType.NULL_PERCENT,
                corruption_type=CorruptionType.NULL,
                random_min=100,
                random_max=100,
                skip_days=[3],
                is_skippable=True,
            ),
        },
        max_days=3,
    )


@pytest.fixture
def sample_settings() -> PipelineSettings:
    return PipelineSettings(
        rows_per_day=100,
        max_days=3,
        schema='public',
        table='water_station_monitor',
    )


# ---------------------------------------------------------------------------
# Integration test helpers
# ---------------------------------------------------------------------------

def get_adapter(db_type: str):
    """
    Shared helper: load connection config and return a connected adapter.
    Skip the test if env vars for this DB are not set.
    """
    import os
    from config_loader.connection_config import load_connection_config
    from database.factory import ConnectionFactory

    try:
        conn_config = load_connection_config(db_type)
        # Check that host is actually set (not empty after env resolution)
        if not conn_config.get('host'):
            pytest.skip(f"No host configured for {db_type} — set env vars to run.")
        adapter = ConnectionFactory.get(db_type, conn_config)
        adapter.connect()
        return adapter
    except Exception as exc:
        pytest.skip(f"Could not connect to {db_type}: {exc}")


TEST_SCHEMA = 'test_dq'
TEST_TABLE  = 'water_station_monitor_test'
