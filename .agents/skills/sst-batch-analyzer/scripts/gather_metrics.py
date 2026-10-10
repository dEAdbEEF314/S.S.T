#!/usr/bin/env python3
"""S.S.T Batch Metrics Gatherer

Collects aggregate metrics from the latest batch run and writes a structured
JSON summary for use by the sst-batch-analyzer skill.

Usage:
    uv run python .agents/skills/sst-batch-analyzer/scripts/gather_metrics.py [--db PATH] [--log-dir PATH] [--out PATH]
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def get_latest_rows(db_path: str) -> list[dict]:
    """Get the latest row per AppID from processed_albums."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT pa.*
        FROM processed_albums pa
        INNER JOIN (
            SELECT app_id, MAX(rowid) as max_rowid
            FROM processed_albums
            GROUP BY app_id
        ) latest ON pa.app_id = latest.app_id AND pa.rowid = latest.max_rowid
        ORDER BY pa.app_id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def parse_metadata(row: dict) -> dict:
    """Parse metadata_json from a row."""
    raw = row.get("metadata_json", "{}")
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_review_causes(message: str) -> list[str]:
    """Extract individual cause keywords from a validator message."""
    causes = []
    keywords = [
        "Steam Slots Missing", "Unassigned Files", "Output Track Count Mismatch",
        "Duplicates", "Steam Slots Unexpected", "Audio quality warning",
        "Dirty Tags", "Low Confidence", "LLM Rejected Slots",
        "LLM Duplicate Assignment", "Track#0", "Unknown Title",
        "CRITICAL: Audio Source Error", "Steam Tracklist Missing",
        "Album confidence too low", "Mapping confidence too low",
        "Data quality too low", "Duplicate Titles",
        "Official Title Mismatch",
    ]
    for kw in keywords:
        if kw in (message or ""):
            causes.append(kw)
    return causes


def classify_review_pattern(meta: dict, message: str) -> str:
    """Classify a Review item's root cause pattern."""
    audit = meta.get("audit", {})
    inp = audit.get("input_file_count", 0) or 0
    steam = audit.get("steam_expected_slots", 0) or 0
    has_dup = "Duplicates" in (message or "")
    has_unassigned = "Unassigned Files" in (message or "")
    has_missing = "Steam Slots Missing" in (message or "")
    has_title_mismatch = "Official Title Mismatch" in (message or "")

    if has_title_mismatch:
        return "STRUCTURAL"
    if "Audio quality warning" in (message or "") and not has_missing and not has_unassigned:
        return "AUDIO_QUALITY"
    if ("Low Confidence" in (message or "") or "Album confidence too low" in (message or "")) and not has_missing:
        return "LOW_CONFIDENCE"
    if has_dup and has_unassigned and not has_missing:
        return "FORMAT_VARIANT"
    if has_missing and has_unassigned and inp > steam * 1.5:
        return "EXCESS_INPUT"
    if has_missing and has_unassigned:
        return "SLOT_MAPPING_FAIL"
    if "Dirty Tags" in (message or ""):
        return "DIRTY_TAGS"
    if "Steam Tracklist Missing" in (message or ""):
        return "STRUCTURAL"
    return "OTHER"


