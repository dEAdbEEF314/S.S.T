import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Iterable

logger = logging.getLogger(__name__)

class ScannerCacheManager:
    def __init__(self, cache_path: str = "data/scout_cache.json", tag_cache_path: str = "data/steam_tags.json", tag_refresh_days: int = 30):
        self.cache_path = Path(cache_path)
        self.tag_cache_path = Path(tag_cache_path)
        self.tag_refresh_days = max(1, tag_refresh_days)
        self.cache = self._load_cache()
        self.tag_cache = self._load_tag_cache()
        self.tag_map = self.tag_cache["tags"]

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

    def _load_tag_cache(self) -> dict:
        if self.tag_cache_path.exists():
            try:
                with open(self.tag_cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data.get("tags"), dict):
                    return {
                        "language": data.get("language"),
                        "updated_at": data.get("updated_at"),
                        "tags": {str(k): str(v) for k, v in data["tags"].items()},
                    }
                if isinstance(data, dict):
                    return {"language": None, "updated_at": None, "tags": {str(k): str(v) for k, v in data.items()}}
            except Exception as e:
                logger.error(f"タグマップの読み込みに失敗しました: {e}")
        return {"language": None, "updated_at": None, "tags": {}}
        
    def get_enriched(self, app_id: str) -> dict:
        return self.cache.get("enriched", {}).get(str(app_id), {})
        
    def set_enriched(self, app_id: str, data: dict):
        if "enriched" not in self.cache:
            self.cache["enriched"] = {}
        self.cache["enriched"][str(app_id)] = data
        self.save_cache()
        
    def get_tag(self, tag_id: str) -> str:
        return self.tag_map.get(str(tag_id))

    def tag_cache_needs_refresh(self, language: str, tag_ids: Iterable[str]) -> bool:
        ids = {str(tag_id) for tag_id in tag_ids}
        if not ids or self.tag_cache.get("language") != language:
            return bool(ids)
        if not ids.issubset(self.tag_map):
            return True
        updated_at = self.tag_cache.get("updated_at")
        if not updated_at:
            return True
        try:
            updated = datetime.fromisoformat(updated_at)
        except ValueError:
            return True
        age_days = (datetime.now(timezone.utc) - updated).total_seconds() / 86400
        return age_days >= self.tag_refresh_days

    def merge_tag_map(self, language: str, tags: Dict[str, str]) -> None:
        self.tag_map.update({str(tag_id): str(name) for tag_id, name in tags.items() if name})
        self.tag_cache = {
            "language": language,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tags": self.tag_map,
        }
        self.tag_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tag_cache_path, "w", encoding="utf-8") as f:
            json.dump(self.tag_cache, f, indent=2, ensure_ascii=False)
