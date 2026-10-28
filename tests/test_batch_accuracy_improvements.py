from pathlib import Path
from unittest.mock import MagicMock, patch

from sst.track_grouper import TrackManager

from sst.models import SteamMetadata
from sst.processor_support import (
    build_slot_variant_index,
    adopt_best_file_per_slot,
    select_best_unassigned_files,
    select_slot_conflict_candidates,
    reconcile_deterministic_unassigned_slots,
)
from sst.llm.client import LLMClient
from sst.llm.organizer import LLMOrganizer
from sst.processor_pipeline import handle_early_review_return
from sst.processing.track_batch import _convert_review_candidates


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


def test_slot_conflict_candidate_keeps_rejected_title_but_collapses_its_formats(tmp_path):
    adopted_path = tmp_path / "27_Final Boss.aiff"
    rejected_mp3_path = tmp_path / "27_Final Boss Extended.mp3"
    rejected_flac_path = tmp_path / "27_Final Boss Extended.flac"
    for path in (adopted_path, rejected_mp3_path, rejected_flac_path):
        path.write_bytes(b"audio")

    adopted_key = (1, "final boss::steam")
    rejected_mp3_key = (1, "final boss extended::mp3")
    rejected_flac_key = (1, "final boss extended::flac")
    track_groups = {
        adopted_key: [{"file_id": "adopted", "path": adopted_path, "format": "aiff"}],
        rejected_mp3_key: [{"file_id": "rejected-mp3", "path": rejected_mp3_path, "format": "mp3"}],
        rejected_flac_key: [{"file_id": "rejected-flac", "path": rejected_flac_path, "format": "flac"}],
    }
    slot_variants = {
        (1, "27"): [
            variant
            for variants in track_groups.values()
            for variant in variants
        ]
    }
    adopted_files = {
        adopted_key: {"path": adopted_path, "slot_key": (1, "27"), "tier_rank": 0}
    }

    candidates = select_slot_conflict_candidates(
        track_groups, slot_variants, adopted_files
    )

    assert len(candidates) == 1
    assert candidates[0]["file_id"] == "rejected-flac"
    assert candidates[0]["path"] == rejected_flac_path
    assert candidates[0]["candidate_type"] == "slot_conflict"


def test_review_candidate_conversion_preserves_basename_and_records_fallback(tmp_path):
    source = tmp_path / "source" / "27 Final Boss Extended.flac"
    source.parent.mkdir()
    source.write_bytes(b"original audio")
    output = tmp_path / "output"

    class FakeTagger:
        def __init__(self, should_fail=False):
            self.should_fail = should_fail

        def convert_and_limit(self, source_path, tier, subdir):
            if self.should_fail:
                raise RuntimeError("synthetic conversion failure")
            target = output / subdir / f"{Path(source_path).stem}.aif"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"converted audio")
            return target, False

    candidate = {
        "path": source,
        "tier": "lossless",
        "candidate_type": "slot_conflict",
        "slot_key": (1, "27"),
        "reason": "Different logical title assigned to Steam slot 1_27",
    }
    converted = _convert_review_candidates(FakeTagger(), output, [candidate])[0]

    assert converted["original_filename"] == "27 Final Boss Extended.flac"
    assert converted["output_filename"] == "27 Final Boss Extended.aif"
    assert converted["converted"] is True
    assert (output / converted["file_path"]).is_file()

    fallback = _convert_review_candidates(
        FakeTagger(should_fail=True), output, [candidate]
    )[0]

    assert fallback["original_filename"] == "27 Final Boss Extended.flac"
    assert fallback["output_filename"] == "27 Final Boss Extended.flac"
    assert fallback["converted"] is False
    assert fallback["included"] is True
    assert fallback["conversion_error_type"] == "RuntimeError"
    assert (output / fallback["file_path"]).read_bytes() == b"original audio"

    missing_source = {
        **candidate,
        "path": tmp_path / "missing" / "Unknown Track.flac",
    }
    unavailable = _convert_review_candidates(
        FakeTagger(should_fail=True), output, [missing_source]
    )[0]

    assert unavailable["original_filename"] == "Unknown Track.flac"
    assert unavailable["included"] is False
    assert unavailable["conversion_error_type"] == "RuntimeError"
    assert unavailable["copy_error_type"] == "FileNotFoundError"


