import os
import vdf
import logging
import requests
import time
from typing import List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Target music extensions
MUSIC_EXTENSIONS = {".flac", ".wav", ".mp3", ".aiff", ".m4a"}

import json

class SteamScanner:
    def __init__(self, library_path: str, cache_path: str = "scout_cache.json", language: str = "japanese"):
        self.library_path = Path(library_path)
        self.cache_path = Path(cache_path)
        self.language = language
        self.cache = self._load_cache()
        
        # Strategy: Find where the .acf files actually are
        if (self.library_path / "steamapps").exists():
            self.steamapps_path = self.library_path / "steamapps"
        elif any(self.library_path.glob("*.acf")):
            self.steamapps_path = self.library_path
            self.library_path = self.library_path.parent
        else:
            # Fallback to default assumption
            self.steamapps_path = self.library_path / "steamapps"
            logger.warning(f"Could not find .acf files in {self.library_path} or its steamapps subdir.")

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {"ignored": [], "processed": {}}

    def _save_cache(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _resolve_install_path(self, installdir_name: str) -> Path:
        """Dynamically resolves the absolute path for an app's installation directory."""
        # Candidate 1: Modern Soundtracks (music folder)
        music_path = self.steamapps_path / "music" / installdir_name
        if music_path.exists():
            return music_path
            
        # Candidate 2: Legacy or Game-bundled Soundtracks (common folder)
        common_path = self.steamapps_path / "common" / installdir_name
        if common_path.exists():
            return common_path
            
        # Fallback: Assume common but log warning if not exists
        return common_path

    def find_soundtracks(self, force: bool = False, limit: Optional[int] = None, is_processed_callback: Optional[callable] = None, target_appid: Optional[int] = None) -> List[dict]:
        """
        Finds soundtrack app manifests (including DLCs) and fetches metadata.
        """
        if not self.steamapps_path.exists():
            logger.error(f"Steamapps directory not found: {self.steamapps_path}")
            return []

        soundtracks = []
        acf_files = list(self.steamapps_path.glob("*.acf"))
        logger.info(f"Found {len(acf_files)} ACF files. Scanning for soundtracks (including DLCs)...")

        for acf_file in acf_files:
            if limit and len(soundtracks) >= limit:
                logger.info(f"Reached limit of {limit} active soundtracks. Stopping scan.")
                break

            manifest = self._parse_acf(acf_file)
            if not manifest: continue
            
            app_state = manifest.get("AppState", {})
            parent_appid = int(app_state.get("appid", 0))
            last_updated = app_state.get("LastUpdated", "0")
            
            # --- Check 1: Is this ACF itself the target (or a soundtrack)? ---
            potential_ids = [parent_appid]
            
            # --- Check 2: Does this ACF contain the target as a DLC? ---
            depots = app_state.get("InstalledDepots", {})
            for d_id, d_data in depots.items():
                dlc_id = d_data.get("dlcappid")
                if dlc_id: potential_ids.append(int(dlc_id))

            for current_id in potential_ids:
                # Filter by specific AppID if requested
                if target_appid and current_id != target_appid:
                    continue
                
                # If target_appid is NOT set, only process if it's a known soundtrack type
                if not target_appid and not self._is_soundtrack(manifest) and current_id == parent_appid:
                    continue

                if not force and is_processed_callback and is_processed_callback(current_id):
                    logger.debug(f"Skipping already processed app: {current_id}")
                    continue

                # It's a valid candidate!
                cached_data = self.cache["processed"].get(str(current_id))
                if not force and cached_data:
                    cached_last_updated = cached_data.get("last_updated_acf", "0")
                    if int(last_updated) > int(cached_last_updated):
                        logger.info(f"Steam update detected for AppID {current_id}. Invalidating cache.")
                    else:
                        logger.info(f"Using cached metadata for AppID {current_id}")
                        ost_data = cached_data.copy()
                        ost_data["app_id"] = current_id
                        ost_data["install_dir"] = str(self._resolve_install_path(app_state.get("installdir", "")))
                        soundtracks.append(ost_data)
                        continue

                # Fetch fresh metadata
                enriched = self.fetch_steam_metadata(current_id, self.language)
                if not enriched: continue

                ost_info = {
                    "app_id": current_id,
                    "name": enriched.get("name", app_state.get("name", "Unknown")),
                    "install_dir": str(self._resolve_install_path(app_state.get("installdir", ""))),
                    "developer": enriched.get("developer"),
                    "publisher": enriched.get("publisher"),
                    "genre": enriched.get("genre"),
                    "tags": enriched.get("tags", []),
                    "release_date": enriched.get("release_date"),
                    "parent_app_id": enriched.get("parent_app_id") or (parent_appid if current_id != parent_appid else None),
                    "parent_name": enriched.get("parent_name") or (app_state.get("name") if current_id != parent_appid else None),
                    "parent_tags": enriched.get("parent_tags", []),
                    "parent_genre": enriched.get("parent_genre"),
                    "parent_release_date": enriched.get("parent_release_date"),
                    "url": f"https://store.steampowered.com/app/{current_id}",
                    "acf_path": str(acf_file),
                    "last_updated_acf": last_updated
                }
                
                self.cache["processed"][str(current_id)] = ost_info.copy()
                soundtracks.append(ost_info)
                time.sleep(2.0)
                if limit and len(soundtracks) >= limit: break
        
        logger.info(f"Scan complete. Found {len(soundtracks)} active apps to process.")
        self._save_cache()
        return soundtracks

    def fetch_steam_metadata(self, app_id: int, language: str = "japanese", is_parent: bool = False) -> dict:
        """
        Fetches metadata with backoff strategy for 429 errors.
        Falls back from specified language to English if needed.
        """
        languages = [language, "english"] if language != "english" else ["english"]
        
        for lang in languages:
            backoff_delays = [60, 180, 300, 600] # 1m, 3m, 5m, 10m
            for attempt, delay in enumerate(backoff_delays + [None]):
                url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l={lang}"
                try:
                    response = requests.get(url, timeout=15)
                    
                    if response.status_code == 429:
                        if delay is None:
                            logger.error(f"Steam API 429 limit exceeded even after retries for {app_id}")
                            return {}
                        logger.warning(f"Steam API 429 detected for {app_id}. Waiting {delay}s (Attempt {attempt+1})...")
                        time.sleep(delay)
                        continue # Retry same language
                    
                    if response.status_code != 200:
                        logger.warning(f"Steam API returned {response.status_code} for {app_id}")
                        break # Try next language

                    data = response.json()
                    if data and data.get(str(app_id), {}).get("success"):
                        info = data[str(app_id)]["data"]
                        
                        metadata = {
                            "name": info.get("name"),
                            "developer": ", ".join(info.get("developers", [])),
                            "publisher": ", ".join(info.get("publishers", [])),
                            "genre": info.get("genres", [{}])[0].get("description") if info.get("genres") else None,
                            "tags": [g.get("description") for g in info.get("genres", [])],
                            "release_date": info.get("release_date", {}).get("date"),
                            "header_image_url": info.get("header_image"),
                            "parent_app_id": info.get("fullgame", {}).get("appid")
                        }

                        # If it's a soundtrack and we have a parent, fetch parent for more tags/genres/name
                        if not is_parent and metadata.get("parent_app_id"):
                            parent_id = int(metadata["parent_app_id"])
                            logger.info(f"Fetching parent game metadata for soundtrack {app_id} (Parent: {parent_id})")
                            parent_meta = self.fetch_steam_metadata(parent_id, lang, is_parent=True)
                            
                            if parent_meta:
                                metadata["parent_name"] = parent_meta.get("name")
                                metadata["parent_tags"] = parent_meta.get("tags", [])
                                metadata["parent_genre"] = parent_meta.get("genre")
                                metadata["parent_release_date"] = parent_meta.get("release_date")
                                # Fallback developer/publisher if missing in soundtrack
                                if not metadata["developer"]:
                                    metadata["developer"] = parent_meta.get("developer")
                                if not metadata["publisher"]:
                                    metadata["publisher"] = parent_meta.get("publisher")
                        
                        logger.info(f"Successfully fetched Steam metadata for {app_id} in {lang}")
                        return metadata
                    else:
                        logger.warning(f"Steam API returned success=False for {app_id} in {lang}")
                        break # Try next language (English)
                
                except Exception as e:
                    logger.warning(f"Failed to fetch Steam API for {app_id}: {e}")
                    break
        return {}

    def _parse_acf(self, path: Path) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return vdf.load(f)
        except Exception as e:
            logger.error(f"Failed to parse ACF {path}: {e}")
            return None

    def _is_soundtrack(self, manifest: dict) -> bool:
        """Determines if the manifest belongs to a soundtrack app."""
        app_state = manifest.get("AppState", {})
        
        # Criteria 1: contenttype == '3' (Music)
        user_config = app_state.get("UserConfig", {})
        if user_config.get("contenttype") == "3":
            return True
            
        # Criteria 2: Name fallback
        app_name = app_state.get("name", "").lower()
        if "soundtrack" in app_name or " ost" in app_name:
            return True
            
        return False

    def collect_music_files(self, install_dir: str) -> List[Path]:
        """Collects music files from 'common/' or 'music/' directories."""
        # Check both potential locations
        search_paths = [
            self.steamapps_path / "common" / install_dir,
            self.steamapps_path / "music" / install_dir,
        ]

        music_files = []
        found_dir = None
        for path in search_paths:
            if path.exists() and path.is_dir():
                found_dir = path
                break
        
        if not found_dir:
            logger.warning(f"Install directory not found for {install_dir} in common/ or music/")
            return []

        for root, dirs, files in os.walk(found_dir):
            # Ignore __MACOSX directories
            if "__MACOSX" in dirs:
                dirs.remove("__MACOSX")

            for file in files:
                # Ignore hidden files and macOS resource forks (._*)
                if file.startswith("."):
                    continue
                
                file_path = Path(root) / file
                if file_path.suffix.lower() in MUSIC_EXTENSIONS:
                    music_files.append(file_path)
        
        return music_files

    def get_relative_path(self, file_path: Path, install_dir: str) -> Path:
        """Calculates path relative to the soundtrack root."""
        # Try common/ and music/ roots
        for prefix in ["common", "music"]:
            root = self.steamapps_path / prefix / install_dir
            try:
                return file_path.relative_to(root)
            except ValueError:
                continue
        return file_path.name # Fallback
