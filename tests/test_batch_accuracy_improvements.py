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


def test_bilingual_and_same_format_variant_consolidation_without_false_unassigned(tmp_path):
    """fix_0.2 指示書 01: 多言語（中国語WAV＋英語MP3）および同一フォーマット重複（WAVx2）が同一スロットに統合され、ロスレス優先・公式タイトル維持で unassigned 0件になること。"""
    wav_cn = tmp_path / "01_主界面.wav"
    mp3_en = tmp_path / "01_Main Menu.mp3"
    wav_dup1 = tmp_path / "WAV" / "02_Battle Theme.wav"
    wav_dup2 = tmp_path / "Root" / "02_Battle Theme.wav"
    wav_dup1.parent.mkdir()
    wav_dup2.parent.mkdir()
    for p in (wav_cn, mp3_en, wav_dup1, wav_dup2):
        p.write_bytes(b"audio")

    steam_meta = SteamMetadata(
        app_id=4131280,
        name="Bilingual & Same-Format Test OST",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Main Menu"},
            {"disc": 1, "number": "2", "title": "Battle Theme"},
        ],
    )
    track_groups = {
        (1, "主界面::wav1"): [
            {"file_id": "wav1", "format": "wav", "duration": 95.0, "norm_stem": "主界面", "t_num_val": "1", "path": wav_cn}
        ],
        (1, "Main Menu::mp31"): [
            {"file_id": "mp31", "format": "mp3", "duration": 95.4, "norm_stem": "main menu", "t_num_val": "1", "path": mp3_en}
        ],
        (1, "Battle Theme::wav2a"): [
            {"file_id": "wav2a", "format": "wav", "duration": 140.0, "norm_stem": "battle theme", "t_num_val": "2", "path": wav_dup1}
        ],
        (1, "Battle Theme::wav2b"): [
            {"file_id": "wav2b", "format": "wav", "duration": 140.0, "norm_stem": "battle theme", "t_num_val": "2", "path": wav_dup2}
        ],
    }
    final_metadata = {
        "1_Main Menu::mp31": {"matched_v_idx": 0, "override_track": "1"},
        "1_Battle Theme::wav2a": {"matched_v_idx": 1, "override_track": "2"},
    }

    slot_variants, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)
    assert len(slot_variants[(1, "1")]) == 2
    assert len(slot_variants[(1, "2")]) == 2

    adopted = adopt_best_file_per_slot(track_groups, slot_variants, track_to_slot)
    assert len(adopted) == 2
    # Slot 1 must adopt the lossless WAV even though its local title was Chinese
    slot_1_adopted = next(v for v in adopted.values() if v["slot_key"] == (1, "1"))
    assert slot_1_adopted["path"] == wav_cn
    assert slot_1_adopted["tier"] == "lossless"

    unassigned = select_best_unassigned_files(
        track_groups, final_metadata, slot_variant_index=slot_variants, track_to_slot_index=track_to_slot
    )
    conflicts = select_slot_conflict_candidates(track_groups, slot_variants, adopted)
    assert unassigned == []
    assert conflicts == []


def test_duplicate_mappings_anchor_protection_and_numeric_qualifier_guards():
    """fix_0.2 指示書 02: resolve_duplicate_mappings が確定アンカーを追い出さず、数値・バージョン修飾語矛盾への誤マッチを防止する。"""
    from sst.processing.duplicate_mappings import resolve_duplicate_mappings

    steam_meta = SteamMetadata(
        app_id=2943720,
        name="Anchor Protection OST",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "00001-01000"},
            {"disc": 1, "number": "2", "title": "01001-02000"},
            {"disc": 1, "number": "3", "title": "Ending (Short Ver.)"},
            {"disc": 1, "number": "4", "title": "Ending (Long Ver.)"},
        ],
    )
    track_groups = {
        (1, "00001-01000::f1"): [{"file_id": "f1", "format": "mp3", "duration": 60.0, "t_num_val": "1", "norm_stem": "1 1000"}],
        (1, "01001-02000::f2"): [{"file_id": "f2", "format": "mp3", "duration": 60.0, "t_num_val": "2", "norm_stem": "1001 2000"}],
        (1, "Ending (Short Ver.)::f3"): [{"file_id": "f3", "format": "mp3", "duration": 90.0, "t_num_val": "3", "norm_stem": "ending short ver"}],
        (1, "Ending (Long Ver.)::f4"): [{"file_id": "f4", "format": "mp3", "duration": 180.0, "t_num_val": "4", "norm_stem": "ending long ver"}],
    }
    # Suppose both Ending (Short Ver.) and Ending (Long Ver.) were mapped to v_idx=2 (Slot #3)
    final_metadata = {
        "1_00001-01000::f1": {"matched_v_idx": 0, "override_track": "1"},
        "1_01001-02000::f2": {"matched_v_idx": 0, "override_track": "1"},
        "1_Ending (Short Ver.)::f3": {"matched_v_idx": 2, "override_track": "3"},
        "1_Ending (Long Ver.)::f4": {"matched_v_idx": 2, "override_track": "3"},
    }

    resolve_duplicate_mappings(2943720, final_metadata, steam_meta, track_groups)

    assert final_metadata["1_00001-01000::f1"]["matched_v_idx"] == 0
    assert final_metadata["1_01001-02000::f2"]["matched_v_idx"] == 1
    assert final_metadata["1_Ending (Short Ver.)::f3"]["matched_v_idx"] == 2
    assert final_metadata["1_Ending (Long Ver.)::f4"]["matched_v_idx"] == 3