def test_review_candidate_audio_manifest_and_html_are_packaged_together(tmp_path):
    import json
    import zipfile
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from sst.packager import PackageManager
    from sst.processing.package_output import save_album_package

    output = tmp_path / "output"
    temp_output = tmp_path / "work"
    candidate_path = temp_output / "review_candidates" / "candidate_001" / "01 Theme.mp3"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(b"synthetic audio")
    candidate = {
        "candidate_type": "slot_conflict",
        "original_filename": "01 Theme.mp3",
        "file_id": "synthetic-file",
        "track_id": "1_01 theme",
        "slot_key": "1_1",
        "reason": "Different logical title assigned to Steam slot 1_1",
        "included": True,
        "converted": True,
        "output_format": "mp3",
        "file_path": "review_candidates/candidate_001/01 Theme.mp3",
    }
    steam_meta = SteamMetadata(
        app_id=887001,
        name="Review Candidate Test",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Theme"}],
    )

    save_album_package(
        app_id=887001,
        status="review",
        steam_meta=steam_meta,
        summary_meta={"audit": {"review_candidate_count": 1}},
        llm_log={"diagnostics": {"review_candidates": [candidate]}},
        mbz_log={},
        processed_tracks_meta=[],
        mbz_candidates=[],
        localized_now_str="2026-10-08 12:00:00",
        message="Synthetic review",
        score=50,
        reason="Synthetic candidate review",
        alignment_inputs_bundle={},
        quality=50,
        unassigned_manifest=[],
        discord_msg=None,
        temp_output=temp_output,
        config=SimpleNamespace(
            resolved_metadata_source_priority="STEAM_STORE,STEAM_PICS",
            sst_output_dir=str(output),
            zip_compression_strategy="stored",
            zip_deflate_level=1,
        ),
        db=MagicMock(),
        package_manager=PackageManager,
        get_localized_now=lambda: datetime(2026, 10, 8, tzinfo=timezone.utc),
        diagnostics={},
        diag=lambda *args, **kwargs: None,
    )

    package_path = output / "review" / "887001_Review_Candidate_Test.zip"
    with zipfile.ZipFile(package_path) as package:
        assert "review_candidates/candidate_001/01 Theme.mp3" in package.namelist()
        manifest = json.loads(package.read("json/review_manifest.json"))
        report = package.read("AUDIT_REPORT.html").decode("utf-8")

    assert manifest["review_candidates"] == [candidate]
    assert "Review候補ファイル (1件)" in report
    assert "01 Theme.mp3" in report
    assert "Different logical title assigned to Steam slot 1_1" in report


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


def test_resolve_disc_title_matches_strips_file_id_and_punctuation():
    from sst.processor_support import resolve_duplicate_mappings

    # Disc 1 has slots:
    # v_idx=4: Disc 1 Track 5 "They're Here"
    # v_idx=5: Disc 1 Track 6 "Coward's Crossing"
    # Disc 2 has slot:
    # v_idx=26: Disc 2 Track 1 "The Pale Reach"
    store_tracklist = [
        {"disc": 1, "number": "1", "title": "Track 1"},
        {"disc": 1, "number": "2", "title": "Track 2"},
        {"disc": 1, "number": "3", "title": "Track 3"},
        {"disc": 1, "number": "4", "title": "Track 4"},
        {"disc": 1, "number": "5", "title": "They're Here"},       # v_idx=4
        {"disc": 1, "number": "6", "title": "Coward's Crossing"},   # v_idx=5
    ]
    # pad up to v_idx=25
    for i in range(7, 27):
        store_tracklist.append({"disc": 1, "number": str(i), "title": f"Track {i}"})
    store_tracklist.append({"disc": 2, "number": "1", "title": "The Pale Reach"})  # v_idx=26

    steam_meta = SteamMetadata(
        app_id=802640,
        name="Test Game",
        store_tracklist=store_tracklist,
    )

    tid1 = "1_they re here::abcdef1234567890"
    tid2 = "1_cowards crossing::1234567890abcdef"
    final_metadata = {
        tid1: {"matched_v_idx": 26, "override_track": "1"},
        tid2: {"matched_v_idx": 26, "override_track": "1"},
    }
    track_groups = {
        (1, "they re here::abcdef1234567890"): [
            {"format": "mp3", "duration": 100.0, "meta": {"title": "They're Here!"}}
        ],
        (1, "cowards crossing::1234567890abcdef"): [
            {"format": "mp3", "duration": 120.0, "meta": {"title": "Cowards Crossing"}}
        ],
    }

    resolve_duplicate_mappings(802640, final_metadata, steam_meta, track_groups)

    assert final_metadata[tid1]["matched_v_idx"] == 4
    assert final_metadata[tid2]["matched_v_idx"] == 5


