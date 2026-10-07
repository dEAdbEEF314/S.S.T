import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


def test_store_browse_tag_request_uses_configured_api_timeout():
    store_response = MagicMock(status_code=200)
    store_response.json.return_value = {
        "123": {
            "success": True,
            "data": {
                "name": "Synthetic Album",
                "genres": [],
                "release_date": {},
                "detailed_description": "",
            },
        }
    }
    pics_response = MagicMock(status_code=200)
    pics_response.json.return_value = {
        "data": {"123": {"_change_number": 1, "albummetadata": {}}}
    }
    tag_response = MagicMock(status_code=200)
    tag_response.json.return_value = {"response": {"store_items": []}}
    session = MagicMock()
    session.get.side_effect = [store_response, pics_response, tag_response]
    db = MagicMock()
    db.get_store_data.return_value = None
    client = SteamWebClient(
        db,
        "http://bridge/",
        api_key="synthetic-key",
        language="english",
        api_timeout=37,
    )

    with patch("sst.steam_web_api.requests.Session", return_value=session), patch(
        "sst.steam_web_api.time.sleep"
    ):
        client.fetch_web_enrichment(123)

    assert session.get.call_args_list[2].kwargs["timeout"] == 37


def test_steam_api_retries_use_configured_backoff():
    failure_response = MagicMock(status_code=503)
    session = MagicMock()
    session.get.return_value = failure_response
    db = MagicMock()
    db.get_store_data.return_value = None
    client = SteamWebClient(
        db,
        "http://bridge/",
        language="english",
        max_retries=3,
        throttle_delay=0,
        retry_delay=3,
        retry_backoff=2,
    )

    with patch("sst.steam_web_api.requests.Session", return_value=session), patch(
        "sst.steam_web_api.time.sleep"
    ) as sleep, patch("random.random", return_value=0):
        client.fetch_web_enrichment(123)

    assert sleep.call_args_list[1:] == [call(3.0), call(6.0), call(3.0), call(6.0)]


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