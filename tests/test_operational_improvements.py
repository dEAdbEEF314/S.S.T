"""
Tests for fix_0.5 operational improvements:
1. BONUS_OR_SE_ISOLATED review sub-status assignment when soundtrack slots are 100% satisfied.
2. Local appinfo.vdf PICS tracklist & credits fallback when Web API / Store page lacks structured data.
3. Batch report and notification badge rendering for review sub-status.
"""
from unittest.mock import MagicMock
import pytest

from sst.models import SteamMetadata
from sst.validator import ResultValidator
from sst.processing.package_metadata import build_album_summary_metadata
from sst.steam_web_api import SteamWebClient
from sst.batch_report import render_batch_row
from sst.processing.notifications import send_notifications
from sst.db import DatabaseManager


def test_bonus_or_se_isolated_sub_status_assigned():
    """Verify that an album with 100% adopted slots and unassigned bonus/SE gets BONUS_OR_SE_ISOLATED."""
    steam_meta = SteamMetadata(
        app_id=1299740,
        name="FlatOut 4 Soundtrack",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Track 1", "duration_s": "180"},
            {"disc": 1, "number": "2", "title": "Track 2", "duration_s": "200"},
            {"disc": 1, "number": "3", "title": "Track 3", "duration_s": "220"},
        ],
    )
    processed_tracks = [
        {"disc": 1, "number": "1", "tags": {"title": "Track 1", "track_number": "1", "disc_number": "1"}, "file_path": "/out/01.mp3"},
        {"disc": 1, "number": "2", "tags": {"title": "Track 2", "track_number": "2", "disc_number": "1"}, "file_path": "/out/02.mp3"},
        {"disc": 1, "number": "3", "tags": {"title": "Track 3", "track_number": "3", "disc_number": "1"}, "file_path": "/out/03.mp3"},
    ]
    unassigned = [
        {"file_id": 10, "path": "/src/engine_sound_01.wav", "reason": "bonus_or_se"},
        {"file_id": 11, "path": "/src/engine_sound_02.wav", "reason": "bonus_or_se"},
    ]
    llm_log = {
        "phase1_res": {
            "strategy": "STEAM_BASED",
            "album_confidence": 68,
            "mapping_confidence": 75,
            "data_quality": 65,
            "confidence_reason": "Good match but unassigned files present",
        },
        "diagnostics": {},
    }

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=1299740,
        tracks=processed_tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
        unassigned_manifest=unassigned,
    )

    assert status == "review"
    assert "Unassigned Files (2)" in message
    assert llm_log["diagnostics"].get("review_sub_status") == "BONUS_OR_SE_ISOLATED"

    # Package metadata integration
    summary = build_album_summary_metadata(
        app_id=1299740,
        steam_meta=steam_meta,
        status=status,
        processing_route="LLM_ONE_SHOT",
        message=message,
        score=score,
        quality=quality,
        mapping_confidence=75,
        archive_vs_review_ratio={"archive": 40, "review": 60},
        reason=reason,
        processed_at="2026-10-31T12:00:00",
        processed_tracks_meta=processed_tracks,
        final_duplicate_slot_count=0,
        llm_log=llm_log,
        all_files_count=5,
        adopted_file_count=3,
        unassigned_manifest=unassigned,
        artifact_issues=[],
        track_groups={},
        slot_variant_index={},
        io_retry_count=0,
        io_retry_logs=[],
        diagnostics=llm_log["diagnostics"],
    )

    assert summary["review_sub_status"] == "BONUS_OR_SE_ISOLATED"
    assert summary["audit"]["review_sub_status"] == "BONUS_OR_SE_ISOLATED"


