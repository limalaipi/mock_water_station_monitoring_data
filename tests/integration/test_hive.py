# tests/integration/test_hive.py
"""
Integration tests for HiveAdapter.
Skipped automatically if HIVE_HOST env var is not set.

Run:
    pytest tests/integration/test_hive.py -v
"""

import pytest
import pandas as pd
import uuid
from tests.conftest import get_adapter, TEST_SCHEMA, TEST_TABLE


@pytest.fixture(scope='module')
def adapter():
    a = get_adapter('hive')
    yield a
    a.close()


class TestHiveAdapter:

    def test_connection(self, adapter):
        # TODO: replace with db-appropriate smoke query
        result = adapter.query("SELECT 1")
        assert result is not None

    def test_ensure_table_exists_creates_table(self, adapter):
        adapter.ensure_table_exists(TEST_SCHEMA, TEST_TABLE)
        assert adapter.table_exists(TEST_SCHEMA, TEST_TABLE)

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
