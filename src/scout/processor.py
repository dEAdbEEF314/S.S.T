import logging
import shutil
import time
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .ident.vgmdb import VGMdbClient
from .notify import NotificationManager
from .db import DatabaseManager
from .builder import MetadataBuilder
from .packager import PackageManager
from .virtual_album import VirtualAlbumBuilder

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
            "fingerprint_match": config.score_mbz_fingerprint_match,
            "direct_recording_match": config.score_mbz_direct_recording_match,
            "acoustid_release_match": config.score_mbz_acoustid_release_match,
            "publisher_label_match": config.score_mbz_publisher_label_match
        }
        self.mbz = MusicBrainzIdentifier(config.mbz_app_name, config.mbz_app_version, config.mbz_contact, scoring_config=mbz_scoring)
        from .ident.acoustid import AcoustIDIdentifier
        self.acoustid = AcoustIDIdentifier(config.acoustid_api_key)
        self.vgmdb = VGMdbClient()
        self.virtual_album_builder = VirtualAlbumBuilder(self.acoustid, self.mbz)
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

    def _check_fast_track(self, app_id: int, steam_meta: SteamMetadata, track_groups: Dict, mbz_candidates: List[Dict], vgmdb_data: Optional[Dict] = None) -> Tuple[bool, Optional[Dict], Optional[Dict]]:
        if not mbz_candidates and not vgmdb_data: return False, None, None
        
        best = mbz_candidates[0] if mbz_candidates else {}
        evidence = best.get("evidence", [])
        has_strong_link = any(e in evidence for e in ["DIRECT_STEAM_LINK", "DIRECT_STEAMDB_LINK"]) or any(e.startswith("ACOUSTID_MATCH") for e in evidence)
        
        # If we have VGMdb data, it's a massive trust boost
        if vgmdb_data:
            has_strong_link = True
            logger.info(f"[{app_id}] Fast-track: VGMdb bilingual metadata available.")

        if not has_strong_link: return False, None, None
        
        local_count = len(track_groups)
        mbz_count = best.get("track_count", 0)
        
        # Validation
        if vgmdb_data:
            # VGMdb tracks are 1-based in my fetch_bilingual_metadata return
            if local_count != len(vgmdb_data["tracks"]):
                logger.warning(f"[{app_id}] Fast-track aborted: Track count mismatch (Local: {local_count}, VGMdb: {len(vgmdb_data['tracks'])})")
                return False, None, None
        elif local_count != mbz_count: 
            return False, None, None

        logger.info(f"[{app_id}] Fast-track enabled: Absolute evidence found.")
        
        # Global Identity Construction
        if vgmdb_data:
            global_id = {
                "canonical_album_artist": vgmdb_data.get("artist_ja") or best.get("artist") or steam_meta.developer,
                "canonical_genre": vgmdb_data.get("genre_ja") or steam_meta.genres[0] if steam_meta.genres else "Game Music",
                "canonical_year": vgmdb_data.get("year") or (steam_meta.release_date[:4] if steam_meta.release_date else None) or best.get("year") or "0000",
                "canonical_label": best.get("label") or steam_meta.label or steam_meta.publisher,
                "chosen_mbz_index": 0,
                "vgmdb_album_ja": vgmdb_data.get("album_ja"),
                "vgmdb_album_en": vgmdb_data.get("album_en")
            }
        else:
            global_id = {
                "canonical_album_artist": best.get("artist") or steam_meta.developer,
                "canonical_genre": steam_meta.genres[0] if steam_meta.genres else "Game Music",
                "canonical_year": (steam_meta.release_date[:4] if steam_meta.release_date else None) or best.get("year") or "0000",
                "canonical_label": best.get("label") or steam_meta.label or steam_meta.publisher,
                "chosen_mbz_index": 0
            }
        
        final_map = {}
        
        # Mapping Logic
        if vgmdb_data:
            # If we have VGMdb, we assume the order matches because we queried by DiscID (offsets)
            # This is much safer than text matching.
            for i, (key, variants) in enumerate(track_groups.items()):
                disc_num, clean_title = key
                tid = f"{disc_num}_{clean_title}"
                # CDDB tracks are usually 0-indexed in raw, but my fetcher made it 1-based
                final_map[tid] = {
                    "action": "use_vgmdb", 
                    "vgmdb_track_index": i + 1, 
                    "override_title": vgmdb_data["tracks"].get(i + 1),
                    "reason": "Fast-track: VGMdb DiscID Match"
                }
        else:
            # Original MBZ name-based matching
            mbz_tracks = best.get("tracks", [])
            # Use alphanumeric normalization consistent with TrackManager
            def n_alpha(s): return re.sub(r'[^a-z0-9]', '', str(s).lower())
            norm_mbz = [n_alpha(t.get("title", "")) for t in mbz_tracks]
            
            for key, variants in track_groups.items():
                disc_num, clean_title = key
                tid = f"{disc_num}_{clean_title}"
                norm_local = n_alpha(clean_title)
                
                found_idx = -1
                for idx, n_mbz in enumerate(norm_mbz):
                    if n_mbz == norm_local:
                        found_idx = idx
                        break
                
                if found_idx == -1:
                    logger.warning(f"[{app_id}] Fast-track mapping failed for: {clean_title}")
                    return False, None, None
                
                final_map[tid] = {"action": "use_mbz", "mbz_track_index": found_idx, "reason": "Fast-track: Perfect MBZ name alignment"}
            
        return True, final_map, global_id

    def _auto_select_model(self, track_count: int) -> int:
        if self.config.llm_backend != "OLLAMA": return 8192
        # All tiers now use qwen2.5:7b-sst for stability against reasoning blocks
        target_model = self.config.llm_model_small # This defaults to qwen2.5:7b-sst
        target_ctx = 32768
        
        if self.llm.model != target_model:
            logger.info(f"Routing to stable model: {target_model} (tracks: {track_count})")
            self.llm.model = target_model
        return target_ctx

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata, on_track_complete: Optional[callable] = None) -> LocalProcessResult:
        logger.info(f"[{app_id}] --- Processing {steam_meta.name} ---")
        try:
            all_files = TrackManager.list_audio_files(install_dir)
            if not all_files: return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)
            track_groups = TrackManager.group_by_logical_track(all_files, album_name=steam_meta.name)
            max_local_disc = max((d for d, _ in track_groups.keys()), default=1) if track_groups else 1
            max_store_disc = max((int(t.get("disc", 1)) for t in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
            total_discs = max(max_local_disc, max_store_disc)
            num_ctx = self._auto_select_model(len(track_groups))

            # --- NEW EXPERIMENTAL VIRTUAL ALBUM FLOW ---
            logger.info(f"[{app_id}] Building Virtual Albums for Identity Consolidation...")
            
            # 1. STEAM Virtual Album
            v_steam = self.virtual_album_builder.build_steam_album(steam_meta)
            
            # 2. LOCAL Virtual Album
            v_local = self.virtual_album_builder.build_local_album(track_groups)
            
            # 3. FINGERPRINT Virtual Album (Majority Vote)
            v_fingerprint = self.virtual_album_builder.build_fingerprint_album(
                track_groups, on_track_complete=on_track_complete
            )
            
            # --- LLM Consolidation via Virtual Albums ---
            mbz_log = {"status": "virtual_album_flow"} # Initialize for log bundle
            final_metadata, llm_log = self.llm.consolidate_virtual_albums(
                app_id, v_steam, v_fingerprint, v_local, num_ctx=num_ctx
            )
            
            if final_metadata is None:
                p1_res = llm_log.get("phase1_res", {}) if llm_log else {}
                error_msg = p1_res.get("confidence_reason") or "Manual Review Required (LLM Failure)"
                summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": "review", "confidence_score": 0, "confidence_reason": error_msg, "processed_at": self._get_localized_now().isoformat(), "tracks": [], "steam_info": steam_meta.model_dump()}
                self.db.record_processed(app_id, "review", steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
                return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=0, confidence_reason=error_msg, message=f"LLM Failure: {error_msg}")

            # Compatibility layer for existing validator/tagger
            # We still need track_sources for build_tag_map
            track_sources = TrackManager.prepare_llm_track_context(track_groups)
            
            # Map v_fingerprint to mbz_candidates for compatibility with existing ReportGenerator/Validator
            mbz_candidates = []
            if v_fingerprint:
                mbz_candidates.append({
                    "mbid": v_fingerprint["mbid"],
                    "album": v_fingerprint["album_name"],
                    "artist": v_fingerprint["artist"],
                    "year": v_fingerprint["year"],
                    "label": v_fingerprint["label"],
                    "score": 1000, # Max score for majority vote winner
                    "evidence": ["MAJORITY_VOTE_WINNER"],
                    "tracks": v_fingerprint["tracks"]
                })
            
            # Identity and strategy for builder
            p1_res = llm_log.get("phase1_res", {})
            global_identity = p1_res.get("global_tags", {})
            
            # For now, we skip the old MusicBrainz Alignment and VGMdb Integration sections
            # but we need to ensure the variables are defined.
            vgmdb_data = None 
            
            # --- END OF NEW FLOW ---
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
                    disc_subdir = f"disc_{disc}"
                    local_raw_dir = buffer_dir / disc_subdir
                    local_raw_dir.mkdir(parents=True, exist_ok=True)
                    local_source_path = local_raw_dir / adopted_info["path"].name
                    shutil.copy2(adopted_info["path"], local_source_path)
                    processed_path, has_warnings = tagger.convert_and_limit(local_source_path, adopted_info["tier"], subdir=disc_subdir)
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
                        "TRUSTED_TITLE_SOURCES": self.config.title_cleaning_trusted_sources,
                    }
                    tag_map = MetadataBuilder.build_tag_map(
                        app_id, disc, clean_title, adopted_info, steam_meta, instr, 
                        mbz_candidates, track_sources, self.config.user_language_639_2, 
                        global_identity, priorities=priorities, total_discs=total_discs,
                        vgmdb_data=vgmdb_data
                    )
                    track_art = TrackManager.get_best_artwork(track_groups[(disc, clean_title)])
                    tagger.write_tags(processed_path, tag_map, tagger.process_artwork(track_art) if track_art else album_artwork)
                    if on_track_complete: on_track_complete()
                    return {"file_path": f"{disc_subdir}/{processed_path.name}", "original_filename": local_source_path.name, "tags": tag_map, "source": instr.get("reason", "Fallback")}
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
                "AUDIT_REPORT.html": ReportGenerator.generate_html_report(app_id, steam_meta, status, message, score, reason, processed_tracks_meta, llm_log, mbz_candidates, localized_now_str, self.config.metadata_source_priority)
            }

            p1_log = llm_log.get("phase1_log", {})
            if p1_log.get("human_prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
            elif p1_log.get("prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]

            PackageManager.save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle, self.config.sst_output_dir)
            self.db.record_processed(app_id, status, steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, confidence_score=score, confidence_reason=reason, message=message)
        except Exception as e:
            logger.error(f"[{app_id}] Critical failure: {e}", exc_info=True)
            self.notifier.notify_critical(f"Process Failed: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            is_debug = self.config.log_level.upper() == "DEBUG"
            if is_debug:
                logger.info(f"[{app_id}] DEBUG mode: Preserving temporary directories: {getattr(locals().get('temp_output'), 'name', 'N/A')}, {getattr(locals().get('buffer_dir'), 'name', 'N/A')}")
            
            if 'temp_output' in locals() and temp_output.exists() and not is_debug:
                shutil.rmtree(temp_output, ignore_errors=True)
            if 'buffer_dir' in locals() and buffer_dir.exists() and not is_debug:
                shutil.rmtree(buffer_dir, ignore_errors=True)

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
        
        # Split reasons clearly
        fields.append({"name": "⚙️ System Logic Reason", "value": f"**{message}**", "inline": False})
        
        llm_reason = "Bypassed for Fast-Track" if is_fast else reason
        if len(llm_reason) > 1000: llm_reason = llm_reason[:997] + "..."
        fields.append({"name": "🧠 LLM Judgment Reason", "value": llm_reason, "inline": False})

        if any_audio_failures: 
            fields.append({"name": "🚨 CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})
        
        if status == "review":
            self.notifier.notify_warning(f"Review Required: {name}", f"Manual check needed for AppID {app_id}", fields)
        else:
            self.notifier.notify_info(f"Archived: {name}", f"Automatic archive successful for AppID {app_id}", fields)
