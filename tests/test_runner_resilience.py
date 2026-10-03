from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

from sst.models import LocalProcessResult
from sst.runner import JobRunner
from sst.track_grouper import TrackManager

def test_list_audio_files_oserror_handling(tmp_path):
    # Test that list_audio_files gracefully handles OSError
    with patch.object(Path, "rglob", side_effect=OSError(112, "Host is down")):
        files = TrackManager.list_audio_files(tmp_path)
        assert files == []

def test_job_runner_resilience_on_host_down_error(tmp_path):
    config = MagicMock()
    config.llm_backend = "TEST"
    config.max_parallel_albums = 2

    processor = MagicMock()
    # Simulate an album process raising OSError(112, "Host is down")
    processor.process_album.side_effect = OSError(112, "Host is down")

    console = Console(quiet=True)
    runner = JobRunner(config=config, processor=processor, console=console)

    soundtracks = [
        {
            "app_id": 100,
            "name": "Host Down OST",
            "install_dir": str(tmp_path / "host_down"),
            "developer": "Dev",
            "publisher": "Pub",
            "release_date": "2020",
            "genres": ["Action"],
            "store_tracklist": []
        },
        {
            "app_id": 101,
            "name": "Normal OST",
            "install_dir": str(tmp_path / "normal"),
            "developer": "Dev",
            "publisher": "Pub",
            "release_date": "2020",
            "genres": ["Action"],
            "store_tracklist": []
        }
    ]

    # Run should complete without raising an unhandled exception
    results = runner.run(soundtracks)

    assert len(results) == 2
    for r in results:
        assert r.status == "error"
        assert "Host is down" in r.message or "Process returned None" in r.message or r.message != ""


def test_job_runner_reuses_scheduling_scan_for_progress_count(tmp_path):
    config = MagicMock()
    config.llm_backend = "TEST"
    config.max_parallel_albums = 1
    config.llm_limit_rpm = 10

    processor = MagicMock()
    processor.process_album.return_value = LocalProcessResult(
        app_id=100,
        status="skip",
        album_name="Test OST",
        message="No work required",
    )
    soundtrack = {
        "app_id": 100,
        "name": "Test OST",
        "install_dir": str(tmp_path),
        "store_tracklist": [],
    }
    runner = JobRunner(config=config, processor=processor, console=Console(quiet=True))

    with patch.object(TrackManager, "list_audio_files", return_value=[tmp_path / "01.flac"]) as scan:
        results = runner.run([soundtrack])

    assert scan.call_count == 1
    assert len(results) == 1


def test_copy_with_retry_records_structured_attempts(tmp_path):
    """提案5: copy_with_retry が試行の構造化記録を返す（成功時）。"""
    from sst.processor_tracks import copy_with_retry

    src = tmp_path / "src.flac"
    src.write_bytes(b"audio")
    dst = tmp_path / "dst.flac"

    log = copy_with_retry(src, dst)

    assert log["final_state"] == "success"
    assert log["retried"] is False
    assert log["attempts"][0]["success"] is True
    assert dst.exists()


def test_copy_with_retry_records_failure_and_does_not_silently_succeed(tmp_path):
    """提案5: 最終コピー失敗は final_state=failed を返し、呼び出し側で検出される。"""
    from sst.processor_tracks import copy_with_retry

    src = tmp_path / "missing.flac"
    dst = tmp_path / "dst.flac"

    log = copy_with_retry(src, dst, retries=2, initial_delay=0.0)

    assert log["final_state"] == "failed"
    assert log["retried"] is True
    assert len(log["attempts"]) == 2
    assert all(not a["success"] for a in log["attempts"])
    assert dst.exists() is False


def test_process_single_track_defers_copy_failure_without_running_ffmpeg(tmp_path):
    from sst.models import SteamMetadata
    from sst.processor_tracks import process_single_track

    source = tmp_path / "shared" / "01_theme.mp3"
    variant = {"file_id": "file-1", "path": source, "format": "mp3", "meta": {}}
    track_groups = {(1, "theme"): [variant]}
    tagger = MagicMock()
    notifier = MagicMock()
    retry_log = {
        "source": source.name,
        "attempts": [{"attempt": 1, "error_type": "OSError", "error": "I/O error", "success": False}],
        "final_state": "failed",
        "retried": False,
    }

    with patch("sst.processor_tracks.MetadataBuilder.build_tag_map", return_value={"disc_number": "1"}), patch(
        "sst.processor_tracks.copy_with_retry", return_value=retry_log
    ):
        result = process_single_track(
            app_id=100,
            steam_meta_name="Synthetic OST",
            track_data=((1, "theme"), {"path": source, "tier": "mp3", "tier_rank": 3}),
            final_metadata={"1_theme": {"matched_v_idx": 0}},
            config=MagicMock(user_language_639_2="eng"),
            steam_meta=SteamMetadata(
                app_id=100,
                name="Synthetic OST",
                store_tracklist=[{"disc": 1, "number": "1", "title": "Theme"}],
            ),
            mbz_candidates=[],
            track_sources={},
            global_identity={},
            total_discs=1,
            buffer_dir=tmp_path / "buffer",
            tagger=tagger,
            track_groups=track_groups,
            slot_variant_index={(1, "1"): [variant]},
            track_to_slot_index={"1_theme": (1, "1")},
            album_artwork=None,
            notifier=notifier,
            defer_copy_failure=True,
        )

    assert result["copy_pending"] is True
    assert result["failed"] is False
    assert result["io_retry_log"] == retry_log
    tagger.convert_and_limit.assert_not_called()
    tagger.write_tags.assert_not_called()


