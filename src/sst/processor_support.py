import logging
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import requests

from .models import SteamMetadata
from .track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def _normalize_slot_key(disc_number: Any, track_number: Any) -> Optional[tuple[int, str]]:
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


def build_slot_variant_index(
    final_metadata: Dict[str, Any],
    track_groups: Dict,
    steam_meta: SteamMetadata,
) -> tuple[Dict[tuple[int, str], List[Dict[str, Any]]], Dict[str, tuple[int, str]]]:
    slot_variants: Dict[tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    track_to_slot: Dict[str, tuple[int, str]] = {}
    priorities = TrackManager.get_audio_format_priority()

    def sort_key(variant: Dict[str, Any]) -> int:
        fmt = str(variant.get("format", "")).lower()
        try:
            return priorities.index(fmt)
        except ValueError:
            return 999

    # 1. First pass: map tracks explicitly aligned in final_metadata
    unaligned_groups = []
    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        instr = final_metadata.get(track_id, {}) if isinstance(final_metadata, dict) else {}
        slot_key = None

        matched_v_idx = instr.get("matched_v_idx")
        if matched_v_idx is not None and 0 <= int(matched_v_idx) < len(steam_meta.store_tracklist or []):
            track = steam_meta.store_tracklist[int(matched_v_idx)]
            slot_key = _normalize_slot_key(track.get("disc", 1), track.get("number"))

        if slot_key is None and instr.get("override_track") is not None:
            slot_key = _normalize_slot_key(instr.get("override_disc", disc), instr.get("override_track"))

        if slot_key is not None:
            slot_variants[slot_key].extend(variants)
            track_to_slot[track_id] = slot_key
        else:
            unaligned_groups.append(((disc, clean_title), variants))

    # 2. Second pass: format variant consolidation for unaligned groups
    # If an unaligned group is a format variant of an already assigned slot (same disc, diff format, dur diff < 1.0s, title match),
    # merge it into that slot's variants as a subordinate variant.
    remaining_unaligned = []
    for (disc, clean_title), variants in unaligned_groups:
        track_id = f"{disc}_{clean_title}"
        if not variants:
            continue
        raw_title = clean_title.split("::")[0] if "::" in clean_title else clean_title
        u_norm_title = TrackManager.normalize_title(raw_title)
        u_dur = float(variants[0].get("duration", 0.0) or 0.0)
        u_fmt = str(variants[0].get("format", "")).lower()
        u_num = str(variants[0].get("t_num_val") or "").lstrip("0")

        merged_slot_key = None
        for slot_key, assigned_variants in list(slot_variants.items()):
            if not isinstance(slot_key, tuple) or len(slot_key) != 2 or not str(slot_key[1]).isdigit():
                continue
            s_disc, _ = slot_key
            if s_disc != disc:
                continue

            for a_var in assigned_variants:
                a_fmt = str(a_var.get("format", "")).lower()
                a_dur = float(a_var.get("duration", 0.0) or 0.0)
                a_stem = a_var.get("norm_stem") or ""
                a_num = str(a_var.get("t_num_val") or "").lstrip("0")

                is_diff_fmt = (a_fmt != u_fmt) and bool(a_fmt and u_fmt)
                dur_ok = abs(a_dur - u_dur) < 1.0 if (a_dur > 0 and u_dur > 0) else True
                num_match = (a_num == u_num and a_num != "")
                title_match = bool(u_norm_title and a_stem and (u_norm_title == a_stem or u_norm_title.startswith(a_stem) or a_stem.startswith(u_norm_title)))

                if is_diff_fmt and dur_ok and (title_match or num_match):
                    merged_slot_key = slot_key
                    break
            if merged_slot_key:
                break

        if merged_slot_key is not None:
            slot_variants[merged_slot_key].extend(variants)
            track_to_slot[track_id] = merged_slot_key
        else:
            remaining_unaligned.append(((disc, clean_title), variants))

    # 3. Third pass: fallback for remaining unaligned groups (inferred track or clean_title)
    for (disc, clean_title), variants in remaining_unaligned:
        track_id = f"{disc}_{clean_title}"
        track_numbers = [variant.get("t_num_val") for variant in variants if variant.get("t_num_val") not in (None, "", "0")]
        inferred_track = track_numbers[0] if track_numbers else None
        slot_key = _normalize_slot_key(disc, inferred_track)
        if slot_key is None:
            slot_key = (disc, clean_title)
        slot_variants[slot_key].extend(variants)
        track_to_slot[track_id] = slot_key

    for slot_key, variants in slot_variants.items():
        slot_variants[slot_key] = sorted(variants, key=sort_key)

    return dict(slot_variants), track_to_slot


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
        }
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
                for v in variants:
                    if v.get("file_id"):
                        assigned_file_ids_in_slots.add(str(v["file_id"]))

    selected = []
    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        if track_id in final_metadata or not variants:
            continue

        if track_to_slot_index and track_id in track_to_slot_index:
            s_key = track_to_slot_index[track_id]
            if isinstance(s_key, tuple) and len(s_key) == 2 and str(s_key[1]).isdigit():
                continue

        if unassigned_file_ids is not None:
            variants = [variant for variant in variants if variant.get("file_id") in unassigned_file_ids]
            if not variants:
                continue

        if assigned_file_ids_in_slots:
            variants = [v for v in variants if str(v.get("file_id")) not in assigned_file_ids_in_slots]
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


