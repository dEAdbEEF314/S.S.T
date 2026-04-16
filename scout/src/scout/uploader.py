import boto3
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class S3Uploader:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket_name: str, region: Optional[str] = None):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region or "us-east-1"
        )
        self.bucket_name = bucket_name

    def upload_files(self, app_id: int, files: List[Tuple[Path, Path]]) -> List[str]:
        """
        Uploads files to S3.
        :param app_id: Steam App ID
        :param files: List of (Local Path, Relative Path)
        :return: List of S3 keys (ingest/{app_id}/...)
        """
        uploaded_keys = []
        for local_path, rel_path in files:
            s3_key = f"ingest/{app_id}/{rel_path.as_posix()}"
            try:
                self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
                uploaded_keys.append(s3_key)
                logger.debug(f"Uploaded: {local_path} -> {s3_key}")
            except ClientError as e:
                logger.error(f"Failed to upload {local_path}: {e}")
        
        return uploaded_keys

    def check_exists(self, app_id: int) -> bool:
        """Checks if metadata.json exists in either archive/ or review/ folders."""
        for prefix in ["archive", "review"]:
            key = f"{prefix}/{app_id}/metadata.json"
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                return True
            except ClientError:
                continue
        return False
