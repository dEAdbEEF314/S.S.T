import importlib.util
import json
import sqlite3
from datetime import datetime
from pathlib import Path


REPORT_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".agents/skills/sst-post-batch-investigator/scripts/generate_post_batch_report.py"
)
SPEC = importlib.util.spec_from_file_location("post_batch_report", REPORT_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def _track(number: str, title: str, slot_key: str = "") -> dict:
    return {
        "file_path": f"synthetic_{number}.aif",
        "slot_key": slot_key,
        "source": "STEAM",
        "title_source": "STEAM",
        "tags": {
            "disc_number": "1",
            "track_number": number,
            "title": title,
        },
    }


def _archive_meta(steam_slots: list[dict], tracks: list[dict]) -> dict:
    return {
        "steam_info": {"store_tracklist": steam_slots},
        "tracks": tracks,
    }


def test_archive_integrity_detects_balanced_missing_and_unexpected_slots():
    meta = _archive_meta(
        [
            {"disc": "1", "number": "1", "title": "Song One"},
            {"disc": "1", "number": "2", "title": "Song Two"},
        ],
        [
            _track("1", "Song One", "1:1"),
            _track("3", "Unexpected Song", "1:3"),
        ],
    )
    tracks = meta["tracks"]
    integrity = REPORT._integrity_snapshot(meta, tracks)

    assert len(tracks) == integrity["expected_slot_count"]
    assert integrity["missing_slots"] == [("1", "2")]
    assert integrity["unexpected_slots"] == [("1", "3")]
    issues = REPORT._archive_integrity_issues(meta, tracks, integrity)
    assert any("Steam slot欠落" in issue for issue in issues)
    assert any("Steam外slot" in issue for issue in issues)


def test_archive_integrity_flags_track_zero_and_only_anomalous_unknown():
    steam_slots = [
        {"disc": "1", "number": "1", "title": "Song One"},
        {"disc": "1", "number": "2", "title": "Unknown (Unused)"},
    ]
    tracks = [
        _track("0", "Unknown", "1:0"),
        _track("2", "Unknown (Unused)", "1:2"),
    ]
    meta = _archive_meta(steam_slots, tracks)
    integrity = REPORT._integrity_snapshot(meta, tracks)

    assert integrity["track_zero_count"] == 1
    assert integrity["legitimate_unknown_title_count"] == 1
    assert integrity["anomalous_unknown_title_count"] == 1
    issues = REPORT._archive_integrity_issues(meta, tracks, integrity)
    assert any("Track#0" in issue for issue in issues)
    assert any("Steam根拠のないUnknownタイトル" in issue for issue in issues)


def test_official_steam_unknown_is_not_an_archive_integrity_issue():
    meta = _archive_meta(
        [{"disc": "1", "number": "1", "title": "Unknown (Unused)"}],
        [_track("1", "Unknown (Unused)", "1:1")],
    )
    integrity = REPORT._integrity_snapshot(meta, meta["tracks"])

    assert integrity["legitimate_unknown_title_count"] == 1
    assert integrity["anomalous_unknown_title_count"] == 0
    assert REPORT._archive_integrity_issues(meta, meta["tracks"], integrity) == []


def test_io_error_evidence_requires_matching_app_and_recent_timestamp():
    item = {
        "app_id": 100,
        "meta": {"processed_at": "2026-01-01T00:30:00+00:00"},
    }
    matching = (100, datetime.fromisoformat("2025-12-31T23:00:00+00:00"))
    stale = (100, datetime.fromisoformat("2025-12-31T17:00:00+00:00"))
    future = (100, datetime.fromisoformat("2026-01-01T00:31:00+00:00"))
    other_app = (101, matching[1])

    assert REPORT._has_matching_io_error(item, [matching])
    assert not REPORT._has_matching_io_error(item, [stale])
    assert not REPORT._has_matching_io_error(item, [future])
    assert not REPORT._has_matching_io_error(item, [other_app])


def _insert_result(connection, app_id: int, status: str, metadata: dict) -> None:
    connection.execute(
        "INSERT INTO processed_albums VALUES (?, ?, ?, ?)",
        (app_id, f"Synthetic Album {app_id}", status, json.dumps(metadata)),
    )


def test_report_uses_explicit_route_and_multilabel_review_causes(tmp_path):
    db_path = tmp_path / "state.db"
    output_dir = tmp_path / "report"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE processed_albums (
                app_id INTEGER,
                album_name TEXT,
                status TEXT,
                metadata_json TEXT
            )
            """
        )
        _insert_result(
            connection,
            101,
            "archive",
            {
                "processing_route": "FAST_TRACK",
                "strategy": "STEAM_BASED",
                **_archive_meta(
                    [{"disc": "1", "number": "1", "title": "Song"}],
                    [_track("1", "Song", "1:1")],
                ),
            },
        )
        _insert_result(
            connection,
            102,
            "archive",
            {
                "processing_route": "LLM_CHUNKED",
                "strategy": "FAST_TRACK",
                "message": "Deterministic Fast-Track",
                **_archive_meta(
                    [{"disc": "1", "number": "1", "title": "Song"}],
                    [_track("1", "Song", "1:1")],
                ),
            },
        )
        review_metadata = [
            (
                201,
                {
                    "message": "[Unassigned Files (1), Duplicates (1)]",
                    "unassigned_files": [{"file_id": "synthetic-file"}],
                    "steam_info": {"store_tracklist": [{"disc": "1", "number": "1", "title": "Song"}]},
                    "tracks": [_track("1", "Song", "1:1"), _track("1", "Song", "1:1")],
                },
            ),
            (202, {"message": "CRITICAL: Audio Source Error", "diagnostics": {"audio_source_failures": True}}),
            (203, {"message": "N/A (Early Review)", "diagnostics": {"review_phase": "EARLY_REVIEW"}}),
            (204, {"message": "Low Confidence", "processed_at": "2026-01-01T00:01:00"}),
            (205, {"message": "Other review"}),
        ]
        for app_id, metadata in review_metadata:
            _insert_result(connection, app_id, "review", metadata)
    (log_dir / "synthetic.log").write_text(
        "2026-01-01 00:00:00,000 - sst.processor - ERROR - [204] Permission denied for synthetic fixture\n",
        encoding="utf-8",
    )

    REPORT.analyze_and_generate_report(db_path, output_dir, log_dir)
    report = (output_dir / "batch_analysis_report.html").read_text(encoding="utf-8")

    assert "Fast-Track 実行route件数</div>" in report
    assert '<div class="kpi-value info">1 ' in report
    assert "Reviewアルバム: 5件。複数原因に該当: 1件。" in report
    assert "Steam構造・slot不整合 (1件)" in report
    assert "未割当ファイル / alignment残差 (1件)" in report
    assert "物理I/O / 音声ソース障害 (2件)" in report
    assert "早期Review / Steam情報不足 (1件)" in report
    assert "信頼度不足・その他 (1件)" in report
