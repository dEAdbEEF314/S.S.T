import requests
import logging
import io
import json
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("ui.s3_service")

class S3UIService:
    """
    Handles file operations with SeaweedFS via Factual Filer API (HTTP) for the UI.
    Bypasses S3 signature issues for robust listing and ZIP generation.
    """
    def __init__(self, filer_url: str, bucket_name: str, access_key: str = None, secret_key: str = None):
        self.filer_url = filer_url.rstrip('/')
        self.bucket = bucket_name
        self.base_path = f"buckets/{bucket_name}"
        self.jst = timezone(timedelta(hours=9), 'JST')

    def _get_url(self, key: str) -> str:
        return f"{self.filer_url}/{self.base_path}/{key}"

    def list_albums(self, status: str) -> List[Dict[str, Any]]:
        """Lists unique albums in archive/ or review/ by scanning Filer directories."""
        url = f"{self.filer_url}/{self.base_path}/{status}/"
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            if r.status_code == 404: return []
            r.raise_for_status()
            
            data = r.json()
            app_ids = []
            for entry in data.get("Entries") or []:
                full_path = entry.get("FullPath") or entry.get("fullpath")
                if full_path:
                    name = Path(full_path).name
                    if name.isdigit():
                        app_ids.append(name)

            albums = []
            for app_id in app_ids:
                album_info = self._get_album_details(status, app_id)
                if album_info:
                    albums.append(album_info)
            
            # Sort by processing time (newest first)
            albums.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
            return albums
        except Exception as e:
            logger.error(f"Failed to list albums via Filer: {e}")
            return []

    def _get_album_details(self, status: str, app_id: str) -> Optional[Dict[str, Any]]:
        """Fetches metadata.json and calculates track stats via Filer API."""
        meta_url = self._get_url(f"{status}/{app_id}/metadata.json")
        dir_url = self._get_url(f"{status}/{app_id}/")
        
        try:
            # 1. Fetch Metadata
            r_meta = requests.get(meta_url, timeout=10)
            meta = {}
            if r_meta.status_code == 200:
                meta = r_meta.json()
            
            # 2. List Directory for stats
            r_dir = requests.get(dir_url, headers={"Accept": "application/json"}, timeout=10)
            if r_dir.status_code != 200: return None
            dir_data = r_dir.json()
            
            audio_exts = {'.flac', '.mp3', '.aiff', '.wav'}
            total_size = 0
            audio_count = 0
            
            # Recursively count files
            def count_entries(entries):
                size, count = 0, 0
                for entry in entries:
                    is_dir = entry.get("Mode", 0) & (1 << 31)
                    entry_name = Path(entry.get("FullPath", "")).name
                    if is_dir:
                        sub_r = requests.get(f"{dir_url}{entry_name}/", headers={"Accept": "application/json"}, timeout=10)
                        if sub_r.status_code == 200:
                            s, c = count_entries(sub_r.json().get("Entries") or [])
                            size += s
                            count += c
                    else:
                        size += entry.get("FileSize") or entry.get("file_size") or 0
                        if any(entry_name.lower().endswith(ext) for ext in audio_exts):
                            count += 1
                return size, count

            total_size, audio_count = count_entries(dir_data.get("Entries") or [])

            # --- Fix: Timezone Conversion (UTC to JST) ---
            processed_at_raw = meta.get("processed_at", "")
            processed_at_jst = ""
            if processed_at_raw:
                try:
                    dt_utc = datetime.fromisoformat(processed_at_raw.replace('Z', '+00:00'))
                    processed_at_jst = dt_utc.astimezone(self.jst).isoformat()
                except:
                    processed_at_jst = processed_at_raw

            steam_info = meta.get("steam_info", {})
            
            # --- Fix: Metadata Inspector Blank Issue ---
            # Ensure tracks information is robustly passed
            tracks = meta.get("tracks") or []

            return {
                "app_id": app_id,
                "name": meta.get("album_name") or steam_info.get("name") or f"App {app_id}",
                "developer": steam_info.get("developer") or "Unknown",
                "publisher": steam_info.get("publisher") or "Unknown",
                "url": steam_info.get("url") or f"https://store.steampowered.com/app/{app_id}",
                "vgmdb_url": meta.get("external_info", {}).get("vgmdb_url"),
                "track_count": audio_count,
                "size_bytes": total_size,
                "processed_at": processed_at_jst,
                "status": status,
                "tracks": tracks,
                "is_ready": True
            }
        except Exception as e:
            logger.warning(f"Failed to get details for {app_id}: {e}")
            return None

    def delete_album(self, status: str, app_id: str):
        """Deletes prefix via Filer recursive delete."""
        url = self._get_url(f"{status}/{app_id}/") + "?recursive=true"
        try:
            r = requests.delete(url, timeout=60)
            r.raise_for_status()
            logger.info(f"Deleted album {app_id} via Filer")
        except Exception as e:
            logger.error(f"Failed to delete album {app_id}: {e}")
            raise

    def move_album(self, app_id: str, from_status: str, to_status: str):
        """Moves album by renaming the directory in Filer."""
        # Use simple URL structure for mv command
        source_path = f"/{self.base_path}/{from_status}/{app_id}"
        target_path = f"/{self.base_path}/{to_status}/{app_id}"
        
        # Fixed URL: Ensure no double slashes and correct param
        url = f"{self.filer_url}{source_path}?mv={target_path}"
        try:
            r = requests.post(url, timeout=60)
            r.raise_for_status()
            logger.info(f"Moved album {app_id} from {from_status} to {to_status} via Filer mv")
        except Exception as e:
            logger.error(f"Failed to move album {app_id}: {e}")
            raise

    def create_zip_stream(self, status: str, app_id: str):
        """Creates a ZIP of the album by downloading files from Filer."""
        dir_url = self._get_url(f"{status}/{app_id}/")
        buffer = io.BytesIO()
        audio_exts = {'.aiff', '.mp3', '.acf', '.json'}

        try:
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                def add_entries(current_url, rel_prefix=""):
                    r_sub = requests.get(current_url, headers={"Accept": "application/json"}, timeout=20)
                    if r_sub.status_code != 200: return
                    for entry in r_sub.json().get("Entries") or []:
                        full_path = entry.get("FullPath") or entry.get("fullpath")
                        if not full_path: continue
                        entry_name = Path(full_path).name
                        is_dir = entry.get("Mode", 0) & (1 << 31)
                        
                        if is_dir:
                            add_entries(f"{current_url}{entry_name}/", f"{rel_prefix}{entry_name}/")
                        else:
                            if any(entry_name.lower().endswith(ext) for ext in audio_exts):
                                # Optimized: Stream content to zip instead of full download first
                                r_file = requests.get(f"{current_url}{entry_name}", stream=True, timeout=60)
                                zip_file.writestr(f"{rel_prefix}{entry_name}", r_file.content)

                add_entries(dir_url)
        except Exception as e:
            logger.error(f"Failed to create ZIP for {app_id}: {e}")
            raise

        buffer.seek(0)
        return buffer

    def download_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Downloads a JSON file via Filer."""
        url = self._get_url(key)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return None
