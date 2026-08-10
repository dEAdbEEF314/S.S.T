import logging
import shutil
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .notify import NotificationManager
from .db import DatabaseManager
from .packager import PackageManager
from .alignment_inputs import AlignmentInputBuilder

# New functional modules
from .track_grouper import TrackManager
from .validator import ResultValidator
from .report_generator import ReportGenerator
from .processor_support import adopt_best_file_per_slot, build_slot_variant_index, fetch_album_artwork, send_notifications, resolve_duplicate_mappings, select_best_unassigned_files
from .processor_tracks import process_single_track
from .alignment_flow import collect_alignment_inputs, consolidate_alignment_inputs
from .processor_pipeline import handle_early_review_return

from dataclasses import dataclass

@dataclass
class AlbumExecutionProfile:
    tier_name: str
    track_count_min: int
    track_count_max: int
    num_ctx_cap: int
    phase2_parallel_workers: int
    prefer_one_shot: bool

logger = logging.getLogger("sst.processor")

class LocalProcessor:
    def __init__(self, config: Any, db: DatabaseManager):
        self.config = config
        self.db = db
        self.notifier = NotificationManager(config)
        
        self.mbz = MusicBrainzIdentifier(
            config.mbz_app_name,
            config.mbz_app_version,
            config.mbz_contact,
            scoring_config=config.build_mbz_scoring_config(),
            db=self.db,
        )
        from .ident.acoustid import AcoustIDIdentifier
        self.acoustid = AcoustIDIdentifier(config.acoustid_api_key, db=self.db)
        self.alignment_input_builder = AlignmentInputBuilder(self.acoustid, self.mbz, fingerprint_all=config.fingerprint_all, min_mbz_search_score_threshold=config.min_mbz_search_score_threshold)
        self.llm = LLMOrganizer(**config.build_llm_organizer_kwargs())
        self.working_dir = Path(config.sst_working_dir)

    def set_vram_manager(self, vram_manager: Any):
        self.llm.set_vram_manager(vram_manager)

    def cleanup_force_working_dirs(self, app_ids: List[int]) -> int:
        """Remove only prior intermediate attempts for the requested AppIDs."""
        removed_count = 0
        if not self.working_dir.is_dir():
            return removed_count
        for app_id in sorted(set(app_ids)):
            for pattern in (f"final_{app_id}_*", f"buffer_{app_id}_*"):
                for path in self.working_dir.glob(pattern):
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.is_file() or path.is_symlink():
                        path.unlink()
                    removed_count += 1
        logger.info(
            "Force cleanup removed %d intermediate directories for AppIDs=%s",
            removed_count,
            sorted(set(app_ids)),
        )
        return removed_count

    def _get_localized_now(self):
        from datetime import timezone, timedelta
        import os
        return datetime.now(timezone(timedelta(hours=9))) if os.environ.get("TZ") == "Asia/Tokyo" else datetime.now(timezone.utc)

    @staticmethod
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

    def _build_fast_track_slot_map(self, steam_meta: SteamMetadata) -> Optional[Dict[tuple[int, str], int]]:
        slot_map: Dict[tuple[int, str], int] = {}
        for idx, track in enumerate(steam_meta.store_tracklist or []):
            slot_key = self._normalize_slot_key(track.get("disc", 1), track.get("number"))
            if slot_key is None or slot_key in slot_map:
                return None
            slot_map[slot_key] = idx
        return slot_map

    def _build_fast_track_group_map(self, track_groups: Dict, steam_meta: Optional[SteamMetadata] = None) -> Optional[Dict[str, tuple[tuple[int, str], str]]]:
        group_map: Dict[str, tuple[tuple[int, str], str]] = {}
        slot_durations: Dict[tuple[int, str], List[float]] = {}
        steam_title_map: Dict[str, List[tuple[int, str]]] = {}
        steam_tracks_by_slot: Dict[tuple[int, str], Dict[str, Any]] = {}
        for track in (steam_meta.store_tracklist if steam_meta else []):
            title = TrackManager.normalize_title(str(track.get("title") or track.get("name") or ""))
            slot_key = self._normalize_slot_key(track.get("disc", 1), track.get("number"))
            if slot_key is None:
                # Ignore malformed Steam entries rather than storing an invalid
                # key that cannot be used by the fast-track matcher.
                continue
            if title:
                steam_title_map.setdefault(title, []).append(slot_key)
            steam_tracks_by_slot[slot_key] = track
        for (disc_num, clean_title), variants in track_groups.items():
            track_numbers = {variant.get("t_num_val") for variant in variants if variant.get("t_num_val") not in (None, "", "0")}
            slot_key: Optional[tuple[int, str]] = None
            if len(track_numbers) == 1:
                candidate_slot_key = self._normalize_slot_key(disc_num, next(iter(track_numbers)))
                if candidate_slot_key is not None:
                    steam_track = steam_tracks_by_slot.get(candidate_slot_key)
                    local_title = TrackManager.normalize_title(clean_title)
                    steam_title = TrackManager.normalize_title(str((steam_track or {}).get("title") or (steam_track or {}).get("name") or ""))
                    slot_key = candidate_slot_key
                    if steam_track and steam_title != local_title:
                        slot_key = None
            if slot_key is None and steam_meta:
                title_matches = steam_title_map.get(TrackManager.normalize_title(clean_title), [])
                if len(title_matches) == 1:
                    slot_key = title_matches[0]
            if slot_key is None:
                return None
            slot_durations.setdefault(slot_key, []).extend(
                float(variant.get("duration", 0.0) or 0.0) for variant in variants
            )
            group_map[f"{disc_num}_{clean_title}"] = (slot_key, clean_title)

        if any(max(durations) - min(durations) >= 1.0 for durations in slot_durations.values() if durations):
            return None
        return group_map

    def _check_fast_track(self, app_id: int, steam_meta: SteamMetadata, track_groups: Dict, mbz_candidates: List[Dict], fingerprint_bundle: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[Dict], Optional[Dict]]:
        if not steam_meta.store_tracklist:
            return False, None, None

        slot_map = self._build_fast_track_slot_map(steam_meta)
        if slot_map is None:
            return False, None, None

        group_map = self._build_fast_track_group_map(track_groups, steam_meta)
        if group_map is None:
            return False, None, None

        if len({slot_key for slot_key, _ in group_map.values()}) != len(steam_meta.store_tracklist):
            return False, None, None

        if set(slot_map.keys()) != {slot_key for slot_key, _ in group_map.values()}:
            return False, None, None

        best = mbz_candidates[0] if mbz_candidates else {}

        logger.info(f"[{app_id}] ファストトラックが有効になりました: 確実な証拠が見つかりました。")
        
        # Global Identity Construction
        global_id = {
            "canonical_album_artist": best.get("artist") or ", ".join([part for part in [steam_meta.developer, steam_meta.publisher] if part]),
            "canonical_genre": steam_meta.genres[0] if steam_meta.genres else "Game Music",
            "canonical_year": (steam_meta.release_date[:4] if steam_meta.release_date else None) or best.get("year") or "0000",
            "canonical_label": best.get("label") or steam_meta.label or steam_meta.publisher,
            "chosen_mbz_index": 0 if best else None
        }
        
        final_map = {}

        fingerprint_by_slot = {}
        for signal_track in (fingerprint_bundle or {}).get("tracks", []):
            track_num = signal_track.get("track_num")
            if track_num in (None, "", 0, "0"):
                continue
            signal_key = self._normalize_slot_key(signal_track.get("disc") or 1, track_num)
            if signal_key is not None and signal_key not in fingerprint_by_slot:
                fingerprint_by_slot[signal_key] = signal_track

        for track_id, (slot_key, clean_title) in group_map.items():
            slot_idx = slot_map[slot_key]
            disc_num, track_number = slot_key
            instruction = {
                "action": "use_steam",
                "matched_v_idx": slot_idx,
                "override_track": track_number,
                "override_disc": str(disc_num),
                "reason": "Fast-track: STEAM slot mapping resolved by track number and duration",
            }
            signal_track = fingerprint_by_slot.get(slot_key)
            if signal_track:
                instruction["chosen_mbz_index"] = 0
                instruction["mbz_track_index"] = signal_track.get("mbz_track_index")
                instruction["alignment_evidence"] = ["filename_track_number", "duration", "acoustid", "mbz_release"]
            final_map[track_id] = instruction
            
        return True, final_map, global_id

    @staticmethod
    def _build_mbz_candidates_from_alignment_inputs(v_fingerprint: Optional[Dict[str, Any]], v_mbz_search: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        mbz_candidates = []
        if v_fingerprint:
            mbz_candidates.append({
                "mbid": v_fingerprint["mbid"],
                "album": v_fingerprint["album_name"],
                "artist": v_fingerprint["artist"],
                "year": v_fingerprint["year"],
                "label": v_fingerprint["label"],
                "score": 1000,
                "evidence": v_fingerprint.get("evidence", ["MAJORITY_VOTE_WINNER"]),
                "tracks": v_fingerprint["tracks"],
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
                "tracks": v_mbz_search["tracks"],
            })
        return mbz_candidates

    @staticmethod
    def _build_fast_track_alignment_res(final_metadata: Dict[str, Any], v_local: Dict[str, Any]) -> Dict[str, Any]:
        slots: Dict[str, Dict[str, Any]] = {}
        local_tracks = v_local.get("tracks", []) if isinstance(v_local, dict) else []
        file_ids_by_tid: Dict[str, List[str]] = {}
        for track in local_tracks:
            local_key = track.get("local_key")
            if not local_key:
                continue
            file_ids_by_tid[f"{local_key[0]}_{local_key[1]}"] = [str(file_id) for file_id in track.get("file_ids", [])]

        for tid, instr in final_metadata.items():
            file_ids = file_ids_by_tid.get(tid)
            if not file_ids:
                continue
            slot_key = str(instr.get("override_track") or int(instr.get("matched_v_idx", 0)) + 1)
            slots.setdefault(slot_key, {"files": [], "confidence": 1.0, "reason": instr.get("reason")})
            slots[slot_key]["files"].extend(file_ids)

        assigned = {file_idx for slot in slots.values() for file_idx in slot.get("files", [])}
        all_file_ids = [str(file_id) for track in local_tracks for file_id in track.get("file_ids", [])]
        unassigned = [file_id for file_id in all_file_ids if file_id not in assigned]
        return {
            "slots": slots,
            "unassigned_files": unassigned,
            "unassigned_reason": None if not unassigned else "Fast-track left files unassigned",
        }

    def process_album(
        self,
        app_id: int,
        install_dir: Path,
        steam_meta: SteamMetadata,
        on_track_complete: Optional[Callable[[], None]] = None,
        llm_progress_callback: Optional[Callable[[], None]] = None,
    ) -> LocalProcessResult:
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

        temp_output: Optional[Path] = None
        buffer_dir: Optional[Path] = None
        try:
            _diag("PROCESS_START", install_dir=str(install_dir))
            all_files = TrackManager.list_audio_files(install_dir)
            _diag("FILES_SCANNED", audio_file_count=len(all_files))
            if not all_files:
                _diag("SKIP_NO_AUDIO")
                return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)
            
            track_groups = TrackManager.build_file_records(all_files, album_name=steam_meta.name)
            
            _diag("FILE_RECORDS_BUILT", file_count=len(track_groups))
            max_local_disc = max((d for d, _ in track_groups.keys()), default=1) if track_groups else 1
            max_store_disc = max((int(t.get("disc", 1)) for t in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
            total_discs = max(max_local_disc, max_store_disc)
            
            track_count = max(len(track_groups), len(steam_meta.store_tracklist) if steam_meta.store_tracklist else 0)
            execution_profile = self._build_album_execution_profile(track_count)
            logger.info(f"[{app_id}] 実行プロファイル: {execution_profile.tier_name} (Tracks: {track_count}, num_ctx: {execution_profile.num_ctx_cap}, workers: {execution_profile.phase2_parallel_workers})")

            v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log = collect_alignment_inputs(
                app_id, steam_meta, track_groups, self.alignment_input_builder, _diag, on_track_complete
            )
            mbz_candidates = self._build_mbz_candidates_from_alignment_inputs(v_fingerprint, v_mbz_search)

            fast_track_ok, fast_track_map, fast_track_identity = self._check_fast_track(app_id, steam_meta, track_groups, mbz_candidates, v_fingerprint)
            if fast_track_ok:
                final_metadata = fast_track_map or {}
                fast_track_alignment_res = self._build_fast_track_alignment_res(final_metadata, v_local)
                llm_log = {
                    "fast_track": True,
                    "phase1_res": {
                        "album_confidence": 100,
                        "mapping_confidence": 100,
                        "data_quality": 100,
                        "identity_confidence": 100,
                        "integrity_quality": 100,
                        "archive_vs_review_ratio": {"archive": 100, "review": 0},
                        "confidence_reason": "SYSTEM: Deterministic fast-track",
                        "strategy": "FAST_TRACK",
                        "semantic_label": "Archive",
                        "global_tags": fast_track_identity or {},
                        "concerns": [],
                    },
                    "alignment_res": fast_track_alignment_res,
                }
                _diag("FAST_TRACK_SELECTED", mapped_track_count=len(final_metadata))
            else:
                final_metadata, llm_log = consolidate_alignment_inputs(
                    app_id,
                    self.llm,
                    execution_profile,
                    v_steam,
                    v_local,
                    v_fingerprint,
                    v_mbz_search,
                    _diag,
                    llm_progress_callback=llm_progress_callback,
                )

            # The LLM may return None when alignment cannot be consolidated.
            # Keep downstream helpers on their declared dictionary contract.
            final_metadata = final_metadata or {}
             
            # --- SMART DUPLICATE RESOLUTION (Post-LLM Cleanup) ---
            if final_metadata:
                self._resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)

            # Compatibility layer for existing validator/tagger
            # We still need track_sources for build_tag_map
            track_sources = TrackManager.prepare_llm_track_context(track_groups)
            slot_variant_index, track_to_slot_index = build_slot_variant_index(final_metadata, track_groups, steam_meta)
            
            # Identity and strategy for builder
            p1_res = llm_log.get("phase1_res", {})
            global_identity = p1_res.get("global_tags", {}) if p1_res else {}
            
            # For now, we skip the old MusicBrainz Alignment and VGMdb Integration sections
            
            # --- END OF NEW FLOW ---
            if not final_metadata:
                return handle_early_review_return(
                    app_id, steam_meta, track_count, llm_log, v_steam, v_local, v_fingerprint, v_mbz_search,
                    diagnostics, _diag, self._get_localized_now, self._send_notifications,
                    self.working_dir, self.config.sst_output_dir, self.db, self.config
                )

            run_id = datetime.now().strftime('%H%M%S')
            temp_output = self.working_dir / f"final_{app_id}_{run_id}"
            temp_output.mkdir(parents=True, exist_ok=True)
            buffer_dir = self.working_dir / f"buffer_{app_id}_{run_id}"
            buffer_dir.mkdir(parents=True, exist_ok=True)
            assert temp_output is not None and buffer_dir is not None
            tagger = AudioTagger(temp_output)
            raw_album_artwork = self._fetch_album_artwork(steam_meta, mbz_candidates, track_groups)
            album_artwork_path = tagger.process_artwork(raw_album_artwork) if raw_album_artwork else None
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
                    slot_variant_index=slot_variant_index,
                    track_to_slot_index=track_to_slot_index,
                    album_artwork=album_artwork_path,
                    notifier=self.notifier,
                    on_track_complete=on_track_complete,
                )

            from concurrent.futures import ThreadPoolExecutor
            adopted_files = adopt_best_file_per_slot(track_groups, slot_variant_index, track_to_slot_index)
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                track_results = list(executor.map(_process_single_track, adopted_files.items()))

            processed_tracks_meta = self._normalize_processed_tracks(
                [r["track_meta"] for r in track_results if r.get("track_meta")]
            )
            alignment_unassigned_ids = {
                str(file_id)
                for file_id in (llm_log.get("alignment_res", {}) or {}).get("unassigned_files", [])
            }
            unassigned_manifest = []
            for unassigned in select_best_unassigned_files(
                track_groups,
                final_metadata,
                alignment_unassigned_ids or None,
            ):
                manifest = {
                    "track_id": unassigned["track_id"],
                    "original_filename": unassigned["path"].name,
                    "file_id": unassigned.get("file_id"),
                    "unassigned_file_ids": unassigned.get("unassigned_file_ids", []),
                    "tier_rank": unassigned["tier_rank"],
                    "original_tags": unassigned.get("original_tags", {}),
                    "reason": "No matching Steam slot",
                }
                try:
                    converted_path, conversion_warning = tagger.convert_and_limit(
                        unassigned["path"], unassigned["tier"], subdir="unassigned"
                    )
                    tagger.mark_unassigned(converted_path, manifest["reason"])
                    manifest["file_path"] = f"unassigned/{converted_path.name}"
                    manifest["converted"] = True
                    manifest["conversion_warning"] = bool(conversion_warning)
                except Exception as error:
                    manifest["converted"] = False
                    manifest["conversion_error"] = str(error)
                unassigned_manifest.append(manifest)
            any_audio_warnings = any(r.get("had_warning") for r in track_results)
            any_audio_failures = any(r.get("failed") for r in track_results)

            status, message, score, quality, reason = ResultValidator.validate(app_id, processed_tracks_meta, llm_log, mbz_candidates, steam_meta, any_audio_failures, any_audio_warnings)
            artifact_issues = self._validate_archive_artifacts(
                app_id,
                temp_output,
                processed_tracks_meta,
                steam_meta,
            )
            if status == "archive" and artifact_issues:
                status = "review"
                existing_message = message.strip("[]") if message else ""
                all_issues = [part for part in [existing_message, *artifact_issues] if part]
                message = f"[{', '.join(all_issues)}]"
                reason = f"{reason}; archive artifact preflight failed"
            _diag(
                "VALIDATION_DONE",
                status=status,
                message=message,
                album_confidence=score,
                data_quality=quality,
                mapping_confidence=p1_res.get("mapping_confidence"),
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
                "album_confidence": score,
                "mapping_confidence": p1_res.get("mapping_confidence"),
                "data_quality": quality,
                "integrity_quality": quality,
                "archive_vs_review_ratio": p1_res.get("archive_vs_review_ratio"),
                "strategy": p1_res.get("strategy"),
                "confidence_reason": reason, 
                "processed_at": self._get_localized_now().isoformat(), 
                "tracks": processed_tracks_meta, 
                "unassigned_files": unassigned_manifest,
                "steam_info": steam_meta.model_dump(),
                "diagnostics": diagnostics,
            }
            discord_msg = self._send_notifications(app_id, steam_meta.name, status, message, score, reason, llm_log, any_audio_failures, len(processed_tracks_meta), mbz_candidates)
            
            alignment_inputs_bundle = {
                "STEAM": v_steam if 'v_steam' in locals() else None,
                "ACOUSTID_MBID": v_fingerprint if 'v_fingerprint' in locals() else None,
                "MBZ_SEARCH": v_mbz_search if 'v_mbz_search' in locals() else None,
                "LOCAL_SIGNALS": v_local if 'v_local' in locals() else None
            }

            localized_now_str = self._get_localized_now().strftime('%Y-%m-%d %H:%M:%S')
            log_bundle = {
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "llm_log.json": llm_log,
                "AUDIT_REPORT.html": ReportGenerator.generate_html_report(app_id, steam_meta, status, message, score, reason, processed_tracks_meta, llm_log, mbz_candidates, localized_now_str, self.config.resolved_metadata_source_priority, quality=quality, alignment_inputs=alignment_inputs_bundle)
            }
            if unassigned_manifest:
                log_bundle["review_manifest.json"] = {
                    "app_id": app_id,
                    "album_name": steam_meta.name,
                    "status": status,
                    "unassigned_files": unassigned_manifest,
                }
            if discord_msg:
                log_bundle["DISCORD_MESSAGE.md"] = discord_msg

            p1_log = llm_log.get("phase1_log", {})
            if p1_log.get("human_prompt"):
                log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
            elif p1_log.get("prompt"):
                log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]

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
            
            if isinstance(temp_output, Path) and temp_output.exists() and not is_debug:
                shutil.rmtree(temp_output, ignore_errors=True)
            if isinstance(buffer_dir, Path) and buffer_dir.exists() and not is_debug:
                shutil.rmtree(buffer_dir, ignore_errors=True)

    def _fetch_album_artwork(
        self,
        steam_meta: SteamMetadata,
        mbz_candidates: List[Dict[str, Any]],
        track_groups: Optional[Dict] = None,
    ) -> Optional[bytes]:
        return fetch_album_artwork(self.config, self.mbz, steam_meta, mbz_candidates, track_groups)

    @staticmethod
    def _validate_archive_artifacts(
        app_id: int,
        artifact_dir: Path,
        tracks: List[Dict[str, Any]],
        steam_meta: SteamMetadata,
    ) -> List[str]:
        """Re-scan physical outputs immediately before packaging an archive."""
        issues: List[str] = []
        expected_keys = {
            (
                str(item.get("disc", 1)).split("/")[0],
                str(item.get("number", "0")).split("/")[0],
            )
            for item in (steam_meta.store_tracklist or [])
        }
        actual_keys = set()
        for track in tracks:
            tags = track.get("tags") or {}
            key = (
                str(tags.get("disc_number", "1")).split("/")[0],
                str(tags.get("track_number", "0")).split("/")[0],
            )
            actual_keys.add(key)
            relative_path = track.get("file_path")
            if not relative_path:
                issues.append("Archive Artifact Path Missing")
                continue
            output_path = artifact_dir / str(relative_path)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                issues.append(f"Archive Artifact Missing ({relative_path})")
                continue
            if not all(str(tags.get(field) or "").strip() for field in ("title", "track_number", "artist", "album_artist")):
                issues.append(f"Archive Artifact Tags Missing ({relative_path})")
        if expected_keys != actual_keys:
            issues.append("Archive Artifact Steam Slot Mismatch")
        logger.info(
            "[%s] Archive artifact preflight: files=%s issues=%s",
            app_id,
            len(tracks),
            len(issues),
        )
        return issues

    @staticmethod
    def _normalize_processed_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep one highest-quality physical file per aligned Steam slot before validation."""
        selected: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for track in tracks:
            key = str(track.get("slot_key") or "")
            if not key:
                tags = track.get("tags", {})
                key = f"{tags.get('disc_number', '1')}_{tags.get('track_number', '0')}"
            if key not in selected:
                selected[key] = track
                order.append(key)
                continue
            current = selected[key]
            if int(track.get("tier_rank", 999)) < int(current.get("tier_rank", 999)):
                selected[key] = track
        return [selected[key] for key in order]


    def _send_notifications(self, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates):
        return send_notifications(self.notifier, app_id, name, status, message, score, reason, llm_log, any_audio_failures, track_count, mbz_candidates)

    def _resolve_duplicate_mappings(self, app_id: int, final_metadata: Dict[str, Any], steam_meta: SteamMetadata, track_groups: Dict):
        resolve_duplicate_mappings(app_id, final_metadata, steam_meta, track_groups)

    def _build_album_execution_profile(self, track_count: int) -> AlbumExecutionProfile:
        cfg = self.config
        # Small
        if track_count <= getattr(cfg, 'llm_album_tier_small_max_tracks', 50):
            return AlbumExecutionProfile(
                tier_name="Small",
                track_count_min=1,
                track_count_max=getattr(cfg, 'llm_album_tier_small_max_tracks', 50),
                num_ctx_cap=getattr(cfg, 'llm_ollama_num_ctx_small', 8192),
                phase2_parallel_workers=getattr(cfg, 'llm_request_parallelism_max_workers_small', 3),
                prefer_one_shot=False
            )
        # Medium
        elif track_count <= getattr(cfg, 'llm_album_tier_medium_max_tracks', 100):
            return AlbumExecutionProfile(
                tier_name="Medium",
                track_count_min=getattr(cfg, 'llm_album_tier_small_max_tracks', 50) + 1,
                track_count_max=getattr(cfg, 'llm_album_tier_medium_max_tracks', 100),
                num_ctx_cap=getattr(cfg, 'llm_ollama_num_ctx_medium', 16384),
                phase2_parallel_workers=getattr(cfg, 'llm_request_parallelism_max_workers_medium', 2),
                prefer_one_shot=True
            )
        # Large
        else:
            return AlbumExecutionProfile(
                tier_name="Large",
                track_count_min=getattr(cfg, 'llm_album_tier_medium_max_tracks', 100) + 1,
                track_count_max=99999,
                num_ctx_cap=getattr(cfg, 'llm_ollama_num_ctx_large', 32768),
                phase2_parallel_workers=getattr(cfg, 'llm_request_parallelism_max_workers_large', 1),
                prefer_one_shot=True
            )
