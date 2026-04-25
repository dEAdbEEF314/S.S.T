import os
import re
import logging
import shutil
import tempfile
import sqlite3
import json
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, TrackMetadata, AlbumMetadataSet, ProcessingContext, LocalProcessResult
from .tagger import AudioTagger
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .ident.embedded import EmbeddedMetadataExtractor

logger = logging.getLogger("scout.processor")

class LocalProcessor:
    _mbz_lock = threading.Lock() # Class-level lock for MBZ 1req/s limit

    def __init__(self, config: Any):
        self.config = config
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
            user_language=config.user_language
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

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata) -> LocalProcessResult:
        if not install_dir.exists():
            return LocalProcessResult(app_id=app_id, status="error", message="Dir not found")

        logger.info(f"--- Processing {steam_meta.name} ({app_id}) ---")
        
        all_files = self._list_audio_files(install_dir)
        if not all_files: return LocalProcessResult(app_id=app_id, status="skip", message="No audio")

        track_groups = self._group_by_logical_track(all_files)
        
        # 1. Collect Sources (Deterministic MBZ Candidates) - Locked for 1req/s
        with LocalProcessor._mbz_lock:
            mbz_candidates, mbz_log = self.mbz.search_release(
                steam_meta.name, 
                len(track_groups), 
                app_id=app_id, 
                artists=[steam_meta.developer, steam_meta.publisher],
                year=steam_meta.release_date[:4] if steam_meta.release_date else None,
                parent_year=steam_meta.parent_release_date[:4] if steam_meta.parent_release_date else None
            )
            import time
            time.sleep(1.0) # Strict enforcement
        
        # 2. Prepare weighted context for LLM
        track_sources = self._prepare_llm_track_context(track_groups)
        
        # 3. LLM Consolidation (Batched Pass for large albums)
        all_tracks_sources = list(track_sources.items())
        chunk_size = 20
        final_metadata = {}
        llm_logs = []
        
        # Determine global context first with the first chunk
        logger.info(f"Consolidating metadata in chunks (Total tracks: {len(all_tracks_sources)})")
        
        for i in range(0, len(all_tracks_sources), chunk_size):
            chunk = dict(all_tracks_sources[i:i + chunk_size])
            logger.info(f"Processing LLM chunk {i//chunk_size + 1} ({len(chunk)} tracks)...")
            
            # For subsequent chunks, we could pass the global_tags from the first chunk to maintain consistency
            # but for now, the differential mapping handles this well enough by being deterministic
            chunk_metadata, chunk_log = self.llm.consolidate_metadata(steam_meta.model_dump(), chunk, mbz_candidates)
            llm_logs.append(chunk_log)
            
            if chunk_metadata:
                final_metadata.update(chunk_metadata)
            else:
                logger.warning(f"LLM chunk {i//chunk_size + 1} failed.")

        llm_log = {"chunks": llm_logs}
        
        status = "archive"
        message = "Success"

        if not final_metadata:
            status = "review"
            message = "LLM failed to return valid data for any chunk"
            final_metadata = {}

        # 4. Conversion, Tagging and Local Packaging
        temp_output = self.working_dir / f"final_{app_id}_{datetime.now().strftime('%H%M%S')}"
        temp_output.mkdir(parents=True, exist_ok=True)
        processed_tracks_meta = [] 
        adopted_files = self._adopt_optimal_files(track_groups)
        
        try:
            tagger = AudioTagger(temp_output)
            
            # --- Act-11 Optimization: Fetch Album-Level Artwork ONCE ---
            album_artwork = None
            if mbz_candidates:
                # Try the top candidate
                art_url = self.mbz.get_release_artwork_url(mbz_candidates[0]["mbid"])
                if art_url:
                    try:
                        logger.info(f"Downloading album artwork from MusicBrainz: {art_url}")
                        import requests
                        r = requests.get(art_url, timeout=15)
                        if r.status_code == 200: album_artwork = r.content
                    except Exception as e:
                        logger.warning(f"Failed to download MusicBrainz artwork: {e}")
            
            if not album_artwork and steam_meta.header_image_url:
                try:
                    logger.info(f"Using Steam header image as fallback: {steam_meta.header_image_url}")
                    import requests
                    r = requests.get(steam_meta.header_image_url, timeout=15)
                    if r.status_code == 200: album_artwork = r.content
                except Exception as e:
                    logger.warning(f"Failed to download Steam fallback artwork: {e}")

            # Process common artwork once
            if album_artwork:
                album_artwork = tagger.process_artwork(album_artwork)
            # -----------------------------------------------------------

            # Extract common confidence for summary
            first_tid = next(iter(final_metadata)) if final_metadata else None
            conf_score = final_metadata.get(first_tid, {}).get("confidence_score", 0) if first_tid else 0
            conf_reason = final_metadata.get(first_tid, {}).get("confidence_reason", "No data") if first_tid else "N/A"
            
            if conf_score < 80:
                status = "review"
                message = f"Low confidence ({conf_score}): {conf_reason}"

            # --- Act-11 Parallel Track Processing ---
            from concurrent.futures import ThreadPoolExecutor

            def _process_single_track(track_data):
                track_key, adopted_info = track_data
                disc, clean_title = track_key
                source_path = adopted_info["path"]
                tier = adopted_info["tier"]
                
                # Conversion (FFmpeg or Copy)
                processed_path = tagger.convert_and_limit(source_path, tier, subdir=str(disc))
                
                track_id_str = f"{disc}_{clean_title}"
                instr = final_metadata.get(track_id_str) or {"action": "use_local_tag"} # Default fallback
                
                # --- Tag Resolution Logic (Differential Mapping) ---
                res_title = clean_title
                res_artist = steam_meta.developer or "Unknown Artist"
                res_track = str(adopted_info.get("filename_track") or 0)
                res_disc = f"{disc}/1"
                
                action = instr.get("action", "use_local_tag")
                
                if action == "use_mbz" and mbz_candidates:
                    try:
                        c_idx = instr.get("mbz_index", 0)
                        t_idx = instr.get("mbz_track_index", 0)
                        mbz_album = mbz_candidates[c_idx]
                        mbz_track = mbz_album["tracks"][t_idx]
                        res_title = mbz_track.get("title", res_title)
                        res_artist = mbz_track.get("artist", res_artist)
                        res_track = str(mbz_track.get("position", res_track))
                        res_disc = f"{mbz_album.get('disc_number', disc)}/{mbz_album.get('total_discs', 1)}"
                    except:
                        pass # Fallback to local if MBZ mapping fails
                
                elif action == "use_local_tag":
                    # Find the validated tags if available
                    local_tags = {}
                    for s in track_sources.get(track_id_str, []):
                        if s["type"] == "embedded_validated" or s["type"].startswith("embedded_variant"):
                            local_tags = s.get("tags", {})
                            break
                    res_title = local_tags.get("title", res_title)
                    res_artist = local_tags.get("artist", res_artist)
                    res_track = str(local_tags.get("track_number", res_track))
                    res_disc = str(local_tags.get("disc_number", res_disc))

                # Overrides
                if instr.get("override_title"): res_title = instr["override_title"]
                if instr.get("override_track"): res_track = str(instr["override_track"])

                # Genre Prefix Guard
                raw_genre = instr.get("TCON", steam_meta.genre or steam_meta.parent_genre or 'Soundtrack')
                final_genre = raw_genre if raw_genre.startswith("STEAM VGM") else f"STEAM VGM, {raw_genre}"

                # --- Act-11: Comment tag construction using Parent Game info ---
                target_comment_appid = steam_meta.parent_app_id or app_id
                target_comment_url = f"https://store.steampowered.com/app/{target_comment_appid}"
                
                tag_map = {
                    "title": res_title.strip(),
                    "artist": res_artist.strip(),
                    "album": instr.get("TALB", steam_meta.name),
                    "album_artist": f"{steam_meta.developer} | {steam_meta.publisher}" if steam_meta.developer and steam_meta.publisher else instr.get("TPE2", "Unknown Artist"),
                    "genre": final_genre,
                    "grouping": f"{steam_meta.parent_name or steam_meta.name} | Steam",
                    "comment": f"{steam_meta.parent_name or steam_meta.name} | {', '.join(steam_meta.tags[:10])} | {target_comment_appid} | {target_comment_url}",
                    "composer": instr.get("TCOM", steam_meta.developer or "Unknown"),
                    "year": instr.get("TDRC", steam_meta.release_date[:4] if steam_meta.release_date else str(datetime.now().year)),
                    "track_number": res_track.split('/')[0].strip(),
                    "disc_number": res_disc if "/" in str(res_disc) else f"{res_disc}/1",
                    "language": self.config.user_language_639_2
                }
                
                # Artwork
                track_artwork = self._get_best_artwork(track_groups[track_key])
                final_art = tagger.process_artwork(track_artwork) if track_artwork else album_artwork

                # Write Tags
                tagger.write_tags(processed_path, tag_map, final_art)
                
                return {
                    "file_path": f"{disc}/{processed_path.name}",
                    "original_filename": source_path.name,
                    "tags": tag_map,
                    "source": instr.get("reason", "System Fallback")
                }

            # Run track processing in parallel to avoid IO/CPU bottleneck
            with ThreadPoolExecutor(max_workers=self.config.max_encoding_tasks) as executor:
                processed_tracks_meta = list(executor.map(_process_single_track, adopted_files.items()))
            # ----------------------------------------

            # Validation Loop
            for t in processed_tracks_meta:
                if t["tags"]["title"] == "Unknown" or t["tags"]["track_number"] == "0":
                    status = "review"
                    message = "Missing mandatory metadata (Title/Track)"
                    break

            summary_meta = {
                "app_id": app_id, "album_name": steam_meta.name, "status": status,
                "confidence_score": conf_score, "confidence_reason": conf_reason,
                "processed_at": self._get_localized_now().isoformat(), "tracks": processed_tracks_meta,
                "steam_info": steam_meta.model_dump()
            }
            
            # --- Act-11 Basis for Classification Generation ---
            from textwrap import dedent
            safe_album = steam_meta.name.replace(" ", "+")
            basis_content = dedent(f"""\
                # Basis for Classification: {steam_meta.name}

                ## Classification Result
                - **Status**: {status.upper()}
                - **Confidence Score**: {conf_score}/100
                - **Primary Reason**: {message}
                - **LLM Reasoning**: {conf_reason}

                ## Investigation Links
                - [Search VGMdb](https://vgmdb.net/search?q={safe_album})
                - [Search MusicBrainz](https://musicbrainz.org/search?type=release&query={safe_album})
                - [Steam Store Page]({steam_meta.url})

                ## Album Context
                - **AppID**: {app_id}
                - **Parent Game**: {steam_meta.parent_name or 'N/A'} ({steam_meta.parent_app_id or 'N/A'})
                - **Track Count**: {len(processed_tracks_meta)}
                - **Language Settings**: {self.config.user_language}
            """)

            log_bundle = {
                "llm_log.json": llm_log, 
                "mbz_log.json": mbz_log, 
                "metadata.json": summary_meta,
                "BASIS_for_CLASSIFICATION.md": basis_content
            }
            self._save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle)
            self._record_processed(app_id, status, steam_meta.name, summary_meta)
            return LocalProcessResult(app_id=app_id, status=status, message=message, processed_at=self._get_localized_now())

        except Exception as e:
            logger.error(f"Critical failure for {app_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return LocalProcessResult(app_id=app_id, status="error", message=str(e), processed_at=self._get_localized_now())
        finally:
            if temp_output.exists(): shutil.rmtree(temp_output)

    def _prepare_llm_track_context(self, track_groups: Dict) -> Dict[str, List[Dict[str, Any]]]:
        """Merges redundant tags and prepares a lean context for LLM with durations."""
        context = {}
        for (disc, clean_title), variants in track_groups.items():
            tid = f"{disc}_{clean_title}"
            sources = []
            avg_duration = sum(v["duration"] for v in variants) / len(variants)
            
            # Source A: Filename (Weak)
            sources.append({
                "type": "filename",
                "content": variants[0]["path"].name,
                "inferred_track_num": variants[0].get("filename_track"),
                "duration": round(avg_duration, 2),
                "weight": "weak"
            })
            
            # Source B: Cross-validated Tags (Strong)
            all_tags = [v["meta"] for v in variants if v["meta"]]
            if all_tags:
                unique_tags = []
                for t in all_tags:
                    if t not in unique_tags: unique_tags.append(t)
                
                if len(unique_tags) == 1 and len(variants) > 1:
                    # Multiple files share identical tags -> Strong Evidence
                    sources.append({
                        "type": "embedded_validated",
                        "tags": unique_tags[0],
                        "duration": round(avg_duration, 2),
                        "weight": "strong"
                    })
                else:
                    # Divergent or single tags -> Moderate
                    for i, t in enumerate(unique_tags):
                        sources.append({
                            "type": f"embedded_variant_{i+1}",
                            "tags": t,
                            "duration": round(variants[i]["duration"], 2),
                            "weight": "moderate"
                        })
            
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
            key = (self._safe_int_track(meta.get("disc_number", 1)) or 1, re.sub(r'^(\d+[\s.-]+)+', '', f.stem).strip().lower())
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
            zip_path = output_base / f"{app_id}_{safe_name}"
            for log_name, log_content in logs.items():
                if log_content:
                    log_file = source_dir / log_name
                    if log_name.endswith(".json"):
                        with open(log_file, "w", encoding="utf-8") as f:
                            json.dump(log_content, f, indent=2, ensure_ascii=False)
                    else:
                        # For .md or other text files
                        log_file.write_text(str(log_content), encoding="utf-8")
            shutil.make_archive(str(zip_path), 'zip', source_dir)
            logger.info(f"Local package saved: {zip_path}.zip")
        except Exception as e:
            logger.error(f"Failed to save local package for {app_id}: {e}")
