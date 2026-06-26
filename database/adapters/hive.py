# database/adapters/hive.py
"""
HiveAdapter
===========
Bulk load strategy (try → fallback):
  1. WebHDFS upload → LOAD DATA INPATH (fastest)
     - Writes CSV to HDFS via WebHDFS REST API
     - Executes: LOAD DATA INPATH 'hdfs:///staging/file.csv' INTO TABLE
     - Requires: WEBHDFS_HOST, WEBHDFS_PORT, WEBHDFS_USER in .env
  2. Multi-row INSERT (fallback — slower, no HDFS needed)
     - Sends chunk_size rows per INSERT statement
     - Slower because Hive creates a MapReduce/Tez job per INSERT

Note: LOAD DATA LOCAL INPATH does not work when connecting from Windows
      because Hive cannot resolve Windows file paths (C:\\...).

Dependencies: pyhive[hive], thrift, thrift-sasl (or pure-sasl), requests
"""

from __future__ import annotations
import io
import os
import uuid
import pandas as pd
from database.adapters.base import BaseAdapter


# Session properties required for ACID tables (INSERT / UPDATE / DELETE).
# Applied once per connection so callers don't have to SET them manually.
_TXN_SESSION_PROPS = [
    "SET hive.support.concurrency=true",
    "SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager",
    "SET hive.exec.dynamic.partition.mode=nonstrict",
]


