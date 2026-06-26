# Water Station Monitoring — Multi-Database Data Quality Framework

A configuration-driven ETL testing framework that generates synthetic water station data with controllable quality patterns and loads it across 7 different database platforms using a unified interface.

---

## Overview

This framework was built to automate data quality unit testing across multiple databases without duplicating test logic. The same pipeline code runs against PostgreSQL, Impala, Hive, MySQL, Oracle, MSSQL, and IBM Db2 — you only change the `--db` argument.

**Key capabilities:**
- Generates realistic water station monitoring data with configurable quality degradation patterns
- Automatically creates target tables if they do not exist (using database-specific DDL templates)
- Uses UUID as the primary key — works identically on all databases including Hive and Impala which have no auto-increment
- Bulk-loads data using each database's fastest available method with automatic fallback
- All scenarios (column rules, thresholds, row counts) are defined in YAML — no Python changes needed

---

## Project Structure

```
water_station_monitoring/
│
├── config/                         # YAML configuration — no Python
│   ├── connections.yaml            # DB connection profiles (references .env)
│   ├── pipeline_water_station.yaml # Scenario 1: station master data
│   └── pipeline_water_quality.yaml # Scenario 2: monitoring measurements
│
├── database/
│   ├── factory.py                  # ConnectionFactory — maps db_type → adapter
│   ├── adapters/
│   │   ├── base.py                 # Abstract interface all adapters implement
│   │   ├── postgres.py             # PostgreSQL (COPY FROM STDIN)
│   │   ├── impala.py               # Impala (Parquet + LOAD DATA)
│   │   ├── hive.py                 # Hive (LOAD DATA LOCAL INPATH)
│   │   ├── mysql.py                # MySQL (LOAD DATA LOCAL INFILE)
│   │   ├── oracle.py               # Oracle (executemany + arraysize)
│   │   ├── mssql.py                # MSSQL (fast_executemany)
│   │   └── db2.py                  # IBM Db2 (executemany)
│   └── ddl/
│       ├── water_station/          # CREATE TABLE DDL — one file per DB
│       │   ├── postgresql.sql
│       │   ├── hive.sql
│       │   └── ...
│       └── water_station_monitor/  # CREATE TABLE DDL — one file per DB
│           ├── postgresql.sql
│           ├── hive.sql
│           └── ...
│
├── pipeline/
│   ├── models.py                   # Dataclasses and enums (single source of truth)
│   ├── generators.py               # Row generation + corruption strategies
│   ├── quality.py                  # Pure quality metric functions
│   ├── state.py                    # PipelineStateRepository (config.json I/O)
│   └── etl.py                      # StatefulWaterQualityPipeline (orchestrator)
│
├── config_loader/
│   ├── pipeline_config.py          # YAML → typed dataclass objects
│   └── connection_config.py        # connections.yaml + .env → connection dict
│
├── runners/
│   ├── water_station.py            # Entry point: water_station table
│   └── water_station_quality.py    # Entry point: water_station_monitor table
│
├── tests/
│   ├── conftest.py                 # Shared pytest fixtures
│   ├── unit/                       # No DB required
│   │   ├── test_quality.py
│   │   ├── test_generators.py
│   │   ├── test_config_loader.py
│   │   └── test_state.py
│   └── integration/                # Requires live DB connection
│       ├── test_postgres.py
│       ├── test_hive.py
│       └── ...
│
├── requirements/                   # Per-DB pip requirements (legacy)
├── pyproject.toml                  # uv project definition (recommended)
├── .env.example                    # Environment variable template
├── run.sh                          # CLI runner (Git Bash / Linux / Mac)
└── Makefile                        # Alternative runner (if make is available)
```

---

## Tables

| Table | Runner | Description |
|---|---|---|
| `water_station` | `runners/water_station.py` | Station master data — station info, officer details |
| `water_station_monitor` | `runners/water_station_quality.py` | Water quality measurements — pH, DO, BOD, WQI, etc. |

### `water_station` columns
`station_id` (UUID PK), `station_name`, `station_url`, `tambon_code`, `amphoe_code`, `province_code`, `country_code`, `officer_name`, `officer_phone`, `officer_email`, `insert_date`

### `water_station_monitor` columns
`monitor_id` (UUID PK), `station_id`, `station_url`, `tambon_code`, `amphoe_code`, `province_code`, `country_code`, `monitor_name`, `monitor_phone`, `monitor_email`, `monitor_id_card`, `department_id`, `insert_date`, `monitor_date`, `wqi`, `water_ph`, `water_do`, `water_bod`, `water_tds`, `water_temp`, `water_nh3_n`

---

## Prerequisites

- Python 3.8+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- Git Bash (Windows) or any bash-compatible shell

