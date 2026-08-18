from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

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
