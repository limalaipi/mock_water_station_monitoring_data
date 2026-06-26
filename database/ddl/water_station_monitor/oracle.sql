-- DDL: water_station_monitor — Oracle Database
-- Placeholders: {schema}, {table}
--
-- Table purpose : Water quality monitoring measurements
-- Source runner : water_station_monitor.py
--
-- ID strategy   : monitor_id = UUID (application-generated, no SEQUENCE/IDENTITY)
-- Note          : Oracle does not support IF NOT EXISTS before 23c.
--                 The adapter's execute_ddl() catches ORA-00955.

CREATE TABLE {schema}.{table} (
    monitor_id          VARCHAR2(36)        NOT NULL,           -- UUID surrogate PK
    station_id          VARCHAR2(10),                           -- e.g. 'ST01' .. 'ST99'
    station_url         VARCHAR2(500),
    tambon_code         VARCHAR2(20),
    amphoe_code         VARCHAR2(20),
    province_code       VARCHAR2(20),
    country_code        VARCHAR2(10),
    monitor_name        VARCHAR2(255),
    monitor_phone       VARCHAR2(20),
    monitor_email       VARCHAR2(255),
    monitor_id_card     VARCHAR2(13),                           -- Thai national ID (13 digits)
    department_id       VARCHAR2(20),
    insert_date         TIMESTAMP,
    monitor_date        TIMESTAMP,
    wqi                 NUMBER(10, 4),
    water_ph            NUMBER(10, 4),
    water_do            NUMBER(10, 4),
    water_bod           NUMBER(10, 4),
    water_tds           NUMBER(10, 4),
    water_temp          NUMBER(10, 4),
    water_nh3_n         NUMBER(10, 4),
    CONSTRAINT pk_{table} PRIMARY KEY (monitor_id)
)