### Install uv (once)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Quick Start

### 1. Clone and setup

```bash
git clone <repo-url>
cd water_station_monitoring

./run.sh setup    # creates .env from .env.example
```

### 2. Fill in credentials

Open `.env` and fill in your database connection details:

```env
ENV=local

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASS=your_password
```

### 3. Install all dependencies

```bash
./run.sh sync
```

This installs everything in one command — all database drivers, base libraries, and dev tools.

### 4. Run ETL

```bash
# Run water_station pipeline against PostgreSQL (1 day)
./run.sh run-station postgresql

# Run water_station_monitor pipeline against Hive (1 day)
./run.sh run-monitor hive
```

The framework will:
1. Connect to the specified database
2. Create the target table automatically if it does not exist
3. Generate rows with UUID IDs
4. Bulk-load using the fastest available method for that database
5. Save pipeline state to `config.json`

---

## Detailed Usage

### run.sh commands

```bash
# Setup
./run.sh setup                          # Create .env from .env.example
./run.sh sync                           # Install all dependencies via uv

# Run ETL — single day, one DB
./run.sh run-station   <db>             # water_station table
./run.sh run-monitor   <db>             # water_station_monitor table
./run.sh run-all       <db>             # both tables on one DB

# Run ETL — multiple days, one DB
./run.sh run-station-loop  <db> <days>  # e.g. 10 days
./run.sh run-monitor-loop  <db> <days>

# Run ETL — all databases at once
./run.sh run-all-db                     # both tables × all 7 DBs (1 day)
./run.sh run-all-db-loop "" <days>      # both tables × all 7 DBs × N days

# Run ETL — all databases except some
# Syntax: ./run.sh run-all-db "" "" "<exclude list>"
./run.sh run-all-db "" "" "postgresql"            # skip postgresql
./run.sh run-all-db "" "" "postgresql oracle"     # skip multiple DBs
./run.sh run-all-db-loop "" 10 "postgresql"       # 10 days, skip postgresql

# Reset — clears state file and truncates target table
./run.sh reset-station  <db>
./run.sh reset-monitor  <db>
./run.sh reset-all      <db>

# Testing
./run.sh test                           # unit tests (no DB needed)
./run.sh test-integration <db>          # integration tests for one DB
./run.sh test-coverage                  # unit tests + coverage report

# Utilities
./run.sh show-state                     # print current pipeline state
./run.sh clean                          # remove __pycache__ files
./run.sh clean-data                     # delete generated CSV files
./run.sh help                           # show all commands
```

### Supported DB values

| Value | Database |
|---|---|
| `postgresql` | PostgreSQL |
| `impala` | Cloudera Impala |
| `hive` | Apache Hive |
| `mysql` | MySQL / MariaDB |
| `oracle` | Oracle Database |
| `mssql` | Microsoft SQL Server |
| `db2` | IBM Db2 |

### Examples

```bash
# Run 10-day quality degradation test on Hive
./run.sh run-monitor-loop hive 10

# Reset PostgreSQL then run fresh 10-day simulation
./run.sh reset-station postgresql
./run.sh run-station-loop postgresql 10

# Run on multiple databases back-to-back
./run.sh run-station postgresql
./run.sh run-station impala
./run.sh run-station hive

# Check state after running
./run.sh show-state
```

### Run all databases at once

```bash
# Both tables × all 7 databases — 1 day each
./run.sh run-all-db

# Both tables × all 7 databases — 10 days each
./run.sh run-all-db-loop "" 10
```

Output shows a summary at the end:

```
══════════════════════════════════════
  SUMMARY
══════════════════════════════════════
  Passed : 14 / 14
  All passed!
```

### Exclude specific databases

The 4th argument is a space-separated list of databases to skip.

```bash
# Skip postgresql
./run.sh run-all-db "" "" "postgresql"

# Skip postgresql and oracle
./run.sh run-all-db "" "" "postgresql oracle"

# 10 days, skip postgresql and oracle
./run.sh run-all-db-loop "" 10 "postgresql oracle"
```

> `""` placeholders are required for the `DB` (arg 2) and `DAYS` (arg 3) positions when using `run-all-db`.

### Argument positions reference

```
./run.sh <command> <db> <days> "<exclude>"
             1       2     3        4
```

| Arg | Used by | Example |
|---|---|---|
| `<db>` | `run-station`, `run-monitor`, `run-all`, `reset-*` | `postgresql` |
| `<days>` | `*-loop` commands | `10` |
| `<exclude>` | `run-all-db`, `run-all-db-loop` | `"postgresql oracle"` |

---

## Configuration

### Changing test scenarios

All test parameters live in `config/pipeline_*.yaml` — no Python changes needed.

