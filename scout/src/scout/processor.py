import os
import re
import logging
import shutil
import tempfile
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import SteamMetadata, TrackMetadata, AlbumMetadataSet, ProcessingContext, LocalProcessResult
from .tagger import AudioTagger
from .storage import WorkerStorage 
from .llm import LLMOrganizer
from .ident.mbz import MusicBrainzIdentifier
from .ident.embedded import EmbeddedMetadataExtractor

logger = logging.getLogger("scout.processor")

class LocalProcessor:
    def __init__(self, config: Any):
        self.config = config
        self.storage = WorkerStorage(
            filer_url=config.s3_filer_url,
            bucket_name=config.s3_bucket_name,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key
        )
        self.mbz = MusicBrainzIdentifier("SST-Local", "2.0", "contact@outergods.lan")
        self.llm = LLMOrganizer(
            api_key=config.llm_api_key, 
            base_url=config.llm_base_url, 
            storage=self.storage,
            model=config.llm_model,
            rpm=config.llm_limit_rpm,
            tpm=config.llm_limit_tpm,
            rpd=config.llm_limit_rpd
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

    def is_processed(self, app_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM processed_albums WHERE app_id = ?", (app_id,))
            return cur.fetchone() is not None

    def _get_localized_now(self):
        # Basic timezone support without extra libs
        from datetime import timezone, timedelta
        tz_env = os.environ.get("TZ", "UTC")
        if tz_env == "Asia/Tokyo":
            return datetime.now(timezone(timedelta(hours=9)))
        return datetime.now(timezone.utc)

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata) -> LocalProcessResult:
        """Processes an album locally, consolidates metadata via LLM, and uploads results."""
        if not install_dir.exists():
            return LocalProcessResult(app_id=app_id, status="error", message="Dir not found")

        logger.info(f"--- Processing {steam_meta.name} ({app_id}) ---")
        
        all_files = self._list_audio_files(install_dir)
        if not all_files: return LocalProcessResult(app_id=app_id, status="skip", message="No audio")

        track_groups = self._group_by_logical_track(all_files)
        sources, mb_log, vgmdb_url = self._collect_metadata_sources(track_groups, steam_meta)
        adopted_files = self._adopt_optimal_files(track_groups)
        
        # Prepare track-by-track context for LLM
        track_sources = self._regroup_sources_by_track(sources, list(track_groups.keys()))
        raw_metadata = {
            "steam": steam_meta.model_dump(),
            "track_sources": track_sources
        }

        # 4. LLM Consolidation (Iterative Chat)
        self.llm.set_context(app_id, steam_meta.name)
        final_metadata, llm_log = self.llm.consolidate_metadata(steam_meta.model_dump(), track_sources)
        
        status = "archive"
        message = "Success"

        if not final_metadata:
            # Save the failure log anyway
            self.storage.upload_json(llm_log, f"review/{app_id}/llm_error_log.json")
            self.storage.upload_json(raw_metadata, f"review/{app_id}/raw_metadata.json")
            if mb_log: self.storage.upload_json(mb_log, f"review/{app_id}/mbz_log.json")
            return LocalProcessResult(app_id=app_id, status="review", message="LLM failed to consolidate")

        # 5. Conversion, Tagging and Upload
        temp_output = self.working_dir / f"final_{app_id}_{datetime.now().strftime('%H%M%S')}"
        temp_output.mkdir(parents=True, exist_ok=True)
        processed_tracks_meta = [] 
        
        try:
            tagger = AudioTagger(temp_output)
            output_refs = []
            
            # First pass: validate mandatory fields
            for track_key in adopted_files.keys():
                disc, clean_title = track_key
                track_id_str = f"{disc}_{clean_title}"
                tags = final_metadata.get(track_id_str) or {}
                
                # TIT2 (Title) or TRCK (Track Number) missing -> Review
                if not tags.get("TIT2") or tags.get("TIT2") == "Unknown" or not tags.get("TRCK") or tags.get("TRCK") == "0":
                    logger.warning(f"Mandatory metadata missing for track {track_id_str}. Moving album to review.")
                    status = "review"
                    message = "Mandatory metadata (TIT2/TRCK) missing"

            for track_key, adopted_info in adopted_files.items():
                disc, clean_title = track_key
                source_path = adopted_info["path"]
                tier = adopted_info["tier"]
                
                # Convert
                processed_path = tagger.convert_and_limit(source_path, tier)
                
                track_id_str = f"{disc}_{clean_title}"
                tags = final_metadata.get(track_id_str) or {}
                
                def _get_val(tag_key, fallback):
                    val = tags.get(tag_key)
                    if val is None or str(val).strip().lower() in ["null", "unknown", ""]:
                        return fallback
                    return str(val).strip()

                # Use Parent info for COMM if available, else fallback to soundtrack
                if steam_meta.parent_app_id:
                    comm_title = steam_meta.parent_name or steam_meta.name
                    comm_tags = steam_meta.parent_tags or steam_meta.tags
                    comm_appid = steam_meta.parent_app_id
                    comm_url = f"https://store.steampowered.com/app/{comm_appid}"
                else:
                    comm_title = steam_meta.name
                    comm_tags = steam_meta.tags
                    comm_appid = app_id
                    comm_url = steam_meta.url

                tag_map = {
                    "title": _get_val("TIT2", clean_title),
                    "artist": _get_val("TPE1", steam_meta.developer or "Unknown Artist"),
                    "album": _get_val("TALB", steam_meta.name),
                    "album_artist": f"{steam_meta.developer} | {steam_meta.publisher}" if steam_meta.developer and steam_meta.publisher else _get_val("TPE2", "Unknown Artist"),
                    "genre": _get_val("TCON", f"STEAM VGM, {steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'}"),
                    "grouping": _get_val("TIT1", f"{steam_meta.name} | Steam"),
                    "comment": f"{comm_title} | {', '.join(comm_tags[:10])} | {comm_appid} | {comm_url}",
                    "composer": _get_val("TCOM", steam_meta.developer or "Unknown"),
                    "year": _get_val("TDRC", steam_meta.release_date[:4] if steam_meta.release_date else str(datetime.now().year)),
                    "track_number": str(tags.get("TRCK") or 0),
                    "disc_number": str(tags.get("TPOS") or f"{disc}/1"),
                    "language": _get_val("TLAN", "jpn" if self.config.steam_language == "japanese" else "eng")
                }
                
                artwork = self._get_best_artwork(track_groups[track_key])
                if artwork: artwork = tagger.process_artwork(artwork)
                
                tagger.write_tags(processed_path, tag_map, artwork)
                
                # Upload
                upload_status = status if status != "archive" else "archive"
                s3_key = self.storage.upload_result(processed_path, upload_status, app_id, f"{disc}/{processed_path.name}")
                output_refs.append(s3_key)

                processed_tracks_meta.append({
                    "file_path": f"{disc}/{processed_path.name}",
                    "original_filename": source_path.name,
                    "tier": tier,
                    "tags": tag_map,
                    "title": tag_map.get("title"),
                    "source": tags.get("source", "Unknown Fallback")
                })

            # Final Metadata and Logs Upload
            dest_dir = "archive" if status == "archive" else f"review/{app_id}"
            prefix = "" if status == "archive" else "" # Path already contains review/app_id
            
            self.storage.upload_json(llm_log, f"{dest_dir}/{app_id}/llm_log.json" if status == "archive" else f"{dest_dir}/llm_log.json")
            self.storage.upload_json(raw_metadata, f"{dest_dir}/{app_id}/raw_metadata.json" if status == "archive" else f"{dest_dir}/raw_metadata.json")
            if mb_log:
                self.storage.upload_json(mb_log, f"{dest_dir}/{app_id}/mbz_log.json" if status == "archive" else f"{dest_dir}/mbz_log.json")
            
            summary_meta = {
                "app_id": app_id,
                "album_name": steam_meta.name,
                "status": status,
                "processed_at": self._get_localized_now().isoformat(),
                "file_refs": output_refs,
                "tracks": processed_tracks_meta,
                "steam_info": steam_meta.model_dump(),
                "external_info": {
                    "source": "llm_consolidated",
                    "vgmdb_url": vgmdb_url
                }
            }
            self.storage.upload_json(summary_meta, f"{dest_dir}/{app_id}/metadata.json" if status == "archive" else f"{dest_dir}/metadata.json")
            
            # 6. Save local ZIP package
            log_bundle = {
                "llm_log.json": llm_log,
                "raw_metadata.json": raw_metadata,
                "mbz_log.json": mb_log,
                "metadata.json": summary_meta
            }
            self._save_local_package(app_id, status, steam_meta.name, temp_output, log_bundle)

            self._record_processed(app_id, status, steam_meta.name, final_metadata)
            return LocalProcessResult(app_id=app_id, status=status, message=message, processed_at=self._get_localized_now())

        except Exception as e:
            logger.error(f"Failed processing {app_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return LocalProcessResult(app_id=app_id, status="error", message=str(e), processed_at=self._get_localized_now())
        finally:
            if temp_output.exists():
                shutil.rmtree(temp_output)

    def _regroup_sources_by_track(self, sources: List[AlbumMetadataSet], track_keys: List[Tuple[int, str]]) -> Dict[str, List[Dict[str, Any]]]:
        regrouped = {}
        for disc, clean_title in track_keys:
            key_str = f"{disc}_{clean_title}"
            track_variants = []
            
            for src_set in sources:
                for t in src_set.tracks:
                    # Robust matching logic:
                    # 1. Exact match on clean title and disc
                    # 2. If MusicBrainz, might not have disc, match on title only if disc is 1
                    t_clean = re.sub(r'^(\d+[\s.-]+)+', '', t.title).strip().lower()
                    if t_clean == clean_title and (t.disc_number == disc or (t.disc_number is None and disc == 1)):
                        track_variants.append({
                            "source_name": src_set.source_name,
                            "metadata": t.model_dump()
                        })
                        break
            regrouped[key_str] = track_variants
        return regrouped

    def _collect_metadata_sources(self, track_groups: Dict, steam: SteamMetadata) -> Tuple[List[AlbumMetadataSet], Optional[Dict[str, Any]], Optional[str]]:
        sources = []
        formats = set()
        vgmdb_url = None
        for variants in track_groups.values():
            for v in variants: formats.add(v["format"])
        for fmt in formats:
            source = AlbumMetadataSet(source_name=f"{fmt.upper()} Embedded Tags")
            for key, variants in track_groups.items():
                for v in variants:
                    if v["format"] == fmt:
                        source.tracks.append(TrackMetadata(
                            title=v["meta"].get("title") or "",
                            artist=v["meta"].get("artist"),
                            album=v["meta"].get("album"),
                            track_number=self._safe_int_track(v["meta"].get("track_number")),
                            disc_number=self._safe_int_track(v["meta"].get("disc_number", 1)),
                            duration_sec=v["duration"],
                            file_format=fmt,
                            source=f"embedded_{fmt}"
                        ))
            if source.tracks: sources.append(source)
            
        mb_data, mb_log = self.mbz.search_release(steam.name, len(track_groups), steam.release_date)
        if mb_data:
            vgmdb_url = mb_data.get("vgmdb_url")
            mb_source = AlbumMetadataSet(source_name="MusicBrainz")
            for t in mb_data.get("tracks", []):
                mb_source.tracks.append(TrackMetadata(
                    title=t.get("title", ""),
                    artist=t.get("artist"),
                    track_number=self._safe_int_track(t.get("track_num")),
                    disc_number=self._safe_int_track(t.get("disc_num", 1)),
                    duration_sec=t.get("duration_msec", 0) / 1000.0 if t.get("duration_msec") else None,
                    file_format="N/A",
                    source="musicbrainz"
                ))
            sources.append(mb_source)
        return sources, mb_log, vgmdb_url

    def _get_best_artwork(self, variants: List[Dict]) -> Optional[bytes]:
        from mutagen import File
        for v in variants:
            try:
                audio = File(v["path"])
                if audio is None or not audio.tags: continue
                if v["format"] in ["mp3", "aiff"]:
                    for tag in audio.tags.values():
                        if hasattr(tag, 'data') and getattr(tag, 'FrameID', None) == "APIC":
                            return tag.data
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
            clean_title = re.sub(r'^(\d+[\s.-]+)+', '', f.stem).strip().lower()
            disc = self._safe_int_track(meta.get("disc_number", 1)) or 1
            key = (disc, clean_title)
            if key not in groups: groups[key] = []
            groups[key].append({
                "path": f, "meta": meta, "duration": self._get_duration(f), "format": f.suffix.lower().lstrip('.')
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
                    chosen = {"path": v["path"], "tier": "lossless"}
                    break
            if not chosen:
                for v in variants:
                    if v["format"] in ["ogg", "aac", "m4a"]:
                        chosen = {"path": v["path"], "tier": "lossy"}
                        break
            if not chosen: chosen = {"path": variants[0]["path"], "tier": "mp3"}
            adopted[key] = chosen
        return adopted

    def _record_processed(self, app_id: int, status: str, name: str, metadata: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO processed_albums VALUES (?, ?, ?, ?, ?)",
                        (app_id, status, name, self._get_localized_now().isoformat(), json.dumps(metadata)))

    def _save_local_package(self, app_id: int, status: str, album_name: str, source_dir: Path, logs: Dict[str, Any]):
        """Creates a ZIP package of the processed album and saves it to the output directory."""
        try:
            output_base = Path("output") / status
            output_base.mkdir(parents=True, exist_ok=True)
            
            # Create a clean name for the zip file
            safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in album_name])
            zip_path = output_base / f"{app_id}_{safe_name}"
            
            # Copy logs into the temp dir before zipping so they are included
            for log_name, log_content in logs.items():
                if log_content:
                    with open(source_dir / log_name, "w", encoding="utf-8") as f:
                        json.dump(log_content, f, indent=2, ensure_ascii=False)
            
            # Create ZIP
            shutil.make_archive(str(zip_path), 'zip', source_dir)
            logger.info(f"Local package saved: {zip_path}.zip")
        except Exception as e:
            logger.error(f"Failed to save local package for {app_id}: {e}")
