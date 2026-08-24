from unittest.mock import MagicMock
from sst.llm.prematch import resolve_prematch_signals
from sst.llm.organizer import LLMOrganizer
from sst.processor_support import reconcile_deterministic_unassigned_slots
from sst.models import SteamMetadata

def test_resolve_prematch_deterministic_signals():
    local_tracks = [
        {"file_ids": ["fid1"], "track_num": 1, "norm_stem": "main theme", "title": "Main Theme", "disc": 1},
        {"file_ids": ["fid2"], "track_num": 2, "norm_stem": "boss battle", "title": "Boss Battle", "disc": 1},
    ]
    ref_steam = [
        {"n": 1, "t": "Main Theme", "d": 1, "v_idx": 0},
        {"n": 2, "t": "Boss Battle", "d": 1, "v_idx": 1},
    ]
    ref_fp = []
    ref_mbz = []
    
    prematch_map = resolve_prematch_signals(local_tracks, ref_steam, ref_fp, ref_mbz)
    assert len(prematch_map) == 2
    assert prematch_map["fid1"].is_deterministic is True
    assert prematch_map["fid1"].deterministic_steam_slot == 1
    assert prematch_map["fid2"].is_deterministic is True
    assert prematch_map["fid2"].deterministic_steam_slot == 2

def test_align_slots_differential_bypass_when_all_deterministic():
    organizer = LLMOrganizer(
        api_key="mock",
        base_url="http://localhost:11434",
        model="ornith:9b",
        llm_backend="OLLAMA",
    )
    organizer.llm_cache.enabled = False
    # Mock client call
    organizer._call_llm = MagicMock()
    
    local_tracks = [
        {"local_key": (1, "main theme"), "file_ids": ["fid1"], "track_num": 1, "title": "Main Theme", "norm_stem": "main theme", "disc": 1},
        {"local_key": (1, "boss battle"), "file_ids": ["fid2"], "track_num": 2, "title": "Boss Battle", "norm_stem": "boss battle", "disc": 1},
    ]
    v_steam = {
        "album": "Test Album",
        "tracks": [
            {"n": 1, "t": "Main Theme", "d": 1, "v_idx": 0},
            {"n": 2, "t": "Boss Battle", "d": 1, "v_idx": 1},
        ]
    }
    v_local = {"tracks": local_tracks}
    v_fingerprint = None
    v_mbz_search = None
    
    # Phase 1 mock
    organizer._call_llm.return_value = (
        {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "identity_confidence": 100,
            "integrity_quality": 100,
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "confidence_reason": "SYSTEM: Test",
            "strategy": "DIRECT",
            "semantic_label": "Archive",
            "global_tags": {"canonical_album": "Test Album"},
        },
        {"status": "ok"}
    )
    
    final_meta, llm_log = organizer.align_slots(
        app_id=12345,
        v_steam=v_steam,
        v_local=v_local,
        v_fingerprint=v_fingerprint,
        v_mbz_search=v_mbz_search,
    )
    
    # Check that Phase 2 was bypassed (only 1 call for Phase 1)
    assert organizer._call_llm.call_count == 1
    assert len(final_meta) == 2
    assert final_meta["1_main theme"]["override_track"] == "1"
    assert final_meta["1_boss battle"]["override_track"] == "2"

def test_reconcile_deterministic_unassigned_multiformat():
    track_groups = {
        (1, "battle theme::fid_flac"): [{"t_num_val": "3", "duration": 120.0, "format": "flac"}],
        (1, "battle theme::fid_mp3"): [{"t_num_val": "3", "duration": 120.05, "format": "mp3"}],
    }
    steam_meta = SteamMetadata(
        app_id=123,
        name="Test Game",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Intro"},
            {"disc": 1, "number": "2", "title": "Field"},
            {"disc": 1, "number": "3", "title": "Battle Theme"},
        ],
    )
    final_metadata = {
        "1_intro": {"matched_v_idx": 0, "override_track": "1"},
        "1_field": {"matched_v_idx": 1, "override_track": "2"},
    }
    
    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata=final_metadata,
        track_groups=track_groups,
        steam_meta=steam_meta,
        global_identity={"canonical_album_artist": "Composer"},
    )
    
    assert len(reconciled) == 2
    assert "1_battle theme::fid_flac" in final_metadata
    assert "1_battle theme::fid_mp3" in final_metadata
    assert final_metadata["1_battle theme::fid_flac"]["override_track"] == "3"
    assert final_metadata["1_battle theme::fid_mp3"]["override_track"] == "3"

def test_steam_trust_multiformat_equivalence():
    organizer = LLMOrganizer(
        api_key="mock",
        base_url="http://localhost:11434",
        model="ornith:9b",
        llm_backend="OLLAMA",
    )
    organizer.llm_cache.enabled = False
    organizer._call_llm = MagicMock()

    # 2 Steam tracks, but 4 local files (FLAC + MP3)
    local_tracks = [
        {"local_key": (1, "main theme::flac"), "file_ids": ["fid1_flac"], "track_num": 1, "title": "Main Theme", "norm_stem": "main theme", "disc": 1},
        {"local_key": (1, "main theme::mp3"), "file_ids": ["fid1_mp3"], "track_num": 1, "title": "Main Theme", "norm_stem": "main theme", "disc": 1},
        {"local_key": (1, "boss battle::flac"), "file_ids": ["fid2_flac"], "track_num": 2, "title": "Boss Battle", "norm_stem": "boss battle", "disc": 1},
        {"local_key": (1, "boss battle::mp3"), "file_ids": ["fid2_mp3"], "track_num": 2, "title": "Boss Battle", "norm_stem": "boss battle", "disc": 1},
    ]
    v_steam = {
        "album": "Multi-format Game Soundtrack",
        "tracks": [
            {"n": 1, "t": "Main Theme", "d": 1, "v_idx": 0},
            {"n": 2, "t": "Boss Battle", "d": 1, "v_idx": 1},
        ]
    }
    v_local = {"tracks": local_tracks}

    # Phase 1 returns conservative scores (85%)
    organizer._call_llm.return_value = (
        {
            "album_confidence": 85,
            "mapping_confidence": 85,
            "data_quality": 60,
            "identity_confidence": 85,
            "integrity_quality": 60,
            "archive_vs_review_ratio": {"archive": 85, "review": 15},
            "strategy": "STEAM_BASED",
            "global_tags": {"canonical_album": "Multi-format Game Soundtrack"},
        },
        {"status": "ok"}
    )

    final_meta, llm_log = organizer.align_slots(
        app_id=99999,
        v_steam=v_steam,
        v_local=v_local,
        v_fingerprint=None,
        v_mbz_search=None,
    )

    p1_res = llm_log["phase1_res"]
    # Check that STEAM-TRUST boosted scores to 100%
    assert p1_res["identity_confidence"] == 100
    assert p1_res["album_confidence"] == 100
    assert p1_res["data_quality"] == 100
    assert p1_res["archive_vs_review_ratio"]["archive"] == 100
    assert len(final_meta) == 4