def test_prematch_norm_stem_unnumbered_and_coherent_format_variants():
    """fix_0.2 指示書 03: norm_stem 参照・番号なし厳密タイトル一致・同一スロット複数フォーマットの非衝突化を検証。"""
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.normalization import resolve_slot_key_to_v_idx

    full_ref_steam = [
        {"v_idx": 0, "d": 1, "n": "1", "t": "Solar Wind by ArtistA", "dur": 120},
        {"v_idx": 1, "d": 1, "n": "2", "t": "Moonlight Sonata", "dur": 180},
    ]
    local_tracks = [
        # Track 1 has localized embedded title but matching norm_stem, plus a second format variant
        {
            "local_key": (1, "太陽風::wav"),
            "disc": 1,
            "track_num": "1",
            "title": "太陽風",
            "norm_stem": "solar wind",
            "duration_ms": 120000,
            "file_ids": ["f1_wav"],
        },
        {
            "local_key": (1, "Solar Wind::mp3"),
            "disc": 1,
            "track_num": "1",
            "title": "Solar Wind",
            "norm_stem": "solar wind",
            "duration_ms": 120500,
            "file_ids": ["f1_mp3"],
        },
        # Track 2 has no track_num (unnumbered filename) but unique exact title match
        {
            "local_key": (1, "Moonlight Sonata::flac"),
            "disc": 1,
            "track_num": None,
            "title": "Moonlight Sonata",
            "norm_stem": "moonlight sonata",
            "duration_ms": 180000,
            "file_ids": ["f2_flac"],
        },
    ]

    pm_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    assert pm_map["f1_wav"].is_deterministic is True
    assert pm_map["f1_mp3"].is_deterministic is True
    assert pm_map["f2_flac"].is_deterministic is True
    assert pm_map["f2_flac"].target_v_idx == 1

    det_instr, resolved_v, unmatched_local, unfilled_steam = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        pm_map,
        {"global_tags": {}},
        resolve_slot_key=resolve_slot_key_to_v_idx,
    )
    assert resolved_v == {0, 1}
    assert unmatched_local == []
    assert unfilled_steam == []
    assert det_instr["1_太陽風::wav"]["matched_v_idx"] == 0
    assert det_instr["1_Solar Wind::mp3"]["matched_v_idx"] == 0
    assert det_instr["1_Moonlight Sonata::flac"]["matched_v_idx"] == 1


def test_two_pass_unassigned_reconciliation_prevents_substring_slot_theft():
    """fix_0.2 指示書 03: reconcile_deterministic_unassigned_slots が Pass 1 (完全一致) を Pass 2 (部分一致) より優先し、'Menu' が 'Main Menu' スロットを横取りしない。"""
    steam_meta = SteamMetadata(
        app_id=990001,
        name="Two Pass Reconciliation OST",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Main Menu (Extended)"},
            {"disc": 1, "number": "2", "title": "Main Menu"},
        ],
    )
    track_groups = {
        # Appears first in dict order, would substring-match Slot 2 ("Main Menu") if single-pass!
        (1, "Main Menu::ext"): [
            {"file_id": "f_ext", "t_num_val": "1", "format": "mp3", "norm_stem": "main menu"}
        ],
        # Exact match for Slot 2 ("Main Menu")
        (1, "Main Menu::exact"): [
            {"file_id": "f_exact", "t_num_val": "2", "format": "mp3", "norm_stem": "main menu"}
        ],
    }
    final_metadata = {}

    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata=final_metadata,
        track_groups=track_groups,
        steam_meta=steam_meta,
        global_identity={},
    )
    assert len(reconciled) == 2
    assert final_metadata["1_Main Menu::exact"]["matched_v_idx"] == 1
    assert final_metadata["1_Main Menu::ext"]["matched_v_idx"] == 0


