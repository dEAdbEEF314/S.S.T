from unittest.mock import MagicMock
from sst.models import SteamMetadata
from sst.validator import ResultValidator
from sst.llm.organizer import LLMOrganizer
from sst.steam_web_api import SteamWebClient
from sst.report_generator import ReportGenerator
from sst.processor_support import send_notifications


def test_validator_zero_pad_normalization():
    """Steam側が'1'でタグ側が'01'でもSteam Slots Missing/Unexpectedにならないことを検証"""
    steam_meta = SteamMetadata(
        app_id=12345,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Track One"},
            {"disc": 1, "number": "2", "title": "Track Two"},
        ]
    )
    # タグ側のtrack_numberがゼロ埋め "01", "02"
    tracks = [
        {"tags": {"disc_number": "1", "track_number": "01", "title": "Track One"}, "title_source": "STEAM"},
        {"tags": {"disc_number": "1", "track_number": "02", "title": "Track Two"}, "title_source": "STEAM"},
    ]
    llm_log = {
        "fast_track": True,
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "strategy": "STEAM_BASED",
        }
    }

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=12345,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )

    assert status == "archive"
    assert "Steam Slots Missing" not in message
    assert "Steam Slots Unexpected" not in message


def test_validate_archive_artifacts_zero_pad_normalization(tmp_path):
    """_validate_archive_artifacts でSteamが'1'でタグが'01'でもSlot Mismatchにならないことを検証"""
    from sst.processor import LocalProcessor

    steam_meta = SteamMetadata(
        app_id=1568690,
        name="DJMAX Test",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Track 1"},
            {"disc": 1, "number": "2", "title": "Track 2"},
        ]
    )

    # 実ファイルを作成
    disc_dir = tmp_path / "disc_1"
    disc_dir.mkdir(parents=True, exist_ok=True)
    f1 = disc_dir / "01. Track 1.aif"
    f2 = disc_dir / "02. Track 2.aif"
    f1.write_bytes(b"dummy audio data 1")
    f2.write_bytes(b"dummy audio data 2")

    tracks = [
        {
            "file_path": "disc_1/01. Track 1.aif",
            "tags": {
                "disc_number": "1",
                "track_number": "01",
                "title": "Track 1",
                "artist": "Test Artist",
                "album_artist": "Test Dev",
            },
        },
        {
            "file_path": "disc_1/02. Track 2.aif",
            "tags": {
                "disc_number": "1",
                "track_number": "02",
                "title": "Track 2",
                "artist": "Test Artist",
                "album_artist": "Test Dev",
            },
        },
    ]

    issues = LocalProcessor._validate_archive_artifacts(
        app_id=1568690,
        artifact_dir=tmp_path,
        tracks=tracks,
        steam_meta=steam_meta,
    )

    assert "Archive Artifact Steam Slot Mismatch" not in issues
    assert issues == []


def test_organizer_slot_key_prefix_and_zero_pad():
    """LLMがプレフィックス付きキーやゼロ埋めを出力しても安全に解決されることを検証"""
    full_ref_steam = [
        {"v_idx": 0, "d": 1, "n": "1", "t": "First Track"},
        {"v_idx": 1, "d": 1, "n": "2", "t": "Second Track"},
        {"v_idx": 2, "d": 1, "n": "3", "t": "Third Track"},
    ]

    # 直接一致（ゼロ埋め "01" -> n="1"）
    assert LLMOrganizer._resolve_slot_key_to_v_idx("01", full_ref_steam) == 0
    assert LLMOrganizer._resolve_slot_key_to_v_idx("1", full_ref_steam) == 0

    # プレフィックス付き ("STEAM_SLOT_0" -> 0-indexed fallback v_idx=0)
    assert LLMOrganizer._resolve_slot_key_to_v_idx("STEAM_SLOT_0", full_ref_steam) == 0

    # プレフィックス付き ("STEAM_SLOT_1" -> direct match n="1" -> v_idx=0)
    assert LLMOrganizer._resolve_slot_key_to_v_idx("STEAM_SLOT_1", full_ref_steam) == 0
    assert LLMOrganizer._resolve_slot_key_to_v_idx("STEAM_SLOT_2", full_ref_steam) == 1

    # "slot_3", "Track 02" 等
    assert LLMOrganizer._resolve_slot_key_to_v_idx("slot_3", full_ref_steam) == 2
    assert LLMOrganizer._resolve_slot_key_to_v_idx("Track 02", full_ref_steam) == 1


def test_steam_pics_duration_parsing():
    """Steam PICS の m (分) と s (秒) から正しく合計秒数が算出されることを検証"""
    app_data = {
        "extended": {
            "albummetadata": {
                "tracks": {
                    "0": {"disc": "1", "track": "1", "m": "2", "s": "30", "name": "Song A"},
                    "1": {"disc": "1", "track": "2", "m": "0", "s": "45", "name": "Song B"},
                    "2": {"disc": "1", "track": "3", "s": "120", "name": "Song C"},
                }
            }
        }
    }
    album_meta = app_data["extended"]["albummetadata"]
    parsed = SteamWebClient.parse_pics_tracks(album_meta)
    assert len(parsed) == 3
    assert parsed[0]["duration_s"] == "150"  # 2 * 60 + 30
    assert parsed[1]["duration_s"] == "45"   # 0 * 60 + 45
    assert parsed[2]["duration_s"] == "120"  # 120


def test_audio_quality_warning_reporting():
    """微小な音声警告（Rice符号化異常等）でトラック番号付きReviewメッセージとdiagnosticsが生成されることを検証"""
    steam_meta = SteamMetadata(
        app_id=99999,
        name="Warning Test",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Track 1"},
            {"disc": 1, "number": "2", "title": "Track 2"},
        ]
    )
    tracks = [
        {"tags": {"disc_number": "1", "track_number": "1", "title": "Track 1"}, "title_source": "STEAM"},
        {"tags": {"disc_number": "1", "track_number": "2", "title": "Track 2"}, "title_source": "STEAM"},
    ]
    llm_log = {
        "fast_track": True,
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "strategy": "STEAM_BASED",
        }
    }

    # 音声警告あり
    status, message, score, quality, reason = ResultValidator.validate(
        app_id=99999,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=True,
        audio_warned_tracks=["Track 01"],
    )

    assert status == "review"
    assert "Audio quality warning (Tracks: Track 01)" in message
    assert llm_log["diagnostics"]["audio_quality_warnings"] is True
    assert llm_log["diagnostics"]["audio_warned_tracks"] == ["Track 01"]

    # HTMLレポートの検証
    html_report = ReportGenerator.generate_html_report(
        app_id=99999,
        steam_meta=steam_meta,
        status=status,
        message=message,
        score=score,
        reason=reason,
        processed_tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        localized_now_str="2026-09-04 12:00:00",
        priority_str="STEAM_STORE,STEAM_PICS",
        quality=quality,
    )
    assert "音声品質警告（本来Archive相当 / 微小異常あり: 1曲）" in html_report
    assert "Track 01" in html_report

    # Discord通知の検証
    notifier = MagicMock()
    send_notifications(
        notifier=notifier,
        app_id=99999,
        name="Warning Test",
        status=status,
        message=message,
        score=score,
        reason=reason,
        llm_log=llm_log,
        any_audio_failures=False,
        track_count=2,
        mbz_candidates=[],
    )
    assert notifier.notify_warning.called
    warning_args = notifier.notify_warning.call_args[0]
    fields = warning_args[2]
    field_names = [f["name"] for f in fields]
    assert any("音声品質警告（本来Archive相当 / 微小異常あり）" in fn for fn in field_names)
