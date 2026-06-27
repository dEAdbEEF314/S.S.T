import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests

from .models import SteamMetadata
from .track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def fetch_album_artwork(
    config: Any,
    mbz_client: Any,
    steam_meta: SteamMetadata,
    mbz_candidates: List[Dict[str, Any]],
    track_groups: Optional[Dict] = None,
) -> Optional[bytes]:
    apic_priority = config.priority_apic.split(",")

    for src in apic_priority:
        src = src.strip().upper()

        if src == "EMBED" and track_groups:
            # Try to find embedded artwork from local files first.
            for (disc, clean_title), files in track_groups.items():
                art = TrackManager.get_best_artwork(files)
                if art:
                    logger.info(f"EMBEDソースからアルバムアートワークを採用しました (トラック: {clean_title})")
                    return art

        elif src == "MBZ" and mbz_candidates:
            url = mbz_client.get_release_artwork_url(mbz_candidates[0]["mbid"])
            if url:
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        logger.info("MBZソースからアルバムアートワークを採用しました")
                        return r.content
                except Exception as e:
                    logger.debug(f"MBZアートワークの取得に失敗しました: {e}")

        elif src in ["PICS_API", "WEB_API"]:
            url = steam_meta.header_image_url
            if not url and steam_meta.app_id:
                url = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_meta.app_id}/header.jpg"
            if url:
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        logger.info(f"{src}ソースからアルバムアートワークを採用しました")
                        return r.content
                except Exception as e:
                    logger.debug(f"Steamアートワーク ({src}) の取得に失敗しました: {e}")

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
    p1_res = llm_log.get("phase1_res", {})
    id_conf = p1_res.get("identity_confidence", 0)
    quality = p1_res.get("integrity_quality", 0)
    ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
    is_fast = llm_log.get("fast_track", False)

    fields = [
        {"name": "AppID", "value": f"[{app_id}](https://store.steampowered.com/app/{app_id})", "inline": True},
        {"name": "Status", "value": f"**{status.upper()}**", "inline": True},
        {"name": "Tracks", "value": str(track_count), "inline": True},
        {"name": "Identity / Quality", "value": f"ID: {id_conf}% / Qual: {quality}%", "inline": True},
        {"name": "Decision Ratio", "value": f"Arch {ratio.get('archive', 0)}% : Rev {ratio.get('review', 0)}%", "inline": True},
    ]

    if is_fast:
        fields.append({"name": "🛡️ Processing Mode", "value": "**DETERMINISTIC FAST-TRACK** (LLM Bypassed)", "inline": True})

    if mbz_candidates:
        top_mbz = mbz_candidates[0]
        mbz_val = f"[{top_mbz.get('album')}](https://musicbrainz.org/release/{top_mbz.get('mbid')}) (Score: {top_mbz.get('score')})"
        fields.append({"name": "MusicBrainz (Top Candidate)", "value": mbz_val, "inline": False})

    fields.append({"name": "⚙️ System Logic Reason", "value": f"**{message}**", "inline": False})

    llm_reason = "Bypassed for Fast-Track" if is_fast else reason
    if len(llm_reason) > 1000:
        llm_reason = llm_reason[:997] + "..."
    fields.append({"name": "🧠 LLM Judgment Reason", "value": llm_reason, "inline": False})

    if any_audio_failures:
        fields.append({"name": "🚨 CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})

    if status == "review":
        notifier.notify_warning(f"要レビュー: {name}", f"AppID {app_id} は手動確認が必要です", fields)
    else:
        notifier.notify_info(f"アーカイブ完了: {name}", f"AppID {app_id} の自動アーカイブに成功しました", fields)


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
