from typing import Any, Callable, Dict

from ..models import LocalProcessResult


def retry_and_finalize_deferred_copy(
    context: Dict[str, Any],
    *,
    encode_and_tag_tracks: Callable[..., Any],
    normalize_processed_tracks: Callable[..., Any],
    finalize_album_package: Callable[..., LocalProcessResult],
) -> LocalProcessResult:
    retry_result = encode_and_tag_tracks(
        context["app_id"],
        context["steam_meta"],
        context["final_metadata"],
        context["mbz_candidates"],
        context["track_groups"],
        context["slot_variant_index"],
        context["track_to_slot_index"],
        context["llm_log"],
        context["total_discs"],
        context["temp_output"],
        context["buffer_dir"],
        None,
        context["_diag"],
        adopted_file_subset=context["deferred_track_data"],
        defer_copy_failures=False,
        include_unassigned=False,
        artwork_prepared=True,
        prepared_album_artwork_path=context["album_artwork_path"],
    )
    (
        retried_tracks,
        retry_audio_failures,
        retry_audio_warnings,
        retry_warned_tracks,
        _,
        retry_count,
        retry_logs,
        _,
        _,
        still_deferred,
        _,
    ) = retry_result

    recovered_track_ids = {
        log.get("track_id")
        for log in retry_logs
        if log.get("final_state") == "success" and log.get("track_id")
    }
    for log in context["io_retry_logs"]:
        if log.get("track_id") in recovered_track_ids:
            log["recovered_after_defer"] = True

    final_copy_failures = [
        log for log in retry_logs if log.get("final_state") == "failed"
    ]
    llm_diagnostics = context["llm_log"].setdefault("diagnostics", {})
    llm_diagnostics["deferred_copy_count"] = len(context["deferred_track_data"])
    llm_diagnostics["deferred_copy_success_count"] = len(recovered_track_ids)
    llm_diagnostics["deferred_copy_failure_count"] = len(final_copy_failures)
    llm_diagnostics["deferred_copy_failures"] = [
        {
            "track_id": log.get("track_id"),
            "slot_key": log.get("slot_key"),
            "source": log.get("source"),
            "attempts": log.get("attempts", []),
        }
        for log in final_copy_failures
    ]
    context["_diag"](
        "DEFERRED_COPY_RETRY_DONE",
        succeeded=len(recovered_track_ids),
        failed=len(final_copy_failures),
        requeued=bool(still_deferred),
    )

    processed_tracks_meta = normalize_processed_tracks(
        context["processed_tracks_meta"] + retried_tracks
    )
    combined_io_retry_logs = context["io_retry_logs"] + retry_logs
    return finalize_album_package(
        context["app_id"],
        context["steam_meta"],
        processed_tracks_meta,
        context["llm_log"],
        context["mbz_candidates"],
        context["any_audio_failures"] or retry_audio_failures or bool(still_deferred),
        context["any_audio_warnings"] or retry_audio_warnings,
        context["audio_warned_tracks"] + retry_warned_tracks,
        context["unassigned_manifest"],
        context["temp_output"],
        context["processing_route"],
        context["all_files_count"],
        context["adopted_file_count"],
        context["track_groups"],
        context["slot_variant_index"],
        context["track_results_len"],
        context["io_retry_count"] + retry_count,
        combined_io_retry_logs,
        context["alignment_inputs_bundle"],
        context["mbz_log"],
        context["diagnostics"],
        context["_diag"],
    )