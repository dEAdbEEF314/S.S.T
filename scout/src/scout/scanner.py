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

class SteamScanner:
    def __init__(self, library_path: str, language: str = "japanese"):
        self.library_path = Path(library_path)
        self.language = language
        
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

    def find_soundtracks(self) -> List[dict]:
        """Finds soundtrack app manifests in the library."""
        if not self.steamapps_path.exists():
            logger.error(f"Steamapps directory not found: {self.steamapps_path}")
            return []

        soundtracks = []
        for acf_file in self.steamapps_path.glob("*.acf"):
            manifest = self._parse_acf(acf_file)
            if manifest and self._is_soundtrack(manifest):
                app_state = manifest.get("AppState", {})
                app_id = int(app_state.get("appid", 0))
                
                # Fetch enriched metadata from Store API
                enriched = self.fetch_steam_metadata(app_id, self.language)
                
                soundtracks.append({
                    "app_id": app_id,
                    "name": app_state.get("name", ""),
                    "install_dir": app_state.get("installdir", ""),
                    "developer": enriched.get("developer"),
                    "publisher": enriched.get("publisher"),
                    "genre": enriched.get("genre"),
                    "tags": enriched.get("tags", []),
                    "url": f"https://store.steampowered.com/app/{app_id}",
                    "acf_path": acf_file
                })
                # Base delay to be kind to the API
                time.sleep(2.0)
        return soundtracks

    def fetch_steam_metadata(self, app_id: int, language: str = "japanese") -> dict:
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
                            "developer": ", ".join(info.get("developers", [])),
                            "publisher": ", ".join(info.get("publishers", [])),
                            "genre": info.get("genres", [{}])[0].get("description") if info.get("genres") else None,
                            "tags": [g.get("description") for g in info.get("genres", [])]
                        }

                        # If basic info is missing, try to fetch from parent game
                        if not metadata["developer"] and "fullgame" in info:
                            parent_id = info["fullgame"].get("appid")
                            if parent_id:
                                logger.info(f"Metadata missing for soundtrack {app_id}, falling back to parent {parent_id}")
                                return self.fetch_steam_metadata(int(parent_id), lang)
                        
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
