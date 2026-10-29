import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from ..models import SteamMetadata
from ..track_grouper import TrackManager

logger = logging.getLogger("sst.processor")

_VERSION_QUALIFIERS = {
    "long", "short", "edit", "extended", "full", "ver", "version",
    "mix", "remix", "chiptuned", "demo", "inst", "instrumental",
    "bonus", "arrange", "arranged", "loop", "ed", "op",
}


def _parse_tid_group_key(tid: str) -> Optional[tuple[int, str]]:
    try:
        disc, clean_title = tid.split("_", 1)
        return int(disc), clean_title
    except (TypeError, ValueError):
        return None


def _get_tid_priority(tid: str, track_groups: Dict, priorities: List[str]) -> int:
    group_key = _parse_tid_group_key(tid)
    if group_key is None:
        return 999
    if group_key in track_groups and track_groups[group_key]:
        fmt = track_groups[group_key][0]["format"].lower()
        try:
            return priorities.index(fmt)
        except ValueError:
            return 999
    return 999


def _get_tid_stem_and_duration(tid: str, track_groups: Dict) -> tuple[str, float, str, Optional[str]]:
    group_key = _parse_tid_group_key(tid)
    if group_key is None or group_key not in track_groups or not track_groups[group_key]:
        return "", 0.0, "", None
    variants = track_groups[group_key]
    raw_title = group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]
    norm_title = TrackManager.normalize_title(raw_title)
    fmt = str(variants[0].get("format", "")).lower()
    duration = float(variants[0].get("duration", 0.0) or 0.0)
    t_num_val = variants[0].get("t_num_val")
    t_num_str = str(t_num_val).strip() if t_num_val not in (None, "", "0") else None
    return norm_title, duration, fmt, t_num_str


def _deduplicate_format_variants_for_slot(
    app_id: int,
    tids: List[str],
    track_groups: Dict,
    final_metadata: Dict[str, Any],
    priorities: List[str],
) -> List[str]:
    tids_sorted = sorted(tids, key=lambda tid: _get_tid_priority(tid, track_groups, priorities))
    best_tid = tids_sorted[0]
    best_group_key = _parse_tid_group_key(best_tid)
    best_norm_title, best_duration, best_format, best_t_num = _get_tid_stem_and_duration(best_tid, track_groups)

    merged_any = False
    tids_to_remove = []
    for tid in tids_sorted[1:]:
        group_key = _parse_tid_group_key(tid)
        this_norm_title, this_duration, this_format, this_t_num = _get_tid_stem_and_duration(tid, track_groups)

        is_different_format = (best_format != this_format) and bool(best_format and this_format)
        duration_difference_ok = abs(best_duration - this_duration) <= 3.0 if (best_duration > 0 and this_duration > 0) else True
        title_matches = (
            (best_norm_title == this_norm_title and bool(best_norm_title))
            or (
                bool(best_norm_title and this_norm_title)
                and (
                    best_norm_title in this_norm_title
                    or this_norm_title in best_norm_title
                    or best_norm_title.replace(" ", "") == this_norm_title.replace(" ", "")
                )
            )
        )
        slot_duration_matches = abs(best_duration - this_duration) <= 1.5 if (best_duration > 0 and this_duration > 0) else False
        same_track_num = (
            best_group_key is not None
            and group_key is not None
            and best_group_key[0] == group_key[0]
            and best_t_num is not None
            and best_t_num == this_t_num
        )
        both_durations_missing = best_duration <= 0 or this_duration <= 0

        can_merge_diff_fmt = is_different_format and (
            (duration_difference_ok and (title_matches or slot_duration_matches))
            or (
                best_norm_title == this_norm_title
                and bool(best_norm_title)
                and same_track_num
                and (both_durations_missing or abs(best_duration - this_duration) <= 5.0)
            )
        )
        can_merge_same_fmt = (not is_different_format) and (
            (slot_duration_matches and (title_matches or same_track_num))
            or (title_matches and same_track_num and both_durations_missing)
            or (best_norm_title == this_norm_title and bool(best_norm_title) and both_durations_missing)
        )
        can_merge = can_merge_diff_fmt or can_merge_same_fmt

        if can_merge:
            if (
                group_key is not None
                and best_group_key is not None
                and group_key in track_groups
                and best_group_key in track_groups
            ):
                for variant in track_groups[group_key]:
                    if variant not in track_groups[best_group_key]:
                        track_groups[best_group_key].append(variant)
                del track_groups[group_key]
            if tid in final_metadata:
                del final_metadata[tid]
            tids_to_remove.append(tid)
            merged_any = True
            logger.info(f"[{app_id}] フォーマット重複を解決: {tid} ({this_format}) を最高品質の {best_tid} ({best_format}) に統合しました (再生時間差: {abs(best_duration - this_duration):.2f}s)。")

    if merged_any:
        if best_group_key is not None and best_group_key in track_groups:
            track_groups[best_group_key].sort(key=lambda variant: priorities.index(variant["format"].lower()) if variant["format"].lower() in priorities else 999)
        return [tid for tid in tids if tid not in tids_to_remove]
    return tids


