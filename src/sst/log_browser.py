import sqlite3
import json
import argparse
import os
from pathlib import Path
from dotenv import dotenv_values
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def resolve_db_path(db_path: str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)

    dotenv_settings = {
        key.upper(): value for key, value in dotenv_values(".env").items()
    }
    configured_path = os.getenv("SST_DB_PATH") or dotenv_settings.get("SST_DB_PATH")
    return Path(configured_path or "data/sst_local_state.db")


def show_stats(db_path: Path):
    if not db_path.exists():
        console.print(f"[yellow]データベースが見つかりません: {db_path}[/yellow]")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT status, count(*) FROM processed_albums GROUP BY status"
            ).fetchall()
    except sqlite3.Error as error:
        console.print(f"[red]統計を読み込めませんでした: {error}[/red]")
        return

    if not rows:
        console.print("[yellow]処理履歴が見つかりません。[/yellow]")
        return

    table = Table(title="S.S.T 処理統計", title_style="bold blue")
    table.add_column("判定", style="bold")
    table.add_column("件数", justify="right")
    for status, count in rows:
        table.add_row(str(status), str(count))
    console.print(table)


def load_history(db_path: Path, limit: int = 20):
    if not db_path.exists():
        console.print(f"[red]データベースが見つかりません: {db_path}[/red]")
        return []
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT app_id, status, album_name, processed_at, metadata_json FROM processed_albums ORDER BY processed_at DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

def show_list(db_path: Path, limit: int = 20):
    rows = load_history(db_path, limit)
    if not rows:
        console.print("[yellow]処理履歴が見つかりません。[/yellow]")
        return

    table = Table(title="S.S.T 処理履歴", title_style="bold blue")
    table.add_column("AppID", style="cyan", no_wrap=True)
    table.add_column("日付", style="dim")
    table.add_column("アルバム名", style="magenta")
    table.add_column("判定", style="bold")
    table.add_column("確信度", justify="right")

    for row in rows:
        meta = json.loads(row["metadata_json"])
        status = row["status"].upper()
        status_style = "green" if status == "ARCHIVE" else "yellow" if status == "REVIEW" else "red"
        
        table.add_row(
            str(row["app_id"]),
            row["processed_at"][:16].replace("T", " "),
            row["album_name"],
            f"[{status_style}]{status}[/{status_style}]",
            f"{meta.get('confidence_score', 0)}%"
        )
    
    console.print(table)

def show_detail(db_path: Path, app_id: int):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM processed_albums WHERE app_id = ?", (app_id,)
        )
        row = cur.fetchone()
        
    if not row:
        console.print(f"[red]AppIDの記録が見つかりません: {app_id}[/red]")
        return

    meta = json.loads(row["metadata_json"])
    
    # Header Panel
    console.print(Panel(
        f"[bold magenta]{row['album_name']}[/bold magenta]\n"
        f"AppID: {row['app_id']} | Status: {row['status'].upper()} | Conf: {meta.get('confidence_score')}%",
        title="アルバム詳細", border_style="blue"
    ))

    # Reasoning
    console.print("\n[bold yellow]分析 / 理由:[/bold yellow]")
    console.print(meta.get("confidence_reason", "N/A"))

    # Tracks with issues
    tracks = meta.get("tracks", [])
    review_tracks = [t for t in tracks if t["tags"].get("track_number") == "0" or t["tags"].get("title") == "Unknown"]
    
    if review_tracks:
        console.print(f"\n[bold red]要注意トラック ({len(review_tracks)}):[/bold red]")
        track_table = Table(box=None)
        track_table.add_column("ファイル")
        track_table.add_column("理由")
        
        for t in review_tracks:
            filename = t.get("original_filename") or t.get("file_path") or "Unknown"
            track_table.add_row(filename, t.get("source", "Unknown error"))
        console.print(track_table)
    else:
        console.print("\n[green]トラックレベルの問題は検出されませんでした。[/green]")

def main():
    parser = argparse.ArgumentParser(description="SST Log Browser")
    parser.add_argument("appid", type=int, nargs="?", help="Show details for a specific AppID")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Number of items to show")
    parser.add_argument("--db", type=str, help="Path to database")
    parser.add_argument("--stats", action="store_true", help="Show processing statistics")
    
    args = parser.parse_args()
    db_path = resolve_db_path(args.db)
    
    if args.stats:
        show_stats(db_path)
    elif args.appid:
        show_detail(db_path, args.appid)
    else:
        show_list(db_path, args.limit)

if __name__ == "__main__":
    main()
