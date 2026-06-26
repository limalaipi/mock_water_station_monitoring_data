# tests/integration/test_postgres.py
"""
Integration tests for PostgresAdapter.
Skipped automatically if POSTGRES_HOST env var is not set.

Run:
    pytest tests/integration/test_postgres.py -v
"""

import pytest
import pandas as pd
import uuid
from tests.conftest import get_adapter, TEST_SCHEMA, TEST_TABLE


@pytest.fixture(scope='module')
def adapter():
    a = get_adapter('postgresql')
    yield a
    a.close()


class TestPostgresAdapter:

    def test_connection(self, adapter):
        result = adapter.query("SELECT 1 AS one")
        assert result[0]['one'] == 1

    def test_ensure_table_exists_creates_table(self, adapter):
        adapter.execute(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{TEST_TABLE}")
        adapter.ensure_table_exists(TEST_SCHEMA, TEST_TABLE)
        assert adapter.table_exists(TEST_SCHEMA, TEST_TABLE)

    def test_ensure_table_exists_is_idempotent(self, adapter):
        # Calling again should not raise
        adapter.ensure_table_exists(TEST_SCHEMA, TEST_TABLE)

    def test_bulk_load_inserts_rows(self, adapter):
        df = pd.DataFrame([{
            'station_id':    str(uuid.uuid4()),
            'station_name':  'TEST_ST001',
            'station_url':   'https://test.example.com',
            'tambon_code':   '100101',
            'amphoe_code':   '1001',
            'province_code': '10',
            'country_code':  'TH',
            'officer_name':  'Test Officer',
            'officer_phone': '0812345678',
            'officer_email': 'test@example.com',
            'insert_date':   '2025-01-01 00:00:00',
        }])
        rows_loaded = adapter.bulk_load(df, TEST_SCHEMA, TEST_TABLE)
        assert rows_loaded == 1

    def test_row_count_after_bulk_load(self, adapter):
        result = adapter.query(
            f"SELECT COUNT(*) AS cnt FROM {TEST_SCHEMA}.{TEST_TABLE}"
        )
        assert result[0]['cnt'] >= 1
