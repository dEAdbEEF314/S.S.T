from tests.analyze_llm_slot_correlation_helper import parse_ollama_events, parse_sst_events, render_summary


def test_parse_sst_events_filters_by_app_id():
    lines = [
        '2026-07-10 11:00:00,001 - sst.llm - INFO - LLM_REQUEST_VRAM {"app_id": 1, "request_kind": "identity", "request_units": 10, "wait_seconds": 0.1, "reserved_bytes": 4096}',
        '2026-07-10 11:00:01,001 - sst.llm - INFO - LLM_REQUEST_DONE {"app_id": 2, "request_kind": "track_mapping", "request_units": 2, "duration_seconds": 1.2}',
    ]

    events = parse_sst_events(lines, app_id=1)

    assert len(events) == 1
    assert events[0].label == "LLM_REQUEST_VRAM"
    assert events[0].details["app_id"] == 1


def test_parse_ollama_events_parses_slot_and_http_lines():
    lines = [
        '2026-01-01T00:00:00+00:00 localhost ollama[1234]: slot launch_slot_: id  0 | task 100001 | processing task, is_child = 0',
        '2026-01-01T00:00:04+00:00 localhost ollama[1234]: [GIN] 2026/01/01 - 00:00:04 | 200 | 4s | 127.0.0.1 | POST     "/api/chat"',
        '2026-01-01T00:00:10+00:00 localhost ollama[1234]: time=2026-01-01T00:00:10.000+00:00 level=INFO source=llama_server.go:1491 msg="aborting completion request due to client closing the connection"',
    ]

    events = parse_ollama_events(lines)

    assert [event.label for event in events] == ["slot_launch_slot_", "http_post", "client_aborted"]
    assert events[0].details["slot_id"] == 0
    assert events[1].details["status"] == 200


def test_render_summary_contains_peak_and_slot_ids():
    sst_lines = [
        '2026-07-10 11:00:00,001 - sst.llm - INFO - LLM_REQUEST_VRAM {"app_id": 1, "request_kind": "identity", "request_units": 10, "wait_seconds": 0.1, "reserved_bytes": 4096}',
        '2026-07-10 11:00:01,001 - sst.llm - INFO - LLM_REQUEST_DONE {"app_id": 1, "request_kind": "identity", "request_units": 10, "duration_seconds": 1.2, "reserved_bytes": 4096}',
        '2026-07-10 11:00:01,500 - sst.llm - INFO - LLM_REQUEST_RELEASE {"app_id": 1, "request_kind": "identity", "request_units": 10, "released_bytes": 4096}',
    ]
    ollama_lines = [
        '2026-01-01T00:00:00+00:00 localhost ollama[1234]: slot launch_slot_: id  0 | task 100001 | processing task, is_child = 0',
    ]

    summary = render_summary(parse_sst_events(sst_lines), parse_ollama_events(ollama_lines), timeline_limit=10)

    assert "peak_inflight_requests: 1" in summary
    assert "slot_ids_seen: {0: 1}" in summary