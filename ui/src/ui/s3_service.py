import boto3
import logging
import io
import json
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError
from datetime import datetime

logger = logging.getLogger(__name__)

class S3UIService:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket_name: str, region: str = "us-east-1"):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.bucket = bucket_name

    def list_albums(self, status: str) -> List[Dict[str, Any]]:
        """Lists unique albums in archive/ or review/ using metadata.json."""
        prefix = f"{status}/"
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            app_ids = set()
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter='/'):
                for cp in page.get('CommonPrefixes', []):
                    app_id = cp['Prefix'].replace(prefix, "").strip('/')
                    if app_id.isdigit():
                        app_ids.add(app_id)

            albums = []
            for app_id in app_ids:
                album_info = self._get_album_details(status, app_id)
                if album_info: # Only add if metadata.json exists and is valid
                    albums.append(album_info)
            
            # Sort by processing time (newest first)
            albums.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
            return albums
        except ClientError as e:
            logger.error(f"Failed to list S3 objects: {e}")
            return []

    def _get_album_details(self, status: str, app_id: str) -> Optional[Dict[str, Any]]:
        """Fetches metadata.json and checks consistency."""
        meta_key = f"{status}/{app_id}/metadata.json"
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=meta_key)
            meta = json.loads(resp['Body'].read().decode('utf-8'))
            
            # Basic validation: check if tracks exist
            prefix = f"{status}/{app_id}/"
            objs = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=1000)
            contents = objs.get('Contents', [])
            
            audio_files = [obj for obj in contents if any(obj['Key'].endswith(ext) for ext in ['.aiff', '.mp3'])]
            
            # If metadata says 20 tracks but we see only 5, it's not ready
            if len(audio_files) < len(meta.get("tracks", [])):
                logger.warning(f"Album {app_id} metadata/file count mismatch. Skipping.")
                return None

            return {
                "app_id": app_id,
                "name": meta.get("album_name", f"App {app_id}"),
                "developer": meta.get("steam_info", {}).get("developer"),
                "publisher": meta.get("steam_info", {}).get("publisher"),
                "url": meta.get("steam_info", {}).get("url"),
                "vgmdb_url": meta.get("external_info", {}).get("vgmdb_url"),
                "track_count": len(audio_files),
                "processed_at": meta.get("processed_at"),
                "status": status,
                "tracks": meta.get("tracks", []),
                "is_ready": True
            }
        except ClientError:
            return None # metadata.json not found or inaccessible

    def create_zip_stream(self, status: str, app_id: str):
        """Creates an on-the-fly ZIP stream of the album."""
        prefix = f"{status}/{app_id}/"
        buffer = io.BytesIO()
        
        # Get metadata to name the ZIP nicely
        details = self._get_album_details(status, app_id)
        album_name = details["name"] if details else str(app_id)

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Include audio and acf and metadata.json
                    if any(key.endswith(ext) for ext in ['.aiff', '.mp3', '.acf', '.json']):
                        file_data = self.s3.get_object(Bucket=self.bucket, Key=key)['Body'].read()
                        rel_path = key.replace(prefix, "")
                        zip_file.writestr(rel_path, file_data)
        
        buffer.seek(0)
        return buffer
