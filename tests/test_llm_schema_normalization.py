from sst.llm.organizer import LLMOrganizer


def make_organizer() -> LLMOrganizer:
    return LLMOrganizer(api_key="dummy", base_url="http://localhost:11434")


def test_identity_result_normalization_adds_new_spec_aliases():
    organizer = make_organizer()

    normalized = organizer._normalize_identity_result(
        {
            "identity_confidence": 92,
            "integrity_quality": 73,
            "global_tags": {"canonical_album_artist": "Dev, Pub"},
        }
    )

    assert normalized["album_confidence"] == 92
    assert normalized["data_quality"] == 73
    assert normalized["mapping_confidence"] == 0
    assert normalized["concerns"] == []


def test_slot_view_preserves_compatibility_track_instructions():
    organizer = make_organizer()
    local_tracks = [
        {"title": "a", "file_ids": ["file-a"]},
        {"title": "b", "file_ids": ["file-b"]},
        {"title": "c", "file_ids": ["file-c"]},
    ]

    slot_view = organizer._build_slot_view(
        {
            "track_instructions": {
                    "file-a": {"matched_v_idx": 0, "reason": "ok"},
                    "file-b": {"matched_v_idx": 0, "reason": "same slot"},
            }
        },
        local_tracks,
    )

    assert slot_view["slots"]["1"]["files"] == ["file-a", "file-b"]
    assert slot_view["unassigned_files"] == ["file-c"]
    assert slot_view["unassigned_reason"] == "No slot assignment returned"


def test_slot_view_preserves_explicit_new_spec_shape():
    organizer = make_organizer()
    explicit = {
        "slots": {"2": {"files": ["5"], "confidence": 0.95, "reason": "mapped"}},
        "unassigned_files": ["7"],
        "unassigned_reason": "bonus track",
    }

    slot_view = organizer._build_slot_view(explicit, [{"title": "x", "file_ids": ["5", "7"]}])

    assert slot_view["slots"] == explicit["slots"]
    assert slot_view["unassigned_files"] == ["7"]
    assert slot_view["unassigned_reason"] == explicit["unassigned_reason"]


def test_slot_view_from_final_instructions_uses_local_track_order():
    organizer = make_organizer()
    local_tracks = [
            {"local_key": (1, "alpha"), "file_ids": ["file-alpha"]},
            {"local_key": (1, "beta"), "file_ids": ["file-beta"]},
            {"local_key": (1, "gamma"), "file_ids": ["file-gamma"]},
    ]
    final_instructions = {
        "1_gamma": {"matched_v_idx": 1, "reason": "mapped gamma"},
        "1_alpha": {"matched_v_idx": 0, "reason": "mapped alpha"},
    }

    slot_view = organizer._build_slot_view_from_final_instructions(final_instructions, local_tracks)

    assert slot_view["slots"]["1"]["files"] == ["file-alpha"]
    assert slot_view["slots"]["2"]["files"] == ["file-gamma"]
    assert slot_view["unassigned_files"] == ["file-beta"]


def test_consolidation_continues_even_when_identity_confidence_is_low(monkeypatch):
    organizer = make_organizer()

    responses = iter([
        (
            {
                "identity_confidence": 40,
                "integrity_quality": 65,
                "archive_vs_review_ratio": {"archive": 10, "review": 90},
                "global_tags": {"canonical_album_artist": "Dev, Pub"},
            },
            {"prompt": "identity"},
        )
    ])

    def fake_call_llm(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(organizer.client, "call_llm", fake_call_llm)
    monkeypatch.setattr(
        organizer,
        "_process_track_mapping_segment",
        lambda *args, **kwargs: (
            0,
            {"1_alpha": {"matched_v_idx": 0, "reason": "mapped alpha"}},
            [{"prompt": "mapping"}],
        ),
    )

    final_instructions, llm_log = organizer.align_slots(
        app_id=1,
        v_steam={"tracks": [{"disc": 1, "track_num": 1, "title": "Alpha"}, {"disc": 1, "track_num": 2, "title": "Beta"}]},
        v_fingerprint=None,
        v_mbz_search=None,
        v_local={"tracks": [{"local_key": (1, "alpha"), "disc": 1, "track_num": 1, "title": "alpha", "duration_ms": 1000}]},
    )

    assert final_instructions == {"1_alpha": {"matched_v_idx": 0, "reason": "mapped alpha"}}
    assert "Low album confidence before slot alignment" in llm_log["phase1_res"]["concerns"]


def test_normalize_track_mapping_result_accepts_explicit_slots_output():
    organizer = make_organizer()

    normalized = organizer._normalize_track_mapping_result(
        {
            "slots": {
                "7": {
                    "files": ["0", "2"],
                    "confidence": 0.95,
                    "reason": "slot mapping",
                }
            },
            "unassigned_files": ["1"],
        },
        [{"v_idx": 4, "n": 5}, {"v_idx": 6, "n": 7}],
    )

    assert normalized["track_instructions"]["0"]["matched_v_idx"] == 6
    assert normalized["track_instructions"]["2"]["override_track"] == "7"


def test_normalize_slot_result_merges_prematch_data():
    from sst.llm.prematch import PrematchResult

    organizer = make_organizer()
    prematch_map = {
        "file-1": PrematchResult(file_id="file-1", mbz_track_index=15, override_track="1"),
    }

    normalized = organizer._normalize_track_mapping_result(
        {
            "slots": {
                "1": {
                    "files": ["file-1"],
                    "confidence": 0.95,
                    "reason": "prematched",
                }
            }
        },
        [{"v_idx": 0, "n": 1}],
        prematch_map=prematch_map,
    )

    assert normalized["track_instructions"]["file-1"]["matched_v_idx"] == 0
    assert normalized["track_instructions"]["file-1"]["mbz_track_index"] == 15
    assert normalized["track_instructions"]["file-1"]["override_track"] == "1"


def test_slot_identity_prefers_explicit_track_number_over_list_position():
    organizer = make_organizer()

    normalized = organizer._normalize_track_mapping_result(
        {
            "slots": {
                "7": {"files": ["file-seven"], "reason": "disc two slot"},
                "5": {"files": ["file-five"], "reason": "disc one slot"},
            }
        },
        [
            {"v_idx": 10, "n": 5},
            {"v_idx": 11, "n": 7},
        ],
    )

    assert normalized["track_instructions"]["file-seven"]["matched_v_idx"] == 11
    assert normalized["track_instructions"]["file-five"]["matched_v_idx"] == 10


def test_slot_assignment_rejects_duplicate_file_ids_in_explicit_slots():
    organizer = make_organizer()

    slot_view = organizer._build_slot_view(
        {
            "slots": {
                "1": {"files": ["file-a"], "reason": "first"},
                "2": {"files": ["file-a", "file-b"], "reason": "duplicate"},
            }
        },
        [{"file_ids": ["file-a", "file-b"]}],
    )

    assert slot_view["slots"]["1"]["files"] == ["file-a"]
    assert slot_view["slots"]["2"]["files"] == ["file-b"]
    assert slot_view["unassigned_files"] == []