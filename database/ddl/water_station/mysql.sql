-- DDL: water_station — MySQL / MariaDB
-- Placeholders: {schema}, {table}
-- ID strategy: UUID (application-generated, no AUTO_INCREMENT)

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
    insert_date         DATETIME,
    PRIMARY KEY (station_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