def test_phase2_partial_slot_resolution_and_contradiction_multi_format_retention():
    """fix_0.2 指示書 04: 部分リスト unfilled_steam_slots に対する相対インデックス暴発防止・複合キー解決・confidence=0除外、および reject_contradictory_slot_assignments の複数フォーマット保持を検証。"""
    from sst.llm.normalization import resolve_slot_key_to_v_idx, normalize_track_mapping_result
    from sst.llm.assignment_validation import reject_contradictory_slot_assignments

    # Partial unfilled_steam_slots (e.g. slots 1..13 were already resolved in Prematch)
    unfilled_steam_slots = [
        {"v_idx": 13, "d": 1, "n": "14", "t": "Stage 14"},
        {"v_idx": 25, "d": 2, "n": "2", "t": "Disc 2 Track 2"},
    ]
    # Relative key "1" must NOT resolve to v_idx=13 on a partial list!
    assert resolve_slot_key_to_v_idx("1", unfilled_steam_slots) is None
    # Explicit track number "14" resolves to v_idx=13
    assert resolve_slot_key_to_v_idx("14", unfilled_steam_slots) == 13
    # Composite key "2_2" resolves to v_idx=25
    assert resolve_slot_key_to_v_idx("2_2", unfilled_steam_slots) == 25

    # Confidence 0 / "0" slot with "No matching STEAM slot" must be ignored
    norm_res = normalize_track_mapping_result(
        {
            "slots": {
                "0": {"files": ["f_unmatched"], "confidence": 0.0, "reason": "No matching STEAM slot"},
                "2_2": {"files": ["f_d2t2"], "confidence": 0.95, "reason": "matched"},
            },
            "unassigned_files": [],
        },
        unfilled_steam_slots,
    )
    assert "f_unmatched" not in norm_res["track_instructions"]
    assert norm_res["track_instructions"]["f_d2t2"]["matched_v_idx"] == 25
    assert norm_res["track_instructions"]["f_d2t2"]["override_disc"] == "2"
    assert norm_res["track_instructions"]["f_d2t2"]["override_track"] == "2"

    # reject_contradictory_slot_assignments retains both WAV and MP3 of the valid song while rejecting a 3rd contradictory song
    full_ref_steam = [{"v_idx": 0, "d": 1, "n": "1", "t": "Opening Theme"}]
    local_tracks = [
        {"local_key": (1, "Opening Theme::wav"), "title": "Opening Theme", "duration_ms": 100000, "track_num": "1"},
        {"local_key": (1, "Opening Theme::mp3"), "title": "Opening Theme", "duration_ms": 100400, "track_num": "1"},
        {"local_key": (1, "Unrelated Bonus::mp3"), "title": "Unrelated Bonus", "duration_ms": 45000, "track_num": "99"},
    ]
    final_instructions = {
        "1_Opening Theme::wav": {"matched_v_idx": 0, "reason": "LLM match"},
        "1_Opening Theme::mp3": {"matched_v_idx": 0, "reason": "LLM match"},
        "1_Unrelated Bonus::mp3": {"matched_v_idx": 0, "reason": "LLM hallucination"},
    }
    filtered, contradictions = reject_contradictory_slot_assignments(
        final_instructions, local_tracks, full_ref_steam
    )
    assert "1_Opening Theme::wav" in filtered
    assert "1_Opening Theme::mp3" in filtered
    assert "1_Unrelated Bonus::mp3" not in filtered
    assert len(contradictions) == 1
    assert contradictions[0]["rejected_track_ids"] == ["1_Unrelated Bonus::mp3"]


def test_reject_contradictory_slot_assignments_retains_bilingual_format_pair_matching_slot_number_and_duration():
    from sst.llm.assignment_validation import reject_contradictory_slot_assignments

    # Steam Slot 1 has Japanese title, 68s (AppID 336870 model)
    full_ref_steam = [{"v_idx": 0, "d": 1, "n": 1, "t": "迫る闇のテーマ", "dur": 68}]
    local_tracks = [
        {
            "local_key": (1, "f1_flac"),
            "d": 1,
            "track_num": 1,
            "title": "01 The Approaching Darkness",
            "duration_ms": 68000,
            "ext": ".flac",
        },
        {
            "local_key": (1, "f1_mp3"),
            "d": 1,
            "track_num": 1,
            "title": "01 The Approaching Darkness",
            "duration_ms": 68000,
            "ext": ".mp3",
        },
        {
            "local_key": (1, "f9_mp3"),
            "d": 1,
            "track_num": 9,
            "title": "09 Subtle Darkness",
            "duration_ms": 108000,
            "ext": ".mp3",
        },
    ]
    final_instructions = {
        "1_f1_flac": {"matched_v_idx": 0, "reason": "chunk 1"},
        "1_f1_mp3": {"matched_v_idx": 0, "reason": "chunk 1"},
        "1_f9_mp3": {"matched_v_idx": 0, "reason": "chunk 2 misalign"},
    }
    filtered, contradictions = reject_contradictory_slot_assignments(
        final_instructions, local_tracks, full_ref_steam
    )
    assert "1_f1_flac" in filtered
    assert "1_f1_mp3" in filtered
    assert "1_f9_mp3" not in filtered
    assert len(contradictions) == 1
    assert contradictions[0]["rejected_track_ids"] == ["1_f9_mp3"]


