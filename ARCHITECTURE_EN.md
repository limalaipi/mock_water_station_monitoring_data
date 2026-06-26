# Architecture Proposal — Multi-Database Test Framework
### Water Station Monitoring · Data Quality Pipeline

---

## 1. Design Philosophy

The refactored framework is built on four principles drawn directly from the problems found in the current codebase:

**Configuration over code.** Every value that could change between environments, databases, or test scenarios — paths, credentials, column rules, thresholds — lives in a config file, not in Python source. You change a scenario by editing YAML, not by commenting and uncommenting lines.

**One adapter per database, zero logic in adapters.** Each database adapter knows how to connect, how to check if a table exists, how to load a DDL template, and how to bulk-load data. It knows nothing about water stations, data quality, or test scenarios. Business logic stays in the pipeline layer.

**The runner is just an orchestrator.** The runner reads config, gets a DB adapter from the factory, calls the pipeline, and calls the adapter. It never makes decisions about SQL syntax, file paths, or ID generation.

**Extend by addition, not modification.** Adding a new database means creating one new adapter file and one new DDL template. No existing files change. This is the Open/Closed Principle applied to the DB layer.

---

## 2. Design Patterns Used

### Factory Pattern — `ConnectionFactory`
Centralises the decision of which adapter class to instantiate. The rest of the codebase never imports `PostgresAdapter` or `HiveAdapter` directly — it only asks the factory for a named adapter. This means adding a new database is a one-line registration, and swapping databases in tests requires only a config change.

```
ConnectionFactory.get("hive")     → HiveAdapter instance
ConnectionFactory.get("postgres") → PostgresAdapter instance
```

### Strategy Pattern — `BulkLoader`
Each adapter encapsulates its own bulk-loading strategy. The runner calls `adapter.bulk_load(df, schema, table)` and the adapter internally decides whether to use `COPY`, `LOAD DATA INFILE`, `BULK INSERT`, or a batched `executemany()` fallback. The strategy can degrade gracefully without the runner knowing.

### Template Method Pattern — `BaseAdapter`
The abstract base class defines the skeleton of the connection lifecycle: `connect()` → `ensure_table_exists()` → `bulk_load()` → `close()`. Subclasses override only the steps that differ. Methods like `table_exists()` and `execute_ddl()` have default implementations that work for standard SQL-compliant databases, so adapters like MySQL and MSSQL may need zero overrides for those methods.

### Repository Pattern — `PipelineStateRepository`
All reads and writes to `config.json` (the runtime state file) are isolated behind a repository class. The pipeline never calls `json.load()` or `json.dump()` directly. This makes the state storage swappable (file today, database tomorrow) without touching the pipeline.

### Data Transfer Object (DTO) — `PipelineConfig`, `ColumnQualityRule`
The existing dataclasses (`DataQualityConfig`, `ColumnQualityConfig`, `ColumnQualityRule`) are already a good DTO pattern. They are kept and moved to `pipeline/models.py`. The key change is that they are instantiated by a config loader, not by hardcoded constructor calls in the runner.

---

## 3. Directory Tree

