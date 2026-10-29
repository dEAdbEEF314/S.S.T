import logging
import re
from typing import Any, Dict, List, Set

from ..models import SteamMetadata
from ..track_grouper import TrackManager

logger = logging.getLogger("sst.processor")

_UNASSIGNED_VERSION_QUALIFIERS = {
    "long", "short", "edit", "extended", "full", "ver", "version",
    "mix", "remix", "chiptuned", "demo", "inst", "instrumental",
    "bonus", "arrange", "arranged", "loop", "hum",
}


def _find_candidate_unassigned_matches(
    s_disc: int,
    s_num: str,
    s_title: str,
    unassigned_group_keys: List[Any],
    track_groups: Dict,
    final_metadata: Dict[str, Any],
    *,
    exact_only: bool = False,
    all_steam_slot_keys: Set[tuple[int, str]] = frozenset(),
) -> List[tuple[Any, str, List[Dict[str, Any]]]]:
    matching_groups = []
    if not s_title:
        return matching_groups

    s_compact = s_title.replace(" ", "")
    s_nums = re.findall(r"\d+", s_title)
    s_quals = set(s_title.split()) & _UNASSIGNED_VERSION_QUALIFIERS

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
        norm_stem = TrackManager.normalize_title(str(variants[0].get("norm_stem") or "")) if variants else ""

        candidate_titles = [t for t in (track_title, norm_stem) if t]
        if not candidate_titles:
            continue

        number_matches = s_disc == track_disc and s_num == track_number and s_num != "0"

        is_exact = any(
            s_title == ct or (len(s_compact) >= 4 and s_compact == ct.replace(" ", ""))
            for ct in candidate_titles
        )
        if exact_only:
            if is_exact:
                matching_groups.append((group_key, "number_match" if number_matches else "title_match", variants))
            continue

        # Pass 2: Strict word-bounded substring match with number/qualifier/slot-theft guards
        if (
            track_number != "0"
            and not number_matches
            and (track_disc, track_number) in all_steam_slot_keys
        ):
            continue

        title_matches = False
        for ct in candidate_titles:
            if s_title == ct or (len(s_compact) >= 4 and s_compact == ct.replace(" ", "")):
                title_matches = True
                break
            ct_nums = re.findall(r"\d+", ct)
            ct_quals = set(ct.split()) & _UNASSIGNED_VERSION_QUALIFIERS
            if (
                (f" {s_title} " in f" {ct} " or f" {ct} " in f" {s_title} ")
                and s_nums == ct_nums
                and (s_quals == ct_quals or number_matches)
            ):
                title_matches = True
                break

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

    all_steam_slot_keys = {
        (
            int(st.get("disc", 1)),
            str(st.get("number") or st.get("n", "0")).split("/")[0].lstrip("0") or "0",
        )
        for st in store_tracklist
    }

    for exact_only in (True, False):
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
            break

        for index, steam_slot in missing_steam:
            steam_disc = int(steam_slot.get("disc", 1))
            steam_number = str(steam_slot.get("number") or steam_slot.get("n", "0")).split("/")[0].lstrip("0") or "0"
            raw_steam_title = str(steam_slot.get("title") or steam_slot.get("name") or "")
            steam_title = TrackManager.normalize_title(
                re.sub(r"\s+by\s+.+$", "", raw_steam_title, flags=re.IGNORECASE)
            ) or TrackManager.normalize_title(raw_steam_title)

            matching_groups = _find_candidate_unassigned_matches(
                steam_disc,
                steam_number,
                steam_title,
                unassigned_group_keys,
                track_groups,
                final_metadata,
                exact_only=exact_only,
                all_steam_slot_keys=all_steam_slot_keys,
            )
            if not matching_groups:
                continue

            if any(rule == "number_match" for _, rule, _ in matching_groups):
                matching_groups = [
                    mg for mg in matching_groups if mg[1] == "number_match"
                ]

            durations = [float(variant.get("duration", 0.0) or 0.0) for _, _, variants in matching_groups for variant in variants if float(variant.get("duration", 0.0) or 0.0) > 0]
            norm_titles = {
                TrackManager.normalize_title(group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1])
                for group_key, _, _ in matching_groups
            }
            distinct_track_nums = {
                str(variants[0].get("t_num_val") or "0").split("/")[0].lstrip("0") or "0"
                for _, _, variants in matching_groups
                if variants and variants[0].get("t_num_val") not in (None, "", "0")
            }
            is_same_variant_set = (
                len(norm_titles) <= 1
                and len(distinct_track_nums) <= 1
                and (len(durations) < 2 or max(durations) - min(durations) <= 3.0)
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

    # Pass 3: 構造的スロット番号＋再生時間一致による残差確定 (指示書 05 3.3)
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

    total_slots = len(store_tracklist)
    confirmed_ratio = len(assigned_v_indices) / total_slots if total_slots > 0 else 0.0
    can_run_pass3 = (
        bool(missing_steam)
        and bool(unassigned_group_keys)
        and (confirmed_ratio >= 0.70 or len(missing_steam) <= 4)
    )

    if can_run_pass3:
        other_missing_titles = {
            TrackManager.normalize_title(str(st.get("title") or st.get("name") or ""))
            for _, st in missing_steam
        }

        for index, steam_slot in list(missing_steam):
            steam_disc = int(steam_slot.get("disc", 1))
            steam_number_str = str(steam_slot.get("number") or steam_slot.get("n", "0")).split("/")[0].lstrip("0") or "0"
            if not steam_number_str.isdigit() or int(steam_number_str) <= 0:
                continue
            steam_num = int(steam_number_str)
            s_dur = float(steam_slot.get("duration_s") or steam_slot.get("duration") or 0.0)
            if s_dur <= 0:
                continue

            raw_steam_title = str(steam_slot.get("title") or steam_slot.get("name") or "")
            steam_title = TrackManager.normalize_title(
                re.sub(r"\s+by\s+.+$", "", raw_steam_title, flags=re.IGNORECASE)
            ) or TrackManager.normalize_title(raw_steam_title)

            matching_unassigned = []
            for group_key in list(unassigned_group_keys):
                u_disc = int(group_key[0])
                if u_disc != steam_disc:
                    continue
                variants = track_groups.get(group_key, [])
                if not variants:
                    continue
                v0 = variants[0]
                u_num_raw = str(v0.get("t_num_val") or v0.get("track_num") or v0.get("filename_track_val") or "").split("/")[0].lstrip("0") or "0"
                if not u_num_raw.isdigit() or int(u_num_raw) != steam_num:
                    continue

                u_durations = [float(v.get("duration", 0.0) or 0.0) for v in variants if float(v.get("duration", 0.0) or 0.0) > 0]
                if not u_durations:
                    continue
                avg_u_dur = sum(u_durations) / len(u_durations)
                dur_diff = abs(avg_u_dur - s_dur)

                u_title_norm = TrackManager.normalize_title(group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1])
                is_dur_compatible = (dur_diff <= 2.0) or (
                    dur_diff <= 3.0 and any(w in u_title_norm for w in steam_title.split() if len(w) >= 3)
                )
                if not is_dur_compatible:
                    continue

                other_titles_without_this = other_missing_titles - {steam_title}
                if u_title_norm in other_titles_without_this:
                    continue

                matching_unassigned.append((group_key, variants))

            if len(matching_unassigned) == 1:
                group_key, variants = matching_unassigned[0]
                track_id = f"{group_key[0]}_{group_key[1]}"
                log_entry = _apply_reconciled_slot(
                    track_id,
                    index,
                    steam_slot,
                    "structural_number_and_duration_match",
                    steam_number_str,
                    steam_title,
                    global_identity,
                    final_metadata,
                )
                reconciled_logs.append(log_entry)
                assigned_v_indices.add(index)
                unassigned_group_keys.remove(group_key)

    return reconciled_logs