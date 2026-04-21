import os
import json
import logging
import argparse
from typing import Optional
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from .scanner import SteamScanner
from .processor import LocalProcessor
from .models import SteamMetadata, LocalProcessResult

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
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "sst_local_state.db"
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    s3_region: str = "us-east-1"
    s3_filer_url: str
    steam_language: str = "japanese"
    env_mode: str = "production"
    log_level: str = "INFO"
    llm_base_url: str
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_limit_rpm: int = 30
    llm_limit_tpm: int = 15000
    llm_limit_rpd: int = 14400

def main():
    # Argument Parsing
    parser = argparse.ArgumentParser(description="SST Scout - Local Processor for Steam Soundtracks.")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit the number of soundtracks to process.")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-processing of already completed albums.")
    args = parser.parse_args()

    load_dotenv()
    try:
        config = Config()
    except Exception as e:
        print(f"Configuration error: {e}")
        return

    # Initialize logging with the level from config
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    logger.setLevel(numeric_level)
    
    logger.info(f"SST Local Processor starting in {config.env_mode} mode")

    scanner = SteamScanner(
        config.steam_library_path,
        cache_path="scout_cache.json",
        language=config.steam_language
    )

    processor = LocalProcessor(config)

    logger.info(f"Scanning library: {config.steam_library_path}")
    soundtracks = scanner.find_soundtracks(force=args.force, limit=args.limit)
    
    # Filter out already processed albums unless forced
    active_list = []
    for ost in soundtracks:
        app_id = ost["app_id"]
        if not args.force and processor.is_processed(app_id):
            logger.info(f"Skipping already processed album: {ost['name']} ({app_id})")
            continue
        active_list.append(ost)

    logger.info(f"Queueing {len(active_list)} soundtracks for local processing.")

    for ost in active_list:
        app_id = ost["app_id"]
        install_dir = Path(ost["install_dir"])
        
        steam_meta = SteamMetadata(
            app_id=app_id,
            name=ost["name"],
            developer=ost.get("developer"),
            publisher=ost.get("publisher"),
            url=ost.get("url"),
            tags=ost.get("tags", []),
            genre=ost.get("genre"),
            release_date=ost.get("release_date")
        )

        # Process locally (Select -> Convert -> Tag -> Upload)
        logger.info(f"Target Directory: {install_dir}")
        result = processor.process_album(app_id, install_dir, steam_meta)
        
        if result.status == "archive":
            logger.info(f"Successfully archived App ID {app_id}: {ost['name']}")
        elif result.status == "review":
            logger.warning(f"Sent App ID {app_id} to review: {result.message}")
        else:
            logger.error(f"Failed to process App ID {app_id}: {result.message}")

if __name__ == "__main__":
    main()
