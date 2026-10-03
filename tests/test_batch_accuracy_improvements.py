from pathlib import Path
from unittest.mock import MagicMock

from sst.models import SteamMetadata
from sst.processor_support import (
    build_slot_variant_index,
    adopt_best_file_per_slot,
    select_best_unassigned_files,
    reconcile_deterministic_unassigned_slots,
)
from sst.llm.client import LLMClient
from sst.llm.organizer import LLMOrganizer
from sst.processor_pipeline import handle_early_review_return


def test_multi_format_variant_consolidation():
    """WAV and MP3 format variants are consolidated into the same Steam slot and excluded from unassigned."""
    steam_meta = SteamMetadata(
        app_id=1029810,
        name="The Textorcist - Soundtrack",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "The Textorcist"},
            {"disc": 1, "number": "2", "title": "Walking the Streets"},
        ],
    )

    track_groups = {
        (1, "The Textorcist::wav1"): [
            {"file_id": "wav1", "format": "wav", "duration": 120.0, "norm_stem": "the textorcist", "t_num_val": "1", "path": Path("/dummy/01_The Textorcist.wav")},
        ],
        (1, "The Textorcist::mp31"): [
            {"file_id": "mp31", "format": "mp3", "duration": 120.2, "norm_stem": "the textorcist", "t_num_val": "1", "path": Path("/dummy/01_The Textorcist.mp3")},
        ],
        (1, "Walking the Streets::wav2"): [
            {"file_id": "wav2", "format": "wav", "duration": 150.0, "norm_stem": "walking the streets", "t_num_val": "2", "path": Path("/dummy/02_Walking the Streets.wav")},
        ],
        (1, "Walking the Streets::mp32"): [
            {"file_id": "mp32", "format": "mp3", "duration": 150.1, "norm_stem": "walking the streets", "t_num_val": "2", "path": Path("/dummy/02_Walking the Streets.mp3")},
        ],
    }

    # Suppose LLM only mapped the WAV files
    final_metadata = {
        "1_The Textorcist::wav1": {"matched_v_idx": 0, "override_track": "1"},
        "1_Walking the Streets::wav2": {"matched_v_idx": 1, "override_track": "2"},
    }

    slot_variant_index, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    # Both slots should have 2 variants (WAV and MP3)
    assert (1, "1") in slot_variant_index
    assert (1, "2") in slot_variant_index
    assert len(slot_variant_index[(1, "1")]) == 2
    assert len(slot_variant_index[(1, "2")]) == 2

    # Adopt best file per slot should select WAV
    adopted = adopt_best_file_per_slot(track_groups, slot_variant_index, track_to_slot)
    assert len(adopted) == 2
    adopted_formats = {v["tier"] for v in adopted.values()}
    assert "lossless" in adopted_formats

    # select_best_unassigned_files should have 0 unassigned files!
    unassigned = select_best_unassigned_files(
        track_groups,
        final_metadata,
        slot_variant_index=slot_variant_index,
        track_to_slot_index=track_to_slot,
    )
    assert len(unassigned) == 0


def test_adopted_same_basename_slots_get_unique_staging_names():
    steam_meta = SteamMetadata(
        app_id=424242,
        name="Collision Test OST",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Gear Shift"},
            {"disc": 1, "number": "2", "title": "Gear Shift"},
        ],
    )
    track_groups = {
        (1, "gear shift first"): [
            {"file_id": "gear-a", "format": "mp3", "path": Path("/source-a/gear_shift.mp3")}
        ],
        (1, "gear shift second"): [
            {"file_id": "gear-b", "format": "mp3", "path": Path("/source-b/gear_shift.mp3")}
        ],
    }
    final_metadata = {
        "1_gear shift first": {"matched_v_idx": 0},
        "1_gear shift second": {"matched_v_idx": 1},
    }

    slot_variants, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)
    adopted = adopt_best_file_per_slot(track_groups, slot_variants, track_to_slot)

    assert len(adopted) == 2
    assert {info["staging_filename"] for info in adopted.values()} == {
        "gear_shift__sst_d1_t1.mp3",
        "gear_shift__sst_d1_t2.mp3",
    }