def test_titles_are_compatible_handles_japanese_particle_diff_and_parenthetical_note():
    from sst.llm.assignment_validation import titles_are_compatible

    # AppID 630380 model: Japanese title particle difference (は vs が) and parenthetical subtitle
    assert titles_are_compatible(
        "かくてゲートは開かれる（エンディングBGM）", "かくてゲートが開かれる"
    )
    assert titles_are_compatible(
        "かくてゲートが開かれる", "かくてゲートは開かれる（エンディングBGM）"
    )

    # Different number tokens must be rejected
    assert not titles_are_compatible("Stage 1", "Stage 2")
    assert not titles_are_compatible("Track 01", "Track 02")


def test_normalize_title_strips_acute_accent_apostrophe_before_nfkc():
    from sst.track_grouper import TrackManager

    # AppID 802640 model: acute accent (´ U+00B4) used as apostrophe
    norm_local = TrackManager.normalize_title("24 - Karl´s End")
    norm_steam = TrackManager.normalize_title("Karl's End", strip_track_prefix=False)
    assert norm_local == "karls end"
    assert norm_steam == "karls end"
    assert norm_local == norm_steam


def test_build_file_records_does_not_extract_track_number_from_alphanumeric_underscore_title():
    from sst.track_grouper import TrackManager
    from sst.llm.prematch import resolve_prematch_signals

    # AppID 1851920 model: radio1_1.mp3, radio1_8.mp3, radio2_14.mp3
    files = [
        Path("/dummy/radio1_1.mp3"),
        Path("/dummy/radio1_8.mp3"),
        Path("/dummy/radio2_14.mp3"),
    ]
    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract", return_value={}):
        with patch.object(TrackManager, "get_duration", return_value=60.0):
            records = TrackManager.build_file_records(files)

    local_tracks = []
    for (d, stem), variants in records.items():
        v = variants[0]
        assert v.get("t_num_val") is None, f"Expected t_num_val to be None, got {v.get('t_num_val')}"
        assert v.get("filename_track_val") is None
        local_tracks.append({
            "local_key": (d, stem),
            "file_ids": [v["file_id"]],
            "track_num": None,
            "filename_track": None,
            "title": v["path"].stem,
            "norm_stem": v.get("norm_stem", ""),
            "disc": d,
            "duration_ms": 60000,
        })

    # Steam slots: Slot 67 "radio1_1", Slot 68 "radio1_8", Slot 69 "radio2_14"
    full_ref_steam = [
        {"v_idx": 66, "d": 1, "n": "67", "t": "radio1_1", "dur": 60},
        {"v_idx": 67, "d": 1, "n": "68", "t": "radio1_8", "dur": 60},
        {"v_idx": 68, "d": 1, "n": "69", "t": "radio2_14", "dur": 60},
    ]
    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    for lt in local_tracks:
        fid = lt["file_ids"][0]
        assert prematch_map[fid].is_deterministic is True
        assert prematch_map[fid].target_v_idx is not None


def test_prematch_matches_continuous_single_folder_numbering_against_multidisc_steam_slots():
    from sst.llm.prematch import resolve_prematch_signals

    # AppID 1879310 model: Steam has Disc 1 (1..19) and Disc 2 (1..13, 1st track is "Technology Crisis")
    full_ref_steam = [
        {"v_idx": idx, "d": 1, "n": str(idx + 1), "t": f"Disc 1 Track {idx + 1}", "dur": 120}
        for idx in range(19)
    ]
    # Disc 2 track 1 (v_idx=19, n=1, t="Technology Crisis")
    full_ref_steam.append({
        "v_idx": 19,
        "d": 2,
        "n": "1",
        "t": "Technology Crisis",
        "dur": 150,
    })

    # Local lossless WAV from single folder: disc=1, track_num=20, title="20 Technology Crisis"
    local_tracks = [
        {
            "local_key": (1, "technology crisis"),
            "file_ids": ["fid_wav_20"],
            "track_num": 20,
            "filename_track": 20,
            "title": "Technology Crisis",
            "norm_stem": "technology crisis",
            "disc": 1,
            "duration_ms": 150000,
        }
    ]
    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    assert "fid_wav_20" in prematch_map
    assert prematch_map["fid_wav_20"].is_deterministic is True
    assert prematch_map["fid_wav_20"].target_v_idx == 19
    assert prematch_map["fid_wav_20"].deterministic_steam_slot == 1


