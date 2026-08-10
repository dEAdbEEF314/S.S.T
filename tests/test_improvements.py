from pathlib import Path
from unittest.mock import MagicMock
from sst.validator import ResultValidator
from sst.builder import MetadataBuilder
from sst.processor_tracks import copy_with_retry
from sst.processor_support import build_slot_variant_index, merge_embedded_tags_for_slot
from sst.models import SteamMetadata

def test_validator_rejects_archive_path_without_steam_structure():
    tracks = [{"tags": {"title": "Test Title", "track_number": "1", "disc_number": "1"}}]
    llm_log = {
        "phase1_res": {
            "identity_confidence": 90,
            "integrity_quality": 85,
            "album_confidence": 90,
            "mapping_confidence": 80,
            "data_quality": 85,
            "semantic_label": "Archive",
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 100, "review": 0}
        }
    }
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = []
    
    status, message, score, quality, reason = ResultValidator.validate(
        app_id=123,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False
    )
    assert status == "review"
    assert "Steam Tracklist Missing" in message


def test_validator_accepts_deterministic_fast_track_path():
    tracks = [{"tags": {"title": "01. Official Title", "track_number": "1", "disc_number": "1"}}]
    llm_log = {
        "fast_track": True,
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "identity_confidence": 100,
            "integrity_quality": 100,
            "confidence_reason": "fast",
        },
    }
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = [{"disc": 1, "number": "1", "title": "01. Official Title"}]

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=123,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )

    assert status == "archive"
    assert "Deterministic Fast-Track" in message


def test_validator_accepts_steam_trust_thresholds():
    tracks = [{"tags": {"title": "Title", "track_number": "1", "disc_number": "1"}}]
    llm_log = {
        "phase1_res": {
            "album_confidence": 95,
            "mapping_confidence": 75,
            "data_quality": 60,
            "identity_confidence": 95,
            "integrity_quality": 60,
            "semantic_label": "Archive",
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 60, "review": 40},
        }
    }
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = [{"disc": 1, "number": "1", "title": "Title"}]

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=123,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )

    assert status == "archive"
    assert "STEAM-TRUST" in message


def test_validator_sends_low_album_confidence_to_review():
    tracks = [{"tags": {"title": "Title", "track_number": "1", "disc_number": "1"}}]
    llm_log = {
        "phase1_res": {
            "album_confidence": 89,
            "mapping_confidence": 95,
            "data_quality": 95,
            "identity_confidence": 89,
            "integrity_quality": 95,
            "semantic_label": "Review",
            "strategy": "HYBRID",
            "archive_vs_review_ratio": {"archive": 40, "review": 60},
        }
    }
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = []

    status, message, score, quality, reason = ResultValidator.validate(
        app_id=123,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
    )

    assert status == "review"
    assert "Album confidence too low" in message

def test_builder_html_unescape():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Test &amp; Album"
    steam_meta.developer = "Dev &amp; Studio"
    steam_meta.publisher = "Pub &amp; Studio"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="Track &amp; Title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="ja"
    )

    assert tag_map["title"] == "Track & Title"
    assert tag_map["album"] == "Test & Album"
    assert tag_map["label"] == ""


def test_builder_keeps_steam_title_without_mechanical_cleaning():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = [{"number": 2, "title": "02. Official Title", "disc": 1}]

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="official title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_steam", "matched_v_idx": 0},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn"
    )

    assert tag_map["title"] == "02. Official Title"


def test_builder_prefers_steam_year_over_mbz_year():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local", "chosen_mbz_index": 0, "mbz_track_index": 0},
        mbz_candidates=[{"year": "1999", "tracks": [{"title": "Title"}], "artist": "Artist", "label": "Label"}],
        track_sources={},
        user_language_639_2="jpn"
    )

    assert tag_map["year"] == "2021"


def test_builder_prefers_recording_artist_from_track_level_signal():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = "Artist: Store Artist"
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local", "chosen_mbz_index": 0, "mbz_track_index": 0},
        mbz_candidates=[{"year": "1999", "artist": "Release Artist", "tracks": [{"title": "Title", "recording_artist": "Recording Artist"}]}],
        track_sources={},
        user_language_639_2="jpn"
    )

    assert tag_map["artist"] == "Recording Artist"


