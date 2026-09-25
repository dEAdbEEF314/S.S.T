import sqlite3
import sys
from pathlib import Path

from sst.log_browser import main, resolve_db_path


def test_resolve_db_path_reads_dotenv_value(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SST_DB_PATH", raising=False)
    (tmp_path / ".env").write_text('SST_DB_PATH="custom/state.db"\n')

    assert resolve_db_path() == Path("custom/state.db")


def test_stats_reads_configured_database(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SST_DB_PATH", raising=False)
    database_path = tmp_path / "custom/state.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE processed_albums (status TEXT)")
        connection.executemany(
            "INSERT INTO processed_albums (status) VALUES (?)",
            [("ARCHIVE",), ("ARCHIVE",), ("REVIEW",)],
        )
    (tmp_path / ".env").write_text(f"SST_DB_PATH={database_path}\n")
    monkeypatch.setattr(sys, "argv", ["sst-log-browser", "--stats"])

    main()

    output = capsys.readouterr().out
    assert "ARCHIVE" in output
    assert "REVIEW" in output
    assert "2" in output