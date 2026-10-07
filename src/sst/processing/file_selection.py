import hashlib
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..track_grouper import TrackManager


def adopt_best_file_per_slot(
    track_groups: Dict,
    slot_variant_index: Dict[tuple[int, str], List[Dict[str, Any]]],
    track_to_slot_index: Dict[str, tuple[int, str]],
) -> Dict[tuple[int, str], Dict[str, Any]]:
    """Select exactly one highest-Tier physical file for each aligned slot."""
    priorities = TrackManager.get_audio_format_priority()
    record_keys_by_file_id = {
        variant.get("file_id"): key
        for key, variants in track_groups.items()
        for variant in variants
    }
    adopted: Dict[tuple[int, str], Dict[str, Any]] = {}
    for slot_key, variants in slot_variant_index.items():
        if not variants:
            continue
        chosen = min(
            variants,
            key=lambda variant: priorities.index(str(variant.get("format", "")).lower())
            if str(variant.get("format", "")).lower() in priorities else len(priorities),
        )
        record_key = record_keys_by_file_id.get(chosen.get("file_id"))
        if record_key is None:
            continue
        tier_rank = TrackManager.get_quality_tier(chosen.get("format", ""))
        adopted[record_key] = {
            "path": chosen["path"],
            "tier": "lossless" if tier_rank in {0, 1} else ("lossy" if chosen.get("format") != "mp3" else "mp3"),
            "tier_rank": tier_rank,
            "filename_track": chosen.get("filename_track"),
            "slot_key": slot_key,
        }

    output_names: Dict[tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for adopted_info in adopted.values():
        source_path = adopted_info["path"]
        output_extension = ".aif" if adopted_info["tier_rank"] in {0, 1} else ".mp3"
        disc_number = str(adopted_info["slot_key"][0])
        output_names[(disc_number, source_path.stem.casefold(), output_extension)].append(adopted_info)

    for colliding_infos in output_names.values():
        if len(colliding_infos) < 2:
            continue
        for adopted_info in colliding_infos:
            source_path = adopted_info["path"]
            disc_number, track_number = adopted_info["slot_key"]
            if str(track_number).isdigit():
                slot_token = f"d{disc_number}_t{int(track_number)}"
            else:
                slot_token = hashlib.sha1(
                    f"{disc_number}_{track_number}".encode("utf-8")
                ).hexdigest()[:8]
            adopted_info["staging_filename"] = (
                f"{source_path.stem}__sst_{slot_token}{source_path.suffix}"
            )
    return adopted


def select_best_unassigned_files(
    track_groups: Dict,
    final_metadata: Dict[str, Any],
    unassigned_file_ids: Optional[set[str]] = None,
    slot_variant_index: Optional[Dict[tuple[int, str], List[Dict[str, Any]]]] = None,
    track_to_slot_index: Optional[Dict[str, tuple[int, str]]] = None,
) -> List[Dict[str, Any]]:
    """Select one highest-tier source file for each unassigned logical group."""
    priorities = TrackManager.get_audio_format_priority()

    assigned_file_ids_in_slots = set()
    if slot_variant_index:
        for slot_key, variants in slot_variant_index.items():
            if isinstance(slot_key, tuple) and len(slot_key) == 2 and str(slot_key[1]).isdigit():
                for variant in variants:
                    if variant.get("file_id"):
                        assigned_file_ids_in_slots.add(str(variant["file_id"]))

    selected = []
    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        if track_id in final_metadata or not variants:
            continue

        if track_to_slot_index and track_id in track_to_slot_index:
            slot_key = track_to_slot_index[track_id]
            if isinstance(slot_key, tuple) and len(slot_key) == 2 and str(slot_key[1]).isdigit():
                continue

        if unassigned_file_ids is not None:
            variants = [variant for variant in variants if variant.get("file_id") in unassigned_file_ids]
            if not variants:
                continue

        if assigned_file_ids_in_slots:
            variants = [variant for variant in variants if str(variant.get("file_id")) not in assigned_file_ids_in_slots]
            if not variants:
                continue

        chosen = min(
            variants,
            key=lambda variant: priorities.index(str(variant.get("format", "")).lower())
            if str(variant.get("format", "")).lower() in priorities else len(priorities),
        )
        tier_rank = TrackManager.get_quality_tier(chosen.get("format", ""))
        selected.append({
            "track_id": track_id,
            "path": chosen["path"],
            "format": chosen.get("format", ""),
            "tier": "lossless" if tier_rank in {0, 1} else "mp3",
            "tier_rank": tier_rank,
            "file_id": chosen.get("file_id"),
            "unassigned_file_ids": [variant.get("file_id") for variant in variants],
            "original_tags": chosen.get("meta", {}),
        })
    return selected