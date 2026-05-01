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
            user_language=config.user_language, llm_backend=config.llm_backend
        )
        self.working_dir = Path(config.sst_working_dir)

    def _get_localized_now(self):
        from datetime import timezone, timedelta
        import os
        return datetime.now(timezone(timedelta(hours=9))) if os.environ.get("TZ") == "Asia/Tokyo" else datetime.now(timezone.utc)

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata, on_track_complete: Optional[callable] = None) -> LocalProcessResult:
        logger.info(f"--- Processing {steam_meta.name} ({app_id}) ---")
        
        try:
            all_files = self._list_audio_files(install_dir)
            if not all_files:
                return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)

            track_groups = self._group_by_logical_track(all_files)
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
            
            # 2. LLM Decision
            final_metadata, llm_log = self.llm.consolidate_metadata(steam_meta.model_dump(), track_sources, mbz_candidates)
            
            if final_metadata is None:
                p1_log = llm_log.get("phase1_log", {})
                error_msg = p1_log.get("error") or "Manual Review Required"
                summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": "review", "confidence_score": 0, 
                                "confidence_reason": error_msg, "processed_at": self._get_localized_now().isoformat(), "tracks": [], "steam_info": steam_meta.model_dump()}
                self.db.record_processed(app_id, "review", steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
                return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=0, confidence_reason=error_msg, message=f"LLM Failure: {error_msg}")

            # 3. Execution Setup
            temp_output = self.working_dir / f"final_{app_id}_{datetime.now().strftime('%H%M%S')}"
            temp_output.mkdir(parents=True, exist_ok=True)
            
            tagger = AudioTagger(temp_output)
            album_artwork = self._fetch_album_artwork(steam_meta, mbz_candidates)
            if album_artwork: album_artwork = tagger.process_artwork(album_artwork)

            any_audio_warnings, any_audio_failures = False, False

            def _process_single_track(track_data):
                nonlocal any_audio_warnings, any_audio_failures
                (disc, clean_title), adopted_info = track_data
                try:
                    local_raw_dir = temp_output / "raw_src" / str(disc)
                    local_raw_dir.mkdir(parents=True, exist_ok=True)
                    local_source_path = local_raw_dir / adopted_info["path"].name
                    shutil.copy2(adopted_info["path"], local_source_path)
                    
                    processed_path, has_warnings = tagger.convert_and_limit(local_source_path, adopted_info["tier"], subdir=str(disc))
                    if has_warnings: any_audio_warnings = True
                    if local_source_path.exists(): local_source_path.unlink()
                    
                    instr = final_metadata.get(f"{disc}_{clean_title}") or {"action": "use_local_tag"}
                    tag_map = MetadataBuilder.build_tag_map(app_id, disc, clean_title, adopted_info, steam_meta, instr, mbz_candidates, track_sources, self.config.user_language_639_2)
                    
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
                if not final_metadata:
                    processed_tracks_meta = []
                else:
                    processed_tracks_meta = [t for t in executor.map(_process_single_track, self._adopt_optimal_files(track_groups).items()) if t]

            # 4. Final Validation (STRICT GATES)
            status, message, score, reason = self._validate_results(processed_tracks_meta, final_metadata, any_audio_failures, any_audio_warnings, llm_log)

            # 5. Result Preservation
            summary_meta = {"app_id": app_id, "album_name": steam_meta.name, "status": status, "confidence_score": score, 
                            "confidence_reason": reason, "processed_at": self._get_localized_now().isoformat(), 
                            "tracks": processed_tracks_meta, "steam_info": steam_meta.model_dump()}
            
            self._send_notifications(app_id, steam_meta.name, status, message, score, reason, llm_log, any_audio_failures)
            
            log_bundle = {"llm_log.json": llm_log, "mbz_log.json": mbz_log, "metadata.json": summary_meta,
                          "BASIS_for_CLASSIFICATION.md": self._generate_classification_basis(app_id, steam_meta, status, message, score, reason, len(processed_tracks_meta), llm_log)}
            
            PackageManager.save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle)
            self.db.record_processed(app_id, status, steam_meta.name, self._get_localized_now().isoformat(), summary_meta)
            
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, confidence_score=score, confidence_reason=reason, message=message)

        except Exception as e:
            logger.error(f"Critical failure for {app_id}: {e}", exc_info=True)
            self.notifier.notify_critical(f"Process Failed: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            if 'temp_output' in locals() and temp_output.exists():
                if not (self.config.env_mode == "development" and 'status' in locals() and status == "error"):
                    shutil.rmtree(temp_output)
        
        return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message="Unexpected fallthrough", confidence_score=0)

    def _extract_local_baseline(self, track_groups: Dict) -> Dict[str, Any]:
        from collections import Counter
        albums, artists, years, track_names = [], [], [], []
        for (disc, title), variants in track_groups.items():
            track_names.append(title)
            for v in variants:
                if v["meta"]:
                    if v["meta"].get("album"): albums.append(v["meta"]["album"])
                    if v["meta"].get("artist"): artists.append(v["meta"]["artist"])
                    if v["meta"].get("year"): years.append(str(v["meta"]["year"]))
        def most_common(lst):
            return Counter(lst).most_common(1)[0][0] if lst else None
        return {"album": most_common(albums), "artist": most_common(artists), "year": most_common(years), "tracks": track_names}

    def _validate_results(self, tracks, llm_data, audio_fail, audio_warn, llm_log) -> Tuple[str, str, int, str]:
        p1_res = llm_log.get("phase1_res", {})
        score = int(p1_res.get("confidence_score", 0))
        reason = p1_res.get("confidence_reason", "No LLM response")
        label = p1_res.get("semantic_label", "Review")
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        
        if score < 95 or ratio.get("archive", 0) < 95:
            return "review", f"[{label}] {reason}", score, reason

        status, message = "archive", "Success"
        z_count = sum(1 for t in tracks if str(t["tags"].get("track_number")) == "0")
        u_count = sum(1 for t in tracks if (t["tags"].get("title") or "Unknown") == "Unknown")
        
        dirty_pattern = re.compile(r'^\d+\s*[-.]\s*')
        d_count = 0
        for t in tracks:
            title = t["tags"].get("title")
            if title and dirty_pattern.match(str(title)):
                d_count += 1

        if z_count > 0 or u_count > 0 or d_count > 0:
            status = "review"
            issues = []
            if z_count > 0: issues.append(f"Track#0 x{z_count}")
            if u_count > 0: issues.append(f"Unknown Title x{u_count}")
            if d_count > 0: issues.append(f"Dirty Tags x{d_count}")
            message = f"{label} [{', '.join(issues)}]"

        if audio_fail: 
            status, message = "review", "[CRITICAL: Audio Source Error]"
        elif audio_warn: 
            status, message = "review", "Audio quality warning detected"

        return status, message, score, reason

    def _send_notifications(self, app_id, name, status, message, score, reason, llm_log, any_audio_failures):
        p1_res = llm_log.get("phase1_res", {})
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        ratio_str = f"Archive {ratio.get('archive', 0)}% : Review {ratio.get('review', 0)}%"

        fields = [
            {"name": "AppID", "value": str(app_id), "inline": True},
            {"name": "Status", "value": status.upper(), "inline": True},
            {"name": "Deduction Score", "value": f"{score}%", "inline": True},
            {"name": "Judgment Ratio", "value": ratio_str, "inline": False},
            {"name": "Reasoning", "value": reason[:1024], "inline": False}
        ]
        if any_audio_failures: fields.append({"name": "⚠️ ALERT", "value": "Track-level failures occurred.", "inline": False})
        if status == "review": self.notifier.notify_warning(f"Review Required: {name}", message, fields)
        else: self.notifier.notify_info(f"Archived: {name}", f"Quality Check: {score}%", fields)

    def _generate_classification_basis(self, app_id, steam_meta, status, message, score, reason, count, llm_log):
        p1_res = llm_log.get("phase1_res", {})
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        from textwrap import dedent
        return dedent(f"""\
            # Basis for Classification: {steam_meta.name}
            - **Status**: {status.upper()}
            - **Deduction Score**: {score}/100
            - **Judgment Ratio**: Archive {ratio.get('archive', 0)}% / Review {ratio.get('review', 0)}%
            - **Summary**: {message}
            - **LLM Reasoning**: {reason}
            - **Parent Game**: {steam_meta.parent_name or 'N/A'} ({steam_meta.parent_app_id or 'N/A'})
            - **Tracks Processed**: {count}
        """)

    def _list_audio_files(self, directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff"}
        return [p for p in directory.rglob("*") if p.suffix.lower() in exts and not p.name.startswith(".") and "__MACOSX" not in p.parts]

    def _group_by_logical_track(self, files: List[Path]) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            t_num = re.match(r'^(\d+)', f.stem)
            disc = 1
            if meta.get("disc_number"):
                try: 
                    d_str = str(meta.get("disc_number")).split('/')[0]
                    if d_str.isdigit(): disc = int(d_str)
                except: pass
            key = (disc, re.sub(r'^(\d+[\s.-]+)+', '', f.stem).strip().lower())
            if key not in groups: groups[key] = []
            groups[key].append({"path": f, "meta": meta, "duration": self._get_duration(f), "format": f.suffix.lower().lstrip('.'),
                                "filename_track": int(t_num.group(1)) if t_num else None})
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
