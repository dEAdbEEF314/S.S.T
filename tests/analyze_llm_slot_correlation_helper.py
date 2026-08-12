import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Optional


SST_EVENT_RE = re.compile(r"LLM_REQUEST_(VRAM|DONE|FAIL|RELEASE)\s+(\{.*\})")
SST_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
# Supports native ISO timestamps and journalctl short-iso prefixes.
OLLAMA_TS_RE = re.compile(
    r"(?:^|\s)(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?(?:[+-]\d{2}:?\d{2}|Z)?)"
)
OLLAMA_SLOT_RE = re.compile(r"slot\s+([a-zA-Z_()]+):\s+id\s+(\d+)\s+\|\s+task\s+(-?\d+)")
OLLAMA_HTTP_RE = re.compile(r'\|\s+(\d{3})\s+\|.*POST\s+"(/api/chat|/api/tokenize)"')


@dataclass
class CorrelationEvent:
    source: str
    timestamp: Optional[datetime]
    label: str
    details: dict
    raw_line: str


def parse_sst_timestamp(line: str) -> Optional[datetime]:
    match = SST_TS_RE.match(line)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")


def parse_ollama_timestamp(line: str) -> Optional[datetime]:
    match = OLLAMA_TS_RE.search(line)
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    if " " in raw:
        raw = raw.replace(" ", "T", 1)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    elif re.search(r"[+-]\d{4}$", raw):
        raw = f"{raw[:-5]}{raw[-5:-2]}:{raw[-2:]}"
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_sst_events(lines: Iterable[str], app_id: Optional[int] = None) -> list[CorrelationEvent]:
    events: list[CorrelationEvent] = []
    for line in lines:
        match = SST_EVENT_RE.search(line)
        if not match:
            continue
        payload = json.loads(match.group(2))
        if app_id is not None and payload.get("app_id") != app_id:
            continue
        label = f"LLM_REQUEST_{match.group(1)}"
        events.append(
            CorrelationEvent(
                source="sst",
                timestamp=parse_sst_timestamp(line),
                label=label,
                details=payload,
                raw_line=line.rstrip(),
            )
        )
    return events


def parse_ollama_events(lines: Iterable[str]) -> list[CorrelationEvent]:
    events: list[CorrelationEvent] = []
    for line in lines:
        timestamp = parse_ollama_timestamp(line)
        slot_match = OLLAMA_SLOT_RE.search(line)
        if slot_match:
            events.append(
                CorrelationEvent(
                    source="ollama",
                    timestamp=timestamp,
                    label=f"slot_{slot_match.group(1)}",
                    details={
                        "slot_id": int(slot_match.group(2)),
                        "task_id": int(slot_match.group(3)),
                    },
                    raw_line=line.rstrip(),
                )
            )
            continue

        http_match = OLLAMA_HTTP_RE.search(line)
        if http_match:
            events.append(
                CorrelationEvent(
                    source="ollama",
                    timestamp=timestamp,
                    label="http_post",
                    details={
                        "status": int(http_match.group(1)),
                        "path": http_match.group(2),
                    },
                    raw_line=line.rstrip(),
                )
            )
            continue

        if "aborting completion request due to client closing the connection" in line:
            events.append(
                CorrelationEvent(
                    source="ollama",
                    timestamp=timestamp,
                    label="client_aborted",
                    details={},
                    raw_line=line.rstrip(),
                )
            )
    return events


def summarize_sst(events: list[CorrelationEvent]) -> dict:
    by_kind = Counter()
    wait_seconds: list[float] = []
    done_durations: list[float] = []
    inflight = 0
    peak_inflight = 0

    for event in sorted(events, key=lambda item: item.timestamp or datetime.min):
        details = event.details
        by_kind[(event.label, details.get("request_kind", "unknown"))] += 1
        if event.label == "LLM_REQUEST_VRAM":
            inflight += 1
            peak_inflight = max(peak_inflight, inflight)
            wait = details.get("wait_seconds")
            if isinstance(wait, (int, float)):
                wait_seconds.append(wait)
        elif event.label == "LLM_REQUEST_RELEASE":
            inflight = max(0, inflight - 1)
        elif event.label == "LLM_REQUEST_DONE":
            duration = details.get("duration_seconds")
            if isinstance(duration, (int, float)):
                done_durations.append(duration)

    return {
        "counts": by_kind,
        "peak_inflight": peak_inflight,
        "avg_wait_seconds": round(sum(wait_seconds) / len(wait_seconds), 3) if wait_seconds else None,
        "avg_done_seconds": round(sum(done_durations) / len(done_durations), 3) if done_durations else None,
    }