def parse_llm_log(log_dir: str, latest_rows: list[dict] | None = None) -> dict:
    """Parse LLM events, correlating them to each AppID's latest saved attempt."""
    log_path = Path(log_dir)
    log_files = sorted(log_path.glob("SST_DEBUG_*.log"))
    if not log_files:
        return {"error": "No log files found", "by_kind": {}, "app_ids": [], "total": 0}

    timestamp_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)")
    start_pattern = re.compile(r"PIPELINE_EVENT app_id=(\d+) stage=PROCESS_START")

    def parse_timestamp(line: str) -> datetime | None:
        match = timestamp_pattern.search(line)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f").astimezone()
        except ValueError:
            return None

    latest_processed_at: dict[int, datetime] = {}
    if latest_rows is not None:
        for row in latest_rows:
            meta = parse_metadata(row)
            processed_at = meta.get("processed_at")
            if not processed_at:
                continue
            try:
                latest_processed_at[int(row["app_id"])] = datetime.fromisoformat(
                    str(processed_at)
                ).astimezone()
            except (TypeError, ValueError):
                continue

    starts_by_app: defaultdict[int, list[datetime]] = defaultdict(list)
    if latest_rows is not None:
        for log_file in log_files:
            with open(log_file, "r", errors="replace") as f:
                for line in f:
                    match = start_pattern.search(line)
                    timestamp = parse_timestamp(line) if match else None
                    if match and timestamp:
                        starts_by_app[int(match.group(1))].append(timestamp)

    attempt_windows: dict[int, tuple[datetime, datetime]] = {}
    unmatched_app_ids = set()
    for app_id, processed_at in latest_processed_at.items():
        eligible_starts = [start for start in starts_by_app[app_id] if start <= processed_at]
        if not eligible_starts:
            unmatched_app_ids.add(app_id)
            continue
        start = max(eligible_starts)
        if processed_at - start <= timedelta(hours=24):
            attempt_windows[app_id] = (start, processed_at)
        else:
            unmatched_app_ids.add(app_id)

    by_kind: dict[str, dict] = {}
    app_ids: set[int] = set()
    event_markers = (
        "LLM_REQUEST_DONE",
        "LLM_REQUEST_FAIL",
        "LLM_RESPONSE_SHAPE",
        "LLM_RESPONSE_JSON_REPAIRED",
    )

    for log_file in log_files:
        with open(log_file, "r", errors="replace") as f:
            for line in f:
                marker = next((item for item in event_markers if item in line), None)
                if marker is None:
                    continue
                idx = line.find("{")
                timestamp = parse_timestamp(line)
                if idx == -1:
                    continue
                try:
                    d = json.loads(line[idx:])
                    app_id = int(d.get("app_id"))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

                if latest_rows is not None:
                    window = attempt_windows.get(app_id)
                    if not window or not timestamp or not window[0] <= timestamp <= window[1]:
                        continue

                kind = d.get("request_kind", "unknown")
                app_ids.add(app_id)

                if kind not in by_kind:
                    by_kind[kind] = {
                        "count": 0, "total_duration_s": 0.0,
                        "total_tokens": 0, "cache_hits": 0,
                        "success_count": 0, "failure_count": 0,
                        "attempt_count": 0, "empty_content_attempts": 0,
                        "attempt_prompt_tokens": 0, "attempt_completion_tokens": 0,
                        "json_repair_count": 0,
                    }
                stats = by_kind[kind]
                if marker == "LLM_RESPONSE_JSON_REPAIRED":
                    stats["json_repair_count"] += len(d.get("repairs") or [])
                elif marker == "LLM_RESPONSE_SHAPE":
                    stats["attempt_count"] += 1
                    stats["attempt_prompt_tokens"] += d.get("prompt_tokens") or 0
                    stats["attempt_completion_tokens"] += d.get("completion_tokens") or 0
                    if d.get("content_empty") is True:
                        stats["empty_content_attempts"] += 1
                else:
                    stats["count"] += 1
                    stats["total_duration_s"] += d.get("duration_seconds", 0)
                    if marker == "LLM_REQUEST_DONE":
                        stats["success_count"] += 1
                        stats["total_tokens"] += d.get("total_tokens", 0)
                        if d.get("cache_hit"):
                            stats["cache_hits"] += 1
                    else:
                        stats["failure_count"] += 1

    for kind, stats in by_kind.items():
        stats["avg_duration_s"] = round(stats["total_duration_s"] / stats["count"], 1) if stats["count"] else 0
        stats["cache_hit_rate"] = round(stats["cache_hits"] / stats["count"] * 100) if stats["count"] else 0

    return {
        "log_files_scanned": [path.name for path in log_files],
        "correlation_basis": "latest PROCESS_START through processed_at" if latest_rows is not None else "all parseable events",
        "unmatched_app_id_count": len(unmatched_app_ids),
        "by_kind": by_kind,
        "app_ids": sorted(app_ids),
        "total": sum(s["count"] for s in by_kind.values()),
    }


