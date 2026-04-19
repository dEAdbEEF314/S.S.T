import os
import sys
import logging
import shutil
import tempfile
from pathlib import Path

# Add current directory to path for robust imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from typing import List, Dict, Any, Optional
from datetime import datetime

from prefect import flow, task, get_run_logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from models import WorkerInput, WorkerOutput, ResolvedMetadata, SteamMetadata
from storage import WorkerStorage
from tagger import AudioTagger
from ident.mbz import MusicBrainzIdentifier
from ident.embedded import EmbeddedMetadataExtractor
from ident.cross_val import CrossFormatValidator

logger = logging.getLogger(__name__)

class WorkerService:
    def __init__(self, config_dict: dict):
        self.storage = WorkerStorage(
            endpoint_url=config_dict.get("S3_ENDPOINT_URL"),
            access_key=config_dict.get("S3_ACCESS_KEY"),
            secret_key=config_dict.get("S3_SECRET_KEY"),
            bucket_name=config_dict.get("S3_BUCKET_NAME")
        )
        self.mbz = MusicBrainzIdentifier("SST-Worker", "1.0", "contact@outergods.lan")
        self.llm = type('LLMStub', (), {'set_context': lambda *a, **k: None})() # Placeholder

    def process_job(self, input_data: WorkerInput) -> WorkerOutput:
        """Processes a single album: selects best files, converts, tags, and uploads."""
        app_id = input_data.app_id
        self.llm.set_context(app_id, input_data.steam.name)
        temp_dir = Path(tempfile.mkdtemp(prefix=f"sst_worker_{app_id}_"))
        logger.info(f"Processing App ID {app_id} in {temp_dir}")
        
        try:
            # 1. Map tracks by filename to avoid massive downloads
            import re
            track_groups_raw = {}
            
            for s3_key in input_data.files:
                filename = Path(s3_key).name
                if filename.endswith(".json") or filename.endswith(".acf"): continue
                
                # Normalize title for grouping
                clean_title = re.sub(r'^(\d+[\s.-]+)+', '', filename.rsplit('.', 1)[0]).strip().lower()
                track_match = re.search(r'^(\d+)', filename)
                track_num = int(track_match.group(1)) if track_match else 0
                
                key = (1, track_num, clean_title)
                if key not in track_groups_raw: track_groups_raw[key] = []
                track_groups_raw[key].append(s3_key)

            logger.info(f"Identified {len(track_groups_raw)} unique tracks from S3.")

            # 2. Identification (Simplification: Status decided by presence of data)
            status = "archive" if input_data.steam.name else "review"
            
            # 3. Loop through tracks, Download only one, Process and Upload
            tagger = AudioTagger(temp_dir / "output")
            output_refs = []
            processed_tracks_meta = []

            for track_id, s3_keys in track_groups_raw.items():
                disc_num, track_num, _ = track_id
                
                # Selection logic: Lossless > MP3
                adopted_key = None
                tier = "lossy"
                for k in s3_keys:
                    if Path(k).suffix.lower() in [".flac", ".wav", ".aiff"]:
                        adopted_key = k
                        tier = "lossless"
                        break
                if not adopted_key:
                    adopted_key = s3_keys[0]
                    tier = "mp3" if Path(adopted_key).suffix.lower() == ".mp3" else "lossy"

                # Download Adopted File
                local_source = temp_dir / Path(adopted_key).name
                logger.info(f"Adopting track {track_num}: {Path(adopted_key).name} ({tier})")
                if not self.storage.download_file(adopted_key, local_source):
                    continue

                # Convert/Limit Quality
                processed_path = tagger.convert_and_limit(local_source, tier)
                
                # Tagging
                best_file_meta = EmbeddedMetadataExtractor.extract(local_source)
                track_tags = self._assemble_tags(best_file_meta, None, input_data.steam)
                tagger.write_tags(processed_path, track_tags, None)
                
                # Upload to Final Destination
                clean_filename = "".join([c if c.isalnum() or c in ".-_" else "_" for c in processed_path.name])
                rel_path = f"{disc_num}/{clean_filename}"
                
                s3_key = self.storage.upload_result(processed_path, status, app_id, rel_path)
                output_refs.append(s3_key)
                
                # Record Metadata
                processed_tracks_meta.append({
                    "file_path": rel_path,
                    "original_filename": Path(adopted_key).name,
                    "tier": tier,
                    "tags": track_tags
                })
                
                # Cleanup to save local space
                local_source.unlink()
                if processed_path.exists() and processed_path != local_source:
                    processed_path.unlink()

            # 4. Final Metadata JSON
            self.storage.upload_metadata(input_data, status, app_id, output_refs)
            logger.info(f"<<< Finished worker processing for {app_id}. Status: {status}")
            return WorkerOutput(app_id=app_id, status=status, file_refs=output_refs)

        except Exception as e:
            logger.error(f"Worker flow failed for {app_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return WorkerOutput(app_id=app_id, status="failed", error=str(e))
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def _assemble_tags(self, best_meta, resolved, steam) -> dict:
        """Assembles final tags for a track."""
        return {
            "title": best_meta.get("title") or "Unknown Track",
            "artist": steam.developer or "Unknown Artist",
            "album": steam.name,
            "track_number": best_meta.get("track_number"),
            "disc_number": best_meta.get("disc_number", 1),
            "date": datetime.now().year,
            "comment": "Tagged by S.S.T"
        }

@flow(name="sst-worker-flow")
def process_single_album_flow(scout_data: dict, config_dict: dict):
    """Prefect flow that runs on the worker to process one album."""
    logger = get_run_logger()
    
    try:
        worker_input = WorkerInput(**scout_data)
        app_id = worker_input.app_id
        album_name = worker_input.steam.name
    except Exception as e:
        logger.error(f"Failed to parse input: {e}")
        return {"status": "failed", "error": "Invalid input"}

    logger.info(f">>> Starting worker processing for: {album_name} ({app_id})")
    service = WorkerService(config_dict)
    result = service.process_job(worker_input)
    return result.model_dump()

def deploy():
    """Starts the Worker and serves its processing flow."""
    print("Starting SST Worker Flow Server...")
    process_single_album_flow.serve(
        name="sst-worker-deployment",
    )

if __name__ == "__main__":
    deploy()