def test_japanese_titles_match_in_unassigned_reconciliation_and_slot_variants():
    steam_meta = SteamMetadata(
        app_id=999999,
        name="Japanese Test Game",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "いつかあの場所で"},
        ],
    )

    track_groups = {
        (1, "いつかあの場所で::wav1"): [
            {"file_id": "wav1", "format": "wav", "duration": 180.0, "norm_stem": "いつかあの場所で", "t_num_val": "1", "path": Path("/dummy/01 いつかあの場所で.wav")},
        ],
        (1, "いつかあの場所で::mp31"): [
            {"file_id": "mp31", "format": "mp3", "duration": 180.1, "norm_stem": "いつかあの場所で", "t_num_val": "1", "path": Path("/dummy/01 いつかあの場所で.mp3")},
        ],
    }

    # 1. Test build_slot_variant_index with Japanese title WAV and MP3 variants
    final_metadata = {
        "1_いつかあの場所で::wav1": {"matched_v_idx": 0, "override_track": "1"},
    }

    slot_variant_index, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    # Slot (1, "1") should consolidate both WAV and MP3 variants
    assert (1, "1") in slot_variant_index
    assert len(slot_variant_index[(1, "1")]) == 2

    # 2. Test reconcile_deterministic_unassigned_slots with unassigned Japanese track
    final_metadata_unassigned = {}
    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata=final_metadata_unassigned,
        track_groups=track_groups,
        steam_meta=steam_meta,
        global_identity={"canonical_album_artist": "Composer"},
    )

    assert len(reconciled) >= 1
    assert "1_いつかあの場所で::wav1" in final_metadata_unassigned
    assert final_metadata_unassigned["1_いつかあの場所で::wav1"]["matched_v_idx"] == 0


def test_adopt_best_file_per_slot_excludes_unaligned_tracks_and_routes_to_unassigned():
    from sst.models import SteamMetadata
    from sst.processor_support import (
        build_slot_variant_index,
        adopt_best_file_per_slot,
        select_best_unassigned_files,
    )
    from sst.validator import ResultValidator

    steam_meta = SteamMetadata(
        app_id=1879310,
        name="TCSTRIKERS4 original soundtrack",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Opening"},
            {"disc": 1, "number": "2", "title": "Ending"},
        ],
    )

    track_groups = {
        (1, "opening::wav1"): [
            {"file_id": "wav1", "format": "wav", "duration": 100.0, "norm_stem": "opening", "t_num_val": "1", "path": Path("/dummy/01 Opening.wav")},
        ],
        (1, "ending::wav2"): [
            {"file_id": "wav2", "format": "wav", "duration": 120.0, "norm_stem": "ending", "t_num_val": "2", "path": Path("/dummy/02 Ending.wav")},
        ],
        (1, "bonus unused::wav3"): [
            {"file_id": "wav3", "format": "wav", "duration": 90.0, "norm_stem": "bonus unused", "t_num_val": "99", "path": Path("/dummy/99 Bonus Unused.wav")},
        ],
    }

    final_metadata = {
        "1_opening::wav1": {"matched_v_idx": 0, "override_track": "1"},
        "1_ending::wav2": {"matched_v_idx": 1, "override_track": "2"},
    }

    # 1. build_slot_variant_index
    slot_variant_index, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    # 2. adopt_best_file_per_slot should only adopt the 2 aligned slots
    adopted = adopt_best_file_per_slot(track_groups, slot_variant_index, track_to_slot)
    assert len(adopted) == 2
    adopted_file_ids = {info["file_id"] for info in adopted.values()}
    assert "wav1" in adopted_file_ids
    assert "wav2" in adopted_file_ids
    assert "wav3" not in adopted_file_ids

    # 3. select_best_unassigned_files should have exactly 1 file: "99 Bonus Unused.wav"
    unassigned = select_best_unassigned_files(
        track_groups,
        final_metadata,
        slot_variant_index=slot_variant_index,
        track_to_slot_index=track_to_slot,
    )
    assert len(unassigned) == 1
    assert unassigned[0]["file_id"] == "wav3"

    # 4. ResultValidator.validate:
    # 2 tracks and 1 unassigned_manifest
    tracks = [
        {"tags": {"disc_number": "1", "track_number": "1", "title": "Opening"}},
        {"tags": {"disc_number": "1", "track_number": "2", "title": "Ending"}},
    ]
    llm_log = {
        "phase1_res": {
            "identity_confidence": 100,
            "integrity_quality": 100,
            "album_confidence": 100,
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "confidence_reason": "Exact match",
        },
        "alignment_res": {
            "slots": {"1": {"title": "Opening"}, "2": {"title": "Ending"}},
        },
    }
    unassigned_manifest = unassigned

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=1879310,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
        unassigned_manifest=unassigned_manifest,
    )

    assert status == "review"
    assert "Unassigned Files (1)" in message
    assert "Output Track Count Mismatch" not in message
    assert "Steam Slots Unexpected" not in message
    assert "Duplicates" not in message


