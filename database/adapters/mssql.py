# database/adapters/mssql.py
"""
MSSQLAdapter
============
Bulk load strategy (try → fallback):
  1. fast_executemany via pyodbc (cursor.fast_executemany = True)  — fast
  2. _batch_insert() row-by-row                                    — always works

Note: BULK INSERT requires the CSV to be on the SQL Server filesystem —
      not reliable in all environments. fast_executemany is preferred.

Note: MSSQL uses GETDATE() for current timestamp.
      TOP n goes after SELECT keyword, not at query end.

Dependencies: pyodbc  (plus the appropriate ODBC driver installed on OS)
"""

from __future__ import annotations
import pandas as pd
from database.adapters.base import BaseAdapter


class MSSQLAdapter(BaseAdapter):

    db_type = "mssql"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "MSSQLAdapter":
        import pyodbc
        driver = self.config.get("driver_name", "ODBC Driver 17 for SQL Server")
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.config.get('host')},{self.config.get('port', 1433)};"
            f"DATABASE={self.config.get('database')};"
            f"UID={self.config.get('username')};"
            f"PWD={self.config.get('password')};"
            "TrustServerCertificate=yes;"
        )
        self.conn = pyodbc.connect(conn_str)
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        self.cur.fast_executemany = True
        print(f"[mssql] Connected to {self.config.get('host')}:{self.config.get('port', 1433)}")
        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[mssql] Connection closed")

    # ------------------------------------------------------------------
    # Query / execute
    # ------------------------------------------------------------------

    def query(self, sql: str, close: bool = False) -> list[dict]:
        self.cur.execute(sql)
        if self.cur.description is None:
            return []
        cols = [d[0] for d in self.cur.description]
        return [dict(zip(cols, row)) for row in self.cur.fetchall()]

    def execute(self, sql: str):
        self.cur.execute(sql)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        # MSSQL keeps '' as an empty string (unlike Oracle, which stores '' as
        # NULL). Convert empty-string placeholders to NULL up front so both the
        # fast path and the _batch_insert fallback land real NULLs — keeping
        # null_percent accurate.
        df = df.replace("", None)

        # 1. fast_executemany (cursor.fast_executemany = True set on connect)
        try:
            cols         = list(df.columns)
            col_sql      = ", ".join(f"[{c}]" for c in cols)
            placeholders = ", ".join(["?"] * len(cols))
            query  = f"INSERT INTO [{schema}].[{table}] ({col_sql}) VALUES ({placeholders})"
            values = [
                tuple(None if pd.isna(v) else v for v in row)
                for row in df.to_numpy()
            ]
            self.cur.executemany(query, values)
            self.conn.commit()
            print(f"[mssql] fast_executemany loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[mssql] fast_executemany failed ({e}) → falling back to _batch_insert")
            self.conn.rollback()

        # 2. _batch_insert fallback
        return self._batch_insert(df, schema, table)

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "GETDATE()"

    def get_dialect_limit(self, n: int) -> str:
        # MSSQL uses TOP n after SELECT — callers handle placement
        return f"TOP {n}"
