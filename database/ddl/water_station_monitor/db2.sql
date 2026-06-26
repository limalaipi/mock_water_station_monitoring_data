-- DDL: water_station_monitor — IBM Db2
-- Placeholders: {schema}, {table}
--
-- Table purpose : Water quality monitoring measurements
-- Source runner : water_station_monitor.py
--
-- ID strategy   : monitor_id = UUID (application-generated, no GENERATED ALWAYS AS IDENTITY)
-- Note          : Db2 may not support IF NOT EXISTS in older versions.
--                 The adapter's execute_ddl() catches SQLCODE -601.

CREATE TABLE {schema}.{table} (
    monitor_id          VARCHAR(36)         NOT NULL,           -- UUID surrogate PK
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
    wqi                 DECIMAL(10, 4),
    water_ph            DECIMAL(10, 4),
    water_do            DECIMAL(10, 4),
    water_bod           DECIMAL(10, 4),
    water_tds           DECIMAL(10, 4),
    water_temp          DECIMAL(10, 4),
    water_nh3_n         DECIMAL(10, 4),
    CONSTRAINT pk_{table} PRIMARY KEY (monitor_id)
);
