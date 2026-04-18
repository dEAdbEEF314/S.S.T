import os
import json
import logging
import asyncio
from typing import List, Dict, Optional

from prefect import flow, task, get_run_logger
from prefect.deployments import run_deployment
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

@flow(name=FLOW_NAME)
async def sst_main_flow(scout_results: List[dict]):
    """
    The main SST orchestration flow.
    This flow triggers remote worker flows via run_deployment.
    """
    config = CoreConfig()
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, force=True)
    
    logger = get_run_logger()
    logger.info(f"SST Pipeline triggered for {len(scout_results)} albums.")

    config_dict = config.model_dump()
    env_mapping = {
        "S3_ENDPOINT_URL": config.s3_endpoint_url,
        "S3_ACCESS_KEY": config.s3_access_key,
        "S3_SECRET_KEY": config.s3_secret_key,
        "S3_BUCKET_NAME": config.s3_bucket_name,
        "MUSICBRAINZ_USER_AGENT": config.musicbrainz_user_agent,
        "LOG_LEVEL": config.log_level
    }

    # Trigger each album processing in the worker pool concurrently
    for album in scout_results:
        logger.info(f"Triggering worker for App ID {album.get('app_id')}...")
        flow_run = await run_deployment(
            name="sst-worker-flow/sst-worker-deployment",
            parameters={
                "scout_data": album,
                "config_dict": env_mapping
            },
            timeout=0 # Don't wait for flow to FINISH, but wait for it to be CREATED
        )
        logger.info(f"Successfully created sub-flow run: {flow_run.id}")
    
    logger.info(f"SST Pipeline delegated {len(scout_results)} albums to worker deployments.")

def deploy():
    """Registers and serves the flow for the Prefect Server."""
    print("Starting SST Core Flow Server...")
    sst_main_flow.serve(
        name="sst-decentralized-deployment",
    )

if __name__ == "__main__":
    deploy()
