from typing import Any, Callable, Dict, List, Tuple

from ..track_grouper import TrackManager


def titles_are_compatible(left: str, right: str) -> bool:
    left_title = TrackManager.normalize_title(left)
    right_title = TrackManager.normalize_title(right)
    if not left_title or not right_title:
        return False
    return (
        left_title == right_title
        or f" {left_title} " in f" {right_title} "
        or f" {right_title} " in f" {left_title} "
    )


def reject_contradictory_slot_assignments(
    final_instructions: Dict[str, Dict[str, Any]],
    local_tracks: List[Dict[str, Any]],
    full_ref_steam: List[Dict[str, Any]],
    *,
    title_compatibility: Callable[[str, str], bool] = titles_are_compatible,
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    local_tracks_by_tid = {
        f"{track['local_key'][0]}_{track['local_key'][1]}": track
        for track in local_tracks
        if track.get("local_key")
    }
    tids_by_slot: Dict[int, List[str]] = {}
    for tid, instruction in final_instructions.items():
        matched_v_idx = instruction.get("matched_v_idx")
        if tid in local_tracks_by_tid and matched_v_idx is not None:
            tids_by_slot.setdefault(int(matched_v_idx), []).append(tid)

    rejected_tids = set()
    contradictions = []
    for matched_v_idx, tids in tids_by_slot.items():
        if len(tids) < 2 or not 0 <= matched_v_idx < len(full_ref_steam):
            continue

        tracks = [local_tracks_by_tid[tid] for tid in tids]
        titles = [
            str(track.get("title") or track.get("t") or track["local_key"][1])
            for track in tracks
        ]
        normalized_titles = [TrackManager.normalize_title(title) for title in titles]
        durations = [
            float(track.get("duration_ms") or 0)
            for track in tracks
            if float(track.get("duration_ms") or 0) > 0
        ]
        coherent_variants = (
            bool(normalized_titles)
            and all(normalized_titles)
            and len(set(normalized_titles)) == 1
            and (len(durations) < 2 or max(durations) - min(durations) < 1000)
        )
        if coherent_variants:
            continue

        steam_track = full_ref_steam[matched_v_idx]
        steam_title = str(steam_track.get("t") or steam_track.get("title") or "")
        steam_matches = {
            tid
            for tid, title in zip(tids, titles)
            if title_compatibility(title, steam_title)
        }
        deterministic_matches = {
            tid
            for tid in tids
            if str(final_instructions[tid].get("reason") or "").startswith(
                "SYSTEM: Deterministic"
            )
        }

        if deterministic_matches:
            retained_tids = deterministic_matches
        elif len(steam_matches) == 1:
            retained_tids = steam_matches
        else:
            retained_tids = set()

        rejected_for_slot = [tid for tid in tids if tid not in retained_tids]
        if rejected_for_slot:
            rejected_tids.update(rejected_for_slot)
            contradictions.append({
                "matched_v_idx": matched_v_idx,
                "steam_title": steam_title,
                "rejected_track_ids": rejected_for_slot,
                "rejected_titles": [titles[tids.index(tid)] for tid in rejected_for_slot],
            })

    filtered_instructions = {
        tid: instruction
        for tid, instruction in final_instructions.items()
        if tid not in rejected_tids
    }
    return filtered_instructions, contradictions