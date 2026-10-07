import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("sst.llm.alignment_segments")


def run_differential_segments(
    app_id: int,
    unmatched_local_tracks: List[Dict[str, Any]],
    local_tracks: List[Dict[str, Any]],
    unfilled_steam_slots: List[Dict[str, Any]],
    global_res: Dict[str, Any],
    s_mbz_search: Dict[str, Any],
    v_mbz_search: Optional[Dict[str, Any]],
    full_ref_fingerprint: List[Dict[str, Any]],
    full_ref_mbz_search: List[Dict[str, Any]],
    coherence_mappings: Optional[Dict[str, Any]],
    resolved_num_ctx: Optional[int],
    dynamic_chunk_size: int,
    progress_callback: Optional[Callable[..., Any]],
    prematch_map: Optional[Dict[str, Any]],
    *,
    should_parallelize: bool,
    resolve_worker_count: Callable[[Optional[Any], int], int],
    execution_profile: Optional[Any],
    process_segment: Callable[..., Tuple[int, Dict[str, Dict[str, Any]], List[Dict[str, Any]]]],
) -> Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]]:
    segment_results: Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]] = {}
    chunk_size = max(1, dynamic_chunk_size)
    segments = [
        (start_idx, unmatched_local_tracks[start_idx : start_idx + chunk_size])
        for start_idx in range(0, len(unmatched_local_tracks), chunk_size)
    ]

    if should_parallelize:
        worker_count = resolve_worker_count(execution_profile, len(segments))
        logger.info(
            "[%s] Phase 2 differential mapping chunk を並列実行します。segments=%s workers=%s",
            app_id,
            len(segments),
            worker_count,
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(
                    process_segment,
                    app_id,
                    start_idx,
                    segment_tracks,
                    local_tracks,
                    global_res,
                    s_mbz_search,
                    v_mbz_search,
                    unfilled_steam_slots,
                    full_ref_fingerprint,
                    full_ref_mbz_search,
                    coherence_mappings,
                    resolved_num_ctx,
                    chunk_size,
                    progress_callback,
                    prematch_map=prematch_map,
                ): start_idx
                for start_idx, segment_tracks in segments
            }
            for future in as_completed(future_map):
                start_idx, instructions, segment_logs = future.result()
                segment_results[start_idx] = (instructions, segment_logs)
    else:
        for start_idx, segment_tracks in segments:
            start_idx, instructions, segment_logs = process_segment(
                app_id,
                start_idx,
                segment_tracks,
                local_tracks,
                global_res,
                s_mbz_search,
                v_mbz_search,
                unfilled_steam_slots,
                full_ref_fingerprint,
                full_ref_mbz_search,
                coherence_mappings,
                resolved_num_ctx,
                chunk_size,
                progress_callback,
                prematch_map=prematch_map,
            )
            segment_results[start_idx] = (instructions, segment_logs)
    return segment_results