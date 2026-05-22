import logging
import shutil
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .notify import NotificationManager
from .db import DatabaseManager
from .builder import MetadataBuilder
from .packager import PackageManager

# New functional modules
from .track_grouper import TrackManager
from .validator import ResultValidator
from .report_generator import ReportGenerator

logger = logging.getLogger("scout.processor")

class LocalProcessor:
    def __init__(self, config: Any, db: DatabaseManager):
        self.config = config
        self.db = db
        self.notifier = NotificationManager(config)
        
        mbz_scoring = {
            "direct_steam_link": config.score_mbz_direct_steam_link,
            "parent_steam_link": config.score_mbz_parent_steam_link,
            "direct_steamdb_link": config.score_mbz_direct_steamdb_link,
            "parent_steamdb_link": config.score_mbz_parent_steamdb_link,
            "bandcamp_link": config.score_mbz_bandcamp_link,
            "title_similarity_max": config.score_mbz_title_similarity_max,
            "track_count_match": config.score_mbz_track_count_match,
            "track_count_penalty_per_track": config.score_mbz_track_count_penalty_per_track,
            "track_count_penalty_max": config.score_mbz_track_count_penalty_max,
            "digital_format": config.score_mbz_digital_format,
            "date_match": config.score_mbz_date_match,
            "date_penalty_per_year": config.score_mbz_date_penalty_per_year,
            "date_penalty_max": config.score_mbz_date_penalty_max,
            "fingerprint_match": config.score_mbz_fingerprint_match
        }
        self.mbz = MusicBrainzIdentifier(config.mbz_app_name, config.mbz_app_version, config.mbz_contact, scoring_config=mbz_scoring)
        self.llm = LLMOrganizer(
            api_key=config.llm_api_key, base_url=config.llm_base_url, model=config.llm_model,
            rpm=config.llm_limit_rpm, tpm=config.llm_limit_tpm, rpd=config.llm_limit_rpd,
            user_language=config.user_language, llm_backend=config.llm_backend,
            draft_model=getattr(config, "llm_draft_model", None),
            metadata_source_priority=config.metadata_source_priority,
            priority_tit2=config.priority_tit2,
            priority_tpe1=config.priority_tpe1,
            priority_trck=config.priority_trck,
            priority_tpos=config.priority_tpos,
            priority_tyer=config.priority_tyer,
            priority_tpub=config.priority_tpub,
            priority_apic=config.priority_apic
        )
        self.working_dir = Path(config.sst_working_dir)

    def _get_localized_now(self):
        from datetime import timezone, timedelta
        import os
        return datetime.now(timezone(timedelta(hours=9))) if os.environ.get("TZ") == "Asia/Tokyo" else datetime.now(timezone.utc)

    def _check_fast_track(self, app_id: int, steam_meta: SteamMetadata, track_groups: Dict, mbz_candidates: List[Dict]) -> Tuple[bool, Optional[Dict], Optional[Dict]]:
        if not mbz_candidates: return False, None, None
        best = mbz_candidates[0]
        evidence = best.get("evidence", [])
        has_direct_link = any(e in evidence for e in ["DIRECT_STEAM_LINK", "DIRECT_STEAMDB_LINK"])
        if not has_direct_link: return False, None, None
        local_count = len(track_groups)
        mbz_count = best.get("track_count", 0)
        pics_count = len(steam_meta.store_tracklist)
        if local_count != mbz_count: return False, None, None
        if pics_count > 0 and local_count != pics_count: return False, None, None
        logger.info(f"[{app_id}] Fast-track enabled: Absolute evidence found.")
        global_id = {
            "canonical_album_artist": best.get("artist") or steam_meta.developer,
            "canonical_genre": steam_meta.genres[0] if steam_meta.genres else "Game Music",
            "canonical_year": best.get("year") or (steam_meta.release_date[:4] if steam_meta.release_date else "0000"),
            "canonical_label": best.get("label") or steam_meta.publisher,
            "chosen_mbz_index": 0
        }
        final_map = {}
        sorted_keys = sorted(track_groups.keys())
        for i, key in enumerate(sorted_keys):
            tid = f"{key[0]}_{key[1]}"
            final_map[tid] = {"action": "use_mbz", "mbz_track_index": i, "reason": "Fast-track: Perfect source alignment"}
        return True, final_map, global_id

    def _auto_select_model(self, track_count: int) -> int:
        if self.config.llm_backend != "OLLAMA": return 8192
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
            all_files = TrackManager.list_audio_files(install_dir)
            if not all_files: return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)
            track_groups = TrackManager.group_by_logical_track(all_files)
            max_local_disc = max((d for d, _ in track_groups.keys()), default=1) if track_groups else 1
            max_store_disc = max((int(t.get("disc", 1)) for t in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
            total_discs = max(max_local_disc, max_store_disc)
            num_ctx = self._auto_select_model(len(track_groups))
            local_baseline = TrackManager.extract_local_baseline(track_groups)
            mbz_candidates, mbz_log = self.mbz.search_release(steam_meta.name, len(track_groups), app_id=app_id, parent_app_id=steam_meta.parent_app_id, year=steam_meta.release_date[:4] if steam_meta.release_date else None, local_baseline=local_baseline)
            time.sleep(1.0)
            track_sources = TrackManager.prepare_llm_track_context(track_groups)
            is_fast, final_metadata, global_identity = self._check_fast_track(app_id, steam_meta, track_groups, mbz_candidates)
            if is_fast:
                llm_log = {"phase1_res": {"identity_confidence": 100, "integrity_quality": 100, "archive_vs_review_ratio": {"archive": 100, "review": 0}, "global_tags": global_identity, "confidence_reason": "Deterministic Fast-track enabled: Album identity and tracklist were perfectly verified against official sources. LLM analysis was skipped to ensure absolute integrity."}, "phase1_log": {"reason": "Fast-track Skip"}, "fast_track": True}
            else:
                final_metadata, llm_log = self.llm.consolidate_metadata(app_id, steam_meta.model_dump(), track_sources, mbz_candidates, num_ctx=num_ctx)
                p1_res = llm_log.get("phase1_res", {})
                global_identity = p1_res.get("global_tags", {})
            if final_metadata is None:
                p1_log = llm_log.get("phase1_log", {})
                error_msg = p1_log.get("error") or "Manual Review Required"
                summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": "review", "confidence_score": 0, "confidence_reason": error_msg, "processed_at": self._get_localized_now().isoformat(), "tracks": [], "steam_info": steam_meta.model_dump()}
                self.db.record_processed(app_id, "review", steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
                return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=0, confidence_reason=error_msg, message=f"LLM Failure: {error_msg}")

            run_id = datetime.now().strftime('%H%M%S')
            temp_output = self.working_dir / f"final_{app_id}_{run_id}"
            temp_output.mkdir(parents=True, exist_ok=True)
            buffer_dir = self.working_dir / f"buffer_{app_id}_{run_id}"
            buffer_dir.mkdir(parents=True, exist_ok=True)
            tagger = AudioTagger(temp_output)
            album_artwork = self._fetch_album_artwork(steam_meta, mbz_candidates, track_groups)
            if album_artwork: album_artwork = tagger.process_artwork(album_artwork)
            any_audio_warnings, any_audio_failures = False, False

            def _process_single_track(track_data):
                nonlocal any_audio_warnings, any_audio_failures
                (disc, clean_title), adopted_info = track_data
                try:
                    local_raw_dir = buffer_dir / str(disc)
                    local_raw_dir.mkdir(parents=True, exist_ok=True)
                    local_source_path = local_raw_dir / adopted_info["path"].name
                    shutil.copy2(adopted_info["path"], local_source_path)
                    processed_path, has_warnings = tagger.convert_and_limit(local_source_path, adopted_info["tier"], subdir=str(disc))
                    if has_warnings: any_audio_warnings = True
                    if local_source_path.exists(): local_source_path.unlink()
                    instr = final_metadata.get(f"{disc}_{clean_title}") or {"action": "use_local_tag"}
                    priorities = {
                        "TIT2": self.config.priority_tit2,
                        "TPE1": self.config.priority_tpe1,
                        "TRCK": self.config.priority_trck,
                        "TPOS": self.config.priority_tpos,
                        "TYER": self.config.priority_tyer,
                        "TPUB": self.config.priority_tpub,
                    }
                    tag_map = MetadataBuilder.build_tag_map(
                        app_id, disc, clean_title, adopted_info, steam_meta, instr, 
                        mbz_candidates, track_sources, self.config.user_language_639_2, 
                        global_identity, priorities=priorities, total_discs=total_discs
                    )
                    track_art = TrackManager.get_best_artwork(track_groups[(disc, clean_title)])
                    tagger.write_tags(processed_path, tag_map, tagger.process_artwork(track_art) if track_art else album_artwork)
                    if on_track_complete: on_track_complete()
                    return {"file_path": f"{disc}/{processed_path.name}", "original_filename": local_source_path.name, "tags": tag_map, "source": instr.get("reason", "Fallback")}
                except Exception as e:
                    logger.error(f"[{app_id}] Track failure for {clean_title}: {e}")
                    self.notifier.notify_critical(f"Track Error: {steam_meta.name}", str(e))
                    any_audio_failures = True
                    return None

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                processed_tracks_meta = [t for t in executor.map(_process_single_track, TrackManager.adopt_optimal_files(track_groups).items()) if t]

            status, message, score, reason = ResultValidator.validate(app_id, processed_tracks_meta, llm_log, mbz_candidates, any_audio_failures, any_audio_warnings)
            summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": status, "confidence_score": score, "confidence_reason": reason, "processed_at": self._get_localized_now().isoformat(), "tracks": processed_tracks_meta, "steam_info": steam_meta.model_dump()}
            self._send_notifications(app_id, steam_meta.name, status, message, score, reason, llm_log, any_audio_failures, len(processed_tracks_meta), mbz_candidates)
            
            localized_now_str = self._get_localized_now().strftime('%Y-%m-%d %H:%M:%S')
            log_bundle = {
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "llm_log.json": llm_log,
                "AUDIT_REPORT.html": ReportGenerator.generate_html_report(app_id, steam_meta, status, message, score, reason, len(processed_tracks_meta), llm_log, mbz_candidates, localized_now_str, self.config.metadata_source_priority),
                "BASIS_for_CLASSIFICATION.md": ReportGenerator.generate_classification_basis(app_id, steam_meta, status, message, score, reason, len(processed_tracks_meta), llm_log, mbz_candidates, localized_now_str)
            }

            p1_log = llm_log.get("phase1_log", {})
            def md_escape(text): return str(text or "-").replace("|", "\\|").replace("\n", "<br>")
            def md_blockquote(text): return "\n".join([f"> {line}" for line in str(text or "-").strip().split("\n")])

            if p1_log.get("human_prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
            elif p1_log.get("prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]
            
            if "phase1_res" in llm_log:
                res_data = llm_log["phase1_res"]
                resp_md = f"# LLM Phase 1 Response: {steam_meta.name}\n\n| Metric | Value |\n|---|---|\n| Identity Confidence | {res_data.get('identity_confidence')} |\n| Integrity Quality | {res_data.get('integrity_quality')} |\n| Strategy | `{res_data.get('strategy')}` |\n| Semantic Label | {md_escape(res_data.get('semantic_label'))} |\n\n## Judgment Reasoning\n{md_blockquote(res_data.get('confidence_reason'))}\n\n## Global Tags Applied\n"
                for k, v in res_data.get('global_tags', {}).items(): resp_md += f"- **{k}**: {md_escape(v)}\n"
                if "phase2_logs" in llm_log and llm_log["phase2_logs"]:
                    resp_md += "\n## Track Mapping Instructions (Phase 2)\n\n| Track ID | Action | MBZ Index | Override Title | Reason |\n|---|---|---|---|---|\n"
                    for c_log in llm_log["phase2_logs"]:
                        try:
                            parsed = json.loads(c_log.get("response", "{}"))
                            instrs = parsed.get("track_instructions", {})
                            for tid, t_data in instrs.items():
                                action = t_data.get('action', 'N/A')
                                if action in ["OVERRIDE", "MAP"]: action = f"**{action}**"
                                resp_md += f"| {md_escape(tid)} | {action} | {md_escape(t_data.get('mbz_track_index', '-'))} | {md_escape(t_data.get('override_title', '-'))} | {md_escape(t_data.get('reason', '-'))} |\n"
                        except: pass
                log_bundle["LLM_RESPONSE.md"] = resp_md
            
            meta_md = f"# Final Metadata Summary: {steam_meta.name}\n\n- **AppID**: [{app_id}](https://store.steampowered.com/app/{app_id})\n- **Status**: `{status.upper()}`\n- **Processed At**: {summary_meta.get('processed_at')}\n\n## Track Tags (ID3v2.3 Mapping)\n| # | Title | Artist | Album Artist | Genre | Year | Comment |\n|---|---|---|---|---|---|---|\n"
            for t in summary_meta.get('tracks', []):
                tg = t.get('tags', {})
                meta_md += f"| {md_escape(tg.get('disc_number','1'))}-{md_escape(tg.get('track_number',''))} | {md_escape(tg.get('title',''))} | {md_escape(tg.get('artist',''))} | {md_escape(tg.get('album_artist',''))} | {md_escape(tg.get('genre',''))} | {md_escape(tg.get('year',''))} | {md_escape(tg.get('comment',''))} |\n"
            log_bundle["METADATA.md"] = meta_md
            
            if mbz_log:
                mbz_md = f"# MusicBrainz Identification Log: {steam_meta.name}\n\n- **Target Search Name**: {md_escape(mbz_log.get('target_name', steam_meta.name))}\n- **Candidates Found**: {len(mbz_log.get('ranked_candidates', []))}\n\n"
                for c in mbz_log.get('ranked_candidates', []):
                    mbz_md += f"## {md_escape(c.get('album'))} (Score: {c.get('score')})\n- **MBID**: [{c.get('mbid')}](https://musicbrainz.org/release/{c.get('mbid')})\n- **Evidence**: {', '.join([md_escape(e) for e in c.get('evidence', [])])}\n\n"
                log_bundle["MBZ_LOG.md"] = mbz_md

            PackageManager.save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle, self.config.sst_output_dir)
            self.db.record_processed(app_id, status, steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, confidence_score=score, confidence_reason=reason, message=message)
        except Exception as e:
            logger.error(f"[{app_id}] Critical failure: {e}", exc_info=True)
            self.notifier.notify_critical(f"Process Failed: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            if 'temp_output' in locals() and temp_output.exists():
                is_debug = self.config.log_level.upper() == "DEBUG"
                if not (is_debug and 'status' in locals() and status == "error"): shutil.rmtree(temp_output, ignore_errors=True)
            if 'buffer_dir' in locals() and buffer_dir.exists(): shutil.rmtree(buffer_dir, ignore_errors=True)

    def _fetch_album_artwork(self, steam_meta: SteamMetadata, mbz_candidates: List[Dict], track_groups: Dict = None) -> Optional[bytes]:
        import requests
        
        apic_priority = self.config.priority_apic.split(",")
        
        for src in apic_priority:
            src = src.strip().upper()
            
            if src == "EMBED" and track_groups:
                # 1. Try to find embedded artwork from local files
                for (disc, clean_title), files in track_groups.items():
                    art = TrackManager.get_best_artwork(files)
                    if art:
                        logger.info(f"Adopted album artwork from EMBED source (track: {clean_title})")
                        return art
                        
            elif src == "MBZ" and mbz_candidates:
                # 2. Try MusicBrainz
                url = self.mbz.get_release_artwork_url(mbz_candidates[0]["mbid"])
                if url:
                    try:
                        r = requests.get(url, timeout=15)
                        if r.status_code == 200:
                            logger.info("Adopted album artwork from MBZ source")
                            return r.content
                    except Exception as e:
                        logger.debug(f"Failed to fetch MBZ artwork: {e}")
                        
            elif src in ["PICS_API", "WEB_API"]:
                # 3. Try Steam APIs (header image)
                url = steam_meta.header_image_url
                if not url and steam_meta.app_id:
                    url = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_meta.app_id}/header.jpg"
                if url:
                    try:
                        r = requests.get(url, timeout=15)
                        if r.status_code == 200:
                            logger.info(f"Adopted album artwork from {src} source")
                            return r.content
                    except Exception as e:
                        logger.debug(f"Failed to fetch Steam artwork ({src}): {e}")
                        
        return None


    def _send_notifications(self, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates):
        p1_res = llm_log.get("phase1_res", {})
        id_conf, quality = p1_res.get("identity_confidence", 0), p1_res.get("integrity_quality", 0)
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        fields = [
            {"name": "AppID", "value": f"[{app_id}](https://store.steampowered.com/app/{app_id})", "inline": True},
            {"name": "Status", "value": f"**{status.upper()}**", "inline": True},
            {"name": "Tracks", "value": str(track_count), "inline": True},
            {"name": "Confidence / Quality", "value": f"ID: {id_conf}% / Qual: {quality}%", "inline": True},
            {"name": "Decision Ratio", "value": f"Arch {ratio.get('archive', 0)}% : Rev {ratio.get('review', 0)}%", "inline": True},
        ]
        if mbz_candidates:
            top_mbz = mbz_candidates[0]
            fields.append({"name": "MusicBrainz (Top)", "value": f"[{top_mbz.get('album')}](https://musicbrainz.org/release/{top_mbz.get('mbid')}) (Score: {top_mbz.get('score')})", "inline": False})
        fields.append({"name": "Reason / Summary", "value": f"_{message}_\n\n{reason[:800]}", "inline": False})
        if any_audio_failures: fields.append({"name": "⚠️ CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})
        if status == "review": self.notifier.notify_warning(f"Review Required: {name}", f"Manual check needed for AppID {app_id}", fields)
        else: self.notifier.notify_info(f"Archived: {name}", f"Quality Check Passed for AppID {app_id}", fields)