def merge_embedded_tags_for_slot(slot_variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_tags: Dict[str, Any] = {}
    for variant in slot_variants:
        meta = variant.get("meta") or {}
        for key, value in meta.items():
            if value and str(value).lower() not in {"", "none", "unknown", "0"} and key not in merged_tags:
                merged_tags[key] = value
    return merged_tags


def fetch_album_artwork(
    config: Any,
    mbz_client: Any,
    steam_meta: SteamMetadata,
    mbz_candidates: List[Dict[str, Any]],
    track_groups: Optional[Dict] = None,
) -> Optional[bytes]:
    # 1. EMBED (Local File)
    if track_groups:
        for (disc, clean_title), files in track_groups.items():
            art = TrackManager.get_best_artwork(files)
            if art:
                logger.info(f"EMBEDソースからアルバムアートワークを採用しました (トラック: {clean_title})")
                return art

    # 2. MBZ (High Quality Cover)
    if mbz_candidates:
        url = mbz_client.get_release_artwork_url(mbz_candidates[0]["mbid"])
        if url:
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    logger.info("MBZソースからアルバムアートワークを採用しました")
                    return r.content
            except Exception as e:
                logger.debug(f"MBZアートワークの取得に失敗しました: {e}")

    # 3. Steam (Store Header)
    # 3. STEAM (Header Image)
    if steam_meta.header_image_url:
        logger.info("STEAMソースからアルバムアートワークを採用しました")
        return mbz_client.download_artwork(steam_meta.header_image_url)

    logger.warning("全ソースから有効なアルバムアートワークを取得できませんでした")
    return None


def reconcile_deterministic_unassigned_slots(
    final_metadata: Dict[str, Any],
    track_groups: Dict,
    steam_meta: SteamMetadata,
    global_identity: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Reconciles unassigned files with missing Steam slots using a deterministic 1:1 match
    (Sudoku-like elimination) without title synthesis or LLM guessing.
    """
    reconciled_logs = []
    store_tracklist = steam_meta.store_tracklist or []
    if not store_tracklist or not track_groups:
        return reconciled_logs

    assigned_v_indices = {
        instr.get("matched_v_idx")
        for instr in final_metadata.values()
        if instr.get("matched_v_idx") is not None
    }

    missing_steam = [
        (idx, st) for idx, st in enumerate(store_tracklist)
        if idx not in assigned_v_indices
    ]

    assigned_tids = set(final_metadata.keys())
    unassigned_group_keys = [
        key for key in track_groups.keys()
        if f"{key[0]}_{key[1]}" not in assigned_tids
    ]

    if not missing_steam or not unassigned_group_keys:
        return reconciled_logs

    # Find unique 1:1 deterministic matches (number match or strict title match)
    for idx, steam_slot in missing_steam:
        s_disc = int(steam_slot.get("disc", 1))
        s_num = str(steam_slot.get("number") or steam_slot.get("n", "0")).split("/")[0].lstrip("0") or "0"
        s_title = TrackManager.normalize_title(str(steam_slot.get("title") or steam_slot.get("name") or ""))

        matching_groups = []
        for group_key in unassigned_group_keys:
            tid = f"{group_key[0]}_{group_key[1]}"
            if tid in final_metadata:
                continue
            variants = track_groups.get(group_key, [])
            t_disc = int(group_key[0])
            t_num_val = variants[0].get("t_num_val") if variants else None
            t_num = str(t_num_val or "0").split("/")[0].lstrip("0") or "0"

            raw_title = group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]
            t_title = TrackManager.normalize_title(raw_title)

            num_match = (s_disc == t_disc and s_num == t_num and s_num != "0")
            title_match = bool(s_title and t_title and (s_title == t_title or s_title.startswith(t_title) or t_title.startswith(s_title)))

            if num_match or title_match:
                matching_groups.append((group_key, "number_match" if num_match else "title_match", variants))

        # Apply when exactly one match or all matches are multi-format variants of the same track
        if matching_groups:
            durations = [float(v.get("duration", 0.0) or 0.0) for _, _, vars in matching_groups for v in vars]
            is_same_variant_set = (
                len({TrackManager.normalize_title(gk[1].split("::")[0] if "::" in gk[1] else gk[1]) for gk, _, _ in matching_groups}) <= 1
                and (not durations or max(durations) - min(durations) < 1.0)
            )

            if len(matching_groups) == 1 or is_same_variant_set:
                for group_key, match_rule, _ in matching_groups:
                    tid = f"{group_key[0]}_{group_key[1]}"
                    final_metadata[tid] = {
                        "matched_v_idx": idx,
                        "mbz_track_index": None,
                        "override_title": None,
                        "override_track": str(steam_slot.get("number") or steam_slot.get("n")),
                        "override_disc": None,
                        "composer": None,
                        "lyricist": None,
                        "arranger": None,
                        "reason": f"SYSTEM: 決定論的残差確定 (Steam Slot #{s_num}: '{s_title}')",
                        "TPE2": global_identity.get("canonical_album_artist"),
                        "TCON": global_identity.get("canonical_genre"),
                        "TDRC": global_identity.get("canonical_year"),
                        "TPUB": global_identity.get("canonical_label"),
                    }
                    log_entry = {
                        "tid": tid,
                        "matched_v_idx": idx,
                        "steam_slot": s_num,
                        "steam_title": s_title,
                        "rule": match_rule,
                    }
                    reconciled_logs.append(log_entry)
                    logger.info(f"決定論的残差確定: {tid} -> Steam Slot {s_num} ('{s_title}') by {match_rule}")
                assigned_v_indices.add(idx)

    return reconciled_logs


def send_notifications(
    notifier: Any,
    app_id: int,
    name: str,
    status: str,
    message: str,
    score: int,
    reason: str,
    llm_log: Dict[str, Any],
    any_audio_failures: bool,
    track_count: int,
    mbz_candidates: List[Dict[str, Any]],
) -> None:
    p1_res = llm_log.get("phase1_res") or {}
    id_conf = p1_res.get("album_confidence", p1_res.get("identity_confidence", 0))
    mapping_conf = p1_res.get("mapping_confidence", id_conf)
    quality = p1_res.get("data_quality", p1_res.get("integrity_quality", 0))
    ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
    is_fast = llm_log.get("fast_track", False)

    fields = [
        {"name": "AppID", "value": f"[{app_id}](https://store.steampowered.com/app/{app_id})", "inline": True},
        {"name": "Status", "value": f"**{status.upper()}**", "inline": True},
        {"name": "Tracks", "value": str(track_count), "inline": True},
        {"name": "Album / Mapping / Data", "value": f"Alb: {id_conf}% / Map: {mapping_conf}% / Data: {quality}%", "inline": True},
        {"name": "Decision Ratio", "value": f"Arch {ratio.get('archive', 0)}% : Rev {ratio.get('review', 0)}%", "inline": True},
    ]

    if is_fast:
        fields.append({"name": "🛡️ Processing Mode", "value": "**DETERMINISTIC FAST-TRACK** (LLM Bypassed)", "inline": True})

    if mbz_candidates:
        top_mbz = mbz_candidates[0]
        mbz_val = f"[{top_mbz.get('album')}](https://musicbrainz.org/release/{top_mbz.get('mbid')}) (Score: {top_mbz.get('score')})"
        fields.append({"name": "MusicBrainz (Top Candidate)", "value": mbz_val, "inline": False})

    fields.append({"name": "⚙️ System Logic Reason", "value": f"**{message}**", "inline": False})

    llm_reason = "Bypassed for Fast-Track" if is_fast else (reason or "No reason provided.")
    if len(llm_reason) > 1000:
        llm_reason = llm_reason[:997] + "..."
    fields.append({"name": "🧠 LLM Judgment Reason", "value": llm_reason, "inline": False})

    if any_audio_failures:
        fields.append({"name": "🚨 CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})

    if status == "review":
        notifier.notify_warning(f"要レビュー: {name}", f"AppID {app_id} は手動確認が必要です", fields)
    else:
        notifier.notify_info(f"アーカイブ完了: {name}", f"AppID {app_id} の自動アーカイブに成功しました", fields)

    md_lines = [f"# {status.upper()}: {name}", f"AppID: {app_id}", ""]
    for f in fields:
        md_lines.append(f"**{f['name']}**: {f['value']}")
    return "\n".join(md_lines)


def resolve_duplicate_mappings(
    app_id: int,
    final_metadata: Dict[str, Any],
    steam_meta: SteamMetadata,
    track_groups: Dict,
) -> None:
    """
    Detects and resolves duplicate index assignments from LLM by checking
    for sequential same-named tracks in the Steam reference list.
    """
    idx_map = defaultdict(list)
    for tid, instr in final_metadata.items():
        v_idx = instr.get("matched_v_idx")
        if v_idx is not None:
            idx_map[v_idx].append(tid)

    store_tracks = steam_meta.store_tracklist
    for v_idx, tids in idx_map.items():
        if len(tids) <= 1:
            continue

        # --- FORMAT DEDUPLICATION ---
        # ユーザーの「フォーマットごとの仮想アルバム処理」に基づき、
        # 同一のSTEAMトラックにマッピングされた異なるフォーマットのトラックを統合する。
        from .track_grouper import TrackManager
        priorities = TrackManager.get_audio_format_priority()

        def get_group_key(tid):
            try:
                disc, clean_title = tid.split("_", 1)
                return int(disc), clean_title
            except (TypeError, ValueError):
                return None
        
        def get_priority(tid):
            group_key = get_group_key(tid)
            if group_key in track_groups and track_groups[group_key]:
                fmt = track_groups[group_key][0]["format"].lower()
                try:
                    return priorities.index(fmt)
                except ValueError:
                    return 999
            return 999

        def get_stem_and_duration(tid):
            group_key = get_group_key(tid)
            if group_key not in track_groups or not track_groups[group_key]:
                return "", 0.0, ""
            variants = track_groups[group_key]
            raw_title = group_key[1].split("::")[0] if "::" in group_key[1] else group_key[1]
            norm_title = TrackManager.normalize_title(raw_title)
            fmt = str(variants[0].get("format", "")).lower()
            dur = float(variants[0].get("duration", 0.0) or 0.0)
            return norm_title, dur, fmt

        tids_sorted = sorted(tids, key=get_priority)
        best_tid = tids_sorted[0]
        best_norm_title, best_dur, best_fmt = get_stem_and_duration(best_tid)
        
        merged_any = False
        tids_to_remove = []
        for tid in tids_sorted[1:]:
            this_norm_title, this_dur, this_fmt = get_stem_and_duration(tid)

            # 4重AND条件による厳格なバリアント統合判定
            # 1. 異なるフォーマットであること
            # 2. 再生時間差が 1.0s 未満であること
            # 3. 正規化タイトル/Stemが一致または高度に類似していること
            is_diff_fmt = (best_fmt != this_fmt) and bool(best_fmt and this_fmt)
            dur_diff_ok = abs(best_dur - this_dur) < 1.0 if (best_dur > 0 and this_dur > 0) else True
            title_match = (best_norm_title == this_norm_title) or (best_norm_title.startswith(this_norm_title) or this_norm_title.startswith(best_norm_title))

            if is_diff_fmt and dur_diff_ok and title_match:
                best_group_key = get_group_key(best_tid)
                group_key = get_group_key(tid)
                if group_key in track_groups and best_group_key in track_groups:
                    for v in track_groups[group_key]:
                        if v not in track_groups[best_group_key]:
                            track_groups[best_group_key].append(v)
                    del track_groups[group_key]
                if tid in final_metadata:
                    del final_metadata[tid]
                tids_to_remove.append(tid)
                merged_any = True
                logger.info(f"[{app_id}] フォーマット重複を解決: {tid} ({this_fmt}) を最高品質の {best_tid} ({best_fmt}) に統合しました (再生時間差: {abs(best_dur - this_dur):.2f}s)。")

        if merged_any:
            best_group_key = get_group_key(best_tid)
            if best_group_key in track_groups:
                track_groups[best_group_key].sort(key=lambda v: priorities.index(v["format"].lower()) if v["format"].lower() in priorities else 999)
            tids = [t for t in tids if t not in tids_to_remove]
            if len(tids) <= 1:
                continue

        local_discs = set(int(tid.split("_", 1)[0]) for tid in tids)
        if len(local_discs) > 1:
            logger.info(f"[{app_id}] v_idx {v_idx} のマルチディスクインデックスの衝突を検出しました。ローカルのディスク番号に基づいて再配置を試みます。")
            for tid in tids:
                l_disc, l_title = tid.split("_", 1)
                l_disc = int(l_disc)

                best_match_idx = -1
                for s_idx, st in enumerate(store_tracks):
                    if int(st.get("disc", 1)) == l_disc:
                        st_name = (st.get("title") or st.get("name", "")).lower()
                        if st_name == l_title.lower() or st_name.startswith(l_title.lower()) or l_title.lower().startswith(st_name):
                            best_match_idx = s_idx
                            break

                if best_match_idx != -1:
                    final_metadata[tid]["matched_v_idx"] = best_match_idx
                    final_metadata[tid]["action"] = "use_steam"
                    final_metadata[tid]["reason"] = f"SYSTEM: ローカル構造に基づきDisc {l_disc} Track {store_tracks[best_match_idx].get('track')}に再配置しました"
            continue

        l_disc = int(tids[0].split("_", 1)[0])

        candidates_in_disc = []
        for s_idx, st in enumerate(store_tracks):
            if int(st.get("disc", 1)) == l_disc:
                candidates_in_disc.append((s_idx, (st.get("title") or st.get("name", "")).lower()))

        resolved_tids = set()
        for tid in tids:
            l_title_clean = tid.split("_", 1)[1].lower()
            for s_idx, st_name in candidates_in_disc:
                if st_name == l_title_clean or st_name.startswith(l_title_clean) or l_title_clean.startswith(st_name):
                    if s_idx != v_idx:
                        final_metadata[tid]["matched_v_idx"] = s_idx
                        final_metadata[tid]["action"] = "use_steam"
                        final_metadata[tid]["reason"] = f"SYSTEM: 曲名の一致により正しいインデックスを復元しました ('{st_name}')"
                        resolved_tids.add(tid)
                        break
                else:
                    # Fuzzy matching fallback (LOGIC.md §5.1 Heuristic 2)
                    similarity = SequenceMatcher(None, l_title_clean, st_name).ratio()
                    if similarity >= 0.80:
                        if s_idx != v_idx:
                            final_metadata[tid]["matched_v_idx"] = s_idx
                            final_metadata[tid]["action"] = "use_steam"
                            final_metadata[tid]["reason"] = f"SYSTEM: ファジーマッチにより正しいインデックスを復元しました ('{st_name}', 類似度: {similarity:.2f})"
                            resolved_tids.add(tid)
                            break

        remaining_tids = [t for t in tids if t not in resolved_tids]
        if len(remaining_tids) <= 1:
            continue

        base_track = store_tracks[v_idx] if v_idx < len(store_tracks) else None
        if not base_track:
            continue
        base_name = (base_track.get("title") or base_track.get("name", "")).lower()

        sequence_indices = [v_idx]
        for next_idx in range(v_idx + 1, len(store_tracks)):
            nt = store_tracks[next_idx]
            nt_name = (nt.get("title") or nt.get("name", "")).lower()
            if nt_name == base_name or nt_name.startswith(base_name) or base_name.startswith(nt_name):
                sequence_indices.append(next_idx)
            else:
                break

        if len(sequence_indices) >= len(remaining_tids):
            logger.info(f"[{app_id}] インデックス {v_idx} から始まるシーケンスを使用して '{base_name}' ({len(remaining_tids)} トラック) の重複マッピングを解決しています")

            def get_sort_key(tid_str: str):
                parts = tid_str.split("_", 1)
                try:
                    k = (int(parts[0]), parts[1])
                    return list(track_groups.keys()).index(k)
                except (ValueError, IndexError):
                    return 999

            sorted_tids = sorted(remaining_tids, key=get_sort_key)
            for i, tid in enumerate(sorted_tids):
                new_idx = sequence_indices[i]
                final_metadata[tid]["matched_v_idx"] = new_idx
                final_metadata[tid]["action"] = "use_steam"
                final_metadata[tid]["reason"] = f"SYSTEM: '{base_name}' の重複シーケンスを解決しました (インデックス {new_idx} を割り当て)"
