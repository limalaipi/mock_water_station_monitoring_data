# tests/unit/test_state.py
"""
Unit tests for pipeline/state.py — state save/load round-trip.
No DB connection needed.
"""

import json
import pytest
from pathlib import Path
from pipeline.state import PipelineStateRepository


@pytest.fixture
def tmp_state_file(tmp_path):
    return str(tmp_path / 'test_state.json')


class TestPipelineStateRepository:

    def test_load_returns_defaults_when_no_file(self, tmp_state_file):
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        assert state['current_day'] == 0
        assert state['cumulative_total_rows'] == 0

    def test_save_and_reload(self, tmp_state_file):
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        state['current_day'] = 5
        state['cumulative_total_rows'] = 500
        repo.save(state)
        reloaded = repo.load()
        assert reloaded['current_day'] == 5
        assert reloaded['cumulative_total_rows'] == 500

    def test_reset_clears_state(self, tmp_state_file):
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        state['current_day'] = 5
        repo.save(state)
        fresh = repo.reset()
        assert fresh['current_day'] == 0

    def test_missing_keys_filled_on_load(self, tmp_state_file):
        # Write a state file missing some keys
        Path(tmp_state_file).write_text(
            json.dumps({'current_day': 3}), encoding='utf-8'
        )
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        # Missing keys should be filled with defaults
        assert 'cumulative_total_rows' in state
        assert 'quality_history' in state

    def test_corrupt_file_returns_defaults(self, tmp_state_file):
        Path(tmp_state_file).write_text('NOT VALID JSON', encoding='utf-8')
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        assert state['current_day'] == 0

    def test_get_summary(self, tmp_state_file):
        repo = PipelineStateRepository(tmp_state_file)
        state = repo.load()
        state['current_day'] = 2
        state['cumulative_quality'] = 87.5
        summary = repo.get_summary(state)
        assert summary['current_day'] == 2
        assert summary['cumulative_quality'] == 87.5
