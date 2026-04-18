import os
import json
import logging
from typing import List, Dict, Optional

from prefect import flow, task, get_run_logger, unmapped
from pydantic_settings import BaseSettings, SettingsConfigDict

class CoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    musicbrainz_user_agent: Optional[str] = None
    log_level: str = "INFO"
    prefect_flow_name: str = "SST-Production-Pipeline"

# Define the flow name from environment for consistency with trigger
FLOW_NAME = os.getenv("PREFECT_FLOW_NAME", "SST-Production-Pipeline")

# We define the task shell here. Prefect 3.x will match this by name 
# when it schedules the task to the worker pool.
# The worker implementation MUST have the same task name.
@task(name="process_single_album_task")
def process_single_album_task_shell(album_data: dict, config_dict: dict):
    """
    Shell task that will be executed by the worker.
    The implementation is provided by the worker component.
    """
    pass

@flow(name=FLOW_NAME)
def sst_main_flow(scout_results: List[dict]):
    """
    The main SST orchestration flow.
    This flow delegates the heavy lifting to the worker pool.
    """
    config = CoreConfig()
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, force=True)
    
    logger = get_run_logger()
    logger.info(f"SST Pipeline triggered for {len(scout_results)} albums.")

    config_dict = config.model_dump()
    env_mapping = {
        "s3_endpoint_url": "S3_ENDPOINT_URL",
        "s3_access_key": "S3_ACCESS_KEY",
        "s3_secret_key": "S3_SECRET_KEY",
        "s3_bucket_name": "S3_BUCKET_NAME",
        "musicbrainz_user_agent": "MUSICBRAINZ_USER_AGENT"
    }
    worker_config = {env_mapping.get(k, k): v for k, v in config_dict.items() if v is not None}

    # Map the shell task over all scout results.
    # Prefect handles the distribution to the worker pool.
    results = process_single_album_task_shell.map(
        scout_results,
        unmapped(worker_config)
    )
    
    logger.info(f"SST Pipeline scheduled {len(scout_results)} tasks to worker pool.")
    return results

def deploy():
    """Registers and serves the flow for the Prefect Server."""
    # In Prefect 3.x, .serve() hosts the flow directly.
    # It will poll for flow runs and delegate tasks to the 'sst-worker-pool'.
    print("Starting Prefect Flow Server...")
    sst_main_flow.serve(
        name="sst-decentralized-deployment",
    )

if __name__ == "__main__":
    deploy()
