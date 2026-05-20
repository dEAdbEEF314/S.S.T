import re
import logging
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .ident.embedded import EmbeddedMetadataExtractor
from .notify import NotificationManager
from .db import DatabaseManager
from .builder import MetadataBuilder
from .packager import PackageManager

logger = logging.getLogger("scout.processor")

class LocalProcessor:
    def __init__(self, config: Any, db: DatabaseManager):
        self.config = config
        self.db = db
        self.notifier = NotificationManager(config)
        self.mbz = MusicBrainzIdentifier(config.mbz_app_name, config.mbz_app_version, config.mbz_contact)
        self.llm = LLMOrganizer(
            api_key=config.llm_api_key, base_url=config.llm_base_url, model=config.llm_model,
            rpm=config.llm_limit_rpm, tpm=config.llm_limit_tpm, rpd=config.llm_limit_rpd,
            user_language=config.user_language, llm_backend=config.llm_backend,
            draft_model=getattr(config, "llm_draft_model", None),
            metadata_source_priority=config.metadata_source_priority
        )
        self.working_dir = Path(config.sst_working_dir)

    def _get_localized_now(self):
        from datetime import timezone, timedelta
        import os
        return datetime.now(timezone(timedelta(hours=9))) if os.environ.get("TZ") == "Asia/Tokyo" else datetime.now(timezone.utc)

    def _check_fast_track(self, app_id: int, steam_meta: SteamMetadata, track_groups: Dict, mbz_candidates: List[Dict]) -> Tuple[bool, Optional[Dict], Optional[Dict]]:
        """
        Attempts to bypass LLM if sources are perfectly aligned.
        """
        if not mbz_candidates: return False, None, None
        
        best = mbz_candidates[0]
        evidence = best.get("evidence", [])
        
        # 1. Check for Absolute Identity Proof
        has_direct_link = any(e in evidence for e in ["DIRECT_STEAM_LINK", "DIRECT_STEAMDB_LINK"])
        if not has_direct_link: return False, None, None
        
        # 2. Check for Structural Alignment (Track Count)
        local_count = len(track_groups)
        mbz_count = best.get("track_count", 0)
        pics_count = len(steam_meta.store_tracklist)
        
        if local_count != mbz_count: return False, None, None
        
        # If PICS is available, it must also match
        if pics_count > 0 and local_count != pics_count: return False, None, None
        
        # 3. Decision: Deterministic Archival is possible.
        logger.info(f"[{app_id}] Fast-track enabled: Absolute evidence found.")
        
        # Build global identity deterministically
        global_id = {
            "canonical_album_artist": best.get("artist") or steam_meta.developer,
            "canonical_genre": steam_meta.genres[0] if steam_meta.genres else "Game Music",
            "canonical_year": best.get("year") or (steam_meta.release_date[:4] if steam_meta.release_date else "0000"),
            "canonical_label": best.get("label") or steam_meta.publisher,
            "chosen_mbz_index": 0
        }
        
        # Build track map deterministically (direct index mapping)
        final_map = {}
        sorted_keys = sorted(track_groups.keys()) # (disc, stem)
        for i, key in enumerate(sorted_keys):
            tid = f"{key[0]}_{key[1]}"
            final_map[tid] = {
                "action": "use_mbz",
                "mbz_track_index": i,
                "reason": "Fast-track: Perfect source alignment"
            }
            
        return True, final_map, global_id

    def _auto_select_model(self, track_count: int) -> int:
        """Dynamically switches LLM model and returns optimal context size."""
        if self.config.llm_backend != "OLLAMA":
            return 8192

        if track_count <= 50:
            target_model = self.config.llm_model_small
            target_ctx = 8192
        elif track_count <= 100:
            target_model = self.config.llm_model_medium
            target_ctx = 16384
        else:
            target_model = self.config.llm_model_large
            target_ctx = 32768

        if self.llm.model != target_model:
            logger.info(f"Routing to model: {target_model} (tracks: {track_count})")
            self.llm.model = target_model
        
        return target_ctx

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata, on_track_complete: Optional[callable] = None) -> LocalProcessResult:
        logger.info(f"[{app_id}] --- Processing {steam_meta.name} ---")
        
        try:
            all_files = self._list_audio_files(install_dir)
            if not all_files:
                return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)

            track_groups = self._group_by_logical_track(all_files)
            
            # Adaptive Routing based on track count
            num_ctx = self._auto_select_model(len(track_groups))
            
            local_baseline = self._extract_local_baseline(track_groups)

            # 1. Evidence Gathering
            mbz_candidates, mbz_log = self.mbz.search_release(
                steam_meta.name, 
                len(track_groups), 
                app_id=app_id, 
                parent_app_id=steam_meta.parent_app_id,
                year=steam_meta.release_date[:4] if steam_meta.release_date else None,
                local_baseline=local_baseline
            )
            time.sleep(1.0)
            track_sources = self._prepare_llm_track_context(track_groups)
            
            # 2. Decision Path (Fast-track or LLM)
            is_fast, final_metadata, global_identity = self._check_fast_track(app_id, steam_meta, track_groups, mbz_candidates)
            
            if is_fast:
                llm_log = {
                    "phase1_res": {
                        "identity_confidence": 100, 
                        "integrity_quality": 100, 
                        "archive_vs_review_ratio": {"archive": 100, "review": 0}, 
                        "global_tags": global_identity,
                        "confidence_reason": "Deterministic Fast-track enabled: Album identity and tracklist were perfectly verified against official sources. LLM analysis was skipped to ensure absolute integrity."
                    },
                    "phase1_log": {"reason": "Fast-track Skip"},
                    "fast_track": True
                }
            else:
                final_metadata, llm_log = self.llm.consolidate_metadata(app_id, steam_meta.model_dump(), track_sources, mbz_candidates, num_ctx=num_ctx)
                p1_res = llm_log.get("phase1_res", {})
                global_identity = p1_res.get("global_tags", {})

            if final_metadata is None:
                p1_log = llm_log.get("phase1_log", {})
                error_msg = p1_log.get("error") or "Manual Review Required"
                summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": "review", "confidence_score": 0, 
                                "confidence_reason": error_msg, "processed_at": self._get_localized_now().isoformat(), "tracks": [], "steam_info": steam_meta.model_dump()}
                self.db.record_processed(app_id, "review", steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
                return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=0, confidence_reason=error_msg, message=f"LLM Failure: {error_msg}")

            # 3. Execution Setup
            run_id = datetime.now().strftime('%H%M%S')
            temp_output = self.working_dir / f"final_{app_id}_{run_id}"
            temp_output.mkdir(parents=True, exist_ok=True)
            
            # Temporary buffer for raw files (OUTSIDE of temp_output)
            buffer_dir = self.working_dir / f"buffer_{app_id}_{run_id}"
            buffer_dir.mkdir(parents=True, exist_ok=True)
            
            tagger = AudioTagger(temp_output)
            album_artwork = self._fetch_album_artwork(steam_meta, mbz_candidates)
            if album_artwork: album_artwork = tagger.process_artwork(album_artwork)

            any_audio_warnings, any_audio_failures = False, False

            def _process_single_track(track_data):
                nonlocal any_audio_warnings, any_audio_failures
                (disc, clean_title), adopted_info = track_data
                try:
                    # Native Buffering (Fast I/O area)
                    local_raw_dir = buffer_dir / str(disc)
                    local_raw_dir.mkdir(parents=True, exist_ok=True)
                    local_source_path = local_raw_dir / adopted_info["path"].name
                    shutil.copy2(adopted_info["path"], local_source_path)
                    
                    processed_path, has_warnings = tagger.convert_and_limit(local_source_path, adopted_info["tier"], subdir=str(disc))
                    if has_warnings: any_audio_warnings = True
                    if local_source_path.exists(): local_source_path.unlink()
                    
                    # FALLBACK: If LLM didn't provide mapping (Review mode), use local tag
                    instr = final_metadata.get(f"{disc}_{clean_title}") or {"action": "use_local_tag"}
                    tag_map = MetadataBuilder.build_tag_map(app_id, disc, clean_title, adopted_info, steam_meta, instr, mbz_candidates, track_sources, self.config.user_language_639_2, global_identity)
                    
                    track_art = self._get_best_artwork(track_groups[(disc, clean_title)])
                    tagger.write_tags(processed_path, tag_map, tagger.process_artwork(track_art) if track_art else album_artwork)
                    
                    if on_track_complete: on_track_complete()
                    return {"file_path": f"{disc}/{processed_path.name}", "original_filename": local_source_path.name, "tags": tag_map, "source": instr.get("reason", "Fallback")}
                except Exception as e:
                    err_msg = f"Track failure for {clean_title}: {e}"
                    logger.error(f"[{app_id}] {err_msg}")
                    self.notifier.notify_critical(f"Track Error: {steam_meta.name}", err_msg)
                    any_audio_failures = True
                    return None

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                # Always attempt to process all variants in track_groups
                processed_tracks_meta = [t for t in executor.map(_process_single_track, self._adopt_optimal_files(track_groups).items()) if t]

            # 4. Final Validation (STRICT GATES)
            status, message, score, reason = self._validate_results(app_id, processed_tracks_meta, final_metadata, any_audio_failures, any_audio_warnings, llm_log, mbz_candidates)

            # 5. Result Preservation
            summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": status, "confidence_score": score, 
                            "confidence_reason": reason, "processed_at": self._get_localized_now().isoformat(), 
                            "tracks": processed_tracks_meta, "steam_info": steam_meta.model_dump()}
            
            self._send_notifications(app_id, steam_meta.name, status, message, score, reason, llm_log, any_audio_failures, len(processed_tracks_meta), mbz_candidates)
            
            log_bundle = {
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "llm_log.json": llm_log,
                "AUDIT_REPORT.html": self._generate_html_report(app_id, steam_meta, status, message, score, reason, len(processed_tracks_meta), llm_log, mbz_candidates),
                "BASIS_for_CLASSIFICATION.md": self._generate_classification_basis(app_id, steam_meta, status, message, score, reason, len(processed_tracks_meta), llm_log, mbz_candidates)
            }

            # Human-readable LLM logs
            p1_log = llm_log.get("phase1_log", {})
            
            def md_escape(text):
                if text is None: return "-"
                return str(text).replace("|", "\\|").replace("\n", "<br>")

            def md_blockquote(text):
                if not text: return "> -"
                lines = str(text).strip().split("\n")
                return "\n".join([f"> {line}" for line in lines])

            if p1_log.get("human_prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
            elif p1_log.get("prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["prompt"] # Fallback
            
            # Format LLM Response as Markdown
            if "phase1_res" in llm_log:
                res_data = llm_log["phase1_res"]
                resp_md = f"# LLM Phase 1 Response: {steam_meta.name}\n\n"
                resp_md += f"| Metric | Value |\n|---|---|\n"
                resp_md += f"| Identity Confidence | {res_data.get('identity_confidence')} |\n"
                resp_md += f"| Integrity Quality | {res_data.get('integrity_quality')} |\n"
                resp_md += f"| Strategy | `{res_data.get('strategy')}` |\n"
                resp_md += f"| Semantic Label | {md_escape(res_data.get('semantic_label'))} |\n"
                resp_md += f"\n## Judgment Reasoning\n{md_blockquote(res_data.get('confidence_reason'))}\n\n"
                resp_md += "## Global Tags Applied\n"
                for k, v in res_data.get('global_tags', {}).items():
                    resp_md += f"- **{k}**: {md_escape(v)}\n"
                
                # Check for track instructions (Phase 2)
                if "phase2_logs" in llm_log and llm_log["phase2_logs"]:
                    resp_md += "\n## Track Mapping Instructions (Phase 2)\n\n| Track ID | Action | MBZ Index | Override Title | Reason |\n|---|---|---|---|---|\n"
                    # Combine all chunks
                    for c_log in llm_log["phase2_logs"]:
                        try:
                            parsed = json.loads(c_log.get("response", "{}"))
                            instrs = parsed.get("track_instructions", {})
                            for tid, t_data in instrs.items():
                                action = t_data.get('action', 'N/A')
                                # Highlight interesting actions
                                if action in ["OVERRIDE", "MAP"]: action = f"**{action}**"
                                resp_md += f"| {md_escape(tid)} | {action} | {md_escape(t_data.get('mbz_track_index', '-'))} | {md_escape(t_data.get('override_title', '-'))} | {md_escape(t_data.get('reason', '-'))} |\n"
                        except: pass
                log_bundle["LLM_RESPONSE.md"] = resp_md
            elif p1_log.get("response"): 
                log_bundle["LLM_RESPONSE.md"] = p1_log["response"] # Fallback
            
            # Human-readable Metadata
            meta_md = f"# Final Metadata Summary: {steam_meta.name}\n\n"
            meta_md += f"- **AppID**: [{app_id}](https://store.steampowered.com/app/{app_id})\n"
            meta_md += f"- **Status**: `{status.upper()}`\n"
            meta_md += f"- **Processed At**: {summary_meta.get('processed_at')}\n\n"
            meta_md += "## Track Tags (ID3v2.3 Mapping)\n"
            meta_md += "| # | Title | Artist | Album Artist | Genre | Year | Comment |\n"
            meta_md += "|---|---|---|---|---|---|---|\n"
            for t in summary_meta.get('tracks', []):
                tg = t.get('tags', {})
                meta_md += f"| {md_escape(tg.get('disc_number','1'))}-{md_escape(tg.get('track_number',''))} | {md_escape(tg.get('title',''))} | {md_escape(tg.get('artist',''))} | {md_escape(tg.get('album_artist',''))} | {md_escape(tg.get('genre',''))} | {md_escape(tg.get('year',''))} | {md_escape(tg.get('comment',''))} |\n"
            log_bundle["METADATA.md"] = meta_md
            
            # Human-readable MBZ Log
            if mbz_log:
                mbz_md = f"# MusicBrainz Identification Log: {steam_meta.name}\n\n"
                cands = mbz_log.get('ranked_candidates', [])
                mbz_md += f"- **Target Search Name**: {md_escape(mbz_log.get('target_name', steam_meta.name))}\n"
                mbz_md += f"- **Candidates Found**: {len(cands)}\n\n"
                for c in cands:
                    mbz_md += f"## {md_escape(c.get('album'))} (Score: {c.get('score')})\n"
                    mbz_md += f"- **MBID**: [{c.get('mbid')}](https://musicbrainz.org/release/{c.get('mbid')})\n"
                    mbz_md += f"- **Evidence**: {', '.join([md_escape(e) for e in c.get('evidence', [])])}\n\n"
                if not cands:
                    mbz_md += "No candidates found matching the search criteria.\n"
                log_bundle["MBZ_LOG.md"] = mbz_md

            if not processed_tracks_meta and status != "skip":
                logger.warning(f"[{app_id}] No tracks were processed successfully. Check logs for failures.")
            
            PackageManager.save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle, self.config.sst_output_dir)
            self.db.record_processed(app_id, status, steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
            
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, confidence_score=score, confidence_reason=reason, message=message)

        except Exception as e:
            logger.error(f"[{app_id}] Critical failure: {e}", exc_info=True)
            self.notifier.notify_critical(f"Process Failed: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            if 'temp_output' in locals() and temp_output.exists():
                # Always cleanup in production. In dev (DEBUG), keep only if there was an error for debugging.
                is_debug = self.config.log_level.upper() == "DEBUG"
                should_keep = (is_debug and 'status' in locals() and status == "error")
                if not should_keep:
                    shutil.rmtree(temp_output, ignore_errors=True)
            
            if 'buffer_dir' in locals() and buffer_dir.exists():
                shutil.rmtree(buffer_dir, ignore_errors=True)
        
        return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message="Unexpected fallthrough", confidence_score=0)

    def _extract_local_baseline(self, track_groups: Dict) -> Dict[str, Any]:
        from collections import Counter
        import re
        albums, artists, years, track_names = [], [], [], []
        for (disc, title), variants in track_groups.items():
            t_name = None
            for v in variants:
                if v["meta"]:
                    if v["meta"].get("album"): albums.append(v["meta"]["album"])
                    if v["meta"].get("artist"): artists.append(v["meta"]["artist"])
                    if v["meta"].get("year"): years.append(str(v["meta"]["year"]))
                    if not t_name and v["meta"].get("title"):
                        t_name = v["meta"]["title"]
            if not t_name and variants:
                t_name = variants[0]["path"].stem
                t_name = re.sub(r'^(\d+[\s.-]+)+', '', t_name).strip()
            if t_name:
                track_names.append(t_name)
        def most_common(lst):
            return Counter(lst).most_common(1)[0][0] if lst else None
        return {"album": most_common(albums), "artist": most_common(artists), "year": most_common(years), "tracks": track_names}

    def _validate_results(self, app_id, tracks, llm_data, audio_fail, audio_warn, llm_log, mbz_candidates) -> Tuple[str, str, int, str]:
        p1_res = llm_log.get("phase1_res", {})
        id_conf = int(p1_res.get("identity_confidence", 0))
        quality = int(p1_res.get("integrity_quality", 0))
        reason = p1_res.get("confidence_reason", "No LLM response")
        label = p1_res.get("semantic_label", "Review")
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        
        # Act-14 Cycle 5 Gate: Balanced Audit
        if id_conf < 95 or ratio.get("archive", 0) < 90 or p1_res.get("strategy") == "REVIEW_REQUIRED":
            return "review", f"[{label}] {reason}", id_conf, reason

        status, message = "archive", "Success"
        
        # Physical Anomaly Detection
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        u_count = sum(1 for t in tracks if (t["tags"].get("title") or "Unknown") == "Unknown")
        
        # Smart Dirty Tags (Shared Spec: Tightened for Archive Reliability)
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
                # SAFETY: Check for decimals (e.g. "14.3 Billion Years")
                if match.group(2) == '.' and match.end() < len(title) and title[match.end()].isdigit():
                    continue

                # 1. Check if MBZ title already has this pattern (Spec)
                mbz_titles = [str(tr.get("title", "")).lower() for tr in mbz_release.get("tracks", [])] if mbz_release else []
                if title.lower() in mbz_titles:
                    continue
                
                # 2. Check if the prefixed number matches the MBZ track number
                prefixed_num = match.group(1).lstrip('0') or '0'
                clean_track_num = track_num.lstrip('0') or '0'
                
                has_leading_zero = match.group(1).startswith('0') and len(match.group(1)) > 1
                has_strong_separator = any(s in match.group(2) for s in ['.', '-', '_'])
                
                if prefixed_num == clean_track_num:
                    # Definitely a redundant track number prefix
                    d_count += 1
                elif has_leading_zero or has_strong_separator:
                    # Not matching track number, but looks very much like a track prefix (e.g. "02. ", "01 - ")
                    # This is a Conflicting Tag.
                    d_count += 1
                else:
                    # Does not match and no strong indicators of being a prefix (e.g. "3 Billion Years")
                    # Likely a legitimate title starting with a number.
                    pass

        if z_count > 0 or u_count > 0 or d_count >= 1:
            status = "review"
            issues = []
            if z_count > 0: issues.append(f"Track#0 x{z_count}")
            if u_count > 0: issues.append(f"Unknown Title x{u_count}")
            if d_count >= 1: issues.append(f"Dirty/Conflicting Tags x{int(d_count)}")
            message = f"{label} [{', '.join(issues)}]"

        # Act-16 Absolute Trust Mandate: Any suspicion or logic gate failure forces Review.
        if id_conf < 100 or quality < 95:
            if status == "archive": # Only downgrade if it was otherwise going to be archived
                status, message = "review", f"[{label}] Trust threshold not met ({id_conf}%/{quality}%)"

        if audio_fail: 
            status, message = "review", "[CRITICAL: Audio Source Error]"
        elif audio_warn: 
            status, message = "review", "Audio quality warning detected"

        return status, message, id_conf, reason

    def _send_notifications(self, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates):
        p1_res = llm_log.get("phase1_res", {})
        id_conf = p1_res.get("identity_confidence", 0)
        quality = p1_res.get("integrity_quality", 0)
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        ratio_str = f"Arch {ratio.get('archive', 0)}% : Rev {ratio.get('review', 0)}%"

        fields = [
            {"name": "AppID", "value": f"[{app_id}](https://store.steampowered.com/app/{app_id})", "inline": True},
            {"name": "Status", "value": f"**{status.upper()}**", "inline": True},
            {"name": "Tracks", "value": str(track_count), "inline": True},
            {"name": "Confidence / Quality", "value": f"ID: {id_conf}% / Qual: {quality}%", "inline": True},
            {"name": "Decision Ratio", "value": ratio_str, "inline": True},
        ]
        
        if mbz_candidates:
            top_mbz = mbz_candidates[0]
            fields.append({"name": "MusicBrainz (Top)", "value": f"[{top_mbz.get('album')}](https://musicbrainz.org/release/{top_mbz.get('mbid')}) (Score: {top_mbz.get('score')})", "inline": False})

        fields.append({"name": "Reason / Summary", "value": f"_{message}_\n\n{reason[:800]}", "inline": False})
        
        if any_audio_failures: 
            fields.append({"name": "⚠️ CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})

        if status == "review": 
            self.notifier.notify_warning(f"Review Required: {name}", f"Manual check needed for AppID {app_id}", fields)
        else: 
            self.notifier.notify_info(f"Archived: {name}", f"Quality Check Passed for AppID {app_id}", fields)

    def _generate_html_report(self, app_id, steam_meta, status, message, score, reason, count, llm_log, mbz_candidates):
        is_fast = llm_log.get("fast_track", False)
        status_class = "status-archive" if status == "archive" else "status-review"
        status_label = "🛡️ ARCHIVE SUCCESS" if status == "archive" else "🔍 REVIEW REQUIRED"
        
        # Determine display reason
        display_reason = reason
        if is_fast:
            display_reason = "<strong>🛡️ DETERMINISTIC FAST-TRACK ENABLED</strong><br><br>This album was automatically verified by matching perfect evidence from MusicBrainz or PICS. LLM inference was bypassed to maintain 100% data integrity."

        p1_res = llm_log.get("phase1_res", {})
        global_tags = p1_res.get("global_tags", {})
        chosen_idx = global_tags.get("chosen_mbz_index")
        chosen_id = global_tags.get("chosen_mbz_id")
        mbz_choice_reason = global_tags.get("mbz_choice_reason")

        # MBZ Candidates HTML
        mbz_html = ""
        if mbz_candidates:
            for i, c in enumerate(mbz_candidates[:5]):
                is_chosen = (i == chosen_idx) or (c.get('mbid') == chosen_id)
                chosen_badge = ' <span class="badge" style="background:#238636;">⭐ CHOSEN</span>' if is_chosen else ''
                card_style = ' style="border: 2px solid var(--accent-green); background: #1a2332; padding: 10px; border-radius: 6px; margin-bottom: 5px;"' if is_chosen else ''
                
                mbz_html += f"""
                <div class="mbz-card"{card_style}>
                    <strong>{c.get('album')}</strong> <span class="badge">Score: {c.get('score')}</span>{chosen_badge}<br>
                    <code style="font-size: 0.85rem; color: var(--accent-yellow);">{c.get('mbid')}</code><br>
                    <a href="https://musicbrainz.org/release/{c.get('mbid')}" target="_blank">View on MusicBrainz ↗</a>
                </div>"""
            if mbz_choice_reason:
                mbz_html += f'<div class="reason-box" style="margin-top:10px;"><strong>LLM MBZ Choice Reason:</strong><br>{mbz_choice_reason}</div>'
        else:
            mbz_html = "<p>No matching MusicBrainz candidates found.</p>"

        # Metadata Matrix HTML (Dynamic via METADATA_SOURCE_PRIORITY)
        matrix_rows = ""
        priority_list = [p.strip().upper() for p in self.config.metadata_source_priority.split(',')]
        
        for source in priority_list:
            if source == "STEAM_PICS":
                matrix_rows += f"<tr><td>{source}</td><td>{steam_meta.name}</td><td>{steam_meta.developer or 'N/A'}</td><td>N/A</td><td>N/A</td></tr>"
            elif source == "STEAM_STORE":
                store_track_count = len(steam_meta.store_tracklist) if steam_meta.store_tracklist else 0
                matrix_rows += f"<tr><td>{source}</td><td>{steam_meta.name}</td><td>{steam_meta.developer or 'N/A'}</td><td>{store_track_count}</td><td>{steam_meta.release_date or 'N/A'}</td></tr>"
            elif source == "MBZ":
                if not mbz_candidates:
                    matrix_rows += f"<tr><td>{source}</td><td>N/A</td><td>N/A</td><td>N/A</td><td>N/A</td></tr>"
                else:
                    for i, c in enumerate(mbz_candidates[:5]):
                        is_chosen = (i == chosen_idx) or (c.get('mbid') == chosen_id)
                        row_style = ' style="background-color: #1a2332; font-weight: bold; border-left: 4px solid var(--accent-green);"' if is_chosen else ''
                        matrix_rows += f"<tr{row_style}><td>{source} (Candidate {i} - Score: {c.get('score')})</td><td>{c.get('album')}</td><td>{c.get('artist')}</td><td>{c.get('track_count')}</td><td>{c.get('year')}</td></tr>"
            elif source in ["STEAM_TAGS", "EMBEDDED"]:
                matrix_rows += f"<tr><td>{source}</td><td>(Per-track data)</td><td>N/A</td><td>N/A</td><td>N/A</td></tr>"
            
        html_template = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SST Audit Report - {steam_meta.name}</title>
    <style>
        :root {{
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --text-color: #c9d1d9;
            --accent-green: #238636;
            --accent-yellow: #d29922;
            --border-color: #30363d;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .header {{
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .status-archive {{ background-color: var(--accent-green); color: white; }}
        .status-review {{ background-color: var(--accent-yellow); color: black; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
        }}
        .card h3 {{ margin-top: 0; font-size: 0.9rem; color: #8b949e; text-transform: uppercase; }}
        .reason-box {{
            background-color: #090c10;
            border-left: 4px solid var(--border-color);
            padding: 15px;
            margin: 20px 0;
            font-style: italic;
        }}
        .mbz-card {{
            border-bottom: 1px solid var(--border-color);
            padding: 10px 0;
        }}
        .mbz-card:last-child {{ border-bottom: none; }}
        .badge {{
            font-size: 0.8rem;
            background: #21262d;
            padding: 2px 6px;
            border-radius: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{ background-color: #0d1117; color: #8b949e; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        footer {{
            margin-top: 40px;
            font-size: 0.8rem;
            color: #8b949e;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="status-badge {status_class}">{status_label}</div>
            <h1>{steam_meta.name}</h1>
        </div>

        <div class="grid">
            <div class="card">
                <h3>Confidence Gates</h3>
                <p>Identity: <strong>{p1_res.get('identity_confidence', 0)}%</strong><br>
                Integrity: <strong>{p1_res.get('integrity_quality', 0)}%</strong></p>
            </div>
            <div class="card">
                <h3>Decision Logic</h3>
                <p>System: {message}<br>
                Tracks: {count}</p>
            </div>
            <div class="card">
                <h3>Steam Links</h3>
                <p><a href="https://store.steampowered.com/app/{app_id}" target="_blank">Store Page</a><br>
                AppID: {app_id}</p>
            </div>
        </div>

        <h2>🔍 Analysis & Reasoning</h2>
        <div class="reason-box">
            {display_reason}
        </div>
        
        <div class="card" style="margin-bottom: 20px;">
            <h3>Metadata Information Matrix</h3>
            <table>
                <tr><th>Source</th><th>Album Title</th><th>Artist</th><th>Tracks</th><th>Year</th></tr>
                {matrix_rows}
            </table>
        </div>

        <div class="grid">
            <div class="card" style="grid-column: span 2;">
                <h3>MusicBrainz Candidates (Provided to LLM)</h3>
                {mbz_html}
            </div>
            <div class="card">
                <h3>Final Global Tags</h3>
                <p>Artist: {global_tags.get('canonical_album_artist', 'N/A')}<br>
                Year: {global_tags.get('canonical_year', 'N/A')}<br>
                Label: {global_tags.get('canonical_label', 'N/A')}</p>
            </div>
        </div>

        <footer>
            Report generated by S.S.T (Steam Soundtrack Tagger) at {self._get_localized_now().strftime('%Y-%m-%d %H:%M:%S')}
        </footer>
    </div>
</body>
</html>
"""
        return html_template


    def _generate_classification_basis(self, app_id, steam_meta, status, message, score, reason, count, llm_log, mbz_candidates):
        p1_res = llm_log.get("phase1_res", {})
        id_conf = p1_res.get("identity_confidence", 0)
        quality = p1_res.get("integrity_quality", 0)
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        is_fast = llm_log.get("fast_track", False)
        
        def md_escape(text):
            if text is None: return "-"
            return str(text).replace("|", "\\|").replace("\n", "<br>")

        def md_blockquote(text):
            if not text: return "> -"
            lines = str(text).strip().split("\n")
            return "\n".join([f"> {line}" for line in lines])

        status_emoji = "🛡️ ARCHIVE" if status == "archive" else "🔍 REVIEW REQUIRED"
        
        candidate_md = ""
        if mbz_candidates:
            for c in mbz_candidates[:5]:
                candidate_md += f"- **{md_escape(c.get('album'))}** (Score: {c.get('score')})\n  - {c.get('mbid_url')}\n"
        else:
            candidate_md = "- No matching MusicBrainz candidates found."

        action_required = ""
        if status == "review":
            action_required = f"""
## 🛠️ Action Required
- [ ] Open the output ZIP file and inspect the tags.
- [ ] Use MP3tag to verify track titles and artists against the [Steam Store](https://store.steampowered.com/app/{app_id}).
- [ ] If tags are incorrect, fix them and run `./sst --finalize` to update the database.
"""

        # Logic for 'No LLM response' clarification
        display_reason = reason
        if is_fast:
            display_reason = "🛡️ **DETERMINISTIC FAST-TRACK ENABLED**\n\nThis album was automatically verified by matching perfect evidence (e.g., Direct Steam links, exact track count, and title alignment) from MusicBrainz or PICS. \n\n**LLM inference was bypassed** to maintain 100% data integrity and save tokens."

        return f"""# {status_emoji} Archive Audit Report: {steam_meta.name}

## 📊 Quick Summary
- **AppID**: {app_id}
- **Status**: **{status.upper()}**
- **Confidence Gates**:
  - Identity Confidence: `{id_conf}/100` (Req: 100 for Archive)
  - Integrity Quality: `{quality}/100` (Req: 95 for Archive)
- **Judgment Ratio**: Archive `{ratio.get('archive', 0)}%` / Review `{ratio.get('review', 0)}%`
- **System Decision Reason**: {md_escape(message)}
- **Tracks Processed**: {count}
{action_required}
## 🔍 LLM Reasoning & Strategy
{md_blockquote(display_reason)}

## 🔗 External References
- **Steam Store**: https://store.steampowered.com/app/{app_id}
- **Parent Game**: {md_escape(steam_meta.parent_name) or 'N/A'} (AppID: {steam_meta.parent_app_id or 'N/A'})

## 🎼 MusicBrainz Candidates (Top 5)
{candidate_md}

---
*Report generated by S.S.T (Steam Soundtrack Tagger) at {self._get_localized_now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

    def _list_audio_files(self, directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff"}
        return [p for p in directory.rglob("*") if p.suffix.lower() in exts and not p.name.startswith(".") and "__MACOSX" not in p.parts]

    def _group_by_logical_track(self, files: List[Path]) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        temp_groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            t_num = re.match(r'^(\d+)', f.stem)
            disc = 1
            if meta.get("disc_number"):
                try:
                    d_str = str(meta.get("disc_number")).split('/')[0]
                    if d_str.isdigit(): disc = int(d_str)
                except: pass

            # Clean stem for grouping: remove leading numbers and common suffixes like (AIFF), (MP3), [FLAC]
            stem = f.stem
            stem = re.sub(r'^(\d+[\s.-]+)+', '', stem)
            # Tier 1 Normalization: Suffix removal
            stem = re.sub(r'[\s(\[]+(aiff|mp3|flac|wav|lossless|high-res|ost|soundtrack|official)[\s)\]]+$', '', stem, flags=re.IGNORECASE)
            # Tier 2 Normalization: Aggressive cleaning (removing non-alphanumeric and extra spaces)
            stem = re.sub(r'[^a-zA-Z0-9]', ' ', stem)
            stem = " ".join(stem.split()).lower()
            # Tier 3 Normalization: Common misspelling and numbering alignment
            stem = stem.replace("artifical", "artificial")
            stem = re.sub(r'\s*0+(\d+)', r' \1', stem) # Remove leading zeros in numbers (01 -> 1)
            
            norm_stem = stem.strip()
            t_num_val = t_num.group(1).lstrip('0') or '0' if t_num else None
            
            # Temporary grouping by (disc, normalized_stem)
            temp_key = (disc, norm_stem)
            if temp_key not in temp_groups: temp_groups[temp_key] = []
            temp_groups[temp_key].append({
                "path": f, "meta": meta, "duration": self._get_duration(f), 
                "format": f.suffix.lower().lstrip('.'),
                "filename_track": int(t_num.group(1)) if t_num else None,
                "t_num_val": t_num_val
            })
            
        groups = {}
        for (disc, norm_stem), variants in temp_groups.items():
            # Find distinct non-None t_num_vals in this norm_stem group
            t_nums = {v["t_num_val"] for v in variants if v["t_num_val"] is not None}
            
            if len(t_nums) <= 1:
                # 0 or 1 distinct track numbers -> safe to group them all together!
                # (Same track across different formats, even if one has a number and the other doesn't)
                final_track_id = list(t_nums)[0] if t_nums else norm_stem
                groups[(disc, final_track_id)] = variants
            else:
                # Multiple track numbers for the same title (e.g. "01 Boss" and "02 Boss")
                # We must split them by t_num_val to avoid losing tracks.
                # Files without track numbers in a multi-numbered group are treated as separate unnumbered tracks.
                for v in variants:
                    # Unique fallback ID if t_num_val is None
                    final_track_id = v["t_num_val"] if v["t_num_val"] else f"{norm_stem}_unnum_{variants.index(v)}"
                    key = (disc, final_track_id)
                    if key not in groups: groups[key] = []
                    groups[key].append(v)
                    
        return groups
    def _get_duration(self, path: Path) -> float:
        import subprocess
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            return float(subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
        except: return 0.0

    def _adopt_optimal_files(self, track_groups: Dict) -> Dict:
        adopted = {}
        for key, variants in track_groups.items():
            chosen = next((v for v in variants if v["format"] in ["flac", "wav", "aiff", "alac"]), None)
            if chosen: adopted[key] = {"path": chosen["path"], "tier": "lossless", "filename_track": chosen["filename_track"]}
            else:
                chosen = next((v for v in variants if v["format"] in ["ogg", "aac", "m4a"]), variants[0])
                adopted[key] = {"path": chosen["path"], "tier": "lossy" if chosen["format"] != "mp3" else "mp3", "filename_track": chosen["filename_track"]}
        return adopted

    def _prepare_llm_track_context(self, track_groups: Dict) -> Dict[str, List[Dict[str, Any]]]:
        context = {}
        for (disc, clean_title), variants in track_groups.items():
            merged_tags = {}
            for v in variants:
                if v["meta"]:
                    for k, val in v["meta"].items():
                        if val and str(val).lower() not in ["", "none", "unknown", "0"] and k not in merged_tags: merged_tags[k] = val
            tid = f"{disc}_{clean_title}"
            sources = [{"type": "filename", "content": variants[0]["path"].name, "inferred_track_num": variants[0].get("filename_track"), "duration": round(sum(v["duration"] for v in variants)/len(variants), 2), "weight": "weak"}]
            if merged_tags: sources.append({"type": "embedded_merged", "tags": merged_tags, "duration": sources[0]["duration"], "weight": "strong" if len(variants) > 1 else "moderate"})
            else: sources.append({"type": "no_tags_found", "content": "No metadata found", "weight": "critical_missing"})
            context[tid] = sources
        return context

    def _fetch_album_artwork(self, steam_meta: SteamMetadata, mbz_candidates: List[Dict]) -> Optional[bytes]:
        import requests
        if mbz_candidates:
            url = self.mbz.get_release_artwork_url(mbz_candidates[0]["mbid"])
            if url:
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200: return r.content
                except: pass
        if steam_meta.header_image_url:
            try:
                r = requests.get(steam_meta.header_image_url, timeout=15)
                if r.status_code == 200: return r.content
            except: pass
        return None

    def _get_best_artwork(self, variants: List[Dict]) -> Optional[bytes]:
        from mutagen import File
        for v in variants:
            try:
                audio = File(v["path"])
                if audio and audio.tags:
                    if v["format"] in ["mp3", "aiff"]:
                        for tag in audio.tags.values():
                            if hasattr(tag, 'data') and getattr(tag, 'FrameID', None) == "APIC": return tag.data
                    elif v["format"] == "flac" and audio.pictures: return audio.pictures[0].data
            except: continue
        return None
