import re
from typing import Any, Dict, List, Optional


def resolve_slot_key_to_v_idx(
    slot_key: str,
    full_ref_steam: Optional[List[Dict[str, Any]]],
) -> Optional[int]:
    if not full_ref_steam:
        return None

    def normalize_key(value: Any) -> str:
        text = str(value).strip()
        return text.lstrip("0") or "0"

    normalized_slot_key = str(slot_key).strip()
    normalized_key = normalize_key(normalized_slot_key)
    direct_matches = [
        track.get("v_idx")
        for track in full_ref_steam
        if normalize_key(track.get("n", "")) == normalized_key
    ]
    direct_matches = [match for match in direct_matches if match is not None]
    if len(direct_matches) == 1:
        return int(direct_matches[0])

    digit_match = re.search(r"\d+", normalized_slot_key)
    extracted_digits = digit_match.group(0) if digit_match else None
    if extracted_digits is not None:
        normalized_digits = normalize_key(extracted_digits)
        direct_matches = [
            track.get("v_idx")
            for track in full_ref_steam
            if normalize_key(track.get("n", "")) == normalized_digits
        ]
        direct_matches = [match for match in direct_matches if match is not None]
        if len(direct_matches) == 1:
            return int(direct_matches[0])

    numeric_key = extracted_digits if extracted_digits is not None else normalized_slot_key
    try:
        value = int(numeric_key)
    except (TypeError, ValueError):
        return None

    if value == 0 and full_ref_steam:
        return int(full_ref_steam[0].get("v_idx", 0))

    fallback_index = value - 1
    if 0 <= fallback_index < len(full_ref_steam):
        return int(full_ref_steam[fallback_index].get("v_idx", fallback_index))

    if 0 <= value < len(full_ref_steam):
        return int(full_ref_steam[value].get("v_idx", value))

    return None


def normalize_track_mapping_result(
    track_res: Dict[str, Any],
    full_ref_steam: Optional[List[Dict[str, Any]]],
    prematch_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(track_res, dict):
        return {}
    if "track_instructions" in track_res:
        return track_res
    if not isinstance(track_res.get("slots"), dict):
        return track_res

    track_instructions: Dict[str, Dict[str, Any]] = {}
    rejected_slot_keys: List[str] = []
    for slot_key, slot_data in track_res.get("slots", {}).items():
        if not isinstance(slot_data, dict):
            continue
        matched_v_idx = resolve_slot_key_to_v_idx(str(slot_key), full_ref_steam)
        if matched_v_idx is None:
            rejected_slot_keys.append(str(slot_key))
            continue
        for file_idx in slot_data.get("files", []):
            file_key = str(file_idx)
            prematch = prematch_map.get(file_key) if prematch_map else None
            track_instructions[file_key] = {
                "matched_v_idx": matched_v_idx,
                "mbz_track_index": prematch.mbz_track_index if prematch else None,
                "override_title": None,
                "override_track": (
                    str(slot_key)
                    if str(slot_key).isdigit()
                    else (prematch.override_track if prematch else None)
                ),
                "override_disc": None,
                "composer": None,
                "lyricist": None,
                "arranger": None,
                "reason": slot_data.get("reason"),
            }

    normalized = dict(track_res)
    normalized["track_instructions"] = track_instructions
    normalized["rejected_slot_keys"] = rejected_slot_keys
    return normalized


def normalize_identity_result(global_res: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(global_res, dict):
        return {}

    normalized = dict(global_res)
    album_confidence = int(
        normalized.get("album_confidence", normalized.get("identity_confidence", 0) or 0)
    )
    data_quality = int(
        normalized.get("data_quality", normalized.get("integrity_quality", 0) or 0)
    )
    normalized["identity_confidence"] = int(
        normalized.get("identity_confidence", album_confidence) or album_confidence
    )
    normalized["integrity_quality"] = int(
        normalized.get("integrity_quality", data_quality) or data_quality
    )
    normalized["album_confidence"] = album_confidence
    normalized["data_quality"] = data_quality
    normalized.setdefault("mapping_confidence", 0)
    normalized.setdefault("concerns", [])
    return normalized


def build_slot_view(
    track_res: Dict[str, Any],
    local_tracks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(track_res, dict):
        return {"slots": {}, "unassigned_files": [], "unassigned_reason": None}

    if isinstance(track_res.get("slots"), dict):
        known_file_ids = {
            str(file_id)
            for track in local_tracks
            for file_id in track.get("file_ids", [])
        }
        seen_file_ids: set[str] = set()
        rejected_file_ids: List[str] = []
        validated_slots: Dict[str, Dict[str, Any]] = {}
        for slot_key, slot_data in track_res.get("slots", {}).items():
            if not isinstance(slot_data, dict):
                continue
            valid_files = []
            for file_id in slot_data.get("files", []):
                normalized_file_id = str(file_id)
                if known_file_ids and (
                    normalized_file_id not in known_file_ids
                    or normalized_file_id in seen_file_ids
                ):
                    rejected_file_ids.append(normalized_file_id)
                    continue
                valid_files.append(normalized_file_id)
                seen_file_ids.add(normalized_file_id)
            validated_slots[str(slot_key)] = {**slot_data, "files": valid_files}
        local_file_ids = [
            str(file_id)
            for track in local_tracks
            for file_id in track.get("file_ids", [])
        ]
        return {
            "slots": validated_slots,
            "unassigned_files": [
                file_id for file_id in local_file_ids if file_id not in seen_file_ids
            ],
            "unassigned_reason": track_res.get("unassigned_reason"),
            "rejected_file_ids": sorted(set(rejected_file_ids)),
        }

    slots: Dict[str, Dict[str, Any]] = {}
    assigned_files: set[str] = set()
    for file_id, data in (track_res.get("track_instructions") or {}).items():
        if not isinstance(data, dict):
            continue
        matched_v_idx = data.get("matched_v_idx")
        if matched_v_idx is None:
            continue
        try:
            slot_key = str(int(matched_v_idx) + 1)
        except (TypeError, ValueError):
            continue
        slots.setdefault(
            slot_key,
            {"files": [], "confidence": 0.9, "reason": data.get("reason")},
        )
        slots[slot_key]["files"].append(str(file_id))
        assigned_files.add(str(file_id))

    local_file_ids = [
        file_id for track in local_tracks for file_id in track.get("file_ids", [])
    ]
    unassigned_files = [
        str(file_id) for file_id in local_file_ids if str(file_id) not in assigned_files
    ]
    return {
        "slots": slots,
        "unassigned_files": unassigned_files,
        "unassigned_reason": "No slot assignment returned" if unassigned_files else None,
    }


def build_slot_view_from_final_instructions(
    final_instructions: Dict[str, Dict[str, Any]],
    local_tracks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    track_instruction_map: Dict[str, Dict[str, Any]] = {}
    local_file_ids_by_tid: Dict[str, List[str]] = {}

    for track in local_tracks:
        local_key = track.get("local_key")
        if not local_key:
            continue
        tid = f"{local_key[0]}_{local_key[1]}"
        local_file_ids_by_tid[tid] = [
            str(file_id) for file_id in track.get("file_ids", [])
        ]

    for tid, data in final_instructions.items():
        file_ids = local_file_ids_by_tid.get(tid)
        if not file_ids:
            continue
        for file_id in file_ids:
            track_instruction_map[file_id] = {
                "matched_v_idx": data.get("matched_v_idx"),
                "reason": data.get("reason"),
            }

    return build_slot_view({"track_instructions": track_instruction_map}, local_tracks)