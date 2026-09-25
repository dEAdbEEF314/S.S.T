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
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["num_retries"] == 0


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