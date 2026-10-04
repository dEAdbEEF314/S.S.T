import pytest
from pathlib import Path
import sqlite3
from sst.db import DatabaseManager
from sst.llm.organizer import LLMOrganizer
from sst.processor import AlbumExecutionProfile

def test_db_wal_mode_and_busy_timeout(tmp_path):
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_file)
    with db._connect() as conn:
        cur = conn.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"
        cur = conn.execute("PRAGMA busy_timeout;")
        timeout = cur.fetchone()[0]
        assert timeout == 5000

def test_adaptive_chunk_size_respects_profile():
    organizer = LLMOrganizer(
        base_url="http://localhost:11434",
        api_key="mock_key",
        llm_cloud_max_tokens=8192,
        chunk_adaptive=True,
        chunk_size_virtual=30,
        chunk_output_tokens_per_track=180,
    )
    
    # Small profile (prefer_one_shot = False) -> should not exceed base_chunk_size
    profile_small = AlbumExecutionProfile(
        tier_name="Small",
        track_count_min=1,
        track_count_max=50,
        num_ctx_cap=8192,
        phase2_parallel_workers=2,
        force_coherence=False,
        prefer_one_shot=False
    )
    chunk_size = organizer._adaptive_chunk_size(30, execution_profile=profile_small)
    assert chunk_size == 30

    # Medium profile (prefer_one_shot = True) -> should be capped at safe maximum (<= 50)
    profile_medium = AlbumExecutionProfile(
        tier_name="Medium",
        track_count_min=51,
        track_count_max=100,
        num_ctx_cap=16384,
        phase2_parallel_workers=1,
        force_coherence=False,
        prefer_one_shot=True
    )
    chunk_size_med = organizer._adaptive_chunk_size(30, execution_profile=profile_medium)
    assert chunk_size_med <= 50
