-- DDL: water_station_monitor — Impala
-- Placeholders: {schema}, {table}
--
-- Table purpose : Water quality monitoring measurements
-- Source runner : water_station_monitor.py
--
-- Note: Impala does not enforce PRIMARY KEY or NOT NULL constraints.
--       Stored as Parquet for optimal query performance.
--       monitor_id is application-generated UUID.

CREATE TABLE IF NOT EXISTS {schema}.{table} (
    monitor_id          STRING,                     -- UUID surrogate PK (app-generated)
    station_id          STRING,                     -- e.g. 'ST01' .. 'ST99'
    station_url         STRING,
    tambon_code         STRING,
    amphoe_code         STRING,
    province_code       STRING,
    country_code        STRING,
    monitor_name        STRING,
    monitor_phone       STRING,
    monitor_email       STRING,
    monitor_id_card     STRING,                     -- Thai national ID (13 digits)
    department_id       STRING,
    insert_date         TIMESTAMP,
    monitor_date        TIMESTAMP,
    wqi                 DOUBLE,
    water_ph            DOUBLE,
    water_do            DOUBLE,
    water_bod           DOUBLE,
    water_tds           DOUBLE,
    water_temp          DOUBLE,
    water_nh3_n         DOUBLE
)
STORED AS PARQUET;
