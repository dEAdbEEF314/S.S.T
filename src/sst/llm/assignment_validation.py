import difflib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..track_grouper import TrackManager


def _clean_artist_affixes(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    candidates = [text]
    no_by = re.sub(r"\s+by\s+.+$", "", text, flags=re.IGNORECASE).strip()
    if no_by and no_by != text:
        candidates.append(no_by)
    if " - " in text:
        after_sep = text.split(" - ", 1)[1].strip()
        if after_sep:
            candidates.append(after_sep)
    # Strip parentheses/brackets
    no_brackets = re.sub(r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", text).strip()
    if no_brackets and no_brackets != text:
        candidates.append(no_brackets)
    return candidates


def titles_are_compatible(left: str, right: str) -> bool:
    left_cands = [TrackManager.normalize_title(c) for c in _clean_artist_affixes(left)]
    right_cands = [TrackManager.normalize_title(c) for c in _clean_artist_affixes(right)]
    left_cands = [c for c in left_cands if c]
    right_cands = [c for c in right_cands if c]
    if not left_cands or not right_cands:
        return False

    for l_title in left_cands:
        l_compact = l_title.replace(" ", "")
        l_nums = re.findall(r"\d+", l_title)
        for r_title in right_cands:
            r_compact = r_title.replace(" ", "")
            if l_title == r_title or (l_compact and l_compact == r_compact):
                return True
            r_nums = re.findall(r"\d+", r_title)
            # Both contain numbers, but different sets -> not compatible (e.g. Stage 1 vs Stage 2)
            if l_nums and r_nums and l_nums != r_nums:
                continue
            if l_nums == r_nums and (
                f" {l_title} " in f" {r_title} "
                or f" {r_title} " in f" {l_title} "
            ):
                return True
            # SequenceMatcher high similarity check (particle diff / minor typo)
            # Both must be >= 5 chars and numbers must match
            if l_nums == r_nums:
                len_l = max(len(l_title), len(l_compact))
                len_r = max(len(r_title), len(r_compact))
                if len_l >= 5 and len_r >= 5:
                    ratio = difflib.SequenceMatcher(None, l_title, r_title).ratio()
                    if ratio >= 0.85:
                        return True
                    if l_compact and r_compact:
                        ratio_compact = difflib.SequenceMatcher(None, l_compact, r_compact).ratio()
                        if ratio_compact >= 0.85:
                            return True
    return False


def _track_candidate_titles(track: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in ("title", "t", "norm_stem"):
        val = track.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())
    local_key = track.get("local_key")
    if isinstance(local_key, (tuple, list)) and len(local_key) >= 2:
        lk_val = str(local_key[1]).strip()
        if lk_val:
            candidates.append(lk_val)
    return candidates or [""]


def _are_tracks_coherent_variants(
    tracks: List[Dict[str, Any]],
    title_compatibility: Callable[[str, str], bool],
) -> bool:
    if len(tracks) < 2:
        return True
    durations = [
        float(track.get("duration_ms") or 0)
        for track in tracks
        if float(track.get("duration_ms") or 0) > 0
    ]
    if len(durations) >= 2 and (max(durations) - min(durations)) > 3000:
        return False

    norm_titles = [
        TrackManager.normalize_title(
            str(track.get("title") or track.get("t") or track["local_key"][1])
        )
        for track in tracks
    ]
    if bool(norm_titles) and all(norm_titles) and len(set(norm_titles)) == 1:
        return True

    norm_stems = [
        TrackManager.normalize_title(str(track.get("norm_stem") or ""))
        for track in tracks
    ]
    if bool(norm_stems) and all(norm_stems) and len(set(norm_stems)) == 1:
        return True

    base_cands = _track_candidate_titles(tracks[0])
    for other in tracks[1:]:
        other_cands = _track_candidate_titles(other)
        if not any(
            title_compatibility(bc, oc)
            for bc in base_cands
            for oc in other_cands
        ):
            return False
    return True


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
        durations = [
            float(track.get("duration_ms") or 0)
            for track in tracks
            if float(track.get("duration_ms") or 0) > 0
        ]

        def _extract_track_num(tr: Dict[str, Any]) -> Optional[int]:
            val = (
                tr.get("track_num")
                or tr.get("track_number")
                or tr.get("n")
                or tr.get("filename_track")
            )
            if val is not None:
                try:
                    return int(str(val).split("/")[0])
                except (ValueError, TypeError):
                    pass
            return None

        track_nums = [_extract_track_num(track) for track in tracks]
        same_title_coherent = _are_tracks_coherent_variants(tracks, title_compatibility)
        same_track_coherent = (
            bool(track_nums)
            and all(tn is not None for tn in track_nums)
            and len(set(track_nums)) == 1
            and len(durations) >= 2
            and max(durations) - min(durations) <= 3000
        )
        coherent_variants = same_title_coherent or same_track_coherent
        if coherent_variants:
            continue

        steam_track = full_ref_steam[matched_v_idx]
        steam_title = str(steam_track.get("t") or steam_track.get("title") or "")
        steam_matches = {
            tid
            for tid, track in zip(tids, tracks)
            if any(
                title_compatibility(cand, steam_title)
                for cand in _track_candidate_titles(track)
            )
        }
        deterministic_matches = {
            tid
            for tid in tids
            if str(final_instructions[tid].get("reason") or "").startswith(
                "SYSTEM: Deterministic"
            )
        }

        matched_subset_tracks = [local_tracks_by_tid[tid] for tid in steam_matches]
        if len(steam_matches) == 1:
            retained_tids = steam_matches | deterministic_matches
        elif len(steam_matches) > 1 and _are_tracks_coherent_variants(
            matched_subset_tracks, title_compatibility
        ):
            retained_tids = steam_matches | deterministic_matches
        elif deterministic_matches:
            retained_tids = deterministic_matches
        else:
            retained_tids = set()

        if not retained_tids:
            expected_disc = int(steam_track.get("d") or steam_track.get("disc") or 1)
            expected_num = _extract_track_num({"n": steam_track.get("n")})
            expected_dur = float(steam_track.get("dur") or steam_track.get("duration_s") or 0)

            slot_num_and_dur_matches = set()
            for tid, track in zip(tids, tracks):
                t_disc = int(track.get("d") or track.get("disc") or 1)
                t_num = _extract_track_num(track)
                t_dur = (
                    float(track.get("duration_ms") or 0) / 1000.0
                    if track.get("duration_ms")
                    else float(track.get("dur") or 0)
                )

                if expected_num is not None and t_disc == expected_disc and t_num == expected_num:
                    if expected_dur > 0 and t_dur > 0:
                        if abs(t_dur - expected_dur) <= 3.0:
                            slot_num_and_dur_matches.add(tid)
                    else:
                        slot_num_and_dur_matches.add(tid)

            if 0 < len(slot_num_and_dur_matches) < len(tids):
                cand_tracks = [local_tracks_by_tid[tid] for tid in slot_num_and_dur_matches]
                if len(slot_num_and_dur_matches) == 1 or _are_tracks_coherent_variants(
                    cand_tracks, title_compatibility
                ):
                    retained_tids = slot_num_and_dur_matches

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