def test_parse_pics_tracks_splits_corrupted_csv_newline_originalname():
    from sst.steam_web_api import SteamWebClient

    # AppID 1299740 model: Corrupted CSV with newline inside originalname
    album_meta = {
        "tracks": {
            "79": {
                "discnumber": "4",
                "tracknumber": "45",
                "originalname": 'Atterissage,,,0:00,\n4,46,"Brake',
                "m": "2",
                "s": "49",
            }
        }
    }
    parsed = SteamWebClient.parse_pics_tracks(album_meta)
    assert len(parsed) == 2
    assert parsed[0]["disc"] == 4
    assert parsed[0]["number"] == "45"
    assert parsed[0]["title"] == "Atterissage"
    assert parsed[0]["duration_s"] == "169"

    assert parsed[1]["disc"] == 4
    assert parsed[1]["number"] == "46"
    assert parsed[1]["title"] == "Brake"
    assert parsed[1]["duration_s"] == "169"


def test_prematch_resolves_zero_indexed_local_files_with_parenthetical_location_subtitles():
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.organizer import LLMOrganizer

    # AppID 4206020 model: 8 tracks (Steam 1-based, Local 0-based with parenthetical notes)
    steam_titles = [
        "Rebel",
        "The Final Stand",
        "Emerald Blue",
        "Midnight Flight",
        "Neon City",
        "Pursuit",
        "Confrontation",
        "Faint Of Heart",
    ]
    full_ref_steam = [
        {"v_idx": idx, "d": 1, "n": str(idx + 1), "t": title, "dur": 120}
        for idx, title in enumerate(steam_titles)
    ]

    local_filenames = [
        (0, "0. REBEL"),
        (1, "1. THE FINAL STAND (New Tokyo)"),
        (2, "2. EMERALD BLUE (Tokyo Tower)"),
        (3, "3. MIDNIGHT FLIGHT (Airspace)"),
        (4, "4. NEON CITY (Downtown)"),
        (5, "5. PURSUIT (Highway)"),
        (6, "6. CONFRONTATION (Roof)"),
        (7, "7. FAINT OF HEART (End)"),
    ]
    local_tracks = []
    for idx, (t_num, name) in enumerate(local_filenames):
        local_tracks.append({
            "local_key": (1, name.lower()),
            "file_ids": [f"fid_{idx}"],
            "track_num": t_num if t_num > 0 else None,
            "filename_track": t_num if t_num > 0 else None,
            "title": name,
            "norm_stem": TrackManager.normalize_title(name),
            "disc": 1,
            "duration_ms": 120000,
        })

    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    (
        det_instructions,
        resolved_v_indices,
        unmatched,
        unfilled,
    ) = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        prematch_map,
        {"global_tags": {}},
        resolve_slot_key=LLMOrganizer._resolve_slot_key_to_v_idx,
    )

    # All 8 tracks must be deterministically prematched to v_idx 0..7
    assert len(resolved_v_indices) == 8
    assert resolved_v_indices == set(range(8))
    assert len(unmatched) == 0
    assert len(unfilled) == 0


def test_prematch_resolves_literal_numbered_steam_titles_with_skipped_slot_number():
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.organizer import LLMOrganizer

    # AppID 2943720 model: Steam slots have literal 00_, 01_ with slot n=2 skipped
    steam_slots_data = [
        (0, 1, "00_OMOHIDE LOOP"),
        (1, 3, "01_SHIKATANAKATTA NO TSUMI"),
        (2, 4, "02_SHIKATANAKATTA NO TSUMI_OPPY"),
        (3, 5, "03_SHIKATANAKATTA NO TSUMI_orgel"),
    ]
    full_ref_steam = [
        {"v_idx": v_idx, "d": 1, "n": str(n), "t": title, "dur": 100}
        for v_idx, n, title in steam_slots_data
    ]

    local_files_data = [
        (0, 0, "00_OMOHIDE LOOP"),
        (1, 1, "01_SHIKATANAKATTA NO TSUMI"),
        (2, 2, "02_SHIKATANAKATTA NO TSUMI_OPPY"),
        (3, 3, "03_SHIKATANAKATTA NO TSUMI_orgel"),
    ]
    local_tracks = []
    for fid_idx, t_num, title in local_files_data:
        local_tracks.append({
            "local_key": (1, title.lower()),
            "file_ids": [f"fid_{fid_idx}"],
            "track_num": t_num if t_num > 0 else None,
            "filename_track": t_num if t_num > 0 else None,
            "title": title,
            "norm_stem": TrackManager.normalize_title(title),
            "disc": 1,
            "duration_ms": 100000,
        })

    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    (
        det_instructions,
        resolved_v_indices,
        unmatched,
        unfilled,
    ) = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        prematch_map,
        {"global_tags": {}},
        resolve_slot_key=LLMOrganizer._resolve_slot_key_to_v_idx,
    )

    assert len(resolved_v_indices) == 4
    assert resolved_v_indices == {0, 1, 2, 3}
    # 03_..._orgel must match v_idx=3 (Slot 5), NOT v_idx=1 (Slot 3)
    assert prematch_map["fid_3"].target_v_idx == 3