def test_builder_comment_preserves_empty_tag_block_and_album_artist_omits_missing_values():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = None
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = "Parent Game"
    steam_meta.parent_app_id = 999
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={"comment": "Existing comment"},
    )

    assert tag_map["album_artist"] == "Dev"
    assert tag_map["comment"] == "Existing comment, Parent Game, https://store.steampowered.com/app/999, []"


def test_builder_uses_embedded_disc_number_when_steam_disc_is_missing():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = [{"number": 3, "title": "Title"}]

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="title",
        adopted_info={"path": Path("dummy.mp3"), "filename_track": 3},
        steam_meta=steam_meta,
        instr={"action": "use_local"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={"disc_number": "2/2"},
        total_discs=2,
    )

    assert tag_map["disc_number"] == "2/2"


def test_builder_uses_embedded_composer_after_store_credits_and_recording_artist():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.name = "Album"
    steam_meta.developer = "Dev"
    steam_meta.publisher = "Pub"
    steam_meta.genre = None
    steam_meta.genres = ["Action"]
    steam_meta.parent_genres = []
    steam_meta.parent_tags = []
    steam_meta.tags = []
    steam_meta.parent_name = None
    steam_meta.parent_app_id = None
    steam_meta.release_date = "2021-10-01"
    steam_meta.label = None
    steam_meta.store_credits = None
    steam_meta.store_tracklist = []

    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="title",
        adopted_info={"path": Path("dummy.mp3")},
        steam_meta=steam_meta,
        instr={"action": "use_local"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={"composer": "Embedded Composer"},
    )

    assert tag_map["composer"] == "Embedded Composer"


def test_slot_variant_index_groups_multiple_track_ids_into_same_steam_slot():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = [{"disc": 1, "number": 1, "title": "Main Theme"}]
    track_groups = {
        (1, "main theme flac"): [{"format": "flac", "meta": {"comment": "from flac"}, "t_num_val": "1"}],
        (1, "main theme mp3"): [{"format": "mp3", "meta": {"comment": "from mp3"}, "t_num_val": "1"}],
    }
    final_metadata = {
        "1_main theme flac": {"matched_v_idx": 0},
        "1_main theme mp3": {"matched_v_idx": 0},
    }

    slot_variants, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)

    assert track_to_slot["1_main theme flac"] == (1, "1")
    assert track_to_slot["1_main theme mp3"] == (1, "1")
    assert len(slot_variants[(1, "1")]) == 2


def test_merge_embedded_tags_for_slot_picks_first_available_comment_by_priority():
    slot_variants = [
        {"format": "flac", "meta": {}},
        {"format": "mp3", "meta": {"comment": "embedded comment", "title": "Song"}},
    ]

    merged = merge_embedded_tags_for_slot(slot_variants)

    assert merged["comment"] == "embedded comment"
    assert merged["title"] == "Song"

def test_copy_with_retry(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"
    
    copy_with_retry(src, dst, retries=2)
    assert dst.read_text() == "hello"

def test_clean_title_logic_strict_matching():
    # Only remove leading track prefix if it strictly matches track_number
    # Case 1: Match -> Cleaned
    assert MetadataBuilder._clean_title_logic("01. Song Title", "1") == "Song Title"
    assert MetadataBuilder._clean_title_logic("01 - Song Title", "1") == "Song Title"
    
    # Case 2: Number mismatch -> Keep as is (let system/validator review if necessary)
    assert MetadataBuilder._clean_title_logic("02. Song Title", "1") == "02. Song Title"
    
    # Case 3: Title with numeric theme like 1984 -> Keep if track is 1
    assert MetadataBuilder._clean_title_logic("1984 Theme", "1") == "1984 Theme"


def test_builder_prioritizes_steam_store_credits_for_composer():
    steam_meta = SteamMetadata(
        app_id=1,
        name="Album",
        developer="Developer",
        publisher="Publisher",
        store_tracklist=[{"disc": 1, "number": 1, "title": "Song"}],
        store_credits="Composer: Steam Composer",
    )

    tag_map = MetadataBuilder.build_tag_map(
        app_id=1,
        disc=1,
        clean_title="song",
        adopted_info={"filename_track": 1},
        steam_meta=steam_meta,
        instr={"matched_v_idx": 0, "composer": "LLM Composer"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
    )

    assert tag_map["composer"] == "Steam Composer"
