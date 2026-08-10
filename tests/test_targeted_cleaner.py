import json
import sqlite3
import importlib.util
from pathlib import Path

_CLEANER_PATH = Path(__file__).parents[1] / "skills" / "sst-cleaner" / "scripts" / "clean_system.py"
_SPEC = importlib.util.spec_from_file_location("clean_system", _CLEANER_PATH)
clean_system = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(clean_system)


class FakeConfig:
    def __init__(self, root: Path):
        self.sst_db_path = str(root / "state.db")
        self.sst_output_dir = str(root / "output")
        self.sst_working_dir = str(root / "sst-work")


def test_targeted_cleaner_preserves_other_appid_data(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE processed_albums (app_id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE steam_store_data (app_id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE api_cache (service TEXT, query_key TEXT, app_id INTEGER, response_data TEXT, fetched_at TEXT, PRIMARY KEY(service, query_key))")
        connection.executemany("INSERT INTO processed_albums VALUES (?)", [(1,), (2,)])
        connection.executemany("INSERT INTO steam_store_data VALUES (?)", [(1,), (2,)])
        connection.executemany("INSERT INTO api_cache VALUES (?, ?, ?, ?, ?)", [("steam", "one", 1, "{}", "2999-01-01T00:00:00"), ("steam", "two", 2, "{}", "2999-01-01T00:00:00")])

    cache_path = tmp_path / "data" / "sst_cache.json"
    cache_path.parent.mkdir()
    cache_path.write_text(json.dumps({"enriched": {"1": {"name": "one"}, "2": {"name": "two"}}}), encoding="utf-8")

    for status in ("archive", "review"):
        output_dir = tmp_path / "output" / status
        output_dir.mkdir(parents=True)
        (output_dir / "1_one.zip").write_bytes(b"one")
        (output_dir / "2_two.zip").write_bytes(b"two")

    work_dir = tmp_path / "sst-work"
    work_dir.mkdir()
    for name in ("final_1_run", "buffer_1_run", "final_2_run", "buffer_2_run"):
        (work_dir / name).mkdir()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clean_system, "Config", lambda: FakeConfig(tmp_path))
    clean_system.clean(keep_cache=False, app_ids=[1])

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT app_id FROM processed_albums").fetchall() == [(2,)]
        assert connection.execute("SELECT app_id FROM steam_store_data").fetchall() == [(2,)]
        assert connection.execute("SELECT app_id FROM api_cache").fetchall() == [(2,)]

    remaining_cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "1" not in remaining_cache["enriched"]
    assert remaining_cache["enriched"]["2"] == {"name": "two"}
    assert not (tmp_path / "output" / "archive" / "1_one.zip").exists()
    assert (tmp_path / "output" / "archive" / "2_two.zip").exists()
    assert not (work_dir / "final_1_run").exists()
    assert (work_dir / "final_2_run").exists()


def test_force_cleanup_removes_only_requested_appids(tmp_path: Path):
    from sst.processor import LocalProcessor

    working_dir = tmp_path / "sst-work"
    working_dir.mkdir()
    for name in ("final_1_old", "buffer_1_old", "final_2_old", "buffer_2_old"):
        (working_dir / name).mkdir()

    processor = object.__new__(LocalProcessor)
    processor.working_dir = working_dir

    assert processor.cleanup_force_working_dirs([1]) == 2
    assert not (working_dir / "final_1_old").exists()
    assert not (working_dir / "buffer_1_old").exists()
    assert (working_dir / "final_2_old").exists()
    assert (working_dir / "buffer_2_old").exists()
