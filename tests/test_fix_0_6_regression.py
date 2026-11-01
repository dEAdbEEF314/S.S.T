from pathlib import Path

from sst.models import SteamMetadata
from sst.processing.file_selection import select_slot_conflict_candidates


def test_multilingual_same_format_variants_not_treated_as_slot_conflict():
    """同一スロットに同一フォーマット（FLAC）の多言語音源（日英）が存在する場合、
    トラック番号・再生時間が一致し他スロット競合がなければ slot_conflict として誤検知されないことを検証。"""
    track_groups = {
        (1, "08 opening battle circuit::id_ja"): [
            {
                "file_id": "id_ja_flac",
                "format": "flac",
                "duration": 82.0,
                "t_num_val": "8",
                "path": Path("08 - オープニング　バトルサーキット.flac"),
            }
        ],
        (1, "08 battle circuit opening::id_en"): [
            {
                "file_id": "id_en_flac",
                "format": "flac",
                "duration": 82.0,
                "t_num_val": "8",
                "path": Path("08 - Battle Circuit - Opening.flac"),
            }
        ],
    }

    slot_variant_index = {
        (1, "8"): [
            track_groups[(1, "08 opening battle circuit::id_ja")][0],
            track_groups[(1, "08 battle circuit opening::id_en")][0],
        ]
    }

    adopted_files = {
        (1, "08 opening battle circuit::id_ja"): {
            "slot_key": (1, "8"),
            "path": Path("08 - オープニング　バトルサーキット.flac"),
            "file_id": "id_ja_flac",
            "tier": "lossless",
            "tier_rank": 1,
        }
    }

    steam_meta = SteamMetadata(
        app_id=1611240,
        name="Capcom Arcade Stadium: Mini-Album Track 8 - Battle Circuit - Opening",
        store_tracklist=[
            {"disc": 1, "number": "8", "title": "オープニング　バトルサーキット"}
        ],
    )

    conflicts = select_slot_conflict_candidates(
        track_groups,
        slot_variant_index,
        adopted_files,
        steam_meta=steam_meta,
    )

    assert conflicts == [], f"多言語同フォーマットバリアントが誤って slot_conflict に選出されました: {conflicts}"


def test_cross_slot_conflict_still_detected_even_with_same_format():
    """他スロットの Steam 公式タイトルと一致する候補（クロススロット誤割当）は、
    同一フォーマットであっても必ず slot_conflict として検知されることを検証。"""
    track_groups = {
        (1, "01 main theme::id_1"): [
            {
                "file_id": "id_1_flac",
                "format": "flac",
                "duration": 120.0,
                "t_num_val": "1",
                "path": Path("01 - Main Theme.flac"),
            }
        ],
        (1, "02 boss theme::id_2"): [
            {
                "file_id": "id_2_flac",
                "format": "flac",
                "duration": 120.5,
                "t_num_val": "1",  # 番号は同一だがタイトルが他スロットと一致
                "path": Path("02 - Boss Theme.flac"),
                "norm_stem": "boss theme",
            }
        ],
    }

    slot_variant_index = {
        (1, "1"): [
            track_groups[(1, "01 main theme::id_1")][0],
            track_groups[(1, "02 boss theme::id_2")][0],
        ]
    }

    adopted_files = {
        (1, "01 main theme::id_1"): {
            "slot_key": (1, "1"),
            "path": Path("01 - Main Theme.flac"),
            "file_id": "id_1_flac",
            "tier": "lossless",
            "tier_rank": 1,
        }
    }

    steam_meta = SteamMetadata(
        app_id=9999999,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "number": "1", "title": "Main Theme"},
            {"disc": 1, "number": "2", "title": "Boss Theme"},  # 他スロット
        ],
    )

    conflicts = select_slot_conflict_candidates(
        track_groups,
        slot_variant_index,
        adopted_files,
        steam_meta=steam_meta,
    )

    assert len(conflicts) == 1
    assert conflicts[0]["candidate_type"] == "slot_conflict"
    assert conflicts[0]["file_id"] == "id_2_flac"


def test_different_track_number_still_detected_as_slot_conflict():
    """トラック番号が異なる候補は slot_conflict として検知されることを検証。"""
    track_groups = {
        (1, "track A::id_a"): [
            {
                "file_id": "id_a",
                "format": "flac",
                "duration": 100.0,
                "t_num_val": "1",
                "path": Path("track_A.flac"),
            }
        ],
        (1, "track B::id_b"): [
            {
                "file_id": "id_b",
                "format": "flac",
                "duration": 100.0,
                "t_num_val": "2",  # 番号不一致
                "path": Path("track_B.flac"),
            }
        ],
    }

    slot_variant_index = {
        (1, "1"): [
            track_groups[(1, "track A::id_a")][0],
            track_groups[(1, "track B::id_b")][0],
        ]
    }

    adopted_files = {
        (1, "track A::id_a"): {
            "slot_key": (1, "1"),
            "path": Path("track_A.flac"),
            "file_id": "id_a",
            "tier": "lossless",
            "tier_rank": 1,
        }
    }

    conflicts = select_slot_conflict_candidates(
        track_groups,
        slot_variant_index,
        adopted_files,
    )

    assert len(conflicts) == 1
    assert conflicts[0]["file_id"] == "id_b"