def _extract_local_titles_for_tid(tid: str, track_groups: Optional[Dict] = None) -> List[str]:
    titles = []
    if "_" in tid:
        raw_local = tid.split("_", 1)[1].split("::", 1)[0]
        titles.append(raw_local)
    group_key = _parse_tid_group_key(tid)
    if track_groups and group_key and group_key in track_groups:
        for variant in track_groups[group_key]:
            t = (variant.get("meta") or {}).get("title") or variant.get("title")
            if t and t not in titles:
                titles.append(t)
    return titles


def _match_titles(norm_local: str, norm_steam: str) -> Tuple[bool, float]:
    """完全一致/プレフィックス一致/空白無視一致、および類似度比率を返す（数値・バージョン矛盾を除外）"""
    if not norm_local or not norm_steam:
        return False, 0.0
    if norm_steam == norm_local or norm_steam.replace(" ", "") == norm_local.replace(" ", ""):
        return True, 1.0

    # Check number token consistency and version qualifier consistency before prefix/fuzzy matching
    local_nums = re.findall(r"\d+", norm_local)
    steam_nums = re.findall(r"\d+", norm_steam)
    if local_nums != steam_nums:
        return False, 0.0

    local_quals = set(norm_local.split()) & _VERSION_QUALIFIERS
    steam_quals = set(norm_steam.split()) & _VERSION_QUALIFIERS
    if local_quals != steam_quals:
        return False, 0.0

    if (
        f" {norm_local} " in f" {norm_steam} "
        or f" {norm_steam} " in f" {norm_local} "
    ):
        return True, 0.95

    sim = SequenceMatcher(None, norm_local, norm_steam).ratio()
    if sim >= 0.80:
        return True, sim
    return False, sim


def _is_exact_title_match(norm_local: str, norm_steam: str) -> bool:
    if not norm_local or not norm_steam:
        return False
    return norm_local == norm_steam or norm_local.replace(" ", "") == norm_steam.replace(" ", "")


def _resolve_multidisc_index_conflicts(
    app_id: int,
    v_idx: int,
    tids: List[str],
    store_tracks: List[Dict[str, Any]],
    final_metadata: Dict[str, Any],
    track_groups: Optional[Dict] = None,
) -> bool:
    local_discs = set(int(tid.split("_", 1)[0]) for tid in tids)
    if len(local_discs) <= 1:
        return False

    logger.info(f"[{app_id}] v_idx {v_idx} のマルチディスクインデックスの衝突を検出しました。ローカルのディスク番号に基づいて再配置を試みます。")
    for tid in tids:
        local_disc_int = int(tid.split("_", 1)[0])
        local_titles = _extract_local_titles_for_tid(tid, track_groups)

        best_match_idx = -1
        for steam_idx, steam_track in enumerate(store_tracks):
            if int(steam_track.get("disc", 1)) == local_disc_int:
                raw_steam = steam_track.get("title") or steam_track.get("name", "")
                norm_steam = TrackManager.normalize_title(raw_steam)
                if not norm_steam:
                    continue
                for raw_l in local_titles:
                    norm_local = TrackManager.normalize_title(raw_l)
                    matched, _ = _match_titles(norm_local, norm_steam)
                    if matched:
                        best_match_idx = steam_idx
                        break
                if best_match_idx != -1:
                    break

        if best_match_idx != -1:
            final_metadata[tid]["matched_v_idx"] = best_match_idx
            track_num = store_tracks[best_match_idx].get("track") or store_tracks[best_match_idx].get("n")
            final_metadata[tid]["reason"] = f"SYSTEM: ローカル構造に基づきDisc {local_disc_int} Track {track_num}に再配置しました"
    return True


