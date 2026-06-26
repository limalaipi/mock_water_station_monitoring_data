from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "aye",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

JOB_DIR = "/opt/airflow/jobs/water_station_monitoring"
DATABASES = ["mysql", "oracle", "mssql", "db2"]

with DAG(
    dag_id="dataquality_water_station_monitoring",
    description="ETL pipeline for data quality — runs every 1 hour",
    start_date=datetime(2024, 1, 1),
    schedule_interval="50 * * * *",
    catchup=False,
    default_args=default_args,
    tags=["etl", "data_quality", "water_station_monitoring"],
) as dag:

    for db in DATABASES:
        BashOperator(
            task_id=f"{db}_etl",
            # Invoke via `bash run.sh` (not `./run.sh`) so it works even when
            # the deployed copy lost its execute bit — avoids "Permission denied".
            bash_command=(
                f"cd {JOB_DIR} && ENV=airflow bash run.sh run-all {db}"
            ),
        )
