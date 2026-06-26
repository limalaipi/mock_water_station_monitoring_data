# pipeline/generators.py
"""
Row Generators
==============
Responsible for producing synthetic water station data rows and
applying column-level corruption to meet quality targets.

Key change from original: station_id is now a UUID (uuid.uuid4()),
generated here in Python — not by the database. This ensures identical
behaviour across all 7 supported databases including Hive and Impala,
which have no auto-increment support.

No database imports. No file I/O. Pure data transformation.
"""

from __future__ import annotations
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from faker import Faker

from pipeline.models import (
    ColumnQualityConfig,
    ColumnQualityRule,
    ColumnStrategy,
    CorruptionType,
    DataQualityConfig,
    QualityCheckType,
)
from pipeline.quality import (
    compute_distinct_percent,
    compute_null_percent,
    compute_null_placeholder_percent,
    compute_unique_percent,
    compute_valid_percent,
)

# Fallback placeholder tokens when a rule defines none.
_DEFAULT_PLACEHOLDERS = ['missing', 'null', 'n/a', 'na', 'none', '-', '']


class WaterStationRowGenerator:
    """
    Generates valid water station rows and applies corruption strategies
    to simulate configurable data quality levels.
    """

    def __init__(self, quality_config: DataQualityConfig):
        self.config = quality_config
        self.fake = Faker(['th_TH', 'en_US'])

    # ------------------------------------------------------------------
    # Valid row generation
    # ------------------------------------------------------------------

    def generate_valid_row(self, sequence_id: int) -> Dict[str, Any]:
        """
        Generate one fully valid row.
        station_id is a UUID4 string — never relies on DB auto-increment.
        """
        station_code = f"ST{sequence_id:06d}"
        return {
            'station_id':    str(uuid.uuid4()),
            'station_name':  station_code,
            'station_url':   f'https://station{station_code.lower()}.example.com',
            'tambon_code':   random.choice(self.config.valid_tambon_codes),
            'amphoe_code':   random.choice(self.config.valid_amphoe_codes),
            'province_code': random.choice(self.config.valid_province_codes),
            'country_code':  random.choice(self.config.valid_country_codes),
            'officer_name':  f"{self.fake.name()}_{station_code}",
            'officer_phone': self.fake.phone_number(),
            'officer_email': self.fake.email(),
            'insert_date':   datetime.now(),
        }

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_column(self, value: Any, column_name: str) -> bool:
        """Return True if value is valid for the given column."""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return False
        value_str = str(value)
        if any(m.lower() in value_str.lower()
               for m in self.config.wrong_data_markers if m):
            return False
        checks = {
            'country_code':  self.config.valid_country_codes,
            'province_code': self.config.valid_province_codes,
            'amphoe_code':   self.config.valid_amphoe_codes,
            'tambon_code':   self.config.valid_tambon_codes,
        }
        if column_name in checks:
            return value in checks[column_name]
        return True

    def validate_row(self, row: Dict) -> bool:
        """Return True if the row passes all critical field validations."""
        geo_fields = {
            'country_code':  self.config.valid_country_codes,
            'province_code': self.config.valid_province_codes,
            'amphoe_code':   self.config.valid_amphoe_codes,
            'tambon_code':   self.config.valid_tambon_codes,
        }
        for field, valid_set in geo_fields.items():
            if row.get(field) not in valid_set:
                return False
        for field in ['country_code', 'province_code', 'officer_name']:
            val = str(row.get(field, ''))
            if any(m.lower() in val.lower()
                   for m in self.config.wrong_data_markers if m):
                return False
        return True

    # ------------------------------------------------------------------
    # Corruption strategies
    # ------------------------------------------------------------------

    def corrupt_for_valid_percent(self, rows: List[Dict], col: str,
                                   target: float, rule: ColumnQualityRule):
        """Replace (100-target)% of values with invalid markers."""
        n = len(rows)
        invalid_count = n - int(n * target / 100.0)
        indices = random.sample(range(n), min(invalid_count, n))
        for idx in indices:
            rows[idx][col] = self._invalid_value(col, rule)

    def corrupt_for_null_percent(self, rows: List[Dict], col: str,
                                  target_non_null: float):
        """Set (100 - target_non_null)% of values to None."""
        n = len(rows)
        null_count = int(n * (100.0 - target_non_null) / 100.0)
        for idx in random.sample(range(n), min(null_count, n)):
            rows[idx][col] = None

    def corrupt_for_null_placeholder_percent(self, rows: List[Dict], col: str,
                                              target_non_placeholder: float,
                                              rule: ColumnQualityRule):
        """Set (100 - target_non_placeholder)% of values to a NULL-text placeholder."""
        pool = rule.placeholder_values or _DEFAULT_PLACEHOLDERS
        n = len(rows)
        placeholder_count = int(n * (100.0 - target_non_placeholder) / 100.0)
        for idx in random.sample(range(n), min(placeholder_count, n)):
            rows[idx][col] = random.choice(pool)

    def corrupt_for_distinct_percent(self, rows: List[Dict], col: str,
                                      target: float, rule: ColumnQualityRule):
        """Reduce distinct value count to match target %."""
        non_null_idx = [i for i, r in enumerate(rows) if r.get(col) is not None]
        n = len(non_null_idx)
        if n == 0:
            return
        target_distinct = max(1, int(round(n * target / 100.0)))
        val_map: Dict[str, List[int]] = {}
        for i in non_null_idx:
            v = str(rows[i][col])
            val_map.setdefault(v, []).append(i)
        current_distinct = len(val_map)
        if current_distinct <= target_distinct:
            return
        vals = list(val_map.keys())
        random.shuffle(vals)
        keep = vals[:target_distinct]
        pool = keep[:min(rule.duplicate_pool_size, len(keep))]
        for v in vals[target_distinct:]:
            for idx in val_map[v]:
                rows[idx][col] = random.choice(pool)

    def corrupt_for_unique_percent(self, rows: List[Dict], col: str,
                                    target: float, rule: ColumnQualityRule):
        """Reduce count of values appearing exactly once to match target %."""
        from collections import Counter
        non_null_idx = [i for i, r in enumerate(rows) if r.get(col) is not None]
        n = len(non_null_idx)
        if n == 0:
            return
        counts = Counter(str(rows[i][col]) for i in non_null_idx)
        unique_vals = {v for v, c in counts.items() if c == 1}
        target_unique = int(round(n * target / 100.0))
        if len(unique_vals) <= target_unique:
            return
        unique_idx = [i for i in non_null_idx if str(rows[i][col]) in unique_vals]
        random.shuffle(unique_idx)
        excess = len(unique_vals) - target_unique
        pairs = excess // 2
        remainder = excess % 2
        ptr = 0
        for _ in range(pairs):
            if ptr + 1 >= len(unique_idx):
                break
            rows[unique_idx[ptr + 1]][col] = rows[unique_idx[ptr]][col]
            ptr += 2
        if remainder and ptr < len(unique_idx):
            updated = Counter(str(rows[i][col]) for i in non_null_idx)
            non_unique = [v for v, c in updated.items() if c >= 2]
            if non_unique:
                rows[unique_idx[ptr]][col] = random.choice(non_unique)
            elif ptr + 1 < len(unique_idx):
                rows[unique_idx[ptr + 1]][col] = rows[unique_idx[ptr]][col]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _invalid_value(self, col: str, rule: ColumnQualityRule) -> Any:
        if rule.corruption_type == CorruptionType.NULL:
            return None
        if rule.corruption_type == CorruptionType.PLACEHOLDER:
            pool = rule.placeholder_values or ['missing', 'null', 'n/a', '-', '']
            return random.choice(pool)
        if rule.corruption_type == CorruptionType.DUPLICATE:
            return "__DUPLICATE__"
        # Default: INVALID_MARKER
        return random.choice(self.config.wrong_data_markers)


