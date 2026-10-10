#!/usr/bin/env python3
"""Create and summarize route-stratified completeness audit samples."""

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

ALBUM_LABELS = (
    "product_identity_correct",
    "slot_structure_correct",
    "critical_metadata_correct",
)
DERIVED_AUDIO_LABEL = "all_sampled_audio_matches_tags"
TRACK_LABEL = "audio_content_matches_title"


def latest_rows(db_path: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT pa.app_id, pa.album_name, pa.status, pa.metadata_json
        FROM processed_albums AS pa
        JOIN (
            SELECT app_id, MAX(rowid) AS latest_rowid
            FROM processed_albums
            GROUP BY app_id
        ) AS latest ON latest.latest_rowid = pa.rowid
        ORDER BY CAST(pa.app_id AS INTEGER)
        """
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def _parse_metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _route(meta: dict[str, Any]) -> str:
    diagnostics = meta.get("diagnostics") or {}
    return str(meta.get("processing_route") or diagnostics.get("processing_route") or "MISSING")


def _slot_key(track: dict[str, Any]) -> tuple[str, str]:
    tags = track.get("tags") or {}
    disc = str(tags.get("disc_number") or "1").split("/")[0].strip().lstrip("0") or "1"
    number = str(tags.get("track_number") or "0").split("/")[0].strip().lstrip("0") or "0"
    return disc, number


def _stable_rank(seed: int, app_id: Any, discriminator: str) -> str:
    payload = f"{seed}:{app_id}:{discriminator}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_zip_member(value: Any) -> str | None:
    if not value:
        return None
    member = PurePosixPath(str(value).replace("\\", "/"))
    if member.is_absolute() or ".." in member.parts:
        return None
    return member.as_posix()


def build_sample_manifest(
    rows: list[dict[str, Any]],
    *,
    per_stratum: int = 5,
    tracks_per_album: int = 3,
    seed: int = 20261010,
) -> dict[str, Any]:
    if per_stratum < 1 or tracks_per_album < 1:
        raise ValueError("sample sizes must be positive")

    strata: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        meta = _parse_metadata(row)
        strata[(_route(meta), str(row.get("status") or "unknown"))].append(row)

    selected = []
    stratum_counts = []
    for (route, status), group in sorted(strata.items()):
        ordered = sorted(
            group,
            key=lambda row: _stable_rank(seed, row.get("app_id"), f"album:{route}:{status}"),
        )
        chosen = ordered[:per_stratum]
        stratum_counts.append(
            {
                "route": route,
                "status": status,
                "population": len(group),
                "sampled": len(chosen),
            }
        )
        for row in chosen:
            meta = _parse_metadata(row)
            tracks = meta.get("tracks") or []
            expected_titles: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
            for slot in (meta.get("steam_info") or {}).get("store_tracklist") or []:
                disc = str(slot.get("disc", 1)).split("/")[0].strip().lstrip("0") or "1"
                number = str(slot.get("number", slot.get("track_number", "0"))).split("/")[0].strip().lstrip("0") or "0"
                expected_titles[(disc, number)].append(str(slot.get("title") or slot.get("name") or ""))

            ranked_tracks = sorted(
                tracks,
                key=lambda track: _stable_rank(
                    seed,
                    row.get("app_id"),
                    "track:" + "_".join(_slot_key(track)) + ":" + str(track.get("file_path") or ""),
                ),
            )
            sampled_tracks = []
            for track in ranked_tracks[:tracks_per_album]:
                key = _slot_key(track)
                tags = track.get("tags") or {}
                sampled_tracks.append(
                    {
                        "slot_key": f"{key[0]}_{key[1]}",
                        "canonical_titles": expected_titles.get(key, []),
                        "tagged_title": str(tags.get("title") or ""),
                        "title_source": str(track.get("title_source") or "MISSING"),
                        "source_format": str(track.get("source_format") or "NOT_RECORDED"),
                        "zip_member": _safe_zip_member(track.get("file_path")),
                        TRACK_LABEL: None,
                        "reviewer_notes": "",
                    }
                )
            selected.append(
                {
                    "app_id": row.get("app_id"),
                    "album_name": str(row.get("album_name") or ""),
                    "route": _route(meta),
                    "status": str(row.get("status") or "unknown"),
                    "track_count": len(tracks),
                    "sampled_track_count": len(sampled_tracks),
                    "title_source_counts": dict(
                        Counter(str(track.get("title_source") or "MISSING") for track in tracks)
                    ),
                    "audit_labels": {label: None for label in ALBUM_LABELS},
                    "sampled_tracks": sampled_tracks,
                    "reviewer_notes": "",
                }
            )

    selected.sort(key=lambda item: (item["route"], item["status"], int(item["app_id"])))
    return {
        "schema_version": 1,
        "purpose": "Manual route-stratified audit; null labels are unmeasured, not correct.",
        "seed": seed,
        "per_route_status_stratum": per_stratum,
        "tracks_per_album": tracks_per_album,
        "label_definitions": {
            "product_identity_correct": "The physical audio belongs to the Steam soundtrack product, or the verified MBZ release when that route is selected.",
            "slot_structure_correct": "Disc, track number, title order, and product track coverage match the route's authoritative tracklist.",
            DERIVED_AUDIO_LABEL: "Automatically true only when every sampled track label is true; false if any is false; otherwise unrated.",
            "critical_metadata_correct": "Album/artist/year and sampled track credits are factually supported by their recorded source.",
            TRACK_LABEL: "The sampled audio member's content matches the shown tagged title.",
        },
        "population_count": len(rows),
        "strata": stratum_counts,
        "samples": selected,
    }


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if trials <= 0:
        return None
    proportion = successes / trials
    denominator = 1 + z * z / trials
    center = (proportion + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / trials + z * z / (4 * trials * trials)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _metric(values: list[bool], unrated: int) -> dict[str, Any]:
    trials = len(values)
    successes = sum(values)
    interval = wilson_interval(successes, trials)
    return {
        "successes": successes,
        "failures": trials - successes,
        "rated": trials,
        "unrated": unrated,
        "rate_pct": round(successes / trials * 100, 1) if trials else None,
        "wilson_95_pct": [round(bound * 100, 1) for bound in interval] if interval else None,
    }


def analyze_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    by_route: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_stratum: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sample in manifest.get("samples", []):
        route = str(sample.get("route") or "MISSING")
        status = str(sample.get("status") or "unknown")
        by_route[route].append(sample)
        by_stratum[(route, status)].append(sample)

    def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
        summary = {}
        for label in ALBUM_LABELS:
            answers = [item.get("audit_labels", {}).get(label) for item in samples]
            rated = [answer for answer in answers if isinstance(answer, bool)]
            summary[label] = _metric(rated, len(answers) - len(rated))
        derived_audio_answers = []
        for item in samples:
            item_answers = [
                track.get(TRACK_LABEL)
                for track in item.get("sampled_tracks", [])
            ]
            if item_answers and all(isinstance(answer, bool) for answer in item_answers):
                derived_audio_answers.append(all(item_answers))
            else:
                derived_audio_answers.append(None)
        rated_audio_answers = [
            answer for answer in derived_audio_answers if isinstance(answer, bool)
        ]
        summary[DERIVED_AUDIO_LABEL] = _metric(
            rated_audio_answers,
            len(derived_audio_answers) - len(rated_audio_answers),
        )
        track_answers = [
            track.get(TRACK_LABEL)
            for item in samples
            for track in item.get("sampled_tracks", [])
        ]
        rated_track_answers = [answer for answer in track_answers if isinstance(answer, bool)]
        summary[TRACK_LABEL] = _metric(
            rated_track_answers,
            len(track_answers) - len(rated_track_answers),
        )
        summary["album_sample_count"] = len(samples)
        return summary

    metrics = {
        route: summarize_samples(samples)
        for route, samples in sorted(by_route.items())
    }
    stratum_metrics = {
        f"{route}|{status}": summarize_samples(samples)
        for (route, status), samples in sorted(by_stratum.items())
    }

    return {
        "schema_version": manifest.get("schema_version"),
        "seed": manifest.get("seed"),
        "population_count": manifest.get("population_count"),
        "sample_count": len(manifest.get("samples", [])),
        "route_metrics": metrics,
        "stratum_metrics": stratum_metrics,
        "interpretation": "Rates use only explicit true/false labels. Unrated items are excluded from the numerator and denominator; they are not assumed correct.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample_parser = subparsers.add_parser("sample", help="Create a reproducible manual audit sample")
    sample_parser.add_argument("--db", default="data/sst_local_state.db")
    sample_parser.add_argument("--per-stratum", type=int, default=5)
    sample_parser.add_argument("--tracks-per-album", type=int, default=3)
    sample_parser.add_argument("--seed", type=int, default=20261010)
    sample_parser.add_argument("--out", required=True)
    analyze_parser = subparsers.add_parser("analyze", help="Summarize completed manual labels")
    analyze_parser.add_argument("--input", required=True)
    analyze_parser.add_argument("--out", required=True)
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "sample":
        result = build_sample_manifest(
            latest_rows(args.db),
            per_stratum=args.per_stratum,
            tracks_per_album=args.tracks_per_album,
            seed=args.seed,
        )
    else:
        manifest = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = analyze_manifest(manifest)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.command} result to {output}")


if __name__ == "__main__":
    main()
