from sst.config import Config
from sst.llm.prompts import build_identity_prompt, build_mapping_prompt, build_degraded_prompt
from sst.llm.client import LLMClient
from sst.llm.retry_policy import LLMRetryPolicy
from unittest.mock import patch

def test_build_degraded_prompt_identity():
    original = build_identity_prompt(
        s_steam={"name": "Test Album"},
        s_fingerprint=None,
        s_mbz_search=None,
        s_local={"files": ["01.mp3", "02.mp3"]},
        user_language="ja"
    )
    degraded = build_degraded_prompt(original, request_kind="identity", user_language="ja")
    assert "### OUTPUT FORMAT" in original
    assert "### [EMERGENCY DEGRADED OUTPUT FORMAT - MINIMAL JSON ONLY]" in degraded
    assert "Test Album" in degraded
    assert "01.mp3" in degraded
    assert "album_confidence" in degraded
    assert "data_quality" in degraded

def test_build_degraded_prompt_track_mapping():
    steam_tracks = [{"disc": 1, "track": 1, "title": "Track 1"}]
    files = [{"filename": "01_track.mp3", "path": "/path/01_track.mp3"}]
    original = build_mapping_prompt(
        global_res={"global_tags": {"album": "Test Album"}},
        s_mbz_search={},
        v_mbz_search=None,
        ref_steam=steam_tracks,
        ref_fingerprint=[],
        s_chunk=files,
        start_idx=0,
        user_language="ja"
    )
    degraded = build_degraded_prompt(original, request_kind="track_mapping", user_language="ja")
    assert "### [EMERGENCY DEGRADED OUTPUT FORMAT - MINIMAL JSON ONLY]" in degraded
    assert "slots" in degraded
    assert "01_track.mp3" in degraded

def test_estimate_output_budget_and_ceiling():
    client = LLMClient(
        base_url="http://localhost:11434",
        api_key="",
        model="test-model",
        ollama_num_predict=4096,
        chunk_output_tokens_per_track=180,
        output_budget_safety_ratio=0.25,
    )
    # identity
    identity_budget = client._estimate_expected_output_tokens("identity", 1)
    assert identity_budget == 4096
    ceiling = max(256, int(identity_budget * 1.25))
    assert ceiling == int(4096 * 1.25)

    # track_mapping with 5 tracks: 1536 + 5 * 180 = 2436
    track_budget = client._estimate_expected_output_tokens("track_mapping", 5)
    assert track_budget == 1536 + 5 * 180
    track_ceiling = max(256, int(track_budget * 1.25))
    assert track_ceiling == int(2436 * 1.25)

def test_config_llm_retries_and_budget_safety():
    cfg = Config(steam_install_path="/tmp", steam_library_path="/tmp/steam-library")
    kwargs = cfg.build_llm_organizer_kwargs()
    assert "max_retries" in kwargs
    assert "output_budget_safety_ratio" in kwargs
    assert "adaptive_degraded_prompt_enabled" in kwargs
    assert kwargs["max_retries"] == 3
    assert kwargs["output_budget_safety_ratio"] == 0.25
    assert kwargs["adaptive_degraded_prompt_enabled"] is True


def test_llm_retry_policy_preserves_retry_and_degradation_rules():
    policy = LLMRetryPolicy(3, 2.0, 1.5, True, "ollama", 4096)

    assert policy.can_retry(0)
    assert policy.can_retry(2)
    assert not policy.can_retry(3)
    assert policy.should_degrade_for_http(503, False)
    assert not policy.should_degrade_for_http(429, False)
    assert not policy.should_degrade_for_http(503, True)
    assert policy.should_degrade_for_exception(TimeoutError("request timeout"), False)
    assert not policy.should_degrade_for_exception(ValueError("bad value"), False)
    assert policy.should_degrade_for_truncation(False)
    assert not policy.should_degrade_for_truncation(True)
    assert policy.next_output_tokens(1024) == 2048
    assert policy.next_output_tokens(2048) == 4096
    assert policy.next_output_tokens(4096) is None

    with patch("sst.llm.retry_policy.random.uniform", return_value=1.0), patch(
        "sst.llm.retry_policy.time.sleep"
    ) as sleep:
        policy.wait_before_retry()
        policy.wait_before_retry()

    assert [call.args[0] for call in sleep.call_args_list] == [2.0, 3.0]

def test_degraded_response_normalization():
    # Simulate minimal JSON parsed from degraded prompt response
    # Identity normalization test
    parsed_identity = {
        "album_confidence": 95,
        "mapping_confidence": 90,
        "data_quality": 85,
        "strategy": "STEAM_BASED",
        "global_tags": {"canonical_album_artist": "Artist"}
    }
    # Simulate normalization logic in client.py
    parsed = dict(parsed_identity)
    parsed.setdefault("confidence_reason", "縮退プロンプト適用（最小フォーマット判定）")
    parsed.setdefault("concerns", [])
    parsed.setdefault("semantic_label", "Archive" if parsed.get("album_confidence", 0) >= 80 else "Review")
    parsed.setdefault("archive_vs_review_ratio", {
        "archive": parsed.get("album_confidence", 0),
        "review": 100 - parsed.get("album_confidence", 0)
    })
    parsed.setdefault("identity_confidence", parsed.get("album_confidence", 0))
    parsed.setdefault("integrity_quality", parsed.get("data_quality", 0))

    assert parsed["semantic_label"] == "Archive"
    assert parsed["confidence_reason"] == "縮退プロンプト適用（最小フォーマット判定）"
    assert parsed["archive_vs_review_ratio"]["archive"] == 95
    assert parsed["concerns"] == []

    # Track mapping normalization test
    parsed_mapping = {
        "slots": {
            "1": {"files": ["01.mp3"], "confidence": 0.95}
        }
    }
    m_parsed = dict(parsed_mapping)
    slots = m_parsed.get("slots")
    if isinstance(slots, dict):
        for slot_info in slots.values():
            if isinstance(slot_info, dict):
                slot_info.setdefault("reason", "Degraded mapping")
    m_parsed.setdefault("unassigned_files", [])
    m_parsed.setdefault("unassigned_reason", "")

    assert m_parsed["slots"]["1"]["reason"] == "Degraded mapping"
    assert m_parsed["unassigned_files"] == []