def test_identity_does_not_trigger_steam_trust_on_api_connection_error():
    organizer = LLMOrganizer(api_key="dummy", base_url="http://localhost:11434")
    organizer._call_llm = MagicMock(
        return_value=(
            None,
            {
                "error": "litellm.APIConnectionError: OllamaException - Cannot connect to host localhost:11434 [Connect call failed]"
            },
        )
    )

    v_steam = {
        "album_name": "Sanctum 2: Original Soundtrack",
        "artist": "Coffee Stain Studios",
        "tracks": [{"disc": 1, "number": str(i), "title": f"Track {i}"} for i in range(1, 31)],
    }
    v_local = {
        "tracks": [
            {
                "disc": 1,
                "number": str(i),
                "title": f"Track {i}",
                "file_ids": [f"fid_{i}"],
                "local_key": (1, f"Track {i}"),
            }
            for i in range(1, 31)
        ],
    }

    final_instructions, llm_log = organizer.align_slots(
        app_id=335370,
        v_steam=v_steam,
        v_fingerprint=None,
        v_mbz_search=None,
        v_local=v_local,
    )

    assert not final_instructions
    assert llm_log.get("phase1_res") is None
    assert "phase1_log" in llm_log
    assert "Cannot connect to host" in str(llm_log["phase1_log"].get("error", ""))


def test_recover_prematch_fallback_slots_rejects_mismatched_titles_and_preserves_multiple_files():
    # Case A: AppID 4206020 reproduction - mismatched title must not be assigned by track number alone
    steam_tracks_a = [
        {"disc": 1, "number": "1", "title": "Rebal"},
        {"disc": 1, "number": "2", "title": "The Final Stand"},
    ]
    local_chunk_a = [
        {"n": 0, "title": "0. REBEL", "file_ids": ["fid0"]},
        {"n": 1, "title": "1. THE FINAL STAND", "file_ids": ["fid1"]},
    ]
    fallback_a = LLMOrganizer._recover_prematch_fallback_slots(local_chunk_a, None, steam_tracks_a)
    assert fallback_a == {}

    # Case B: Multiple file IDs for same slot are preserved (no dict overwrite)
    steam_tracks_b = [
        {"disc": 1, "number": "1", "title": "Main Theme"},
    ]
    local_chunk_b = [
        {"n": 1, "title": "Main Theme", "file_ids": ["wav1", "mp31"]},
    ]
    fallback_b = LLMOrganizer._recover_prematch_fallback_slots(local_chunk_b, None, steam_tracks_b)
    assert "1" in fallback_b
    assert fallback_b["1"]["files"] == ["wav1", "mp31"]


