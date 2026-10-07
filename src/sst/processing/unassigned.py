import logging
from typing import Any, Dict, List

from ..models import SteamMetadata
from ..track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def _find_candidate_unassigned_matches(
    s_disc: int,
    s_num: str,
    s_title: str,
    unassigned_group_keys: List[Any],
    track_groups: Dict,
    final_metadata: Dict[str, Any],
) -> List[tuple[Any, str, List[Dict[str, Any]]]]:
    matching_groups = []
    for group_key in unassigned_group_keys:
        track_id = f"{group_key[0]}_{group_key[1]}"
        if track_id in final_metadata:
            continue
        variants = track_groups.get(group_key, [])
        track_disc = int(group_key[0])
        track_number_value = variants[0].get("t_num_val") if variants else None
        track_number = str(track_number_value or "0").split("/")[0].lstrip("0") or "0"

        raw_title = group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]
        track_title = TrackManager.normalize_title(raw_title)

        number_matches = s_disc == track_disc and s_num == track_number and s_num != "0"
        title_matches = bool(
            s_title
            and track_title
            and (
                s_title == track_title
                or s_title.startswith(track_title)
                or track_title.startswith(s_title)
            )
        )

        if title_matches:
            matching_groups.append((group_key, "number_match" if number_matches else "title_match", variants))
    return matching_groups


def _apply_reconciled_slot(
    track_id: str,
    index: int,
    steam_slot: Dict[str, Any],
    match_rule: str,
    steam_number: str,
    steam_title: str,
    global_identity: Dict[str, Any],
    final_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    final_metadata[track_id] = {
        "matched_v_idx": index,
        "mbz_track_index": None,
        "override_title": None,
        "override_track": str(steam_slot.get("number") or steam_slot.get("n")),
        "override_disc": None,
        "composer": None,
        "lyricist": None,
        "arranger": None,
        "reason": f"SYSTEM: 決定論的残差確定 (Steam Slot #{steam_number}: '{steam_title}')",
        "TPE2": global_identity.get("canonical_album_artist"),
        "TCON": global_identity.get("canonical_genre"),
        "TDRC": global_identity.get("canonical_year"),
        "TPUB": global_identity.get("canonical_label"),
    }
    logger.info(f"決定論的残差確定: {track_id} -> Steam Slot {steam_number} ('{steam_title}') by {match_rule}")
    return {
        "tid": track_id,
        "matched_v_idx": index,
        "steam_slot": steam_number,
        "steam_title": steam_title,
        "rule": match_rule,
    }


def reconcile_deterministic_unassigned_slots(
    final_metadata: Dict[str, Any],
    track_groups: Dict,
    steam_meta: SteamMetadata,
    global_identity: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Reconcile unassigned files with missing Steam slots using deterministic 1:1 matches."""
    reconciled_logs = []
    store_tracklist = steam_meta.store_tracklist or []
    if not store_tracklist or not track_groups:
        return reconciled_logs

    assigned_v_indices = {
        instruction.get("matched_v_idx")
        for instruction in final_metadata.values()
        if instruction.get("matched_v_idx") is not None
    }

    missing_steam = [
        (index, steam_track)
        for index, steam_track in enumerate(store_tracklist)
        if index not in assigned_v_indices
    ]

    assigned_track_ids = set(final_metadata.keys())
    unassigned_group_keys = [
        key for key in track_groups.keys()
        if f"{key[0]}_{key[1]}" not in assigned_track_ids
    ]

    if not missing_steam or not unassigned_group_keys:
        return reconciled_logs

    for index, steam_slot in missing_steam:
        steam_disc = int(steam_slot.get("disc", 1))
        steam_number = str(steam_slot.get("number") or steam_slot.get("n", "0")).split("/")[0].lstrip("0") or "0"
        steam_title = TrackManager.normalize_title(str(steam_slot.get("title") or steam_slot.get("name") or ""))

        matching_groups = _find_candidate_unassigned_matches(
            steam_disc, steam_number, steam_title, unassigned_group_keys, track_groups, final_metadata
        )
        if not matching_groups:
            continue

        durations = [float(variant.get("duration", 0.0) or 0.0) for _, _, variants in matching_groups for variant in variants]
        is_same_variant_set = (
            len({TrackManager.normalize_title(group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]) for group_key, _, _ in matching_groups}) <= 1
            and (not durations or max(durations) - min(durations) < 1.0)
        )

        if len(matching_groups) == 1 or is_same_variant_set:
            for group_key, match_rule, _ in matching_groups:
                track_id = f"{group_key[0]}_{group_key[1]}"
                log_entry = _apply_reconciled_slot(
                    track_id,
                    index,
                    steam_slot,
                    match_rule,
                    steam_number,
                    steam_title,
                    global_identity,
                    final_metadata,
                )
                reconciled_logs.append(log_entry)
            assigned_v_indices.add(index)

    return reconciled_logs