from pathlib import Path

from sst.processor import LocalProcessor
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