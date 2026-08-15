from typing import Any

import sst.processor as processor_module
from sst.db import DatabaseManager
from sst.processor_support import select_best_unassigned_files
from sst.config import Config
from sst.models import SteamMetadata
from sst.processor import LocalProcessor


class MockDB(DatabaseManager):
    """Minimal database double accepted by ``LocalProcessor``'s type contract."""

    def __init__(self) -> None:
        # The processor's constructor passes the database to collaborators, but
        # these tests do not perform database I/O.
        pass

    def record_processed(self, *args: Any, **kwargs: Any) -> None:
        return None


def make_processor() -> LocalProcessor:
    return LocalProcessor(Config(steam_install_path="/tmp"), MockDB())


def make_steam_meta() -> SteamMetadata:
    return SteamMetadata(
        app_id=1,
        name="Test OST",
        developer="Dev",
        publisher="Pub",
        release_date="2024-01-02",
        store_tracklist=[
            {"number": 1, "title": "Main Theme", "disc": 1},
            {"number": 2, "title": "Battle Theme", "disc": 1},
        ],
    )


def make_track_groups(duration_gap: float = 0.4):
    return {
        (1, "main theme"): [
            {"t_num_val": "1", "duration": 180.0, "format": "wav"},
            {"t_num_val": "1", "duration": 180.0 + duration_gap, "format": "mp3"},
        ],
        (1, "battle theme"): [
            {"t_num_val": "2", "duration": 200.0, "format": "flac"},
        ],
    }


def test_fast_track_succeeds_with_steam_slot_match():
    processor = make_processor()

    ok, final_map, global_id = processor._check_fast_track(1, make_steam_meta(), make_track_groups(), [])

    assert ok is True
    assert final_map is not None
    assert global_id is not None
    assert final_map["1_main theme"]["matched_v_idx"] == 0
    assert final_map["1_battle theme"]["matched_v_idx"] == 1
    assert global_id["canonical_year"] == "2024"


def test_fast_track_fails_without_steam_tracklist():
    processor = make_processor()
    steam_meta = make_steam_meta().model_copy(update={"store_tracklist": []})

    ok, final_map, global_id = processor._check_fast_track(1, steam_meta, make_track_groups(), [])

    assert ok is False
    assert final_map is None
    assert global_id is None

def test_select_best_unassigned_files_keeps_only_highest_tier_variant(tmp_path):
    lossless = tmp_path / "unassigned.aif"
    lossy = tmp_path / "unassigned.mp3"
    lossless.write_bytes(b"aif")
    lossy.write_bytes(b"mp3")

    track_groups = {
        (1, "unassigned"): [
            {"path": lossy, "format": "mp3", "file_id": "mp3-id", "meta": {}},
            {"path": lossless, "format": "aif", "file_id": "aif-id", "meta": {}},
        ],
        (1, "assigned"): [
            {"path": lossless, "format": "aif", "file_id": "assigned-id", "meta": {}},
        ],
    }

    selected = select_best_unassigned_files(track_groups, {"1_assigned": {"matched_v_idx": 0}})

    assert len(selected) == 1
    assert selected[0]["file_id"] == "aif-id"
    assert selected[0]["tier"] == "lossless"


def test_select_best_unassigned_files_filters_by_llm_file_ids(tmp_path):
    selected_path = tmp_path / "selected.aif"
    ignored_path = tmp_path / "ignored.mp3"
    selected_path.write_bytes(b"aif")
    ignored_path.write_bytes(b"mp3")
    track_groups = {
        (1, "candidate"): [
            {"path": ignored_path, "format": "mp3", "file_id": "ignored", "meta": {}},
            {"path": selected_path, "format": "aif", "file_id": "selected", "meta": {}},
        ],
    }

    selected = select_best_unassigned_files(track_groups, {}, {"selected"})

    assert len(selected) == 1
    assert selected[0]["file_id"] == "selected"
    assert selected[0]["unassigned_file_ids"] == ["selected"]


