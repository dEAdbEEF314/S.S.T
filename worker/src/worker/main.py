import os
import logging
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from .models import WorkerInput, WorkerOutput, ResolvedMetadata
from .storage import WorkerStorage
from .ident.embedded import EmbeddedMetadataExtractor
from .ident.cross_val import CrossFormatValidator
from .ident.mbz import MusicBrainzIdentifier
from .tagger import AudioTagger

logger = logging.getLogger("worker")

class WorkerService:
    def __init__(self, config: dict):
        self.storage = WorkerStorage(
            endpoint_url=config["S3_ENDPOINT_URL"],
            access_key=config["S3_ACCESS_KEY"],
            secret_key=config["S3_SECRET_KEY"],
            bucket_name=config["S3_BUCKET_NAME"]
        )
        self.mbz = MusicBrainzIdentifier(app_name="SST", version="1.0.0", contact="contact@example.com")

    def process_job(self, input_data: WorkerInput) -> WorkerOutput:
        app_id = input_data.app_id
        temp_dir = Path(tempfile.mkdtemp(prefix=f"sst_worker_{app_id}_"))
        logger.info(f"Processing App ID {app_id} in {temp_dir}")
        
        try:
            # 1. Download & Categorize
            local_files = []
            for s3_key in input_data.files:
                dest = temp_dir / Path(s3_key).relative_to("ingest")
                if self.storage.download_file(s3_key, dest):
                    local_files.append(dest)

            # 2. Extract Metadata & Group by "Unique Track"
            # Key = (disc, track_num, title_hint)
            track_groups = self._group_by_track(local_files)
            
            # 3. Validation & Identification (Album level)
            format_map = {ext: [m for m in tracks] for ext, tracks in self._get_format_map(local_files).items()}
            validated_album = CrossFormatValidator.validate_album(format_map)
            mb_result = self.mbz.search_release(input_data.steam.name, len(track_groups))
            
            resolved = self._merge_metadata(input_data, validated_album, mb_result)
            status = "success" if (resolved.resolved and resolved.album) else "review"

            # 4. Exclusive Selection & Tagging
            tagger = AudioTagger(temp_dir / "output")
            output_refs = []

            for track_id, tracks in track_groups.items():
                # SELECT BEST QUALITY TRACK
                best_file_meta = self._select_best_quality(tracks)
                source_path = best_file_meta["path"]
                tier = best_file_meta["tier"]
                
                logger.info(f"Selected {tier} for track {track_id}: {source_path.name}")
                
                # Convert with strict 48kHz/24bit/320k limits
                processed_path = tagger.convert_and_limit(source_path, tier)
                
                # Process Artwork (Track-specific)
                artwork_bytes = None
                if best_file_meta.get("has_artwork"):
                    # Extract raw bytes first (simplified here)
                    artwork_bytes = self._extract_raw_artwork(source_path)
                    if artwork_bytes:
                        artwork_bytes = tagger.process_artwork(artwork_bytes)

                # Write Tags
                track_tags = self._assemble_tags(best_file_meta, resolved, input_data.steam)
                tagger.write_tags(processed_path, track_tags, artwork_bytes)
                
                # Upload single file
                rel_path = f"{track_id[0]}/{processed_path.name}"
                s3_key = self.storage.upload_result(processed_path, status, app_id, rel_path)
                output_refs.append(s3_key)

            return WorkerOutput(app_id=app_id, status=status, file_refs=output_refs, resolved=resolved)

        except Exception as e:
            logger.error(f"Job failed: {e}", exc_info=True)
            return WorkerOutput(app_id=app_id, status="failed", error=str(e))
        finally:
            shutil.rmtree(temp_dir)

    def _group_by_track(self, files: List[Path]) -> Dict[tuple, List[dict]]:
        groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            # Use disc/track/title as unique key to group format variants
            key = (meta.get("disc_number", 1), meta.get("track_number", 0), meta.get("title") or f.stem)
            if key not in groups: groups[key] = []
            meta["path"] = f
            groups[key].append(meta)
        return groups

    def _select_best_quality(self, variants: List[dict]) -> dict:
        """Priority: Lossless -> MP3 -> Other Lossy"""
        # 1. Lossless
        for v in variants:
            if v["path"].suffix.lower() in [".flac", ".wav", ".aiff", ".m4a"]:
                v["tier"] = "lossless"
                return v
        # 2. MP3
        for v in variants:
            if v["path"].suffix.lower() == ".mp3":
                v["tier"] = "mp3"
                return v
        # 3. Other Lossy
        v = variants[0]
        v["tier"] = "lossy"
        return v

    def _merge_metadata(self, input_data, validated, mb) -> ResolvedMetadata:
        # Implementation of about_TAG.txt mapping (simplified here)
        s = input_data.steam
        return ResolvedMetadata(
            resolved=bool(mb or validated),
            source="musicbrainz" if mb else "embedded",
            album=s.name if s else validated.get("album"),
            artist=validated.get("artist") or (mb.get("artist") if mb else None),
            album_artist=f"{s.developer} | {s.publisher}" if s else None,
            genre=f"STEAM, VGM, {s.genre or ''}",
            year=validated.get("year") or (mb.get("year") if mb else None),
            mbid=mb.get("mbid") if mb else None
        )

    def _assemble_tags(self, track_meta, album_resolved, steam) -> dict:
        total_discs = album_resolved.total_discs if hasattr(album_resolved, 'total_discs') else 1
        return {
            "title": track_meta.get("title") or track_meta["path"].stem,
            "artist": track_meta.get("artist") or album_resolved.artist,
            "album": album_resolved.album,
            "album_artist": album_resolved.album_artist,
            "genre": album_resolved.genre,
            "year": album_resolved.year,
            "track_num": str(track_meta.get("track_number", 1)),
            "disc_num": f"{track_meta.get('disc_number', 1)}/{total_discs or 1}",
            "steam_appid": steam.app_id if steam else None,
            "mbid": album_resolved.mbid
        }

    def _get_format_map(self, files):
        res = {}
        for f in files:
            ext = f.suffix.lower().lstrip('.')
            if ext not in res: res[ext] = []
            res[ext].append(EmbeddedMetadataExtractor.extract(f))
        return res

    def _extract_raw_artwork(self, path: Path) -> Optional[bytes]:
        from mutagen import File
        from mutagen.id3 import ID3
        try:
            audio = File(path)
            if hasattr(audio, 'pictures') and audio.pictures:
                return audio.pictures[0].data
            elif isinstance(audio, ID3):
                apics = audio.getall("APIC")
                if apics: return apics[0].data
        except: pass
        return None
