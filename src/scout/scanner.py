import os
import vdf
import logging
import requests
import time
import json
import re
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from .utils import ensure_wsl_path
from .steam_vdf import SteamBinaryVDF, SteamLibraryDiscovery
from .db import DatabaseManager

logger = logging.getLogger(__name__)

# Target music extensions
MUSIC_EXTENSIONS = {".flac", ".wav", ".mp3", ".aiff", ".m4a"}

class SteamScanner:
    def __init__(self, install_path: str, db: DatabaseManager, bridge_url: str, api_key: Optional[str] = None, override_library_path: Optional[str] = None, cache_path: str = "data/scout_cache.json", language: str = "japanese"):
        self.install_path = ensure_wsl_path(install_path)
        self.db = db
        self.bridge_url = bridge_url if bridge_url.endswith("/") else bridge_url + "/"
        self.api_key = api_key
        self.cache_path = Path(cache_path)
        self.language = language
        self.cache = self._load_cache()
        
        # 1. Discover all libraries
        self.library_paths = self._discover_all_libraries(override_library_path)
        
        # 2. Parse appinfo.vdf
        appcache_path = self.install_path / "appcache" / "appinfo.vdf"
        if appcache_path.exists():
            self.appinfo_dict = SteamBinaryVDF.parse_appinfo(appcache_path)
            logger.info(f"Loaded {len(self.appinfo_dict)} apps from local appinfo.vdf")
        else:
            self.appinfo_dict = {}
            logger.warning(f"appinfo.vdf not found at {appcache_path}. Falling back to basic scan.")

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
        return {"enriched": {}}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _discover_all_libraries(self, override_path: Optional[str]) -> List[Path]:
        libs = SteamLibraryDiscovery.discover(self.install_path)
        # CRITICAL: Convert all Windows paths from libraryfolders.vdf to WSL paths
        wsl_libs = [ensure_wsl_path(str(p)) for p in libs]
        
        if override_path:
            p = ensure_wsl_path(override_path)
            if p not in wsl_libs: wsl_libs.append(p)
        
        logger.info(f"Initialized SteamScanner with {len(wsl_libs)} libraries.")
        return wsl_libs

    def find_soundtracks(self, force: bool = False, limit: Optional[int] = None, is_processed_callback: Optional[callable] = None, target_appid: Optional[int] = None) -> List[dict]:
        """
        Finds soundtrack app manifests and merges them with local appinfo metadata.
        """
        soundtracks = []
        
        # Scan all libraries for .acf files
        all_acf_files = []
        for lib in self.library_paths:
            acf_dir = lib / "steamapps"
            if acf_dir.exists():
                all_acf_files.extend(list(acf_dir.glob("appmanifest_*.acf")))
        
        logger.info(f"Found {len(all_acf_files)} ACF files across {len(self.library_paths)} libraries.")

        for acf_file in all_acf_files:
            if limit and len(soundtracks) >= limit: break
            
            try:
                manifest = self._parse_acf(acf_file)
                if not manifest: continue
                
                app_state = manifest.get("AppState", {})
                current_id = int(app_state.get("appid", 0))
                parent_appid = int(app_state.get("appid", 0)) # Default
                
                # Filter by AppID if requested
                if target_appid and current_id != target_appid:
                    continue

                if not force and is_processed_callback and is_processed_callback(current_id):
                    continue

                # If target_appid is NOT set, only process if it's a known soundtrack
                if not target_appid and not self._is_soundtrack(manifest, current_id) and current_id == parent_appid:
                    continue

                last_updated = app_state.get("LastUpdated", "0")
                library_root = acf_file.parent # The root containing common/music/workshop
                
                # Check for main app and DLCs
                potential_ids = [parent_appid]
                depots = app_state.get("InstalledDepots", {})
                for d_id, d_data in depots.items():
                    try: potential_ids.append(int(d_id))
                    except: pass
                
                enriched = self._get_local_metadata(current_id)
                if not enriched and not target_appid:
                    # If we can't find metadata locally and it wasn't a targeted scan, skip
                    continue

                soundtracks.append({
                    "app_id": current_id,
                    "name": enriched.get("name") or app_state.get("name", f"App {current_id}"),
                    "install_dir": str(self._resolve_install_path(library_root, app_state.get("installdir"), current_id)),
                    "developer": enriched.get("developer"),
                    "publisher": enriched.get("publisher"),
                    "genre": enriched.get("genre"),
                    "genres": enriched.get("genres", []),
                    "label": enriched.get("label"),
                    "tags": enriched.get("tags", []),
                    "release_date": enriched.get("release_date"),
                    "parent_app_id": enriched.get("parent_app_id") or (parent_appid if current_id != parent_appid else None),
                    "parent_name": enriched.get("parent_name") or (app_state.get("name") if current_id != parent_appid else None),
                    "parent_tags": enriched.get("parent_tags", []),
                    "parent_genre": enriched.get("parent_genre"),
                    "parent_genres": enriched.get("parent_genres", []),
                    "parent_release_date": enriched.get("parent_release_date"),
                    "store_tracklist": enriched.get("store_tracklist", []),
                    "store_credits": enriched.get("store_credits", ""),
                    "url": f"https://store.steampowered.com/app/{current_id}",
                    "header_image_url": enriched.get("header_image_url"),
                    "acf_path": str(acf_file),
                    "last_updated_acf": last_updated
                })
            except Exception as e:
                logger.error(f"Error processing ACF {acf_file}: {e}")

        logger.info(f"Scan complete. Found {len(soundtracks)} soundtracks to process.")
        return soundtracks

    def _get_local_metadata(self, app_id: int) -> dict:
        """Extracts metadata from local appinfo and enriches with web data if missing."""
        data = self.appinfo_dict.get(app_id)
        if not data: return {}

        common = data.get("common", {})
        extended = data.get("extended", {})
        
        metadata = {
            "name": common.get("name"),
            "developer": extended.get("developer"),
            "publisher": extended.get("publisher"),
            "genre": None,
            "genres": [], # All genres
            "tags": [],
            "release_date": None,
            "label": extended.get("publisher"),
            "header_image_url": None,
            "store_tracklist": [],
            "store_credits": "",
            "parent_app_id": common.get("parent") or common.get("fullgameid"),
            "parent_genres": []
        }

        # 1. Try to get basic enriched data from cache
        cache_key = str(app_id)
        enriched = self.cache.get("enriched", {}).get(cache_key, {})
        metadata.update(enriched)

        # 2. Ensure Tracklist/Credits/PICS data are fetched (Phase 1)
        if not metadata.get("store_tracklist"):
            web_data = self._fetch_web_enrichment(app_id)
            if web_data:
                metadata.update(web_data)
                # Update cache too for basic fields
                if "enriched" not in self.cache: self.cache["enriched"] = {}
                self.cache["enriched"][cache_key] = web_data
                self._save_cache()

        # Fallback to local genre if web failed
        if not metadata.get("genres"):
            genres_data = common.get("genres", {})
            if isinstance(genres_data, dict):
                metadata["genres"] = [g.get("name") for g in genres_data.values() if isinstance(g, dict) and "name" in g]
            if metadata["genres"]: metadata["genre"] = metadata["genres"][0]

        # Release Date & Artwork (Local fallbacks)
        if not metadata.get("release_date"):
            rt = common.get("release_date")
            if rt: metadata["release_date"] = str(rt)
        if not metadata.get("header_image_url"):
            if common.get("logo"):
                metadata["header_image_url"] = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"

        # 3. Handle Parent Enrichment
        if metadata.get("parent_app_id"):
            pid = int(metadata["parent_app_id"])
            p_cache_key = str(pid)
            if p_cache_key in self.cache.get("enriched", {}):
                p_enriched = self.cache["enriched"][p_cache_key]
                metadata["parent_name"] = p_enriched.get("name")
                metadata["parent_tags"] = p_enriched.get("tags", [])
                metadata["parent_genres"] = p_enriched.get("genres", [])
                metadata["parent_genre"] = metadata["parent_genres"][0] if metadata["parent_genres"] else None
            else:
                p_web = self._fetch_web_enrichment(pid)
                if p_web:
                    metadata["parent_name"] = p_web.get("name")
                    metadata["parent_tags"] = p_web.get("tags", [])
                    metadata["parent_genres"] = p_web.get("genres", [])
                    metadata["parent_genre"] = metadata["parent_genres"][0] if metadata["parent_genres"] else None
                    if "enriched" not in self.cache: self.cache["enriched"] = {}
                    self.cache["enriched"][p_cache_key] = p_web
                    self._save_cache()
                else:
                    # Local fallback for parent
                    p_data = self.appinfo_dict.get(pid, {}).get("common", {})
                    if p_data:
                        metadata["parent_name"] = p_data.get("name")

        return metadata

    def _fetch_web_enrichment(self, app_id: int) -> Dict[str, Any]:
        """Fetches metadata from 3 tiers of APIs (Official Store, PICS Bridge, Official Tags) with DB persistence."""
        # 1. Check Database first
        db_data = self.db.get_store_data(app_id)
        
        result = {"genres": [], "tags": [], "name": None, "store_tracklist": [], "store_credits": "", "label": None, "release_date": None}
        
        if db_data:
            result["store_tracklist"] = db_data.get("tracklist", [])
            result["store_credits"] = db_data.get("credits", "")
            logger.debug(f"Loaded store data from DB for {app_id}")

        try:
            # Only fetch if missing or incomplete
            if not result["store_tracklist"]:
                # Mandatory Throttle (2s + jitter)
                import random
                time.sleep(2.0 + random.random())
                
                session = requests.Session()
                common_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*'
                }

                # --- Tier 1: Official Store API (Localized name/genres) ---
                store_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l={self.language}"
                sr = session.get(store_url, headers=common_headers, timeout=15)
                if sr.status_code == 200:
                    s_json = sr.json()
                    if str(app_id) in s_json and s_json[str(app_id)]["success"]:
                        app_data = s_json[str(app_id)]["data"]
                        result["name"] = app_data.get("name")
                        result["genres"] = [g.get("description") for g in app_data.get("genres", []) if g.get("description")]
                        result["release_date"] = app_data.get("release_date", {}).get("date")

                # --- Tier 2: PICS Data via (Local/Remote) Bridge API ---
                pics_url = f"{self.bridge_url}{app_id}"
                
                # Retry logic for Tier 2 (Critical for structured data)
                for attempt in range(3):
                    try:
                        pr = session.get(pics_url, headers=common_headers, timeout=30)
                        if pr.status_code == 200:
                            p_json = pr.json()
                            app_pics = p_json.get("data", {}).get(str(app_id), {})
                            if app_pics: break # Success
                        logger.debug(f"Tier 2 attempt {attempt+1} failed (Status: {pr.status_code})")
                    except Exception as e:
                        logger.debug(f"Tier 2 attempt {attempt+1} error: {e}")
                    time.sleep(2 * (attempt + 1))
                else:
                    app_pics = {} # All retries failed

                album_meta = app_pics.get("albummetadata", {})
                
                # Maximum Information: Change Number and Raw PICS
                pics_change_num = app_pics.get("_change_number")
                
                pics_tracks = album_meta.get("tracks", {})
                if isinstance(pics_tracks, dict):
                    try:
                        sorted_keys = sorted(pics_tracks.keys(), key=lambda x: int(x))
                        for k in sorted_keys:
                            t = pics_tracks[k]
                            result["store_tracklist"].append({
                                "disc": int(t.get("discnumber", 1)),
                                "number": str(t.get("tracknumber", "")),
                                "title": t.get("originalname", ""),
                                "duration_s": t.get("s", "0")
                            })
                    except Exception as e:
                        logger.debug(f"Error sorting PICS tracks: {e}")
                
                meta_section = album_meta.get("metadata", {})
                credits_parts = []
                target_lang = {"ja": "japanese", "en": "english"}.get(self.language, "english")
                
                for role in ["artist", "composer", "label", "othercredits"]:
                    role_data = meta_section.get(role, {})
                    val = role_data.get(target_lang) or role_data.get("english")
                    if val:
                        if role == "label": result["label"] = val
                        else: credits_parts.append(f"{role.capitalize()}: {val}")
                
                if credits_parts:
                    result["store_credits"] = "\n".join(credits_parts)

                # --- Tier 3: Official Tags via IStoreBrowseService (If API key exists) ---
                if self.api_key:
                    try:
                        tag_url = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
                        params = {
                            "key": self.api_key,
                            "ids": app_id,
                            "context": json.dumps({"language": self.language, "country_code": "JP"}),
                            "data_request": json.dumps({"include_tag_count": 20})
                        }
                        tr = session.get(tag_url, params=params, timeout=10)
                        if tr.status_code == 200:
                            t_json = tr.json()
                            store_items = t_json.get("response", {}).get("store_items", [])
                            if store_items:
                                tags_data = store_items[0].get("tags", [])
                                result["tags"] = [t.get("name") for t in tags_data if t.get("name")]
                    except Exception as te:
                        logger.debug(f"Official Tags fetch failed: {te}")

                # 4. Save to Database (Extended Storage)
                if result["store_tracklist"]:
                    self.db.save_store_data(
                        app_id, 
                        result["store_tracklist"], 
                        result["store_credits"], 
                        change_number=locals().get("pics_change_num"), 
                        raw_pics=locals().get("app_pics")
                    )
            
            return result
        except Exception as e:
            logger.debug(f"Web enrichment failed for {app_id}: {e}")
            return None

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

    def _resolve_install_path(self, library_root: Path, manifest_dir: str, app_id: int) -> Path:
        """Determines the absolute installation path of a soundtrack."""
        if manifest_dir:
            # 1. Check common/
            path = library_root / "common" / manifest_dir
            if path.exists(): return path
            # 2. Check music/
            path = library_root / "music" / manifest_dir
            if path.exists(): return path
            
        # 3. Last resort: check by AppID folder name in common or music
        for sub in ["common", "music"]:
            path = library_root / sub / str(app_id)
            if path.exists(): return path
            
        # 4. Fallback to common/manifest_dir even if not exist (for downstream skip)
        return library_root / "common" / (manifest_dir or str(app_id))
