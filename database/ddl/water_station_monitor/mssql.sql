-- DDL: water_station_monitor — Microsoft SQL Server
-- Placeholders: {schema}, {table}
--
-- Table purpose : Water quality monitoring measurements
-- Source runner : water_station_monitor.py
--
-- ID strategy   : monitor_id = UUID (application-generated, no IDENTITY)

IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = '{schema}' AND table_name = '{table}'
)
BEGIN
    CREATE TABLE [{schema}].[{table}] (
        monitor_id          NVARCHAR(36)        NOT NULL,       -- UUID surrogate PK
        station_id          NVARCHAR(10),                       -- e.g. 'ST01' .. 'ST99'
        station_url         NVARCHAR(500),
        tambon_code         NVARCHAR(20),
        amphoe_code         NVARCHAR(20),
        province_code       NVARCHAR(20),
        country_code        NVARCHAR(10),
        monitor_name        NVARCHAR(255),
        monitor_phone       NVARCHAR(20),
        monitor_email       NVARCHAR(255),
        monitor_id_card     NVARCHAR(13),                       -- Thai national ID (13 digits)
        department_id       NVARCHAR(20),
        insert_date         DATETIME2,
        monitor_date        DATETIME2,
        wqi                 DECIMAL(10, 4),
        water_ph            DECIMAL(10, 4),
        water_do            DECIMAL(10, 4),
        water_bod           DECIMAL(10, 4),
        water_tds           DECIMAL(10, 4),
        water_temp          DECIMAL(10, 4),
        water_nh3_n         DECIMAL(10, 4),
        CONSTRAINT [pk_{table}] PRIMARY KEY (monitor_id)
    );
END;
