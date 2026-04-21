import os
import logging
import json
import requests
from pathlib import Path
from typing import List, Optional, Any, Dict
from datetime import datetime

logger = logging.getLogger("scout.storage")

class WorkerStorage:
    """
    Handles file operations with SeaweedFS via Factual Filer API (HTTP).
    Bypasses S3 signature issues by using direct HTTP uploads/downloads.
    """
    def __init__(self, filer_url: str, bucket_name: str, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.filer_url = filer_url.rstrip('/')
        self.bucket_name = bucket_name
        self.base_path = f"buckets/{bucket_name}"
        # Filer might require basic auth if configured, but here we assume direct access or token
        self.auth = None
        if access_key and secret_key:
            # SeaweedFS Filer usually doesn't use S3 keys for HTTP, 
            # but we keep the structure for potential future auth.
            pass

    def _get_url(self, s3_key: str) -> str:
        return f"{self.filer_url}/{self.base_path}/{s3_key}"

    def download_file(self, s3_key: str, local_dest: Path) -> bool:
        """Downloads a file from Filer to a local temporary path."""
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        url = self._get_url(s3_key)
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(local_dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Downloaded via Filer: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to download {s3_key} from Filer: {e}")
            return False

    def upload_result(self, local_path: Path, status: str, app_id: int, rel_path: str) -> str:
        """Uploads the processed file to archive/ or review/ using Filer POST."""
        s3_key = f"{status}/{app_id}/{rel_path}"
        url = self._get_url(s3_key)
        try:
            with open(local_path, "rb") as f:
                # SeaweedFS Filer handles nested directories automatically on PUT/POST
                r = requests.put(url, data=f, timeout=300)
                r.raise_for_status()
            logger.info(f"Uploaded result via Filer: {s3_key}")
            return s3_key
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to Filer: {e}")
            raise

    def upload_json(self, data: dict, s3_key: str):
        """Uploads a dictionary as a JSON file via Filer."""
        url = self._get_url(s3_key)
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False)
            r = requests.put(url, data=content.encode("utf-8"), headers={"Content-Type": "application/json"}, timeout=60)
            r.raise_for_status()
            logger.info(f"Uploaded JSON via Filer: {s3_key}")
        except Exception as e:
            logger.error(f"Failed to upload JSON {s3_key} to Filer: {e}")

    def download_json(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """Downloads and parses a JSON file via Filer."""
        url = self._get_url(s3_key)
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 404: return None
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def upload_metadata(self, context: Any, status: str, app_id: int, file_refs: List[str], tracks_meta: List[Dict[str, Any]]):
        """Finalizes the album by uploading metadata.json including full track details."""
        metadata = {
            "app_id": app_id,
            "album_name": context.steam.name,
            "status": status,
            "processed_at": datetime.utcnow().isoformat(),
            "file_refs": file_refs,
            "tracks": tracks_meta,
            "steam_info": context.steam.model_dump()
        }
        s3_key = f"{status}/{app_id}/metadata.json"
        self.upload_json(metadata, s3_key)
        
    def list_objects(self, prefix: str) -> List[str]:
        """Lists objects under a prefix via Filer directory listing API."""
        url = f"{self.filer_url}/{self.base_path}/{prefix}/"
        try:
            # Filer returns JSON listing when requested with Accept: application/json
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            if r.status_code == 404: return []
            r.raise_for_status()
            data = r.json()
            # SeaweedFS Filer JSON format has 'Entries' list
            entries = data.get("Entries", [])
            return [f"{prefix}/{e['FullName'].lstrip('/')}" for e in entries]
        except Exception as e:
            logger.error(f"Failed to list Filer objects for {prefix}: {e}")
            return []
