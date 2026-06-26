#!/usr/bin/env bash
# =============================================================================
# run.sh — Water Station Monitoring Framework (Git Bash / Linux / Mac)
# =============================================================================
# Usage:
#   ./run.sh setup
#   ./run.sh sync postgresql        # uv sync + install DB extra
#   ./run.sh run-station postgresql
#   ./run.sh run-monitor hive
#   ./run.sh run-station-loop postgresql 10
#   ./run.sh reset-all postgresql
#   ./run.sh test
#   ./run.sh help
# =============================================================================

set -e

COMMAND=${1:-help}
DB=${2:-postgresql}
DAYS=${3:-10}
EXCLUDE=${4:-""}          # space-separated list of DBs to skip, e.g. "postgresql oracle"

ALL_DBS="postgresql impala hive mysql oracle mssql db2"

# Filter out excluded DBs
get_target_dbs() {
    local result=""
    for db in $ALL_DBS; do
        if [[ ! " $EXCLUDE " =~ " $db " ]]; then
            result="$result $db"
        fi
    done
    echo $result
}

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'

run_cmd() {
    echo -e "${GRAY}[run] $*${NC}"
    "$@"
}

case "$COMMAND" in

# -----------------------------------------------------------------------------
setup)
    if [ ! -f .env ]; then
        cp .env.example .env
        echo -e "${GREEN}[setup] Created .env from .env.example${NC}"
        echo -e "${YELLOW}[setup] Please fill in your database credentials in .env${NC}"
    else
        echo -e "${GRAY}[setup] .env already exists — skipping${NC}"
    fi
    ;;

# -----------------------------------------------------------------------------
sync)
    echo -e "${CYAN}[sync] installing all dependencies${NC}"
    run_cmd uv sync
    ;;

# -----------------------------------------------------------------------------
run-station)
    echo -e "${CYAN}[run] water_station → $DB${NC}"
    run_cmd uv run python -m runners.water_station --db "$DB"
    ;;

run-monitor)
    echo -e "${CYAN}[run] water_station_monitor → $DB${NC}"
    run_cmd uv run python -m runners.water_station_quality --db "$DB"
    ;;

run-all)
    echo -e "${CYAN}[run] both pipelines → $DB${NC}"
    run_cmd uv run python -m runners.water_station --db "$DB"
    run_cmd uv run python -m runners.water_station_quality --db "$DB"
    ;;

run-both)
    # Both tables over ONE connection (recommended for Hive/ACID — no
    # connect/close churn, no lock-wait stalls between the two tables).
    echo -e "${CYAN}[run] both tables (single connection) → $DB${NC}"
    run_cmd uv run python -m runners.water_station_both --db "$DB"
    ;;

reset-both)
    # Truncate BOTH tables then load, all over one connection.
    echo -e "${YELLOW}[reset+run] both tables (single connection) → $DB${NC}"
    run_cmd uv run python -m runners.water_station_both --db "$DB" --reset
    ;;

run-station-loop)
    echo -e "${CYAN}[run] water_station × $DAYS days → $DB${NC}"
    for i in $(seq 1 "$DAYS"); do
        echo -e "${GRAY}  Day $i / $DAYS${NC}"
        run_cmd uv run python -m runners.water_station --db "$DB"
    done
    ;;

run-monitor-loop)
    echo -e "${CYAN}[run] water_station_monitor × $DAYS days → $DB${NC}"
    for i in $(seq 1 "$DAYS"); do
        echo -e "${GRAY}  Day $i / $DAYS${NC}"
        run_cmd uv run python -m runners.water_station_quality --db "$DB"
    done
    ;;