@pytest.mark.parametrize(
    "fatal_scenario",
    [
        "audio_fail",
        "audio_warn",
        "missing_slot",
        "duplicate_slot",
        "track_zero",
        "official_title_mismatch",
        "artifact_issue",
    ],
)
def test_bonus_or_se_isolated_rejected_when_fatal_defect(fatal_scenario):
    """Ensure BONUS_OR_SE_ISOLATED is NOT given when genuine fatal errors exist."""
    steam_meta = SteamMetadata(
        app_id=999999,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Track 1", "duration_s": "180"},
            {"disc": 1, "number": "2", "title": "Track 2", "duration_s": "200"},
        ],
    )
    processed_tracks = [
        {"disc": 1, "number": "1", "tags": {"title": "Track 1", "track_number": "1", "disc_number": "1"}, "file_path": "/out/01.mp3"},
        {"disc": 1, "number": "2", "tags": {"title": "Track 2", "track_number": "2", "disc_number": "1"}, "file_path": "/out/02.mp3"},
    ]
    unassigned = [{"file_id": 99, "path": "/src/extra.wav"}]
    llm_log = {
        "phase1_res": {
            "strategy": "STEAM_BASED",
            "album_confidence": 70,
            "mapping_confidence": 80,
            "data_quality": 80,
            "confidence_reason": "testing",
        },
        "diagnostics": {},
    }

    audio_fail = (fatal_scenario == "audio_fail")
    audio_warn = (fatal_scenario == "audio_warn")

    if fatal_scenario == "missing_slot":
        processed_tracks = processed_tracks[:1]  # Only 1 adopted out of 2 expected
    elif fatal_scenario == "duplicate_slot":
        processed_tracks.append({"disc": 1, "number": "2", "tags": {"title": "Track 2 dup", "track_number": "2", "disc_number": "1"}, "file_path": "/out/02_dup.mp3"})
    elif fatal_scenario == "track_zero":
        processed_tracks[0]["tags"]["track_number"] = "0"
        processed_tracks[0]["number"] = "0"
    elif fatal_scenario == "official_title_mismatch":
        processed_tracks[0]["tags"]["title"] = "Track 2"  # Cross-slot collision

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=999999,
        tracks=processed_tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=audio_fail,
        audio_warn=audio_warn,
        audio_warned_tracks=["Track 1"] if audio_warn else None,
        unassigned_manifest=unassigned,
    )

    artifact_issues = ["zero byte file found"] if fatal_scenario == "artifact_issue" else []

    summary = build_album_summary_metadata(
        app_id=999999,
        steam_meta=steam_meta,
        status=status,
        processing_route="LLM_ONE_SHOT",
        message=message,
        score=score,
        quality=quality,
        mapping_confidence=80,
        archive_vs_review_ratio={"archive": 50, "review": 50},
        reason=reason,
        processed_at="2026-10-31T12:00:00",
        processed_tracks_meta=processed_tracks,
        final_duplicate_slot_count=1 if fatal_scenario == "duplicate_slot" else 0,
        llm_log=llm_log,
        all_files_count=3,
        adopted_file_count=len(processed_tracks),
        unassigned_manifest=unassigned,
        artifact_issues=artifact_issues,
        track_groups={},
        slot_variant_index={},
        io_retry_count=0,
        io_retry_logs=[],
        diagnostics=llm_log["diagnostics"],
    )

    assert summary["review_sub_status"] is None
    assert summary["audit"]["review_sub_status"] is None


def test_local_appinfo_pics_fallback_in_scanner(tmp_path):
    """Verify scanner extracts PICS tracks and credits from local appinfo without web lookup."""
    from sst.scanner import SteamScanner
    from sst.db import DatabaseManager

    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)

    # Mock steam install dir & library
    steam_install = tmp_path / "steam_install"
    steam_install.mkdir()
    lib_path = tmp_path / "steamlib"
    (lib_path / "steamapps").mkdir(parents=True)

    scanner = SteamScanner(
        install_path=str(steam_install),
        db=db,
        bridge_url="http://non-existent:8080/",
        library_path=str(lib_path),
        cache_path=str(tmp_path / "scout_cache.json"),
        tag_cache_path=str(tmp_path / "steam_tags.json"),
    )

    # Inject mock appinfo_dict with albummetadata
    scanner.appinfo_dict = {
        870530: {
            "appid": 870530,
            "common": {"name": "Warhammer 40k Soundtrack"},
            "extended": {"developer": "Proxy Studios", "publisher": "Slitherine Ltd."},
            "albummetadata": {
                "tracks": {
                    "0": {"discnumber": 1, "tracknumber": 1, "originalname": "BGM 1", "m": 3, "s": 30},
                    "1": {"discnumber": 1, "tracknumber": 2, "originalname": "Theme 2", "m": 4, "s": 15},
                },
                "metadata": {
                    "artist": {"english": "Dan Bewick"},
                    "composer": {"english": "Dan Bewick"},
                    "label": {"english": "Proxy Studios"},
                },
            },
        }
    }

    # Mock web_client.fetch_web_enrichment to return empty store tracklist
    scanner.web_client.fetch_web_enrichment = MagicMock(return_value={
        "store_tracklist": [],
        "store_tracklist_source": None,
        "store_credits": "",
    })

    meta = scanner._get_local_metadata(870530, force=True)

    assert len(meta["store_tracklist"]) == 2
    assert meta["store_tracklist"][0]["title"] == "BGM 1"
    assert meta["store_tracklist"][0]["source"] == "STEAM_PICS"
    assert meta["store_tracklist"][1]["title"] == "Theme 2"
    assert "Artist: Dan Bewick" in meta["store_credits"]
    assert "Composer: Dan Bewick" in meta["store_credits"]


