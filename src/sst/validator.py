import re
import logging
from typing import Tuple, List, Dict, Any

from .models import SteamMetadata

logger = logging.getLogger("sst.validator")

class ResultValidator:
    @staticmethod
    def validate(app_id: int, tracks: List[Dict[str, Any]], llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], steam_meta: SteamMetadata, audio_fail: bool, audio_warn: bool) -> Tuple[str, str, int, int, str]:
        p1_res = llm_log.get("phase1_res", {})
        id_conf = int(p1_res.get("identity_confidence", 0))
        quality = int(p1_res.get("integrity_quality", 0))
        album_confidence = int(p1_res.get("album_confidence", id_conf))
        mapping_confidence = int(p1_res.get("mapping_confidence", album_confidence if album_confidence else id_conf))
        data_quality = int(p1_res.get("data_quality", quality))
        reason = p1_res.get("confidence_reason")
        if reason is None:
            reason = "No LLM response"
        strategy = p1_res.get("strategy", "UNKNOWN")
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        is_fast_track = bool(llm_log.get("fast_track", False))
        alignment_res = llm_log.get("alignment_res", {}) or {}
        
        # --- 1. Decision Strategy Badges ---
        strategy_badges = []
        is_steam_trust = False
        
        if strategy == "STEAM_BASED" or "STEAM-TRUST" in str(llm_log):
            strategy_badges.append("Steam Trust")
            is_steam_trust = True
        elif strategy == "LOCAL_BASED" and "シングル盤の法則" in str(llm_log): 
            strategy_badges.append("Fallback (Single)")
        elif strategy == "LOCAL_BASED": 
            strategy_badges.append("Steam Fallback")
        elif strategy in {"MBZ_BASED", "ACOUSTID_BASED", "FINGERPRINT_BASED"}:
            strategy_badges.append("MBZ Match")
        elif strategy == "HYBRID": 
            strategy_badges.append("Hybrid (MBZ+Steam)")
        
        if "AcoustID" in str(llm_log):
            strategy_badges.append("AcoustID")
        badge_str = f"[{'+'.join(strategy_badges)}]" if strategy_badges else ""

        # --- 2. Physical Integrity Checks (Pre-gate) ---
        status = "archive"
        issues = []

        if not steam_meta.store_tracklist:
            issues.append("Steam Tracklist Missing")
        else:
            expected_keys = {
                (str(track.get("disc", 1)), str(track.get("number", "0")).split("/")[0])
                for track in steam_meta.store_tracklist
            }
            final_keys = {
                (
                    str(track.get("tags", {}).get("disc_number", "1")).split("/")[0],
                    str(track.get("tags", {}).get("track_number", "0")).split("/")[0],
                )
                for track in tracks
            }
            missing_count = len(expected_keys - final_keys)
            unexpected_count = len(final_keys - expected_keys)
            if missing_count:
                issues.append(f"Steam Slots Missing ({missing_count})")
            if unexpected_count:
                issues.append(f"Steam Slots Unexpected ({unexpected_count})")

        unassigned_files = alignment_res.get("unassigned_files") or []
        if unassigned_files:
            issues.append(f"Unassigned Files ({len(unassigned_files)})")

        # 提案3: LLM矛盾の拒否を明示（自動修正で隠さない）
        rejected_slot_keys = alignment_res.get("rejected_slot_keys") or []
        if rejected_slot_keys:
            issues.append(f"LLM Rejected Slots ({len(rejected_slot_keys)})")
        duplicate_assignment_file_ids = alignment_res.get("duplicate_assignment_file_ids") or []
        if duplicate_assignment_file_ids:
            issues.append(f"LLM Duplicate Assignment ({len(duplicate_assignment_file_ids)})")
        
        # Track #0 / Unknown Title. Steam is authoritative: an official
        # Unknown (Unused) slot is legitimate and must not be treated as an
        # anomaly merely because the rendered title contains "Unknown".
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        steam_titles_by_key = {
            (
                str(item.get("disc", 1)).split("/")[0],
                str(item.get("number", "0")).split("/")[0],
            ): str(item.get("title") or item.get("name") or "")
            for item in (steam_meta.store_tracklist or [])
        }
        legitimate_unknown_count = 0
        anomalous_unknown_count = 0
        for track in tracks:
            tags = track.get("tags", {})
            key = (
                str(tags.get("disc_number", "1")).split("/")[0],
                str(tags.get("track_number", "0")).split("/")[0],
            )
            title = str(tags.get("title") or "Unknown").strip()
            if title.casefold().startswith("unknown"):
                steam_title = steam_titles_by_key.get(key, "").strip()
                if steam_title.casefold().startswith("unknown"):
                    legitimate_unknown_count += 1
                else:
                    anomalous_unknown_count += 1
        if z_count > 0:
            issues.append(f"Track#0 x{z_count}")
        if anomalous_unknown_count > 0:
            issues.append(f"Unknown Title x{anomalous_unknown_count}")

        # Dirty Tags (Pre-existing track numbers in titles)
        dirty_pattern = re.compile(r'^(\d+)([\s.-]+)')
        d_count = 0
        chosen_mbz_idx = p1_res.get("global_tags", {}).get("chosen_mbz_index")
        mbz_release = mbz_candidates[chosen_mbz_idx] if mbz_candidates and chosen_mbz_idx is not None and chosen_mbz_idx < len(mbz_candidates) else None
        steam_titles = [str(tr.get("title") or tr.get("name") or "").strip().lower() for tr in (steam_meta.store_tracklist or [])]
        mbz_titles = [str(tr.get("title", "")).strip().lower() for tr in (mbz_release.get("tracks", []) if mbz_release else [])]

        for t in tracks:
            title = str(t["tags"].get("title", "")).strip()
            title_source = str(t.get("title_source", "")).upper()
            track_num = str(t["tags"].get("track_number", "0"))
            
            # If the title source is directly from Steam, it is authoritative by spec
            if title_source == "STEAM" or title.lower() in steam_titles:
                continue

            match = dirty_pattern.match(title)
            if match:
                if match.group(2) == '.' and match.end() < len(title) and title[match.end()].isdigit():
                    continue
                if title.lower() in mbz_titles:
                    continue
                prefixed_num = match.group(1).lstrip('0') or '0'
                clean_track_num = track_num.lstrip('0') or '0'
                if prefixed_num == clean_track_num or any(s in match.group(2) for s in ['.', '-', '_']):
                    d_count += 1
        if d_count >= 1:
            issues.append(f"Dirty Tags x{int(d_count)}")

        # Duplicate Tracks
        track_keys = []
        duplicate_pairs = []
        for t in tracks:
            key = (str(t["tags"].get("disc_number", "1")).split('/')[0], str(t["tags"].get("track_number", "0")).split('/')[0])
            if key in track_keys:
                duplicate_pairs.append(f"{key}")
            track_keys.append(key)
        if steam_meta.store_tracklist and len(tracks) != len(steam_meta.store_tracklist):
            issues.append(f"Output Track Count Mismatch ({len(tracks)}/{len(steam_meta.store_tracklist)})")
        if duplicate_pairs:
            issues.append(f"Duplicates ({len(duplicate_pairs)})")

        # Duplicate Titles (Heavy Hallucination Guard)
        titles = [str(t["tags"].get("title", "")).strip() for t in tracks if t["tags"].get("title")]
        from collections import Counter
        most_common_title, count = Counter(titles).most_common(1)[0] if titles else (None, 0)
        if len(tracks) > 3 and count >= (len(tracks) / 2):
            issues.append(f"Duplicate Titles ({count}/{len(tracks)})")

        # Audio Failures
        if audio_fail:
            issues.append("CRITICAL: Audio Source Error")
        elif audio_warn:
            issues.append("Audio quality warning")

        diagnostics = llm_log.setdefault("diagnostics", {})
        diagnostics["audio_quality_warnings"] = bool(audio_warn)
        diagnostics["audio_source_failures"] = bool(audio_fail)

        # --- 3. Confidence & Quality Thresholds ---
        llm_archive_path = album_confidence >= 90 and mapping_confidence >= 80 and data_quality >= 70
        steam_trust_path = is_steam_trust and album_confidence >= 90 and mapping_confidence >= 75 and data_quality >= 60
        llm_wants_review = (ratio.get("archive", 0) < 50 or strategy == "REVIEW_REQUIRED")

        if not is_fast_track and not llm_archive_path and not steam_trust_path:
            if llm_wants_review:
                issues.append("LLM's decision (Low Confidence/Ratio)")
            if album_confidence < 90:
                issues.append(f"Album confidence too low ({album_confidence}%)")
            if mapping_confidence < (75 if is_steam_trust else 80):
                issues.append(f"Mapping confidence too low ({mapping_confidence}%)")
            if data_quality < (60 if is_steam_trust else 70):
                issues.append(f"Data quality too low ({data_quality}%)")

        # --- 4. Final Status Determination ---
        diagnostics = llm_log.setdefault("diagnostics", {})
        diagnostics["steam_unknown_count"] = legitimate_unknown_count
        diagnostics["anomalous_unknown_count"] = anomalous_unknown_count
        steam_expected_slots = len(steam_meta.store_tracklist or [])
        adopted_slots = len(tracks)
        unassigned_slots = max(0, steam_expected_slots - adopted_slots)
        diagnostics["steam_expected_slots"] = steam_expected_slots
        diagnostics["adopted_slots"] = adopted_slots
        diagnostics["unassigned_slots"] = unassigned_slots
        diagnostics["review_causes"] = list(issues)
        diagnostics["primary_review_cause"] = issues[0] if issues else None
        diagnostics["secondary_review_causes"] = issues[1:]
        if issues:
            status = "review"
            message = f"[{', '.join(issues)}]"
        else:
            status = "archive"
            if is_fast_track:
                message = "Success [Deterministic Fast-Track]"
            elif steam_trust_path:
                message = f"Success [STEAM-TRUST]{badge_str}".strip()
            elif llm_archive_path:
                message = f"Success [LLM-ARCHIVE]{badge_str}".strip()
            else:
                message = f"Success {badge_str}".strip() or "Success (Validated)"

        return status, message, album_confidence, data_quality, reason
