-- mysql (MYSQL_DB=demo_dg_db)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM demo_dg_db.water_station_monitor;

-- postgresql (POSTGRES_DB=postgres, schema public)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM public.water_station_monitor;

-- impala (IMPALA_SCHEMA=demo_dg_db)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM demo_dg_db.water_station_monitor;

-- hive (HIVE_DB=demo_dg_db) — Hive ไม่มี NULLIF ใช้ CASE แทน
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / (CASE WHEN COUNT(*) = 0 THEN NULL ELSE COUNT(*) END), 2), 0) AS pct_in_range
FROM demo_dg_db.water_station_monitor;

-- oracle (ORACLE_SCHEMA=sa)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM sa.water_station_monitor;

-- mssql (MSSQL_DB=demo_dg_db, MSSQL_SCHEMA=dbo)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM demo_dg_db.dbo.water_station_monitor;

-- db2 (DB2_SCHEMA=DB2INST1)
SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN (water_ph BETWEEN 1 AND 14) OR water_ph IN (-9999, 9999) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) AS pct_in_range
FROM DB2INST1.water_station_monitor;
