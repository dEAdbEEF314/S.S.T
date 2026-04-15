import os
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from .scanner import SteamScanner
from .uploader import S3Uploader
from .models import ScoutResult, WorkerInput

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scout")

class Config(BaseSettings):
    steam_library_path: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    s3_region: str = "us-east-1"
    env_mode: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

def main():
    # Argument Parsing
    parser = argparse.ArgumentParser(description="SST Scout - Scan Steam library for soundtracks.")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit the number of soundtracks to process (for testing).")
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
    
    # Apply limit if specified
    if args.limit:
        logger.info(f"Test Mode: Limiting processing to first {args.limit} soundtracks.")
        soundtracks = soundtracks[:args.limit]

    logger.info(f"Found {len(soundtracks)} soundtrack manifests to process.")

    for ost in soundtracks:
        app_id = ost["app_id"]
        logger.info(f"Processing App ID {app_id}: {ost['name']}")
        
        music_files = scanner.collect_music_files(ost["install_dir"])
        if not music_files:
            logger.warning(f"No music files found for {ost['name']}. Skipping.")
            continue

        logger.info(f"Found {len(music_files)} music files. Uploading...")
        
        # Prepare for upload: (local_path, relative_path)
        upload_queue = [
            (f, scanner.get_relative_path(f, ost["install_dir"])) 
            for f in music_files
        ]

        uploaded_keys = uploader.upload_files(app_id, upload_queue)

        # Generate Result
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
            track_count=len(uploaded_keys),
            files_by_ext=ext_counts,
            acf_key=str(app_id),
            uploaded_at=datetime.utcnow()
        )

        worker_input = WorkerInput(
            app_id=app_id,
            files=uploaded_keys
        )

        # Output results (to stdout as JSON for Prefect/next step to capture)
        print("--- SCOUT RESULT ---")
        print(scout_result.model_dump_json(indent=2))
        print("--- WORKER INPUT ---")
        print(worker_input.model_dump_json(indent=2))
        print("--------------------")

if __name__ == "__main__":
    main()
