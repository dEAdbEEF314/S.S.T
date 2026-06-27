import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("sst.db")

class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Ensures the processing history and store data tables exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_albums (
                    app_id INTEGER PRIMARY KEY,
                    status TEXT,
                    album_name TEXT,
                    processed_at TEXT,
                    metadata_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steam_store_data (
                    app_id INTEGER PRIMARY KEY,
                    change_number INTEGER,
                    tracklist_json TEXT,
                    credits_text TEXT,
                    raw_pics_json TEXT,
                    scraped_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    service TEXT,
                    query_key TEXT,
                    response_data TEXT,
                    fetched_at TEXT,
                    PRIMARY KEY (service, query_key)
                )
            """)

    def get_store_data(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves cached Steam store data including PICS fields."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT tracklist_json, credits_text, change_number, raw_pics_json FROM steam_store_data WHERE app_id = ?", (app_id,))
            row = cur.fetchone()
            if row:
                return {
                    "tracklist": json.loads(row[0]),
                    "credits": row[1],
                    "change_number": row[2],
                    "raw_pics": json.loads(row[3]) if row[3] else {}
                }
        return None

    def save_store_data(self, app_id: int, tracklist: list, credits: str, change_number: Optional[int] = None, raw_pics: Optional[Dict] = None):
        """Saves comprehensive Steam store and PICS data."""
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO steam_store_data (app_id, change_number, tracklist_json, credits_text, raw_pics_json, scraped_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    app_id, 
                    change_number, 
                    json.dumps(tracklist, ensure_ascii=False), 
                    credits, 
                    json.dumps(raw_pics, ensure_ascii=False) if raw_pics else None,
                    datetime.utcnow().isoformat()
                )
            )
        logger.debug(f"Saved extended store data for AppID {app_id}")

    def is_already_processed(self, app_id: int) -> bool:
        """Checks if an AppID has already been handled."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM processed_albums WHERE app_id = ?", (app_id,))
            return cur.fetchone() is not None

    def record_processed(self, app_id: int, status: str, name: str, processed_at: str, summary_meta: Dict):
        """Saves or updates a processing result."""
        if status == "review" and not summary_meta.get("message"):
            diag = summary_meta.get("diagnostics", {})
            logger.warning(
                "Review metadata missing message for AppID %s (cause=%s, upstream=%s)",
                app_id,
                diag.get("review_cause_code"),
                diag.get("upstream_cause_code"),
            )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_albums (app_id, status, album_name, processed_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (app_id, status, name, processed_at, json.dumps(summary_meta, ensure_ascii=False))
            )
        logger.debug(f"Recorded AppID {app_id} in DB with status: {status}")

    def get_api_cache(self, service: str, query_key: str, ttl_days: int = 30) -> Optional[Any]:
        """Retrieves cached API response if it is within the TTL."""
        from datetime import datetime, timedelta
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT response_data, fetched_at FROM api_cache WHERE service = ? AND query_key = ?", (service, query_key))
            row = cur.fetchone()
            if row:
                fetched_at = datetime.fromisoformat(row[1])
                if datetime.utcnow() - fetched_at <= timedelta(days=ttl_days):
                    return json.loads(row[0])
        return None

    def set_api_cache(self, service: str, query_key: str, data: Any):
        """Saves an API response to the cache."""
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_cache (service, query_key, response_data, fetched_at) VALUES (?, ?, ?, ?)",
                (service, query_key, json.dumps(data, ensure_ascii=False), datetime.utcnow().isoformat())
            )