def test_single_disc_numeric_title_filenames_do_not_corrupt_disc_number(tmp_path):
    file_names = [
        "01_monorail hype.mp3",
        "05_4.8 stars.mp3",
        "07_9.01 am.mp3",
        "12_401cave.mp3",
        "20_401grave.mp3",
        "24-NormalTrack.flac",
        "25-5StarArcade.flac",
        "52_Normal.wav",
        "53_17 Doors.wav",
        "06_EP3_sarai_Remix.mp3",
        "07_18noayamachi.mp3",
    ]
    files = []
    for name in file_names:
        p = tmp_path / name
        p.write_bytes(b"dummy audio content")
        files.append(p)

    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract", return_value={}), \
         patch("sst.track_grouper.TrackManager.get_duration", return_value=120.0):
        records_by_group = TrackManager.build_file_records(files)

    all_tracks = [t for group in records_by_group.values() for t in group]
    assert len(all_tracks) == len(file_names)

    # Every record's disc must be 1
    for t in all_tracks:
        assert t["disc"] == 1, f"Expected disc 1 for {t['path'].name}, got {t['disc']}"

    tracks_by_name = {t["path"].name: t for t in all_tracks}

    assert tracks_by_name["05_4.8 stars.mp3"]["filename_track"] == 5
    assert tracks_by_name["05_4.8 stars.mp3"]["t_num_val"] == "5"
    assert "4 8 stars" in tracks_by_name["05_4.8 stars.mp3"]["norm_stem"]

    assert tracks_by_name["07_9.01 am.mp3"]["filename_track"] == 7
    assert tracks_by_name["07_9.01 am.mp3"]["t_num_val"] == "7"

    assert tracks_by_name["12_401cave.mp3"]["filename_track"] == 12
    assert tracks_by_name["12_401cave.mp3"]["t_num_val"] == "12"

    assert tracks_by_name["20_401grave.mp3"]["filename_track"] == 20
    assert tracks_by_name["20_401grave.mp3"]["t_num_val"] == "20"

    assert tracks_by_name["25-5StarArcade.flac"]["filename_track"] == 25
    assert tracks_by_name["25-5StarArcade.flac"]["t_num_val"] == "25"
    assert "5stararcade" in tracks_by_name["25-5StarArcade.flac"]["norm_stem"]

    assert tracks_by_name["53_17 Doors.wav"]["filename_track"] == 53
    assert tracks_by_name["53_17 Doors.wav"]["t_num_val"] == "53"
    assert "17 doors" in tracks_by_name["53_17 Doors.wav"]["norm_stem"]

    assert tracks_by_name["07_18noayamachi.mp3"]["filename_track"] == 7
    assert tracks_by_name["07_18noayamachi.mp3"]["t_num_val"] == "7"
    assert "18noayamachi" in tracks_by_name["07_18noayamachi.mp3"]["norm_stem"]


def test_genuine_multidisc_compound_filenames_are_still_detected(tmp_path):
    file_names = [
        "01_001_OPENING.wav",
        "01_002_SELECT.wav",
        "02_001_OPENING.wav",
        "02_002_SELECT.wav",
    ]
    files = []
    for name in file_names:
        p = tmp_path / name
        p.write_bytes(b"dummy audio content")
        files.append(p)

    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract", return_value={}), \
         patch("sst.track_grouper.TrackManager.get_duration", return_value=120.0):
        records_by_group = TrackManager.build_file_records(files)

    all_tracks = [t for group in records_by_group.values() for t in group]
    tracks_by_name = {t["path"].name: t for t in all_tracks}

    assert tracks_by_name["01_001_OPENING.wav"]["disc"] == 1
    assert tracks_by_name["01_001_OPENING.wav"]["t_num_val"] == "1"

    assert tracks_by_name["01_002_SELECT.wav"]["disc"] == 1
    assert tracks_by_name["01_002_SELECT.wav"]["t_num_val"] == "2"

    assert tracks_by_name["02_001_OPENING.wav"]["disc"] == 2
    assert tracks_by_name["02_001_OPENING.wav"]["t_num_val"] == "1"

    assert tracks_by_name["02_002_SELECT.wav"]["disc"] == 2
    assert tracks_by_name["02_002_SELECT.wav"]["t_num_val"] == "2"