# Run both tables against specific databases: ./run.sh run-db mysql oracle mssql db2
run-db)
    shift  # remove command name, rest are db names
    DBS="$*"
    if [ -z "$DBS" ]; then
        echo "Usage: ./run.sh run-db mysql oracle mssql db2"
        exit 1
    fi
    PASS=0; FAIL=0; FAILED_LIST=""
    echo -e "${CYAN}[run] both tables × $DBS${NC}"
    for db in $DBS; do
        echo -e "${YELLOW}── $db ──${NC}"
        if uv run python -m runners.water_station --db "$db"; then
            echo -e "${GREEN}  [OK] water_station → $db${NC}"; PASS=$((PASS+1))
        else
            echo -e "${RED}  [FAIL] water_station → $db${NC}"; FAIL=$((FAIL+1))
            FAILED_LIST="$FAILED_LIST\n    - water_station → $db"
        fi
        if uv run python -m runners.water_station_quality --db "$db"; then
            echo -e "${GREEN}  [OK] water_station_monitor → $db${NC}"; PASS=$((PASS+1))
        else
            echo -e "${RED}  [FAIL] water_station_monitor → $db${NC}"; FAIL=$((FAIL+1))
            FAILED_LIST="$FAILED_LIST\n    - water_station_monitor → $db"
        fi
    done
    echo -e "${CYAN}  Passed: $PASS / $((PASS+FAIL))${NC}"
    [ "$FAIL" -gt 0 ] && echo -e "${RED}  Failed:$FAILED_LIST${NC}"
    ;;

# Run both tables against ALL 7 databases — single command
run-all-db)
    PASS=0
    FAIL=0
    FAILED_LIST=""
    TARGET_DBS=$(get_target_dbs)

    echo -e "${CYAN}[run] both tables × databases: $TARGET_DBS${NC}"
    [ -n "$EXCLUDE" ] && echo -e "${GRAY}  excluding: $EXCLUDE${NC}"
    echo ""

    for db in $TARGET_DBS; do
        echo -e "${YELLOW}──────────────────────────────────────${NC}"
        echo -e "${YELLOW}  DB: $db${NC}"
        echo -e "${YELLOW}──────────────────────────────────────${NC}"

        # water_station
        if uv run python -m runners.water_station --db "$db"; then
            echo -e "${GREEN}  [OK] water_station → $db${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}  [FAIL] water_station → $db${NC}"
            FAIL=$((FAIL + 1))
            FAILED_LIST="$FAILED_LIST\n    - water_station → $db"
        fi

        # water_station_monitor
        if uv run python -m runners.water_station_quality --db "$db"; then
            echo -e "${GREEN}  [OK] water_station_monitor → $db${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}  [FAIL] water_station_monitor → $db${NC}"
            FAIL=$((FAIL + 1))
            FAILED_LIST="$FAILED_LIST\n    - water_station_monitor → $db"
        fi

        echo ""
    done

    # Summary
    echo -e "${CYAN}══════════════════════════════════════${NC}"
    echo -e "${CYAN}  SUMMARY${NC}"
    echo -e "${CYAN}══════════════════════════════════════${NC}"
    echo -e "${GREEN}  Passed : $PASS / $((PASS + FAIL))${NC}"
    if [ "$FAIL" -gt 0 ]; then
        echo -e "${RED}  Failed : $FAIL${NC}"
        echo -e "${RED}  Failed list:${NC}"
        echo -e "${RED}$FAILED_LIST${NC}"
    else
        echo -e "${GREEN}  All passed!${NC}"
    fi
    ;;

# Run both tables × all databases × N days
run-all-db-loop)
    TARGET_DBS=$(get_target_dbs)
    echo -e "${CYAN}[run] both tables × databases: $TARGET_DBS × $DAYS days${NC}"
    [ -n "$EXCLUDE" ] && echo -e "${GRAY}  excluding: $EXCLUDE${NC}"
    for db in $TARGET_DBS; do
        echo -e "${YELLOW}── $db ──${NC}"
        for i in $(seq 1 "$DAYS"); do
            echo -e "${GRAY}  Day $i / $DAYS${NC}"
            uv run python -m runners.water_station --db "$db" || true
            uv run python -m runners.water_station_quality --db "$db" || true
        done
    done
    ;;

# -----------------------------------------------------------------------------
reset-station)
    echo -e "${YELLOW}[reset] water_station → $DB${NC}"
    run_cmd uv run python -m runners.water_station --db "$DB" --reset
    ;;

reset-monitor)
    echo -e "${YELLOW}[reset] water_station_monitor → $DB${NC}"
    run_cmd uv run python -m runners.water_station_quality --db "$DB" --reset
    ;;

reset-all)
    echo -e "${YELLOW}[reset] both pipelines → $DB${NC}"
    run_cmd uv run python -m runners.water_station --db "$DB" --reset
    run_cmd uv run python -m runners.water_station_quality --db "$DB" --reset
    ;;

