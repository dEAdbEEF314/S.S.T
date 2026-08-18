import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("sst.llm.cache")


class LLMResultCache:
    """TTL付きLLM結果キャッシュ（steam_tracklist_extraction / identity 用）。

    検証を弱めないため、キャッシュヒット結果も通常のLLM結果と同様に
    organizer の正規化層と validator を通過する。本クラスは単に同一入力の
    再計算を省略するだけであり、自動修正や判定の隠蔽を行わない。
    """

    def __init__(
        self,
        cache_path: str = "data/llm_cache.json",
        ttl_seconds: int = 86400,
        enabled: bool = True,
    ):
        self.cache_path = Path(cache_path)
        self.ttl_seconds = max(1, ttl_seconds)
        self.enabled = enabled
        self._cache: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.enabled:
            return {}
        try:
            if self.cache_path.exists():
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.warning(f"LLMキャッシュの読み込みに失敗しました: {e}")
        return {}

    def _save(self) -> None:
        if not self.enabled:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            tmp.replace(self.cache_path)
        except Exception as e:
            logger.warning(f"LLMキャッシュの保存に失敗しました: {e}")

    @staticmethod
    def _make_key(input_text: str, request_kind: str, user_language: str) -> str:
        digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]
        return f"{digest}:{request_kind}:{user_language}"

    def get(self, input_text: str, request_kind: str, user_language: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        key = self._make_key(input_text, request_kind, user_language)
        entry = self._cache.get(key)
        if not isinstance(entry, dict):
            return None
        saved_at = entry.get("saved_at")
        if saved_at is None:
            return None
        try:
            age = time.time() - float(saved_at)
        except (TypeError, ValueError):
            return None
        if age >= self.ttl_seconds:
            self._cache.pop(key, None)
            self._save()
            return None
        return entry.get("result")

    def put(self, input_text: str, request_kind: str, user_language: str, result: Any) -> Dict[str, Any]:
        """結果を保存し、監査用の cache ブロックを返す。"""
        if not self.enabled:
            return {"hit": False, "enabled": False}
        key = self._make_key(input_text, request_kind, user_language)
        saved_at = time.time()
        self._cache[key] = {
            "result": result,
            "saved_at": saved_at,
            "ttl_seconds": self.ttl_seconds,
            "request_kind": request_kind,
            "user_language": user_language,
        }
        self._save()
        return {
            "hit": False,
            "request_kind": request_kind,
            "input_hash": key.split(":", 1)[0],
            "saved_at": saved_at,
            "ttl_seconds": self.ttl_seconds,
        }

    def audit_hit(self, input_text: str, request_kind: str, user_language: str) -> Dict[str, Any]:
        """キャッシュヒット時の監査ブロックを構築する（保存は行わない）。"""
        key = self._make_key(input_text, request_kind, user_language)
        entry = self._cache.get(key, {})
        return {
            "hit": True,
            "request_kind": request_kind,
            "input_hash": key.split(":", 1)[0],
            "saved_at": entry.get("saved_at"),
            "ttl_seconds": self.ttl_seconds,
        }
