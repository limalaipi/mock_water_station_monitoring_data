# config_loader/connection_config.py
"""
Connection Config Loader
========================
Reads connections.yaml and resolves ${ENV_VAR} placeholders using
values from the .env file (loaded via python-dotenv).

Returns a plain dict ready to pass into ConnectionFactory.get().
"""

from __future__ import annotations
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env on first import
load_dotenv(override=True)

_ENV_VAR_RE = re.compile(r'\$\{([^}]+)\}')
_DEFAULT_CONNECTIONS_YAML = Path(__file__).parent.parent / 'config' / 'connections.yaml'


def load_connection_config(db_type: str,
                           yaml_path: str = None) -> dict:
    """
    Load connection settings for a specific db_type from connections.yaml,
    resolving any ${ENV_VAR} placeholders from the environment.

    Args:
        db_type:   One of the keys in connections.yaml (e.g. "postgresql").
        yaml_path: Optional override path to connections.yaml.

    Returns:
        Dict of connection parameters with all env vars resolved.

    Raises:
        KeyError: If db_type is not found in connections.yaml.
        ValueError: If a required env var is missing.
    """
    path = Path(yaml_path) if yaml_path else _DEFAULT_CONNECTIONS_YAML
    if not path.exists():
        raise FileNotFoundError(f"connections.yaml not found at {path}")

    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    databases = raw.get('databases', {})
    if db_type not in databases:
        available = ', '.join(databases.keys())
        raise KeyError(
            f"db_type '{db_type}' not found in {path}. Available: {available}"
        )

    return _resolve_env_vars(databases[db_type])


def resolve_runtime_paths(db_type: str = None, scenario: str = None) -> dict:
    """
    Resolve state_file and data_dir paths from .env based on ENV variable.

    State files are per-database and per-scenario so each DB tracks its own
    current_day independently. Example:
        db_type="postgresql", scenario="water_station"
        → state_file: ./state/water_station_postgresql.json
        → data_dir:   ./data/water_station_postgresql/

    Args:
        db_type:  Database type (e.g. "postgresql", "hive").
                  If None, falls back to the legacy single config.json.
        scenario: Pipeline scenario name (e.g. "water_station").
                  If None, uses "pipeline" as a generic prefix.

    Returns:
        {'state_file': str, 'data_dir': str}
    """
    env = os.getenv('ENV', 'local').lower()

    if db_type:
        prefix = f"{scenario}_{db_type}" if scenario else f"pipeline_{db_type}"
        if env == 'airflow':
            base_state = os.getenv('STATE_DIR_AIRFLOW',
                                   '/opt/airflow/jobs/water_station_monitoring/state')
            base_data  = os.getenv('DATA_DIR_AIRFLOW',
                                   '/opt/airflow/jobs/water_station_monitoring/data')
        else:
            base_state = os.getenv('STATE_DIR_LOCAL', './state')
            base_data  = os.getenv('DATA_DIR_LOCAL',  './data')
        return {
            'state_file': f"{base_state}/{prefix}.json",
            'data_dir':   f"{base_data}/{prefix}",
        }

    # Legacy fallback — single shared config.json (backward compatible)
    if env == 'airflow':
        return {
            'state_file': os.getenv('STATE_FILE_AIRFLOW',
                                    '/opt/airflow/jobs/water_station_monitoring/station_config.json'),
            'data_dir':   os.getenv('DATA_DIR_AIRFLOW',
                                    '/opt/airflow/jobs/water_station_monitoring/station_data'),
        }
    return {
        'state_file': os.getenv('STATE_FILE_LOCAL', './config.json'),
        'data_dir':   os.getenv('DATA_DIR_LOCAL',   './data'),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_env_vars(config: dict) -> dict:
    """Recursively resolve ${VAR} placeholders in all string values."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str):
            resolved[key] = _substitute(value)
        elif isinstance(value, dict):
            resolved[key] = _resolve_env_vars(value)
        else:
            resolved[key] = value
    return resolved


def _substitute(value: str) -> str:
    """Replace all ${VAR} occurrences with environment variable values."""
    def replacer(match):
        var_name = match.group(1)
        result = os.getenv(var_name)
        if result is None:
            # Return empty string rather than raising — caller decides if required
            return ''
        return result
    return _ENV_VAR_RE.sub(replacer, value)