def _resolve_disc_title_matches(
    tids: List[str],
    store_tracks: List[Dict[str, Any]],
    v_idx: int,
    final_metadata: Dict[str, Any],
    track_groups: Optional[Dict] = None,
) -> List[str]:
    resolved_tids = set()
    current_steam_track = store_tracks[v_idx] if 0 <= v_idx < len(store_tracks) else None
    current_norm_steam = (
        TrackManager.normalize_title(
            str(current_steam_track.get("title") or current_steam_track.get("name") or "")
        )
        if current_steam_track
        else ""
    )

    # Identify slots that already have a legitimate exact-title owner so fuzzy matches never overwrite them
    exact_owner_slots = set()
    for other_tid, instr in final_metadata.items():
        other_v_idx = instr.get("matched_v_idx")
        if other_v_idx is None or not (0 <= int(other_v_idx) < len(store_tracks)):
            continue
        s_tr = store_tracks[int(other_v_idx)]
        s_norm = TrackManager.normalize_title(str(s_tr.get("title") or s_tr.get("name") or ""))
        if not s_norm:
            continue
        for raw_l in _extract_local_titles_for_tid(other_tid, track_groups):
            if _is_exact_title_match(TrackManager.normalize_title(raw_l), s_norm):
                exact_owner_slots.add(int(other_v_idx))
                break

    for tid in tids:
        local_disc = int(tid.split("_", 1)[0])
        local_titles = _extract_local_titles_for_tid(tid, track_groups)
        local_norms = [TrackManager.normalize_title(raw_l) for raw_l in local_titles if TrackManager.normalize_title(raw_l)]

        # Anchor guard: if this tid already matches the current slot v_idx, NEVER evict it to another slot!
        if current_norm_steam and any(
            _is_exact_title_match(nl, current_norm_steam) or _match_titles(nl, current_norm_steam)[0]
            for nl in local_norms
        ):
            continue

        candidates_same_disc = []
        candidates_other_disc = []

        for steam_idx, steam_track in enumerate(store_tracks):
            if steam_idx == v_idx:
                continue
            s_disc = int(steam_track.get("disc", 1))
            raw_steam = steam_track.get("title") or steam_track.get("name", "")
            norm_steam = TrackManager.normalize_title(raw_steam)
            if not norm_steam:
                continue

            for norm_local in local_norms:
                is_exact = _is_exact_title_match(norm_local, norm_steam)
                matched, sim = (True, 1.0) if is_exact else _match_titles(norm_local, norm_steam)
                if matched:
                    if not is_exact and steam_idx in exact_owner_slots:
                        continue
                    entry = (steam_idx, raw_steam, sim)
                    if s_disc == local_disc:
                        candidates_same_disc.append(entry)
                    else:
                        candidates_other_disc.append(entry)
                    break

        best_match = None
        if candidates_same_disc:
            candidates_same_disc.sort(key=lambda x: x[2], reverse=True)
            s_idx, s_name, sim = candidates_same_disc[0]
            best_match = (s_idx, s_name, sim, False)
        elif len(candidates_other_disc) == 1:
            s_idx, s_name, sim = candidates_other_disc[0]
            best_match = (s_idx, s_name, sim, True)

        if best_match is not None:
            s_idx, s_name, sim, is_other = best_match
            final_metadata[tid]["matched_v_idx"] = s_idx
            disc_desc = "他ディスク" if is_other else ""
            if sim == 1.0:
                final_metadata[tid]["reason"] = f"SYSTEM: 曲名の一致により正しい{disc_desc}インデックスを復元しました ('{s_name}')"
            else:
                final_metadata[tid]["reason"] = f"SYSTEM: ファジーマッチにより正しい{disc_desc}インデックスを復元しました ('{s_name}', 類似度: {sim:.2f})"
            resolved_tids.add(tid)

    return [tid for tid in tids if tid not in resolved_tids]


