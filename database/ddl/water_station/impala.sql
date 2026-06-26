-- DDL: water_station — Impala
-- Placeholders: {schema}, {table}
-- Note: Impala does not enforce PRIMARY KEY or NOT NULL constraints.
-- Stored as Parquet for optimal query performance.

CREATE TABLE IF NOT EXISTS {schema}.{table} (
    station_id          STRING,
    station_name        STRING,
    station_url         STRING,
    tambon_code         STRING,
    amphoe_code         STRING,
    province_code       STRING,
    country_code        STRING,
    officer_name        STRING,
    officer_phone       STRING,
    officer_email       STRING,
    insert_date         TIMESTAMP
)
STORED AS PARQUET;
