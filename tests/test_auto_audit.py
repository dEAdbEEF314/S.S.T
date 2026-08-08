import importlib.util
import sqlite3
from pathlib import Path


def test_batch_inspector_compatibility_script_exposes_canonical_report_api(tmp_path):
    db_path = tmp_path / "state.db"
    output_dir = tmp_path / "report"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE processed_albums (
                app_id INTEGER,
                album_name TEXT,
                status TEXT,
                metadata_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO processed_albums VALUES (?, ?, ?, ?)",
            (100, "Synthetic OST", "review", "{}"),
        )

    script_path = Path(
        ".agents/skills/sst-batch-inspector/scripts/generate_html_report.py"
    )
    spec = importlib.util.spec_from_file_location("batch_inspector_report", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.analyze_and_generate_report(db_path, output_dir)

    assert (output_dir / "batch_analysis_report.html").is_file()