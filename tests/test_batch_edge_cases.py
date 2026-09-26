from pathlib import Path
import logging
from unittest.mock import MagicMock, call, patch

from sst.processor import LocalProcessor
from sst.processor_support import (
    adopt_best_file_per_slot,
    build_slot_variant_index,
    resolve_duplicate_mappings,
)
from sst.steam_web_api import SteamWebClient
from sst.track_grouper import TrackManager
from sst.models import SteamMetadata


def test_parse_text_tracklist_requires_contiguous_numbered_lines():
    description = """
    Track list:<br>
    01. Re-Boot (OP DEMO)<br>
    02 Iron Attack (STAGE 1)<br>
    03. Cornered! (BOSS 1)<br>
    """

    tracks = SteamWebClient._parse_text_tracklist(description)

    assert [track["number"] for track in tracks] == ["01", "02", "03"]
    assert tracks[1]["title"] == "Iron Attack (STAGE 1)"


def test_parse_text_tracklist_rejects_unstructured_numbered_prose():
    description = "Install the game.\n1. First step\n3. Third step"

    assert SteamWebClient._parse_text_tracklist(description) == []


def test_steam_metadata_preserves_tracklist_source():
    metadata = SteamMetadata(
        app_id=1040700,
        name="Devil Engine",
        store_tracklist_source="STEAM_TEXT_TRACKLIST",
    )

    assert metadata.store_tracklist_source == "STEAM_TEXT_TRACKLIST"


def test_store_api_debug_log_classifies_http_200_failure_without_final_backoff(caplog):
    app_id = 424242
    db = MagicMock()
    db.get_store_data.return_value = None
    session = MagicMock()

    unsuccessful_store_response = MagicMock(status_code=200)
    unsuccessful_store_response.json.return_value = {str(app_id): {"success": False}}
    pics_response = MagicMock(status_code=200)
    pics_response.json.return_value = {
        "data": {str(app_id): {"albummetadata": {}}}
    }
    session.get.side_effect = [
        unsuccessful_store_response,
        unsuccessful_store_response,
        unsuccessful_store_response,
        pics_response,
    ]

    client = SteamWebClient(db, "http://bridge/", language="english")
    with patch("sst.steam_web_api.requests.Session", return_value=session), patch(
        "sst.steam_web_api.time.sleep"
    ) as sleep, patch("random.random", return_value=0.5), caplog.at_level(
        logging.DEBUG, logger="sst.steam_web_api"
    ):
        result = client.fetch_web_enrichment(app_id)

    assert result is not None
    assert session.get.call_count == 4
    assert sleep.call_args_list == [call(2.5), call(2), call(4)]
    tier1_logs = [record.getMessage() for record in caplog.records if "tier=1" in record.getMessage()]
    failure_logs = [message for message in tier1_logs if "outcome=retryable_failure" in message]
    assert len(failure_logs) == 3
    assert all(f"app_id={app_id}" in message for message in tier1_logs)
    assert all("reason=success_false" in message for message in failure_logs)
    assert "retry_delay_seconds=0" in failure_logs[-1]


def test_processor_debug_logs_pipeline_stages_without_local_paths(tmp_path, caplog):
    processor = LocalProcessor.__new__(LocalProcessor)
    processor.preserve_working_files = False
    steam_meta = SteamMetadata(app_id=424243, name="Synthetic OST")

    with caplog.at_level(logging.DEBUG, logger="sst.processor"):
        result = processor.process_album(steam_meta.app_id, tmp_path, steam_meta)

    assert result.status == "skip"
    pipeline_logs = [record.getMessage() for record in caplog.records if "PIPELINE_EVENT" in record.getMessage()]
    assert any("stage=PROCESS_START" in message for message in pipeline_logs)
    assert any("stage=SKIP_NO_AUDIO" in message for message in pipeline_logs)
    assert all("elapsed_seconds=" in message for message in pipeline_logs)
    assert all("install_dir" not in message and str(tmp_path) not in message for message in pipeline_logs)


def test_list_audio_files_excludes_macos_artifacts(tmp_path: Path):
    (tmp_path / "01 Main.wav").touch()
    (tmp_path / ".DS_Store").touch()
    (tmp_path / "._01 Main.wav").touch()
    macosx = tmp_path / "__MACOSX"
    macosx.mkdir()
    (macosx / "._01 Main.wav").touch()
    (macosx / "02 Main.wav").touch()

    assert TrackManager.list_audio_files(tmp_path) == [tmp_path / "01 Main.wav"]


def test_normalize_processed_tracks_keeps_highest_tier_per_slot():
    tracks = [
        {"slot_key": "3_1", "tier_rank": 3, "tags": {"track_number": "1"}},
        {"slot_key": "3_1", "tier_rank": 0, "tags": {"track_number": "1"}},
        {"slot_key": "3_2", "tier_rank": 1, "tags": {"track_number": "2"}},
    ]

    normalized = LocalProcessor._normalize_processed_tracks(tracks)

    assert [track["slot_key"] for track in normalized] == ["3_1", "3_2"]
    assert normalized[0]["tier_rank"] == 0


def test_katana_zero_format_variants_collapse_to_one_steam_file_per_slot():
    steam_meta = SteamMetadata(
        app_id=1075710,
        name="Katana ZERO Soundtrack",
        store_tracklist=[
            {"disc": 1, "number": str(track_number), "title": f"Track {track_number}"}
            for track_number in range(1, 39)
        ],
    )
    track_groups = {}
    final_metadata = {}

    for track_number in range(1, 39):
        title = f"track {track_number}"
        mp3_id = f"mp3-{track_number}"
        aiff_id = f"aiff-{track_number}"
        track_groups[(1, f"{title}::{mp3_id}")] = [
            {
                "file_id": mp3_id,
                "path": Path(f"{mp3_id}.mp3"),
                "format": "mp3",
                "t_num_val": track_number,
            }
        ]
        track_groups[(1, f"{title}::{aiff_id}")] = [
            {
                "file_id": aiff_id,
                "path": Path(f"{aiff_id}.aiff"),
                "format": "aiff",
                "t_num_val": track_number,
            }
        ]
        final_metadata[f"1_{title}::{mp3_id}"] = {
            "matched_v_idx": track_number - 1,
            "reason": "タイトルが一致。",
        }
        final_metadata[f"1_{title}::{aiff_id}"] = {
            "matched_v_idx": track_number - 1,
            "reason": "タイトルが一致。",
        }

    resolve_duplicate_mappings(1075710, final_metadata, steam_meta, track_groups)
    slot_variant_index, track_to_slot_index = build_slot_variant_index(
        final_metadata, track_groups, steam_meta
    )
    adopted_files = adopt_best_file_per_slot(
        track_groups, slot_variant_index, track_to_slot_index
    )

    assert len(track_groups) == 38
    assert len(final_metadata) == 38
    assert len(slot_variant_index) == 38
    assert len(adopted_files) == 38
    assert all(
        instruction["matched_v_idx"] == index
        and instruction["reason"] != "Fallback"
        for index, instruction in enumerate(final_metadata.values())
    )
    assert {
        variant["format"]
        for variants in slot_variant_index.values()
        for variant in variants
    } == {"aiff", "mp3"}
    assert all(
        info["tier_rank"] == TrackManager.get_quality_tier("aiff")
        and info["tier_rank"] < TrackManager.get_quality_tier("mp3")
        and info["path"].suffix == ".aiff"
        for info in adopted_files.values()
    )
