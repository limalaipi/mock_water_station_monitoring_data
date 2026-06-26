# runners/water_station.py
"""
Runner: Standard Water Station ETL
====================================
Thin orchestrator — loads config, gets adapter, runs pipeline, bulk-loads.
All logic lives in pipeline/ and database/. This file is ~50 lines.

Usage (local):
    python -m runners.water_station --db postgresql

Usage (Airflow DAG):
    from runners.water_station import run_daily_water_station_etl
    run_daily_water_station_etl(db_type="postgresql")
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader.connection_config import load_connection_config, resolve_runtime_paths
from config_loader.pipeline_config import load_pipeline_config
from database.factory import ConnectionFactory
from pipeline.etl import StatefulWaterQualityPipeline

_SCENARIO_YAML = Path(__file__).parent.parent / 'config' / 'pipeline_water_station.yaml'


def run_daily_water_station_etl(db_type: str = "postgresql", **airflow_context):
    """
    Entry point for both CLI and Airflow DAG.

    Args:
        db_type: Target database. Must match a key in connections.yaml.
    """
    # 1. Load pipeline config from YAML
    cfg = load_pipeline_config(str(_SCENARIO_YAML))
    settings = cfg['settings']

    # 2. Resolve runtime paths — per DB + per scenario
    paths = resolve_runtime_paths(db_type=db_type, scenario="water_station")

    # 3. Build pipeline
    pipeline = StatefulWaterQualityPipeline(
        quality_config        = cfg['quality_config'],
        column_quality_config = cfg['column_config'],
        settings              = settings,
        state_file            = paths['state_file'],
        data_dir              = paths['data_dir'],
        db_type               = db_type,
    )

    # 4. Get DB adapter and connect
    conn_config = load_connection_config(db_type)
    schema      = conn_config.get('schema', settings.schema)
    adapter     = ConnectionFactory.get(db_type, conn_config)
    adapter.connect()

    try:
        # 5. Ensure table exists (creates from DDL template if missing)
        adapter.ensure_table_exists(schema, settings.table)

        # 6. Run ETL — generates data, saves CSV, updates state
        df, result = pipeline.run_daily_etl()

        if result['status'] == 'HARD_STOP':
            print(f"[runner] {result['message']}")
            return result

        # 7. Bulk-load into target DB
        rows_loaded = adapter.bulk_load(df, schema, settings.table)
        print(f"[runner] Loaded {rows_loaded} rows into "
              f"{schema}.{settings.table} via {db_type}")

        return result

    finally:
        adapter.close()


def reset_pipeline(db_type: str = "postgresql"):
    """Reset pipeline state and truncate the target table."""
    cfg      = load_pipeline_config(str(_SCENARIO_YAML))
    settings = cfg['settings']
    paths    = resolve_runtime_paths(db_type=db_type, scenario="water_station")

    pipeline = StatefulWaterQualityPipeline(
        quality_config        = cfg['quality_config'],
        column_quality_config = cfg['column_config'],
        settings              = settings,
        state_file            = paths['state_file'],
        data_dir              = paths['data_dir'],
        db_type               = db_type,
    )
    pipeline.reset()

    conn_config = load_connection_config(db_type)
    schema      = conn_config.get('schema', settings.schema)
    adapter     = ConnectionFactory.get(db_type, conn_config)
    adapter.connect()
    try:
        if adapter.table_exists(schema, settings.table):
            if hasattr(adapter, 'truncate_table'):
                adapter.truncate_table(schema, settings.table)
            else:
                adapter.execute(f"TRUNCATE TABLE {schema}.{settings.table}")
            print(f"[runner] Truncated {schema}.{settings.table}")
        else:
            print(f"[runner] Table {schema}.{settings.table} does not exist — skipping truncate")
    finally:
        adapter.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Water Station ETL runner")
    parser.add_argument('--db',    default='postgresql', help='Database type')
    parser.add_argument('--reset', action='store_true',  help='Reset state and truncate table')
    args = parser.parse_args()

    if args.reset:
        reset_pipeline(args.db)
    else:
        run_daily_water_station_etl(args.db)
