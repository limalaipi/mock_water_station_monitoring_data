-- DDL: water_station_monitor — PostgreSQL
-- Placeholders: {schema}, {table}
--
-- Table purpose : Water quality monitoring measurements
-- Source runner : water_station_monitor.py
--
-- ID strategy   : monitor_id = UUID (application-generated surrogate PK)
--                 station_id is ST01-ST99 format — NOT unique per row,
--                 so it cannot be used as a primary key.

CREATE TABLE IF NOT EXISTS {schema}.{table} (
    monitor_id          VARCHAR(36)         NOT NULL,           -- UUID surrogate PK (app-generated)
    station_id          VARCHAR(10),                            -- e.g. 'ST01' .. 'ST99'
    station_url         VARCHAR(500),
    tambon_code         VARCHAR(20),
    amphoe_code         VARCHAR(20),
    province_code       VARCHAR(20),
    country_code        VARCHAR(10),
    monitor_name        VARCHAR(255),
    monitor_phone       VARCHAR(20),
    monitor_email       VARCHAR(255),
    monitor_id_card     VARCHAR(13),                            -- Thai national ID (13 digits)
    department_id       VARCHAR(20),
    insert_date         TIMESTAMP,
    monitor_date        TIMESTAMP,
    wqi                 NUMERIC(10, 4),
    water_ph            NUMERIC(10, 4),
    water_do            NUMERIC(10, 4),
    water_bod           NUMERIC(10, 4),
    water_tds           NUMERIC(10, 4),
    water_temp          NUMERIC(10, 4),
    water_nh3_n         NUMERIC(10, 4),
    CONSTRAINT pk_{table} PRIMARY KEY (monitor_id)
);