def test_mastering_bitrate_numbers_in_filename_prefix_are_ignored(tmp_path):
    file_names = [
        "PGRC OST 24 MASTER 01 Main Theme.wav",
        "PGRC OST 24 MASTER 02 Menu.wav",
        "PGRC OST 320 MASTER 01 Main Theme.mp3",
        "PGRC OST 320 MASTER 02 Menu.mp3",
    ]
    files = []
    for name in file_names:
        p = tmp_path / name
        p.write_bytes(b"dummy audio content")
        files.append(p)

    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract", return_value={}), \
         patch("sst.track_grouper.TrackManager.get_duration", return_value=120.0):
        records_by_group = TrackManager.build_file_records(files)

    all_tracks = [t for group in records_by_group.values() for t in group]
    tracks_by_name = {t["path"].name: t for t in all_tracks}

    assert tracks_by_name["PGRC OST 24 MASTER 01 Main Theme.wav"]["t_num_val"] == "1"
    assert tracks_by_name["PGRC OST 24 MASTER 02 Menu.wav"]["t_num_val"] == "2"
    assert tracks_by_name["PGRC OST 320 MASTER 01 Main Theme.mp3"]["t_num_val"] == "1"
    assert tracks_by_name["PGRC OST 320 MASTER 02 Menu.mp3"]["t_num_val"] == "2"


def test_initialize_album_context_total_discs_prefers_store_tracklist():
    steam_meta = SteamMetadata(
        app_id=1944840,
        name="Ghostwire: Tokyo Soundtrack",
        store_tracklist=[{"disc": 1, "number": str(i), "title": f"T{i}"} for i in range(1, 66)],
    )
    from sst.processing.album_context import initialize_album_context
    with patch("sst.track_grouper.TrackManager.list_audio_files", return_value=[Path("/dummy/track.wav")]), \
         patch("sst.track_grouper.TrackManager.build_file_records", return_value={(53, "17 doors"): [{"file_id": "f1"}]}):
        _, _, total_discs, _, _ = initialize_album_context(
            app_id=1944840,
            install_dir=Path("/dummy"),
            steam_meta=steam_meta,
            diag=lambda *args, **kwargs: None,
            llm=None,
            db=MagicMock(),
            build_execution_profile=MagicMock(),
            pre_scanned_files=[Path("/dummy/track.wav")],
        )
    assert total_discs == 1


def test_organizer_bypasses_phase2_when_unfilled_steam_slots_empty():
    from sst.llm.organizer import LLMOrganizer
    organizer = LLMOrganizer("dummy_key", "http://localhost")

    v_steam = {
        "tracks": [{"disc": 1, "n": 1, "t": "Track 1", "duration_ms": 1000}],
    }
    v_local = {
        "tracks": [
            {"local_key": [1, 1], "title": "Track 1", "disc": 1, "track_num": 1, "duration_ms": 1000, "file_ids": ["f1"]},
            {"local_key": [1, 2], "title": "Bonus Track", "disc": 1, "track_num": 2, "duration_ms": 1000, "file_ids": ["f2"]},
        ],
    }

    with patch.object(organizer, "_resolve_album_identity", return_value=({"identity_confidence": 100, "album_confidence": 100}, None)), \
         patch.object(organizer, "_run_differential_segments") as mock_diff:
        instructions, diag = organizer.align_slots(
            app_id=100,
            v_steam=v_steam,
            v_fingerprint=None,
            v_mbz_search=None,
            v_local=v_local,
        )
        mock_diff.assert_not_called()
    assert instructions is not None
    assert "1_1" in instructions
    assert "1_2" not in instructions


def test_assignment_validation_coherent_variants_with_same_track_num_and_duration():
    from sst.llm.assignment_validation import reject_contradictory_slot_assignments

    local_tracks = [
        {"local_key": (1, "いつかあの場所で"), "title": "いつかあの場所で", "track_num": 1, "duration_ms": 177200},
        {"local_key": (1, "murasaki_ost01"), "title": "murasaki_ost01", "track_num": 1, "duration_ms": 177100},
    ]
    full_ref_steam = [
        {"disc": 1, "number": "1", "title": "いつかあの場所で", "duration_ms": 177200}
    ]
    final_instructions = {
        "1_いつかあの場所で": {"matched_v_idx": 0, "reason": "SYSTEM: Matched"},
        "1_murasaki_ost01": {"matched_v_idx": 0, "reason": "SYSTEM: Matched"},
    }

    filtered, contradictions = reject_contradictory_slot_assignments(
        final_instructions, local_tracks, full_ref_steam
    )
    assert len(contradictions) == 0
    assert len(filtered) == 2


