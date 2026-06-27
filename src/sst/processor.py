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
from .notify import NotificationManager
from .db import DatabaseManager
from .packager import PackageManager
from .virtual_album import VirtualAlbumBuilder

# New functional modules
from .track_grouper import TrackManager
from .validator import ResultValidator
from .report_generator import ReportGenerator
from .processor_support import fetch_album_artwork, send_notifications, resolve_duplicate_mappings
from .processor_tracks import process_single_track

logger = logging.getLogger("sst.processor")

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
        self.mbz = MusicBrainzIdentifier(config.mbz_app_name, config.mbz_app_version, config.mbz_contact, scoring_config=mbz_scoring, db=self.db)
        from .ident.acoustid import AcoustIDIdentifier
        self.acoustid = AcoustIDIdentifier(config.acoustid_api_key, db=self.db)
        self.virtual_album_builder = VirtualAlbumBuilder(self.acoustid, self.mbz, fingerprint_all=config.fingerprint_all, min_mbz_search_score_threshold=config.min_mbz_search_score_threshold)
        self.llm = LLMOrganizer(
            api_key=config.llm_api_key, base_url=config.llm_base_url, model=config.llm_model,
            rpm=config.llm_limit_rpm, tpm=config.llm_limit_tpm, rpd=config.llm_limit_rpd,
            user_language=config.user_language, llm_backend=config.llm_backend,
            draft_model=getattr(config, "llm_draft_model", None),
            ollama_num_ctx=getattr(config, "llm_ollama_num_ctx", 32768),
            ollama_num_predict=getattr(config, "llm_ollama_num_predict", 4096),
            chunk_size_virtual=getattr(config, "llm_chunk_size_virtual", 20),
            chunk_size_metadata_ollama=getattr(config, "llm_chunk_size_metadata_ollama", 10),
            chunk_size_metadata_cloud=getattr(config, "llm_chunk_size_metadata_cloud", 30),
            chunk_adaptive=getattr(config, "llm_chunk_adaptive", True),
            chunk_output_tokens_per_track=getattr(config, "llm_chunk_output_tokens_per_track", 180),
            chunk_output_safety_ratio=getattr(config, "llm_chunk_output_safety_ratio", 0.75),
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
        
        best = mbz_candidates[0] if mbz_candidates else {}
        evidence = best.get("evidence", [])
        has_strong_link = any(e in evidence for e in ["DIRECT_STEAM_LINK", "DIRECT_STEAMDB_LINK"]) or any(e.startswith("ACOUSTID_MATCH") for e in evidence)
        
        if not has_strong_link: return False, None, None
        
        local_count = len(track_groups)
        mbz_count = best.get("track_count", 0)
        
        # Validation
        if local_count != mbz_count: 
            return False, None, None

        logger.info(f"[{app_id}] ファストトラックが有効になりました: 確実な証拠が見つかりました。")
        
        # Global Identity Construction
        global_id = {
            "canonical_album_artist": best.get("artist") or steam_meta.developer,
            "canonical_genre": steam_meta.genres[0] if steam_meta.genres else "Game Music",
            "canonical_year": (steam_meta.release_date[:4] if steam_meta.release_date else None) or best.get("year") or "0000",
            "canonical_label": best.get("label") or steam_meta.label or steam_meta.publisher,
            "chosen_mbz_index": 0
        }
        
        final_map = {}
        
        # Mapping Logic
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
                logger.warning(f"[{app_id}] ファストトラックのマッピングに失敗しました: {clean_title}")
                return False, None, None
            
            final_map[tid] = {"action": "use_mbz", "mbz_track_index": found_idx, "reason": "Fast-track: Perfect MBZ name alignment"}
            
        return True, final_map, global_id

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata, on_track_complete: Optional[callable] = None) -> LocalProcessResult:
        logger.info(f"[{app_id}] --- 処理中: {steam_meta.name} ---")
        diagnostics = {
            "trace": [],
            "review_cause_code": None,
            "upstream_cause_code": None,
            "packager_invoked": False,
        }

        def _diag(stage: str, **details: Any):
            diagnostics["trace"].append({
                "stage": stage,
                "details": details,
                "at": self._get_localized_now().isoformat()
            })

        try:
            _diag("PROCESS_START", install_dir=str(install_dir))
            all_files = TrackManager.list_audio_files(install_dir)
            _diag("FILES_SCANNED", audio_file_count=len(all_files))
            if not all_files:
                _diag("SKIP_NO_AUDIO")
                return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)
            track_groups = TrackManager.group_by_logical_track(all_files, album_name=steam_meta.name)
            _diag("TRACK_GROUPS_BUILT", group_count=len(track_groups))
            max_local_disc = max((d for d, _ in track_groups.keys()), default=1) if track_groups else 1
            max_store_disc = max((int(t.get("disc", 1)) for t in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
            total_discs = max(max_local_disc, max_store_disc)
            num_ctx = getattr(self.config, "llm_ollama_num_ctx", 32768) if self.config.llm_backend == "OLLAMA" else None

            # --- NEW EXPERIMENTAL VIRTUAL ALBUM FLOW ---
            logger.info(f"[{app_id}] アイデンティティ統合のために仮想アルバムを構築しています...")
            
            # 1. STEAM Virtual Album
            v_steam = self.virtual_album_builder.build_steam_album(steam_meta)
            
            # 2. LOCAL Virtual Album
            v_local = self.virtual_album_builder.build_local_album(track_groups)
            
            # 3. FINGERPRINT Virtual Album (Majority Vote)
            v_fingerprint = self.virtual_album_builder.build_fingerprint_album(
                track_groups, on_track_complete=on_track_complete
            )
            _diag("VIRTUAL_ALBUM_FINGERPRINT_BUILT", has_fingerprint=bool(v_fingerprint))
            
            # 4. MBZ_SEARCH Virtual Album (Semantic Truth)
            # Create a simple local_baseline for scoring
            local_baseline = {
                "publisher": steam_meta.publisher,
                "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
                "tracks": [(t.get("title", ""), t.get("duration_ms", 0)) for t in v_local["tracks"]]
            }
            v_mbz_search = self.virtual_album_builder.build_mbz_search_album(
                app_id, steam_meta.name, len(steam_meta.store_tracklist), steam_meta, local_baseline
            )
            _diag("VIRTUAL_ALBUM_MBZ_SEARCH_BUILT", has_mbz_search=bool(v_mbz_search))
            
            # Unification logic
            if v_fingerprint and v_mbz_search and v_fingerprint.get("mbid") == v_mbz_search.get("mbid"):
                logger.info(f"[{app_id}] FINGERPRINT and MBZ_SEARCH point to the same MBID. Creating VERIFIED Virtual Album.")
                v_fingerprint["source"] = "VERIFIED_MBZ"
                v_fingerprint["evidence"] = v_mbz_search.get("evidence", []) + ["AUDIO_TEXT_PERFECT_MATCH"]
                v_mbz_search = None # Drop the duplicate
            
            # --- LLM Consolidation via Virtual Albums ---
            mbz_log = {"status": "virtual_album_flow"} # Initialize for log bundle
            final_metadata, llm_log = self.llm.consolidate_virtual_albums(
                app_id, v_steam, v_fingerprint, v_mbz_search, v_local, num_ctx=num_ctx
            )
            _diag(
                "LLM_CONSOLIDATED",
                final_metadata_type=type(final_metadata).__name__,
                phase1_has_result=isinstance(llm_log.get("phase1_res"), dict),
                phase1_has_log=isinstance(llm_log.get("phase1_log"), dict),
            )
            
            # --- SMART DUPLICATE RESOLUTION (Post-LLM Cleanup) ---
            if final_metadata:
                self._resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)

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
                    "evidence": v_fingerprint.get("evidence", ["MAJORITY_VOTE_WINNER"]),
                    "tracks": v_fingerprint["tracks"]
                })
            elif v_mbz_search:
                mbz_candidates.append({
                    "mbid": v_mbz_search["mbid"],
                    "album": v_mbz_search["album_name"],
                    "artist": v_mbz_search["artist"],
                    "year": v_mbz_search["year"],
                    "label": v_mbz_search["label"],
                    "score": v_mbz_search["score"],
                    "evidence": v_mbz_search.get("evidence", ["MBZ_SEARCH_WINNER"]),
                    "tracks": v_mbz_search["tracks"]
                })
            
            # Identity and strategy for builder
            p1_res = llm_log.get("phase1_res", {})
            global_identity = p1_res.get("global_tags", {}) if p1_res else {}
            
            # For now, we skip the old MusicBrainz Alignment and VGMdb Integration sections
            
            # --- END OF NEW FLOW ---
            if not final_metadata:
                p1_log = llm_log.get("phase1_log", {})
                score = p1_res.get("identity_confidence", 0) if isinstance(p1_res, dict) else 0
                error_msg = p1_res.get("confidence_reason") if isinstance(p1_res, dict) else (p1_log.get("error") or "Manual Review Required")
                diagnostics["review_cause_code"] = "EARLY_REVIEW_RETURN"
                diagnostics["upstream_cause_code"] = "LLM_RESPONSE_MISSING" if final_metadata is None else "LOW_CONFIDENCE_GATE"
                _diag(
                    "EARLY_REVIEW_RETURN",
                    review_cause_code=diagnostics["review_cause_code"],
                    upstream_cause_code=diagnostics["upstream_cause_code"],
                    identity_confidence=score,
                    error=error_msg,
                )
                summary_meta = {
                    "app_id": app_id,
                    "album_name": steam_meta.name,
                    "status": "review",
                    "confidence_score": score,
                    "confidence_reason": error_msg,
                    "processed_at": self._get_localized_now().isoformat(),
                    "tracks": [],
                    "steam_info": steam_meta.model_dump(),
                    "diagnostics": diagnostics,
                }
                self.db.record_processed(app_id, "review", steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
                
                if final_metadata is None:
                    return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=0, confidence_reason=error_msg, message=f"LLM Failure: {error_msg}")
                else:
                    return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=score, confidence_reason=error_msg, message=f"Low Confidence: {error_msg}")

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
                return process_single_track(
                    app_id=app_id,
                    steam_meta_name=steam_meta.name,
                    track_data=track_data,
                    final_metadata=final_metadata,
                    config=self.config,
                    steam_meta=steam_meta,
                    mbz_candidates=mbz_candidates,
                    track_sources=track_sources,
                    global_identity=global_identity,
                    total_discs=total_discs,
                    buffer_dir=buffer_dir,
                    tagger=tagger,
                    track_groups=track_groups,
                    album_artwork=album_artwork,
                    notifier=self.notifier,
                    on_track_complete=on_track_complete,
                )

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                track_results = list(executor.map(_process_single_track, TrackManager.adopt_optimal_files(track_groups).items()))

            processed_tracks_meta = [r["track_meta"] for r in track_results if r.get("track_meta")]
            any_audio_warnings = any(r.get("had_warning") for r in track_results)
            any_audio_failures = any(r.get("failed") for r in track_results)

            status, message, score, quality, reason = ResultValidator.validate(app_id, processed_tracks_meta, llm_log, mbz_candidates, steam_meta, any_audio_failures, any_audio_warnings)
            _diag(
                "VALIDATION_DONE",
                status=status,
                message=message,
                confidence_score=score,
                integrity_quality=quality,
                processed_track_count=len(processed_tracks_meta),
            )
            
            # Extract ratio and strategy from llm_log for database persistence
            p1_res = llm_log.get("phase1_res", {})
            
            summary_meta = {
                "app_id": app_id, 
                "album_name": steam_meta.name, 
                "status": status, 
                "message": message,
                "confidence_score": score, 
                "integrity_quality": quality,
                "archive_vs_review_ratio": p1_res.get("archive_vs_review_ratio"),
                "strategy": p1_res.get("strategy"),
                "confidence_reason": reason, 
                "processed_at": self._get_localized_now().isoformat(), 
                "tracks": processed_tracks_meta, 
                "steam_info": steam_meta.model_dump(),
                "diagnostics": diagnostics,
            }
            self._send_notifications(app_id, steam_meta.name, status, message, score, reason, llm_log, any_audio_failures, len(processed_tracks_meta), mbz_candidates)
            
            localized_now_str = self._get_localized_now().strftime('%Y-%m-%d %H:%M:%S')
            log_bundle = {
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "llm_log.json": llm_log,
                "AUDIT_REPORT.html": ReportGenerator.generate_html_report(app_id, steam_meta, status, message, score, reason, processed_tracks_meta, llm_log, mbz_candidates, localized_now_str, self.config.metadata_source_priority, quality=quality)
            }

            p1_log = llm_log.get("phase1_log", {})
            if p1_log.get("human_prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
            elif p1_log.get("prompt"): log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]

            diagnostics["packager_invoked"] = True
            _diag("PACKAGE_SAVE_START", status=status, output_root=self.config.sst_output_dir)
            PackageManager.save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle, self.config.sst_output_dir)
            _diag("PACKAGE_SAVE_DONE", status=status)
            self.db.record_processed(app_id, status, steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, confidence_score=score, confidence_reason=reason, message=message)
        except Exception as e:
            _diag("EXCEPTION_FALLBACK", error=str(e), error_type=type(e).__name__)
            logger.error(f"[{app_id}] 致命的な失敗: {e}", exc_info=True)
            self.notifier.notify_critical(f"処理失敗: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            is_debug = self.config.log_level.upper() == "DEBUG"
            if is_debug:
                logger.info(f"[{app_id}] DEBUG モード: 一時ディレクトリを保持しています: {getattr(locals().get('temp_output'), 'name', 'N/A')}, {getattr(locals().get('buffer_dir'), 'name', 'N/A')}")
            
            if 'temp_output' in locals() and temp_output.exists() and not is_debug:
                shutil.rmtree(temp_output, ignore_errors=True)
            if 'buffer_dir' in locals() and buffer_dir.exists() and not is_debug:
                shutil.rmtree(buffer_dir, ignore_errors=True)

    def _fetch_album_artwork(self, steam_meta: SteamMetadata, mbz_candidates: List[Dict], track_groups: Dict = None) -> Optional[bytes]:
        return fetch_album_artwork(self.config, self.mbz, steam_meta, mbz_candidates, track_groups)


    def _send_notifications(self, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates):
        send_notifications(self.notifier, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates)

    def _resolve_duplicate_mappings(self, app_id: int, final_metadata: Dict[str, Any], steam_meta: SteamMetadata, track_groups: Dict):
        resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)
