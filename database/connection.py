# database/connection.py
import os
import sys
from dotenv import load_dotenv
from database.connector.postgres import PostGresInstance
from database.connector.impala import ImpalaInstance
from os import environ as env

project_path = os.getenv("PROJECT_PATH")
if project_path and project_path not in sys.path:
    sys.path.append(project_path)

load_dotenv(override=True)

postgres_config = {
    "host": env.get("POSTGRES_HOST", "localhost"),
    "database": env.get("POSTGRES_DB", "maholan_dev"),
    "user": env.get("POSTGRES_USER", "postgres"),
    "password": env.get("POSTGRES_PASS", "password"),
    "port": int(env.get("POSTGRES_PORT", 5432)),
}

impala_config = {
    "host": env.get("IMPALA_HOST"),
    "port": int(env.get("IMPALA_PORT")),
    "database": env.get("IMPALA_DB"),
    "user": env.get("IMPALA_USER")    
}

postgres = PostGresInstance(postgres_config)
impala = ImpalaInstance(impala_config)
