import logging
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from ..models import SteamMetadata
from ..track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


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


def _get_tid_stem_and_duration(tid: str, track_groups: Dict) -> tuple[str, float, str]:
    group_key = _parse_tid_group_key(tid)
    if group_key is None or group_key not in track_groups or not track_groups[group_key]:
        return "", 0.0, ""
    variants = track_groups[group_key]
    raw_title = group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]
    norm_title = TrackManager.normalize_title(raw_title)
    fmt = str(variants[0].get("format", "")).lower()
    duration = float(variants[0].get("duration", 0.0) or 0.0)
    return norm_title, duration, fmt


def _deduplicate_format_variants_for_slot(
    app_id: int,
    tids: List[str],
    track_groups: Dict,
    final_metadata: Dict[str, Any],
    priorities: List[str],
) -> List[str]:
    tids_sorted = sorted(tids, key=lambda tid: _get_tid_priority(tid, track_groups, priorities))
    best_tid = tids_sorted[0]
    best_norm_title, best_duration, best_format = _get_tid_stem_and_duration(best_tid, track_groups)

    merged_any = False
    tids_to_remove = []
    for tid in tids_sorted[1:]:
        this_norm_title, this_duration, this_format = _get_tid_stem_and_duration(tid, track_groups)

        is_different_format = (best_format != this_format) and bool(best_format and this_format)
        duration_difference_ok = abs(best_duration - this_duration) <= 3.0 if (best_duration > 0 and this_duration > 0) else True
        title_matches = (best_norm_title == this_norm_title) or (bool(best_norm_title and this_norm_title) and (best_norm_title in this_norm_title or this_norm_title in best_norm_title))
        slot_duration_matches = abs(best_duration - this_duration) <= 1.5 if (best_duration > 0 and this_duration > 0) else False

        can_merge = is_different_format and duration_difference_ok and (title_matches or slot_duration_matches)

        if can_merge:
            best_group_key = _parse_tid_group_key(best_tid)
            group_key = _parse_tid_group_key(tid)
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
        best_group_key = _parse_tid_group_key(best_tid)
        if best_group_key is not None and best_group_key in track_groups:
            track_groups[best_group_key].sort(key=lambda variant: priorities.index(variant["format"].lower()) if variant["format"].lower() in priorities else 999)
        return [tid for tid in tids if tid not in tids_to_remove]
    return tids


def _resolve_multidisc_index_conflicts(
    app_id: int,
    v_idx: int,
    tids: List[str],
    store_tracks: List[Dict[str, Any]],
    final_metadata: Dict[str, Any],
) -> bool:
    local_discs = set(int(tid.split("_", 1)[0]) for tid in tids)
    if len(local_discs) <= 1:
        return False

    logger.info(f"[{app_id}] v_idx {v_idx} のマルチディスクインデックスの衝突を検出しました。ローカルのディスク番号に基づいて再配置を試みます。")
    for tid in tids:
        local_disc, local_title = tid.split("_", 1)
        local_disc_int = int(local_disc)

        best_match_idx = -1
        for steam_idx, steam_track in enumerate(store_tracks):
            if int(steam_track.get("disc", 1)) == local_disc_int:
                steam_name = (steam_track.get("title") or steam_track.get("name", "")).lower()
                if steam_name == local_title.lower() or steam_name.startswith(local_title.lower()) or local_title.lower().startswith(steam_name):
                    best_match_idx = steam_idx
                    break

        if best_match_idx != -1:
            final_metadata[tid]["matched_v_idx"] = best_match_idx
            final_metadata[tid]["reason"] = f"SYSTEM: ローカル構造に基づきDisc {local_disc_int} Track {store_tracks[best_match_idx].get('track')}に再配置しました"
    return True


def _resolve_disc_title_matches(
    tids: List[str],
    store_tracks: List[Dict[str, Any]],
    v_idx: int,
    final_metadata: Dict[str, Any],
) -> List[str]:
    local_disc = int(tids[0].split("_", 1)[0])

    candidates_in_disc = []
    for steam_idx, steam_track in enumerate(store_tracks):
        if int(steam_track.get("disc", 1)) == local_disc:
            candidates_in_disc.append((steam_idx, (steam_track.get("title") or steam_track.get("name", "")).lower()))

    resolved_tids = set()
    for tid in tids:
        local_title = tid.split("_", 1)[1].lower()
        for steam_idx, steam_name in candidates_in_disc:
            if steam_name == local_title or steam_name.startswith(local_title) or local_title.startswith(steam_name):
                if steam_idx != v_idx:
                    final_metadata[tid]["matched_v_idx"] = steam_idx
                    final_metadata[tid]["reason"] = f"SYSTEM: 曲名の一致により正しいインデックスを復元しました ('{steam_name}')"
                    resolved_tids.add(tid)
                    break
            else:
                similarity = SequenceMatcher(None, local_title, steam_name).ratio()
                if similarity >= 0.80:
                    if steam_idx != v_idx:
                        final_metadata[tid]["matched_v_idx"] = steam_idx
                        final_metadata[tid]["reason"] = f"SYSTEM: ファジーマッチにより正しいインデックスを復元しました ('{steam_name}', 類似度: {similarity:.2f})"
                        resolved_tids.add(tid)
                        break

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
    base_name = (base_track.get("title") or base_track.get("name", "")).lower()

    sequence_indices = [v_idx]
    for next_idx in range(v_idx + 1, len(store_tracks)):
        next_track = store_tracks[next_idx]
        next_name = (next_track.get("title") or next_track.get("name", "")).lower()
        if next_name == base_name or next_name.startswith(base_name) or base_name.startswith(next_name):
            sequence_indices.append(next_idx)
        else:
            break

    if len(sequence_indices) >= len(remaining_tids):
        logger.info(f"[{app_id}] インデックス {v_idx} から始まるシーケンスを使用して '{base_name}' ({len(remaining_tids)} トラック) の重複マッピングを解決しています")

        def get_sort_key(track_id: str):
            parts = track_id.split("_", 1)
            try:
                key = (int(parts[0]), parts[1])
                return list(track_groups.keys()).index(key)
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

        if _resolve_multidisc_index_conflicts(app_id, variant_index, tids, store_tracks, final_metadata):
            continue

        remaining_tids = _resolve_disc_title_matches(tids, store_tracks, variant_index, final_metadata)
        if len(remaining_tids) <= 1:
            continue

        _resolve_sequential_track_duplicates(
            app_id, remaining_tids, store_tracks, variant_index, track_groups, final_metadata
        )