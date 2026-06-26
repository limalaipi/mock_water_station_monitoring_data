# config_loader/pipeline_config.py
"""
Pipeline Config Loader
======================
Reads a pipeline_*.yaml file and returns the typed dataclass objects
the pipeline expects. This is the only place that parses YAML for pipeline
settings — runners and ETL classes never call yaml.safe_load() directly.

Raises clear errors for missing or invalid config keys so problems are
caught at startup, not mid-run.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

import yaml

from pipeline.models import (
    ColumnQualityConfig,
    ColumnQualityRule,
    ColumnStrategy,
    CorruptionType,
    DataQualityConfig,
    PipelineSettings,
    QualityCheckType,
)


def load_pipeline_config(yaml_path: str) -> Dict[str, Any]:
    """
    Parse a pipeline YAML file and return a dict with keys:
        'quality_config'  → DataQualityConfig
        'column_config'   → ColumnQualityConfig
        'settings'        → PipelineSettings

    Args:
        yaml_path: Path to a pipeline_*.yaml file.

    Returns:
        dict with the three typed config objects.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        KeyError / ValueError: If required fields are missing or invalid.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline config not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    return {
        'quality_config': _parse_data_quality(raw),
        'column_config':  _parse_column_config(raw),
        'settings':       _parse_pipeline_settings(raw),
    }


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _parse_data_quality(raw: dict) -> DataQualityConfig:
    dq = raw.get('data_quality', {})
    return DataQualityConfig(
        valid_country_codes  = dq.get('valid_country_codes',  ['TH']),
        valid_province_codes = dq.get('valid_province_codes', []),
        valid_amphoe_codes   = dq.get('valid_amphoe_codes',   []),
        valid_tambon_codes   = dq.get('valid_tambon_codes',   []),
        valid_department_id  = dq.get('valid_department_id',  []),
        wrong_data_markers   = dq.get('wrong_data_markers',   ['No', 'Invalid']),
    )


def _parse_pipeline_settings(raw: dict) -> PipelineSettings:
    p = raw.get('pipeline', {})
    t = raw.get('target', {})
    return PipelineSettings(
        rows_per_day          = int(p.get('rows_per_day',          100)),
        max_days              = int(p.get('max_days',              10)),
        pattern_type          = str(p.get('pattern_type',          'INCREASE')).upper(),
        increase_count        = int(p.get('increase_count',        3)),
        decrease_count        = int(p.get('decrease_count',        2)),
        target_start_quality  = float(p.get('target_start_quality', 20.0)),
        target_end_quality    = float(p.get('target_end_quality',   100.0)),
        schema                = str(t.get('schema', 'public')),
        table                 = str(t.get('table',  'water_station_monitor')),
    )


def _parse_column_config(raw: dict) -> ColumnQualityConfig:
    p         = raw.get('pipeline', {})
    rules_raw = raw.get('column_rules', {})

    rules = {}
    for col_name, col_raw in rules_raw.items():
        rules[col_name] = _parse_column_rule(col_name, col_raw)

    return ColumnQualityConfig(
        column_rules      = rules,
        global_skip_days  = raw.get('global_skip_days', []),
        required_columns  = raw.get('required_columns', []),
        max_days          = int(p.get('max_days', 10)),
    )


def _parse_column_rule(col_name: str, raw: dict) -> ColumnQualityRule:
    try:
        strategy      = ColumnStrategy(raw['strategy'])
        quality_check = QualityCheckType(raw.get('quality_check', 'valid_percent'))
        corruption    = CorruptionType(raw.get('corruption_type', 'invalid_marker'))
    except ValueError as exc:
        raise ValueError(f"Invalid enum value in column_rules.{col_name}: {exc}")

    return ColumnQualityRule(
        column_name         = col_name,
        strategy            = strategy,
        quality_check       = quality_check,
        corruption_type     = corruption,
        placeholder_values  = raw.get('placeholder_values', None) or [],
        fixed_targets       = raw.get('fixed_targets', None),
        random_min          = float(raw.get('random_min', 70.0)),
        random_max          = float(raw.get('random_max', 95.0)),
        skip_days           = [int(d) for d in raw.get('skip_days', [])],
        is_skippable        = bool(raw.get('is_skippable', True)),
        duplicate_pool_size = int(raw.get('duplicate_pool_size', 3)),
    )