def test_validator_allows_intermediate_contradiction_when_outcome_is_fully_resolved():
    from sst.validator import ResultValidator

    steam_meta = SteamMetadata(
        app_id=461050,
        name="Murasaki Soundtrack",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Song 1"}],
    )
    tracks = [
        {
            "tags": {
                "disc_number": "1",
                "track_number": "1",
                "title": "Song 1",
                "artist": "Artist",
                "album": "Murasaki Soundtrack",
            },
            "path": Path("/out/01.aif"),
        }
    ]
    llm_log = {
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "confidence_reason": "ok",
        },
        "alignment_res": {
            "contradictory_slot_assignments": [{"matched_v_idx": 0, "rejected_track_ids": ["dummy"]}],
            "unassigned_files": [],
        },
    }

    status, message, score, data_q, reason = ResultValidator.validate(
        app_id=461050,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
        unassigned_manifest=[],
    )
    assert status == "archive"
    assert "LLM Contradictory Slot Assignments" not in reason


def test_unassigned_files_tagged_with_common_metadata_and_isolated(tmp_path):
    output = tmp_path / "output"
    source = tmp_path / "bonus.flac"
    source.write_bytes(b"dummy audio")

    class MockAudioTagger:
        def __init__(self):
            self.written_tags = {}

        def convert_and_limit(self, source_path, tier, subdir=""):
            target = output / subdir / f"{source_path.stem}.aif"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"converted aif")
            return target, False

        def write_tags(self, file_path, tag_map, artwork_path=None):
            self.written_tags[str(file_path)] = tag_map

    tagger = MockAudioTagger()
    candidate = {
        "path": source,
        "tier": "lossless",
        "candidate_type": "unassigned",
        "title": "Bonus Song",
    }
    common_meta = {
        "album": "Test Album",
        "artist": "Test Artist",
        "album_artist": "Test Artist",
        "year": "2024",
    }

    converted = _convert_review_candidates(
        tagger,
        output,
        [candidate],
        start_index=0,
        common_metadata=common_meta,
    )[0]

    assert converted["file_path"].startswith("unassigned/candidate_001")
    target_file = str(output / converted["file_path"])
    assert target_file in tagger.written_tags
    written = tagger.written_tags[target_file]
    assert written["album"] == "Test Album"
    assert written["artist"] == "Test Artist"
    assert "track_number" not in written
    assert "disc_number" not in written


def test_coherence_and_normalization_filter_prompt_placeholder_echoes():
    from sst.llm.normalization import normalize_track_mapping_result, build_slot_view
    from sst.llm.coherence import merge_track_instructions

    full_ref_steam = [
        {"disc": 1, "number": "1", "title": "T1"},
        {"disc": 1, "number": "2", "title": "T2"},
    ]
    track_res = {
        "slots": {
            "1": {"files": ["<FILE_ID>", "file_1"], "reason": "ok"},
            "2": {"files": ["FILE_ID_A"], "reason": "ok"},
        }
    }
    normalized = normalize_track_mapping_result(track_res, full_ref_steam=full_ref_steam)
    assert "<FILE_ID>" not in normalized["track_instructions"]
    assert "FILE_ID_A" not in normalized["track_instructions"]
    assert "file_1" in normalized["track_instructions"]

    slot_view = build_slot_view(track_res, local_tracks=[{"file_ids": ["file_1"]}])
    assert slot_view["slots"]["1"]["files"] == ["file_1"]
    assert slot_view["slots"]["2"]["files"] == []

    chunk_1 = [{"local_key": [1, 1], "file_ids": ["f1"]}]
    chunk_2 = [{"local_key": [1, 2], "file_ids": ["f2"]}]
    local_tracks = chunk_1 + chunk_2

    chunk_2_res = {
        "slots": {
            "1": {"files": ["f1"], "reason": "echo from chunk 1"},
            "2": {"files": ["f2"], "reason": "legit match"},
        }
    }
    merged = merge_track_instructions(
        chunk_2_res,
        local_tracks=local_tracks,
        chunk=chunk_2,
        global_res={"identity_confidence": 100},
        ref_fingerprint=[],
        full_ref_mbz_search=[],
        v_mbz_search=None,
        full_ref_steam=full_ref_steam,
        normalize_mapping_result=normalize_track_mapping_result,
    )
    # f1 is from chunk 1, so chunk 2's echo must be skipped
    assert "1_1" not in merged
    assert "1_2" in merged






