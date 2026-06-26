# pipeline/state.py
"""
PipelineStateRepository
========================
All reads and writes to the JSON state file (config.json) are
isolated here. The rest of the pipeline never calls json.load()
or json.dump() directly.

Design pattern: Repository
  - Hides storage format behind a clean interface.
  - State storage is swappable (file today, database tomorrow)
    without changing any other module.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict


_DEFAULT_STATE = {
    'current_day':            0,
    'cumulative_total_rows':  0,
    'cumulative_valid_rows':  0,
    'cumulative_quality':     0.0,
    'last_run_date':          None,
    'pattern':                'increase',
    'pattern_day_count':      0,
    'quality_history':        [],
    'column_quality_history': [],
    'config':                 {},
}


class PipelineStateRepository:
    """Manages persistence of pipeline run state to a JSON file."""

    def __init__(self, state_file: str):
        self.state_file = Path(state_file)

    def load(self, pipeline_config: Dict = None) -> Dict[str, Any]:
        """
        Load state from disk. Returns default state if file does not exist
        or cannot be read. Merges in any missing keys from the default.

        Args:
            pipeline_config: Optional dict of pipeline settings to embed
                             in state['config'] when creating a fresh state.
        """
        default = _DEFAULT_STATE.copy()
        if pipeline_config:
            default['config'] = pipeline_config.copy()

        if not self.state_file.exists():
            return default

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            # Fill in any keys added since the file was last written
            for key, value in default.items():
                if key not in loaded:
                    loaded[key] = value
            if pipeline_config:
                for k, v in pipeline_config.items():
                    loaded['config'].setdefault(k, v)
            return loaded
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[state] Warning: could not load {self.state_file} ({exc}). Using defaults.")
            return default

    def save(self, state: Dict[str, Any]):
        """Persist state to disk atomically (write to tmp then rename)."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, default=str)
        tmp.replace(self.state_file)

    def reset(self, pipeline_config: Dict = None):
        """
        Delete state file, returning a clean default state.
        Does NOT delete CSV data files — that is the ETL's responsibility.
        """
        if self.state_file.exists():
            self.state_file.unlink()
        return self.load(pipeline_config)

    def get_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return a concise summary dict for logging."""
        return {
            'current_day':           state.get('current_day', 0),
            'cumulative_total_rows': state.get('cumulative_total_rows', 0),
            'cumulative_quality':    round(state.get('cumulative_quality', 0.0), 2),
        }