def summarize_ollama(events: list[CorrelationEvent]) -> dict:
    slot_ids = Counter()
    labels = Counter(event.label for event in events)
    http_statuses = Counter()
    for event in events:
        if "slot_id" in event.details:
            slot_ids[event.details["slot_id"]] += 1
        if event.label == "http_post":
            http_statuses[(event.details.get("path"), event.details.get("status"))] += 1

    return {
        "labels": labels,
        "slot_ids": slot_ids,
        "http_statuses": http_statuses,
    }


def _sst_wait_values(events: list[CorrelationEvent]) -> list[float]:
    return [
        float(event.details["wait_seconds"])
        for event in events
        if event.label == "LLM_REQUEST_VRAM"
        and isinstance(event.details.get("wait_seconds"), (int, float))
        and event.details.get("wait_seconds") != 0
    ]


def render_summary(sst_events: list[CorrelationEvent], ollama_events: list[CorrelationEvent], timeline_limit: int) -> str:
    sst_summary = summarize_sst(sst_events)
    ollama_summary = summarize_ollama(ollama_events)

    lines: list[str] = []
    observed_waits = _sst_wait_values(sst_events)
    avg_observed_wait = round(sum(observed_waits) / len(observed_waits), 3) if observed_waits else None
    lines.append("== SST Summary ==")
    lines.append(f"events: {len(sst_events)}")
    lines.append(f"peak_inflight_requests: {sst_summary['peak_inflight']}")
    lines.append(f"avg_wait_seconds_observed: {avg_observed_wait}")
    lines.append("wait_seconds_note: zero is treated as an unmeasured/reserved value")
    lines.append(f"avg_done_seconds: {sst_summary['avg_done_seconds']}")
    for (label, request_kind), count in sorted(sst_summary["counts"].items()):
        lines.append(f"- {label} / {request_kind}: {count}")

    lines.append("")
    lines.append("== Ollama Summary ==")
    lines.append(f"events: {len(ollama_events)}")
    lines.append(f"slot_ids_seen: {dict(ollama_summary['slot_ids'])}")
    for label, count in sorted(ollama_summary["labels"].items()):
        lines.append(f"- {label}: {count}")
    for (path, status), count in sorted(ollama_summary["http_statuses"].items()):
        lines.append(f"- http {status} {path}: {count}")

    lines.append("")
    lines.append("== Timeline ==")

    def _sort_key(event: CorrelationEvent):
        if event.timestamp is None:
            return (float("-inf"), event.source, event.label)
        if event.timestamp.tzinfo is None:
            ts_value = event.timestamp.replace(tzinfo=UTC).timestamp()
        else:
            ts_value = event.timestamp.astimezone(UTC).timestamp()
        return (ts_value, event.source, event.label)

    timeline = sorted(
        sst_events + ollama_events,
        key=_sort_key,
    )
    for event in timeline[:timeline_limit]:
        ts = event.timestamp.isoformat(sep=" ") if event.timestamp else "NO_TIMESTAMP"
        if event.source == "sst":
            details = event.details
            lines.append(
                f"{ts} | SST | {event.label} | kind={details.get('request_kind')} units={details.get('request_units')} "
                f"wait={details.get('wait_seconds')} dur={details.get('duration_seconds')} reserved={details.get('reserved_bytes')}"
            )
        else:
            lines.append(f"{ts} | OLLAMA | {event.label} | {event.details}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate SST structured LLM logs with Ollama slot logs.")
    parser.add_argument("--sst-log", required=True, help="Path to SST log file (e.g. logs/SST_DEBUG_*.log)")
    parser.add_argument("--ollama-log", required=True, help="Path to Ollama log export captured with journalctl -o short-iso")
    parser.add_argument("--app-id", type=int, default=None, help="Optional AppID filter for SST structured logs")
    parser.add_argument("--timeline-limit", type=int, default=60, help="Maximum number of timeline rows to print")
    args = parser.parse_args()

    sst_log_path = Path(args.sst_log)
    ollama_log_path = Path(args.ollama_log)
    if not sst_log_path.exists():
        raise SystemExit(f"SST log not found: {sst_log_path}")
    if not ollama_log_path.exists():
        raise SystemExit(f"Ollama log not found: {ollama_log_path}")

    sst_events = parse_sst_events(sst_log_path.read_text(encoding="utf-8").splitlines(), app_id=args.app_id)
    ollama_events = parse_ollama_events(ollama_log_path.read_text(encoding="utf-8").splitlines())
    print(render_summary(sst_events, ollama_events, timeline_limit=args.timeline_limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())