def test_unaligned_filename_number_does_not_override_steam_title():
    steam_meta = SteamMetadata(
        app_id=424243,
        name="Slot Identity Test OST",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Opening Theme"}],
    )
    track_groups = {
        (1, "menu whoosh::sfx1"): [
            {
                "file_id": "sfx1",
                "format": "mp3",
                "duration": 2.0,
                "t_num_val": "1",
                "path": Path("/source/menu_whoosh_01.mp3"),
            }
        ]
    }

    slot_variants, track_to_slot = build_slot_variant_index({}, track_groups, steam_meta)

    assert (1, "1") not in slot_variants
    assert (1, "menu whoosh::sfx1") in slot_variants
    assert track_to_slot["1_menu whoosh::sfx1"] == (1, "menu whoosh::sfx1")


def test_format_variant_can_merge_across_local_disc_tags_when_steam_title_is_unique():
    steam_meta = SteamMetadata(
        app_id=424244,
        name="Cross Disc Variant Test OST",
        store_tracklist=[{"disc": 4, "number": "20", "title": "Impact Truck Big 1"}],
    )
    track_groups = {
        (4, "Impact Truck Big 1::mp3"): [
            {
                "file_id": "mp3",
                "format": "mp3",
                "duration": 12.0,
                "norm_stem": "impact truck big 1",
                "t_num_val": "20",
                "path": Path("/source/disc4/impact_truck_big_01.mp3"),
            }
        ],
        (1, "Impact Truck Big 1::aiff"): [
            {
                "file_id": "aiff",
                "format": "aiff",
                "duration": 12.4,
                "norm_stem": "impact truck big 1",
                "t_num_val": "20",
                "path": Path("/source/disc1/impact_truck_big_01.aiff"),
            }
        ],
    }
    final_metadata = {"4_Impact Truck Big 1::mp3": {"matched_v_idx": 0}}

    slot_variants, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    assert len(slot_variants[(4, "20")]) == 2
    assert track_to_slot["1_Impact Truck Big 1::aiff"] == (4, "20")
    assert (1, "20") not in slot_variants


def test_reconciliation_does_not_assign_number_only_match():
    steam_meta = SteamMetadata(
        app_id=424245,
        name="No Number Only Match OST",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Known Theme"},
            {"disc": 1, "number": "2", "title": "Another Theme"},
        ],
    )
    final_metadata = {"1_known": {"matched_v_idx": 0}}
    track_groups = {
        (1, "Known Theme"): [{"file_id": "known", "t_num_val": "1", "norm_stem": "known theme"}],
        (1, "Menu Whoosh"): [{"file_id": "sfx", "t_num_val": "2", "norm_stem": "menu whoosh"}],
    }

    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata,
        track_groups,
        steam_meta,
        global_identity={},
    )

    assert reconciled == []
    assert "1_Menu Whoosh" not in final_metadata


def test_contradictory_llm_slot_keeps_steam_title_and_rejects_unrelated_file():
    local_tracks = [
        {
            "local_key": (1, "opening theme::good"),
            "file_ids": ["good"],
            "title": "Composer - Opening Theme",
            "duration_ms": 120000,
        },
        {
            "local_key": (1, "menu whoosh::bad"),
            "file_ids": ["bad"],
            "title": "Menu Whoosh",
            "duration_ms": 2000,
        },
    ]
    instructions = {
        "1_opening theme::good": {"matched_v_idx": 0, "reason": "LLM assignment"},
        "1_menu whoosh::bad": {"matched_v_idx": 0, "reason": "LLM assignment"},
    }

    filtered, contradictions = LLMOrganizer._reject_contradictory_slot_assignments(
        instructions,
        local_tracks,
        [{"v_idx": 0, "d": 1, "n": 1, "t": "Opening Theme"}],
    )

    assert list(filtered) == ["1_opening theme::good"]
    assert len(contradictions) == 1
    assert contradictions[0]["rejected_track_ids"] == ["1_menu whoosh::bad"]