def test_deferred_copy_finalizers_wait_once_and_are_not_requeued():
    from threading import Lock

    from sst.processor import LocalProcessor

    processor = LocalProcessor.__new__(LocalProcessor)
    processor._deferred_copy_lock = Lock()
    processor._deferred_copy_finalizers = {
        100: lambda: LocalProcessResult(
            app_id=100,
            status="review",
            album_name="Synthetic OST",
            message="Deferred copy recovery exhausted",
        )
    }

    with patch("sst.processor.time.sleep") as sleep:
        results = processor.resolve_deferred_copy_retries(600)

    sleep.assert_called_once_with(600)
    assert results[100].status == "review"
    assert processor.resolve_deferred_copy_retries(600) == {}


def test_runner_resolves_deferred_copies_after_all_normal_albums(tmp_path, monkeypatch):
    events = []

    class DeferredProcessor:
        def process_album(self, app_id, install_dir, steam_meta, **kwargs):
            events.append(("normal", app_id, kwargs.get("defer_copy_retries")))
            return LocalProcessResult(
                app_id=app_id,
                status="deferred" if app_id == 100 else "archive",
                album_name=steam_meta.name,
                message="Pending" if app_id == 100 else "Done",
            )

        def resolve_deferred_copy_retries(self, delay_seconds):
            events.append(("resolve", delay_seconds))
            return {
                100: LocalProcessResult(
                    app_id=100,
                    status="review",
                    album_name="Pending OST",
                    message="Deferred Copy Recovery Exhausted (1)",
                )
            }

    config = MagicMock()
    config.llm_backend = "TEST"
    config.max_parallel_albums = 2
    config.llm_limit_rpm = 10
    config.sst_deferred_copy_delay_seconds = 37
    processor = DeferredProcessor()
    soundtracks = [
        {"app_id": 100, "name": "Pending OST", "install_dir": str(tmp_path), "store_tracklist": []},
        {"app_id": 101, "name": "Normal OST", "install_dir": str(tmp_path), "store_tracklist": []},
    ]
    monkeypatch.setattr(TrackManager, "list_audio_files", lambda _path: [])

    results = JobRunner(config=config, processor=processor, console=Console(quiet=True)).run(soundtracks)

    assert [event[0] for event in events].count("normal") == 2
    assert events[-1] == ("resolve", 37)
    assert all(event[2] is True for event in events if event[0] == "normal")
    assert {result.app_id: result.status for result in results} == {100: "review", 101: "archive"}


def test_process_album_defers_package_finalization_until_copy_retry(tmp_path):
    from datetime import datetime
    from threading import Lock
    from types import SimpleNamespace

    from sst.processor import LocalProcessor
    from sst.models import SteamMetadata

    processor = LocalProcessor.__new__(LocalProcessor)
    processor.config = SimpleNamespace(sst_output_dir=str(tmp_path / "output"))
    processor.working_dir = tmp_path / "work"
    processor.preserve_working_files = True
    processor.notifier = MagicMock()
    processor.db = MagicMock()
    processor._deferred_copy_lock = Lock()
    processor._deferred_copy_finalizers = {}
    processor._get_localized_now = MagicMock(return_value=datetime.now().astimezone())
    processor._init_album_context = MagicMock(
        return_value=([tmp_path / "01_theme.mp3"], {}, 1, 1, None)
    )
    processor._execute_alignment_flow = MagicMock(
        return_value=(
            {"1_theme": {"matched_v_idx": 0}},
            {"phase1_res": {"global_tags": {}}},
            [],
            {(1, "1"): []},
            {"1_theme": (1, "1")},
            "FAST_TRACK",
            {},
            {},
            None,
            None,
            None,
            None,
        )
    )
    deferred_track = ((1, "theme"), {"path": tmp_path / "01_theme.mp3", "tier_rank": 3})
    first_io_log = {
        "track_id": "1_theme",
        "slot_key": "1_1",
        "source": "01_theme.mp3",
        "attempts": [{"attempt": 1, "error_type": "OSError", "error": "I/O error", "success": False}],
        "final_state": "failed",
        "retried": False,
    }
    retry_io_log = {
        "track_id": "1_theme",
        "slot_key": "1_1",
        "source": "01_theme.mp3",
        "attempts": [{"attempt": 1, "error_type": None, "error": None, "success": True}],
        "final_state": "success",
        "retried": False,
    }
    recovered_track = {
        "file_path": "disc_1/01_theme.mp3",
        "slot_key": "1_1",
        "tier_rank": 3,
        "tags": {"disc_number": "1", "track_number": "1", "title": "Theme"},
    }
    processor._encode_and_tag_tracks = MagicMock(side_effect=[
        ([], False, False, [], [], 0, [first_io_log], 1, 1, [deferred_track], None),
        ([recovered_track], False, False, [], [], 0, [retry_io_log], 1, 1, [], None),
    ])
    expected = LocalProcessResult(
        app_id=100,
        status="archive",
        album_name="Synthetic OST",
        message="Recovered",
    )
    processor._finalize_album_package = MagicMock(return_value=expected)

    pending = processor.process_album(
        100,
        tmp_path,
        SteamMetadata(app_id=100, name="Synthetic OST", store_tracklist=[]),
        defer_copy_retries=True,
    )

    assert pending.status == "deferred"
    processor._finalize_album_package.assert_not_called()
    resolved = processor.resolve_deferred_copy_retries(0)

    assert resolved[100] is expected
    assert processor._encode_and_tag_tracks.call_count == 2
    processor._finalize_album_package.assert_called_once()
    assert processor._finalize_album_package.call_args.args[2] == [recovered_track]
    assert first_io_log["recovered_after_defer"] is True
