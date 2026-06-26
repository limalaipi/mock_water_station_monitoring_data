# tests/unit/test_config_loader.py
"""
Unit tests for config_loader/pipeline_config.py.
Tests that YAML parsing produces the correct typed config objects.
No DB connection needed.
"""

import pytest
from pathlib import Path
from config_loader.pipeline_config import load_pipeline_config
from pipeline.models import ColumnStrategy, CorruptionType, QualityCheckType

_WATER_STATION_YAML = (
    Path(__file__).parent.parent.parent / 'config' / 'pipeline_water_station.yaml'
)
_WATER_QUALITY_YAML = (
    Path(__file__).parent.parent.parent / 'config' / 'pipeline_water_quality.yaml'
)


class TestLoadPipelineConfig:

    def test_loads_water_station_yaml(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        assert 'quality_config' in cfg
        assert 'column_config' in cfg
        assert 'settings' in cfg

    def test_settings_rows_per_day(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        assert cfg['settings'].rows_per_day == 1000

    def test_settings_max_days(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        assert cfg['settings'].max_days == 10

    def test_quality_config_country_codes(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        assert 'TH' in cfg['quality_config'].valid_country_codes

    def test_column_rules_loaded(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        assert 'province_code' in cfg['column_config'].column_rules
        assert 'insert_date' in cfg['column_config'].column_rules

    def test_province_code_strategy_is_fixed(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        rule = cfg['column_config'].column_rules['province_code']
        assert rule.strategy == ColumnStrategy.FIXED

    def test_insert_date_skip_days(self):
        cfg = load_pipeline_config(str(_WATER_STATION_YAML))
        rule = cfg['column_config'].column_rules['insert_date']
        assert 3 in rule.skip_days

    def test_water_quality_has_lower_rows_per_day(self):
        cfg = load_pipeline_config(str(_WATER_QUALITY_YAML))
        assert cfg['settings'].rows_per_day == 100

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_pipeline_config('/nonexistent/path.yaml')
