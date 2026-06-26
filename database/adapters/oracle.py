# database/adapters/oracle.py
"""
OracleAdapter
=============
Bulk load strategy (try → fallback):
  1. executemany() with large arraysize    — efficient in-process batch
  2. _batch_insert() row-by-row            — always works

Note: Oracle SQL*Loader is a CLI tool — not used here to avoid
      external process dependency. executemany() with arraysize is
      the recommended in-process bulk approach for oracledb.

Note: execute_ddl() silently ignores ORA-00955
      (object already exists) so ensure_table_exists() is safe to
      call repeatedly.

Dependencies: oracledb  (pip install oracledb)
"""

from __future__ import annotations
import pandas as pd
from database.adapters.base import BaseAdapter


class OracleAdapter(BaseAdapter):

    db_type = "oracle"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def table_exists(self, schema: str, table: str) -> bool:
        """Override: Oracle uses ALL_TABLES, not information_schema."""
        sql = f"""
            SELECT COUNT(*) as cnt FROM ALL_TABLES
            WHERE UPPER(OWNER) = UPPER('{schema}')
              AND UPPER(TABLE_NAME) = UPPER('{table}')
        """
        try:
            rows = self.query(sql)
            return rows[0]['cnt'] > 0
        except Exception:
            return False

    def connect(self) -> "OracleAdapter":
        # oracledb pulls in `cryptography`, which warns that Python 3.8 is
        # deprecated. We intentionally pin 3.8 (CPU lacks x86-64-v2 for newer
        # numpy), so silence just that one message — not warnings in general.
        import warnings
        warnings.filterwarnings(
            "ignore",
            message=r".*Python 3\.8 is no longer supported.*",
        )
        import oracledb
        dsn = oracledb.makedsn(
            host         = self.config.get("host"),
            port         = int(self.config.get("port", 1521)),
            service_name = self.config.get("service_name"),
        )
        self.conn = oracledb.connect(
            user     = self.config.get("username"),
            password = self.config.get("password"),
            dsn      = dsn,
        )
        self.cur = self.conn.cursor()
        print(f"[oracle] Connected to {self.config.get('host')}:{self.config.get('port')}")
        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[oracle] Connection closed")

    # ------------------------------------------------------------------
    # Query / execute
    # ------------------------------------------------------------------

    def query(self, sql: str, close: bool = False) -> list[dict]:
        self.cur.execute(sql)
        if self.cur.description is None:
            return []
        cols = [d[0].lower() for d in self.cur.description]
        return [dict(zip(cols, row)) for row in self.cur.fetchall()]

    def execute(self, sql: str):
        self.cur.execute(sql)
        self.conn.commit()

    # ------------------------------------------------------------------
    # DDL execution  (override — silently ignore ORA-00955)
    # ------------------------------------------------------------------

    def execute_ddl(self, sql: str):
        import oracledb
        try:
            self.cur.execute(sql)
            self.conn.commit()
        except oracledb.DatabaseError as exc:
            error, = exc.args
            if error.code == 955:  # ORA-00955: name already used by an existing object
                print(f"[oracle] Table already exists — skipping CREATE")
            else:
                raise

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        # 1. executemany with large arraysize
        try:
            cols         = list(df.columns)
            col_sql      = ", ".join(cols)
            placeholders = ", ".join([f":{i+1}" for i in range(len(cols))])
            query  = f"INSERT INTO {schema}.{table} ({col_sql}) VALUES ({placeholders})"
            values = [
                tuple(self._to_oracle(v) for v in row)
                for row in df.to_numpy()
            ]
            self.cur.arraysize = 1000
            self.cur.executemany(query, values)
            self.conn.commit()
            print(f"[oracle] executemany loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[oracle] executemany failed ({e}) → falling back to _batch_insert")
            self.conn.rollback()

        # 2. _batch_insert fallback (Oracle-safe)
        return self._oracle_batch_insert(df, schema, table)

    def _to_oracle(self, v):
        """Convert Python value to Oracle-compatible type for executemany."""
        import numpy as np
        from datetime import datetime
        if v is None:
            return None
        if isinstance(v, float) and np.isnan(v):
            return None
        if isinstance(v, (int, float, str, bool)):
            return v
        if isinstance(v, datetime):
            return v          # oracledb handles datetime natively
        return str(v)

    def _oracle_batch_insert(self, df: pd.DataFrame, schema: str, table: str,
                              batch_size: int = 200) -> int:
        """
        Oracle-specific batch insert.
        Formats datetime as TO_TIMESTAMP() — Oracle cannot implicitly cast
        ISO datetime strings to TIMESTAMP via string literals.
        """
        import numpy as np
        from datetime import datetime
        total = 0
        cols  = list(df.columns)
        col_list = ", ".join(cols)

        for start in range(0, len(df), batch_size):
            chunk = df.iloc[start: start + batch_size]
            for _, row in chunk.iterrows():
                values = []
                for v in row:
                    if v is None or (isinstance(v, float) and np.isnan(v)):
                        values.append("NULL")
                    elif isinstance(v, datetime):
                        ts = v.strftime('%Y-%m-%d %H:%M:%S')
                        values.append(f"TO_TIMESTAMP('{ts}', 'YYYY-MM-DD HH24:MI:SS')")
                    elif isinstance(v, (int, float)):
                        values.append(str(v))
                    else:
                        safe = str(v).replace("'", "''")
                        values.append(f"'{safe}'")
                sql = f"INSERT INTO {schema}.{table} ({col_list}) VALUES ({', '.join(values)})"
                self.execute(sql)
            total += len(chunk)
        return total

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "SYSDATE"

    def get_dialect_limit(self, n: int) -> str:
        return f"FETCH FIRST {n} ROWS ONLY"
