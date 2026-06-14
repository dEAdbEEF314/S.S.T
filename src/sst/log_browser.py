import sqlite3
import json
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

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
    parser.add_argument("--db", type=str, default="data/sst_local_state.db", help="Path to database")
    
    args = parser.parse_args()
    db_path = Path(args.db)
    
    if args.appid:
        show_detail(db_path, args.appid)
    else:
        show_list(db_path, args.limit)

if __name__ == "__main__":
    main()
