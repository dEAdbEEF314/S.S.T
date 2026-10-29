import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("sst.llm.alignment_segments")


def is_same_track_variant(t1: Dict[str, Any], t2: Dict[str, Any]) -> bool:
    if not isinstance(t1, dict) or not isinstance(t2, dict):
        return False
    # 1. (disc, track_num)
    d1 = t1.get("disc") or t1.get("d") or 1
    d2 = t2.get("disc") or t2.get("d") or 1
    n1 = t1.get("track_num") or t1.get("n") or t1.get("filename_track")
    n2 = t2.get("track_num") or t2.get("n") or t2.get("filename_track")
    if n1 is not None and n2 is not None and str(d1) == str(d2) and str(n1) == str(n2):
        return True
    # 2. norm_stem
    ns1 = t1.get("norm_stem")
    ns2 = t2.get("norm_stem")
    if ns1 and ns2 and str(ns1).strip() == str(ns2).strip():
        return True
    # 3. clean_title or title with matching duration
    title1 = t1.get("clean_title") or t1.get("title") or t1.get("t")
    title2 = t2.get("clean_title") or t2.get("title") or t2.get("t")
    if title1 and title2 and str(title1).strip().lower() == str(title2).strip().lower():
        dur1 = t1.get("duration_ms") or ((t1.get("dur") or 0) * 1000)
        dur2 = t2.get("duration_ms") or ((t2.get("dur") or 0) * 1000)
        if dur1 and dur2 and abs(int(dur1) - int(dur2)) <= 3000:
            return True
    return False


def split_tracks_into_chunks(
    tracks: List[Dict[str, Any]], base_chunk_size: int
) -> List[Tuple[int, List[Dict[str, Any]]]]:
    chunks: List[Tuple[int, List[Dict[str, Any]]]] = []
    chunk_size = max(1, base_chunk_size)
    offset = 0
    while offset < len(tracks):
        c_size = min(chunk_size, len(tracks) - offset)
        end_idx = offset + c_size
        while end_idx < len(tracks) and is_same_track_variant(
            tracks[end_idx - 1], tracks[end_idx]
        ):
            end_idx += 1
        chunks.append((offset, tracks[offset:end_idx]))
        offset = end_idx
    return chunks


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
    segments = split_tracks_into_chunks(unmatched_local_tracks, chunk_size)

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