reset-all-db)
    TARGET_DBS=$(get_target_dbs)
    echo -e "${YELLOW}[reset] both pipelines × databases: $TARGET_DBS${NC}"
    [ -n "$EXCLUDE" ] && echo -e "${GRAY}  excluding: $EXCLUDE${NC}"
    for db in $TARGET_DBS; do
        echo -e "${YELLOW}── $db ──${NC}"
        uv run python -m runners.water_station --db "$db" --reset || true
        uv run python -m runners.water_station_quality --db "$db" --reset || true
    done
    echo -e "${GREEN}[reset] done${NC}"
    ;;

# -----------------------------------------------------------------------------
test)
    echo -e "${CYAN}[test] running unit tests${NC}"
    run_cmd uv run pytest tests/unit/ -v
    ;;

test-integration)
    echo -e "${CYAN}[test] integration tests → $DB${NC}"
    run_cmd uv run pytest tests/integration/test_"$DB".py -v
    ;;

test-all)
    run_cmd uv run pytest tests/ -v
    ;;

test-coverage)
    run_cmd uv run pytest tests/unit/ --cov=pipeline --cov=config_loader --cov-report=term-missing
    ;;

# -----------------------------------------------------------------------------
show-state)
    uv run python3 - <<'EOF'
import json
try:
    with open("config.json") as f:
        d = json.load(f)
    print(f"  Current day  : {d['current_day']}")
    print(f"  Total rows   : {d['cumulative_total_rows']}")
    print(f"  Valid rows   : {d['cumulative_valid_rows']}")
    print(f"  Quality      : {round(d['cumulative_quality'], 2)} %")
    print(f"  Last run     : {d.get('last_run_date', '—')}")
except FileNotFoundError:
    print("  No state file found. Run a pipeline first.")
EOF
    ;;

clean)
    echo -e "${GRAY}[clean] removing __pycache__ and .pyc files${NC}"
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}[clean] done${NC}"
    ;;

clean-data)
    echo -e "${GRAY}[clean] removing generated CSV files${NC}"
    rm -f data/water_data_day_*.csv
    rm -f station_data/water_data_day_*.csv
    echo -e "${GREEN}[clean] done${NC}"
    ;;

# -----------------------------------------------------------------------------
help|*)
    echo ""
    echo -e "${CYAN}  Water Station Monitoring Framework${NC}"
    echo "  ==================================="
    echo ""
    echo -e "${YELLOW}  SETUP (ครั้งแรก)${NC}"
    echo "    ./run.sh setup                        Create .env from .env.example"
    echo "    ./run.sh sync                         Install everything (all DBs + dev)"
    echo ""
    echo -e "${YELLOW}  RUN  (default DB = postgresql)${NC}"
    echo "    ./run.sh run-station        hive      Run water_station ETL (1 day)"
    echo "    ./run.sh run-monitor        hive      Run water_station_monitor ETL (1 day)"
    echo "    ./run.sh run-all            postgresql Run both tables (two connections)"
    echo "    ./run.sh run-both           hive      Run both tables on ONE connection (best for Hive)"
    echo "    ./run.sh reset-both         hive      Truncate + load both tables on ONE connection"
    echo "    ./run.sh run-station-loop   postgresql 10  Run 10 days"
    echo "    ./run.sh run-monitor-loop   hive       10  Run 10 days"
    echo "    ./run.sh run-db         mysql oracle   Run both tables on specific DBs"
    echo "    ./run.sh run-all-db                   Run both tables on ALL 7 databases"
    echo "    ./run.sh run-all-db-loop           10 Run 10 days × both tables × all DBs"
    echo ""
    echo -e "${YELLOW}  RESET${NC}"
    echo "    ./run.sh reset-station  postgresql    Reset state + truncate table"
    echo "    ./run.sh reset-monitor  hive          Reset state + truncate table"
    echo "    ./run.sh reset-all      postgresql    Reset both pipelines"
    echo ""
    echo -e "${YELLOW}  TEST${NC}"
    echo "    ./run.sh test                         Unit tests (no DB needed)"
    echo "    ./run.sh test-integration postgresql  Integration tests"
    echo "    ./run.sh test-coverage                Unit tests + coverage"
    echo ""
    echo -e "${YELLOW}  UTILITIES${NC}"
    echo "    ./run.sh show-state                   Show current pipeline state"
    echo "    ./run.sh clean                        Remove __pycache__ files"
    echo "    ./run.sh clean-data                   Delete generated CSV files"
    echo ""
    ;;
esac
