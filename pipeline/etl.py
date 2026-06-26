# pipeline/etl.py
"""
StatefulWaterQualityPipeline
=============================
Orchestrates one ETL day run: advances state, generates data,
measures quality, saves state, and writes the daily CSV.

Responsibilities:
  - Pattern management (increase / decrease cycles)
  - Delegating row generation to DataQualityBatchGenerator
  - Delegating state I/O to PipelineStateRepository
  - Returning a DataFrame + result dict to the runner

NOT responsible for:
  - Database connections (handled by adapters)
  - Config parsing (handled by config_loader)
  - Bulk loading (handled by adapters)
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from pipeline.generators import (
    DataQualityBatchGenerator,
    WaterMonitorBatchGenerator,
    WaterMonitorRowGenerator,
    WaterStationRowGenerator,
)
from pipeline.models import (
    ColumnQualityConfig,
    DataQualityConfig,
    PipelineSettings,
)
from pipeline.state import PipelineStateRepository


class StatefulWaterQualityPipeline:

    def __init__(
        self,
        quality_config: DataQualityConfig,
        column_quality_config: ColumnQualityConfig,
        settings: PipelineSettings,
        state_file: str,
        data_dir: str,
        generator_type: str = "water_station",   # "water_station" | "water_monitor"
        db_type: Optional[str] = None,            # target DB — used for DB-specific quirks
    ):
        self.settings     = settings
        self.col_cfg      = column_quality_config
        self.state_repo   = PipelineStateRepository(state_file)
        self.data_dir     = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Oracle stores '' as NULL, which would turn empty-string placeholders
        # into real NULLs (polluting null_percent columns). Drop '' from
        # placeholder pools so placeholder columns stay text-only on Oracle.
        if db_type and db_type.lower() == "oracle":
            self._strip_empty_placeholders(column_quality_config)

        if generator_type == "water_monitor":
            self.row_gen   = WaterMonitorRowGenerator(quality_config)
            self.batch_gen = WaterMonitorBatchGenerator(self.row_gen, column_quality_config)
        else:
            self.row_gen   = WaterStationRowGenerator(quality_config)
            self.batch_gen = DataQualityBatchGenerator(self.row_gen, column_quality_config)

        pipeline_config   = self._settings_to_dict()
        self.state        = self.state_repo.load(pipeline_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_daily_etl(
        self,
        execution_date: Optional[datetime] = None,
        rows_to_add: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Run one ETL day. Returns (DataFrame, result_dict).
        The runner is responsible for calling adapter.bulk_load(df, ...).
        """
        if execution_date is None:
            execution_date = datetime.now()
        if rows_to_add is None:
            rows_to_add = self.state['config'].get('rows_per_day',
                                                    self.settings.rows_per_day)

        next_day = self.state['current_day'] + 1
        if self.col_cfg.should_hard_stop(next_day):
            return pd.DataFrame(), {
                'status':   'HARD_STOP',
                'day':      next_day,
                'max_days': self.col_cfg.max_days,
                'message':  f'Day {next_day} exceeds max_days={self.col_cfg.max_days}',
            }

        self.state['current_day'] = next_day
        next_pattern, pattern_count = self._determine_next_pattern()
        self.state['pattern']           = next_pattern
        self.state['pattern_day_count'] = pattern_count

        start_seq = self.state['cumulative_total_rows'] + 1
        daily_data, column_report = self.batch_gen.generate(
            rows_to_add, next_day, start_seq
        )

        day_df          = pd.DataFrame(daily_data)
        actual_valid    = sum(self.row_gen.validate_row(r) for r in daily_data)
        new_total       = self.state['cumulative_total_rows'] + rows_to_add

        self.state['cumulative_total_rows']  = new_total
        self.state['cumulative_valid_rows'] += actual_valid
        self.state['cumulative_quality']     = (
            self.state['cumulative_valid_rows'] / new_total * 100
            if new_total > 0 else 0.0
        )
        self.state['last_run_date'] = execution_date.isoformat()

        self.state['quality_history'].append({
            'day':                   next_day,
            'date':                  execution_date.isoformat(),
            'pattern':               next_pattern,
            'rows_added':            rows_to_add,
            'valid_added':           actual_valid,
            'invalid_added':         rows_to_add - actual_valid,
            'cumulative_total_rows': new_total,
            'cumulative_valid_rows': self.state['cumulative_valid_rows'],
            'cumulative_quality':    round(self.state['cumulative_quality'], 2),
        })
        self.state.setdefault('column_quality_history', []).append(column_report)

        daily_file = self.data_dir / f'water_data_day_{next_day:03d}.csv'
        day_df.to_csv(daily_file, index=False)
        self.state_repo.save(self.state)

        self._print_report(next_day, next_pattern, rows_to_add,
                           actual_valid, column_report, daily_file)

        return day_df, {
            'status':               'SUCCESS',
            'day':                  next_day,
            'execution_date':       execution_date.isoformat(),
            'pattern':              next_pattern,
            'rows_added':           rows_to_add,
            'valid_added':          actual_valid,
            'cumulative_total':     new_total,
            'cumulative_quality':   round(self.state['cumulative_quality'], 2),
            'daily_file':           str(daily_file),
            'column_quality_report': column_report,
        }

    def reset(self):
        """Reset state and delete all daily CSV files."""
        self.state = self.state_repo.reset(self._settings_to_dict())
        for f in self.data_dir.glob('water_data_day_*.csv'):
            f.unlink()
        print("[etl] State reset complete.")

    def get_summary(self) -> Dict[str, Any]:
        return self.state_repo.get_summary(self.state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_empty_placeholders(column_config: ColumnQualityConfig) -> None:
        """Remove '' from every column's placeholder_values (Oracle treats '' as NULL)."""
        for rule in column_config.column_rules.values():
            if rule.placeholder_values:
                rule.placeholder_values = [
                    p for p in rule.placeholder_values if p != ''
                ]

    def _determine_next_pattern(self) -> Tuple[str, int]:
        current      = self.state['pattern']
        count        = self.state['pattern_day_count']
        inc_limit    = self.state['config'].get('increase_count', self.settings.increase_count)
        dec_limit    = self.state['config'].get('decrease_count', self.settings.decrease_count)
        if current == 'increase':
            return ('decrease', 1) if count >= inc_limit else ('increase', count + 1)
        return ('increase', 1) if count >= dec_limit else ('decrease', count + 1)

    def _settings_to_dict(self) -> Dict[str, Any]:
        return {
            'pattern_type':         self.settings.pattern_type,
            'increase_count':       self.settings.increase_count,
            'decrease_count':       self.settings.decrease_count,
            'target_start_quality': self.settings.target_start_quality,
            'target_end_quality':   self.settings.target_end_quality,
            'rows_per_day':         self.settings.rows_per_day,
        }

    def _print_report(self, day, pattern, rows_added, valid_added,
                      column_report, daily_file):
        print(f"\nDay {day} ETL complete | pattern={pattern} | "
              f"{valid_added}/{rows_added} valid | "
              f"cumulative quality={self.state['cumulative_quality']:.2f}%")
        if column_report:
            for col, stats in column_report['column_quality'].items():
                tag = " [SKIPPED]" if stats['skipped'] else ""
                print(f"  {col} ({stats['check_type']}): "
                      f"target={stats['target']:.1f}%  "
                      f"achieved={stats['achieved']:.1f}%{tag}")
        print(f"  → {daily_file}")