def main():
    parser = argparse.ArgumentParser(description="S.S.T Batch Metrics Gatherer")
    parser.add_argument("--db", default="data/sst_local_state.db", help="Path to SQLite DB")
    parser.add_argument("--log-dir", default="logs", help="Path to log directory")
    parser.add_argument("--out", default=".agents/skills/sst-batch-analyzer/scratch/metrics.json",
                        help="Output JSON path")
    args = parser.parse_args()

    rows = get_latest_rows(args.db)
    if not rows:
        print("No rows found in processed_albums", file=sys.stderr)
        sys.exit(1)

    # Aggregate metrics
    status_counts: Counter = Counter()
    strategy_counts: defaultdict = defaultdict(lambda: {"archive": 0, "review": 0, "total": 0})
    review_cause_counts: Counter = Counter()
    review_items: list[dict] = []
    review_patterns: Counter = Counter()
    archive_confidence: Counter = Counter()

    for row in rows:
        meta = parse_metadata(row)
        status = row.get("status", "unknown")
        strategy = meta.get("strategy", "UNKNOWN")
        message = meta.get("message", "")
        audit = meta.get("audit", {})

        status_counts[status] += 1
        strategy_counts[strategy]["total"] += 1
        strategy_counts[strategy][status] += 1

        if status == "archive":
            conf = meta.get("confidence", meta.get("album_confidence", "N/A"))
            archive_confidence[str(conf)] += 1

        if status == "review":
            causes = extract_review_causes(message)
            for c in causes:
                review_cause_counts[c] += 1

            pattern = classify_review_pattern(meta, message)
            review_patterns[pattern] += 1

            review_items.append({
                "app_id": row["app_id"],
                "album_name": row.get("album_name", ""),
                "message": message,
                "strategy": strategy,
                "pattern": pattern,
                "input_files": audit.get("input_file_count", 0),
                "steam_expected": audit.get("steam_expected_slots", 0),
                "final_adopted": audit.get("final_adopted_slots", 0),
                "unassigned_count": audit.get("unassigned_file_count", 0),
                "duplicate_slots": audit.get("final_duplicate_slots", 0),
                "multi_variant": audit.get("multi_variant_slot_count", 0),
            })

    llm_stats = parse_llm_log(args.log_dir, rows)

    total = len(rows)
    archive_count = status_counts.get("archive", 0)
    review_count = status_counts.get("review", 0)

    result = {
        "summary": {
            "total_app_ids": total,
            "archive_count": archive_count,
            "review_count": review_count,
            "archive_rate_pct": round(archive_count / total * 100, 1) if total else 0,
            "review_rate_pct": round(review_count / total * 100, 1) if total else 0,
        },
        "strategy_distribution": dict(strategy_counts),
        "archive_confidence_distribution": dict(archive_confidence),
        "review_cause_counts": dict(review_cause_counts.most_common()),
        "review_pattern_counts": dict(review_patterns.most_common()),
        "review_items": review_items,
        "llm_stats": llm_stats,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Metrics written to {out_path}")
    print(f"  Total: {total}, Archive: {archive_count} ({result['summary']['archive_rate_pct']}%), "
          f"Review: {review_count} ({result['summary']['review_rate_pct']}%)")
    print(f"  Review patterns: {dict(review_patterns.most_common())}")
    print(f"  LLM requests: {llm_stats['total']} across {len(llm_stats['app_ids'])} AppIDs")


if __name__ == "__main__":
    main()