def test_steam_web_api_fallback_to_local_album_meta(tmp_path):
    """Verify fetch_web_enrichment falls back to local_album_meta when bridge API fails."""
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)
    client = SteamWebClient(
        db=db,
        bridge_url="http://127.0.0.1:59999/",  # non-existent port
        max_retries=1,
        throttle_delay=0.0,
        retry_delay=0.0,
    )

    local_album_meta = {
        "tracks": {
            "0": {"discnumber": 1, "tracknumber": 1, "originalname": "Intro", "m": 1, "s": 23},
        },
        "metadata": {
            "artist": {"english": "Test Composer"},
        },
    }

    res = client.fetch_web_enrichment(123456, force=True, local_album_meta=local_album_meta)
    assert res is not None
    assert len(res["store_tracklist"]) == 1
    assert res["store_tracklist"][0]["title"] == "Intro"
    assert res["store_tracklist_source"] == "STEAM_PICS"
    assert "Artist: Test Composer" in res["store_credits"]

    # Verify persisted in database
    db_data = db.get_store_data(123456)
    assert db_data is not None
    assert len(db_data["tracklist"]) == 1
    assert db_data["tracklist"][0]["title"] == "Intro"


def test_batch_report_renders_bonus_se_badge():
    """Verify batch report table row renders Bonus/SE Isolated badge."""
    mock_result = MagicMock()
    mock_result.app_id = 1299740
    mock_result.album_name = "FlatOut 4 Soundtrack"
    mock_result.status = "review"
    mock_result.confidence_score = 68
    mock_result.message = "[Unassigned Files (12)]"
    mock_result.confidence_reason = "100% slots covered, extra files isolated"
    mock_result.metadata = {
        "diagnostics": {"primary_review_cause": "Unassigned Files (12)"},
        "audit": {
            "review_sub_status": "BONUS_OR_SE_ISOLATED",
            "steam_expected_slots": 24,
            "final_adopted_slots": 24,
            "unassigned_file_count": 12,
        },
    }

    row_html = render_batch_row(mock_result, escape=lambda s: str(s))
    assert "REVIEW (BONUS_OR_SE_ISOLATED)" in row_html
    assert "Bonus/SE Isolated" in row_html


def test_notifications_renders_bonus_se_sub_status():
    """Verify Discord notifications include review sub-status in title/status field."""
    notifier = MagicMock()
    llm_log = {
        "diagnostics": {"review_sub_status": "BONUS_OR_SE_ISOLATED"},
        "phase1_res": {"album_confidence": 70, "mapping_confidence": 75, "data_quality": 65},
    }
    markdown_output = send_notifications(
        notifier=notifier,
        app_id=1299740,
        name="FlatOut 4 Soundtrack",
        status="review",
        message="[Unassigned Files (12)]",
        score=70,
        reason="Clean bonus isolation",
        llm_log=llm_log,
        any_audio_failures=False,
        track_count=24,
        mbz_candidates=[],
    )
    notifier.notify_warning.assert_called_once()
    fields = notifier.notify_warning.call_args[0][2]
    status_field = next(f for f in fields if f["name"] == "Status")
    assert status_field["value"] == "**REVIEW (BONUS_OR_SE_ISOLATED)**"
    assert "**Status**: **REVIEW (BONUS_OR_SE_ISOLATED)**" in markdown_output