def test_fast_track_fails_when_any_group_lacks_track_number():
    processor = make_processor()
    track_groups = make_track_groups()
    track_groups[(1, "battle theme")][0]["t_num_val"] = None

    ok, _, _ = processor._check_fast_track(1, make_steam_meta(), track_groups, [])

    assert ok is True


def test_fast_track_uses_unique_title_when_track_number_is_missing():
    processor = make_processor()
    track_groups = make_track_groups()
    track_groups[(1, "battle theme")][0]["t_num_val"] = None

    ok, final_map, _ = processor._check_fast_track(1, make_steam_meta(), track_groups, [])

    assert ok is True
    assert final_map is not None
    assert final_map["1_battle theme"]["matched_v_idx"] == 1


def test_fast_track_replaces_wrong_number_with_unique_title_match():
    processor = make_processor()
    track_groups = make_track_groups()
    track_groups[(1, "battle theme")][0]["t_num_val"] = "1"

    ok, final_map, _ = processor._check_fast_track(1, make_steam_meta(), track_groups, [])

    assert ok is True
    assert final_map is not None
    assert final_map["1_battle theme"]["matched_v_idx"] == 1


def test_fast_track_fails_when_duplicate_formats_have_large_duration_gap():
    processor = make_processor()

    ok, _, _ = processor._check_fast_track(1, make_steam_meta(), make_track_groups(duration_gap=1.2), [])

    assert ok is False


def test_fast_track_fails_when_track_numbers_do_not_map_one_to_one():
    processor = make_processor()
    track_groups = make_track_groups()
    track_groups[(1, "battle theme")][0]["t_num_val"] = "3"

    ok, _, _ = processor._check_fast_track(1, make_steam_meta(), track_groups, [])

    assert ok is False


def test_process_album_skips_llm_when_fast_track_matches(monkeypatch, tmp_path):
    processor = make_processor()
    steam_meta = make_steam_meta()
    track_groups = {
        (1, "main theme"): [{"file_id": "file-a", "path": tmp_path / "a.wav", "meta": {}, "duration": 180.0, "format": "wav", "filename_track": 1, "t_num_val": "1"}],
        (1, "battle theme"): [{"file_id": "file-b", "path": tmp_path / "b.flac", "meta": {}, "duration": 200.0, "format": "flac", "filename_track": 2, "t_num_val": "2"}],
    }

    monkeypatch.setattr(processor_module.TrackManager, "list_audio_files", lambda install_dir: [tmp_path / "a.wav", tmp_path / "b.flac"])
    monkeypatch.setattr(processor_module.TrackManager, "build_file_records", lambda files, album_name=None: track_groups)
    monkeypatch.setattr(processor_module.TrackManager, "prepare_llm_track_context", lambda groups: {})
    monkeypatch.setattr(processor_module, "collect_alignment_inputs", lambda *args, **kwargs: (
        {"tracks": [{"disc": 1, "track_num": 1, "title": "Main Theme"}, {"disc": 1, "track_num": 2, "title": "Battle Theme"}]},
        {"tracks": [{"local_key": (1, "main theme"), "file_ids": ["file-a"]}, {"local_key": (1, "battle theme"), "file_ids": ["file-b"]}]},
        None,
        None,
        {"status": "signal_alignment_inputs"},
    ))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM consolidation should not run during deterministic fast-track")

    monkeypatch.setattr(processor_module, "consolidate_alignment_inputs", fail_if_called)
    def fake_process_single_track(**kwargs):
        (disc_num, clean_title), adopted_info = kwargs["track_data"]
        track_number = str(adopted_info["filename_track"])
        return {
            "track_meta": {
                "file_path": f"disc_{disc_num}/{clean_title}.aif",
                "original_filename": adopted_info["path"].name,
                "tags": {
                    "title": clean_title.title(),
                    "track_number": track_number,
                    "disc_number": str(disc_num),
                    "album_artist": "Dev, Pub",
                    "artist": "Dev",
                    "genre": "STEAM VGM, Action",
                    "year": "2024",
                },
                "source": "Fast-track",
                "title_source": "STEAM",
            },
            "had_warning": False,
            "failed": False,
        }

    monkeypatch.setattr(processor_module, "process_single_track", fake_process_single_track)
    monkeypatch.setattr(processor_module.PackageManager, "save_local_package", lambda *args, **kwargs: None)
    monkeypatch.setattr(processor, "_validate_archive_artifacts", lambda *args, **kwargs: [])
    monkeypatch.setattr(processor, "_fetch_album_artwork", lambda *args, **kwargs: None)
    monkeypatch.setattr(processor, "_send_notifications", lambda *args, **kwargs: None)

    result = processor.process_album(1, tmp_path, steam_meta)

    assert result.status == "archive"
    assert result.confidence_score == 100


