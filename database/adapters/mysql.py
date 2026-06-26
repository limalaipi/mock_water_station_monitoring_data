# database/adapters/mysql.py
"""
MySQLAdapter
============
Bulk load strategy (try → fallback):
  1. LOAD DATA LOCAL INFILE (temp CSV)     — fastest
  2. executemany() batch insert            — fast parameterised
  3. _batch_insert() row-by-row            — always works

Note: LOAD DATA LOCAL INFILE may be disabled on some servers.
      allow_local_infile=True must be set on both client and server.

Dependencies: mysql-connector-python
"""

from __future__ import annotations
import os
import tempfile
import pandas as pd
from database.adapters.base import BaseAdapter


class MySQLAdapter(BaseAdapter):

    db_type = "mysql"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "MySQLAdapter":
        import mysql.connector
        self.conn = mysql.connector.connect(
            host             = self.config.get("host"),
            port             = int(self.config.get("port", 3306)),
            database         = self.config.get("database"),
            user             = self.config.get("username"),
            password         = self.config.get("password"),
            allow_local_infile = True,
        )
        self.cur = self.conn.cursor(dictionary=True)
        print(f"[mysql] Connected to {self.config.get('host')}:{self.config.get('port')}")
        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[mysql] Connection closed")

    # ------------------------------------------------------------------
    # Query / execute
    # ------------------------------------------------------------------

    def query(self, sql: str, close: bool = False) -> list[dict]:
        self.cur.execute(sql)
        return self.cur.fetchall() or []

    def execute(self, sql: str):
        self.cur.execute(sql)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        tmp_path = None

        # 1. LOAD DATA LOCAL INFILE
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding="utf-8"
            ) as f:
                df.to_csv(f, index=False, header=False, na_rep="")
                tmp_path = f.name

            # Escape backslashes in path for Windows
            safe_path = tmp_path.replace("\\", "/")
            cols = ", ".join(f"`{c}`" for c in df.columns)
            self.cur.execute(f"""
                LOAD DATA LOCAL INFILE '{safe_path}'
                INTO TABLE `{schema}`.`{table}`
                FIELDS TERMINATED BY ','
                OPTIONALLY ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                ({cols})
            """)
            self.conn.commit()
            print(f"[mysql] LOAD DATA loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[mysql] LOAD DATA failed ({e}) → trying executemany")
            self.conn.rollback()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # 2. executemany batch
        try:
            cols        = list(df.columns)
            col_sql     = ", ".join(f"`{c}`" for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            query  = f"INSERT INTO `{schema}`.`{table}` ({col_sql}) VALUES ({placeholders})"
            values = [
                tuple(None if pd.isna(v) else v for v in row)
                for row in df.to_numpy()
            ]
            self.cur.executemany(query, values)
            self.conn.commit()
            print(f"[mysql] executemany loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[mysql] executemany failed ({e}) → falling back to _batch_insert")
            self.conn.rollback()

        # 3. _batch_insert fallback
        return self._batch_insert(df, schema, table)

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "NOW()"
