import os
import json
import logging
from datetime import datetime
from typing import List, Dict

from prefect import flow, task, get_run_logger, unmapped
from pydantic_settings import BaseSettings, SettingsConfigDict

# Import logic from other modules (since we have them mounted)
from scout.models import ScoutResult
from worker.main import WorkerService
from worker.models import WorkerInput, SteamMetadata

class CoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    musicbrainz_user_agent: str
    log_level: str = "INFO"

@task(retries=2, retry_delay_seconds=30)
def process_single_album_task(scout_data: dict, config_dict: dict) -> dict:
    """
    Prefect task that runs the Worker logic for a specific album.
    """
    logger = get_run_logger()
    app_id = scout_data["app_id"]
    album_name = scout_data["name"]
    logger.info(f">>> Starting worker processing for: {album_name} ({app_id})")

    try:
        # Initialize Worker with global config
        service = WorkerService(config_dict)
        
        # Construct WorkerInput from Scout output
        # Ensure 'files' is present (passed from the orchestrator)
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
        logger.error(f"Worker task failed for {app_id}: {e}", exc_info=True)
        raise

@flow(name="SST-Production-Pipeline")
def sst_main_flow(scout_results: List[dict]):
    """
    The main SST orchestration flow.
    """
    config = CoreConfig()
    logger = get_run_logger()
    logger.info(f"SST Pipeline triggered for {len(scout_results)} albums.")

    # Convert config to dict for worker initialization
    config_dict = config.model_dump(by_alias=True)
    env_mapping = {
        "s3_endpoint_url": "S3_ENDPOINT_URL",
        "s3_access_key": "S3_ACCESS_KEY",
        "s3_secret_key": "S3_SECRET_KEY",
        "s3_bucket_name": "S3_BUCKET_NAME",
        "musicbrainz_user_agent": "MUSICBRAINZ_USER_AGENT"
    }
    worker_config = {env_mapping.get(k, k): v for k, v in config_dict.items()}

    # Parallel execution with unmapped configuration
    futures = process_single_album_task.map(scout_results, config_dict=unmapped(worker_config))

    # Summary
    success_count = 0
    review_count = 0
    final_results = []

    for f in futures:
        try:
            res = f.result()
            final_results.append(res)
            if res.get("status") == "success":
                success_count += 1
            elif res.get("status") == "review":
                review_count += 1
        except Exception as e:
            logger.error(f"Task future failed: {e}")
    
    logger.info(f"Pipeline Finished. Success: {success_count}, Review: {review_count}")
    return final_results

if __name__ == "__main__":
    pass