def test_build_fast_track_alignment_res_uses_local_track_order():
    alignment_res = LocalProcessor._build_fast_track_alignment_res(
        {
            "1_main theme": {"matched_v_idx": 0, "override_track": "1", "reason": "slot 1"},
            "1_battle theme": {"matched_v_idx": 1, "override_track": "2", "reason": "slot 2"},
        },
        {
            "tracks": [
                {"local_key": (1, "main theme"), "file_ids": ["file-a"]},
                {"local_key": (1, "battle theme"), "file_ids": ["file-b"]},
            ]
        },
    )

    assert alignment_res["slots"]["1"]["files"] == ["file-a"]
    assert alignment_res["slots"]["2"]["files"] == ["file-b"]
    assert alignment_res["unassigned_files"] == []


def test_fast_track_succeeds_with_hash_delimited_record_keys():
    processor = make_processor()
    steam_meta = make_steam_meta()
    
    # Track groups with hashed record keys as produced by TrackManager.build_file_records
    track_groups = {
        (1, "main theme::a1b2c3d4"): [
            {"file_id": "a1b2c3d4", "t_num_val": "1", "duration": 180.0, "format": "flac", "norm_stem": "main theme"}
        ],
        (1, "battle theme::e5f6g7h8"): [
            {"file_id": "e5f6g7h8", "t_num_val": "2", "duration": 200.0, "format": "mp3", "norm_stem": "battle theme"}
        ],
    }

    ok, final_map, global_id = processor._check_fast_track(1, steam_meta, track_groups, [])

    assert ok is True
    assert final_map is not None
    assert "1_main theme::a1b2c3d4" in final_map
    assert "1_battle theme::e5f6g7h8" in final_map
    assert final_map["1_main theme::a1b2c3d4"]["matched_v_idx"] == 0
    assert final_map["1_battle theme::e5f6g7h8"]["matched_v_idx"] == 1


def test_fast_track_bundles_flac_and_mp3_variants_to_same_slot():
    processor = make_processor()
    steam_meta = make_steam_meta()

    track_groups = {
        (1, "main theme::flac_id"): [
            {"file_id": "flac_id", "t_num_val": "1", "duration": 180.2, "format": "flac", "norm_stem": "main theme"}
        ],
        (1, "main theme::mp3_id"): [
            {"file_id": "mp3_id", "t_num_val": "1", "duration": 180.5, "format": "mp3", "norm_stem": "main theme"}
        ],
        (1, "battle theme::flac_id2"): [
            {"file_id": "flac_id2", "t_num_val": "2", "duration": 200.0, "format": "flac", "norm_stem": "battle theme"}
        ],
    }

    ok, final_map, global_id = processor._check_fast_track(1, steam_meta, track_groups, [])

    assert ok is True
    assert final_map is not None
    assert final_map["1_main theme::flac_id"]["matched_v_idx"] == 0
    assert final_map["1_main theme::mp3_id"]["matched_v_idx"] == 0
    assert final_map["1_battle theme::flac_id2"]["matched_v_idx"] == 1