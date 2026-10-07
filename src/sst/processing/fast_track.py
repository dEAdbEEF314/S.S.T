from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import SteamMetadata
from ..track_grouper import TrackManager


def normalize_slot_key(
    disc_number: Any,
    track_number: Any,
) -> Optional[tuple[int, str]]:
    if track_number in (None, "", "0", 0):
        return None
    try:
        disc_value = int(disc_number or 1)
    except (TypeError, ValueError):
        disc_value = 1
    track_value = str(track_number).split("/")[0].strip()
    if not track_value.isdigit():
        return None
    normalized_track = str(int(track_value))
    if normalized_track == "0":
        return None
    return disc_value, normalized_track


def build_fast_track_slot_map(
    steam_meta: SteamMetadata,
) -> Optional[Dict[tuple[int, str], int]]:
    slot_map: Dict[tuple[int, str], int] = {}
    for index, track in enumerate(steam_meta.store_tracklist or []):
        slot_key = normalize_slot_key(track.get("disc", 1), track.get("number"))
        if slot_key is None or slot_key in slot_map:
            return None
        slot_map[slot_key] = index
    return slot_map


def build_fast_track_group_map(
    track_groups: Dict,
    steam_meta: Optional[SteamMetadata] = None,
) -> Optional[Dict[str, tuple[tuple[int, str], str]]]:
    group_map: Dict[str, tuple[tuple[int, str], str]] = {}
    slot_durations: Dict[tuple[int, str], List[float]] = {}
    steam_title_map: Dict[str, List[tuple[int, str]]] = {}
    steam_tracks_by_slot: Dict[tuple[int, str], Dict[str, Any]] = {}

    for track in (steam_meta.store_tracklist if steam_meta else []):
        title = TrackManager.normalize_title(str(track.get("title") or track.get("name") or ""))
        slot_key = normalize_slot_key(track.get("disc", 1), track.get("number"))
        if slot_key is None:
            continue
        if title:
            steam_title_map.setdefault(title, []).append(slot_key)
        steam_tracks_by_slot[slot_key] = track

    for (disc_number, record_title), variants in track_groups.items():
        track_numbers = {
            variant.get("t_num_val")
            for variant in variants
            if variant.get("t_num_val") not in (None, "", "0")
        }
        slot_key: Optional[tuple[int, str]] = None

        clean_title_part = record_title.split("::")[0] if "::" in record_title else record_title
        normalized_titles = [
            TrackManager.normalize_title(clean_title_part),
            TrackManager.normalize_title(Path(clean_title_part).stem),
            TrackManager.normalize_title(
                str((variants[0].get("meta") or {}).get("title") or "")
            ) if variants else "",
        ]
        normalized_titles = [title for title in normalized_titles if title]

        candidate_slot_key = None
        if len(track_numbers) == 1:
            candidate_slot_key = normalize_slot_key(disc_number, next(iter(track_numbers)))
            if candidate_slot_key is not None and candidate_slot_key not in steam_tracks_by_slot:
                return None

        if candidate_slot_key is not None and candidate_slot_key in steam_tracks_by_slot:
            steam_track = steam_tracks_by_slot[candidate_slot_key]
            steam_title = TrackManager.normalize_title(
                str((steam_track or {}).get("title") or (steam_track or {}).get("name") or "")
            )
            if not normalized_titles or steam_title in normalized_titles:
                slot_key = candidate_slot_key

        if slot_key is None and steam_meta:
            for normalized_title in normalized_titles:
                title_matches = steam_title_map.get(normalized_title, [])
                if len(title_matches) == 1:
                    slot_key = title_matches[0]
                    break

        if slot_key is None and candidate_slot_key is not None and candidate_slot_key in steam_tracks_by_slot:
            slot_key = candidate_slot_key

        if slot_key is None:
            return None

        slot_durations.setdefault(slot_key, []).extend(
            float(variant.get("duration", 0.0) or 0.0) for variant in variants
        )
        group_map[f"{disc_number}_{record_title}"] = (slot_key, record_title)

    if any(
        max(durations) - min(durations) >= 1.0
        for durations in slot_durations.values()
        if durations
    ):
        return None

    return group_map


def apply_mbz_track_artists(
    final_metadata: Dict[str, Dict[str, Any]],
    steam_tracklist: List[Dict[str, Any]],
    mbz_candidate: Optional[Dict[str, Any]],
) -> int:
    if not mbz_candidate:
        return 0

    steam_titles: Dict[str, List[int]] = {}
    mbz_titles: Dict[str, List[Dict[str, Any]]] = {}
    for slot_index, steam_track in enumerate(steam_tracklist):
        title = str(steam_track.get("title") or steam_track.get("name") or "")
        normalized = TrackManager.normalize_title(title)
        if normalized:
            steam_titles.setdefault(normalized, []).append(slot_index)
    for mbz_track in mbz_candidate.get("tracks", []):
        title = str(mbz_track.get("title") or "")
        normalized = TrackManager.normalize_title(title)
        if normalized and mbz_track.get("recording_artist"):
            mbz_titles.setdefault(normalized, []).append(mbz_track)

    applied = 0
    for instruction in final_metadata.values():
        slot_index = instruction.get("matched_v_idx")
        if not isinstance(slot_index, int) or not 0 <= slot_index < len(steam_tracklist):
            continue
        steam_track = steam_tracklist[slot_index]
        steam_title = str(steam_track.get("title") or steam_track.get("name") or "")
        normalized = TrackManager.normalize_title(steam_title)
        matching_slots = steam_titles.get(normalized, [])
        matching_mbz_tracks = mbz_titles.get(normalized, [])
        if len(matching_slots) == 1 and len(matching_mbz_tracks) == 1:
            instruction["mbz_track_artist"] = matching_mbz_tracks[0]["recording_artist"]
            applied += 1
    return applied