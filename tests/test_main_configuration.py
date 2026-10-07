import json

from rich.console import Console
from unittest.mock import patch

from sst.config import Config
from sst.main import fetch_steam_userdata
from sst.scanner import SteamScanner


def test_fetch_steam_userdata_uses_configured_timeout_and_path(tmp_path, monkeypatch):
    userdata_path = tmp_path / "nested" / "steam" / "userdata.json"
    request = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"owned": [123]}

    def fake_get(url, *, cookies, timeout):
        request.update(url=url, cookies=cookies, timeout=timeout)
        return Response()

    monkeypatch.setattr("sst.main.requests.get", fake_get)
    config = Config(
        steam_install_path="/tmp",
        steam_login_secure="synthetic-cookie",
        steam_userdata_timeout=23,
        sst_userdata_path=str(userdata_path),
    )

    fetch_steam_userdata(config, Console())

    assert request["timeout"] == 23
    assert request["cookies"] == {"steamLoginSecure": "synthetic-cookie"}
    assert json.loads(userdata_path.read_text(encoding="utf-8")) == {"owned": [123]}


def test_scanner_forwards_configured_tag_cache_and_retry_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(SteamScanner, "_discover_all_libraries", lambda self, path: [])
    cache_path = tmp_path / "scan-cache.json"
    tag_cache_path = tmp_path / "tag-cache.json"

    with patch("sst.scanner.SteamWebClient") as steam_web_client:
        scanner = SteamScanner(
            install_path=str(tmp_path),
            db=object(),
            bridge_url="http://localhost:8080",
            cache_path=str(cache_path),
            tag_cache_path=str(tag_cache_path),
            retry_delay=7.0,
            retry_backoff=3.0,
        )

    assert scanner.cache_manager.cache_path == cache_path
    assert scanner.cache_manager.tag_cache_path == tag_cache_path
    forwarded = steam_web_client.call_args.kwargs
    assert forwarded["retry_delay"] == 7.0
    assert forwarded["retry_backoff"] == 3.0