-- DDL: water_station — Oracle Database
-- Placeholders: {schema}, {table}
-- ID strategy: UUID (application-generated, no SEQUENCE/IDENTITY)
-- Note: Oracle does not support IF NOT EXISTS before 23c.
-- The adapter's execute_ddl() catches ORA-00955 (name already used by existing object).

CREATE TABLE {schema}.{table} (
    station_id          VARCHAR2(36)    NOT NULL,
    station_name        VARCHAR2(255),
    station_url         VARCHAR2(500),
    tambon_code         VARCHAR2(20),
    amphoe_code         VARCHAR2(20),
    province_code       VARCHAR2(20),
    country_code        VARCHAR2(10),
    officer_name        VARCHAR2(255),
    officer_phone       VARCHAR2(50),
    officer_email       VARCHAR2(255),
    insert_date         TIMESTAMP,
    CONSTRAINT pk_{table} PRIMARY KEY (station_id)
)
