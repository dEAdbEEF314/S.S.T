import json
import zipfile
from pathlib import Path
from sst.models import SteamMetadata
from sst.report_generator import ReportGenerator


def test_unassigned_warning_with_app_1806720():
    zip_path = Path("output/review/1806720_Dead_Estate_Soundtrack.zip")
    if not zip_path.exists():
        return

    with zipfile.ZipFile(zip_path) as z:
        meta = json.loads(z.read("json/metadata.json"))
        llm_log = json.loads(z.read("json/llm_log.json"))

    steam_meta = SteamMetadata(
        app_id=1806720,
        name=meta.get("album_name", "Dead Estate Soundtrack"),
        store_tracklist=meta.get("steam_info", {}).get("store_tracklist", []),
    )

    html = ReportGenerator.generate_html_report(
        app_id=1806720,
        steam_meta=steam_meta,
        status="review",
        message="[Review: BONUS_OR_SE_ISOLATED]",
        score=85,
        reason="STEAM-based match with unassigned bonus files",
        processed_tracks=meta.get("tracks", []),
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり: 1件）" in html
    assert "MajorWipeout - Dead Estate- Assignment Anya OST - 02 Fend 4 Yourself.wav" in html
    assert "[Track 2: Fend 4 Yourself]" in html
    assert "ID: a448c48077b5e35c" in html
    assert "unassigned/candidate_001/MajorWipeout - Dead Estate- Assignment Anya OST - 02 Fend 4 Yourself.aif" in html
    assert "No matching Steam slot" in html
    # Ensure raw bare code list item does NOT exist
    assert "<li><code>a448c48077b5e35c</code></li>" not in html


def test_unassigned_warning_synthetic_review_candidates():
    steam_meta = SteamMetadata(app_id=999999, name="Synthetic OST", store_tracklist=[])
    llm_log = {
        "alignment_res": {"unassigned_files": ["bonus_fid_01"]},
        "diagnostics": {
            "review_candidates": [
                {
                    "candidate_type": "unassigned",
                    "original_filename": "bonus_theme.wav",
                    "title": "Bonus Stage Theme",
                    "track_number": "5",
                    "disc_number": "2",
                    "file_id": "bonus_fid_01",
                    "file_path": "unassigned/candidate_001/bonus_theme.aif",
                    "reason": "Not in official Steam tracklist",
                }
            ]
        },
    }

    html = ReportGenerator.generate_html_report(
        app_id=999999,
        steam_meta=steam_meta,
        status="review",
        message="Review",
        score=80,
        reason="Unassigned file",
        processed_tracks=[],
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり: 1件）" in html
    assert "bonus_theme.wav" in html
    assert "[Disc 2 Track 5: Bonus Stage Theme]" in html
    assert "ID: bonus_fid_01" in html
    assert "unassigned/candidate_001/bonus_theme.aif" in html
    assert "Not in official Steam tracklist" in html


def test_unassigned_warning_synthetic_local_signals_lookup():
    steam_meta = SteamMetadata(app_id=999999, name="Synthetic OST", store_tracklist=[])
    llm_log = {
        "alignment_res": {"unassigned_files": ["sig_fid_02"]},
        "diagnostics": {
            "review_candidates": [
                {
                    "candidate_type": "unassigned",
                    "original_filename": "secret_track.flac",
                    "file_id": "sig_fid_02",
                    "file_path": "unassigned/candidate_002/secret_track.flac",
                    "reason": "Bonus track",
                }
            ]
        },
    }
    alignment_inputs = {
        "LOCAL_SIGNALS": {
            "tracks": [
                {
                    "file_ids": ["sig_fid_02"],
                    "title": "Secret Boss Battle",
                    "track_num": 9,
                    "disc": 1,
                }
            ]
        }
    }

    html = ReportGenerator.generate_html_report(
        app_id=999999,
        steam_meta=steam_meta,
        status="review",
        message="Review",
        score=80,
        reason="Unassigned file",
        processed_tracks=[],
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
        alignment_inputs=alignment_inputs,
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり: 1件）" in html
    assert "secret_track.flac" in html
    assert "[Track 9: Secret Boss Battle]" in html
    assert "ID: sig_fid_02" in html


def test_unassigned_warning_synthetic_filename_fallback():
    steam_meta = SteamMetadata(app_id=999999, name="Synthetic OST", store_tracklist=[])
    llm_log = {
        "alignment_res": {"unassigned_files": ["raw_fid_03"]},
        "diagnostics": {
            "review_candidates": [
                {
                    "candidate_type": "unassigned",
                    "original_filename": "Game OST - 12 Hidden Ending.mp3",
                    "file_id": "raw_fid_03",
                    "file_path": "unassigned/candidate_003/Game OST - 12 Hidden Ending.mp3",
                    "reason": "Hidden track",
                }
            ]
        },
    }

    html = ReportGenerator.generate_html_report(
        app_id=999999,
        steam_meta=steam_meta,
        status="review",
        message="Review",
        score=80,
        reason="Unassigned file",
        processed_tracks=[],
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり: 1件）" in html
    assert "Game OST - 12 Hidden Ending.mp3" in html
    assert "[Track 12: Hidden Ending]" in html
    assert "ID: raw_fid_03" in html


def test_unassigned_warning_empty_when_no_unassigned():
    steam_meta = SteamMetadata(app_id=999999, name="Clean Album", store_tracklist=[])
    llm_log = {
        "alignment_res": {"unassigned_files": []},
        "diagnostics": {"review_candidates": []},
    }

    html = ReportGenerator.generate_html_report(
        app_id=999999,
        steam_meta=steam_meta,
        status="archive",
        message="Clean Archive",
        score=100,
        reason="Clean",
        processed_tracks=[],
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり" not in html
    assert "以下のローカルファイルはどのSteamスロットにも割り当てられなかったため" not in html


def test_unassigned_warning_ignores_slot_conflict():
    steam_meta = SteamMetadata(app_id=999999, name="Conflict Album", store_tracklist=[])
    llm_log = {
        "alignment_res": {"unassigned_files": []},
        "diagnostics": {
            "review_candidates": [
                {
                    "candidate_type": "slot_conflict",
                    "original_filename": "duplicate_take.wav",
                    "file_id": "conflict_01",
                    "slot_key": "1_1",
                    "reason": "Duplicate take",
                }
            ]
        },
    }

    html = ReportGenerator.generate_html_report(
        app_id=999999,
        steam_meta=steam_meta,
        status="review",
        message="Review",
        score=80,
        reason="Conflict",
        processed_tracks=[],
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-11-03 18:00:00",
        priority_str="STEAM_FIRST",
    )

    assert "⚠️ Steamスロット充足（余剰未割当ファイルあり" not in html

