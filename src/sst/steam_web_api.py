import json
import logging
import requests
import time
import html
import re
from html.parser import HTMLParser
from typing import Dict, Any, Optional

from .db import DatabaseManager
from .steam_tracklist import validate_llm_tracklist

logger = logging.getLogger(__name__)

class SteamWebClient:
    def __init__(self, db: DatabaseManager, bridge_url: str, bridge_api_key: Optional[str] = None, api_key: Optional[str] = None, language: str = "japanese", llm_extractor: Any = None):
        self.db = db
        self.bridge_url = bridge_url if bridge_url.endswith("/") else bridge_url + "/"
        self.bridge_api_key = bridge_api_key
        self.api_key = api_key
        self.language = language
        self.llm_extractor = llm_extractor

    @staticmethod
    def _parse_text_tracklist(description: str) -> list[Dict[str, Any]]:
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.lines = []

            def handle_data(self, data):
                self.lines.extend(line.strip() for line in data.splitlines() if line.strip())

        parser = TextExtractor()
        parser.feed(description or "")
        candidates = []
        for line in parser.lines:
            match = re.match(r"^\s*(\d{1,3})\s*[.\-:)\u3001]?\s+(.+?)\s*$", line)
            if match and len(match.group(2)) >= 2:
                candidates.append({"disc": 1, "number": match.group(1), "title": html.unescape(match.group(2)), "duration_s": ""})
        numbers = [int(track["number"]) for track in candidates]
        if len(candidates) < 2 or numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            return []
        return candidates

    def fetch_store_tags(self, app_id: int) -> Dict[str, str]:
        """Fetch the official tagid/name pairs embedded in the Steam store page."""
        url = f"https://store.steampowered.com/app/{app_id}/?l={self.language}"
        headers = {"User-Agent": "SST/0.1 (+local Steam metadata tool)"}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            tags = {}
            pattern = re.compile(r'"tagid":(\d+),"name":"((?:\\.|[^"\\])*)"')
            for tag_id, encoded_name in pattern.findall(response.text):
                try:
                    name = json.loads(f'"{encoded_name}"')
                except json.JSONDecodeError:
                    name = encoded_name
                name = html.unescape(name).strip()
                if name:
                    tags[tag_id] = name
            logger.debug(f"AppID {app_id} の公式Steamタグを {len(tags)} 件取得しました (language={self.language})")
            return tags
        except Exception as e:
            logger.warning(f"AppID {app_id} の公式Steamタグ取得に失敗しました: {e}")
            return {}

    def fetch_web_enrichment(self, app_id: int, force: bool = False) -> Optional[Dict[str, Any]]:
        """Fetches metadata from 3 tiers of APIs (Official Store, PICS Bridge, Official Tags) with DB persistence."""
        # 1. Check Database first
        db_data = None if force else self.db.get_store_data(app_id)
        
        result = {"genres": [], "tags": [], "name": None, "store_tracklist": [], "store_tracklist_source": None, "store_tracklist_language": None, "store_credits": "", "label": None, "release_date": None}
        
        if db_data:
            result["store_tracklist"] = db_data.get("tracklist", [])
            result["store_credits"] = db_data.get("credits", "")
            if result["store_tracklist"]:
                result["store_tracklist_source"] = result["store_tracklist"][0].get("source")
                result["store_tracklist_language"] = db_data.get("tracklist_language")
            logger.debug(f"{app_id} のストアデータをDBから読み込みました")

        try:
            # Only fetch if missing or incomplete
            if force or not result["store_tracklist"]:
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
                    description = app_data.get("detailed_description", "")
                else:
                    description = ""

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
                                "duration_s": t.get("s", "0"),
                                "source": "STEAM_PICS",
                            })
                        if result["store_tracklist"]:
                            result["store_tracklist_source"] = "STEAM_PICS"
                    except Exception as e:
                        logger.debug(f"PICS トラックのソート中にエラーが発生しました: {e}")

                if not result["store_tracklist"]:
                    description_language = self.language
                    candidate_description = description
                    if self.language.lower() not in {"english", "en"}:
                        try:
                            english_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
                            english_response = session.get(english_url, headers=common_headers, timeout=15)
                            if english_response.status_code == 200:
                                english_data = english_response.json().get(str(app_id), {})
                                if english_data.get("success"):
                                    candidate_description = english_data.get("data", {}).get("detailed_description", "")
                                    description_language = "english"
                        except Exception as language_error:
                            logger.debug(f"{app_id} の英語説明文フォールバックに失敗しました: {language_error}")

                    text_tracks = self._parse_text_tracklist(candidate_description)
                    if text_tracks:
                        for track in text_tracks:
                            track["source"] = "STEAM_TEXT_TRACKLIST"
                        result["store_tracklist"] = text_tracks
                        result["store_tracklist_source"] = "STEAM_TEXT_TRACKLIST"
                        result["store_tracklist_language"] = description_language
                    elif self.llm_extractor and candidate_description:
                        llm_tracks, llm_log = self.llm_extractor.extract_steam_tracklist(app_id, self._description_text(candidate_description))
                        if llm_tracks:
                            result["store_tracklist"] = llm_tracks
                            result["store_tracklist_source"] = "STEAM_TEXT_TRACKLIST_LLM"
                            result["store_tracklist_language"] = description_language
                            result["store_tracklist_extraction_log"] = llm_log
                        else:
                            result["store_tracklist_extraction_log"] = llm_log
                
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
                        raw_pics=locals().get("app_pics"),
                        tracklist_language=result.get("store_tracklist_language")
                    )
            
            return result

        except Exception as e:
            logger.debug(f"{app_id} のウェブエンリッチメントに失敗しました: {e}")
            return None

    @staticmethod
    def _description_text(description: str) -> str:
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []

            def handle_data(self, data):
                text = data.strip()
                if text:
                    self.parts.append(text)

        parser = TextExtractor()
        parser.feed(description or "")
        return "\n".join(parser.parts)[:30000]
