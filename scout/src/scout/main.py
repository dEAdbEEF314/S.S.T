import os
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from .scanner import SteamScanner
from .uploader import S3Uploader
from .models import ScoutResult, WorkerInput

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scout")

class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore",
        env_ignore_empty=True,
        case_sensitive=False
    )

    steam_library_path: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    s3_region: str = "us-east-1"
    env_mode: str = "development"
    log_level: str = "INFO"

def main():
    # Argument Parsing
    parser = argparse.ArgumentParser(description="SST Scout - Scan Steam library for soundtracks.")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit the number of soundtracks to process.")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-processing of already completed albums.")
    args = parser.parse_args()

    load_dotenv()
    try:
        config = Config()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return

    logging.getLogger().setLevel(config.log_level)

    scanner = SteamScanner(config.steam_library_path)
    uploader = S3Uploader(
        endpoint_url=config.s3_endpoint_url,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        bucket_name=config.s3_bucket_name,
        region=config.s3_region
    )

    logger.info(f"Scanning library: {config.steam_library_path}")
    soundtracks = scanner.find_soundtracks()
    
    # 1. Duplicate Check (Skip if exists and not forced)
    active_list = []
    for ost in soundtracks:
        app_id = ost["app_id"]
        if not args.force and uploader.check_exists(app_id):
            logger.info(f"Skipping already processed album: {ost['name']} ({app_id})")
            continue
        active_list.append(ost)

    # 2. Apply limit
    if args.limit:
        logger.info(f"Test Mode: Limiting processing to first {args.limit} albums.")
        active_list = active_list[:args.limit]

    logger.info(f"Processing {len(active_list)} soundtracks.")

    for ost in active_list:
        app_id = ost["app_id"]
        logger.info(f"Processing App ID {app_id}: {ost['name']}")
        
        music_files = scanner.collect_music_files(ost["install_dir"])
        if not music_files:
            logger.warning(f"No music files found for {ost['name']}. Skipping.")
            continue

        # Prepare for upload: (local_path, relative_path)
        upload_queue = []
        
        # A. Add audio files
        for f in music_files:
            upload_queue.append((f, scanner.get_relative_path(f, ost["install_dir"])))
        
        # B. Add ACF file (New Requirement)
        acf_path = Path(ost["acf_path"])
        if acf_path.exists():
            upload_queue.append((acf_path, Path(acf_path.name)))

        logger.info(f"Uploading {len(upload_queue)} files (incl. manifest)...")
        uploaded_keys = uploader.upload_files(app_id, upload_queue)

        # Generate Result (Filtering out the manifest from track counts)
        audio_keys = [k for k in uploaded_keys if not k.endswith('.acf')]
        ext_counts = {}
        for f in music_files:
            ext = f.suffix.lower().lstrip('.')
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        scout_result = ScoutResult(
            app_id=app_id,
            name=ost["name"],
            install_dir=ost["install_dir"],
            developer=ost.get("developer"),
            publisher=ost.get("publisher"),
            url=ost.get("url"),
            track_count=len(audio_keys),
            files_by_ext=ext_counts,
            acf_key=str(app_id),
            uploaded_at=datetime.utcnow()
        )

        worker_input = WorkerInput(
            app_id=app_id,
            files=audio_keys,
            steam=scout_result # Pass full metadata to worker
        )

        # Output results
        print("--- SCOUT RESULT ---")
        print(scout_result.model_dump_json(indent=2))
        print("--- WORKER INPUT ---")
        print(worker_input.model_dump_json(indent=2))
        print("--------------------")

if __name__ == "__main__":
    main()
