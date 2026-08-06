from pathlib import Path
from unittest.mock import MagicMock

from sst.builder import MetadataBuilder
from sst.processor_support import build_slot_variant_index, merge_embedded_tags_for_slot
from sst.track_grouper import TrackManager


def test_merge_embedded_tags_for_slot_uses_priority_order():
    slot_variants = [
        {"format": "flac", "meta": {"title": "Lossless Title"}},
        {"format": "mp3", "meta": {"comment": "MP3 Comment", "title": "MP3 Title"}},
    ]

    merged = merge_embedded_tags_for_slot(slot_variants)

    assert merged["title"] == "Lossless Title"
    assert merged["comment"] == "MP3 Comment"


def test_slot_variant_index_prefers_steam_slot_numbers_over_local_title_keys():
    steam_meta = MagicMock()
    steam_meta.store_tracklist = [{"disc": 2, "number": 7, "title": "Boss Theme"}]
    final_metadata = {"1_boss theme": {"matched_v_idx": 0}}
    track_groups = {(1, "boss theme"): [{"format": "flac", "meta": {}, "t_num_val": "7"}]}

    slot_variants, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    assert track_to_slot["1_boss theme"] == (2, "7")
    assert (2, "7") in slot_variants


def test_builder_uses_slot_wide_comment_pickup():
    steam_meta = MagicMock()
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = ["tag1", "tag2"]
    steam_meta.tags = []
    steam_meta.parent_name = "Game"
    steam_meta.parent_app_id = 77
    steam_meta.release_date = "2022-01-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = [{"number": 1, "title": "Boss Theme", "disc": 1}]

    tag_map = MetadataBuilder.build_tag_map(
        app_id=77,
        disc=1,
        clean_title="boss theme",
        adopted_info={"path": Path("dummy.flac"), "filename_track": 1},
        steam_meta=steam_meta,
        instr={"action": "use_steam", "matched_v_idx": 0},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={"comment": "Recovered from sibling MP3"},
    )

    assert tag_map["comment"] == "Recovered from sibling MP3, Game, https://store.steampowered.com/app/77, [tag1/ tag2]"


def test_get_best_artwork_uses_first_available_variant(monkeypatch):
    fake_apic = MagicMock()
    fake_apic.data = b"img"
    fake_apic.FrameID = "APIC"
    fake_audio = MagicMock()
    fake_audio.tags = {"APIC:test": fake_apic}

    monkeypatch.setattr("mutagen.File", lambda path: fake_audio)

    art = TrackManager.get_best_artwork([
        {"path": Path("song.mp3"), "format": "mp3"},
    ])

    assert art == b"img"