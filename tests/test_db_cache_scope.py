from pathlib import Path

from sst.db import DatabaseManager


def test_api_cache_supports_shared_and_app_owned_rows(tmp_path: Path):
    db = DatabaseManager(tmp_path / "state.db")

    db.set_api_cache("steam", "tracklist", {"source": "shared"})
    db.set_api_cache("steam", "tracklist-app", {"source": "owned"}, app_id=1495710)

    assert db.get_api_cache("steam", "tracklist") == {"source": "shared"}
    assert db.get_api_cache("steam", "tracklist-app", app_id=1495710) == {"source": "owned"}
    assert db.get_api_cache("steam", "tracklist-app") is None

    assert db.delete_api_cache_for_app(1495710) == 1
    assert db.get_api_cache("steam", "tracklist") == {"source": "shared"}
    assert db.get_api_cache("steam", "tracklist-app", app_id=1495710) is None


def test_api_cache_migrates_existing_schema(tmp_path: Path):
    import sqlite3

    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE api_cache (service TEXT, query_key TEXT, response_data TEXT, fetched_at TEXT, PRIMARY KEY (service, query_key))"
        )
        connection.execute(
            "INSERT INTO api_cache VALUES (?, ?, ?, ?)",
            ("mbz", "release", '{"ok": true}', "2999-01-01T00:00:00"),
        )

    db = DatabaseManager(db_path)

    assert db.get_api_cache("mbz", "release") == {"ok": True}
    columns = {row[1] for row in sqlite3.connect(db_path).execute("PRAGMA table_info(api_cache)")}
    assert "app_id" in columns
