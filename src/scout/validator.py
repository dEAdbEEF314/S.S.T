import re
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger("scout.validator")

class ResultValidator:
    @staticmethod
    def validate(app_id: int, tracks: List[Dict[str, Any]], llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], audio_fail: bool, audio_warn: bool) -> Tuple[str, str, int, str]:
        p1_res = llm_log.get("phase1_res", {})
        id_conf = int(p1_res.get("identity_confidence", 0))
        quality = int(p1_res.get("integrity_quality", 0))
        reason = p1_res.get("confidence_reason", "No LLM response")
        label = p1_res.get("semantic_label", "Review")
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        
        if id_conf < 95 or ratio.get("archive", 0) < 90 or p1_res.get("strategy") == "REVIEW_REQUIRED":
            return "review", f"[{label}] {reason}", id_conf, reason

        status, message = "archive", "Success"
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        u_count = sum(1 for t in tracks if (t["tags"].get("title") or "Unknown") == "Unknown")
        
        dirty_pattern = re.compile(r'^(\d+)([\s.-]+)')
        d_count = 0
        
        chosen_mbz_idx = p1_res.get("global_tags", {}).get("chosen_mbz_index")
        mbz_release = None
        if mbz_candidates and chosen_mbz_idx is not None and chosen_mbz_idx < len(mbz_candidates):
            mbz_release = mbz_candidates[chosen_mbz_idx]

        for t in tracks:
            title = str(t["tags"].get("title", ""))
            track_num = str(t["tags"].get("track_number", "0"))
            match = dirty_pattern.match(title)
            if match:
                if match.group(2) == '.' and match.end() < len(title) and title[match.end()].isdigit():
                    continue
                mbz_titles = [str(tr.get("title", "")).lower() for tr in mbz_release.get("tracks", [])] if mbz_release else []
                if title.lower() in mbz_titles: continue
                prefixed_num = match.group(1).lstrip('0') or '0'
                clean_track_num = track_num.lstrip('0') or '0'
                has_leading_zero = match.group(1).startswith('0') and len(match.group(1)) > 1
                has_strong_separator = any(s in match.group(2) for s in ['.', '-', '_'])
                if prefixed_num == clean_track_num: d_count += 1
                elif has_leading_zero or has_strong_separator: d_count += 1

        track_keys = []
        has_duplicates = False
        for t in tracks:
            d_num = str(t["tags"].get("disc_number", "1")).split('/')[0]
            t_num = str(t["tags"].get("track_number", "0")).split('/')[0]
            key = (d_num, t_num)
            if key in track_keys:
                has_duplicates = True
            track_keys.append(key)

        if z_count > 0 or u_count > 0 or d_count >= 1 or has_duplicates:
            status = "review"
            issues = []
            if z_count > 0: issues.append(f"Track#0 x{z_count}")
            if u_count > 0: issues.append(f"Unknown Title x{u_count}")
            if d_count >= 1: issues.append(f"Dirty/Conflicting Tags x{int(d_count)}")
            if has_duplicates: issues.append("Duplicate Disc/Track pairs")
            message = f"{label} [{', '.join(issues)}]"

        if id_conf < 100 or quality < 95:
            if status == "archive": status, message = "review", f"[{label}] Trust threshold not met ({id_conf}%/{quality}%)"

        if audio_fail: status, message = "review", "[CRITICAL: Audio Source Error]"
        elif audio_warn: status, message = "review", "Audio quality warning detected"
        return status, message, id_conf, reason
