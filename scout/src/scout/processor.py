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
            endpoint_url=config.s3_endpoint_url,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket_name=config.s3_bucket_name,
            region=config.s3_region
        )
        self.mbz = MusicBrainzIdentifier("SST-Local", "2.0", "contact@outergods.lan")
        self.llm = LLMOrganizer(api_key=config.llm_api_key, model=config.llm_model)
        # Setup working directories
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

    def process_album(self, app_id: int, install_dir: Path, steam_meta: SteamMetadata) -> LocalProcessResult:
        """Processes an album locally, consolidates metadata via LLM, and uploads results."""
        if not install_dir.exists():
            return LocalProcessResult(app_id=app_id, status="error", message="Dir not found")

        logger.info(f"--- Processing {steam_meta.name} ({app_id}) ---")
        
        # 1. Scan and Extract
        all_files = self._list_audio_files(install_dir)
        if not all_files: return LocalProcessResult(app_id=app_id, status="skip", message="No audio")

        track_groups = self._group_by_logical_track(all_files)
        
        # 2. Collect Metadata Sources (Factual pooling)
        sources = self._collect_metadata_sources(track_groups, steam_meta)
        
        # 3. Adopt Optimal Files (Determine physical files to keep)
        adopted_files = self._adopt_optimal_files(track_groups)
        
        # 4. LLM Consolidation (Organizing the truth)
        self.llm.set_context(app_id, steam_meta.name)
        llm_context = {
            "steam": steam_meta.model_dump(),
            "sources": [s.model_dump() for s in sources]
        }
        final_metadata = self.llm.consolidate_metadata(llm_context)
        
        if not final_metadata:
            return LocalProcessResult(app_id=app_id, status="review", message="LLM failed to consolidate")

        # 5. Conversion, Tagging and Upload
        temp_output = self.working_dir / f"final_{app_id}_{datetime.now().strftime('%H%M%S')}"
        temp_output.mkdir(parents=True, exist_ok=True)
        try:
            tagger = AudioTagger(temp_output)
            output_refs = []
            
            # Map LLM results back to track keys
            # LLM output keys are typically track identifiers like "1_clean_title"
            
            for track_key, adopted_info in adopted_files.items():
                disc, clean_title = track_key
                source_path = adopted_info["path"]
                tier = adopted_info["tier"]
                
                # Convert
                processed_path = tagger.convert_and_limit(source_path, tier)
                
                # Get tags from LLM result (matching by track identifier)
                # LLM output structure needs to be robustly matched
                track_id_str = f"{disc}_{clean_title}"
                tags = final_metadata.get(track_id_str) or final_metadata.get(clean_title)
                
                if not tags:
                    # Fallback to global album tags
                    tags = final_metadata.get("album_global", {}).copy()
                    tags["TIT2"] = clean_title.capitalize()
                
                # Map to standard names for tagger
                tag_map = {
                    "title": tags.get("TIT2"),
                    "artist": tags.get("TPE1"),
                    "album": tags.get("TALB"),
                    "album_artist": tags.get("TPE2"),
                    "genre": tags.get("TCON"),
                    "grouping": tags.get("TIT1"),
                    "comment": tags.get("COMM"),
                    "composer": tags.get("TCOM"),
                    "year": tags.get("TDRC"),
                    "track_number": tags.get("TRCK"),
                    "disc_number": tags.get("TPOS"),
                    "language": tags.get("TLAN")
                }
                
                # Artwork
                artwork = self._get_best_artwork(track_groups[track_key])
                if artwork: artwork = tagger.process_artwork(artwork)
                
                tagger.write_tags(processed_path, tag_map, artwork)
                
                # Upload
                s3_key = self.storage.upload_result(processed_path, "archive", app_id, f"{disc}/{processed_path.name}")
                output_refs.append(s3_key)

            # Final Metadata Upload
            self.storage.upload_json(final_metadata, f"archive/{app_id}/llm_log.json")
            self.storage.upload_metadata(ProcessingContext(app_id=app_id, steam=steam_meta), "archive", app_id, output_refs)
            
            self._record_processed(app_id, "archive", steam_meta.name, final_metadata)
            return LocalProcessResult(app_id=app_id, status="archive", message="Success")

        except Exception as e:
            logger.error(f"Failed processing {app_id}: {e}")
            return LocalProcessResult(app_id=app_id, status="error", message=str(e))
        finally:
            shutil.rmtree(temp_output)

    def _list_audio_files(self, directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff"}
        return [p for p in directory.rglob("*") if p.suffix.lower() in exts]

    def _group_by_logical_track(self, files: List[Path]) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            # Normalize title (remove numbers, extension, junk)
            clean_title = re.sub(r'^(\d+[\s.-]+)+', '', f.stem).strip().lower()
            
            key = (meta.get("disc_number", 1), clean_title)
            if key not in groups: groups[key] = []
            
            groups[key].append({
                "path": f,
                "meta": meta,
                "duration": self._get_duration(f),
                "format": f.suffix.lower().lstrip('.')
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
            # 1. Lossless
            for v in variants:
                if v["format"] in ["flac", "wav", "aiff", "alac"]:
                    chosen = {"path": v["path"], "tier": "lossless"}
                    break
            # 2. High-quality lossy
            if not chosen:
                for v in variants:
                    if v["format"] in ["ogg", "aac", "m4a"]:
                        chosen = {"path": v["path"], "tier": "lossy"}
                        break
            # 3. MP3
            if not chosen:
                chosen = {"path": variants[0]["path"], "tier": "mp3"}
            adopted[key] = chosen
        return adopted

    def _collect_metadata_sources(self, track_groups: Dict, steam: SteamMetadata) -> List[AlbumMetadataSet]:
        sources = []
        
        # A. Format-specific tag sets
        formats = set()
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
                            track_number=v["meta"].get("track_number"),
                            disc_number=v["meta"].get("disc_number", 1),
                            duration_sec=v["duration"],
                            file_format=fmt,
                            source=f"embedded_{fmt}"
                        ))
            if source.tracks: sources.append(source)

        # B. MusicBrainz Data with Duration Matching for WAV
        mb_data = self.mbz.search_release(steam.name, len(track_groups))
        if mb_data:
            mb_source = AlbumMetadataSet(source_name="MusicBrainz")
            for t in mb_data.get("tracks", []):
                mb_source.tracks.append(TrackMetadata(
                    title=t.get("title", ""),
                    artist=t.get("artist"),
                    track_number=t.get("track_number"),
                    duration_sec=t.get("duration_msec", 0) / 1000.0,
                    file_format="N/A",
                    source="musicbrainz"
                ))
            sources.append(mb_source)

        return sources

    def _get_best_artwork(self, variants: List[Dict]) -> Optional[bytes]:
        # Try to find artwork in any variant
        for v in variants:
            img = EmbeddedMetadataExtractor.extract_artwork(v["path"])
            if img: return img
        return None

    def _record_processed(self, app_id: int, status: str, name: str, metadata: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO processed_albums VALUES (?, ?, ?, ?, ?)",
                        (app_id, status, name, datetime.now().isoformat(), json.dumps(metadata)))
