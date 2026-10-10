from typing import Any, Dict, List

from ..models import SteamMetadata
from ..track_grouper import TrackManager


def _build_format_selection_audit(
    slot_variant_index: Dict[Any, Any],
    processed_tracks_meta: List[Dict[str, Any]],
) -> Dict[str, Any]:
    priorities = TrackManager.get_audio_format_priority()
    selected_by_slot = {
        str(track.get("slot_key")): str(track.get("source_format") or "").lower()
        for track in processed_tracks_meta
        if track.get("slot_key")
    }
    slot_records = []

    for slot_key, variants in slot_variant_index.items():
        if not isinstance(slot_key, tuple) or len(slot_key) != 2:
            continue
        disc_number, track_number = slot_key
        if not str(track_number).isdigit():
            continue

        normalized_slot = f"{disc_number}_{int(track_number)}"
        format_counts: Dict[str, int] = {}
        for variant in variants:
            file_format = str(variant.get("format") or "unknown").lower()
            format_counts[file_format] = format_counts.get(file_format, 0) + 1

        ordered_formats = sorted(
            format_counts.items(),
            key=lambda item: priorities.index(item[0]) if item[0] in priorities else len(priorities),
        )
        best_format = ordered_formats[0][0] if ordered_formats else None
        selected_format = selected_by_slot.get(normalized_slot) or None
        matches_best = selected_format == best_format if selected_format else None
        slot_records.append(
            {
                "slot_key": normalized_slot,
                "candidate_count": sum(format_counts.values()),
                "candidate_formats": [
                    {
                        "format": file_format,
                        "count": count,
                        "priority_rank": priorities.index(file_format)
                        if file_format in priorities
                        else len(priorities),
                    }
                    for file_format, count in ordered_formats
                ],
                "best_available_format": best_format,
                "selected_source_format": selected_format,
                "selection_matches_best": matches_best,
            }
        )

    slot_records.sort(key=lambda item: tuple(int(part) for part in item["slot_key"].split("_")))
    return {
        "selection_priority": priorities,
        "candidate_slot_count": len(slot_records),
        "verified_slot_count": sum(item["selection_matches_best"] is True for item in slot_records),
        "mismatch_slot_count": sum(item["selection_matches_best"] is False for item in slot_records),
        "unverifiable_slot_count": sum(item["selection_matches_best"] is None for item in slot_records),
        "slots": slot_records,
    }


def _build_field_provenance_audit(
    processed_tracks_meta: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fields = (
        "title",
        "artist",
        "album",
        "album_artist",
        "year",
        "track_number",
        "disc_number",
        "genre",
        "grouping",
        "comment",
        "composer",
        "language",
        "steam_appid",
        "apic",
    )
    counts: Dict[str, Dict[str, int]] = {field: {} for field in fields}
    for track in processed_tracks_meta:
        provenance = track.get("field_provenance") or {}
        for field in fields:
            source = provenance.get(field, "NOT_RECORDED")
            if isinstance(source, list):
                source = "+".join(str(item) for item in source) or "NOT_RECORDED"
            source_name = str(source or "NOT_RECORDED")
            counts[field][source_name] = counts[field].get(source_name, 0) + 1
    return {
        "track_count": len(processed_tracks_meta),
        "fields": counts,
    }


def build_album_summary_metadata(
    *,
    app_id: int,
    steam_meta: SteamMetadata,
    status: str,
    processing_route: str,
    message: str,
    score: Any,
    quality: Any,
    mapping_confidence: Any,
    archive_vs_review_ratio: Any,
    reason: str,
    processed_at: str,
    processed_tracks_meta: List[Dict[str, Any]],
    final_duplicate_slot_count: int,
    llm_log: Dict[str, Any],
    all_files_count: int,
    adopted_file_count: int,
    unassigned_manifest: List[Dict[str, Any]],
    artifact_issues: List[str],
    track_groups: Dict[Any, Any],
    slot_variant_index: Dict[Any, Any],
    io_retry_count: int,
    io_retry_logs: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    multi_variant_slot_count = sum(
        1 for variants in slot_variant_index.values() if len(variants) > 1
    )
    llm_diagnostics = llm_log.get("diagnostics") or {}
    deferred_copy_diagnostics = {
        key: llm_diagnostics.get(key, default)
        for key, default in (
            ("deferred_copy_count", 0),
            ("deferred_copy_success_count", 0),
            ("deferred_copy_failure_count", 0),
            ("deferred_copy_failures", []),
        )
    }
    failed_copy_logs = [
        log for log in io_retry_logs if log.get("final_state") == "failed"
    ]
    successful_copy_logs = [
        log for log in io_retry_logs if log.get("final_state") != "failed"
    ][:5]
    audit_copy_logs = failed_copy_logs + successful_copy_logs
    format_selection_audit = _build_format_selection_audit(
        slot_variant_index,
        processed_tracks_meta,
    )
    field_provenance_audit = _build_field_provenance_audit(processed_tracks_meta)
    return {
        "app_id": app_id,
        "album_name": steam_meta.name,
        "status": status,
        "processing_route": processing_route,
        "message": message,
        "confidence_score": score,
        "album_confidence": score,
        "mapping_confidence": mapping_confidence,
        "data_quality": quality,
        "integrity_quality": quality,
        "archive_vs_review_ratio": archive_vs_review_ratio,
        "audit": {
            "steam_expected_slots": len(steam_meta.store_tracklist or []),
            "final_adopted_slots": len(processed_tracks_meta),
            "final_duplicate_slots": final_duplicate_slot_count,
            "steam_legitimate_unknown": llm_diagnostics.get("steam_unknown_count", 0),
            "anomalous_unknown": llm_diagnostics.get("anomalous_unknown_count", 0),
            "input_file_count": all_files_count,
            "adopted_file_count": adopted_file_count,
            "unassigned_file_count": len(unassigned_manifest),
            "archive_artifact_issues": artifact_issues,
            "track_group_count": len(track_groups),
            "slot_variant_count": len(slot_variant_index),
            "multi_variant_slot_count": multi_variant_slot_count,
            "format_selection": format_selection_audit,
            "field_provenance": field_provenance_audit,
            "adopted_slot_count": adopted_file_count,
            "io_retry_count": io_retry_count,
            "io_retry_logs": audit_copy_logs,
            "review_candidate_count": len(llm_diagnostics.get("review_candidates") or []),
            **deferred_copy_diagnostics,
        },
        "strategy": (llm_log.get("phase1_res") or {}).get("strategy"),
        "confidence_reason": reason,
        "processed_at": processed_at,
        "tracks": processed_tracks_meta,
        "unassigned_files": unassigned_manifest,
        "steam_info": steam_meta.model_dump(),
        "diagnostics": {**diagnostics, **deferred_copy_diagnostics},
    }