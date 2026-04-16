import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from worker.main import WorkerService
from worker.models import WorkerInput, SteamMetadata

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker-test")

def test_worker_run(app_id: int, files: list, name: str, developer: str, publisher: str):
    load_dotenv()
    
    config = {
        "S3_ENDPOINT_URL": os.getenv("S3_ENDPOINT_URL"),
        "S3_ACCESS_KEY": os.getenv("S3_ACCESS_KEY"),
        "S3_SECRET_KEY": os.getenv("S3_SECRET_KEY"),
        "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
        "MUSICBRAINZ_USER_AGENT": os.getenv("MUSICBRAINZ_USER_AGENT")
    }

    service = WorkerService(config)
    
    input_data = WorkerInput(
        app_id=app_id,
        files=files,
        steam=SteamMetadata(
            app_id=app_id, 
            name=name,
            developer=developer,
            publisher=publisher,
            url=f"https://store.steampowered.com/app/{app_id}"
        )
    )
    
    logger.info(f"--- Starting Final Worker Test for {name} ({app_id}) ---")
    result = service.process_job(input_data)
    
    print("--- WORKER RESULT ---")
    print(result.model_dump_json(indent=2))
    print("----------------------")

if __name__ == "__main__":
    app_id = 1040700
    name = "Devil Engine Original Soundtrack"
    
    # Values successfully fetched by Scout API test
    developer = "Protoculture Games"
    publisher = "Poppy Works"
    
    files = [
        f"ingest/{app_id}/01 - Re-Boot (OP DEMO).flac",
        f"ingest/{app_id}/Re-Boot (OP DEMO).mp3",
        f"ingest/{app_id}/23 - コモドールは十字架に磔られました (OMAKE).flac"
    ]
    
    test_worker_run(app_id, files, name, developer, publisher)