class DataQualityBatchGenerator:
    """
    Generates a batch of rows for one ETL day, applying all column-level
    quality rules from ColumnQualityConfig.
    """

    def __init__(self, row_generator: WaterStationRowGenerator,
                 column_config: ColumnQualityConfig):
        self.gen = row_generator
        self.col_cfg = column_config

    def generate(self, num_rows: int, day: int,
                 start_seq: int = 1) -> Tuple[List[Dict], Dict]:
        """
        Generate num_rows rows for the given day, applying all column rules.

        Returns:
            (data_rows, column_report)
        """
        columns_to_skip = self.col_cfg.get_columns_to_skip(day)
        is_global_skip = self.col_cfg.is_global_skip_day(day)

        # Collect day targets
        column_targets = {
            col: rule.get_target_for_day(day)
            for col, rule in self.col_cfg.column_rules.items()
            if rule.get_target_for_day(day) is not None
        }

        # 1. Generate all valid rows
        rows = [self.gen.generate_valid_row(start_seq + i) for i in range(num_rows)]

        # 2. Null out skipped columns
        for row in rows:
            for col in columns_to_skip:
                if col in row:
                    row[col] = None

        # 3. Apply corruption per column
        for col, target in column_targets.items():
            if col in columns_to_skip:
                continue
            rule = self.col_cfg.column_rules[col]
            check = rule.quality_check
            if check == QualityCheckType.VALID_PERCENT:
                self.gen.corrupt_for_valid_percent(rows, col, target, rule)
            elif check == QualityCheckType.NULL_PERCENT:
                self.gen.corrupt_for_null_percent(rows, col, target)
            elif check == QualityCheckType.NULL_PLACEHOLDER_PERCENT:
                self.gen.corrupt_for_null_placeholder_percent(rows, col, target, rule)
            elif check == QualityCheckType.DISTINCT_PERCENT:
                self.gen.corrupt_for_distinct_percent(rows, col, target, rule)
            elif check == QualityCheckType.UNIQUE_PERCENT:
                self.gen.corrupt_for_unique_percent(rows, col, target, rule)

        # 4. Measure achieved quality per column
        column_achieved = {}
        for col, target in column_targets.items():
            rule = self.col_cfg.column_rules[col]
            values = [r.get(col) for r in rows]
            check = rule.quality_check
            if check == QualityCheckType.VALID_PERCENT:
                achieved = round(compute_valid_percent(
                    values, lambda v, c=col: self.gen.validate_column(v, c)), 2)
            elif check == QualityCheckType.NULL_PERCENT:
                achieved = round(compute_null_percent(values), 2)
            elif check == QualityCheckType.NULL_PLACEHOLDER_PERCENT:
                achieved = round(compute_null_placeholder_percent(
                    values, rule.placeholder_values or _DEFAULT_PLACEHOLDERS), 2)
            elif check == QualityCheckType.DISTINCT_PERCENT:
                achieved = round(compute_distinct_percent(values), 2)
            elif check == QualityCheckType.UNIQUE_PERCENT:
                achieved = round(compute_unique_percent(values), 2)
            else:
                achieved = 0.0
            column_achieved[col] = {
                'check_type': rule.quality_check.value,
                'target':     target,
                'achieved':   achieved,
                'skipped':    col in columns_to_skip,
            }

        report = {
            'day':               day,
            'is_global_skip_day': is_global_skip,
            'columns_skipped':   columns_to_skip,
            'column_quality':    column_achieved,
            'total_rows':        num_rows,
        }
        return rows, report


