# database/adapters/db2.py
"""
Db2Adapter
==========
Uses jaydebeapi + JPype1 to connect via JDBC — no IBM C CLI Driver needed.

Bulk load strategy (try → fallback):
  1. executemany() via JDBC batch       — fast
  2. _batch_insert() row-by-row         — always works

Requirements:
  - Java 8+ installed (java -version)
  - db2jcc4.jar in ./drivers/ (download once from Maven Central)
  - jaydebeapi, jpype1 (installed via uv sync)

.env:
  DB2_HOST, DB2_PORT, DB2_DB, DB2_USER, DB2_PASS, DB2_SCHEMA
  DB2_JDBC_JAR=./drivers/db2jcc4.jar
"""

from __future__ import annotations
import os
import pandas as pd
from database.adapters.base import BaseAdapter


class Db2Adapter(BaseAdapter):

    db_type = "db2"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "Db2Adapter":
        import jaydebeapi

        host     = self.config.get("host")
        port     = self.config.get("port", 50000)
        database = self.config.get("database")
        user     = self.config.get("username")
        password = self.config.get("password")
        jar_path = self.config.get("jdbc_jar", "./drivers/db2jcc4.jar")

        # Resolve relative path from project root
        if not os.path.isabs(jar_path):
            jar_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                jar_path
            )

        if not os.path.exists(jar_path):
            raise FileNotFoundError(
                f"Db2 JDBC driver not found at {jar_path}\n"
                f"Download with:\n"
                f"  curl -L https://repo1.maven.org/maven2/com/ibm/db2/jcc/"
                f"db2jcc/db2jcc4/db2jcc4.jar -o drivers/db2jcc4.jar"
            )

        jdbc_url = f"jdbc:db2://{host}:{port}/{database}"

        self.conn = jaydebeapi.connect(
            "com.ibm.db2.jcc.DB2Driver",
            jdbc_url,
            [user, password],
            jar_path,
        )
        self.conn.jconn.setAutoCommit(False)
        self.cur = self.conn.cursor()
        print(f"[db2] Connected to {host}:{port}/{database} via JDBC")
        return self

    def close(self):
        if self.cur:
            try:
                self.cur.close()
            except Exception:
                pass
        if self.conn:
            try:
                self.conn.rollback()   # rollback any pending transaction before close
            except Exception:
                pass
            try:
                self.conn.close()
            except Exception:
                pass
        print("[db2] Connection closed")

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
    # DDL execution (override — ignore -601: object already exists)
    # ------------------------------------------------------------------

    def table_exists(self, schema: str, table: str) -> bool:
        """Override: Db2 uses SYSCAT.TABLES instead of INFORMATION_SCHEMA."""
        sql = f"""
            SELECT COUNT(*) FROM SYSCAT.TABLES
            WHERE UPPER(TABSCHEMA) = UPPER('{schema}')
              AND UPPER(TABNAME)   = UPPER('{table}')
        """
        try:
            rows = self.query(sql)
            return rows[0][list(rows[0].keys())[0]] > 0
        except Exception:
            return False

    def execute_ddl(self, sql: str):
        try:
            self.cur.execute(sql)
            self.conn.commit()
        except Exception as exc:
            if "-601" in str(exc):
                print(f"[db2] Table already exists — skipping CREATE")
            else:
                raise

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        import numpy as np
        from datetime import datetime

        def to_jdbc(v):
            """Convert Python value to JDBC-compatible type."""
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            if isinstance(v, datetime):
                return v.strftime('%Y-%m-%d %H:%M:%S')  # string for Db2 TIMESTAMP
            if isinstance(v, (int, float, str, bool)):
                return v
            return str(v)

        try:
            cols         = list(df.columns)
            col_sql      = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            query  = f"INSERT INTO {schema}.{table} ({col_sql}) VALUES ({placeholders})"
            values = [
                tuple(to_jdbc(v) for v in row)
                for row in df.to_numpy()
            ]
            self.cur.executemany(query, values)
            self.conn.commit()
            print(f"[db2] executemany loaded {len(df)} rows → {schema}.{table}")
            return len(df)
        except Exception as e:
            print(f"[db2] executemany failed ({e}) → falling back to _batch_insert")
            self.conn.rollback()

        return self._batch_insert(df, schema, table)

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def truncate_table(self, schema: str, table: str):
        """
        Override: Db2 TRUNCATE TABLE requires IMMEDIATE and must run
        outside a transaction (autocommit=True).
        """
        self.conn.jconn.setAutoCommit(True)
        try:
            self.cur.execute(f"TRUNCATE TABLE {schema}.{table} IMMEDIATE")
        finally:
            self.conn.jconn.setAutoCommit(False)

    def get_dialect_now(self) -> str:
        return "CURRENT TIMESTAMP"

    def get_dialect_limit(self, n: int) -> str:
        return f"FETCH FIRST {n} ROWS ONLY"
