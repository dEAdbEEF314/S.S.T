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

    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        instr = final_metadata.get(track_id, {}) if isinstance(final_metadata, dict) else {}
        slot_key = None

        matched_v_idx = instr.get("matched_v_idx")
        if matched_v_idx is not None and 0 <= int(matched_v_idx) < len(steam_meta.store_tracklist or []):
            track = steam_meta.store_tracklist[int(matched_v_idx)]
            slot_key = _normalize_slot_key(track.get("disc", 1), track.get("number"))

        if slot_key is None:
            slot_key = _normalize_slot_key(instr.get("override_disc", disc), instr.get("override_track"))

        if slot_key is None:
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
    url = steam_meta.header_image_url
    if not url and steam_meta.app_id:
        url = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_meta.app_id}/header.jpg"
    if url:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                logger.info("Steamソースからアルバムアートワークを採用しました")
                return r.content
        except Exception as e:
            logger.debug(f"Steamアートワークの取得に失敗しました: {e}")

    return None


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
        if v_idx is not None and instr.get("action") in ["use_steam", "use_fingerprint"]:
            idx_map[v_idx].append(tid)

    store_tracks = steam_meta.store_tracklist
    for v_idx, tids in idx_map.items():
        if len(tids) <= 1:
            continue

        # --- NEW: FORMAT DEDUPLICATION ---
        # ユーザーの「フォーマットごとの仮想アルバム処理」に基づき、
        # LLMが同一のSTEAMトラックにマッピングした異なるフォーマットのトラックを統合する。
        from .track_grouper import TrackManager
        priorities = TrackManager.get_audio_format_priority()
        
        def get_priority(tid):
            if tid in track_groups and track_groups[tid]:
                fmt = track_groups[tid][0]["format"].lower()
                try:
                    return priorities.index(fmt)
                except ValueError:
                    return 999
            return 999

        tids_sorted = sorted(tids, key=get_priority)
        best_tid = tids_sorted[0]
        
        merged_any = False
        tids_to_remove = []
        for tid in tids_sorted[1:]:
            try:
                best_stem = best_tid.split("_", 1)[1].rsplit(" ", 1)[0]
                this_stem = tid.split("_", 1)[1].rsplit(" ", 1)[0]
            except Exception:
                best_stem = best_tid
                this_stem = tid

            if best_stem == this_stem:
                if tid in track_groups:
                    for v in track_groups[tid]:
                        if v not in track_groups[best_tid]:
                            track_groups[best_tid].append(v)
                    del track_groups[tid]
                if tid in final_metadata:
                    del final_metadata[tid]
                tids_to_remove.append(tid)
                merged_any = True
                logger.info(f"[{app_id}] フォーマット重複を解決: {tid} を最高品質の {best_tid} に統合しました。")

        if merged_any:
            if best_tid in track_groups:
                track_groups[best_tid].sort(key=lambda v: priorities.index(v["format"].lower()) if v["format"].lower() in priorities else 999)
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