class HiveAdapter(BaseAdapter):

    db_type = "hive"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "HiveAdapter":
        from pyhive import hive
        auth = self.config.get("auth", "NONE")
        connect_kwargs = dict(
            host     = self.config.get("host"),
            port     = int(self.config.get("port", 10000)),
            database = self.config.get("database", "default"),
            username = self.config.get("username"),
            auth     = auth,
        )
        if auth.upper() == "KERBEROS":
            connect_kwargs["kerberos_service_name"] = self.config.get(
                "kerberos_service_name", "hive"
            )
        self.conn = hive.connect(**connect_kwargs)
        self.cur  = self.conn.cursor()
        print(f"[hive] Connected to {self.config.get('host')}:{self.config.get('port')}")

        # --- Enable ACID transactions for this session ---
        # Without these, DELETE / UPDATE on transactional tables fail with
        # "transaction manager does not support these operations".
        for prop in _TXN_SESSION_PROPS:
            self.cur.execute(prop)

        # --- Optional execution-engine override ---
        # Hive-on-MapReduce (mr) is very slow: every query stage spawns a
        # separate MR job (~15-20s startup each). On CDH set this to 'spark'
        # for a large speedup. Leave unset to keep the cluster default.
        #   export HIVE_EXECUTION_ENGINE=spark   (or set execution_engine in config)
        engine = self.config.get("execution_engine") or os.getenv("HIVE_EXECUTION_ENGINE")
        if engine:
            self.cur.execute(f"SET hive.execution.engine={engine}")
            print(f"[hive] hive.execution.engine set to '{engine}'")

        return self

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print("[hive] Connection closed")

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

    def commit(self):
        """
        Flush/commit any pending work before close.

        HiveServer2 auto-commits each DML statement (and pyhive's execute()
        blocks until the statement finishes), so this is mostly a safety net:
        it guarantees we don't close the session while work is still in flight,
        which is what leaves ACID locks behind for the next connection.
        """
        if self.conn is not None and hasattr(self.conn, "commit"):
            try:
                self.conn.commit()
            except Exception:
                pass  # HiveServer2 commit is a no-op on some drivers

    # ------------------------------------------------------------------
    # Table existence (override — Hive uses SHOW TABLES)
    # ------------------------------------------------------------------

    def table_exists(self, schema: str, table: str) -> bool:
        try:
            self.cur.execute(f"SHOW TABLES IN `{schema}` LIKE '{table}'")
            rows = self.cur.fetchall()
            return len(rows) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # DDL execution (override — set Hive session properties first)
    # ------------------------------------------------------------------

    def execute_ddl(self, sql: str):
        self.cur.execute("SET hive.exec.dynamic.partition.mode=nonstrict")
        self.cur.execute("SET hive.support.concurrency=true")
        self.cur.execute("SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager")
        # pyhive does not accept trailing semicolons
        self.cur.execute(sql.rstrip().rstrip(";"))

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def bulk_load(self, df: pd.DataFrame, schema: str, table: str,
                  chunk_size: int = 1000) -> int:
        """
        Strategy:
          1. WebHDFS upload → LOAD DATA INPATH (fast)
          2. Multi-row INSERT fallback (slower)
        """
        webhdfs_host = self.config.get("webhdfs_host", "")
        if webhdfs_host:
            try:
                return self._webhdfs_load(df, schema, table)
            except Exception as e:
                print(f"[hive] WebHDFS failed ({e}) → falling back to multi-row INSERT")

        return self._multirow_insert(df, schema, table, chunk_size)

    # ------------------------------------------------------------------
    # WebHDFS upload → LOAD DATA INPATH
    # ------------------------------------------------------------------

    def _webhdfs_load(self, df: pd.DataFrame, schema: str, table: str) -> int:
        """
        1. Convert DataFrame to CSV in memory
        2. Upload to HDFS via WebHDFS REST API
        3. LOAD DATA INPATH into a temporary non-transactional staging table
        4. INSERT ... SELECT from staging into the (ACID) target table
        5. Drop the staging table

        Why the staging hop?
            Hive forbids `LOAD DATA` directly into full-ACID (transactional)
            tables. So we land the file in a plain TEXTFILE table first, then
            do a single INSERT...SELECT — one job, still fast, and the target
            stays transactional so DELETE / UPDATE keep working.
        """
        import requests

        host     = self.config.get("webhdfs_host")
        port     = int(self.config.get("webhdfs_port", 9870))
        user     = self.config.get("webhdfs_user", self.config.get("username", ""))
        staging  = self.config.get("webhdfs_staging", "/tmp/water_station_staging")
        filename = f"{schema}_{table}_{uuid.uuid4().hex}.csv"
        hdfs_path = f"{staging}/{filename}"
        webhdfs_base = f"http://{host}:{port}/webhdfs/v1"

        # 1. Convert DataFrame to CSV bytes (no header, NULL as empty string)
        buf = io.StringIO()
        df.to_csv(buf, index=False, header=False, na_rep="")
        csv_bytes = buf.getvalue().encode("utf-8")

        # 2. Ensure staging directory exists
        mkdir_url = f"{webhdfs_base}{staging}"
        requests.put(mkdir_url, params={
            "op": "MKDIRS", "user.name": user
        })

        # 3. Upload CSV to HDFS (WebHDFS two-step: namenode redirect → datanode write)
        upload_url = f"{webhdfs_base}{hdfs_path}"
        resp = requests.put(
            upload_url,
            params={"op": "CREATE", "user.name": user, "overwrite": "true"},
            data=csv_bytes,
            allow_redirects=True,
        )
        resp.raise_for_status()
        print(f"[hive] Uploaded {len(df)} rows to HDFS: {hdfs_path}")

        # 4. LOAD into a temporary non-transactional staging table, then
        #    INSERT...SELECT into the ACID target (LOAD DATA can't target ACID).
        cols        = list(df.columns)
        col_list    = ", ".join(f"`{c}`" for c in cols)
        staging_cols = ",\n    ".join(f"`{c}` STRING" for c in cols)
        stg_table   = f"{table}_stg_{uuid.uuid4().hex[:8]}"

        self.cur.execute(
            f"CREATE TABLE `{schema}`.`{stg_table}` (\n    {staging_cols}\n) "
            f"ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' "
            f"STORED AS TEXTFILE "
            f"TBLPROPERTIES ('transactional'='false')"
        )
        try:
            self.cur.execute(
                f"LOAD DATA INPATH '{hdfs_path}' INTO TABLE `{schema}`.`{stg_table}`"
            )
            # Implicit casts (STRING -> TIMESTAMP / DOUBLE) happen against the
            # target column types during INSERT...SELECT.
            self.cur.execute(
                f"INSERT INTO TABLE `{schema}`.`{table}` ({col_list}) "
                f"SELECT {col_list} FROM `{schema}`.`{stg_table}`"
            )
        finally:
            self.cur.execute(f"DROP TABLE IF EXISTS `{schema}`.`{stg_table}`")

        print(f"[hive] staged load + INSERT...SELECT: {len(df)} rows → {schema}.{table}")
        return len(df)

    # ------------------------------------------------------------------
    # Multi-row INSERT fallback
    # ------------------------------------------------------------------

    def _multirow_insert(self, df: pd.DataFrame, schema: str, table: str,
                         chunk_size: int = 1000) -> int:
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
            chunk = df.iloc[start: start + chunk_size]
            rows  = [f"({', '.join(fmt(v) for v in row)})"
                     for _, row in chunk.iterrows()]
            sql   = (f"INSERT INTO `{schema}`.`{table}` ({col_list}) "
                     f"VALUES {', '.join(rows)}")
            self.cur.execute(sql)
            total += len(chunk)

        print(f"[hive] multi-row INSERT loaded {total} rows → {schema}.{table}")
        return total

    # ------------------------------------------------------------------
    # Dialect helpers
    # ------------------------------------------------------------------

    def get_dialect_now(self) -> str:
        return "CURRENT_TIMESTAMP"
