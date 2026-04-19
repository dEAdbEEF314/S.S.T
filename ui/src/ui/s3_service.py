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
        """Fetches metadata.json and checks consistency, including total size."""
        meta_key = f"{status}/{app_id}/metadata.json"
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=meta_key)
            meta = json.loads(resp['Body'].read().decode('utf-8'))
            
            prefix = f"{status}/{app_id}/"
            objs = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            contents = objs.get('Contents', [])
            
            # Calculate total size in bytes
            total_size = sum(obj.get('Size', 0) for obj in contents)
            
            audio_files = [obj for obj in contents if any(obj['Key'].lower().endswith(ext) for ext in ['.flac', '.mp3', '.aiff', '.wav'])]
            
            # Basic validation: ensure we see at least some files
            if not audio_files and status != "ingest":
                logger.warning(f"Album {app_id} in {status} has no audio files. Skipping.")
                return None

            return {
                "app_id": app_id,
                "name": meta.get("album_name", f"App {app_id}"),
                "developer": meta.get("steam_info", {}).get("developer"),
                "publisher": meta.get("steam_info", {}).get("publisher"),
                "url": meta.get("steam_info", {}).get("url"),
                "vgmdb_url": meta.get("external_info", {}).get("vgmdb_url"),
                "track_count": len(audio_files),
                "size_bytes": total_size,
                "processed_at": meta.get("processed_at"),
                "status": status,
                "tracks": meta.get("tracks", []),
                "is_ready": True
            }
        except ClientError:
            return None

    def delete_album(self, status: str, app_id: str):
        """Deletes all objects under status/app_id/ prefix."""
        prefix = f"{status}/{app_id}/"
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    delete_keys = [{'Key': obj['Key']} for obj in page['Contents']]
                    self.s3.delete_objects(Bucket=self.bucket, Delete={'Objects': delete_keys})
            logger.info(f"Deleted album {app_id} from {status}")
        except Exception as e:
            logger.error(f"Failed to delete album {app_id}: {e}")
            raise

    def move_album(self, app_id: str, from_status: str, to_status: str):
        """Moves all objects from one status prefix to another."""
        source_prefix = f"{from_status}/{app_id}/"
        target_prefix = f"{to_status}/{app_id}/"
        
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=source_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        source_key = obj['Key']
                        target_key = source_key.replace(source_prefix, target_prefix, 1)
                        
                        # Copy
                        self.s3.copy_object(
                            Bucket=self.bucket,
                            CopySource={'Bucket': self.bucket, 'Key': source_key},
                            Key=target_key
                        )
            
            # After copying everything, delete the source
            self.delete_album(from_status, app_id)
            logger.info(f"Moved album {app_id} from {from_status} to {to_status}")
            
        except Exception as e:
            logger.error(f"Failed to move album {app_id}: {e}")
            raise

    def create_zip_stream(self, status: str, app_id: str):
        """Creates an on-the-fly ZIP stream of the album including audio files."""
        prefix = f"{status}/{app_id}/"
        buffer = io.BytesIO()
        
        # Audio and metadata extensions to include per specification
        audio_exts = ['.aiff', '.mp3', '.acf', '.json']

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if any(key.lower().endswith(ext) for ext in audio_exts):
                            file_data = self.s3.get_object(Bucket=self.bucket, Key=key)['Body'].read()
                            rel_path = key.replace(prefix, "")
                            zip_file.writestr(rel_path, file_data)
        
        buffer.seek(0)
        return buffer
