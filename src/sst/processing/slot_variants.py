from collections import defaultdict
from typing import Any, Dict, List

from ..models import SteamMetadata
from ..track_grouper import TrackManager
from .fast_track import normalize_slot_key


def _normalized_titles_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return (
        left == right
        or f" {left} " in f" {right} "
        or f" {right} " in f" {left} "
    )


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
    for steam_track in steam_meta.store_tracklist or []:
        slot_key = normalize_slot_key(
            steam_track.get("disc", 1),
            steam_track.get("number", steam_track.get("track_number")),
        )
        if slot_key is not None:
            steam_slots_by_key[slot_key].append(steam_track)

    def sort_key(variant: Dict[str, Any]) -> int:
        fmt = str(variant.get("format", "")).lower()
        try:
            return priorities.index(fmt)
        except ValueError:
            return 999

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

    remaining_unaligned = []
    for (disc, clean_title), variants in unaligned_groups:
        track_id = f"{disc}_{clean_title}"
        if not variants:
            continue
        raw_title = clean_title.split("::")[0] if "::" in clean_title else clean_title
        unaligned_title = TrackManager.normalize_title(raw_title)
        unaligned_duration = float(variants[0].get("duration", 0.0) or 0.0)
        unaligned_format = str(variants[0].get("format", "")).lower()
        matching_slot_keys = set()
        for slot_key, assigned_variants in list(slot_variants.items()):
            if not isinstance(slot_key, tuple) or len(slot_key) != 2 or not str(slot_key[1]).isdigit():
                continue
            for assigned_variant in assigned_variants:
                assigned_format = str(assigned_variant.get("format", "")).lower()
                assigned_duration = float(assigned_variant.get("duration", 0.0) or 0.0)
                assigned_title = assigned_variant.get("norm_stem") or variant_titles.get(assigned_variant.get("file_id"), "")

                is_different_format = (assigned_format != unaligned_format) and bool(assigned_format and unaligned_format)
                duration_matches = abs(assigned_duration - unaligned_duration) < 1.0 if (assigned_duration > 0 and unaligned_duration > 0) else True
                title_matches = _normalized_titles_match(unaligned_title, assigned_title)

                if not (is_different_format and duration_matches and title_matches):
                    continue

                if slot_key[0] != disc:
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
        slot_variants[slot_key] = sorted(variants, key=sort_key)

    return dict(slot_variants), track_to_slot


def merge_embedded_tags_for_slot(slot_variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_tags: Dict[str, Any] = {}
    for variant in slot_variants:
        meta = variant.get("meta") or {}
        for key, value in meta.items():
            if value and str(value).lower() not in {"", "none", "unknown", "0"} and key not in merged_tags:
                merged_tags[key] = value
    return merged_tags