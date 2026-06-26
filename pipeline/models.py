# pipeline/models.py
"""
Models (DTOs and Enums)
=======================
Single source of truth for all enums and dataclasses used across the pipeline.
Replaces duplicated definitions in water_station.py and water_station_good_quality.py.

These classes are pure data containers — no DB logic, no file I/O.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# Enums
# =============================================================================

class QualityPattern(Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    RANDOM = "random"


class ColumnStrategy(Enum):
    """How column quality targets are determined each day."""
    FIXED = "fixed"    # Uses a fixed list of targets (one per day)
    RANDOM = "random"  # Draws uniformly from [random_min, random_max]


class CorruptionType(Enum):
    """How invalid values are generated when corrupting a column."""
    NULL             = "null"           # Set value to None
    PLACEHOLDER      = "placeholder"    # Set value to a placeholder string ('missing', etc.)
    INVALID_MARKER   = "invalid_marker" # Set value to a wrong-data marker ('No', 'Invalid')
    DUPLICATE        = "duplicate"      # Replace with a repeated value (lowers distinct/unique %)


class QualityCheckType(Enum):
    """Which quality metric is measured and targeted for a column."""
    VALID_PERCENT    = "valid_percent"    # % of rows passing domain validation
    DISTINCT_PERCENT = "distinct_percent" # COUNT(DISTINCT col) / COUNT(col) * 100
    UNIQUE_PERCENT   = "unique_percent"   # values appearing exactly once / COUNT(col) * 100
    NULL_PERCENT     = "null_percent"     # % of values that are NOT real NULL (None)
    # % of values that are NOT a NULL-text placeholder ('', 'na', 'n/a', ...)
    NULL_PLACEHOLDER_PERCENT = "null_placeholder_percent"


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class ColumnQualityRule:
    """Configuration for a single column's quality simulation rule."""

    column_name: str
    strategy: ColumnStrategy

    quality_check: QualityCheckType = QualityCheckType.VALID_PERCENT
    corruption_type: CorruptionType = CorruptionType.INVALID_MARKER

    placeholder_values: List[str] = field(default_factory=lambda: [
        'null', 'undefined', 'missing', 'nan', 'none', 'na', 'n/a',
        'empty', '#n/d', 'blank', '""', "''", '-', ''
    ])

    # Fixed strategy: one target per day (index 0 = day 1)
    fixed_targets: Optional[List[float]] = None

    # Random strategy: draw from [random_min, random_max]
    random_min: float = 70.0
    random_max: float = 95.0

    # Days on which this column should be nulled out entirely
    skip_days: List[int] = field(default_factory=list)
    is_skippable: bool = True

    # For validation-based checks — allowed values
    valid_values: Optional[List[Any]] = None

    # For duplicate corruption — how many distinct repeated values to use
    duplicate_pool_size: int = 3

    def get_target_for_day(self, day: int) -> Optional[float]:
        import random
        if self.strategy == ColumnStrategy.FIXED:
            if self.fixed_targets and 0 < day <= len(self.fixed_targets):
                return self.fixed_targets[day - 1]
            return None
        return random.uniform(self.random_min, self.random_max)

    def should_skip_on_day(self, day: int) -> bool:
        return day in self.skip_days


@dataclass
class DataQualityConfig:
    """Domain-level validation rules. Populated from pipeline_*.yaml."""
    valid_country_codes: List[str]
    valid_province_codes: List[str]
    valid_amphoe_codes: List[str]
    valid_tambon_codes: List[str]
    valid_department_id: List[str] = field(default_factory=list)
    wrong_data_markers: List[str] = field(default_factory=lambda: ['NO', 'Invalid'])


@dataclass
class ColumnQualityConfig:
    """Collection of per-column rules plus global skip/required settings."""
    column_rules: Dict[str, ColumnQualityRule] = field(default_factory=dict)
    global_skip_days: List[int] = field(default_factory=list)
    required_columns: List[str] = field(default_factory=list)
    max_days: int = 10

    def should_hard_stop(self, day: int) -> bool:
        return day > self.max_days

    def is_global_skip_day(self, day: int) -> bool:
        return day in self.global_skip_days

    def get_columns_to_skip(self, day: int) -> List[str]:
        skip = []
        if self.is_global_skip_day(day):
            skip += [
                col for col, rule in self.column_rules.items()
                if rule.is_skippable and col not in self.required_columns
            ]
        skip += [
            col for col, rule in self.column_rules.items()
            if rule.should_skip_on_day(day) and col not in skip
        ]
        return skip


@dataclass
class PipelineSettings:
    """Top-level pipeline execution settings from pipeline_*.yaml."""
    rows_per_day: int = 100
    max_days: int = 10
    pattern_type: str = "INCREASE"
    increase_count: int = 3
    decrease_count: int = 2
    target_start_quality: float = 20.0
    target_end_quality: float = 100.0
    schema: str = "public"
    table: str = "water_station_monitor"
