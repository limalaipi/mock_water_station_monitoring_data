# runners/water_station_both.py
"""
Runner: Both tables in ONE connection
======================================
Loads BOTH water_station and water_station_monitor over a SINGLE database
connection, then closes once at the very end.

Why this exists
---------------
The standard flow (`run-all`) runs two separate Python processes — each opens
its own connection, does its load, then closes. On Hive ACID tables this is
slow and can appear to "hang": closing a HiveServer2 session that touched a
transactional table can leave a lock behind, and the *next* connection waits
for it to expire (hive.txn.timeout, default 300s). Reusing one connection for
both tables removes the connect/close churn and the lock-wait stalls.

Usage (local):
    python -m runners.water_station_both --db hive
    python -m runners.water_station_both --db hive --reset   # truncate both first

Usage (Airflow DAG):
    from runners.water_station_both import run_both
    run_both(db_type="hive")
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader.connection_config import load_connection_config, resolve_runtime_paths
from config_loader.pipeline_config import load_pipeline_config
from database.factory import ConnectionFactory
from pipeline.etl import StatefulWaterQualityPipeline

_ROOT         = Path(__file__).parent.parent
_STATION_YAML = _ROOT / 'config' / 'pipeline_water_station.yaml'
_QUALITY_YAML = _ROOT / 'config' / 'pipeline_water_quality.yaml'


def _build_pipeline(yaml_path: Path, db_type: str, scenario: str,
                    generator_type: str | None = None):
    """Build a pipeline + return (pipeline, settings)."""
    cfg      = load_pipeline_config(str(yaml_path))
    settings = cfg['settings']
    paths    = resolve_runtime_paths(db_type=db_type, scenario=scenario)

    kwargs = dict(
        quality_config        = cfg['quality_config'],
        column_quality_config = cfg['column_config'],
        settings              = settings,
        state_file            = paths['state_file'],
        data_dir              = paths['data_dir'],
        db_type               = db_type,
    )
    if generator_type:
        kwargs['generator_type'] = generator_type

    return StatefulWaterQualityPipeline(**kwargs), settings


def _truncate(adapter, schema: str, table: str):
    if not adapter.table_exists(schema, table):
        print(f"[both] {schema}.{table} does not exist — skipping truncate")
        return
    if hasattr(adapter, 'truncate_table'):
        adapter.truncate_table(schema, table)
    else:
        adapter.execute(f"TRUNCATE TABLE {schema}.{table}")
    print(f"[both] Truncated {schema}.{table}")


def _load_one(adapter, schema: str, settings, pipeline):
    """Ensure table + run ETL + bulk-load. Uses the SHARED adapter; never closes it."""
    adapter.ensure_table_exists(schema, settings.table)
    df, result = pipeline.run_daily_etl()

    if result['status'] == 'HARD_STOP':
        print(f"[both] {settings.table}: {result['message']}")
        return result

    rows = adapter.bulk_load(df, schema, settings.table)
    print(f"[both] Loaded {rows} rows into {schema}.{settings.table}")
    return result


def run_both(db_type: str = "hive", reset: bool = False, **airflow_context):
    """
    Open ONE connection, process both tables, then close once.

    Args:
        db_type: Target database key from connections.yaml.
        reset:   If True, reset pipeline state and truncate both tables first.
    """
    conn_config = load_connection_config(db_type)

    # Build both pipelines up front (no DB connection needed yet).
    ws_pipe, ws_settings = _build_pipeline(_STATION_YAML, db_type, "water_station")
    wq_pipe, wq_settings = _build_pipeline(_QUALITY_YAML, db_type, "water_quality",
                                           generator_type="water_monitor")

    ws_schema = conn_config.get('schema', ws_settings.schema)
    wq_schema = conn_config.get('schema', wq_settings.schema)

    # --- ONE connection for both tables ---
    adapter = ConnectionFactory.get(db_type, conn_config)
    adapter.connect()
    results = {}
    try:
        if reset:
            ws_pipe.reset()
            wq_pipe.reset()
            _truncate(adapter, ws_schema, ws_settings.table)
            _truncate(adapter, wq_schema, wq_settings.table)

        # Do ALL inserts/deletes for both tables before closing.
        results['water_station']         = _load_one(adapter, ws_schema, ws_settings, ws_pipe)
        results['water_station_monitor'] = _load_one(adapter, wq_schema, wq_settings, wq_pipe)

        # Make sure everything is committed/flushed BEFORE we close, so the
        # next connection doesn't wait on a lingering ACID lock.
        if hasattr(adapter, 'commit'):
            adapter.commit()
        elif getattr(adapter, 'conn', None) is not None and hasattr(adapter.conn, 'commit'):
            adapter.conn.commit()

        print("[both] Both tables finished — committing and closing connection now.")
        return results

    finally:
        adapter.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load water_station + water_station_monitor over one connection")
    parser.add_argument('--db',    default='hive', help='Database type')
    parser.add_argument('--reset', action='store_true',
                        help='Reset state and truncate BOTH tables before loading')
    args = parser.parse_args()

    run_both(args.db, reset=args.reset)