def test_prematch_resolves_unnumbered_filenames_with_offset_embedded_track_numbers():
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.organizer import LLMOrganizer

    # AppID 3994280 / 942070 model: Unnumbered filenames with offset tag numbers
    full_ref_steam = [
        {"v_idx": 0, "d": 1, "n": "1", "t": "Rainless", "dur": 180},
        {"v_idx": 1, "d": 1, "n": "2", "t": "It's No Problem", "dur": 200},
    ]
    # Local files have tag track_num=5 and 10 (offset from 1, 2), but exact titles and duration
    local_tracks = [
        {
            "local_key": (1, "rainless"),
            "file_ids": ["fid_rain"],
            "track_num": 5,
            "filename_track": None,
            "title": "Rainless",
            "norm_stem": "rainless",
            "disc": 1,
            "duration_ms": 180000,
        },
        {
            "local_key": (1, "it_s no problem"),
            "file_ids": ["fid_prob"],
            "track_num": 10,
            "filename_track": None,
            "title": "It_s No Problem",
            "norm_stem": "it s no problem",
            "disc": 1,
            "duration_ms": 200000,
        },
    ]

    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    (
        det_instructions,
        resolved_v_indices,
        unmatched,
        unfilled,
    ) = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        prematch_map,
        {"global_tags": {}},
        resolve_slot_key=LLMOrganizer._resolve_slot_key_to_v_idx,
    )

    assert len(resolved_v_indices) == 2
    assert resolved_v_indices == {0, 1}
    assert prematch_map["fid_rain"].target_v_idx == 0
    assert prematch_map["fid_prob"].target_v_idx == 1


def test_prematch_and_variant_consolidation_handles_me_prefix_unused_tag_and_duplicate_dungeon_titles():
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.organizer import LLMOrganizer
    from sst.processor_support import build_slot_variant_index, adopt_best_file_per_slot

    # AppID 1167720 model: Duplicate Dungeon titles, ME prefix, (unused) subtitle
    steam_slots_data = [
        (0, 20, "Dungeon - Artificial", 116),
        (1, 21, "Dungeon - Artificial", 134),
        (2, 22, "Dungeon - Artificial", 129),
        (3, 30, "ME 01 - Quest", 8),
        (4, 34, "Battle - Mirai 02 (unused)", 95),
    ]
    full_ref_steam = [
        {"v_idx": v_idx, "d": 1, "n": str(n), "t": title, "dur": dur}
        for v_idx, n, title, dur in steam_slots_data
    ]

    local_specs = [
        (20, "20 - Dungeon Artifical 1", "Dungeon - Artificial", 116),
        (21, "21 - Dungeon Artificial 2", "Dungeon - Artificial", 134),
        (22, "22 - Dungeon Artificial 3", "Dungeon - Artificial", 129),
        (30, "30 - Quest", "ME 01 - Quest", 8),
        (34, "34 - Battle Mirai 02", "Battle - Mirai 02 (unused)", 95),
    ]
    local_tracks = []
    track_groups = {}
    for t_num, stem, tag_title, dur in local_specs:
        fid_wav = f"fid_wav_{t_num}"
        fid_mp3 = f"fid_mp3_{t_num}"
        # Untagged WAV
        local_tracks.append({
            "local_key": (1, f"{stem}::wav"),
            "file_ids": [fid_wav],
            "track_num": t_num,
            "filename_track": t_num,
            "title": stem,
            "norm_stem": TrackManager.normalize_title(stem),
            "disc": 1,
            "ext": ".wav",
            "duration_ms": dur * 1000,
        })
        # Tagged MP3
        local_tracks.append({
            "local_key": (1, f"{stem}::mp3"),
            "file_ids": [fid_mp3],
            "track_num": t_num,
            "filename_track": t_num,
            "title": tag_title,
            "norm_stem": TrackManager.normalize_title(stem),
            "disc": 1,
            "ext": ".mp3",
            "duration_ms": dur * 1000,
        })
        track_groups[(1, f"{stem}::wav")] = [{
            "file_id": fid_wav,
            "format": "wav",
            "duration": float(dur),
            "norm_stem": TrackManager.normalize_title(stem),
            "t_num_val": str(t_num),
            "path": Path(f"/dummy/{stem}.wav"),
        }]
        track_groups[(1, f"{stem}::mp3")] = [{
            "file_id": fid_mp3,
            "format": "mp3",
            "duration": float(dur),
            "norm_stem": TrackManager.normalize_title(stem),
            "t_num_val": str(t_num),
            "path": Path(f"/dummy/{stem}.mp3"),
        }]

    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    (
        det_instructions,
        resolved_v_indices,
        unmatched,
        unfilled,
    ) = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        prematch_map,
        {"global_tags": {}},
        resolve_slot_key=LLMOrganizer._resolve_slot_key_to_v_idx,
    )

    # All 5 slots must be resolved deterministically
    assert len(resolved_v_indices) == 5
    assert resolved_v_indices == {0, 1, 2, 3, 4}
    assert len(unmatched) == 0

    # Build slot variants index and verify lossless WAV is adopted
    steam_meta = SteamMetadata(
        app_id=1167720,
        name="Artifact Adventure Gaiden DX",
        store_tracklist=[
            {"disc": 1, "number": str(n), "title": title, "duration_s": dur}
            for _, n, title, dur in steam_slots_data
        ],
    )
    final_meta = {
        tid: {"matched_v_idx": info["matched_v_idx"], "override_track": info["override_track"]}
        for tid, info in det_instructions.items()
    }

    slot_variants, track_to_slot = build_slot_variant_index(
        final_meta, track_groups, steam_meta
    )
    adopted = adopt_best_file_per_slot(track_groups, slot_variants, track_to_slot)
    # Each of the 5 slots must have lossless WAV adopted
    assert len(adopted) == 5
    for record_key, best_file in adopted.items():
        assert best_file["path"].suffix == ".wav", f"Expected wav for {record_key}, got {best_file['path']}"


