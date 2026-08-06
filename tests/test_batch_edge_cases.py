from pathlib import Path

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
            "action": "use_steam",
            "matched_v_idx": track_number - 1,
            "reason": "タイトルが一致。",
        }
        final_metadata[f"1_{title}::{aiff_id}"] = {
            "action": "use_steam",
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
        instruction["action"] == "use_steam"
        and instruction["matched_v_idx"] == index
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
