-- DDL: water_station — Microsoft SQL Server
-- Placeholders: {schema}, {table}
-- ID strategy: UUID (application-generated, no IDENTITY)

IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = '{schema}' AND table_name = '{table}'
)
BEGIN
    CREATE TABLE [{schema}].[{table}] (
        station_id          NVARCHAR(36)    NOT NULL,
        station_name        NVARCHAR(255),
        station_url         NVARCHAR(500),
        tambon_code         NVARCHAR(20),
        amphoe_code         NVARCHAR(20),
        province_code       NVARCHAR(20),
        country_code        NVARCHAR(10),
        officer_name        NVARCHAR(255),
        officer_phone       NVARCHAR(50),
        officer_email       NVARCHAR(255),
        insert_date         DATETIME2,
        CONSTRAINT [pk_{table}] PRIMARY KEY (station_id)
    );
END;
