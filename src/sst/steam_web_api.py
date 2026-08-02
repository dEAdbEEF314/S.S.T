import json
import logging
import requests
import time
from typing import Dict, Any, Optional

from .db import DatabaseManager

logger = logging.getLogger(__name__)

class SteamWebClient:
    def __init__(self, db: DatabaseManager, bridge_url: str, bridge_api_key: Optional[str] = None, api_key: Optional[str] = None, language: str = "japanese"):
        self.db = db
        self.bridge_url = bridge_url if bridge_url.endswith("/") else bridge_url + "/"
        self.bridge_api_key = bridge_api_key
        self.api_key = api_key
        self.language = language

    def fetch_web_enrichment(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Fetches metadata from 3 tiers of APIs (Official Store, PICS Bridge, Official Tags) with DB persistence."""
        # 1. Check Database first
        db_data = self.db.get_store_data(app_id)
        
        result = {"genres": [], "tags": [], "name": None, "store_tracklist": [], "store_credits": "", "label": None, "release_date": None}
        
        if db_data:
            result["store_tracklist"] = db_data.get("tracklist", [])
            result["store_credits"] = db_data.get("credits", "")
            logger.debug(f"{app_id} のストアデータをDBから読み込みました")

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
                app_data = None
                for attempt in range(3):
                    try:
                        sr = session.get(store_url, headers=common_headers, timeout=15)
                        if sr.status_code == 200:
                            s_json = sr.json()
                            if str(app_id) in s_json and s_json[str(app_id)]["success"]:
                                app_data = s_json[str(app_id)]["data"]
                                break
                        logger.debug(f"Tier 1 の試行 {attempt+1} が失敗しました (ステータス: {sr.status_code})")
                    except Exception as e:
                        logger.debug(f"Tier 1 の試行 {attempt+1} エラー: {e}")
                    time.sleep(2 ** (attempt + 1))  # 2s, 4s, 8s exponential backoff
                
                if app_data:
                    result["name"] = app_data.get("name")
                    result["genres"] = [g.get("description") for g in app_data.get("genres", []) if g.get("description")]
                    result["release_date"] = app_data.get("release_date", {}).get("date")

                # --- Tier 2: PICS Data via (Local/Remote) Bridge API ---
                pics_url = f"{self.bridge_url}{app_id}"
                
                pics_headers = common_headers.copy()
                if self.bridge_api_key:
                    if self.bridge_api_key.startswith("Bearer "):
                        pics_headers["Authorization"] = self.bridge_api_key
                    else:
                        pics_headers["X-API-Key"] = self.bridge_api_key

                # Retry logic for Tier 2 (Critical for structured data)
                for attempt in range(3):
                    try:
                        pr = session.get(pics_url, headers=pics_headers, timeout=30)
                        if pr.status_code == 200:
                            p_json = pr.json()
                            app_pics = p_json.get("data", {}).get(str(app_id), {})
                            if app_pics: break # Success
                        logger.debug(f"Tier 2 の試行 {attempt+1} が失敗しました (ステータス: {pr.status_code})")
                    except Exception as e:
                        logger.debug(f"Tier 2 の試行 {attempt+1} エラー: {e}")
                    time.sleep(2 ** (attempt + 1))
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
                        logger.debug(f"PICS トラックのソート中にエラーが発生しました: {e}")
                
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
                        logger.debug(f"公式タグの取得に失敗しました: {te}")

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
            logger.debug(f"{app_id} のウェブエンリッチメントに失敗しました: {e}")
            return None