def test_reconcile_deterministic_unassigned_slots_pass3_resolves_bilingual_and_abbreviated_slots_by_number_and_duration():
    from sst.processing.unassigned import reconcile_deterministic_unassigned_slots

    # AppID 2260070 model: 13 slots total. Slots 1..10 assigned, slots 11, 12, 13 missing.
    store_tracklist = [
        {"disc": 1, "number": str(i), "title": f"Song {i}", "duration_s": 100}
        for i in range(1, 11)
    ]
    store_tracklist.extend([
        {"disc": 1, "number": "11", "title": "《送别》中年安玲版", "duration_s": 117},
        {"disc": 1, "number": "12", "title": "《送别》少年安玲版", "duration_s": 117},
        {"disc": 1, "number": "13", "title": "《送别》科迪版", "duration_s": 112},
    ])
    steam_meta = SteamMetadata(
        app_id=2260070,
        name="Undying",
        store_tracklist=store_tracklist,
    )

    final_metadata = {
        f"1_song_{i}": {"matched_v_idx": i - 1, "override_track": str(i)}
        for i in range(1, 11)
    }

    track_groups = {}
    for i in range(1, 11):
        track_groups[(1, f"song_{i}")] = [{"file_id": f"fid_{i}", "format": "flac", "duration": 100.0, "t_num_val": str(i)}]

    # Unassigned tracks 11, 12, 13 with English titles
    unassigned_data = [
        (11, "11 Farewell By Anling", 117.1),
        (12, "12 Farewell By Young Anling", 117.1),
        (13, "13 Farewell By Cody", 112.1),
    ]
    for t_num, title, dur in unassigned_data:
        key = (1, title.lower())
        track_groups[key] = [
            {"file_id": f"fid_{t_num}_flac", "format": "flac", "duration": dur, "t_num_val": str(t_num)},
            {"file_id": f"fid_{t_num}_mp3", "format": "mp3", "duration": dur, "t_num_val": str(t_num)},
        ]

    reconciled = reconcile_deterministic_unassigned_slots(
        final_metadata,
        track_groups,
        steam_meta,
        {"canonical_album_artist": "Test Artist"},
    )

    # Pass 3 must reconcile all 3 missing slots
    assert len(reconciled) == 3
    reconciled_slots = {r["steam_slot"] for r in reconciled}
    assert reconciled_slots == {"11", "12", "13"}
    for r in reconciled:
        assert r["rule"] == "structural_number_and_duration_match"


def test_validator_detects_cross_slot_mismatch_with_parenthetical_location_subtitles():
    from sst.validator import ResultValidator
    from sst.models import SteamMetadata

    steam_meta = SteamMetadata(
        app_id=4206020,
        name="Emerald Blue Soundtrack",
        store_tracklist=[
            {"disc": 1, "number": "2", "title": "The Final Stand", "duration_s": 150},
            {"disc": 1, "number": "8", "title": "Faint Of Heart", "duration_s": 200},
        ],
    )
    album_result = {
        "status": "archive",
        "tracks": [
            {
                "file_path": "disc_1/02 The Final Stand.mp3",
                "original_filename": "7. FAINT OF HEART (End).mp3",
                "clean_title": "FAINT OF HEART (End)",
                "original_embedded_title": "",
                "duration_s": 200.0,
                "tags": {
                    "disc_number": "1/1",
                    "track_number": "2/2",
                    "title": "The Final Stand",
                },
            },
            {
                "file_path": "disc_1/08 Faint Of Heart.mp3",
                "original_filename": "1. THE FINAL STAND (New Tokyo).mp3",
                "clean_title": "THE FINAL STAND (New Tokyo)",
                "original_embedded_title": "",
                "duration_s": 150.0,
                "tags": {
                    "disc_number": "1/1",
                    "track_number": "8/2",
                    "title": "Faint Of Heart",
                },
            },
        ],
    }
    llm_log = {"phase1_res": {"album_confidence": 100, "mapping_confidence": 100}}
    status, message, score, data_q, reason = ResultValidator.validate(
        app_id=4206020,
        tracks=album_result["tracks"],
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )
    assert status == "review"
    assert "Official Title Mismatch (2)" in message