# =============================================================================
# Water Station Monitor Generator
# Generates rows for water_station_monitor table (measurement data)
# Source: water_station_monitor.py (v2)
# Different from WaterStationRowGenerator — different columns entirely
# =============================================================================

class WaterMonitorRowGenerator:
    """
    Generates valid water_station_monitor rows.

    Columns: monitor_id (UUID PK), station_id (ST01-ST99 ref),
             station_url, tambon/amphoe/province/country_code,
             monitor_name, monitor_phone, monitor_email, monitor_id_card,
             department_id, insert_date, monitor_date,
             wqi, water_ph, water_do, water_bod, water_tds, water_temp, water_nh3_n
    """

    FIRST_NAMES = [
        'Somchai', 'Somsak', 'Surachai', 'Narong', 'Prasert', 'Wichai',
        'Apinya', 'Siriwan', 'Nuttaya', 'Kanokwan', 'Siriporn',
        'John', 'David', 'Michael', 'Sarah', 'Emily',
    ]
    LAST_NAMES = [
        'Sooksai', 'Chaiwong', 'Thongkham', 'Buasri', 'Saetang',
        'Smith', 'Johnson', 'Williams', 'Brown', 'Jones',
    ]

    def __init__(self, quality_config: DataQualityConfig):
        self.config = quality_config

    def generate_valid_row(self, sequence_id: int) -> Dict[str, Any]:
        """
        Generate one fully valid monitoring row.
        monitor_id = UUID4 (surrogate PK, app-generated)
        station_id = ST01-ST99 (foreign reference, not unique per row)
        """
        station_code = f"ST{random.randint(1, 99):02d}"
        first = random.choice(self.FIRST_NAMES)
        last  = random.choice(self.LAST_NAMES)
        email = f"{first.lower()}{random.randint(1, 999)}@{random.choice(['gmail.com','yahoo.com','mail.com'])}"
        phone = f"0{random.randint(100000000, 999999999):09d}"

        # Valid Thai national ID (13 digits with check digit)
        digits = [random.randint(1, 8)] + [random.randint(0, 9) for _ in range(11)]
        total  = sum(digits[i] * (13 - i) for i in range(12))
        digits.append((11 - (total % 11)) % 10)
        id_card = ''.join(map(str, digits))

        monitor_date = datetime.now()

        return {
            'monitor_id':     str(uuid.uuid4()),
            'station_id':     station_code,
            'station_url':    f'https://station{station_code.lower()}.example.com',
            'tambon_code':    random.choice(self.config.valid_tambon_codes),
            'amphoe_code':    random.choice(self.config.valid_amphoe_codes),
            'province_code':  random.choice(self.config.valid_province_codes),
            'country_code':   random.choice(self.config.valid_country_codes),
            'monitor_name':   f"{first} {last}",
            'monitor_phone':  phone,
            'monitor_email':  email,
            'monitor_id_card': id_card,
            'department_id':  random.choice(self.config.valid_department_id) if hasattr(self.config, 'valid_department_id') else 'DEPT001',
            'insert_date':    datetime.now(),
            'monitor_date':   monitor_date,
            'wqi':            round(random.uniform(0, 100), 2),
            'water_ph':       round(random.uniform(6.5, 8.5), 2),
            'water_do':       round(random.uniform(5, 9), 2),
            'water_bod':      round(random.uniform(0, 5), 2),
            'water_tds':      round(random.uniform(100, 500), 2),
            'water_temp':     round(random.uniform(20, 35), 2),
            'water_nh3_n':    round(random.uniform(0.01, 0.5), 3),
        }

    def validate_column(self, value: Any, column_name: str) -> bool:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return False
        value_str = str(value)
        if any(m.lower() in value_str.lower()
               for m in self.config.wrong_data_markers if m):
            return False
        geo = {
            'country_code':  self.config.valid_country_codes,
            'province_code': self.config.valid_province_codes,
            'amphoe_code':   self.config.valid_amphoe_codes,
            'tambon_code':   self.config.valid_tambon_codes,
        }
        if column_name in geo:
            return value in geo[column_name]
        if column_name in ['wqi', 'water_ph', 'water_do', 'water_bod',
                           'water_tds', 'water_temp', 'water_nh3_n']:
            try:
                return float(value) >= 0
            except (ValueError, TypeError):
                return False
        return True

    def validate_row(self, row: Dict) -> bool:
        geo = {
            'country_code':  self.config.valid_country_codes,
            'province_code': self.config.valid_province_codes,
            'amphoe_code':   self.config.valid_amphoe_codes,
            'tambon_code':   self.config.valid_tambon_codes,
        }
        for col, valid_set in geo.items():
            if row.get(col) not in valid_set:
                return False
        for col in ['wqi', 'water_ph', 'water_do', 'water_bod',
                    'water_tds', 'water_temp', 'water_nh3_n']:
            try:
                if float(row[col]) < 0:
                    return False
            except (ValueError, TypeError):
                return False
        return True