def test_llm_same_title_format_candidates_remain_in_one_slot():
    local_tracks = [
        {
            "local_key": (1, "opening theme::aiff"),
            "file_ids": ["aiff"],
            "title": "Opening Theme",
            "duration_ms": 120000,
        },
        {
            "local_key": (1, "opening theme::mp3"),
            "file_ids": ["mp3"],
            "title": "Opening Theme",
            "duration_ms": 120500,
        },
    ]
    instructions = {
        "1_opening theme::aiff": {"matched_v_idx": 0, "reason": "LLM assignment"},
        "1_opening theme::mp3": {"matched_v_idx": 0, "reason": "LLM assignment"},
    }

    filtered, contradictions = LLMOrganizer._reject_contradictory_slot_assignments(
        instructions,
        local_tracks,
        [{"v_idx": 0, "d": 1, "n": 1, "t": "Opening Theme"}],
    )

    assert filtered == instructions
    assert contradictions == []


def test_client_token_budget_elevation():
    """Client provides at least 1536 minimum output tokens for track_mapping to withstand thinking models."""
    client = LLMClient(api_key="dummy", base_url="http://localhost:11434", model="test-model", llm_backend="OLLAMA")
    budget_1_track = client._estimate_expected_output_tokens("track_mapping", 1)
    assert budget_1_track >= 1536

    budget_20_tracks = client._estimate_expected_output_tokens("track_mapping", 20)
    assert budget_20_tracks >= 1536 + 20 * 80


def test_organizer_truncation_prematch_fallback():
    """Organizer recovers slot mapping via prematch hints if LLM track mapping returns None (truncated)."""
    organizer = LLMOrganizer(api_key="dummy", base_url="http://localhost:11434")
    # Mock LLM call to return None (simulating truncation error)
    organizer._call_llm = MagicMock(return_value=(None, {"error": "response truncated by backend", "error_code": "response_truncated"}))

    local_tracks = [
        {"local_key": (1, "What's wrong?"), "file_ids": ["fid1"], "n": 1, "title": "What's wrong?"},
        {"local_key": (1, "Red demon"), "file_ids": ["fid2"], "n": 2, "title": "Red demon"},
    ]
    global_res = {"identity_confidence": 100, "global_tags": {"canonical_album_artist": "Test Artist"}}
    full_ref_steam = [
        {"disc": 1, "number": "1", "title": "What's wrong!"},
        {"disc": 1, "number": "2", "title": "Red demon"},
    ]

    start_idx, instructions, logs = organizer._process_track_mapping_segment(
        app_id=789870,
        start_idx=0,
        segment_tracks=local_tracks,
        local_tracks=local_tracks,
        global_res=global_res,
        s_mbz_search={},
        v_mbz_search=None,
        full_ref_steam=full_ref_steam,
        full_ref_fingerprint=[],
        full_ref_mbz_search=[],
        coherence_mappings=None,
        num_ctx=8192,
        base_chunk_size=1,
        progress_callback=None,
        prematch_map=None,
    )

    # Should recover both slots via fallback number matching
    assert len(instructions) == 2
    assert "1_What's wrong?" in instructions
    assert "1_Red demon" in instructions


