import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ScannerCacheManager:
    def __init__(self, cache_path: str = "data/scout_cache.json"):
        self.cache_path = Path(cache_path)
        self.cache = self._load_cache()
        self.tag_map = self._load_tag_map()

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"キャッシュの読み込みに失敗しました: {e}")
        return {"enriched": {}}

    def save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"キャッシュの保存に失敗しました: {e}")

    def _load_tag_map(self) -> dict:
        tag_file = Path("data/steam_tags.json")
        if tag_file.exists():
            try:
                with open(tag_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"タグマップの読み込みに失敗しました: {e}")
        return {}
        
    def get_enriched(self, app_id: str) -> dict:
        return self.cache.get("enriched", {}).get(str(app_id), {})
        
    def set_enriched(self, app_id: str, data: dict):
        if "enriched" not in self.cache:
            self.cache["enriched"] = {}
        self.cache["enriched"][str(app_id)] = data
        self.save_cache()
        
    def get_tag(self, tag_id: str) -> str:
        return self.tag_map.get(str(tag_id))
