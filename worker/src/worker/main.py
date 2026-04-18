import os
import logging
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import WorkerInput, WorkerOutput, ResolvedMetadata, SteamMetadata
from .storage import WorkerStorage
from .ident.embedded import EmbeddedMetadataExtractor
from .ident.cross_val import CrossFormatValidator
from .ident.mbz import MusicBrainzIdentifier
from .tagger import AudioTagger
from .llm import LLMService

import logging
logger = logging.getLogger("worker")
from prefect import flow, task

@flow(name="sst-worker-flow")
def process_single_album_flow(scout_data: dict, config_dict: dict) -> dict:
    """
    Prefect flow that runs the Worker logic for a specific album.
    This can be triggered remotely by Core.
    """
    # Setup logging inside the flow based on config
    log_level = config_dict.get("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(level=numeric_level, force=True)
    logger.setLevel(numeric_level)

    app_id = scout_data["app_id"]
    album_name = scout_data["name"]
    logger.info(f">>> Starting worker processing for: {album_name} ({app_id})")

    try:
        service = WorkerService(config_dict)
        worker_input = WorkerInput(
            app_id=app_id,
            files=scout_data.get("files", []),
            steam=SteamMetadata(
                app_id=app_id,
                name=album_name,
                developer=scout_data.get("developer"),
                publisher=scout_data.get("publisher"),
                genre=scout_data.get("genre"),
                tags=scout_data.get("tags", []),
                url=scout_data.get("url")
            )
        )
        
        result = service.process_job(worker_input)
        logger.info(f"<<< Finished worker processing for {app_id}. Status: {result.status}")
        return result.model_dump()
        
    except Exception as e:
        logger.error(f"Worker flow failed for {app_id}: {e}", exc_info=True)
        raise


class WorkerService:
    def __init__(self, config: dict):
        self.config = config
        self.storage = WorkerStorage(
            endpoint_url=config["S3_ENDPOINT_URL"],
            access_key=config["S3_ACCESS_KEY"],
            secret_key=config["S3_SECRET_KEY"],
            bucket_name=config["S3_BUCKET_NAME"]
        )
        mbz_agent = config.get("MUSICBRAINZ_USER_AGENT", "SST/1.0.0 (contact@example.com)")
        self.mbz = MusicBrainzIdentifier(app_name="SST", version="1.0.0", contact=mbz_agent)
        self.llm = LLMService(config, self.storage)

    def process_job(self, input_data: WorkerInput) -> WorkerOutput:
        app_id = input_data.app_id
        self.llm.set_context(app_id, input_data.steam.name)
        temp_dir = Path(tempfile.mkdtemp(prefix=f"sst_worker_{app_id}_"))
        logger.info(f"Processing App ID {app_id} in {temp_dir}")
        
        try:
            # 1. Download & Categorize
            local_files_with_rel = []
            for s3_key in input_data.files:
                relative_path = str(Path(s3_key).relative_to(f"ingest/{app_id}"))
                dest = temp_dir / relative_path
                if self.storage.download_file(s3_key, dest):
                    local_files_with_rel.append((dest, relative_path))

            # 2. Extract & Group
            track_groups = self._group_by_track(local_files_with_rel)
            format_map = self._get_format_map([f for f, _ in local_files_with_rel])
            
            # 3. Identification
            validated_album = CrossFormatValidator.validate_album(format_map)
            mb_result = self.mbz.search_release(input_data.steam.name, len(track_groups))
            
            resolved = self._merge_metadata(input_data, validated_album, mb_result)
            status = "success" if (resolved.resolved and resolved.album) else "review"

            # 4. Processing & Tagging
            tagger = AudioTagger(temp_dir / "output")
            processed_tracks_meta = []
            output_refs = []

            for track_id, tracks in track_groups.items():
                best_file_meta = self._select_best_quality(tracks)
                source_path = best_file_meta["path"]
                tier = best_file_meta["tier"]
                
                processed_path = tagger.convert_and_limit(source_path, tier)
                
                artwork_bytes = None
                if best_file_meta.get("has_artwork"):
                    artwork_bytes = self._extract_raw_artwork(source_path)
                    if artwork_bytes:
                        artwork_bytes = tagger.process_artwork(artwork_bytes)

                track_tags = self._assemble_tags(best_file_meta, resolved, input_data.steam)
                tagger.write_tags(processed_path, track_tags, artwork_bytes)
                
                # Upload single file
                rel_path = f"{track_id[0]}/{processed_path.name}"
                s3_key = self.storage.upload_result(processed_path, status, app_id, rel_path)
                output_refs.append(s3_key)
                
                # Record track metadata for metadata.json
                processed_tracks_meta.append({
                    "file_path": rel_path,
                    "original_filename": source_path.name,
                    "parent_dir": best_file_meta.get("parent_dir", ""),
                    "title": track_tags["title"],
                    "artist": track_tags["artist"],
                    "tier": tier
                })

            # 5. Save metadata.json & Preserve .acf
            final_prefix = f"{status}/{app_id}"
            metadata_payload = {
                "app_id": app_id,
                "album_name": resolved.album,
                "status": status,
                "processed_at": datetime.utcnow().isoformat(),
                "steam_info": {
                    "developer": input_data.steam.developer,
                    "publisher": input_data.steam.publisher,
                    "url": input_data.steam.url
                },
                "external_info": {
                    "source": resolved.source,
                    "mbid": resolved.mbid,
                    "vgmdb_url": resolved.vgmdb_url
                },
                "tracks": processed_tracks_meta
            }
            self.storage.upload_json(metadata_payload, f"{final_prefix}/metadata.json")

            acf_key = f"ingest/{app_id}/appmanifest_{app_id}.acf"
            self.storage.copy_file(acf_key, f"{final_prefix}/appmanifest_{app_id}.acf")

            return WorkerOutput(app_id=app_id, status=status, file_refs=output_refs, resolved=resolved)

        except Exception as e:
            logger.error(f"Job failed: {e}", exc_info=True)
            return WorkerOutput(app_id=app_id, status="failed", error=str(e))
        finally:
            shutil.rmtree(temp_dir)

    def _group_by_track(self, files_with_rel: List[tuple]) -> Dict[tuple, List[dict]]:
        groups = {}
        for f, rel_path in files_with_rel:
            meta = EmbeddedMetadataExtractor.extract(f)
            key = (meta.get("disc_number", 1), meta.get("track_number", 0), meta.get("title") or f.stem)
            if key not in groups: groups[key] = []
            meta["path"] = f
            p = Path(rel_path).parent
            meta["parent_dir"] = p.as_posix() if str(p) != "." else ""
            groups[key].append(meta)
        return groups

    def _select_best_quality(self, variants: List[dict]) -> dict:
        for v in variants:
            if v["path"].suffix.lower() in [".flac", ".wav", ".aiff", ".m4a"]:
                v["tier"] = "lossless"
                return v
        for v in variants:
            if v["path"].suffix.lower() == ".mp3":
                v["tier"] = "mp3"
                return v
        v = variants[0]
        v["tier"] = "lossy"
        return v

    def _merge_metadata(self, input_data, validated, mb) -> ResolvedMetadata:
        s = input_data.steam
        return ResolvedMetadata(
            resolved=bool(mb or validated),
            source="musicbrainz" if mb else "embedded",
            album=s.name if s else validated.get("album"),
            artist=validated.get("artist") or (mb.get("artist") if mb else None),
            album_artist=f"{s.developer} | {s.publisher}" if s else None,
            genre=f"STEAM, VGM, {s.genre or ''}",
            year=validated.get("year") or (mb.get("year") if mb else None),
            mbid=mb.get("mbid") if mb else None,
            vgmdb_url=mb.get("vgmdb_url") if mb else None
        )

    def _assemble_tags(self, track_meta, album_resolved, steam) -> dict:
        total_discs = album_resolved.total_discs if hasattr(album_resolved, 'total_discs') else 1
        raw_title = track_meta.get("title") or track_meta["path"].stem
        
        normalized_title = self.llm.ask(
            "title_normalization",
            [
                {"role": "system", "content": "You are a professional music metadata editor. Normalize the given track title. Remove track numbers, extensions, and clarify Japanese titles if possible. Return ONLY the title."},
                {"role": "user", "content": f"Title: {raw_title}"}
            ]
        ) or raw_title

        return {
            "title": normalized_title,
            "artist": track_meta.get("artist") or album_resolved.artist,
            "album": album_resolved.album,
            "album_artist": album_resolved.album_artist,
            "genre": album_resolved.genre,
            "year": album_resolved.year,
            "track_num": str(track_meta.get("track_number", 1)),
            "disc_num": f"{track_meta.get('disc_number', 1)}/{total_discs or 1}",
            "steam_appid": steam.app_id if steam else None,
            "mbid": album_resolved.mbid,
            "vgmdb_url": album_resolved.vgmdb_url
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

def deploy():
    """Starts the Worker and serves its processing flow."""
    print("Starting SST Worker Flow Server...")
    process_single_album_flow.serve(
        name="sst-worker-deployment",
    )

if __name__ == "__main__":
    deploy()
