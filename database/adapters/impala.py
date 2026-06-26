# database/adapters/impala.py
"""
ImpalaAdapter
=============
Bulk load strategy (try → fallback):
  1. Write Parquet to HDFS staging path + LOAD DATA + INVALIDATE METADATA
  2. _batch_insert() INSERT INTO ... VALUES

Note: Impala has no auto-increment. All IDs are application-generated (UUID).
Note: SHOW TABLES used for table existence check (no information_schema).

Dependencies: impyla, thrift, thrift-sasl
"""

from __future__ import annotations
import pandas as pd
from database.adapters.base import BaseAdapter


class ImpalaAdapter(BaseAdapter):

    db_type = "impala"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "ImpalaAdapter":
        from impala.dbapi import connect as impala_connect
        self.conn = impala_connect(
            host     = self.config.get("host"),
            port     = int(self.config.get("port", 21050)),
            database = self.config.get("database", "default"),
            user     = self.config.get("username"),
            use_ssl  = self.config.get("use_ssl", False),
        )
        self.cur = self.conn.cursor()
        print(f"[impala] Connected to {self.config.get('host')}:{self.config.get('port')}")
        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[impala] Connection closed")

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

    # ------------------------------------------------------------------
    # Table existence  (override — Impala uses SHOW TABLES)
    # ------------------------------------------------------------------

    def table_exists(self, schema: str, table: str) -> bool:
        try:
            self.cur.execute(f"SHOW TABLES IN `{schema}` LIKE '{table}'")
            rows = self.cur.fetchall()
            return len(rows) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str,
                  chunk_size: int = 100) -> int:
        """
        Multi-row INSERT: sends chunk_size rows per statement instead of 1.
        Reduces 1000 network round trips → ~10 round trips for 1000 rows.

        Impala does not support LOAD DATA LOCAL (requires HDFS path).
        """
        import numpy as np
        from datetime import datetime

        cols     = list(df.columns)
        col_list = ", ".join(cols)
        total    = 0

        def fmt(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "NULL"
            if isinstance(v, datetime):
                return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
            if isinstance(v, (int, float)):
                return str(v)
            return f"'{str(v).replace(chr(39), chr(39)*2)}'"

        for start in range(0, len(df), chunk_size):
            chunk  = df.iloc[start: start + chunk_size]
            rows   = [f"({', '.join(fmt(v) for v in row)})"
                      for _, row in chunk.iterrows()]
            sql    = f"INSERT INTO `{schema}`.`{table}` ({col_list}) VALUES {', '.join(rows)}"
            self.cur.execute(sql)
            total += len(chunk)

        print(f"[impala] multi-row INSERT loaded {total} rows → {schema}.{table}")
        return total

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "NOW()"
