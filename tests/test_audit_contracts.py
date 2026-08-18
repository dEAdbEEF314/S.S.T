from pathlib import Path

from sst.models import SteamMetadata
from sst.validator import ResultValidator
from sst.processor_pipeline import handle_early_review_return


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


def _early_review_mocks():
    class _Diag:
        def __call__(self, *a, **k):
            pass
    class _Now:
        def __call__(self):
            return self
        def isoformat(self):
            return "2026-08-18T00:00:00+09:00"
        def strftime(self, *_a):
            return "2026-08-18 00:00:00"
    class _Notify:
        def __call__(self, *a, **k):
            return None
    return _Diag(), _Now(), _Notify()


def test_early_review_preserves_audit_block_and_diagnostics():
    """提案1: Early Review経路でも audit ブロックと構造化 diagnostics が保存される。"""
    steam = SteamMetadata(
        app_id=999,
        name="Early Review OST",
        store_tracklist=[{"disc": "1", "number": "1", "title": "A"}, {"disc": "1", "number": "2", "title": "B"}],
    )
    llm_log_payload = {
        "phase1_log": {},
        "phase1_res": {},
        "diagnostics": {},
    }
    _diag, _now, _notify = _early_review_mocks()
    result = handle_early_review_return(
        app_id=999,
        steam_meta=steam,
        track_count=2,
        llm_log=llm_log_payload,
        v_steam={}, v_local={}, v_fingerprint=None, v_mbz_search=None,
        diagnostics=llm_log_payload["diagnostics"],
        _diag=_diag,
        get_localized_now=_now,
        send_notifications=_notify,
        working_dir=Path("/tmp"),
        output_dir="/tmp",
        db=None,
        config=type("C", (), {"resolved_metadata_source_priority": "STEAM,LOCAL"})(),
        preserve_working_files=True,
    )
    meta = result.metadata
    assert meta["status"] == "review"
    assert "audit" in meta
    audit = meta["audit"]
    assert audit["steam_expected_slots"] == 2
    assert audit["final_adopted_slots"] == 0
    assert audit["review_phase"] == "EARLY_REVIEW"
    assert audit["unassigned_file_count"] == 2
    diag = meta["diagnostics"]
    assert diag["review_cause_code"] == "EARLY_REVIEW_RETURN"
    assert diag["steam_expected_slots"] == 2
    assert diag["adopted_slots"] == 0
    assert diag["unassigned_slots"] == 2
    assert diag["primary_review_cause"] is not None
    assert isinstance(diag["secondary_review_causes"], list)


def test_validator_diagnostics_records_slot_counts():
    """提案2: validator が steam_expected_slots / adopted_slots / unassigned_slots を diagnostics へ記録する。"""
    log = llm_log()
    status, _, _, _, _ = ResultValidator.validate(
        1, [track("Real Title")], log, [], steam_meta("Real Title"), False, False
    )
    diag = log["diagnostics"]
    assert diag["steam_expected_slots"] == 1
    assert diag["adopted_slots"] == 1
    assert diag["unassigned_slots"] == 0
    assert "primary_review_cause" in diag


def test_validator_flags_llm_rejected_slots_and_duplicates():
    """提案3: LLM矛盾（Steam外slot・重複割当）が Review 理由へ明示される。"""
    log = llm_log()
    log["alignment_res"] = {
        "rejected_slot_keys": ["9", "13"],
        "duplicate_assignment_file_ids": ["abc123"],
        "unassigned_files": [],
    }
    status, message, _, _, _ = ResultValidator.validate(
        1, [track("Real Title")], log, [], steam_meta("Real Title"), False, False
    )
    assert status == "review"
    assert "LLM Rejected Slots (2)" in message
    assert "LLM Duplicate Assignment (1)" in message
