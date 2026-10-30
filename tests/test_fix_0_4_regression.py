from pathlib import Path


from sst.track_grouper import TrackManager, EmbeddedMetadataExtractor
from sst.llm.response_parser import parse_llm_response
from sst.validator import ResultValidator
from sst.models import SteamMetadata
from sst.processing.slot_variants import build_slot_variant_index


def test_validator_remix_extended_coexistence():
    """Test that tracks with (Remix) or (Extended Ver.) coexisting with original tracks
    do not trigger false positive Official Title Mismatch when matched with their assigned slot.
    """
    steam_meta = SteamMetadata(
        app_id="123450",
        name="Test OST",
        store_tracklist=[
            {"disc": 1, "number": 1, "title": "In My Heart"},
            {"disc": 1, "number": 2, "title": "In My Heart (Extended Ver.)"},
        ],
    )
    
    # Track assigned to slot 1_1 and 1_2
    tracks = [
        {
            "disc": 1,
            "track": 1,
            "clean_title": "In My Heart",
            "original_filename": "01. In My Heart.mp3",
            "original_title": "In My Heart",
            "file_id": "file1",
            "duration_s": 180.0,
            "tags": {
                "disc_number": "1",
                "track_number": "1",
                "title": "In My Heart",
            },
        },
        {
            "disc": 1,
            "track": 2,
            "clean_title": "In My Heart (Extended Ver.)",
            "original_filename": "02. In My Heart (Extended Ver.).mp3",
            "original_title": "In My Heart (Extended Ver.)",
            "file_id": "file2",
            "duration_s": 240.0,
            "tags": {
                "disc_number": "1",
                "track_number": "2",
                "title": "In My Heart (Extended Ver.)",
            },
        },
    ]
    
    llm_log = {
        "phase1_res": {
            "album_confidence": 95,
            "data_quality": 95,
            "strategy": "STEAM_BASED",
            "confidence_reason": "High match",
        }
    }
    
    status, message, album_conf, quality, reason = ResultValidator.validate(
        app_id=123450,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )
    assert "Official Title Mismatch" not in message, f"False positive mismatch found in message: {message}"
    assert status == "archive"


def test_validator_detects_true_swap():
    """Test that true track swapping (e.g. 4206020 case) is still detected as an issue."""
    steam_meta = SteamMetadata(
        app_id="123451",
        name="Test OST",
        store_tracklist=[
            {"disc": 1, "number": 1, "title": "Opening Theme"},
            {"disc": 1, "number": 2, "title": "Battle Theme"},
        ],
    )
    
    # Swapped: slot 1_1 has Battle Theme file and titles, slot 1_2 has Opening Theme
    tracks = [
        {
            "disc": 1,
            "track": 1,
            "clean_title": "Battle Theme",
            "original_filename": "02. Battle Theme.mp3",
            "original_title": "Battle Theme",
            "file_id": "file1",
            "duration_s": 120.0,
            "tags": {
                "disc_number": "1",
                "track_number": "1",
                "title": "Opening Theme",
            },
        },
        {
            "disc": 1,
            "track": 2,
            "clean_title": "Opening Theme",
            "original_filename": "01. Opening Theme.mp3",
            "original_title": "Opening Theme",
            "file_id": "file2",
            "duration_s": 150.0,
            "tags": {
                "disc_number": "1",
                "track_number": "2",
                "title": "Battle Theme",
            },
        },
    ]
    
    llm_log = {
        "phase1_res": {
            "album_confidence": 95,
            "data_quality": 95,
            "strategy": "STEAM_BASED",
            "confidence_reason": "Test",
        }
    }
    
    status, message, album_conf, quality, reason = ResultValidator.validate(
        app_id=123451,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )
    assert "Official Title Mismatch" in message, f"Expected Official Title Mismatch in message: {message}"
    assert status == "review"


def test_single_letter_prefix_track_extraction():
    """Test that single letter prefix filenames like A_25_Track.mp3 correctly extract track 25."""
    fake_file = Path("/music/A_25_Oligarch_s Dream.mp3")
    
    orig_extract = EmbeddedMetadataExtractor.extract
    orig_get_duration = TrackManager.get_duration
    try:
        EmbeddedMetadataExtractor.extract = staticmethod(lambda p: {})
        TrackManager.get_duration = staticmethod(lambda p: 120.0)
        
        file_records = TrackManager.build_file_records([fake_file])
        found_tracks = []
        for (disc, fmt), records in file_records.items():
            for r in records:
                found_tracks.append((r.get("t_num_val"), r.get("norm_stem")))
        
        assert any(t[0] == "25" for t in found_tracks), f"Expected track 25 extracted, got: {found_tracks}"
    finally:
        EmbeddedMetadataExtractor.extract = orig_extract
        TrackManager.get_duration = orig_get_duration


def test_llm_json_duplicate_key_merging():
    """Test that parse_llm_response preserves valid slot mappings when LLM outputs duplicate keys."""
    json_text = """
    {
        "status": "success",
        "slots": {
            "1_1": {"files": ["01.mp3"], "reason": "match"},
            "1_23": {"files": ["23.mp3"], "reason": "match 23"},
            "1_2": {"files": ["02.mp3"], "reason": "match"},
            "1_23": {"files": [], "reason": "cleared by mistake"}
        },
        "unassigned_files": ["bonus.mp3"]
    }
    """
    parsed = parse_llm_response(json_text, request_kind="track_mapping", degraded_active=False)
    slots = parsed.get("slots", {})
    assert "1_23" in slots
    # Should retain the non-empty files from the earlier pair
    assert slots["1_23"]["files"] == ["23.mp3"]


def test_multidisc_continuous_numbering_variant_consolidation():
    """Test that a brother WAV file with matching track number and stem integrates into Disc 2 slot."""
    final_metadata = {
        "2_stage 5 boss::mp3_20": {
            "matched_v_idx": 1,
        }
    }

    track_groups = {
        (2, "stage 5 boss::mp3_20"): [
            {
                "file_id": "mp3_20",
                "path": Path("/music/20. Stage 5 Boss.mp3"),
                "format": "mp3",
                "duration": 180.0,
                "norm_stem": "stage 5 boss",
                "disc": 1,
                "t_num_val": "20",
            }
        ],
        (1, "stage 5 boss::wav_20"): [
            {
                "file_id": "wav_20",
                "path": Path("/music/20. Stage 5 Boss.wav"),
                "format": "wav",
                "duration": 180.0,
                "norm_stem": "stage 5 boss",
                "disc": 1,
                "t_num_val": "20",
            }
        ],
    }

    steam_meta = SteamMetadata(
        app_id="1879310",
        name="TCSTRIKERS4",
        store_tracklist=[
            {"disc": 1, "number": 1, "title": "Track 1"},
            {"disc": 2, "number": 20, "title": "Stage 5 Boss"},
        ],
    )

    orig_get_dur = TrackManager.get_duration
    try:
        TrackManager.get_duration = staticmethod(lambda p: 180.0)
        slot_variants, track_to_slot = build_slot_variant_index(
            final_metadata=final_metadata,
            track_groups=track_groups,
            steam_meta=steam_meta,
        )
    finally:
        TrackManager.get_duration = orig_get_dur

    assert (2, "20") in slot_variants
    variant_ids = [v["file_id"] for v in slot_variants[(2, "20")]]
    assert "wav_20" in variant_ids
    assert track_to_slot["1_stage 5 boss::wav_20"] == (2, "20")
