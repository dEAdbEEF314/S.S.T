import json
import time
from unittest.mock import patch

from sst.llm import LLMOrganizer


def _build_organizer() -> LLMOrganizer:
    return LLMOrganizer(
        api_key="",
        base_url="http://localhost:11434",
        model="test-model",
        llm_backend="OLLAMA",
        chunk_adaptive=False,
        chunk_size_virtual=2,
        llm_request_parallelism_enabled=True,
        llm_request_parallelism_max_workers=2,
    )


def test_process_track_mapping_segment_retries_truncation(monkeypatch):
    organizer = _build_organizer()
    call_sizes = []

    def fake_call_llm(app_id, prompt, num_ctx=None, request_kind="generic", request_units=0, progress_callback=None):
        call_sizes.append(request_units)
        if request_units == 2 and len(call_sizes) == 1:
            return None, {"error_code": "response_truncated", "error": "response truncated"}
        chunk_idx = 0 if request_units == 1 and len(call_sizes) == 2 else 1
        return {
            "track_instructions": {
                str(chunk_idx): {
                    "action": "use_local",
                    "matched_v_idx": None,
                    "override_title": None,
                    "override_track": None,
                    "override_disc": None,
                    "composer": None,
                    "lyricist": None,
                    "arranger": None,
                    "reason": "ok",
                }
            }
        }, {"ok": True}

    monkeypatch.setattr(organizer, "_call_llm", fake_call_llm)

    local_tracks = [
        {"local_key": [1, 1], "title": "Track 1", "disc": 1, "duration_ms": 1000},
        {"local_key": [1, 2], "title": "Track 2", "disc": 1, "duration_ms": 1000},
    ]
    global_res = {
        "global_tags": {
            "canonical_album_artist": "Artist",
            "canonical_genre": "Genre",
            "canonical_year": "2024",
            "canonical_label": "Label",
        },
        "identity_confidence": 100,
        "integrity_quality": 100,
        "archive_vs_review_ratio": {"archive": 100, "review": 0},
        "strategy": "STEAM_BASED",
        "semantic_label": "ok",
    }

    _, instructions, logs = organizer._process_track_mapping_segment(
        1,
        0,
        local_tracks,
        local_tracks,
        global_res,
        {},
        None,
        [],
        [],
        [],
        None,
        None,
        2,
        None,
    )

    assert call_sizes == [2, 1, 1]
    assert sorted(instructions.keys()) == ["1_1", "1_2"]
    assert len(logs) == 2


def test_align_slots_parallel_merges_deterministically(monkeypatch):
    organizer = _build_organizer()

    monkeypatch.setattr(organizer, "_simplify_v_album", lambda album, sampled=True: album or {})

    def fake_call_llm(app_id, prompt, num_ctx=None, request_kind="generic", request_units=0, progress_callback=None):
        if request_kind == "identity":
            return {
                "identity_confidence": 100,
                "integrity_quality": 100,
                "archive_vs_review_ratio": {"archive": 100, "review": 0},
                "confidence_reason": "ok",
                "strategy": "STEAM_BASED",
                "semantic_label": "ok",
                "global_tags": {
                    "canonical_album_artist": "Artist",
                    "canonical_genre": "Genre",
                    "canonical_year": "2024",
                    "canonical_label": "Label",
                    "chosen_mbz_id": "",
                },
            }, {"ok": True}
        raise AssertionError("track mapping should be stubbed by helper")

    def fake_process_segment(
        app_id,
        start_idx,
        segment_tracks,
        local_tracks,
        global_res,
        s_mbz_search,
        v_mbz_search,
        full_ref_steam,
        full_ref_fingerprint,
        full_ref_mbz_search,
        coherence_mappings,
        num_ctx,
        base_chunk_size,
        progress_callback,
    ):
        if start_idx == 0:
            time.sleep(0.02)
        instructions = {}
        logs = [{"segment": start_idx}]
        for offset, track in enumerate(segment_tracks):
            instructions[f"{track['local_key'][0]}_{track['local_key'][1]}"] = {
                "action": "use_local",
                "matched_v_idx": None,
                "override_title": None,
                "override_track": None,
                "override_disc": None,
                "composer": None,
                "lyricist": None,
                "arranger": None,
                "reason": str(start_idx + offset),
            }
        return start_idx, instructions, logs

    monkeypatch.setattr(organizer, "_call_llm", fake_call_llm)
    monkeypatch.setattr(organizer, "_process_track_mapping_segment", fake_process_segment)

    tracks = [
        {"local_key": [1, 1], "title": "Track 1", "disc": 1, "duration_ms": 1000},
        {"local_key": [1, 2], "title": "Track 2", "disc": 1, "duration_ms": 1000},
        {"local_key": [1, 3], "title": "Track 3", "disc": 1, "duration_ms": 1000},
        {"local_key": [1, 4], "title": "Track 4", "disc": 1, "duration_ms": 1000},
    ]
    album = {"tracks": tracks}

    instructions, logs = organizer.align_slots(1, album, None, None, album)

    assert instructions is not None
    assert list(instructions.keys()) == ["1_1", "1_2", "1_3", "1_4"]
    assert [entry["segment"] for entry in logs["logs"] if "segment" in entry] == [0, 2]


def test_call_llm_emits_progress_and_structured_logs(monkeypatch):
    organizer = _build_organizer()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "message": {"content": '{"ok": true}'},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

    events = []

    with patch("sst.llm.client.requests.post", return_value=FakeResponse()), patch("sst.llm.client.logger.info") as mock_info:
        result, _ = organizer._call_llm(
            1,
            "prompt",
            num_ctx=64,
            request_kind="track_mapping",
            request_units=2,
            progress_callback=events.append,
        )

    assert result == {"ok": True}
    phases = [event["phase"] for event in events]
    assert "llm_prepare" in phases
    assert "llm_request_running" in phases
    assert "llm_request_done" in phases
    logged_messages = [call.args[0] for call in mock_info.call_args_list]
    assert "LLM_REQUEST_DONE %s" in logged_messages
    done_payload = json.loads(next(
        call.args[1] for call in mock_info.call_args_list
        if call.args[0] == "LLM_REQUEST_DONE %s"
    ))
    assert done_payload["total_tokens"] == 15
    assert done_payload["eval_count"] == 5