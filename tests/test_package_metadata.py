from pathlib import Path

from sst.models import SteamMetadata
from sst.processing.package_metadata import (
    _build_field_provenance_audit,
    build_album_summary_metadata,
)
from sst.report_generator import ReportGenerator


def test_format_selection_audit_records_candidate_formats_and_detects_bad_adoption():
    metadata = build_album_summary_metadata(
        app_id=1,
        steam_meta=SteamMetadata(
            app_id=1,
            name="Synthetic OST",
            store_tracklist=[{"disc": 1, "number": "1", "title": "Theme"}],
        ),
        status="archive",
        processing_route="FAST_TRACK",
        message="Success",
        score=100,
        quality=100,
        mapping_confidence=100,
        archive_vs_review_ratio={"archive": 100, "review": 0},
        reason="Synthetic fixture",
        processed_at="2026-10-10T00:00:00+00:00",
        processed_tracks_meta=[
            {
                "slot_key": "1_1",
                "source_format": "mp3",
                "tier_rank": 3,
                "field_provenance": {
                    "title": "STEAM",
                    "artist": "STEAM_DEVELOPER",
                    "album": "STEAM",
                    "album_artist": "STEAM_DEVELOPER_PUBLISHER",
                    "year": "STEAM",
                    "track_number": "STEAM",
                    "disc_number": "STEAM",
                    "genre": "STEAM_GENRES",
                    "grouping": "STEAM",
                    "comment": ["EMBED", "STEAM"],
                    "composer": "STEAM_STORE_CREDITS",
                    "language": "CONFIG_USER_LANGUAGE",
                    "steam_appid": "STEAM_APP_IDENTITY",
                    "apic": "EMBED",
                },
            }
        ],
        final_duplicate_slot_count=0,
        llm_log={},
        all_files_count=2,
        adopted_file_count=1,
        unassigned_manifest=[],
        artifact_issues=[],
        track_groups={},
        slot_variant_index={
            (1, "1"): [
                {"format": "mp3", "path": Path("synthetic/theme.mp3")},
                {"format": "flac", "path": Path("synthetic/theme.flac")},
            ]
        },
        io_retry_count=0,
        io_retry_logs=[],
        diagnostics={},
    )

    format_audit = metadata["audit"]["format_selection"]
    assert format_audit["candidate_slot_count"] == 1
    assert format_audit["verified_slot_count"] == 0
    assert format_audit["mismatch_slot_count"] == 1
    assert format_audit["unverifiable_slot_count"] == 0
    assert format_audit["slots"][0] == {
        "slot_key": "1_1",
        "candidate_count": 2,
        "candidate_formats": [
            {"format": "flac", "count": 1, "priority_rank": 1},
            {"format": "mp3", "count": 1, "priority_rank": 8},
        ],
        "best_available_format": "flac",
        "selected_source_format": "mp3",
        "selection_matches_best": False,
    }
    assert "synthetic" not in repr(format_audit)
    html = ReportGenerator._render_format_selection_audit_html(format_audit)
    assert "入力形式と採用形式の監査" in html
    assert "flac x1, mp3 x1" in html
    assert "不一致" in html
    assert "synthetic" not in html
    provenance_audit = metadata["audit"]["field_provenance"]
    assert provenance_audit["fields"]["title"] == {"STEAM": 1}
    assert provenance_audit["fields"]["comment"] == {"EMBED+STEAM": 1}
    provenance_html = ReportGenerator._render_field_provenance_audit_html(provenance_audit)
    assert "タグフィールドのsource監査" in provenance_html
    assert "STEAM_STORE_CREDITS: 1" in provenance_html


def test_missing_field_source_is_counted_as_not_recorded():
    audit = _build_field_provenance_audit([{"tags": {"title": "Synthetic Title"}}])

    assert audit["fields"]["title"] == {"NOT_RECORDED": 1}
    assert audit["fields"]["apic"] == {"NOT_RECORDED": 1}