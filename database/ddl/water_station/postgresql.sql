-- DDL: water_station — PostgreSQL
-- Placeholders: {schema}, {table}
-- ID strategy: UUID (application-generated, no SERIAL/IDENTITY)
-- Columns derived from original water_station.py pipeline output

CREATE TABLE IF NOT EXISTS {schema}.{table} (
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
