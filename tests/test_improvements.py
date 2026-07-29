import pytest
from pathlib import Path
from unittest.mock import MagicMock
from sst.validator import ResultValidator
from sst.builder import MetadataBuilder
from sst.processor_tracks import copy_with_retry
from sst.models import SteamMetadata

def test_validator_relaxed_thresholds():
    # id_conf = 90, quality = 85 should pass validation
    tracks = [{"tags": {"title": "Test Title", "track_number": "1", "disc_number": "1"}}]
    llm_log = {
        "phase1_res": {
            "identity_confidence": 90,
            "integrity_quality": 85,
            "semantic_label": "Archive",
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 100, "review": 0}
        }
    }
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = []
    
    status, message, score, quality, reason = ResultValidator.validate(
        app_id=123,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False
    )
    assert status == "archive"
    assert "Success" in message

def test_builder_html_unescape():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Test &amp; Album"
    steam_meta.developer = "Dev &amp; Studio"
    steam_meta.publisher = "Pub &amp; Studio"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="Track &amp; Title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="ja"
    )

    assert tag_map["title"] == "Track & Title"
    assert tag_map["album"] == "Test & Album"

def test_copy_with_retry(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"
    
    copy_with_retry(src, dst, retries=2)
    assert dst.read_text() == "hello"

def test_clean_title_logic_strict_matching():
    # Only remove leading track prefix if it strictly matches track_number
    # Case 1: Match -> Cleaned
    assert MetadataBuilder._clean_title_logic("01. Song Title", "1") == "Song Title"
    assert MetadataBuilder._clean_title_logic("01 - Song Title", "1") == "Song Title"
    
    # Case 2: Number mismatch -> Keep as is (let system/validator review if necessary)
    assert MetadataBuilder._clean_title_logic("02. Song Title", "1") == "02. Song Title"
    
    # Case 3: Title with numeric theme like 1984 -> Keep if track is 1
    assert MetadataBuilder._clean_title_logic("1984 Theme", "1") == "1984 Theme"
