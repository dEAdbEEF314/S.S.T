import re
from typing import Any, Dict, List, Optional


def resolve_slot_key_to_v_idx(
    slot_key: str,
    full_ref_steam: Optional[List[Dict[str, Any]]],
    assigned_local_tracks: Optional[List[Dict[str, Any]]] = None,
    reason: Optional[str] = None,
) -> Optional[int]:
    if not full_ref_steam:
        return None

    def normalize_key(value: Any) -> str:
        text = str(value).strip()
        return text.lstrip("0") or "0"

    normalized_slot_key = str(slot_key).strip()
    if not normalized_slot_key:
        return None

    local_t = assigned_local_tracks[0] if assigned_local_tracks else None
    local_d = local_t.get("disc") or local_t.get("d") or 1 if local_t else None
    local_n = local_t.get("track_num") or local_t.get("n") or local_t.get("filename_track") if local_t else None
    local_dur = local_t.get("dur") if local_t and local_t.get("dur") is not None else (
        (local_t.get("duration_ms") // 1000) if (local_t and local_t.get("duration_ms")) else None
    )

    # 1. reason 内の明示的スロット表記 ("d1n25", "1_25", "slot 25") とローカル情報の一致検証
    if reason:
        reason_comp = re.search(r"d(\d+)[_\-]?n(\d+)", reason, flags=re.IGNORECASE)
        if not reason_comp:
            reason_comp = re.search(r"\b(\d+)[_\-](\d+)\b", reason)
        if reason_comp:
            r_d = normalize_key(reason_comp.group(1))
            r_n = normalize_key(reason_comp.group(2))
            for track in full_ref_steam:
                t_d = normalize_key(track.get("d") or track.get("disc") or 1)
                t_n = normalize_key(track.get("n", ""))
                if t_d == r_d and t_n == r_n and track.get("v_idx") is not None:
                    if local_n is not None and normalize_key(local_n) == r_n:
                        return int(track["v_idx"])
                    elif local_n is None:
                        return int(track["v_idx"])

    # 2. 複合キー ("1_5", "2-12", "d2_n3", "Disc 2 - 03") の解決
    composite_match = re.match(
        r"^(?:d(?:isc)?\s*)?(\d+)\s*[_\-:/]\s*(?:n|t(?:rack)?\s*)?(\d+)$",
        normalized_slot_key,
        flags=re.IGNORECASE,
    )
    if composite_match:
        disc_part = normalize_key(composite_match.group(1))
        num_part = normalize_key(composite_match.group(2))
        comp_matches = [
            track.get("v_idx")
            for track in full_ref_steam
            if normalize_key(track.get("d") or track.get("disc") or 1) == disc_part
            and normalize_key(track.get("n", "")) == num_part
            and track.get("v_idx") is not None
        ]
        if len(comp_matches) == 1:
            return int(comp_matches[0])
        return None

    # 3. 明示的な v_idx 指定 ("v_idx:12", "v12")
    v_idx_prefix = re.match(
        r"^v(?:_?idx)?\s*[:_=]?\s*(\d+)$",
        normalized_slot_key,
        flags=re.IGNORECASE,
    )
    if v_idx_prefix:
        target_v = int(v_idx_prefix.group(1))
        v_matches = [
            int(track["v_idx"])
            for track in full_ref_steam
            if track.get("v_idx") is not None and int(track["v_idx"]) == target_v
        ]
        if len(v_matches) == 1:
            return v_matches[0]
        return None

    digit_match = re.search(r"\d+", normalized_slot_key)
    extracted_digits = digit_match.group(0) if digit_match else None
    numeric_key = extracted_digits if extracted_digits is not None else normalized_slot_key
    try:
        value = int(numeric_key)
    except (TypeError, ValueError):
        value = None

    is_partial_list = any(
        track.get("v_idx") is not None and int(track.get("v_idx")) != idx
        for idx, track in enumerate(full_ref_steam)
    )

    # 4. 相対連番キー救済ガード（指示書 01 3.2-3）
    # 万が一 LLM が複合キー指示に従わず "1".."K" 等の連番キーを返した場合：
    # 割り当てられたローカル番号 (local_d, local_n) が Steam スロット (s_d, s_n) と一致し、
    # かつ再生時間差が ±3.0秒以内なら、キーの値ではなくそのスロットへ解決する。
    if local_n is not None:
        local_n_norm = normalize_key(local_n)
        local_d_norm = normalize_key(local_d)
        for track in full_ref_steam:
            s_d_norm = normalize_key(track.get("d") or track.get("disc") or 1)
            s_n_norm = normalize_key(track.get("n", ""))
            if s_d_norm == local_d_norm and s_n_norm == local_n_norm and track.get("v_idx") is not None:
                s_dur = track.get("dur")
                if local_dur is not None and s_dur is not None:
                    if abs(int(local_dur) - int(s_dur)) <= 3:
                        return int(track["v_idx"])
                elif value is not None and value != int(local_n):
                    return int(track["v_idx"])

    # 5. スロット番号 "n" との直接一意照合
    normalized_key = normalize_key(normalized_slot_key)
    direct_matches = [
        track
        for track in full_ref_steam
        if track.get("n") is not None
        and normalize_key(track.get("n", "")) == normalized_key
        and track.get("v_idx") is not None
    ]
    if len(direct_matches) == 1:
        target_slot = direct_matches[0]
        # 逆ガード: キー "1" に割り当てられたファイルのローカルトラック番号が local_n == 9 であるのに
        # Slot 1 (s_n == 1) とはトラック番号もタイトルも一致しない場合は拒否
        if local_n is not None and normalize_key(local_n) != normalized_key:
            s_title = str(target_slot.get("t") or target_slot.get("title") or "").strip().lower()
            l_title = str(local_t.get("clean_title") or local_t.get("title") or local_t.get("t") or "").strip().lower() if local_t else ""
            s_dur = target_slot.get("dur")
            title_match = bool(s_title and l_title and (s_title == l_title or s_title in l_title or l_title in s_title))
            dur_match = bool(local_dur is not None and s_dur is not None and abs(int(local_dur) - int(s_dur)) <= 3)
            if not title_match and not dur_match:
                return None
        return int(target_slot["v_idx"])

    if len(direct_matches) > 1:
        return None

    if extracted_digits is not None:
        normalized_digits = normalize_key(extracted_digits)
        direct_matches = [
            track
            for track in full_ref_steam
            if track.get("n") is not None
            and normalize_key(track.get("n", "")) == normalized_digits
            and track.get("v_idx") is not None
        ]
        if len(direct_matches) == 1:
            target_slot = direct_matches[0]
            if local_n is not None and normalize_key(local_n) != normalized_digits:
                s_title = str(target_slot.get("t") or target_slot.get("title") or "").strip().lower()
                l_title = str(local_t.get("clean_title") or local_t.get("title") or local_t.get("t") or "").strip().lower() if local_t else ""
                s_dur = target_slot.get("dur")
                title_match = bool(s_title and l_title and (s_title == l_title or s_title in l_title or l_title in s_title))
                dur_match = bool(local_dur is not None and s_dur is not None and abs(int(local_dur) - int(s_dur)) <= 3)
                if not title_match and not dur_match:
                    return None
            return int(target_slot["v_idx"])
        if len(direct_matches) > 1:
            return None

    if value is None:
        return None

    # 6. is_partial_list における v_idx フォールバック（安全ガード付き: 指示書 01 3.2-2）
    if is_partial_list:
        if value == 0:
            v0_matches = [
                int(track["v_idx"])
                for track in full_ref_steam
                if track.get("v_idx") is not None and int(track["v_idx"]) == 0
            ]
            return v0_matches[0] if len(v0_matches) == 1 else None

        v_matches = [
            track
            for track in full_ref_steam
            if track.get("v_idx") is not None and int(track["v_idx"]) == value
        ]
        if len(v_matches) == 1:
            target_slot = v_matches[0]
            # 安全ガード条件:
            # 1. 割り当てられたローカルファイルの local_n が value ではないこと
            # 2. local_n が解決先スロットの n と一致するか、または再生時間差が ±3.0秒以内であること
            if local_n is not None:
                if int(local_n) == value:
                    return None
                s_n = target_slot.get("n")
                s_dur = target_slot.get("dur")
                num_matches = (s_n is not None and int(s_n) == int(local_n))
                dur_matches = (local_dur is not None and s_dur is not None and abs(int(local_dur) - int(s_dur)) <= 3)
                if not (num_matches or dur_matches):
                    return None
            return int(target_slot["v_idx"])
        return None

    if value == 0 and full_ref_steam:
        return int(full_ref_steam[0].get("v_idx", 0))

    fallback_index = value - 1
    if 0 <= fallback_index < len(full_ref_steam):
        return int(full_ref_steam[fallback_index].get("v_idx", fallback_index))

    if 0 <= value < len(full_ref_steam):
        return int(full_ref_steam[value].get("v_idx", value))

    return None


PROMPT_DUMMY_FILE_IDS = {"<FILE_ID>", "FILE_ID", "FILE_ID_A", "FILE_ID_B", "FILE_ID_C", "<FILE_ID_A>"}


def _is_unassigned_slot_entry(slot_key: str, slot_data: Dict[str, Any]) -> bool:
    key_norm = str(slot_key).strip().lower()
    if key_norm in {"null", "none", "unassigned", "-1"}:
        return True
    conf = slot_data.get("confidence")
    if conf is not None:
        try:
            if float(conf) <= 0.0:
                return True
        except (TypeError, ValueError):
            pass
    reason = str(slot_data.get("reason") or "").strip().lower()
    if key_norm == "0" and any(
        phrase in reason
        for phrase in ("no matching", "unassigned", "not found", "該当なし", "一致なし", "未割当")
    ):
        return True
    return False


def normalize_track_mapping_result(
    track_res: Dict[str, Any],
    full_ref_steam: Optional[List[Dict[str, Any]]],
    prematch_map: Optional[Dict[str, Any]] = None,
    local_tracks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if not isinstance(track_res, dict):
        return {}
    if "track_instructions" in track_res:
        return track_res
    if not isinstance(track_res.get("slots"), dict):
        return track_res

    fid_to_local_track: Dict[str, Dict[str, Any]] = {}
    if local_tracks:
        for lt in local_tracks:
            if not isinstance(lt, dict):
                continue
            for fid in lt.get("file_ids", []):
                fid_to_local_track[str(fid).strip()] = lt
            if lt.get("file_id") is not None:
                fid_to_local_track[str(lt.get("file_id")).strip()] = lt

    track_instructions: Dict[str, Dict[str, Any]] = {}
    rejected_slot_keys: List[str] = []
    for slot_key, slot_data in track_res.get("slots", {}).items():
        if not isinstance(slot_data, dict):
            continue
        if _is_unassigned_slot_entry(str(slot_key), slot_data):
            continue

        raw_files = slot_data.get("files", [])
        assigned_tracks = [
            fid_to_local_track[str(fid).strip()]
            for fid in raw_files
            if str(fid).strip() in fid_to_local_track
        ]
        slot_reason = slot_data.get("reason")
        matched_v_idx = resolve_slot_key_to_v_idx(
            str(slot_key),
            full_ref_steam,
            assigned_local_tracks=assigned_tracks or None,
            reason=slot_reason,
        )
        if matched_v_idx is None and prematch_map and full_ref_steam:
            valid_v_indices = {
                int(t["v_idx"]) for t in full_ref_steam if t.get("v_idx") is not None
            }
            pm_v_indices = {
                int(prematch_map[str(fid).strip()].target_v_idx)
                for fid in raw_files
                if str(fid).strip() in prematch_map
                and getattr(prematch_map[str(fid).strip()], "target_v_idx", None) is not None
                and int(prematch_map[str(fid).strip()].target_v_idx) in valid_v_indices
            }
            if len(pm_v_indices) == 1:
                matched_v_idx = next(iter(pm_v_indices))

        if matched_v_idx is None:
            rejected_slot_keys.append(str(slot_key))
            continue

        matched_slot = next(
            (t for t in (full_ref_steam or []) if t.get("v_idx") == matched_v_idx),
            None,
        )
        slot_n = matched_slot.get("n") if matched_slot else None
        slot_d = (matched_slot.get("d") or matched_slot.get("disc")) if matched_slot else None

        for file_idx in slot_data.get("files", []):
            file_key = str(file_idx).strip()
            if not file_key or file_key.upper() in PROMPT_DUMMY_FILE_IDS:
                continue
            prematch = prematch_map.get(file_key) if prematch_map else None
            track_instructions[file_key] = {
                "matched_v_idx": matched_v_idx,
                "mbz_track_index": prematch.mbz_track_index if prematch else None,
                "override_title": None,
                "override_track": (
                    str(slot_n)
                    if slot_n is not None
                    else (
                        str(slot_key)
                        if str(slot_key).isdigit()
                        else (prematch.override_track if prematch else None)
                    )
                ),
                "override_disc": str(slot_d) if slot_d is not None else None,
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
                normalized_file_id = str(file_id).strip()
                if not normalized_file_id or normalized_file_id.upper() in PROMPT_DUMMY_FILE_IDS:
                    continue
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