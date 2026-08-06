import vdf
import logging
import requests
import time
import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from .utils import ensure_path
from .steam_vdf import SteamBinaryVDF, SteamLibraryDiscovery
from .db import DatabaseManager
from .scanner_cache import ScannerCacheManager
from .steam_web_api import SteamWebClient

logger = logging.getLogger(__name__)

# Target music extensions
MUSIC_EXTENSIONS = {".flac", ".wav", ".mp3", ".aiff", ".aif", ".m4a", ".ogg"}

class SteamScanner:
    def __init__(self, install_path: str, db: DatabaseManager, bridge_url: str, bridge_api_key: Optional[str] = None, api_key: Optional[str] = None, override_library_path: Optional[str] = None, cache_path: str = "data/scout_cache.json", language: str = "japanese", tag_refresh_days: int = 30, llm_extractor: Any = None):
        self.install_path = ensure_path(install_path)
        self.db = db
        
        self.cache_manager = ScannerCacheManager(cache_path, tag_refresh_days=tag_refresh_days)
        self.web_client = SteamWebClient(db, bridge_url, bridge_api_key, api_key, language, llm_extractor=llm_extractor)
        
        # 1. Discover all libraries
        self.library_paths = self._discover_all_libraries(override_library_path)
        
        # 2. Parse appinfo.vdf
        appcache_path = self.install_path / "appcache" / "appinfo.vdf"
        if appcache_path.exists():
            self.appinfo_dict = SteamBinaryVDF.parse_appinfo(appcache_path)
            logger.info(f"ローカルの appinfo.vdf から {len(self.appinfo_dict)} 個のアプリを読み込みました")
        else:
            self.appinfo_dict = {}
            logger.warning(f"appinfo.vdf が {appcache_path} に見つかりません。基本スキャンにフォールバックします。")




    def _discover_all_libraries(self, override_path: Optional[str]) -> List[Path]:
        libs = SteamLibraryDiscovery.discover(self.install_path)
        # CRITICAL: Convert all Windows paths from libraryfolders.vdf to WSL paths
        wsl_libs = [ensure_path(str(p)) for p in libs]
        
        if override_path:
            p = ensure_path(override_path)
            if p not in wsl_libs: wsl_libs.append(p)
        
        logger.info(f"{len(wsl_libs)} 個のライブラリで SteamScanner を初期化しました。")
        return wsl_libs

    def find_soundtracks(self, force: bool = False, limit: Optional[int] = None, is_processed_callback: Optional[callable] = None, target_appids: Optional[List[int]] = None) -> List[dict]:
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
        
        logger.info(f"{len(self.library_paths)} 個のライブラリから {len(all_acf_files)} 個の ACF ファイルを見つけました。")

        for acf_file in all_acf_files:
            if limit and len(soundtracks) >= limit: break
            
            try:
                manifest = self._parse_acf(acf_file)
                if not manifest: continue
                
                app_state = manifest.get("AppState", {})
                current_id = int(app_state.get("appid", 0))
                parent_appid = int(app_state.get("appid", 0)) # Default
                
                # Filter by AppID if requested
                if target_appids and current_id not in target_appids:
                    continue

                if not force and is_processed_callback and is_processed_callback(current_id):
                    continue

                # If target_appids is NOT set, only process if it's a known soundtrack
                if not target_appids and not self._is_soundtrack(manifest, current_id) and current_id == parent_appid:
                    continue

                last_updated = app_state.get("LastUpdated", "0")
                library_root = acf_file.parent # The root containing common/music/workshop
                
                # Check for main app and DLCs
                potential_ids = [parent_appid]
                depots = app_state.get("InstalledDepots", {})
                for d_id, d_data in depots.items():
                    try: potential_ids.append(int(d_id))
                    except Exception: pass
                
                enriched = self._get_local_metadata(current_id)
                if not enriched and not target_appids:
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
                    "store_tracklist_source": enriched.get("store_tracklist_source"),
                    "store_tracklist_language": enriched.get("store_tracklist_language"),
                    "store_credits": enriched.get("store_credits", ""),
                    "url": f"https://store.steampowered.com/app/{current_id}",
                    "header_image_url": enriched.get("header_image_url"),
                    "acf_path": str(acf_file),
                    "last_updated_acf": last_updated
                })
            except Exception as e:
                logger.error(f"ACF {acf_file} の処理中にエラーが発生しました: {e}")

        logger.info(f"スキャンが完了しました。処理対象のサウンドトラックが {len(soundtracks)} 個見つかりました。")
        return soundtracks

    def _get_local_metadata(self, app_id: int) -> dict:
        """Extracts metadata from local appinfo and enriches with web data if missing."""
        data = self.appinfo_dict.get(app_id, {})
        
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
            "store_tracklist_source": None,
            "store_tracklist_language": None,
            "store_credits": "",
            "parent_app_id": common.get("parent") or common.get("fullgameid"),
            "parent_genres": []
        }

        # 1. Try to get basic enriched data from cache
        cache_key = str(app_id)
        enriched = self.cache_manager.cache.get("enriched", {}).get(cache_key, {})
        metadata.update(enriched)

        # 2. Extract tags from local appinfo (Topic: Local Tags)
        if not metadata.get("tags") and "store_tags" in common:
            metadata["tags"] = self._resolve_tags(app_id, common["store_tags"])

        # 3. Ensure Tracklist/Credits/PICS data are fetched during signal gathering
        if not metadata.get("store_tracklist"):
            web_data = self.web_client.fetch_web_enrichment(app_id)
            if web_data:
                metadata.update(web_data)
                # Update cache too for basic fields
                
                self.cache_manager.set_enriched(cache_key, web_data)


        # Fallback to local genre if web failed
        if not metadata.get("genres"):
            genres_data = common.get("genres", {})
            if isinstance(genres_data, dict):
                metadata["genres"] = [g.get("description") or g.get("name") for g in genres_data.values() if isinstance(g, dict) and (g.get("description") or g.get("name"))]
            if metadata["genres"]: metadata["genre"] = metadata["genres"][0]

        # Release Date & Artwork (Local fallbacks)
        if not metadata.get("release_date"):
            rt = common.get("release_date")
            if rt: metadata["release_date"] = str(rt)
        if not metadata.get("header_image_url"):
            if common.get("logo"):
                metadata["header_image_url"] = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"

        # 4. Handle Parent Enrichment
        if metadata.get("parent_app_id"):
            pid = int(metadata["parent_app_id"])
            p_cache_key = str(pid)
            
            # Try local appinfo for parent tags first (much faster)
            p_appinfo = self.appinfo_dict.get(pid, {}).get("common", {})
            if "store_tags" in p_appinfo:
                metadata["parent_tags"] = self._resolve_tags(pid, p_appinfo["store_tags"])

            if p_cache_key in self.cache_manager.cache.get("enriched", {}):
                p_enriched = self.cache_manager.cache["enriched"][p_cache_key]
                metadata["parent_name"] = p_enriched.get("name")
                if not metadata.get("parent_tags"):
                    metadata["parent_tags"] = p_enriched.get("tags", [])
                metadata["parent_genres"] = p_enriched.get("genres", [])
                metadata["parent_genre"] = metadata["parent_genres"][0] if metadata["parent_genres"] else None
            else:
                p_web = self.web_client.fetch_web_enrichment(pid)
                if p_web:
                    metadata["parent_name"] = p_web.get("name")
                    if not metadata.get("parent_tags"):
                        metadata["parent_tags"] = p_web.get("tags", [])
                    metadata["parent_genres"] = p_web.get("genres", [])
                    metadata["parent_genre"] = metadata["parent_genres"][0] if metadata["parent_genres"] else None
                    
                    self.cache_manager.set_enriched(p_cache_key, p_web)
                    
                else:
                    # Local fallback for parent
                    if not metadata.get("parent_name"):
                        metadata["parent_name"] = p_appinfo.get("name")

        return metadata

    def _resolve_tags(self, app_id: int, raw_tag_ids: Any) -> List[str]:
        tag_ids = list(raw_tag_ids.values()) if isinstance(raw_tag_ids, dict) else list(raw_tag_ids or [])
        normalized_ids = [str(tag_id) for tag_id in tag_ids]
        if self.cache_manager.tag_cache_needs_refresh(self.web_client.language, normalized_ids):
            fetched = self.web_client.fetch_store_tags(app_id)
            if fetched:
                self.cache_manager.merge_tag_map(self.web_client.language, fetched)
        return [self.cache_manager.get_tag(tag_id) for tag_id in normalized_ids if self.cache_manager.get_tag(tag_id)]


    def _parse_acf(self, path: Path) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return vdf.load(f)
        except Exception as e:
            logger.error(f"ACF {path} の解析に失敗しました: {e}")
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
            # 1. Check music/ (Prioritize dedicated soundtrack folder)
            path = library_root / "music" / manifest_dir
            if path.exists(): return path
            # 2. Check common/ (Standard game install folder)
            path = library_root / "common" / manifest_dir
            if path.exists(): return path
            
        # 3. Last resort: check by AppID folder name in music or common
        for sub in ["music", "common"]:
            path = library_root / sub / str(app_id)
            if path.exists(): return path
            
        # 4. Fallback to music/manifest_dir even if not exist (for downstream skip)
        return library_root / "music" / (manifest_dir or str(app_id))