```yaml
# config/pipeline_water_station.yaml

pipeline:
  rows_per_day: 1000        # rows inserted per ETL run
  max_days: 10              # hard stop after this many days
  pattern_type: INCREASE    # INCREASE | DECREASE | RANDOM
  increase_count: 3         # days per increase cycle
  decrease_count: 1         # days per decrease cycle
  target_start_quality: 75  # quality % on day 1
  target_end_quality: 100   # quality % target by max_days

target:
  schema: public
  table: water_station
```

### Changing column quality rules

```yaml
column_rules:

  province_code:
    strategy: fixed                 # fixed = per-day targets, random = range
    quality_check: valid_percent    # valid_percent | null_percent | distinct_percent | unique_percent
    corruption_type: invalid_marker # invalid_marker | null | placeholder | duplicate
    fixed_targets: [75, 80, 65, 70, 65, 95, 95, 90, 75, 80]  # one per day
    is_skippable: false

  insert_date:
    strategy: random
    quality_check: null_percent
    corruption_type: "null"
    random_min: 100
    random_max: 100
    skip_days: [3, 4, 5]           # insert_date will be NULL on these days
    is_skippable: true
```

### Switching between local and Airflow paths

```env
# .env
ENV=local      # uses STATE_FILE_LOCAL and DATA_DIR_LOCAL
ENV=airflow    # uses STATE_FILE_AIRFLOW and DATA_DIR_AIRFLOW

STATE_FILE_LOCAL=./config.json
DATA_DIR_LOCAL=./data

STATE_FILE_AIRFLOW=/opt/airflow/jobs/water_station_monitoring/config.json
DATA_DIR_AIRFLOW=/opt/airflow/jobs/water_station_monitoring/data
```

---

## Adding a New Database

1. **Add connection profile** to `config/connections.yaml`
2. **Create the adapter** in `database/adapters/newdb.py` — extend `BaseAdapter`, implement `connect()`, `close()`, `query()`, `execute()`, `bulk_load()`
3. **Register it** in `database/factory.py` — add one line to `_REGISTRY`
4. **Add DDL templates** in `database/ddl/water_station/newdb.sql` and `database/ddl/water_station_monitor/newdb.sql`
5. **Add env vars** to `.env.example`
6. **Add integration test** — copy `tests/integration/test_postgres.py`, change the adapter name

No other files need to change.

---

## Running Tests

### Unit tests (no database required)

```bash
./run.sh test
```

Tests cover: quality metric functions, row generation, UUID assignment, corruption strategies, YAML config parsing, and state file save/load.

```
tests/unit/test_quality.py        — compute_null/distinct/unique/valid_percent
tests/unit/test_generators.py     — row generation, UUID, corruption
tests/unit/test_config_loader.py  — YAML → dataclass parsing
tests/unit/test_state.py          — config.json save/load/reset
```

### Integration tests (requires live DB)

```bash
# Set credentials in .env first, then:
./run.sh test-integration postgresql
./run.sh test-integration hive
```

Integration tests verify: connection, table auto-creation, bulk load row count.

### Coverage report

```bash
./run.sh test-coverage
```

---

## Bulk Loading Strategy

Each adapter tries the fastest method available and falls back automatically:

| Database | Method 1 (fastest) | Method 2 | Method 3 |
|---|---|---|---|
| PostgreSQL | `COPY FROM STDIN` | `execute_values()` | batch insert |
| Impala | Parquet + `LOAD DATA` | batch insert | — |
| Hive | `LOAD DATA LOCAL INPATH` | batch insert | — |
| MySQL | `LOAD DATA LOCAL INFILE` | `executemany()` | batch insert |
| Oracle | `executemany()` + arraysize | batch insert | — |
| MSSQL | `fast_executemany` | batch insert | — |
| IBM Db2 | `executemany()` | batch insert | — |

---

## Airflow Integration

```python
from runners.water_station import run_daily_water_station_etl
from runners.water_station_quality import run_daily_water_quality_etl

# In a DAG task
run_daily_water_station_etl(db_type="postgresql")
run_daily_water_quality_etl(db_type="hive")
```

Set `ENV=airflow` in your Airflow environment variables to automatically use the correct state file and data directory paths.

---

## Design Patterns

| Pattern | Where used | Purpose |
|---|---|---|
| Factory | `database/factory.py` | Maps `db_type` string → adapter class |
| Strategy | `adapter.bulk_load()` | Each adapter owns its loading strategy |
| Template Method | `database/adapters/base.py` | Defines lifecycle; subclasses override only what differs |
| Repository | `pipeline/state.py` | Isolates all config.json I/O |
| DTO | `pipeline/models.py` | Typed config objects passed between layers |
