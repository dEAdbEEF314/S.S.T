import os
import re
import logging
import shutil
import tempfile
import sqlite3
import json
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, TrackMetadata, AlbumMetadataSet, ProcessingContext, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .ident.embedded import EmbeddedMetadataExtractor
from .notify import NotificationManager

logger = logging.getLogger("scout.processor")

class LocalProcessor:
    _mbz_lock = threading.Lock() # Class-level lock for MBZ 1req/s limit

    def __init__(self, config: Any):
        self.config = config
        self.notifier = NotificationManager(config)
        self.mbz = MusicBrainzIdentifier(
            config.mbz_app_name, 
            config.mbz_app_version, 
            config.mbz_contact
        )
        logger.info(f"Initializing LLM with model: {config.llm_model}")
        self.llm = LLMOrganizer(
            api_key=config.llm_api_key, 
            base_url=config.llm_base_url, 
            model=config.llm_model,
            rpm=config.llm_limit_rpm,
            tpm=config.llm_limit_tpm,
            rpd=config.llm_limit_rpd,
            user_language=config.user_language,
            force_local=config.llm_force_local
        )
        self.working_dir = Path(config.sst_working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(config.sst_db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_albums (
                    app_id INTEGER PRIMARY KEY,
                    status TEXT,
                    album_name TEXT,
                    processed_at TEXT,
                    metadata_json TEXT
                )
            """)

    def is_already_processed(self, app_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM processed_albums WHERE app_id = ?", (app_id,))
            return cur.fetchone() is not None

    def is_processed(self, app_id: int) -> bool:
        return self.is_already_processed(app_id)

    def _get_localized_now(self):
        from datetime import timezone, timedelta
        tz_env = os.environ.get("TZ", "UTC")
        if tz_env == "Asia/Tokyo":
            return datetime.now(timezone(timedelta(hours=9)))
        return datetime.now(timezone.utc)

    def _fetch_album_artwork(self, steam_meta: SteamMetadata, mbz_candidates: List[Dict]) -> Optional[bytes]:
        """Prioritizes MBZ artwork, falls back to Steam header."""
        if mbz_candidates:
            art_url = self.mbz.get_release_artwork_url(mbz_candidates[0]["mbid"])
            if art_url:
                try:
                    logger.info(f"Downloading album artwork from MusicBrainz: {art_url}")
                    import requests
                    r = requests.get(art_url, timeout=15)
                    if r.status_code == 200: return r.content
                except Exception as e:
                    logger.warning(f"Failed to download MusicBrainz artwork: {e}")
        
        if steam_meta.header_image_url:
            try:
                logger.info(f"Using Steam header image as fallback: {steam_meta.header_image_url}")
                import requests
                r = requests.get(steam_meta.header_image_url, timeout=15)
                if r.status_code == 200: return r.content
            except Exception as e:
                logger.warning(f"Failed to download Steam fallback artwork: {e}")
        return None

    def _build_tag_map(self, app_id: int, disc: int, clean_title: str, adopted_info: Dict, 
                       steam_meta: SteamMetadata, instr: Dict, mbz_candidates: List[Dict], track_sources: Dict) -> Dict[str, Any]:
        """Constructs the ID3v2.3 tag map based on merged sources and definitions."""
        res_title = clean_title
        res_artist = steam_meta.developer or "Unknown Artist"
        res_track = str(adopted_info.get("filename_track") or 0)
        res_disc = f"{disc}/1"
        
        action = instr.get("action", "use_local_tag")
        
        if action == "use_mbz" and mbz_candidates:
            try:
                # SST.md: Top pre-filtered candidate is the primary source
                mbz_album = mbz_candidates[0]
                t_idx = instr.get("mbz_track_index", 0)
                mbz_track = mbz_album["tracks"][t_idx]
                res_title = mbz_track.get("title", res_title)
                res_artist = mbz_track.get("artist", res_artist)
                res_track = str(mbz_track.get("position", res_track))
                res_disc = f"{mbz_album.get('disc_number', disc)}/{mbz_album.get('total_discs', 1)}"
            except: pass
        
        elif action == "use_local_tag":
            local_tags = {}
            tid = f"{disc}_{clean_title}"
            for s in track_sources.get(tid, []):
                if s["type"] == "embedded_merged":
                    local_tags = s.get("tags", {})
                    break
            res_title = local_tags.get("title", res_title)
            res_artist = local_tags.get("artist", res_artist)
            res_track = str(local_tags.get("track_number", res_track))
            res_disc = str(local_tags.get("disc_number", res_disc))

        if instr.get("override_title"): res_title = instr["override_title"]
        if instr.get("override_track"): res_track = str(instr["override_track"])

        raw_genre = instr.get("TCON", steam_meta.genre or steam_meta.parent_genre or 'Soundtrack')
        final_genre = raw_genre if raw_genre.startswith("STEAM VGM") else f"STEAM VGM, {raw_genre}"

        target_comment_appid = steam_meta.parent_app_id or app_id
        target_comment_url = f"https://store.steampowered.com/app/{target_comment_appid}"
        
        return {
            "title": res_title.strip(),
            "artist": res_artist.strip(),
            "album": steam_meta.name, # LOCKED
            "album_artist": f"{steam_meta.developer}; {steam_meta.publisher}",
            "genre": final_genre,
            "grouping": f"{steam_meta.parent_name or steam_meta.name}; Steam",
            "comment": f"{steam_meta.parent_name or steam_meta.name}; {', '.join(steam_meta.tags[:10])}; {target_comment_appid}; {target_comment_url}",
            "composer": instr.get("TCOM", steam_meta.developer or "Unknown"),
            "year": instr.get("TDRC", steam_meta.release_date[:4] if steam_meta.release_date else str(datetime.now().year)),
            "track_number": res_track.split('/')[0].strip(),
            "disc_number": res_disc if "/" in str(res_disc) else f"{res_disc}/1",
            "language": self.config.user_language_639_2
        }

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata, on_track_complete: Optional[callable] = None) -> LocalProcessResult:
        if not install_dir.exists():
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message="Dir not found", confidence_score=0)

        logger.info(f"--- Processing {steam_meta.name} ({app_id}) ---")
        all_files = self._list_audio_files(install_dir)
        if not all_files: return LocalProcessResult(app_id=app_id, status="skip", album_name=steam_meta.name, message="No audio", confidence_score=0)

        track_groups = self._group_by_logical_track(all_files)
        
        with LocalProcessor._mbz_lock:
            mbz_candidates, mbz_log = self.mbz.search_release(
                steam_meta.name, len(track_groups), app_id=app_id, 
                artists=[steam_meta.developer, steam_meta.publisher],
                year=steam_meta.release_date[:4] if steam_meta.release_date else None,
                parent_year=steam_meta.parent_release_date[:4] if steam_meta.parent_release_date else None
            )
            time.sleep(1.0)
        
        track_sources = self._prepare_llm_track_context(track_groups)
        final_metadata, llm_log = self.llm.consolidate_metadata(steam_meta.model_dump(), track_sources, mbz_candidates)
        
        if not final_metadata:
            p1_log = llm_log.get("phase1_log", {})
            error_msg = p1_log.get("error") or "Manual Review Required"
            summary_meta = {
                "app_id": app_id, "album_name": steam_meta.name, "status": "review",
                "confidence_score": 0, "confidence_reason": error_msg,
                "processed_at": self._get_localized_now().isoformat(), "tracks": [],
                "steam_info": steam_meta.model_dump()
            }
            self._record_processed(app_id, "review", steam_meta.name, summary_meta)
            return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, 
                                     confidence_score=0, confidence_reason=error_msg, 
                                     message=f"LLM Failure: {error_msg}", processed_at=self._get_localized_now())

        temp_output = self.working_dir / f"final_{app_id}_{datetime.now().strftime('%H%M%S')}"
        temp_output.mkdir(parents=True, exist_ok=True)
        album_process_status = "unknown"
        
        try:
            tagger = AudioTagger(temp_output)
            album_artwork = self._fetch_album_artwork(steam_meta, mbz_candidates)
            if album_artwork: album_artwork = tagger.process_artwork(album_artwork)

            any_audio_warnings = False
            any_audio_failures = False

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
                    tag_map = self._build_tag_map(app_id, disc, clean_title, adopted_info, steam_meta, instr, mbz_candidates, track_sources)
                    
                    track_art = self._get_best_artwork(track_groups[(disc, clean_title)])
                    tagger.write_tags(processed_path, tag_map, tagger.process_artwork(track_art) if track_art else album_artwork)
                    
                    if on_track_complete: on_track_complete()
                    
                    return {
                        "file_path": f"{disc}/{processed_path.name}", 
                        "original_filename": local_source_path.name,
                        "tags": tag_map, 
                        "source": instr.get("reason", "Fallback")
                    }
                except Exception as e:
                    logger.error(f"Track failure for {clean_title}: {e}")
                    any_audio_failures = True
                    return None

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                processed_tracks_meta = [t for t in executor.map(_process_single_track, self._adopt_optimal_files(track_groups).items()) if t]

            # Final Validation & Results
            status, message, conf_score, conf_reason = self._validate_results(
                processed_tracks_meta, final_metadata, any_audio_failures, any_audio_warnings
            )

            summary_meta = {
                "app_id": app_id, "album_name": steam_meta.name, "status": status,
                "confidence_score": conf_score, "confidence_reason": conf_reason,
                "processed_at": self._get_localized_now().isoformat(), "tracks": processed_tracks_meta,
                "steam_info": steam_meta.model_dump()
            }
            
            self._send_notifications(app_id, steam_meta.name, status, message, conf_score, conf_reason)
            
            # Basis for Classification
            basis_content = self._generate_classification_basis(app_id, steam_meta, status, message, conf_score, conf_reason, len(processed_tracks_meta))
            
            log_bundle = {
                "llm_log.json": llm_log, 
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "BASIS_for_CLASSIFICATION.md": basis_content
            }
            self._save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle)
            self._record_processed(app_id, status, steam_meta.name, summary_meta)
            album_process_status = status
            
            return LocalProcessResult(app_id=app_id, status=status, album_name=steam_meta.name, 
                                     confidence_score=conf_score, confidence_reason=conf_reason, message=message)

        except Exception as e:
            album_process_status = "error"
            logger.error(f"Process failed for {app_id}: {e}")
            self.notifier.notify_critical(f"Process Failed: {app_id}", str(e))
            return LocalProcessResult(app_id=app_id, status="error", album_name=steam_meta.name, message=str(e))
        finally:
            if self.config.env_mode == "development" and album_process_status == "error":
                logger.warning(f"Dev Mode: Preserving {temp_output}")
            else:
                if temp_output.exists(): shutil.rmtree(temp_output)

    def _validate_results(self, tracks, llm_data, audio_fail, audio_warn) -> Tuple[str, str, int, str]:
        """Applies SST.md strict gates."""
        status = "archive"
        message = "Success"
        
        first_tid = next(iter(llm_data)) if llm_data else None
        conf_score = llm_data.get(first_tid, {}).get("confidence_score", 0) if first_tid else 0
        conf_reason = llm_data.get(first_tid, {}).get("confidence_reason", "No data") if first_tid else "N/A"
        
        zero_tracks = sum(1 for t in tracks if t["tags"]["track_number"] == "0")
        unknown_titles = sum(1 for t in tracks if t["tags"]["title"] == "Unknown")
        dirty_pattern = re.compile(r'^\d+\s*[-.]\s*')
        dirty_tags = sum(1 for t in tracks if dirty_pattern.match(t["tags"]["title"]))

        if zero_tracks > 0 or unknown_titles > 0 or dirty_tags > 0:
            status = "review"
            issues = []
            if zero_tracks > 0: issues.append(f"Track#0 x{zero_tracks}")
            if unknown_titles > 0: issues.append(f"Unknown Title x{unknown_titles}")
            if dirty_tags > 0: issues.append(f"Dirty Tags x{dirty_tags}")
            semantic_label = llm_data.get(first_tid, {}).get("semantic_label") if first_tid else None
            message = f"{semantic_label} [{', '.join(issues)}]" if semantic_label else f"Metadata anomalies: [{', '.join(issues)}]"

        if audio_fail:
            status = "review"
            message = "[CRITICAL: Audio Source Error]"
        elif audio_warn:
            status = "review"
            message = "Audio quality warning detected"

        if status == "archive" and conf_score < 95:
            status = "review"
            message = f"Low confidence ({conf_score}%): {conf_reason}"

        return status, message, conf_score, conf_reason

    def _send_notifications(self, app_id, name, status, message, score, reason):
        fields = [{"name": "AppID", "value": str(app_id), "inline": True},
                  {"name": "Status", "value": status.upper(), "inline": True},
                  {"name": "Confidence", "value": f"{score}%", "inline": True},
                  {"name": "Reasoning", "value": reason[:1024], "inline": False}]
        if status == "review":
            self.notifier.notify_warning(f"Review Required: {name}", message, fields)
        else:
            self.notifier.notify_info(f"Archived: {name}", f"Quality Check: {score}%", fields)

    def _generate_classification_basis(self, app_id, steam_meta, status, message, score, reason, count):
        from textwrap import dedent
        return dedent(f"""\
            # Basis for Classification: {steam_meta.name}

            ## Classification Result
            - **Status**: {status.upper()}
            - **Confidence Score**: {score}/100
            - **Primary Reason**: {message}
            - **LLM Reasoning**: {reason}

            ## Investigation Links
            - [Search VGMdb](https://vgmdb.net/search?q={steam_meta.name.replace(" ", "+")})
            - [Search MusicBrainz](https://musicbrainz.org/search?type=release&query={steam_meta.name.replace(" ", "+")})
            - [Steam Store Page]({steam_meta.url})

            ## Album Context
            - **AppID**: {app_id}
            - **Parent Game**: {steam_meta.parent_name or 'N/A'} ({steam_meta.parent_app_id or 'N/A'})
            - **Track Count**: {count}
            - **Language Settings**: {self.config.user_language}
        """)

    def _prepare_llm_track_context(self, track_groups: Dict) -> Dict[str, List[Dict[str, Any]]]:
        context = {}
        for (disc, clean_title), variants in track_groups.items():
            tid = f"{disc}_{clean_title}"
            sources = []
            avg_duration = sum(v["duration"] for v in variants) / len(variants)
            merged_tags = {}
            for v in variants:
                if v["meta"]:
                    for key, val in v["meta"].items():
                        if val and str(val).lower() not in ["", "none", "unknown", "0"]:
                            if key not in merged_tags: merged_tags[key] = val

            sources.append({
                "type": "filename", "content": variants[0]["path"].name,
                "inferred_track_num": variants[0].get("filename_track"),
                "duration": round(avg_duration, 2), "weight": "weak"
            })
            if merged_tags:
                sources.append({"type": "embedded_merged", "tags": merged_tags,
                                "duration": round(avg_duration, 2), "weight": "strong" if len(variants) > 1 else "moderate"})
            else:
                sources.append({"type": "no_tags_found", "content": "No metadata found", "weight": "critical_missing"})
            context[tid] = sources
        return context

    def _get_best_artwork(self, variants: List[Dict]) -> Optional[bytes]:
        from mutagen import File
        for v in variants:
            try:
                audio = File(v["path"])
                if audio is None or not audio.tags: continue
                if v["format"] in ["mp3", "aiff"]:
                    for tag in audio.tags.values():
                        if hasattr(tag, 'data') and getattr(tag, 'FrameID', None) == "APIC": return tag.data
                elif v["format"] == "flac":
                    if audio.pictures: return audio.pictures[0].data
            except: continue
        return None

    def _list_audio_files(self, directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff"}
        files = []
        for p in directory.rglob("*"):
            if p.name.startswith(".") or "__MACOSX" in p.parts: continue
            if p.suffix.lower() in exts: files.append(p)
        return files

    def _safe_int_track(self, val: Any) -> Optional[int]:
        if val is None: return None
        try:
            s = str(val).split('/')[0].strip()
            return int(s) if s.isdigit() else None
        except: return None

    def _group_by_logical_track(self, files: List[Path]) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            fn_track = re.match(r'^(\d+)', f.stem)
            disc_num = self._safe_int_track(meta.get("disc_number", 1)) or 1
            clean_stem = re.sub(r'^(\d+[\s.-]+)+', '', f.stem).strip().lower()
            key = (disc_num, clean_stem)
            if key not in groups: groups[key] = []
            groups[key].append({
                "path": f, "meta": meta, "duration": self._get_duration(f), 
                "format": f.suffix.lower().lstrip('.'),
                "filename_track": int(fn_track.group(1)) if fn_track else None
            })
        return groups

    def _get_duration(self, path: Path) -> float:
        import subprocess
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return float(result.stdout.strip())
        except: return 0.0

    def _adopt_optimal_files(self, track_groups: Dict) -> Dict:
        adopted = {}
        for key, variants in track_groups.items():
            chosen = None
            for v in variants:
                if v["format"] in ["flac", "wav", "aiff", "alac"]:
                    chosen = {"path": v["path"], "tier": "lossless", "filename_track": v["filename_track"]}
                    break
            if not chosen:
                for v in variants:
                    if v["format"] in ["ogg", "aac", "m4a"]:
                        chosen = {"path": v["path"], "tier": "lossy", "filename_track": v["filename_track"]}
                        break
            if not chosen: chosen = {"path": variants[0]["path"], "tier": "mp3", "filename_track": variants[0]["filename_track"]}
            adopted[key] = chosen
        return adopted

    def _record_processed(self, app_id: int, status: str, name: str, summary_meta: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO processed_albums (app_id, status, album_name, processed_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
                        (app_id, status, name, self._get_localized_now().isoformat(), json.dumps(summary_meta, ensure_ascii=False)))

    def _save_local_package(self, app_id: int, status: str, album_name: str, source_dir: Path, logs: Dict[str, Any]):
        try:
            output_base = Path("output") / status
            output_base.mkdir(parents=True, exist_ok=True)
            safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in album_name])
            final_zip_path = output_base / f"{app_id}_{safe_name}.zip"
            temp_zip_base = source_dir.parent / f"bundle_{app_id}"
            for log_name, log_content in logs.items():
                if log_content:
                    log_file = source_dir / log_name
                    if log_name.endswith(".json"):
                        with open(log_file, "w", encoding="utf-8") as f:
                            json.dump(log_content, f, indent=2, ensure_ascii=False)
                    else:
                        log_file.write_text(str(log_content), encoding="utf-8")
            archive_result = shutil.make_archive(str(temp_zip_base), 'zip', source_dir)
            shutil.move(str(archive_result), str(final_zip_path))
            logger.info(f"Local package saved: {final_zip_path}")
        except Exception as e:
            logger.error(f"Failed to save local package for {app_id}: {e}")