def _resolve_sequential_track_duplicates(
    app_id: int,
    remaining_tids: List[str],
    store_tracks: List[Dict[str, Any]],
    v_idx: int,
    track_groups: Dict,
    final_metadata: Dict[str, Any],
) -> None:
    base_track = store_tracks[v_idx] if v_idx < len(store_tracks) else None
    if not base_track:
        return
    base_name = TrackManager.normalize_title(base_track.get("title") or base_track.get("name", ""))
    if not base_name:
        return

    occupied_indices = {
        int(instr["matched_v_idx"])
        for tid, instr in final_metadata.items()
        if tid not in remaining_tids and instr.get("matched_v_idx") is not None
    }

    sequence_indices = [v_idx]
    for next_idx in range(v_idx + 1, len(store_tracks)):
        if next_idx in occupied_indices:
            break
        next_track = store_tracks[next_idx]
        next_name = TrackManager.normalize_title(next_track.get("title") or next_track.get("name", ""))
        if next_name == base_name:
            sequence_indices.append(next_idx)
        else:
            break

    if len(sequence_indices) >= len(remaining_tids):
        logger.info(f"[{app_id}] インデックス {v_idx} から始まるシーケンスを使用して '{base_name}' ({len(remaining_tids)} トラック) の重複マッピングを解決しています")

        def get_sort_key(track_id: str):
            parts = track_id.split("_", 1)
            try:
                clean_t = parts[1].split("::", 1)[0]
                key = (int(parts[0]), clean_t)
                for g_k in track_groups:
                    if g_k[0] == key[0] and (g_k[1] == key[1] or g_k[1].split("::", 1)[0] == key[1]):
                        return list(track_groups.keys()).index(g_k)
                return 999
            except (ValueError, IndexError):
                return 999

        sorted_tids = sorted(remaining_tids, key=get_sort_key)
        for index, tid in enumerate(sorted_tids):
            new_idx = sequence_indices[index]
            final_metadata[tid]["matched_v_idx"] = new_idx
            final_metadata[tid]["reason"] = f"SYSTEM: '{base_name}' の重複シーケンスを解決しました (インデックス {new_idx} を割り当て)"


def resolve_duplicate_mappings(
    app_id: int,
    final_metadata: Dict[str, Any],
    steam_meta: SteamMetadata,
    track_groups: Dict,
) -> None:
    """Repair duplicate LLM slot assignments using Steam structure and local variants."""
    index_map = defaultdict(list)
    for track_id, instruction in final_metadata.items():
        variant_index = instruction.get("matched_v_idx")
        if variant_index is not None:
            index_map[variant_index].append(track_id)

    store_tracks = steam_meta.store_tracklist or []
    priorities = TrackManager.get_audio_format_priority()

    for variant_index, tids in index_map.items():
        if len(tids) <= 1:
            continue

        tids = _deduplicate_format_variants_for_slot(
            app_id, tids, track_groups, final_metadata, priorities
        )
        if len(tids) <= 1:
            continue

        if _resolve_multidisc_index_conflicts(app_id, variant_index, tids, store_tracks, final_metadata, track_groups):
            continue

        remaining_tids = _resolve_disc_title_matches(tids, store_tracks, variant_index, final_metadata, track_groups)
        if len(remaining_tids) <= 1:
            continue

        _resolve_sequential_track_duplicates(
            app_id, remaining_tids, store_tracks, variant_index, track_groups, final_metadata
        )