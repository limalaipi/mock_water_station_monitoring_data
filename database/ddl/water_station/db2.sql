-- DDL: water_station — IBM Db2
-- Placeholders: {schema}, {table}
-- ID strategy: UUID (application-generated, no GENERATED ALWAYS AS IDENTITY)
-- Note: Db2 does not support IF NOT EXISTS in older versions.
-- The adapter's execute_ddl() catches SQLCODE -601 (object already exists).

CREATE TABLE {schema}.{table} (
    station_id          VARCHAR(36)     NOT NULL,
    station_name        VARCHAR(255),
    station_url         VARCHAR(500),
    tambon_code         VARCHAR(20),
    amphoe_code         VARCHAR(20),
    province_code       VARCHAR(20),
    country_code        VARCHAR(10),
    officer_name        VARCHAR(255),
    officer_phone       VARCHAR(50),
    officer_email       VARCHAR(255),
    insert_date         TIMESTAMP,
    CONSTRAINT pk_{table} PRIMARY KEY (station_id)
);
