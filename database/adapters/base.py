# database/adapters/base.py
"""
BaseAdapter
===========
Abstract base class that all database adapters must implement.
Defines the contract for connection lifecycle, DDL, and data operations.

Design pattern: Template Method
  - Skeleton methods (table_exists, execute_ddl) have default SQL-standard
    implementations that work for most databases.
  - Hive and Impala override only the methods that differ.
  - bulk_load() is abstract — each adapter defines its own strategy.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

# Root of the DDL templates folder, relative to this file.
_DDL_ROOT = Path(__file__).parent.parent / "ddl"


class BaseAdapter(ABC):

    # Subclasses set this to match their registry key, e.g. "postgresql"
    db_type: str = ""

    def __init__(self, config: dict):
        self.config = config
        self.conn = None
        self.cur = None

    # ------------------------------------------------------------------
    # Connection lifecycle — must be implemented by every adapter
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> "BaseAdapter":
        """Open connection. Returns self for chaining."""
        ...

    @abstractmethod
    def close(self):
        """Release connection and cursor cleanly."""
        ...

    # ------------------------------------------------------------------
    # Query execution — must be implemented by every adapter
    # ------------------------------------------------------------------

    @abstractmethod
    def query(self, sql: str, close: bool = False) -> list[dict]:
        """Execute a SELECT statement and return rows as list of dicts."""
        ...

    @abstractmethod
    def execute(self, sql: str):
        """Execute a non-SELECT statement (INSERT, UPDATE, DDL, etc.)."""
        ...

    # ------------------------------------------------------------------
    # DDL and table management
    # Default implementations use information_schema (standard SQL).
    # Override in Hive / Impala.
    # ------------------------------------------------------------------

    def table_exists(self, schema: str, table: str) -> bool:
        """
        Return True if the table exists in the given schema.
        Uses information_schema.tables — valid for PG, MySQL, MSSQL, Oracle, Db2.
        """
        sql = f"""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE LOWER(table_schema) = LOWER('{schema}')
              AND LOWER(table_name)   = LOWER('{table}')
        """
        rows = self.query(sql)
        return rows[0]["cnt"] > 0

    def load_ddl(self, table_folder: str) -> str:
        """
        Load the DDL template for this adapter's db_type.

        Args:
            table_folder: Name of the subdirectory under database/ddl/,
                          e.g. 'water_station_monitor'.

        Returns:
            DDL SQL string with {schema} and {table} placeholders.

        Raises:
            FileNotFoundError: If no DDL file exists for this db_type.
        """
        ddl_path = _DDL_ROOT / table_folder / f"{self.db_type}.sql"
        if not ddl_path.exists():
            raise FileNotFoundError(
                f"No DDL template found at {ddl_path}. "
                f"Create database/ddl/{table_folder}/{self.db_type}.sql"
            )
        return ddl_path.read_text(encoding="utf-8")

    def ensure_table_exists(self, schema: str, table: str, table_folder: str = None):
        """
        Check if table exists; create it from the DDL template if not.

        Args:
            schema:       Target schema/database name.
            table:        Target table name.
            table_folder: DDL subfolder name. Defaults to the table name.
        """
        folder = table_folder or table
        if not self.table_exists(schema, table):
            print(f"[{self.db_type}] Table {schema}.{table} not found — creating...")
            ddl_template = self.load_ddl(folder)
            ddl = ddl_template.format(schema=schema, table=table)
            self.execute_ddl(ddl)
            print(f"[{self.db_type}] Table {schema}.{table} created.")
        else:
            print(f"[{self.db_type}] Table {schema}.{table} already exists.")

    def execute_ddl(self, sql: str):
        """Execute a DDL statement. Override if DDL requires special handling."""
        self.execute(sql)

    # ------------------------------------------------------------------
    # Bulk loading — must be implemented by every adapter
    # ------------------------------------------------------------------

    @abstractmethod
    def bulk_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        """
        Load a DataFrame into the target table using the most efficient
        method available for this database.

        Implementations should follow the try→fallback pattern:
            1. Try fastest method (COPY, LOAD DATA, BULK INSERT, etc.)
            2. Fall back to _batch_insert() on any exception.

        Returns:
            Number of rows successfully loaded.
        """
        ...

    def _batch_insert(self, df: pd.DataFrame, schema: str, table: str,
                      batch_size: int = 500) -> int:
        """
        Universal fallback: insert rows in batches using parameterised statements.
        Used when the fast bulk method is unavailable or fails.
        Subclasses may override batch_size.
        """
        total = 0
        cols = list(df.columns)
        col_list = ", ".join(cols)

        for start in range(0, len(df), batch_size):
            chunk = df.iloc[start: start + batch_size]
            for _, row in chunk.iterrows():
                values = ", ".join(
                    "NULL" if (v is None or (isinstance(v, float) and pd.isna(v)))
                    else f"'{str(v).replace(chr(39), chr(39)*2)}'"
                    for v in row
                )
                sql = f"INSERT INTO {schema}.{table} ({col_list}) VALUES ({values})"
                self.execute(sql)
            total += len(chunk)

        return total

    # ------------------------------------------------------------------
    # Dialect helpers — override per database as needed
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        """Return the SQL expression for the current timestamp."""
        return "NOW()"

    def get_dialect_limit(self, n: int) -> str:
        """Return the SQL clause for limiting result rows."""
        return f"LIMIT {n}"