def test_organizer_identity_truncation_steam_trust_fallback():
    """Organizer applies STEAM-TRUST fallback when identity LLM fails but tracks structurally match 1:1."""
    organizer = LLMOrganizer(api_key="dummy", base_url="http://localhost:11434")
    organizer._call_llm = MagicMock(return_value=(None, {"error": "response truncated by backend"}))

    v_steam = {
        "album_name": "Sanctum 2: Original Soundtrack",
        "artist": "Coffee Stain Studios",
        "tracks": [{"disc": 1, "number": str(i), "title": f"Track {i}"} for i in range(1, 31)],
    }
    v_local = {
        "tracks": [{"disc": 1, "number": str(i), "title": f"Track {i}", "file_ids": [f"fid_{i}"], "local_key": (1, f"Track {i}")} for i in range(1, 31)],
    }

    final_instructions, llm_log = organizer.align_slots(
        app_id=335370,
        v_steam=v_steam,
        v_fingerprint=None,
        v_mbz_search=None,
        v_local=v_local,
    )

    phase1_res = llm_log.get("phase1_res")
    assert phase1_res is not None
    assert phase1_res.get("strategy") == "STEAM_BASED"
    assert phase1_res.get("identity_confidence") == 100
    assert "STEAM-TRUST" in phase1_res.get("confidence_reason", "")


def test_reconcile_deterministic_unassigned_slots_unique_match():
    """Deterministic residual reconciliation resolves 1:1 unique number/title matches."""
    steam_meta = SteamMetadata(
        app_id=2195300,
        name="Terra Flame Soundtrack",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Stage 1"},
            {"disc": 1, "number": "2", "title": "Boss 1"},
            {"disc": 1, "number": "3", "title": "Stage 2"},
        ],
    )
    # Slot 3 was already mapped
    final_metadata = {
        "1_Stage 2::fid3": {"matched_v_idx": 2, "override_track": "3"},
    }
    track_groups = {
        (1, "Stage 1::fid1"): [{"file_id": "fid1", "t_num_val": "1", "format": "mp3", "norm_stem": "stage 1"}],
        (1, "Boss 1::fid2"): [{"file_id": "fid2", "t_num_val": "2", "format": "mp3", "norm_stem": "boss 1"}],
        (1, "Stage 2::fid3"): [{"file_id": "fid3", "t_num_val": "3", "format": "mp3", "norm_stem": "stage 2"}],
    }

    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata=final_metadata,
        track_groups=track_groups,
        steam_meta=steam_meta,
        global_identity={"canonical_album_artist": "Composer"},
    )

    assert len(reconciled) == 2
    assert "1_Stage 1::fid1" in final_metadata
    assert "1_Boss 1::fid2" in final_metadata


def test_pipeline_early_review_message_alignment(tmp_path):
    """handle_early_review_return reports TRACK_MAPPING_FAILURE when Phase 1 was confident but Phase 2 produced no slots."""
    steam_meta = SteamMetadata(
        app_id=789870,
        name="Dead Dungeon - Soundtrack",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Track 1"}],
    )
    llm_log = {
        "phase1_res": {
            "album_confidence": 100,
            "confidence_reason": "SteamとMBZの完全一致",
        },
        "phase1_log": {},
    }
    diagnostics = {"trace": []}
    mock_now = MagicMock()
    mock_now.isoformat.return_value = "2026-08-24T00:00:00Z"
    mock_now.strftime.return_value = "2026-08-24 00:00:00"
    mock_config = MagicMock(resolved_metadata_source_priority="STEAM_BASED")

    res = handle_early_review_return(
        app_id=789870,
        steam_meta=steam_meta,
        track_count=1,
        llm_log=llm_log,
        v_steam={},
        v_local={},
        v_fingerprint=None,
        v_mbz_search=None,
        diagnostics=diagnostics,
        _diag=lambda *args, **kwargs: None,
        get_localized_now=lambda: mock_now,
        send_notifications=lambda *args, **kwargs: None,
        working_dir=tmp_path,
        output_dir=str(tmp_path / "output"),
        db=None,
        config=mock_config,
        preserve_working_files=False,
    )

    assert res.status == "review"
    assert "Track Mapping Failure" in res.message
    assert diagnostics["upstream_cause_code"] == "TRACK_MAPPING_FAILURE"
