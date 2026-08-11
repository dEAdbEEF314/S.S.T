from sst.models import SteamMetadata
from sst.validator import ResultValidator


def steam_meta(title: str = "Unknown (Unused)") -> SteamMetadata:
    return SteamMetadata(
        app_id=1517040,
        name="Synthetic OST",
        store_tracklist=[{"disc": "1", "number": "1", "title": title}],
    )


def track(title: str) -> dict:
    return {"tags": {"disc_number": "1", "track_number": "1", "title": title}}


def llm_log() -> dict:
    return {
        "phase1_res": {
            "identity_confidence": 100,
            "album_confidence": 100,
            "mapping_confidence": 100,
            "data_quality": 100,
            "integrity_quality": 100,
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
        },
        "alignment_res": {},
    }


def test_steam_unknown_is_legitimate():
    log = llm_log()
    status, _, _, _, _ = ResultValidator.validate(1517040, [track("Unknown (Unused)")], log, [], steam_meta(), False, False)
    assert status == "archive"
    assert log["diagnostics"]["steam_unknown_count"] == 1
    assert log["diagnostics"]["anomalous_unknown_count"] == 0


def test_unknown_against_normal_steam_slot_is_anomalous():
    log = llm_log()
    status, message, _, _, _ = ResultValidator.validate(1, [track("Unknown")], log, [], steam_meta("Real Title"), False, False)
    assert status == "review"
    assert "Unknown Title" in message
    assert log["diagnostics"]["anomalous_unknown_count"] == 1


def test_review_causes_are_structured():
    log = llm_log()
    log["alignment_res"]["unassigned_files"] = ["file-1"]
    status, _, _, _, _ = ResultValidator.validate(1, [track("Real Title")], log, [], steam_meta("Real Title"), False, False)
    assert status == "review"
    assert log["diagnostics"]["primary_review_cause"] == "Unassigned Files (1)"
    assert isinstance(log["diagnostics"]["secondary_review_causes"], list)
