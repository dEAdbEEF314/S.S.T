from unittest.mock import patch
from types import SimpleNamespace

from sst.llm import client as llm_client_module
from sst.llm.client import LLMClient


def _build_client(base_url: str = "auto") -> LLMClient:
    client = LLMClient(
        api_key="test-key",
        base_url=base_url,
        model="openai/gpt-4o-mini",
        llm_backend="LITELLM",
        request_timeout=12,
    )
    client.limiter.acquire = lambda messages: True
    return client


def test_litellm_backend_uses_sdk_and_parses_openai_response(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }

    monkeypatch.setattr(llm_client_module.litellm, "completion", fake_completion)
    client = _build_client()

    result, log_entry = client.call_llm(42, "Return JSON", request_kind="identity")

    assert result == {"ok": True}
    assert log_entry["meta"]["prompt_eval_count"] == 12
    assert log_entry["meta"]["eval_count"] == 5
    assert len(calls) == 1
    assert calls[0]["model"] == "openai/gpt-4o-mini"
    assert calls[0]["api_key"] == "test-key"
    assert calls[0]["api_base"] is None
    assert calls[0]["timeout"] == 12
    assert "response_format" not in calls[0]
    assert calls[0]["extra_body"] == {"think": False}
    assert calls[0]["num_retries"] == 0


def test_litellm_empty_content_logs_response_shape_without_text(monkeypatch):
    secret_reasoning = "private reasoning text"
    monkeypatch.setattr(
        llm_client_module.litellm,
        "completion",
        lambda **kwargs: {
            "choices": [{
                "message": {"content": "", "reasoning_content": secret_reasoning},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        },
    )
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda _: None)
    client = _build_client()

    with patch("sst.llm.client.logger.info") as mock_info:
        result, log_entry = client.call_llm(42, "Return JSON", request_kind="identity")

    assert result is None
    assert log_entry["error"] == "Empty response"
    response_shape = log_entry["meta"]["response_shape"]
    assert response_shape["message_keys"] == ["content", "reasoning_content"]
    assert response_shape["content_empty"] is True
    assert response_shape["content_length"] == 0
    assert response_shape["reasoning_content_present"] is True
    assert response_shape["reasoning_content_length"] == len(secret_reasoning)
    assert response_shape["completion_tokens"] == 5
    shape_logs = [
        call.args[1]
        for call in mock_info.call_args_list
        if call.args[0] == "LLM_RESPONSE_SHAPE %s"
    ]
    assert shape_logs
    assert all(secret_reasoning not in logged for logged in shape_logs)


def test_litellm_backend_uses_custom_api_base(monkeypatch):
    calls = []
    monkeypatch.setattr(
        llm_client_module.litellm,
        "completion",
        lambda **kwargs: calls.append(kwargs) or {
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
        },
    )
    client = _build_client("https://litellm.example/v1")

    result, _ = client.call_llm(42, "Return JSON")

    assert result == {"ok": True}
    assert calls[0]["api_base"] == "https://litellm.example/v1"


def test_litellm_backend_preserves_ollama_provider_and_alias(monkeypatch):
    calls = []
    monkeypatch.setattr(
        llm_client_module.litellm,
        "completion",
        lambda **kwargs: calls.append(kwargs) or {
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
        },
    )
    client = _build_client("http://litellm.example/v1")
    client.model = "ollama/local-ornith-9B"

    result, _ = client.call_llm(42, "Return JSON")

    assert result == {"ok": True}
    assert calls[0]["model"] == "ollama/local-ornith-9B"
    assert "response_format" not in calls[0]


def test_litellm_availability_defers_provider_validation(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected HTTP probe")),
    )

    assert _build_client().check_availability() is True


def test_litellm_backend_marks_length_finish_as_truncated(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.litellm,
        "completion",
        lambda **kwargs: {
            "choices": [{"message": {"content": '{"partial":'}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        },
    )
    client = _build_client()

    result, log_entry = client.call_llm(42, "Return JSON")

    assert result is None
    assert log_entry["error_code"] == "response_truncated"
    assert log_entry["meta"]["done_reason"] == "length"


def test_ollama_backend_disables_thinking_by_default(monkeypatch):
    calls = []
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "message": {"content": '{"ok": true}'},
            "done_reason": "stop",
            "eval_count": 5,
        },
        text="",
    )
    monkeypatch.setattr(
        llm_client_module.requests,
        "post",
        lambda *args, **kwargs: calls.append(kwargs) or response,
    )
    client = LLMClient(
        api_key="test-key",
        base_url="http://ollama.example",
        model="test-model",
        llm_backend="OLLAMA",
    )

    result, _ = client.call_llm(42, "Return JSON")

    assert result == {"ok": True}
    assert calls[0]["json"]["think"] is False