class WaterMonitorBatchGenerator:
    """Batch generator for water_station_monitor rows."""

    def __init__(self, row_generator: WaterMonitorRowGenerator,
                 column_config: ColumnQualityConfig):
        self.gen     = row_generator
        self.col_cfg = column_config

    def generate(self, num_rows: int, day: int,
                 start_seq: int = 1) -> Tuple[List[Dict], Dict]:

        columns_to_skip = self.col_cfg.get_columns_to_skip(day)
        is_global_skip  = self.col_cfg.is_global_skip_day(day)

        column_targets = {
            col: rule.get_target_for_day(day)
            for col, rule in self.col_cfg.column_rules.items()
            if rule.get_target_for_day(day) is not None
        }

        rows = [self.gen.generate_valid_row(start_seq + i) for i in range(num_rows)]

        for row in rows:
            for col in columns_to_skip:
                if col in row:
                    row[col] = None

        for col, target in column_targets.items():
            if col in columns_to_skip:
                continue
            rule  = self.col_cfg.column_rules[col]
            check = rule.quality_check
            if check == QualityCheckType.VALID_PERCENT:
                n_invalid = num_rows - int(num_rows * target / 100.0)
                for idx in random.sample(range(num_rows), min(n_invalid, num_rows)):
                    rows[idx][col] = random.choice(self.gen.config.wrong_data_markers)
            elif check == QualityCheckType.NULL_PERCENT:
                n_null = int(num_rows * (100.0 - target) / 100.0)
                for idx in random.sample(range(num_rows), min(n_null, num_rows)):
                    rows[idx][col] = None

        column_achieved = {}
        for col, target in column_targets.items():
            rule   = self.col_cfg.column_rules[col]
            values = [r.get(col) for r in rows]
            check  = rule.quality_check
            if check == QualityCheckType.VALID_PERCENT:
                achieved = round(compute_valid_percent(
                    values, lambda v, c=col: self.gen.validate_column(v, c)), 2)
            elif check == QualityCheckType.NULL_PERCENT:
                achieved = round(compute_null_percent(values), 2)
            elif check == QualityCheckType.DISTINCT_PERCENT:
                achieved = round(compute_distinct_percent(values), 2)
            elif check == QualityCheckType.UNIQUE_PERCENT:
                achieved = round(compute_unique_percent(values), 2)
            else:
                achieved = 0.0
            column_achieved[col] = {
                'check_type': rule.quality_check.value,
                'target':     target,
                'achieved':   achieved,
                'skipped':    col in columns_to_skip,
            }

        return rows, {
            'day':               day,
            'is_global_skip_day': is_global_skip,
            'columns_skipped':   columns_to_skip,
            'column_quality':    column_achieved,
            'total_rows':        num_rows,
        }