```
water_station_monitoring/
│
├── .env                          # Secrets and environment-specific settings (never committed)
├── .env.example                  # Template showing all required env variables
│
├── config/
│   ├── pipeline_water_station.yaml       # Scenario: standard water station ETL
│   ├── pipeline_water_quality.yaml       # Scenario: data quality degradation ETL
│   └── connections.yaml                  # DB connection profiles (no secrets — uses env refs)
│
├── database/
│   ├── __init__.py
│   ├── factory.py                # ConnectionFactory — maps db_type → adapter class
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py               # BaseAdapter — abstract interface all adapters implement
│   │   ├── postgres.py           # PostgresAdapter (refactored from connector/postgres.py)
│   │   ├── impala.py             # ImpalaAdapter  (refactored from connector/impala.py)
│   │   ├── hive.py               # HiveAdapter
│   │   ├── mysql.py              # MySQLAdapter
│   │   ├── oracle.py             # OracleAdapter
│   │   ├── mssql.py              # MSSQLAdapter
│   │   └── db2.py                # Db2Adapter
│   │
│   └── ddl/
│       ├── water_station_monitor/
│       │   ├── postgresql.sql    # CREATE TABLE DDL for PostgreSQL
│       │   ├── impala.sql
│       │   ├── hive.sql
│       │   ├── mysql.sql
│       │   ├── oracle.sql
│       │   ├── mssql.sql
│       │   └── db2.sql
│       └── (future tables go here as new subdirectories)
│
├── pipeline/
│   ├── __init__.py
│   ├── models.py                 # All dataclasses and enums (DTO layer)
│   │                             #   QualityPattern, ColumnStrategy, CorruptionType,
│   │                             #   QualityCheckType, ColumnQualityRule,
│   │                             #   DataQualityConfig, ColumnQualityConfig
│   ├── generators.py             # WaterMonitoringDataQualityPipeline — row generation only
│   ├── quality.py                # Quality assessment functions (compute_distinct_percent, etc.)
│   ├── state.py                  # PipelineStateRepository — all config.json read/write
│   └── etl.py                    # StatefulWaterQualityPipeline — orchestration only
│
├── config_loader/
│   ├── __init__.py
│   ├── pipeline_config.py        # Reads pipeline_*.yaml → DataQualityConfig + ColumnQualityConfig
│   └── connection_config.py      # Reads connections.yaml + .env → DB adapter config dict
│
├── runners/
│   ├── water_station.py          # Thin runner: load config → get adapter → run ETL → bulk load
│   └── water_station_quality.py  # Thin runner: same flow, different pipeline_*.yaml
│
├── data/                         # Generated CSV output (gitignored except .gitkeep)
│   └── .gitkeep
│
├── station_data/                 # Airflow-path equivalent (symlink or env-controlled)
│   └── .gitkeep
│
├── tests/
│   ├── conftest.py               # Shared pytest fixtures: adapter factory, test DB configs
│   ├── unit/
│   │   ├── test_generators.py    # Tests for row generation (no DB needed)
│   │   ├── test_quality.py       # Tests for quality compute functions (pure Python)
│   │   ├── test_config_loader.py # Tests YAML parsing produces correct config objects
│   │   └── test_state.py         # Tests state save/load round-trip
│   └── integration/
│       ├── test_postgres.py      # Full connect → create table → bulk load → assert
│       ├── test_impala.py
│       ├── test_hive.py
│       ├── test_mysql.py
│       ├── test_oracle.py
│       ├── test_mssql.py
│       └── test_db2.py
│
└── requirements/
    ├── base.txt                  # pandas, pyyaml, python-dotenv, faker, numpy
    ├── postgres.txt              # psycopg2, sqlalchemy
    ├── impala.txt                # impyla
    ├── hive.txt                  # pyhive, thrift
    ├── mysql.txt                 # mysql-connector-python
    ├── oracle.txt                # oracledb
    ├── mssql.txt                 # pyodbc
    └── db2.txt                   # ibm_db
```

---

## 4. Responsibility of Each Layer

### `config/` — Scenario and connection definitions
Contains only YAML. No Python. Two types of files live here:

- **`pipeline_*.yaml`** — one file per test scenario. Owns all values currently hardcoded in `run_daily_water_quality_etl()`: valid codes, wrong_data_markers, column rules with fixed_targets and skip_days, pipeline settings (rows_per_day, max_days, etc.). Changing a test scenario = editing this file only.
- **`connections.yaml`** — declares named connection profiles. Secrets are not stored here; they are referenced as `${POSTGRES_HOST}` and resolved from `.env` at runtime.

### `database/factory.py` — ConnectionFactory
A single function (or class) that maps a string like `"hive"` to the correct adapter class and instantiates it with the config dict from `connection_config.py`. This is the only place that imports all adapter modules. Everything else imports only the factory.

### `database/adapters/base.py` — BaseAdapter (abstract)
Defines the contract all adapters must fulfill:

