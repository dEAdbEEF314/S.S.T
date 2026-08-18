import time

from sst.llm.llm_cache import LLMResultCache


def test_llm_cache_hit_returns_same_result(tmp_path):
    """提案7: 同一入力・同一言語・TTL内で2回目はキャッシュヒット（LLM呼び出しなし）。"""
    cache = LLMResultCache(cache_path=str(tmp_path / "llm_cache.json"), ttl_seconds=86400, enabled=True)
    result = {"ok": True}
    put_audit = cache.put("same input", "identity", "ja", result)
    assert put_audit["hit"] is False

    hit_audit = cache.audit_hit("same input", "identity", "ja")
    assert hit_audit["hit"] is True
    assert cache.get("same input", "identity", "ja") == result


def test_llm_cache_misses_on_different_language(tmp_path):
    """提案7: 言語だけ異なる同一入力はキャッシュミス。"""
    cache = LLMResultCache(cache_path=str(tmp_path / "llm_cache.json"), ttl_seconds=86400, enabled=True)
    cache.put("same input", "identity", "ja", {"ok": True})
    assert cache.get("same input", "identity", "en") is None


def test_llm_cache_expires_after_ttl(tmp_path):
    """提案7: TTL超過でキャッシュミス。"""
    cache = LLMResultCache(cache_path=str(tmp_path / "llm_cache.json"), ttl_seconds=1, enabled=True)
    cache.put("same input", "identity", "ja", {"ok": True})
    time.sleep(1.1)
    assert cache.get("same input", "identity", "ja") is None


def test_llm_cache_does_not_share_across_inputs(tmp_path):
    """提案7: 入力ハッシュが異なる場合はキャッシュミス。"""
    cache = LLMResultCache(cache_path=str(tmp_path / "llm_cache.json"), ttl_seconds=86400, enabled=True)
    cache.put("input A", "identity", "ja", {"ok": True})
    assert cache.get("input B", "identity", "ja") is None


def test_llm_cache_disabled_returns_none(tmp_path):
    """提案7: 無効化スイッチで完全にキャッシュしない。"""
    cache = LLMResultCache(cache_path=str(tmp_path / "llm_cache.json"), ttl_seconds=86400, enabled=False)
    cache.put("same input", "identity", "ja", {"ok": True})
    assert cache.get("same input", "identity", "ja") is None
