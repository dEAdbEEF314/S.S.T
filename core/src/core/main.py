import os
import json
import logging
from typing import List, Dict, Optional

from prefect import flow, task, get_run_logger, unmapped
from pydantic_settings import BaseSettings, SettingsConfigDict


# Instead of importing worker logic directly, we define tasks that will be executed by the worker.
# We map these to the actual functions available in the worker's environment.

class CoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    musicbrainz_user_agent: Optional[str] = None
    log_level: str = "INFO"

# Define the flow. The actual worker task logic will be defined in the worker repository
# and registered with Prefect. For simplicity, we assume the task 'process_single_album_task'
# is already known to Prefect via the Worker.

@flow(name="SST-Production-Pipeline")
def sst_main_flow(scout_results: List[dict]):
    """
    The main SST orchestration flow.
    This flow delegates the heavy lifting to the worker pool.
    """
    logger = get_run_logger()
    logger.info(f"SST Pipeline triggered for {len(scout_results)} albums.")

    # Since we are fully decentralized, the best approach is to trigger
    # a deployment for each album, or map over a task that runs on the worker pool.
    
    # We will dynamically import the task definition so Prefect knows its signature,
    # but execution will happen on the worker.
    from worker.main import process_single_album_task
    
    config = CoreConfig()
    config_dict = config.model_dump(by_alias=True)
    env_mapping = {
        "s3_endpoint_url": "S3_ENDPOINT_URL",
        "s3_access_key": "S3_ACCESS_KEY",
        "s3_secret_key": "S3_SECRET_KEY",
        "s3_bucket_name": "S3_BUCKET_NAME",
        "musicbrainz_user_agent": "MUSICBRAINZ_USER_AGENT"
    }
    worker_config = {env_mapping.get(k, k): v for k, v in config_dict.items() if v is not None}

    from prefect import unmapped
    futures = process_single_album_task.map(scout_results, config_dict=unmapped(worker_config))

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

def deploy():
    """Registers the flow with Prefect Server."""
    deployment = Deployment.build_from_flow(
        flow=sst_main_flow,
        name="sst-decentralized-deployment",
        work_pool_name="sst-worker-pool",
    )
    deployment.apply()
    print("Deployment registered successfully.")

if __name__ == "__main__":
    deploy()
