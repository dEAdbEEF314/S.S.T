import os
import vdf
import logging
import requests
import time
import json
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from .utils import ensure_wsl_path
from .steam_vdf import SteamBinaryVDF, SteamLibraryDiscovery

logger = logging.getLogger(__name__)

# Target music extensions
MUSIC_EXTENSIONS = {".flac", ".wav", ".mp3", ".aiff", ".m4a"}

class SteamScanner:
    def __init__(self, install_path: str, override_library_path: Optional[str] = None, cache_path: str = "data/scout_cache.json", language: str = "japanese"):
        self.install_path = ensure_wsl_path(install_path)
        self.cache_path = Path(cache_path)
        self.language = language
        self.cache = self._load_cache()
        
        # 1. Discover all libraries
        self.library_paths = self._discover_all_libraries(override_library_path)
        
        # 2. Pre-load appinfo metadata (Offline dictionary)
        self.appinfo_dict = self._load_appinfo()
        logger.info(f"Initialized SteamScanner with {len(self.library_paths)} libraries and {len(self.appinfo_dict)} apps in local cache.")

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load scout cache: {e}")
        return {"ignored": [], "processed": {}}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save scout cache: {e}")

    def _discover_all_libraries(self, override_path: Optional[str]) -> List[Path]:
        """Discovers all Steam library folders, optionally restricted by override_path."""
        if override_path:
            p = ensure_wsl_path(override_path)
            if (p / "steamapps").exists():
                return [p / "steamapps"]
            return [p]

        raw_folders = SteamLibraryDiscovery.discover(self.install_path)
        discovered = []
        for rf in raw_folders:
            p = ensure_wsl_path(rf)
            if (p / "steamapps").exists():
                discovered.append(p / "steamapps")
            else:
                discovered.append(p)
        
        # Always include the primary install library if not in list
        primary = self.install_path / "steamapps"
        if primary not in discovered:
            discovered.append(primary)
            
        return discovered

    def _load_appinfo(self) -> Dict[int, Dict[str, Any]]:
        """Loads and parses the binary appinfo.vdf for instant metadata access."""
        vdf_path = self.install_path / "appcache" / "appinfo.vdf"
        if not vdf_path.exists():
            logger.warning(f"appinfo.vdf not found. Falling back to web API is disabled in Act-15.")
            return {}
        return SteamBinaryVDF.parse_appinfo(vdf_path)

    def _resolve_install_path(self, library_root: Path, installdir_name: str) -> Path:
        """Resolves the absolute path for an app's installation directory within a library."""
        # Candidate 1: Modern Soundtracks (music folder)
        music_path = library_root / "music" / installdir_name
        if music_path.exists(): return music_path
            
        # Candidate 2: Legacy or Game-bundled Soundtracks (common folder)
        common_path = library_root / "common" / installdir_name
        if common_path.exists(): return common_path
            
        return common_path

    def find_soundtracks(self, force: bool = False, limit: Optional[int] = None, is_processed_callback: Optional[callable] = None, target_appid: Optional[int] = None) -> List[dict]:
        """
        Finds soundtrack app manifests and merges them with local appinfo metadata.
        """
        soundtracks = []
        
        # Scan all libraries for .acf files
        all_acf_files = []
        for lib in self.library_paths:
            if lib.exists():
                all_acf_files.extend(list(lib.glob("*.acf")))

        logger.info(f"Found {len(all_acf_files)} ACF files across {len(self.library_paths)} libraries.")

        for acf_file in all_acf_files:
            if limit and len(soundtracks) >= limit: break

            manifest = self._parse_acf(acf_file)
            if not manifest: continue
            
            app_state = manifest.get("AppState", {})
            parent_appid = int(app_state.get("appid", 0))
            last_updated = app_state.get("LastUpdated", "0")
            library_root = acf_file.parent # The root containing common/music/workshop
            
            # Check for main app and DLCs
            potential_ids = [parent_appid]
            depots = app_state.get("InstalledDepots", {})
            for d_id, d_data in depots.items():
                dlc_id = d_data.get("dlcappid")
                if dlc_id: potential_ids.append(int(dlc_id))

            for current_id in potential_ids:
                if target_appid and current_id != target_appid: continue
                
                # If target_appid is NOT set, only process if it's a known soundtrack
                if not target_appid and not self._is_soundtrack(manifest, current_id) and current_id == parent_appid:
                    continue

                if not force and is_processed_callback and is_processed_callback(current_id):
                    continue

                # Get Local Metadata (Instant)
                enriched = self._get_local_metadata(current_id)
                if not enriched and not target_appid:
                    # If we can't find metadata locally and it wasn't a targeted scan, skip
                    continue

                ost_info = {
                    "app_id": current_id,
                    "name": enriched.get("name") or app_state.get("name", f"App {current_id}"),
                    "install_dir": str(self._resolve_install_path(library_root, app_state.get("installdir", ""))),
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
                    "header_image_url": enriched.get("header_image_url"),
                    "acf_path": str(acf_file),
                    "last_updated_acf": last_updated
                }
                
                soundtracks.append(ost_info)
                if limit and len(soundtracks) >= limit: break
        
        logger.info(f"Scan complete. Found {len(soundtracks)} soundtracks to process.")
        return soundtracks

    def _get_local_metadata(self, app_id: int) -> dict:
        """Extracts metadata from the local appinfo dictionary."""
        data = self.appinfo_dict.get(app_id)
        if not data: return {}

        common = data.get("common", {})
        extended = data.get("extended", {})
        
        metadata = {
            "name": common.get("name"),
            "developer": extended.get("developer"),
            "publisher": extended.get("publisher"),
            "genre": None,
            "tags": [],
            "release_date": None,
            "header_image_url": None,
            "parent_app_id": common.get("parent") or common.get("fullgameid")
        }

        # Handle Genres/Tags from local data
        genres_data = common.get("genres", {})
        if genres_data:
            # Usually it's a list of indices or objects
            if isinstance(genres_data, dict):
                metadata["tags"] = [g.get("name") for g in genres_data.values() if isinstance(g, dict) and "name" in g]
            elif isinstance(genres_data, list):
                metadata["tags"] = [g.get("name") for g in genres_data if isinstance(g, dict) and "name" in g]
        
        if metadata["tags"]:
            metadata["genre"] = metadata["tags"][0]

        # Release Date
        release_state = common.get("releasestate")
        if release_state == "released":
            # Steam stores timestamps in many places, or just a string in 'release_date'
            rt = common.get("release_date")
            if rt: metadata["release_date"] = str(rt) # Might need conversion from epoch

        # Image
        logo = common.get("logo")
        if logo:
            metadata["header_image_url"] = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"

        # If parent exists, try to get parent info too (from same dict)
        if metadata.get("parent_app_id"):
            pid = int(metadata["parent_app_id"])
            p_data = self.appinfo_dict.get(pid, {}).get("common", {})
            if p_data:
                metadata["parent_name"] = p_data.get("name")
                p_genres = p_data.get("genres", {})
                if isinstance(p_genres, dict):
                    metadata["parent_tags"] = [g.get("name") for g in p_genres.values() if isinstance(g, dict) and "name" in g]
                if metadata["parent_tags"]: metadata["parent_genre"] = metadata["parent_tags"][0]

        return metadata

    def _parse_acf(self, path: Path) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return vdf.load(f)
        except Exception as e:
            logger.error(f"Failed to parse ACF {path}: {e}")
            return None

    def _is_soundtrack(self, manifest: dict, app_id: int) -> bool:
        """Checks if an app is a soundtrack using local manifest or appinfo."""
        # Check 1: Manifest contenttype
        app_state = manifest.get("AppState", {})
        if app_state.get("UserConfig", {}).get("contenttype") == "3":
            return True
            
        # Check 2: appinfo type
        app_info = self.appinfo_dict.get(app_id, {}).get("common", {})
        if app_info.get("type", "").lower() in ["music", "soundtrack"]:
            return True
            
        # Check 3: Name fallback
        app_name = app_info.get("name") or app_state.get("name", "").lower()
        if "soundtrack" in str(app_name).lower() or " ost" in str(app_name).lower():
            return True
            
        return False
