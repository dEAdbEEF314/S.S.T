import html
import re
import unicodedata
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional, Set

from .models import SteamMetadata
from .track_grouper import TrackManager
from .llm.assignment_validation import titles_are_compatible

logger = logging.getLogger("sst.validator")

class ResultValidator:
    @staticmethod
    def validate(
        app_id: int,
        tracks: List[Dict[str, Any]],
        llm_log: Dict[str, Any],
        mbz_candidates: List[Dict[str, Any]],
        steam_meta: SteamMetadata,
        audio_fail: bool,
        audio_warn: bool,
        unassigned_manifest: Optional[List[Any]] = None,
        audio_warned_tracks: Optional[List[str]] = None,
    ) -> Tuple[str, str, int, int, str]:
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
        is_verified_mbz_trust = strategy == "MBZ_STEAM_VERIFIED"
        
        if is_verified_mbz_trust:
            strategy_badges.append("Verified MBZ Steam Release")
        elif strategy == "STEAM_BASED" or "STEAM-TRUST" in str(llm_log):
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

        def _norm_slot(disc: Any, num: Any) -> Tuple[str, str]:
            d = str(disc or "1").split("/")[0].strip().lstrip("0") or "1"
            n = str(num or "0").split("/")[0].strip().lstrip("0") or "0"
            return d, n

        def _normalize_official_title(value: Any) -> str:
            decoded = html.unescape(str(value or ""))
            normalized = unicodedata.normalize("NFKC", decoded)
            return " ".join(normalized.split()).casefold()

        expected_keys: Set[Tuple[str, str]] = set()
        final_keys: Set[Tuple[str, str]] = set()
        expected_titles_by_key: Dict[Tuple[str, str], List[str]] = {}
        if not steam_meta.store_tracklist:
            issues.append("Steam Tracklist Missing")
        else:
            expected_keys = {
                _norm_slot(track.get("disc", 1), track.get("number", "0"))
                for track in steam_meta.store_tracklist
            }
            for steam_track in steam_meta.store_tracklist:
                key = _norm_slot(
                    steam_track.get("disc", 1),
                    steam_track.get("number", "0"),
                )
                expected_titles_by_key.setdefault(key, []).append(
                    str(steam_track.get("title") or steam_track.get("name") or "")
                )
            final_keys = {
                _norm_slot(
                    track.get("tags", {}).get("disc_number", "1"),
                    track.get("tags", {}).get("track_number", "0"),
                )
                for track in tracks
            }
            missing_count = len(expected_keys - final_keys)
            unexpected_count = len(final_keys - expected_keys)
            if missing_count:
                issues.append(f"Steam Slots Missing ({missing_count})")
            if unexpected_count:
                issues.append(f"Steam Slots Unexpected ({unexpected_count})")

        # 未割当ファイルの検証: バリアント統合・残差確定後の真の未割当リストを優先
        actual_unassigned = unassigned_manifest if unassigned_manifest is not None else (alignment_res.get("unassigned_files") or [])
        if actual_unassigned:
            issues.append(f"Unassigned Files ({len(actual_unassigned)})")

        # 提案3: LLM矛盾の拒否を明示（自動修正で隠さない）
        alignment_diagnostics = alignment_res.get("diagnostics") or {}
        rejected_slot_keys = alignment_res.get("rejected_slot_keys") or alignment_diagnostics.get("rejected_slot_keys") or []
        if rejected_slot_keys:
            issues.append(f"LLM Rejected Slots ({len(rejected_slot_keys)})")
        duplicate_assignment_file_ids = alignment_res.get("duplicate_assignment_file_ids") or alignment_diagnostics.get("duplicate_assignment_file_ids") or []
        if duplicate_assignment_file_ids:
            issues.append(f"LLM Duplicate Assignment ({len(duplicate_assignment_file_ids)})")
        contradictory_slot_assignments = (
            alignment_res.get("contradictory_slot_assignments")
            or alignment_diagnostics.get("contradictory_slot_assignments")
            or []
        )
        if contradictory_slot_assignments:
            is_resolved = (
                bool(expected_keys)
                and final_keys == expected_keys
                and not actual_unassigned
                and not rejected_slot_keys
                and not duplicate_assignment_file_ids
            )
            if not is_resolved:
                issues.append(f"LLM Contradictory Slot Assignments ({len(contradictory_slot_assignments)})")
            else:
                logger.info(
                    "Intermediate contradictory slot assignments (%d) resolved by variant adoption (full slot coverage, 0 unassigned)",
                    len(contradictory_slot_assignments),
                )
        deferred_copy_failures = (llm_log.get("diagnostics") or {}).get("deferred_copy_failures") or []
        if deferred_copy_failures:
            issues.append(f"Deferred Copy Recovery Exhausted ({len(deferred_copy_failures)})")
        
        # Track #0 / Unknown Title. Steam is authoritative: an official
        # Unknown (Unused) slot is legitimate and must not be treated as an
        # anomaly merely because the rendered title contains "Unknown".
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        steam_titles_by_key = {
            _norm_slot(item.get("disc", 1), item.get("number", "0")): str(item.get("title") or item.get("name") or "")
            for item in (steam_meta.store_tracklist or [])
        }
        legitimate_unknown_count = 0
        anomalous_unknown_count = 0
        for track in tracks:
            tags = track.get("tags", {})
            key = _norm_slot(tags.get("disc_number", "1"), tags.get("track_number", "0"))
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

        paren_pattern = r"\s*[\(\[（【][^)\]）】]*[\)\]）】]"

        def _expand_title_variants(text_val: Any) -> Set[str]:
            variants: Set[str] = set()
            if not text_val:
                return variants
            s = str(text_val).strip()
            if not s:
                return variants
            variants.add(s)

            # 1. Strip "by <Artist>"
            no_by = re.sub(r"\s+by\s+.+$", "", s, flags=re.IGNORECASE).strip()
            if no_by and no_by != s:
                variants.add(no_by)

            # 2. Split on " - "
            base_parts = [s]
            if no_by and no_by != s:
                base_parts.append(no_by)
            for p in list(base_parts):
                if " - " in p:
                    p1, p2 = p.split(" - ", 1)
                    if p1.strip():
                        base_parts.append(p1.strip())
                    if p2.strip():
                        base_parts.append(p2.strip())

            for p in base_parts:
                variants.add(p)
                np = re.sub(paren_pattern, "", p).strip()
                if np and np != p:
                    variants.add(np)

            # 3. Strip leading track numbers and leading articles
            for v in list(variants):
                sn = re.sub(r"^\d{1,3}[\s._-]+", "", v).strip()
                if sn and sn != v:
                    variants.add(sn)
                    v = sn
                na = re.sub(r"^(?:the|a|an)\s+", "", v, flags=re.IGNORECASE).strip()
                if na and na != v:
                    variants.add(na)

            return variants

        # Build normalized titles for all Steam slots to detect cross-slot title misassignments
        all_steam_norm_titles_by_key: Dict[Tuple[str, str], Set[str]] = {}
        for s_key, exp_titles in expected_titles_by_key.items():
            norm_set: Set[str] = set()
            for t in exp_titles:
                if not t:
                    continue
                for tv in _expand_title_variants(t):
                    norm_off = _normalize_official_title(tv)
                    if norm_off:
                        norm_set.add(norm_off)
                    norm_tm = TrackManager.normalize_title(tv)
                    if norm_tm:
                        norm_set.add(norm_tm)
            norm_set.discard("")
            all_steam_norm_titles_by_key[s_key] = norm_set

        track_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for t in tracks:
            t_tags = t.get("tags", {})
            t_key = _norm_slot(
                t_tags.get("disc_number", "1"),
                t_tags.get("track_number", "0"),
            )
            track_by_key[t_key] = t

        official_title_mismatch_count = 0
        for track in tracks:
            tags = track.get("tags", {})
            key = _norm_slot(
                tags.get("disc_number", "1"),
                tags.get("track_number", "0"),
            )
            expected_titles = expected_titles_by_key.get(key, [])
            if not expected_titles:
                continue
            output_title = _normalize_official_title(tags.get("title"))
            if not output_title or not any(
                output_title == _normalize_official_title(expected_title)
                for expected_title in expected_titles
            ):
                official_title_mismatch_count += 1
                continue

            # Additional physical cross-slot title misassignment detection:
            # Check if local origin title belongs to another Steam slot and conflicts with this assigned slot
            assigned_norm_titles = all_steam_norm_titles_by_key.get(key, set())
            raw_local_candidates: List[str] = []
            orig_fn = track.get("original_filename")
            fn_matches_slot_num = False
            if orig_fn:
                stem = Path(orig_fn).stem
                raw_local_candidates.append(stem)
                lead_m = re.match(r"^\D*(\d{1,3})(?:[\s._-]+)", stem)
                if lead_m and str(int(lead_m.group(1))) == key[1]:
                    fn_matches_slot_num = True
            if track.get("original_title"):
                raw_local_candidates.append(str(track["original_title"]))
            if track.get("clean_title"):
                raw_local_candidates.append(str(track["clean_title"]))
            if track.get("original_embedded_title"):
                raw_local_candidates.append(str(track["original_embedded_title"]))

            local_candidates: List[str] = []
            for raw_cand in raw_local_candidates:
                for cv in _expand_title_variants(raw_cand):
                    if cv not in local_candidates:
                        local_candidates.append(cv)

            # 1. Self-slot match check: if any candidate matches the assigned slot
            matches_assigned = False
            for cand in local_candidates:
                cand_off = _normalize_official_title(cand)
                cand_tm = TrackManager.normalize_title(cand)
                cand_norms = {n for n in (cand_off, cand_tm) if n and len(n) >= 2}
                if any(n in assigned_norm_titles for n in cand_norms):
                    matches_assigned = True
                    break

            # Secondary self-slot match: track number matches and titles are compatible
            if not matches_assigned and fn_matches_slot_num:
                if is_verified_mbz_trust or any(
                    titles_are_compatible(c, exp)
                    for c in local_candidates
                    for exp in expected_titles
                ):
                    matches_assigned = True

            # 2. Cross-slot conflict check: ONLY if this track does NOT match its assigned slot
            is_cross_mismatch = False
            if not matches_assigned:
                for cand in local_candidates:
                    cand_off = _normalize_official_title(cand)
                    cand_tm = TrackManager.normalize_title(cand)
                    cand_norms = {n for n in (cand_off, cand_tm) if n and len(n) >= 2}
                    if not cand_norms:
                        continue

                    # Guard against false positive on numbered disambiguation titles (e.g. "Untitled" -> "Untitled 2")
                    if (fn_matches_slot_num or is_verified_mbz_trust) and any(
                        re.match(rf"^{re.escape(n)}\s*\d+$", assigned_t)
                        for n in cand_norms
                        for assigned_t in assigned_norm_titles
                    ):
                        continue

                    # If local candidate matches a different Steam slot in this album, it's a cross-slot conflict
                    for other_key, other_norm_titles in all_steam_norm_titles_by_key.items():
                        if other_key != key and any(n in other_norm_titles for n in cand_norms):
                            is_cross_mismatch = True
                            break
                    if is_cross_mismatch:
                        break

            # 2. 埋め込みタイトル（original_embedded_title）とファイル名のスロット間矛盾（ハイブリッド汚染）の検出
            if not is_cross_mismatch and track.get("original_embedded_title"):
                emb_raw = str(track["original_embedded_title"]).strip()
                if emb_raw:
                    emb_off = _normalize_official_title(emb_raw)
                    emb_tm = TrackManager.normalize_title(emb_raw)
                    emb_norms = {n for n in (emb_off, emb_tm) if n and len(n) >= 2}
                    matches_assigned_emb = any(
                        n in assigned_norm_titles or any(n in at or at in n for at in assigned_norm_titles)
                        for n in emb_norms
                    )
                    if not matches_assigned_emb:
                        for other_k, other_norms in all_steam_norm_titles_by_key.items():
                            if other_k != key and any(n in other_norms for n in emb_norms):
                                other_track = track_by_key.get(other_k)
                                if other_track:
                                    o_emb = str(other_track.get("original_embedded_title") or "").strip()
                                    o_fn = Path(str(other_track.get("original_filename") or "")).stem
                                    o_norms = {
                                        _normalize_official_title(s) for s in (o_emb, o_fn) if s
                                    } | {
                                        TrackManager.normalize_title(s) for s in (o_emb, o_fn) if s
                                    }
                                    if any(n in o_norms for n in emb_norms):
                                        c_dur = track.get("duration_s")
                                        o_dur = other_track.get("duration_s")
                                        if c_dur is not None and o_dur is not None:
                                            try:
                                                if abs(float(c_dur) - float(o_dur)) <= 1.0:
                                                    is_cross_mismatch = True
                                                    break
                                            except (ValueError, TypeError):
                                                is_cross_mismatch = True
                                                break
                                        else:
                                            is_cross_mismatch = True
                                            break
                                else:
                                    is_cross_mismatch = True
                                    break

            if is_cross_mismatch:
                official_title_mismatch_count += 1
        if official_title_mismatch_count:
            issues.append(f"Official Title Mismatch ({official_title_mismatch_count})")

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
            key = _norm_slot(t["tags"].get("disc_number", "1"), t["tags"].get("track_number", "0"))
            if key in track_keys:
                duplicate_pairs.append(f"{key}")
            track_keys.append(key)
        if steam_meta.store_tracklist and len(tracks) != len(steam_meta.store_tracklist):
            issues.append(f"Output Track Count Mismatch ({len(tracks)}/{len(steam_meta.store_tracklist)})")
        if duplicate_pairs:
            issues.append(f"Duplicates ({len(duplicate_pairs)})")

        output_paths = [
            str(track.get("file_path") or "").strip().casefold()
            for track in tracks
            if str(track.get("file_path") or "").strip()
        ]
        duplicate_output_path_count = len(output_paths) - len(set(output_paths))
        if duplicate_output_path_count:
            issues.append(f"Duplicate Output Paths ({duplicate_output_path_count})")

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
            warn_detail = f" (Tracks: {', '.join(audio_warned_tracks)})" if audio_warned_tracks else ""
            issues.append(f"Audio quality warning{warn_detail}")

        diagnostics = llm_log.setdefault("diagnostics", {})
        diagnostics["audio_quality_warnings"] = bool(audio_warn)
        diagnostics["audio_source_failures"] = bool(audio_fail)
        diagnostics["audio_warned_tracks"] = audio_warned_tracks or []
        diagnostics["duplicate_output_path_count"] = duplicate_output_path_count

        # --- 3. Confidence & Quality Thresholds ---
        llm_archive_path = album_confidence >= 90 and mapping_confidence >= 80 and data_quality >= 70
        steam_trust_path = is_steam_trust and album_confidence >= 90 and mapping_confidence >= 75 and data_quality >= 60
        verified_mbz_path = is_verified_mbz_trust
        llm_wants_review = (ratio.get("archive", 0) < 50 or strategy == "REVIEW_REQUIRED")

        if (
            not is_fast_track
            and not verified_mbz_path
            and not llm_archive_path
            and not steam_trust_path
        ):
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
        diagnostics["official_title_mismatch_count"] = official_title_mismatch_count
        steam_expected_slots = len(steam_meta.store_tracklist or [])
        adopted_slots = len(tracks)
        unassigned_slots = max(0, steam_expected_slots - adopted_slots)
        diagnostics["steam_expected_slots"] = steam_expected_slots
        diagnostics["adopted_slots"] = adopted_slots
        diagnostics["unassigned_slots"] = unassigned_slots
        diagnostics["review_causes"] = list(issues)
        diagnostics["primary_review_cause"] = issues[0] if issues else None
        diagnostics["secondary_review_causes"] = issues[1:]

        review_sub_status = None
        if issues:
            status = "review"
            message = f"[{', '.join(issues)}]"

            # BONUS_OR_SE_ISOLATED サブステータス判定
            # 本編スロット100%充足、重複なし、音声破損・Track0等の致命的欠陥なしで、余剰未割当ファイルのみが存在する場合
            fatal_issue_patterns = [
                "Steam Tracklist Missing",
                "Steam Slots Missing",
                "Steam Slots Unexpected",
                "Output Track Count Mismatch",
                "CRITICAL: Audio Source Error",
                "Audio quality warning",
                "Track#0",
                "Unknown Title",
                "Official Title Mismatch",
                "Duplicates",
                "Duplicate Output Paths",
                "Duplicate Titles",
                "Dirty Tags",
                "LLM Rejected Slots",
                "LLM Duplicate Assignment",
                "Deferred Copy Recovery Exhausted",
            ]
            has_fatal_issue = any(any(pat in iss for pat in fatal_issue_patterns) for iss in issues)
            slots_fully_adopted = (steam_expected_slots > 0 and adopted_slots == steam_expected_slots)
            no_duplicates = (len(duplicate_pairs) == 0 and duplicate_output_path_count == 0)
            has_unassigned = len(actual_unassigned) > 0
            no_fatal_defects = (
                not audio_fail
                and not audio_warn
                and z_count == 0
                and anomalous_unknown_count == 0
                and official_title_mismatch_count == 0
            )

            if slots_fully_adopted and no_duplicates and has_unassigned and no_fatal_defects and not has_fatal_issue:
                review_sub_status = "BONUS_OR_SE_ISOLATED"
        else:
            status = "archive"
            if is_fast_track:
                message = "Success [Deterministic Fast-Track]"
            elif verified_mbz_path:
                message = f"Success [MBZ_STEAM_VERIFIED]{badge_str}".strip()
            elif steam_trust_path:
                message = f"Success [STEAM-TRUST]{badge_str}".strip()
            elif llm_archive_path:
                message = f"Success [LLM-ARCHIVE]{badge_str}".strip()
            else:
                message = f"Success {badge_str}".strip() or "Success (Validated)"

        diagnostics["review_sub_status"] = review_sub_status
        return status, message, album_confidence, data_quality, reason
