# runners/water_station_quality.py
"""
Runner: Data Quality Degradation ETL
======================================
Loads pipeline_water_quality.yaml and uses WaterMonitorRowGenerator
to generate rows for the water_station_monitor table.

Usage (local):
    python -m runners.water_station_quality --db hive

Usage (Airflow DAG):
    from runners.water_station_quality import run_daily_water_quality_etl
    run_daily_water_quality_etl(db_type="hive")
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader.connection_config import load_connection_config, resolve_runtime_paths
from config_loader.pipeline_config import load_pipeline_config
from database.factory import ConnectionFactory
from pipeline.etl import StatefulWaterQualityPipeline

_SCENARIO_YAML = Path(__file__).parent.parent / 'config' / 'pipeline_water_quality.yaml'


def run_daily_water_quality_etl(db_type: str = "postgresql", **airflow_context):
    cfg      = load_pipeline_config(str(_SCENARIO_YAML))
    settings = cfg['settings']
    paths    = resolve_runtime_paths(db_type=db_type, scenario="water_quality")

    pipeline = StatefulWaterQualityPipeline(
        quality_config        = cfg['quality_config'],
        column_quality_config = cfg['column_config'],
        settings              = settings,
        state_file            = paths['state_file'],
        data_dir              = paths['data_dir'],
        db_type               = db_type,
        generator_type        = "water_monitor",   # WaterMonitorRowGenerator
    )

    conn_config = load_connection_config(db_type)
    schema      = conn_config.get('schema', settings.schema)
    adapter     = ConnectionFactory.get(db_type, conn_config)
    adapter.connect()

    try:
        adapter.ensure_table_exists(schema, settings.table)
        df, result = pipeline.run_daily_etl()

        if result['status'] == 'HARD_STOP':
            print(f"[runner] {result['message']}")
            return result

        rows_loaded = adapter.bulk_load(df, schema, settings.table)
        print(f"[runner] Loaded {rows_loaded} rows into {schema}.{settings.table} via {db_type}")
        return result

    finally:
        adapter.close()


def reset_pipeline(db_type: str = "postgresql"):
    cfg      = load_pipeline_config(str(_SCENARIO_YAML))
    settings = cfg['settings']
    paths    = resolve_runtime_paths(db_type=db_type, scenario="water_quality")

    pipeline = StatefulWaterQualityPipeline(
        quality_config        = cfg['quality_config'],
        column_quality_config = cfg['column_config'],
        settings              = settings,
        state_file            = paths['state_file'],
        data_dir              = paths['data_dir'],
        db_type               = db_type,
        generator_type        = "water_monitor",
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
    parser = argparse.ArgumentParser(description="Water Quality ETL runner")
    parser.add_argument('--db',    default='postgresql', help='Database type')
    parser.add_argument('--reset', action='store_true',  help='Reset state and truncate table')
    args = parser.parse_args()

    if args.reset:
        reset_pipeline(args.db)
    else:
        run_daily_water_quality_etl(args.db)
