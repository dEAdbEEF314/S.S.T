from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set

from ..models import SteamMetadata
from ..track_grouper import TrackManager
from .fast_track import normalize_slot_key


def _normalized_titles_match(
    left: str,
    right: str,
    *,
    same_slot_number: bool = False,
    duration_diff: Optional[float] = None,
) -> bool:
    if not left or not right:
        return False
    if (
        left == right
        or f" {left} " in f" {right} "
        or f" {right} " in f" {left} "
    ):
        return True
    left_compact = left.replace(" ", "")
    right_compact = right.replace(" ", "")
    if len(left_compact) >= 3 and left_compact == right_compact:
        return True
    if same_slot_number and (duration_diff is None or duration_diff <= 3.0):
        if len(left) >= 4 and len(right) >= 4:
            if SequenceMatcher(None, left, right).ratio() >= 0.85:
                return True
    return False


def build_slot_variant_index(
    final_metadata: Dict[str, Any],
    track_groups: Dict,
    steam_meta: SteamMetadata,
) -> tuple[Dict[tuple[int, str], List[Dict[str, Any]]], Dict[str, tuple[int, str]]]:
    slot_variants: Dict[tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    track_to_slot: Dict[str, tuple[int, str]] = {}
    priorities = TrackManager.get_audio_format_priority()
    variant_titles = {
        variant.get("file_id"): TrackManager.normalize_title(
            str(group_key[1]).split("::", 1)[0]
        )
        for group_key, variants in track_groups.items()
        for variant in variants
    }
    steam_slots_by_key: Dict[tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    steam_norm_titles_by_key: Dict[tuple[int, str], Set[str]] = defaultdict(set)
    for steam_track in steam_meta.store_tracklist or []:
        slot_key = normalize_slot_key(
            steam_track.get("disc", 1),
            steam_track.get("number", steam_track.get("track_number")),
        )
        if slot_key is not None:
            steam_slots_by_key[slot_key].append(steam_track)
            norm_st = TrackManager.normalize_title(
                str(steam_track.get("title") or steam_track.get("name") or "")
            )
            if norm_st:
                steam_norm_titles_by_key[slot_key].add(norm_st)

    def sort_key(variant: Dict[str, Any], target_slot_key: Optional[tuple[int, str]] = None) -> tuple[int, int]:
        fmt = str(variant.get("format", "")).lower()
        try:
            fmt_rank = priorities.index(fmt)
        except ValueError:
            fmt_rank = 999
        title_rank = 1
        if target_slot_key and target_slot_key in steam_norm_titles_by_key:
            v_title = TrackManager.normalize_title(
                str(variant.get("norm_stem") or variant_titles.get(variant.get("file_id"), "") or "")
            )
            if v_title and any(_normalized_titles_match(v_title, st) for st in steam_norm_titles_by_key[target_slot_key]):
                title_rank = 0
        return (fmt_rank, title_rank)

    unaligned_groups = []
    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        instr = final_metadata.get(track_id, {}) if isinstance(final_metadata, dict) else {}
        slot_key = None

        matched_v_idx = instr.get("matched_v_idx")
        if matched_v_idx is not None and 0 <= int(matched_v_idx) < len(steam_meta.store_tracklist or []):
            track = steam_meta.store_tracklist[int(matched_v_idx)]
            slot_key = normalize_slot_key(track.get("disc", 1), track.get("number"))

        if slot_key is None and instr.get("override_track") is not None:
            slot_key = normalize_slot_key(instr.get("override_disc", disc), instr.get("override_track"))

        if slot_key is not None:
            slot_variants[slot_key].extend(variants)
            track_to_slot[track_id] = slot_key
        else:
            unaligned_groups.append(((disc, clean_title), variants))

    is_single_slot_album = len(steam_slots_by_key) == 1

    remaining_unaligned = []
    for (disc, clean_title), variants in unaligned_groups:
        track_id = f"{disc}_{clean_title}"
        if not variants:
            continue
        raw_title = clean_title.split("::")[0] if "::" in clean_title else clean_title
        unaligned_title = TrackManager.normalize_title(raw_title)
        embedded_title = TrackManager.normalize_title(
            str((variants[0].get("meta") or {}).get("title") or "")
        )
        unaligned_duration = float(variants[0].get("duration", 0.0) or 0.0)
        unaligned_format = str(variants[0].get("format", "")).lower()
        track_numbers = [
            variant.get("t_num_val")
            for variant in variants
            if variant.get("t_num_val") not in (None, "", "0")
        ]
        inferred_track = track_numbers[0] if track_numbers else None
        inferred_slot_key = normalize_slot_key(disc, inferred_track)

        other_steam_matches = {
            s_key
            for s_key, s_titles in steam_norm_titles_by_key.items()
            if any(
                _normalized_titles_match(unaligned_title, st)
                or (bool(embedded_title) and _normalized_titles_match(embedded_title, st))
                for st in s_titles
            )
        }

        matching_slot_keys = set()
        for slot_key, assigned_variants in list(slot_variants.items()):
            if not isinstance(slot_key, tuple) or len(slot_key) != 2 or not str(slot_key[1]).isdigit():
                continue
            same_track_number = (
                inferred_track is not None and str(inferred_track) == str(slot_key[1])
            )
            same_slot_number = (
                (inferred_slot_key is not None and inferred_slot_key == slot_key)
                or (is_single_slot_album and inferred_track in (None, "1", 1))
            )
            for assigned_variant in assigned_variants:
                assigned_format = str(assigned_variant.get("format", "")).lower()
                assigned_duration = float(assigned_variant.get("duration", 0.0) or 0.0)
                assigned_raw_title = assigned_variant.get("norm_stem") or variant_titles.get(assigned_variant.get("file_id"), "")
                assigned_title = TrackManager.normalize_title(str(assigned_raw_title or ""))
                assigned_orig_track = assigned_variant.get("t_num_val") or assigned_variant.get("filename_track")
                same_orig_track = (
                    inferred_track is not None
                    and assigned_orig_track is not None
                    and str(inferred_track).lstrip("0") == str(assigned_orig_track).lstrip("0")
                )
                effective_same_track = same_track_number or same_orig_track

                is_different_format = (assigned_format != unaligned_format) and bool(assigned_format and unaligned_format)
                dur_diff = (
                    abs(assigned_duration - unaligned_duration)
                    if (assigned_duration > 0 and unaligned_duration > 0)
                    else None
                )
                title_matches = _normalized_titles_match(
                    unaligned_title,
                    assigned_title,
                    same_slot_number=same_slot_number,
                    duration_diff=dur_diff,
                ) or (
                    bool(embedded_title)
                    and _normalized_titles_match(
                        embedded_title,
                        assigned_title,
                        same_slot_number=same_slot_number,
                        duration_diff=dur_diff,
                    )
                )
                matches_this_steam = any(
                    _normalized_titles_match(
                        unaligned_title,
                        st,
                        same_slot_number=same_slot_number,
                        duration_diff=dur_diff,
                    )
                    for st in steam_norm_titles_by_key.get(slot_key, set())
                )
                effective_title_matches = title_matches or matches_this_steam

                # 指示書 05 3.2-1 / fix_0.5 指示書 02: 同一 (disc, n) または同一トラック番号・元トラック番号一致・異フォーマット・同一 norm_stem の最優先判定
                is_sibling_stem_match = (
                    (same_slot_number or effective_same_track or same_orig_track)
                    and is_different_format
                    and (dur_diff is None or dur_diff <= 2.0)
                    and (
                        unaligned_title == assigned_title
                        or SequenceMatcher(None, unaligned_title, assigned_title).ratio() >= 0.88
                    )
                )

                max_dur_tol = 5.0 if (same_slot_number and (unaligned_title == assigned_title or matches_this_steam)) else 3.0
                cond1_diff_fmt = (
                    is_sibling_stem_match
                    or (
                        is_different_format
                        and (dur_diff <= max_dur_tol if dur_diff is not None else True)
                        and effective_title_matches
                    )
                )
                no_conflicting_other_slot = not (other_steam_matches - {slot_key})
                cond2_same_fmt_dup = (
                    not is_different_format
                    and effective_title_matches
                    and (dur_diff <= 1.5 if dur_diff is not None else same_slot_number)
                    and (same_slot_number or no_conflicting_other_slot)
                )
                cond3_coherent_bilingual = (
                    same_slot_number
                    and dur_diff is not None
                    and dur_diff <= 1.5
                    and no_conflicting_other_slot
                )

                if not (cond1_diff_fmt or cond2_same_fmt_dup or cond3_coherent_bilingual):
                    continue

                if is_sibling_stem_match and (slot_key[0] == disc or effective_same_track or same_orig_track):
                    matching_slot_keys = {slot_key}
                    break

                if slot_key[0] != disc and not (is_single_slot_album and same_slot_number):
                    candidate_steam_slots = {
                        steam_key
                        for steam_key, steam_tracks in steam_slots_by_key.items()
                        if any(
                            _normalized_titles_match(
                                unaligned_title,
                                TrackManager.normalize_title(
                                    str(track.get("title") or track.get("name") or "")
                                ),
                            )
                            for track in steam_tracks
                        )
                    }
                    if candidate_steam_slots != {slot_key}:
                        continue

                matching_slot_keys.add(slot_key)

        if len(matching_slot_keys) == 1:
            merged_slot_key = next(iter(matching_slot_keys))
            slot_variants[merged_slot_key].extend(variants)
            track_to_slot[track_id] = merged_slot_key
        else:
            remaining_unaligned.append(((disc, clean_title), variants))

    for (disc, clean_title), variants in remaining_unaligned:
        track_id = f"{disc}_{clean_title}"
        track_numbers = [variant.get("t_num_val") for variant in variants if variant.get("t_num_val") not in (None, "", "0")]
        inferred_track = track_numbers[0] if track_numbers else None
        inferred_slot_key = normalize_slot_key(disc, inferred_track)
        raw_title = clean_title.split("::", 1)[0]
        local_title = TrackManager.normalize_title(raw_title)
        matching_steam_tracks = steam_slots_by_key.get(inferred_slot_key, []) if inferred_slot_key else []
        title_matches_steam = len(matching_steam_tracks) == 1 and _normalized_titles_match(
            local_title,
            TrackManager.normalize_title(
                str(matching_steam_tracks[0].get("title") or matching_steam_tracks[0].get("name") or "")
            ),
            same_slot_number=True,
        )
        if (
            inferred_slot_key is not None
            and title_matches_steam
            and inferred_slot_key not in slot_variants
        ):
            slot_key = inferred_slot_key
        else:
            slot_key = (disc, clean_title)
        slot_variants[slot_key].extend(variants)
        track_to_slot[track_id] = slot_key

    for slot_key, variants in slot_variants.items():
        slot_variants[slot_key] = sorted(variants, key=lambda v, sk=slot_key: sort_key(v, sk))

    return dict(slot_variants), track_to_slot


def merge_embedded_tags_for_slot(slot_variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_tags: Dict[str, Any] = {}
    for variant in slot_variants:
        meta = variant.get("meta") or {}
        for key, value in meta.items():
            if value and str(value).lower() not in {"", "none", "unknown", "0"} and key not in merged_tags:
                merged_tags[key] = value
    return merged_tags