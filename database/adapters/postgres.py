# database/adapters/postgres.py
"""
PostgresAdapter
===============
Bulk load strategy (try → fallback):
  1. COPY FROM STDIN via psycopg2.copy_expert()  — fastest
  2. execute_values() batch insert                — fast parameterised
  3. _batch_insert()  row-by-row                 — always works

Dependencies: psycopg2-binary
"""

from __future__ import annotations
import io
import pandas as pd
from database.adapters.base import BaseAdapter


class PostgresAdapter(BaseAdapter):

    db_type = "postgresql"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "PostgresAdapter":
        import psycopg2
        self.conn = psycopg2.connect(
            host     = self.config.get("host"),
            port     = int(self.config.get("port", 5432)),
            dbname   = self.config.get("database"),
            user     = self.config.get("username"),
            password = self.config.get("password"),
        )
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        print(f"[postgresql] Connected to {self.config.get('host')}:{self.config.get('port')}")
        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[postgresql] Connection closed")

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
        # 1. COPY FROM STDIN
        try:
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, na_rep="")
            buf.seek(0)
            cols = ", ".join(df.columns)
            self.cur.copy_expert(
                f"COPY {schema}.{table} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '')",
                buf,
            )
            self.conn.commit()
            print(f"[postgresql] COPY loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[postgresql] COPY failed ({e}) → trying execute_values")
            self.conn.rollback()

        # 2. execute_values batch
        try:
            from psycopg2.extras import execute_values
            cols  = list(df.columns)
            col_sql = ", ".join(cols)
            values  = [
                tuple(None if pd.isna(v) else v for v in row)
                for row in df.to_numpy()
            ]
            execute_values(
                self.cur,
                f"INSERT INTO {schema}.{table} ({col_sql}) VALUES %s",
                values,
                page_size=500,
            )
            self.conn.commit()
            print(f"[postgresql] execute_values loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[postgresql] execute_values failed ({e}) → falling back to _batch_insert")
            self.conn.rollback()

        # 3. _batch_insert fallback
        return self._batch_insert(df, schema, table)

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "NOW()"

    def get_dialect_limit(self, n: int) -> str:
        return f"LIMIT {n}"
