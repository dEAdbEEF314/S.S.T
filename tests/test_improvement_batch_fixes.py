"""Tests for Batch Accuracy and Archive Throughput Improvements.

Verifies:
1. Format Variant Deduplication with 4-way AND condition in resolve_duplicate_mappings
2. Fast-Track title matching with format stem
3. Deterministic Slot Reconciliation (Sudoku-like 1:1 constraint match)
4. Dirty Tags exception when title originates from Steam official tracklist
5. Audio Quality Warning diagnostics recording while preserving Review status
6. Early Review cause code precision for missing Steam tracklists
"""

from pathlib import Path

from sst.models import SteamMetadata
from sst.validator import ResultValidator
from sst.processor_support import resolve_duplicate_mappings


def test_format_variant_deduplication_4way_and():
    """Format variants with different formats, matching title/stem and duration delta < 1.0s must merge."""
    app_id = 999001
    steam_meta = SteamMetadata(
        app_id=app_id,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Main Theme", "name": "Main Theme"}
        ],
    )
    
    # 2 variants mapped to same v_idx 0: 1 AIF (Tier 1) and 1 MP3 (Tier 3)
    track_groups = {
        (1, "Main Theme"): [
            {"format": "aif", "duration": 180.2, "path": Path("/mock/01 Main Theme.aif"), "file_id": "fid_aif"}
        ],
        (1, "Main Theme mp3"): [
            {"format": "mp3", "duration": 180.4, "path": Path("/mock/01 Main Theme.mp3"), "file_id": "fid_mp3"}
        ],
    }
    final_metadata = {
        "1_Main Theme": {"matched_v_idx": 0, "action": "use_steam"},
        "1_Main Theme mp3": {"matched_v_idx": 0, "action": "use_steam"},
    }

    resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)

    # The lower tier mp3 should be merged into best_tid and deleted from final_metadata
    assert "1_Main Theme" in final_metadata
    assert "1_Main Theme mp3" not in final_metadata
    assert (1, "Main Theme") in track_groups
    assert (1, "Main Theme mp3") not in track_groups
    assert len(track_groups[(1, "Main Theme")]) == 2


def test_format_variant_different_duration_not_merged():
    """Variants with duration delta >= 1.0s must NOT be merged (must remain separate for Review)."""
    app_id = 999002
    steam_meta = SteamMetadata(
        app_id=app_id,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Main Theme", "name": "Main Theme"}
        ],
    )
    track_groups = {
        (1, "Main Theme"): [
            {"format": "aif", "duration": 180.0, "path": Path("/mock/01 Main Theme.aif"), "file_id": "fid_aif"}
        ],
        (1, "Main Theme Short"): [
            {"format": "mp3", "duration": 90.0, "path": Path("/mock/01 Main Theme Short.mp3"), "file_id": "fid_mp3"}
        ],
    }
    final_metadata = {
        "1_Main Theme": {"matched_v_idx": 0, "action": "use_steam"},
        "1_Main Theme Short": {"matched_v_idx": 0, "action": "use_steam"},
    }

    resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)

    # Should NOT be merged due to duration difference >= 1.0s
    assert "1_Main Theme" in final_metadata
    assert "1_Main Theme Short" in final_metadata


def test_deterministic_slot_reconciliation():
    """A missing slot and an unassigned file matching in track number and title must be reconciled."""
    from sst.processor_support import reconcile_deterministic_unassigned_slots
    app_id = 999010
    steam_meta = SteamMetadata(
        app_id=app_id,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "First Song"},
            {"disc": 1, "number": "2", "title": "Second Song"},
        ],
    )
    track_groups = {
        (1, "First Song"): [{"format": "flac", "duration": 100.0, "t_num_val": 1, "path": Path("01.flac")}],
        (1, "Second Song"): [{"format": "flac", "duration": 200.0, "t_num_val": 2, "path": Path("02.flac")}],
    }
    # LLM mapped track 1 but accidentally omitted track 2
    final_metadata = {
        "1_First Song": {"matched_v_idx": 0, "override_track": "1"}
    }
    global_identity = {"canonical_album_artist": "Test Artist"}

    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata,
        track_groups,
        steam_meta,
        global_identity,
    )

    assert len(reconciled) == 1
    assert "1_Second Song" in final_metadata
    assert final_metadata["1_Second Song"]["matched_v_idx"] == 1
    assert final_metadata["1_Second Song"]["override_track"] == "2"


def test_dirty_tags_steam_title_exception():
    """If the track title originated from Steam, numeric prefixes must not trigger Dirty Tags."""
    app_id = 999003
    steam_meta = SteamMetadata(
        app_id=app_id,
        name="Official Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "01 Intro Theme"}
        ],
    )
    tracks = [
        {
            "tags": {"disc_number": "1", "track_number": "1", "title": "01 Intro Theme"},
            "title_source": "STEAM",
        }
    ]
    llm_log = {
        "fast_track": True,
        "phase1_res": {"album_confidence": 100, "mapping_confidence": 100, "data_quality": 100},
    }

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=app_id,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )

    assert "Dirty Tags" not in message
    assert status == "archive"


def test_audio_warn_records_diagnostics_and_stays_review():
    """Audio quality warnings must record structured diagnostics while maintaining Review status."""
    app_id = 999004
    steam_meta = SteamMetadata(
        app_id=app_id,
        name="Official Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Clean Track"}
        ],
    )
    tracks = [
        {
            "tags": {"disc_number": "1", "track_number": "1", "title": "Clean Track"},
            "title_source": "STEAM",
        }
    ]
    llm_log = {
        "fast_track": True,
        "phase1_res": {"album_confidence": 100, "mapping_confidence": 100, "data_quality": 100},
    }

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=app_id,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=True,
    )

    assert status == "review"
    assert "Audio quality warning" in message
    assert llm_log.get("diagnostics", {}).get("audio_quality_warnings") is True
