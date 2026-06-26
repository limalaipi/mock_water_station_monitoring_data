"""
Data Quality Verification Test
================================
Verifies that the quality scores reported in config.json match
the actual data in the database.

Usage:
    uv run pytest tests/integration/test_quality_verify.py -v --db postgresql
    uv run pytest tests/integration/test_quality_verify.py -v --db hive
    uv run pytest tests/integration/test_quality_verify.py -v  # all DBs with state

Run as script:
    uv run python tests/integration/test_quality_verify.py --db postgresql
"""

import json
import os
import sys
import argparse
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config_loader.connection_config import load_connection_config, resolve_runtime_paths
from database.factory import ConnectionFactory


TOLERANCE = 5.0  # allowed difference % between reported and actual


# =============================================================================
# Quality metric calculators (same logic as pipeline/quality.py)
# =============================================================================

def calc_null_percent(values: list) -> float:
    """% of non-null values."""
    if not values:
        return 100.0
    non_null = sum(1 for v in values if v is not None)
    return round(100.0 * non_null / len(values), 2)


def calc_valid_percent(values: list, valid_set: list) -> float:
    """% of values in valid_set."""
    if not values:
        return 100.0
    valid_count = sum(1 for v in values if v in valid_set)
    return round(100.0 * valid_count / len(values), 2)


def calc_distinct_percent(values: list) -> float:
    """% of distinct values."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return 100.0
    return round(100.0 * len(set(str(v) for v in non_null)) / len(non_null), 2)


def calc_unique_percent(values: list) -> float:
    """% of values appearing exactly once."""
    from collections import Counter
    non_null = [str(v) for v in values if v is not None]
    if not non_null:
        return 100.0
    counts = Counter(non_null)
    unique = sum(1 for c in counts.values() if c == 1)
    return round(100.0 * unique / len(non_null), 2)


# =============================================================================
# State reader
# =============================================================================

def load_quality_state(db_type: str, scenario: str) -> dict:
    """Load the latest day's column quality report from state file."""
    paths = resolve_runtime_paths(db_type=db_type, scenario=scenario)
    state_file = paths["state_file"]

    if not Path(state_file).exists():
        print(f"  [warn] State file not found: {state_file}")
        return {}

    with open(state_file) as f:
        state = json.load(f)

    history = state.get("column_quality_history", [])
    if not history:
        return {}

    latest = history[-1]
    return {
        "day": latest["day"],
        "column_quality": latest.get("column_quality", {}),
        "total_rows": latest.get("total_rows", 0),
    }


# =============================================================================
# DB quality checker
# =============================================================================

def check_quality_in_db(db_type: str, schema: str, table: str) -> dict:
    """Query DB and compute actual quality metrics for key columns."""
    conn_config = load_connection_config(db_type)
    actual_schema = conn_config.get("schema", schema)
    adapter = ConnectionFactory.get(db_type, conn_config)
    adapter.connect()

    results = {}
    try:
        # Get latest batch (last 1000 rows by insert_date)
        limit_clause = adapter.get_dialect_limit(1000)

        # Columns to check
        check_cols = [
            "province_code", "country_code", "amphoe_code",
            "tambon_code", "officer_phone", "insert_date"
        ]

        for col in check_cols:
            try:
                sql = f"""
                    SELECT {col}
                    FROM {actual_schema}.{table}
                    ORDER BY insert_date DESC
                    {limit_clause}
                """
                rows = adapter.query(sql)
                values = [r.get(col) for r in rows]

                # Compute metrics
                results[col] = {
                    "null_percent":     calc_null_percent(values),
                    "distinct_percent": calc_distinct_percent(values),
                    "row_count":        len(values),
                }
            except Exception as e:
                results[col] = {"error": str(e)[:100]}

        # Row count total
        try:
            count_rows = adapter.query(f"SELECT COUNT(*) as cnt FROM {actual_schema}.{table}")
            results["_total_rows"] = count_rows[0].get("cnt", 0)
        except Exception:
            results["_total_rows"] = "unknown"

    finally:
        adapter.close()

    return results


# =============================================================================
# Comparison report
# =============================================================================

def compare_and_report(db_type: str, scenario: str, schema: str, table: str):
    print(f"\n{'='*60}")
    print(f"  DB: {db_type}  |  Table: {schema}.{table}")
    print(f"{'='*60}")

    # Load reported values
    state = load_quality_state(db_type, scenario)
    if not state:
        print("  [skip] No state file found — run ETL first")
        return {"status": "skip"}

    reported = state["column_quality"]
    print(f"  Reported day: {state['day']}  |  rows/day: {state['total_rows']}")

    # Query actual DB
    print("  Querying DB...")
    try:
        actual = check_quality_in_db(db_type, schema, table)
    except Exception as e:
        print(f"  [error] DB query failed: {e}")
        return {"status": "error", "error": str(e)}

    print(f"  Total rows in DB: {actual.get('_total_rows', '?')}")

    # Compare
    results = []
    print(f"\n  {'Column':<25} {'Metric':<18} {'Reported':>10} {'Actual':>10} {'Diff':>8} {'Status'}")
    print(f"  {'-'*25} {'-'*18} {'-'*10} {'-'*10} {'-'*8} {'-'*6}")

    for col, report in reported.items():
        if report.get("skipped"):
            continue

        check_type = report.get("check_type", "valid_percent")
        reported_val = report.get("achieved", 0)

        # Map check_type to actual metric
        if col in actual and "error" not in actual[col]:
            if check_type == "null_percent":
                actual_val = actual[col]["null_percent"]
            elif check_type in ("distinct_percent", "valid_percent"):
                actual_val = actual[col]["distinct_percent"]
            else:
                actual_val = None
        else:
            actual_val = None

        if actual_val is not None:
            diff = abs(reported_val - actual_val)
            status = "PASS" if diff <= TOLERANCE else "FAIL"
            results.append({
                "column": col, "check_type": check_type,
                "reported": reported_val, "actual": actual_val,
                "diff": diff, "status": status
            })
            flag = "✓" if status == "PASS" else "✗"
            print(f"  {col:<25} {check_type:<18} {reported_val:>9.1f}% {actual_val:>9.1f}% "
                  f"{diff:>7.1f}% {flag} {status}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"\n  Result: {passed}/{total} passed  |  Tolerance: ±{TOLERANCE}%")

    return {
        "status": "pass" if passed == total else "fail",
        "passed": passed, "total": total,
        "details": results
    }


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Data Quality Verification")
    parser.add_argument("--db", default="postgresql",
                        help="DB type: postgresql, hive, mysql, oracle, mssql, db2, impala")
    parser.add_argument("--schema", default=None, help="Override schema")
    args = parser.parse_args()

    db_type = args.db

    # water_station table
    schema = args.schema or ("public" if db_type == "postgresql" else "demo_dg_db")

    r1 = compare_and_report(db_type, "water_station", schema, "water_station")
    r2 = compare_and_report(db_type, "water_quality", schema, "water_station_monitor")

    # Exit code
    all_ok = (r1.get("status") in ("pass", "skip") and
              r2.get("status") in ("pass", "skip"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