| Method | Responsibility |
|---|---|
| `connect()` | Establish connection, return self |
| `close()` | Release connection cleanly |
| `table_exists(schema, table)` | Check information_schema or equivalent |
| `execute_ddl(sql)` | Run a DDL statement |
| `bulk_load(df, schema, table)` | Load DataFrame using best available method |
| `query(sql)` | Execute SELECT, return list of dicts |
| `get_dialect_now()` | Return DB-specific current timestamp SQL |

Default implementations of `table_exists()` and `execute_ddl()` use standard SQL that works for PostgreSQL, MySQL, MSSQL, Oracle, and Db2. Hive and Impala override just these two methods.

### `database/adapters/{db}.py` — Concrete adapters
Each file contains exactly one class that extends `BaseAdapter`. It overrides only the methods that differ for that database. The `bulk_load()` method implements the try→fallback chain described in the recommendations.

No adapter contains any business logic. They know nothing about water stations.

### `database/ddl/` — DDL templates
Plain `.sql` files with `{schema}` and `{table}` placeholders. One subdirectory per table, one file per database. The base adapter loads the correct file using the adapter's db_type name as the filename.

This structure makes it trivial to inspect all DDL in one place, and lets a DBA review or modify schema without opening Python files.

### `pipeline/models.py` — DTOs and enums
Consolidates everything currently duplicated between `water_station.py` and `water_station_good_quality.py`: all enums, all dataclasses. Single source of truth. Both runners import from here.

### `pipeline/generators.py` — Row generation
Contains `WaterMonitoringDataQualityPipeline`. Generates valid rows and applies corruption strategies. Knows about data shapes but not about databases. UUID assignment happens here.

### `pipeline/quality.py` — Quality functions
The three pure functions (`compute_distinct_percent`, `compute_unique_percent`, `compute_null_percent`) in isolation. They have no dependencies and are unit-testable with a simple list of values.

### `pipeline/state.py` — PipelineStateRepository
Wraps all `config.json` reads and writes. Exposes `load()`, `save()`, `reset()`, `get_summary()`. The rest of the codebase never calls `json.load()` directly.

### `pipeline/etl.py` — StatefulWaterQualityPipeline
The orchestration class. Delegates to `generators.py` for data, `state.py` for persistence, and receives an adapter for DB operations. Does not know which database it is talking to.

### `config_loader/` — Config parsing
Translates YAML files into the dataclass objects the pipeline expects (`DataQualityConfig`, `ColumnQualityConfig`). Validates required fields and provides meaningful error messages for missing config. This layer prevents YAML parsing logic from leaking into the runners.

### `runners/` — Entry points
Each runner file is now very short (~50 lines). Its only job:
1. Parse CLI args or Airflow context to determine which DB and which scenario
2. Call `config_loader` to get pipeline config
3. Call `ConnectionFactory.get(db_type)` to get an adapter
4. Call `adapter.ensure_table_exists()`
5. Call `pipeline.run_daily_etl()`
6. Call `adapter.bulk_load(df)`

No enums, no dataclasses, no SQL, no JSON parsing in runner files.

### `tests/` — Unit and integration tests
**Unit tests** (`tests/unit/`) have zero database dependencies. They test the pipeline math, config parsing, state round-trips, and row generation in pure Python.

**Integration tests** (`tests/integration/`) test one adapter each. They share a common test body via a `pytest` fixture that accepts an adapter — so adding a new DB test file means writing `adapter = ConnectionFactory.get("newdb")` and calling the shared fixture. The actual assertions (table exists, row count, timeliness calculation) are written once and run for all databases.

---

## 5. Application Flow

