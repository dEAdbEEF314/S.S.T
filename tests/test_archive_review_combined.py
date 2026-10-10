from unittest.mock import MagicMock

from sst.models import SteamMetadata
from sst.validator import ResultValidator


def _make_track(title: str, track_number: str, disc_number: str = "1"):
    return {"tags": {"title": title, "track_number": track_number, "disc_number": disc_number}}


def _make_steam_meta():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = [{"disc": 1, "number": "1", "title": "Official Title"}]
    return steam_meta


def test_validator_returns_llm_archive_path_when_all_thresholds_pass():
    status, message, score, quality, reason = ResultValidator.validate(
        1,
        [_make_track("Official Title", "1")],
        {
            "phase1_res": {
                "album_confidence": 95,
                "mapping_confidence": 82,
                "data_quality": 74,
                "identity_confidence": 95,
                "integrity_quality": 74,
                "strategy": "HYBRID",
                "archive_vs_review_ratio": {"archive": 70, "review": 30},
            }
        },
        [],
        _make_steam_meta(),
        False,
        False,
    )

    assert status == "archive"
    assert "LLM-ARCHIVE" in message


def test_validator_reviews_title_that_disagrees_with_authoritative_slot():
    log = {
        "fast_track": True,
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "strategy": "FAST_TRACK",
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
        },
    }

    status, message, *_ = ResultValidator.validate(
        1,
        [_make_track("Different Track", "1")],
        log,
        [],
        _make_steam_meta(),
        False,
        False,
    )

    assert status == "review"
    assert "Official Title Mismatch (1)" in message
    assert log["diagnostics"]["official_title_mismatch_count"] == 1


def test_validator_accepts_entity_and_unicode_normalized_official_title():
    steam_meta = _make_steam_meta()
    steam_meta.store_tracklist = [
        {"disc": 1, "number": "1", "title": "Giant&apos;s Deep"}
    ]
    log = {
        "fast_track": True,
        "phase1_res": {
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "strategy": "FAST_TRACK",
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
        },
    }

    status, message, *_ = ResultValidator.validate(
        1,
        [_make_track("Giant's Deep", "01")],
        log,
        [],
        steam_meta,
        False,
        False,
    )

    assert status == "archive"
    assert "Official Title Mismatch" not in message
    assert log["diagnostics"]["official_title_mismatch_count"] == 0


def test_validator_returns_review_when_mapping_confidence_fails():
    status, message, score, quality, reason = ResultValidator.validate(
        1,
        [_make_track("Official Title", "1")],
        {
            "phase1_res": {
                "album_confidence": 95,
                "mapping_confidence": 79,
                "data_quality": 74,
                "identity_confidence": 95,
                "integrity_quality": 74,
                "strategy": "HYBRID",
                "archive_vs_review_ratio": {"archive": 30, "review": 70},
            }
        },
        [],
        _make_steam_meta(),
        False,
        False,
    )

    assert status == "review"
    assert "Mapping confidence too low" in message


def test_validator_rejects_steam_trust_without_a_tracklist():
    steam_meta = MagicMock(spec=SteamMetadata)
    steam_meta.store_tracklist = []
    status, message, *_ = ResultValidator.validate(
        1,
        [_make_track("Local title", "1")],
        {
            "phase1_res": {
                "album_confidence": 100,
                "mapping_confidence": 100,
                "data_quality": 100,
                "strategy": "STEAM_BASED",
            },
            "logs": ["STEAM-TRUST"],
        },
        [],
        steam_meta,
        False,
        False,
    )

    assert status == "review"
    assert "Steam Tracklist Missing" in message


def test_validator_returns_review_when_data_quality_fails():
    status, message, score, quality, reason = ResultValidator.validate(
        1,
        [_make_track("Official Title", "1")],
        {
            "phase1_res": {
                "album_confidence": 95,
                "mapping_confidence": 82,
                "data_quality": 69,
                "identity_confidence": 95,
                "integrity_quality": 69,
                "strategy": "HYBRID",
                "archive_vs_review_ratio": {"archive": 30, "review": 70},
            }
        },
        [],
        _make_steam_meta(),
        False,
        False,
    )

    assert status == "review"
    assert "Data quality too low" in message


def test_validator_returns_review_for_duplicate_tracks_even_with_good_scores():
    status, message, score, quality, reason = ResultValidator.validate(
        1,
        [_make_track("Official Title", "1"), _make_track("Another Title", "1")],
        {
            "fast_track": True,
            "phase1_res": {
                "album_confidence": 100,
                "mapping_confidence": 100,
                "data_quality": 100,
                "identity_confidence": 100,
                "integrity_quality": 100,
                "strategy": "FAST_TRACK",
                "archive_vs_review_ratio": {"archive": 100, "review": 0},
            }
        },
        [],
        _make_steam_meta(),
        False,
        False,
    )

    assert status == "review"
    assert "Duplicates" in message