def test_validator_and_prematch_detect_duplicate_audio_with_conflicting_embedded_title_and_filename():
    from sst.llm.prematch import resolve_prematch_signals, extract_deterministic_prematches
    from sst.llm.organizer import LLMOrganizer
    from sst.validator import ResultValidator
    from sst.models import SteamMetadata

    # Steam slots: 1_11 = "Time to Vent" (262s), 1_12 = "Time to Leave" (120s)
    full_ref_steam = [
        {"v_idx": i, "d": 1, "n": str(i + 1), "t": f"Track {i + 1}", "dur": 100.0}
        for i in range(10)
    ] + [
        {"v_idx": 10, "d": 1, "n": "11", "t": "Time to Vent", "dur": 262.0},
        {"v_idx": 11, "d": 1, "n": "12", "t": "Time to Leave", "dur": 120.0},
    ]
    # Local files: both have embedded title "Time to Vent" and duration 262.7s
    local_tracks = [
        {
            "local_key": (1, "11. Time to Vent::mp3"),
            "file_ids": ["fid_11_vent"],
            "track_num": 11,
            "filename_track": 11,
            "title": "Time to Vent",
            "norm_stem": TrackManager.normalize_title("11. Time to Vent"),
            "disc": 1,
            "ext": ".mp3",
            "duration_ms": 262700,
        },
        {
            "local_key": (1, "11 - Desktop - Time to Leave::mp3"),
            "file_ids": ["fid_11_leave"],
            "track_num": 11,
            "filename_track": 11,
            "title": "Time to Vent",  # Embedded title is conflictingly "Time to Vent"
            "norm_stem": TrackManager.normalize_title("11 - Desktop - Time to Leave"),
            "disc": 1,
            "ext": ".mp3",
            "duration_ms": 262700,
        },
    ]

    prematch_map = resolve_prematch_signals(local_tracks, full_ref_steam, [], [])
    (
        det_instructions,
        resolved_v_indices,
        unmatched,
        unfilled,
    ) = extract_deterministic_prematches(
        local_tracks,
        full_ref_steam,
        prematch_map,
        {"global_tags": {}},
        resolve_slot_key=LLMOrganizer._resolve_slot_key_to_v_idx,
    )

    # Slot 11 (v_idx=10) should resolve ONLY "fid_11_vent", and exclude conflicting "fid_11_leave"
    assert 10 in resolved_v_indices
    vent_track_id = "1_11. Time to Vent::mp3"
    assert vent_track_id in det_instructions
    assert det_instructions[vent_track_id]["matched_v_idx"] == 10
    leave_track_id = "1_11 - Desktop - Time to Leave::mp3"
    assert leave_track_id not in det_instructions

    # And if 11 - Desktop - Time to Leave is mistakenly put into Slot 12 in ResultValidator:
    steam_meta = SteamMetadata(
        app_id=1832420,
        name="Happy's Humble Burger Farm OST",
        store_tracklist=[
            {"disc": 1, "number": "11", "title": "Time to Vent", "duration_s": 262},
            {"disc": 1, "number": "12", "title": "Time to Leave", "duration_s": 120},
        ],
    )
    album_result = {
        "status": "archive",
        "tracks": [
            {
                "file_path": "disc_1/11 Time to Vent.mp3",
                "original_filename": "11. Time to Vent.mp3",
                "clean_title": "Time to Vent",
                "original_embedded_title": "Time to Vent",
                "duration_s": 262.7,
                "tags": {
                    "disc_number": "1/1",
                    "track_number": "11/25",
                    "title": "Time to Vent",
                },
            },
            {
                "file_path": "disc_1/12 Time to Leave.mp3",
                "original_filename": "11 - Desktop - Time to Leave.mp3",
                "clean_title": "Time to Leave",
                "original_embedded_title": "Time to Vent",  # Duplicate conflicting audio
                "duration_s": 262.7,
                "tags": {
                    "disc_number": "1/1",
                    "track_number": "12/25",
                    "title": "Time to Leave",
                },
            },
        ],
    }
    llm_log = {"phase1_res": {"album_confidence": 100, "mapping_confidence": 100}}
    status, message, score, data_q, reason = ResultValidator.validate(
        app_id=1832420,
        tracks=album_result["tracks"],
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )
    assert status == "review"
    assert "Official Title Mismatch" in message

