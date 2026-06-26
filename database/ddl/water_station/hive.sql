-- DDL: water_station — Hive
-- Placeholders: {schema}, {table}
-- Note: Hive does not enforce PRIMARY KEY or NOT NULL constraints.
-- ORC format with ACID support for transactional operations.

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
STORED AS ORC
TBLPROPERTIES (
    'transactional'='true',
    'transactional_properties'='default'   -- full ACID: enables INSERT / UPDATE / DELETE
);
