import boto3
import os
import logging
from pathlib import Path
from typing import List
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class WorkerStorage:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket_name: str, region: str = "us-east-1"):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.bucket_name = bucket_name

    def download_file(self, s3_key: str, local_dest: Path) -> bool:
        """Downloads a file from S3 to a local temporary path."""
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.s3_client.download_file(self.bucket_name, s3_key, str(local_dest))
            logger.debug(f"Downloaded: {s3_key} -> {local_dest}")
            return True
        except ClientError as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            return False

    def upload_result(self, local_path: Path, status: str, app_id: int, rel_path: str) -> str:
        """
        Uploads the processed file to archive/ or review/.
        :param status: 'success' (archive) or 'review'
        """
        prefix = "archive" if status == "success" else "review"
        s3_key = f"{prefix}/{app_id}/{rel_path}"
        
        try:
            self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
            logger.info(f"Uploaded result: {s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Failed to upload result {local_path}: {e}")
            raise

    def delete_ingest_file(self, s3_key: str):
        """Cleanup: Deletes the original ingest file after successful processing."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.debug(f"Deleted ingest file: {s3_key}")
        except ClientError as e:
            logger.warning(f"Failed to delete ingest file {s3_key}: {e}")
