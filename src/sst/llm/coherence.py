from typing import Any, Callable, Dict, List, Optional, Tuple


def resolve_mapping_references(
    start_idx: int,
    full_ref_steam: List[Dict[str, Any]],
    full_ref_fingerprint: List[Dict[str, Any]],
    coherence_mappings: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ref_steam = full_ref_steam
    ref_fingerprint = full_ref_fingerprint

    if coherence_mappings:
        coherence_key = f"Segment_{(start_idx // 30) + 1}"
        segment_mapping = coherence_mappings.get(coherence_key, {})
        if segment_mapping:
            steam_start = segment_mapping.get("steam_start_v_idx")
            steam_end = segment_mapping.get("steam_end_v_idx")
            if steam_start is not None and steam_end is not None:
                ref_steam = [
                    track
                    for track in full_ref_steam
                    if steam_start <= track.get("v_idx", 0) <= steam_end
                ]
            else:
                ref_steam = []

            fingerprint_start = segment_mapping.get("fingerprint_start_v_idx")
            fingerprint_end = segment_mapping.get("fingerprint_end_v_idx")
            if fingerprint_start is not None and fingerprint_end is not None:
                ref_fingerprint = [
                    track
                    for track in full_ref_fingerprint
                    if fingerprint_start <= track.get("v_idx", 0) <= fingerprint_end
                ]
            else:
                ref_fingerprint = []

    return ref_steam, ref_fingerprint


def merge_track_instructions(
    track_res: Dict[str, Any],
    local_tracks: List[Dict[str, Any]],
    chunk: List[Dict[str, Any]],
    global_res: Dict[str, Any],
    ref_fingerprint: List[Dict[str, Any]],
    full_ref_mbz_search: List[Dict[str, Any]],
    v_mbz_search: Optional[Dict[str, Any]],
    full_ref_steam: Optional[List[Dict[str, Any]]] = None,
    prematch_map: Optional[Dict[str, Any]] = None,
    *,
    normalize_mapping_result: Callable[..., Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    normalized_track_res = normalize_mapping_result(
        track_res,
        full_ref_steam,
        prematch_map=prematch_map,
    )
    if not normalized_track_res or "track_instructions" not in normalized_track_res:
        return merged

    assigned_file_ids: set[str] = set()
    known_file_ids = {
        str(file_id)
        for track in local_tracks
        for file_id in track.get("file_ids", [])
    }
    for c_idx_str, data in normalized_track_res["track_instructions"].items():
        file_id = str(c_idx_str)
        if known_file_ids:
            if file_id not in known_file_ids or file_id in assigned_file_ids:
                continue
            matching_track = next(
                (
                    track
                    for track in local_tracks
                    if file_id in {str(value) for value in track.get("file_ids", [])}
                ),
                None,
            )
            assigned_file_ids.add(file_id)
        else:
            try:
                chunk_index = int(c_idx_str)
                if chunk_index < 0 or chunk_index >= len(local_tracks):
                    continue
                matching_track = local_tracks[chunk_index]
            except ValueError:
                matching_track = next(
                    (track for track in chunk if track["title"] == c_idx_str),
                    None,
                )

        if not matching_track:
            continue

        track_id = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"
        matched_v_idx = data.get("matched_v_idx")
        if data.get("mbz_track_index") is None:
            if (
                data.get("action") == "use_fingerprint"
                and matched_v_idx is not None
                and matched_v_idx < len(ref_fingerprint)
            ):
                ref_track = ref_fingerprint[matched_v_idx]
                data["mbz_track_index"] = ref_track.get("mbz_idx")
                if data.get("override_track") is None and ref_track.get("n") is not None:
                    data["override_track"] = str(ref_track.get("n"))
            elif (
                data.get("action") == "use_mbz_search"
                and matched_v_idx is not None
                and v_mbz_search
                and matched_v_idx < len(full_ref_mbz_search)
            ):
                ref_track = full_ref_mbz_search[matched_v_idx]
                data["mbz_track_index"] = ref_track.get("mbz_idx")
                if data.get("override_track") is None and ref_track.get("n") is not None:
                    data["override_track"] = str(ref_track.get("n"))
            elif (
                matched_v_idx is not None
                and full_ref_steam
                and matched_v_idx < len(full_ref_steam)
            ):
                ref_track = full_ref_steam[matched_v_idx]
                if data.get("override_track") is None and ref_track.get("n") is not None:
                    data["override_track"] = str(ref_track.get("n"))

        tags = global_res.get("global_tags", {})
        if not isinstance(tags, dict):
            tags = {}
        data.update({
            "TPE2": tags.get("canonical_album_artist") or global_res.get("canonical_album_artist"),
            "TCON": tags.get("canonical_genre") or global_res.get("canonical_genre"),
            "TDRC": tags.get("canonical_year") or global_res.get("canonical_year"),
            "TPUB": tags.get("canonical_label") or global_res.get("canonical_label"),
            "TEXT": data.get("lyricist"),
            "TCOM": data.get("composer"),
            "TPE4": data.get("arranger"),
            "identity_confidence": global_res["identity_confidence"],
            "integrity_quality": global_res.get("integrity_quality", 0),
            "archive_vs_review_ratio": global_res.get(
                "archive_vs_review_ratio",
                {"archive": 0, "review": 100},
            ),
            "confidence_score": global_res.get("identity_confidence", 0),
            "strategy": global_res.get("strategy", "UNKNOWN"),
            "semantic_label": global_res.get("semantic_label", "Review"),
        })
        merged[track_id] = data

    return merged