```
STARTUP
  │
  ├─ Load .env
  ├─ config_loader reads pipeline_water_station.yaml
  │     → DataQualityConfig
  │     → ColumnQualityConfig
  │     → PipelineSettings (rows_per_day, max_days, paths)
  │
  ├─ config_loader reads connections.yaml + .env
  │     → {host, port, db, user, password, ...} for chosen db_type
  │
  ├─ ConnectionFactory.get(db_type, config)
  │     → concrete adapter (e.g., HiveAdapter)
  │
  ├─ adapter.connect()
  │
  ├─ adapter.ensure_table_exists(schema, table)
  │     ├─ adapter.table_exists(schema, table)  → False
  │     └─ load ddl/water_station_monitor/{db_type}.sql
  │           → adapter.execute_ddl(sql)
  │
ETL RUN
  │
  ├─ PipelineStateRepository.load(state_file)
  │     → current_day, cumulative totals, pattern state
  │
  ├─ StatefulWaterQualityPipeline.run_daily_etl()
  │     ├─ determine next pattern
  │     ├─ collect column targets for this day
  │     ├─ generators.generate_valid_rows(n)
  │     │     └─ UUID assigned to each row (uuid.uuid4())
  │     ├─ apply corruption per column strategy
  │     ├─ quality.compute_*() to measure achieved quality
  │     └─ return DataFrame + column_quality_report
  │
  ├─ adapter.bulk_load(df, schema, table)
  │     ├─ try:  COPY / LOAD DATA / BULK INSERT / LOAD DATA INPATH
  │     └─ except: _fallback_batch_insert(df, batch_size=500)
  │
  ├─ PipelineStateRepository.save(updated_state)
  ├─ day_df.to_csv(daily_file)
  │
TEARDOWN
  └─ adapter.close()
```

---

## 6. Refactoring `water_station.py` and `water_station_quality.py`

### What gets moved where

| Current location | Moves to |
|---|---|
| All enums (QualityPattern, ColumnStrategy, etc.) | `pipeline/models.py` |
| All dataclasses (ColumnQualityRule, DataQualityConfig, etc.) | `pipeline/models.py` |
| `compute_distinct_percent`, `compute_unique_percent`, `compute_null_percent` | `pipeline/quality.py` |
| `WaterMonitoringDataQualityPipeline` (row generation + corruption) | `pipeline/generators.py` |
| `StatefulWaterQualityPipeline` (orchestration) | `pipeline/etl.py` |
| `_load_state`, `_save_state` | `pipeline/state.py` |
| `DataQualityConfig(valid_country_codes=["TH"], ...)` constructor call | `config/pipeline_water_station.yaml` |
| `create_column_config()` function | `config/pipeline_water_station.yaml` |
| `state_file=` and `data_dir=` path selection | `.env` (ENV variable) |
| `db = postgres.connect()` at module level | Inside `runners/water_station.py main()` |
| `db.insert_data(df=df, ...)` call | `adapter.bulk_load(df, ...)` in runner |

### What the runner files look like after refactoring

`runners/water_station.py` becomes a ~50-line orchestrator that imports from the new layers and runs the flow. It contains no class definitions, no dataclasses, and no SQL. The two runner files differ only in which YAML config they load — all shared logic is in `pipeline/etl.py`.

The distinction between the two current files (`water_station.py` produces high-quality data on day 1, `water_station_good_quality.py` uses different DEFAULT_CONFIG values) is expressed entirely in the two YAML files:
- `pipeline_water_station.yaml` — rows_per_day: 100, target_start_quality: 20
- `pipeline_water_quality.yaml` — rows_per_day: 1000, target_start_quality: 75

Same runner code, different config files.

---

## 7. Migration Plan

The migration is designed so the existing code keeps working throughout. No big-bang rewrite.

### Phase 1 — Extract shared models (no behaviour change)
Create `pipeline/models.py` by copying the enums and dataclasses from one of the runner files. Update both runner files to import from `pipeline/models.py`. Delete the duplicate definitions. **All existing behaviour is unchanged.** This is safe to do first because it is pure refactoring — no logic moves, only imports change.

Estimated effort: 1–2 hours. Risk: low.

### Phase 2 — Extract pure functions
Move `compute_distinct_percent`, `compute_unique_percent`, `compute_null_percent` to `pipeline/quality.py`. Update imports. Write the first unit tests against these functions — they are pure Python and require no DB or fixture setup.

Estimated effort: 1 hour. Risk: very low.

