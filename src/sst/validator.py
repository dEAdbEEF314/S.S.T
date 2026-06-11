import re
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger("sst.validator")

class ResultValidator:
    @staticmethod
    def validate(app_id: int, tracks: List[Dict[str, Any]], llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], audio_fail: bool, audio_warn: bool) -> Tuple[str, str, int, int, str]:
        p1_res = llm_log.get("phase1_res", {})
        id_conf = int(p1_res.get("identity_confidence", 0))
        quality = int(p1_res.get("integrity_quality", 0))
        reason = p1_res.get("confidence_reason", "No LLM response")
        label = p1_res.get("semantic_label", "Review")
        strategy = p1_res.get("strategy", "UNKNOWN")
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        
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
        elif strategy == "MBZ_BASED" or strategy == "FINGERPRINT_BASED": 
            strategy_badges.append("MBZ Match")
        elif strategy == "HYBRID": 
            strategy_badges.append("Hybrid (MBZ+Steam)")
        
        if "AcoustID" in str(llm_log): strategy_badges.append("AcoustID")
        badge_str = f"[{'+'.join(strategy_badges)}]" if strategy_badges else ""

        # --- 2. Physical Integrity Checks (Pre-gate) ---
        status = "archive"
        issues = []
        
        # Track #0 / Unknown Title
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        u_count = sum(1 for t in tracks if (t["tags"].get("title") or "Unknown") == "Unknown")
        if z_count > 0: issues.append(f"Track#0 x{z_count}")
        if u_count > 0: issues.append(f"Unknown Title x{u_count}")

        # Dirty Tags (Pre-existing track numbers in titles)
        dirty_pattern = re.compile(r'^(\d+)([\s.-]+)')
        d_count = 0
        chosen_mbz_idx = p1_res.get("global_tags", {}).get("chosen_mbz_index")
        mbz_release = mbz_candidates[chosen_mbz_idx] if mbz_candidates and chosen_mbz_idx is not None and chosen_mbz_idx < len(mbz_candidates) else None

        for t in tracks:
            title = str(t["tags"].get("title", ""))
            track_num = str(t["tags"].get("track_number", "0"))
            match = dirty_pattern.match(title)
            if match:
                if match.group(2) == '.' and match.end() < len(title) and title[match.end()].isdigit(): continue
                mbz_titles = [str(tr.get("title", "")).lower() for tr in mbz_release.get("tracks", [])] if mbz_release else []
                if title.lower() in mbz_titles: continue
                prefixed_num = match.group(1).lstrip('0') or '0'
                clean_track_num = track_num.lstrip('0') or '0'
                if prefixed_num == clean_track_num or any(s in match.group(2) for s in ['.', '-', '_']):
                    d_count += 1
        if d_count >= 1: issues.append(f"Dirty Tags x{int(d_count)}")

        # Duplicate Tracks
        track_keys = []
        duplicate_pairs = []
        for t in tracks:
            key = (str(t["tags"].get("disc_number", "1")).split('/')[0], str(t["tags"].get("track_number", "0")).split('/')[0])
            if key in track_keys: duplicate_pairs.append(f"{key}")
            track_keys.append(key)
        if duplicate_pairs: issues.append(f"Duplicates ({len(duplicate_pairs)})")

        # Duplicate Titles (Heavy Hallucination Guard)
        titles = [str(t["tags"].get("title", "")).strip() for t in tracks if t["tags"].get("title")]
        from collections import Counter
        most_common_title, count = Counter(titles).most_common(1)[0] if titles else (None, 0)
        if len(tracks) > 3 and count >= (len(tracks) / 2):
            issues.append(f"Duplicate Titles ({count}/{len(tracks)})")

        # Audio Failures
        if audio_fail: issues.append("CRITICAL: Audio Source Error")
        elif audio_warn: issues.append("Audio quality warning")

        # --- 3. Confidence & Quality Thresholds ---
        quality_threshold = 90
        if is_steam_trust and id_conf >= 100:
            quality_threshold = 80 # Relaxed for perfect Steam matches without fingerprint
            
        # Decision Logic: Prioritize scores over LLM's explicit ratio if they are high enough
        is_score_perfect = (id_conf >= 95 and quality >= quality_threshold)
        llm_wants_review = (ratio.get("archive", 0) < 50 or strategy == "REVIEW_REQUIRED")

        if not is_score_perfect and llm_wants_review:
            issues.append("LLM's decision (Low Confidence/Ratio)")
        elif quality < quality_threshold:
            issues.append(f"Quality too low ({quality}%)")
        elif id_conf < 95:
            issues.append(f"Confidence too low ({id_conf}%)")

        # --- 4. Final Status Determination ---
        if issues:
            status = "review"
            message = f"[{', '.join(issues)}]"
        else:
            status = "archive"
            message = f"Success {badge_str}".strip() or "Success (Validated)"

        return status, message, id_conf, quality, reason
