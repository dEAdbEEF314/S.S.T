import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sst.scanner_cache import ScannerCacheManager
from sst.steam_web_api import SteamWebClient


def test_fetch_store_tags_extracts_localized_tag_names():
    response = MagicMock()
    response.text = '"tagid":1752,"name":"リズム","count":10,"browseable":true'
    response.raise_for_status.return_value = None

    with patch("sst.steam_web_api.requests.get", return_value=response) as get:
        client = SteamWebClient(MagicMock(), "http://bridge/", language="japanese")
        tags = client.fetch_store_tags(977950)

    assert tags == {"1752": "リズム"}
    get.assert_called_once()
    assert get.call_args.args[0] == "https://store.steampowered.com/app/977950/?l=japanese"


def test_tag_cache_migrates_flat_map_and_refreshes_after_expiry(tmp_path: Path):
    tag_path = tmp_path / "steam_tags.json"
    tag_path.write_text(json.dumps({"1752": "Rhythm"}), encoding="utf-8")
    cache = ScannerCacheManager(tmp_path / "scout.json", tag_path, tag_refresh_days=30)

    assert cache.get_tag("1752") == "Rhythm"
    assert cache.tag_cache_needs_refresh("japanese", ["1752"])

    cache.merge_tag_map("japanese", {"1752": "リズム", "1621": "音楽"})
    assert not cache.tag_cache_needs_refresh("japanese", ["1752"])
    assert cache.tag_cache_needs_refresh("english", ["1752"])

    cache.tag_cache["updated_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    assert cache.tag_cache_needs_refresh("japanese", ["1752"])