### Phase 3 — Extract state management
Create `pipeline/state.py` with `PipelineStateRepository`. Replace `_load_state()` and `_save_state()` calls inside `StatefulWaterQualityPipeline` with repository calls. State file paths still come from the constructor at this point — the .env switch comes in Phase 5.

Estimated effort: 2 hours. Risk: low (state logic is self-contained).

### Phase 4 — Build the adapter layer
Create `database/adapters/base.py` with the abstract interface. Refactor the existing `database/connector/postgres.py` into `database/adapters/postgres.py` to implement `BaseAdapter`. Do the same for `impala.py`. Create `database/factory.py`.

At this point the runner files can switch from:
```python
from database.connection import postgres
db = postgres.connect()
db.insert_data(df, table, schema)
```
to:
```python
from database.factory import ConnectionFactory
adapter = ConnectionFactory.get("postgres")
adapter.bulk_load(df, schema, table)
```

Estimated effort: 3–4 hours. Risk: medium (connection behaviour must be verified).

### Phase 5 — Introduce config-driven pipeline settings
Create `config_loader/pipeline_config.py`. Write `config/pipeline_water_station.yaml` containing all the values currently hardcoded in `run_daily_water_quality_etl()`. Update the runner to load from YAML instead of hardcoded constructors. Write unit tests for the config loader.

The `.env`-based path selection (`ENV=local` vs `ENV=airflow`) is implemented here, eliminating the commented-out path lines.

Estimated effort: 3–4 hours. Risk: medium (requires care to preserve all column rule nuances).

### Phase 6 — DDL templates and table auto-creation
Create `database/ddl/water_station_monitor/` with one SQL file per database. Implement `ensure_table_exists()` on the base adapter and override it in Hive/Impala. Add the UUID column to the DDL templates. Update `generators.py` to assign `uuid.uuid4()` instead of relying on DB sequences.

Estimated effort: 3–4 hours. Risk: medium (requires DDL review per database).

### Phase 7 — Remaining database adapters
Add `hive.py`, `mysql.py`, `oracle.py`, `mssql.py`, `db2.py` adapters one at a time. Each can be added independently without touching any other file. Write one integration test file per adapter.

Estimated effort: 2–4 hours per database adapter. Risk: low per adapter (isolated by design).

### Phase 8 — Slim down runners
Once phases 1–6 are complete, replace the full bodies of `water_station.py` and `water_station_good_quality.py` with thin orchestration-only code. The old files can be kept alongside during transition (under `runners/legacy/`) until the new runners are verified.

Estimated effort: 2 hours. Risk: low.

---

## 8. Trade-offs and Decisions

### YAML vs Python for column rules
The column rules (fixed_targets per day, skip_days, strategy type) are more verbose in YAML than in Python dataclass constructors. The trade-off is intentional: YAML is editable without Python knowledge and is version-controllable separately from code. For very complex conditional rules that can't be expressed in YAML, the config loader can accept a Python override file — but the default path is YAML-only.

### UUID vs integer IDs
UUID strings are 36 characters vs 4–8 bytes for an integer. For test volumes (100–1000 rows/day), this is completely irrelevant. The gain — no DB-specific DDL difference and no Hive/Impala workaround — far outweighs the storage cost.

### Single `bulk_load()` with internal fallback vs explicit method selection
The runner could call `adapter.copy_load(df)` or `adapter.batch_insert(df)` explicitly. The proposed design instead hides this choice inside `bulk_load()`. This is a deliberate trade-off: the runner becomes simpler and more portable (it doesn't need to know which method is supported), at the cost of slightly less transparency. The fallback decision is logged so failures are observable.

### Separate DDL files vs DDL in Python
Keeping DDL in `.sql` files means a DBA can review and modify schema without touching Python. The cost is that schema changes require updating multiple files. This is acceptable because schema changes are rare and the files are colocated in one folder.

### Integration tests per-adapter vs shared test matrix
Each integration test file is a thin wrapper that calls shared fixture functions. The alternative — a single parametrized test file — is cleaner but harder to run selectively (`pytest tests/integration/test_hive.py` is more explicit than `pytest -k hive`). Per-adapter files win for operational clarity.
