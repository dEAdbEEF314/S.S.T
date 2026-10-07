from typing import Any, Dict, List

from ..models import SteamMetadata


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
            "adopted_slot_count": adopted_file_count,
            "io_retry_count": io_retry_count,
            "io_retry_logs": audit_copy_logs,
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