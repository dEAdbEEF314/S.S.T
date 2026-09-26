import importlib.util
import json
from pathlib import Path

import pytest


def _load_metrics_module():
    script_path = Path(__file__).resolve().parents[1] / ".agents/skills/sst-batch-analyzer/scripts/gather_metrics.py"
    if not script_path.is_file():
        pytest.skip("Local batch-analyzer skill is not installed in this checkout")
    spec = importlib.util.spec_from_file_location("sst_batch_metrics", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load batch metrics script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_llm_log_counts_failures_and_empty_response_attempts(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "SST_DEBUG_fixture.log"
    events = [
        ("LLM_RESPONSE_SHAPE", {
            "app_id": 12001, "request_kind": "identity", "content_empty": True,
            "prompt_tokens": 10, "completion_tokens": 5,
        }),
        ("LLM_RESPONSE_SHAPE", {
            "app_id": 12001, "request_kind": "identity", "content_empty": True,
            "prompt_tokens": 10, "completion_tokens": 5,
        }),
        ("LLM_REQUEST_FAIL", {
            "app_id": 12001, "request_kind": "identity", "duration_seconds": 20.0,
        }),
        ("LLM_RESPONSE_SHAPE", {
            "app_id": 12002, "request_kind": "track_mapping", "content_empty": False,
        }),
        ("LLM_REQUEST_DONE", {
            "app_id": 12002, "request_kind": "track_mapping", "duration_seconds": 3.0,
            "total_tokens": 25, "cache_hit": False,
        }),
    ]
    log_path.write_text("".join(f"INFO - {marker} {json.dumps(event)}\n" for marker, event in events))

    result = _load_metrics_module().parse_llm_log(str(log_dir))

    assert result["total"] == 2
    assert result["app_ids"] == [12001, 12002]
    identity = result["by_kind"]["identity"]
    assert identity["count"] == 1
    assert identity["failure_count"] == 1
    assert identity["success_count"] == 0
    assert identity["attempt_count"] == 2
    assert identity["empty_content_attempts"] == 2
    assert identity["attempt_prompt_tokens"] == 20
    assert identity["attempt_completion_tokens"] == 10
    mapping = result["by_kind"]["track_mapping"]
    assert mapping["count"] == 1
    assert mapping["success_count"] == 1
    assert mapping["failure_count"] == 0