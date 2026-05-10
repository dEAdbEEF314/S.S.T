import os
import json
import requests
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from rich.logging import RichHandler
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from .scanner import SteamScanner
from .processor import LocalProcessor
from .db import DatabaseManager
from .runner import JobRunner
from .models import LocalProcessResult

# Setup Logging
logger = logging.getLogger("scout")

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, case_sensitive=False, env_prefix="")
    steam_install_path: str
    steam_library_path: Optional[str] = None
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "data/sst_local_state.db"
    sst_output_dir: str = "output"
    steam_login_secure: Optional[str] = None
    steam_pics_bridge_url: str = "http://localhost:8080/v1/info/"
    steam_web_api_key: Optional[str] = None
    user_language: str = "ja"
    steam_language_full: str = "japanese"
    user_language_639_2: str = "jpn"
    log_level: str = "INFO"
    llm_backend: str = "GEMINI"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_limit_rpm: int = 15
    llm_limit_tpm: int = 10000000
    llm_limit_rpd: int = 1500
    max_encoding_tasks: int = 4
    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"
    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None
    metadata_source_priority: str = "MBZ,STEAM_PICS,STEAM_STORE,STEAM_TAGS,EMBEDDED"

def setup_logging(config: Config, console: Console, is_dev: bool = False):
    log_level_str = "DEBUG" if is_dev else config.log_level.upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    
    handlers = [RichHandler(level=numeric_level, console=console, rich_tracebacks=True, markup=True, show_path=False)]
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if is_dev or numeric_level == logging.DEBUG:
        # Unique log file per run for auditing
        log_file = log_dir / f"SST_DEBUG_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
    else:
        # Standard daily append log
        log_file = log_dir / f"SST_{datetime.now().strftime('%Y%m%d')}.log"

    
    handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)
    for lib in ["urllib3", "PIL", "musicbrainzngs", "requests", "mutagen"]: logging.getLogger(lib).setLevel(logging.ERROR)
    return log_file

def handle_db_reset(db_path: Path, console: Console):
    if not db_path.exists(): return console.print("Database not found.")
    console.print(f"[bold red]!!! WARNING: RESETTING DATABASE: {db_path} !!![/bold red]")
    # 3-Step Confirmation
    if not Confirm.ask("[Step 1/3] Clear ALL history?", console=console): return
    if input("[Step 2/3] Type 'YES' to proceed: ") != 'YES': return
    if input("[Step 3/3] Type 'DELETE' to finalize: ") == 'DELETE':
        db_path.unlink()
        console.print("[green]Database reset.[/green]")

def render_summary_table(results: List[LocalProcessResult], lang: str, console: Console):
    reviews = [r for r in results if r.status == "review"]
    if not reviews: return console.print("\n[bold green]All archived successfully![/bold green]")
    h = {"ja": ["AppID", "アルバム名", "判定", "確信度", "分析"], "en": ["AppID", "Album Name", "Status", "Conf.", "Analysis"]}.get(lang, ["AppID", "Album", "Status", "Conf.", "Analysis"])
    table = Table(title=f"\nItems Requiring Review ({len(reviews)})", title_style="bold yellow")
    for col in h: table.add_column(col)
    for r in reviews: table.add_row(str(r.app_id), r.album_name, r.status.capitalize(), f"{r.confidence_score}%", r.message)
    console.print(table)

def handle_finalize(config: Config, db: DatabaseManager, console: Console):
    from .tagger import AudioTagger
    from .utils import ensure_wsl_path
    from datetime import timezone, timedelta
    
    review_dir = ensure_wsl_path(config.sst_output_dir) / "review"
    if not review_dir.exists():
        return console.print(f"[yellow]Review directory not found: {review_dir}[/yellow]")

    folders = [f for f in review_dir.iterdir() if f.is_dir()]
    if not folders:
        return console.print("[yellow]No albums found in review directory.[/yellow]")

    console.print(f"[bold red]!!! WARNING: FINALIZING {len(folders)} ALBUMS FROM REVIEW !!![/bold red]")
    console.print("[dim]This will ingest metadata from files and update the database history.[/dim]")
    
    # 3-Step Confirmation
    if not Confirm.ask("[Step 1/3] Proceed with finalization?", console=console): return
    if input("[Step 2/3] Type 'YES' to proceed: ") != 'YES': return
    if input("[Step 3/3] Type 'FINALIZE' to confirm: ") != 'FINALIZE': return

    console.print(f"[bold blue]Finalizing {len(folders)} albums...[/bold blue]")
    
    for album_dir in folders:
        # Extract AppID from folder name (format: APPID_Name)
        try:
            app_id = int(album_dir.name.split('_')[0])
        except (ValueError, IndexError):
            console.print(f"[red]Skipping {album_dir.name}: Could not extract AppID.[/red]")
            continue

        audio_files = []
        for ext in [".mp3", ".aif", ".flac", ".wav"]:
            audio_files.extend(list(album_dir.rglob(f"*{ext}")))
        
        if not audio_files:
            console.print(f"[yellow]Skipping {album_dir.name}: No audio files found.[/yellow]")
            continue

        # Extract metadata from the first audio file as a representative
        representative_tags = AudioTagger.read_tags(audio_files[0])
        album_name = representative_tags.get("album") or album_dir.name.split('_', 1)[1].replace('_', ' ')
        
        processed_at = datetime.now(timezone(timedelta(hours=9))).isoformat()
        
        # Build a minimal summary_meta based on what we can see now
        summary_meta = {
            "app_id": app_id,
            "album_name": album_name,
            "status": "archive",
            "processed_at": processed_at,
            "tracks": [{"file_path": str(p.relative_to(album_dir)), "tags": AudioTagger.read_tags(p)} for p in audio_files],
            "note": "Finalized by user review"
        }
        
        db.record_processed(app_id, "archive", album_name, processed_at, summary_meta)
        console.print(f"[green]✓ {album_name} (AppID: {app_id}) finalized and recorded as archived.[/green]")

    console.print("\n[bold green]Finalization complete. The S.S.T database has been updated.[/bold green]")
    console.print("[dim]Note: Files were not deleted. You can now move them to your library.[/dim]")

def fetch_steam_userdata(config: Config, console: Console):
    if not config.steam_login_secure:
        return
    
    console.print("[dim]Fetching Steam userdata.json...[/dim]")
    url = "https://store.steampowered.com/dynamicstore/userdata/"
    cookies = {"steamLoginSecure": config.steam_login_secure}
    try:
        r = requests.get(url, cookies=cookies, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        with open(data_dir / "userdata.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        console.print("[green]✓ Steam userdata.json updated.[/green]")
    except Exception as e:
        console.print(f"[yellow]! Failed to fetch Steam userdata: {e}[/yellow]")

def main():
    parser = argparse.ArgumentParser(description="SST Scout")
    parser.add_argument("--all", action="store_true", help="Process all unprocessed soundtracks")
    parser.add_argument("--limit", "-n", type=int)
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--appid", type=int)
    parser.add_argument("--dev", action="store_true", help="Run in development mode (DEBUG logs, unique log files)")
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--finalize", action="store_true", help="Ingest corrected metadata from review folders into DB")
    args = parser.parse_args()
    console = Console()

    # If no specific action is provided, show help and exit (safety gate)
    if not any([args.all, args.limit, args.appid, args.reset_db, args.finalize]):
        parser.print_help()
        return

    # Load configuration
    try:
        config = Config()
        config.steam_language_full = {"ja": "japanese", "en": "english"}.get(config.user_language, "english")
        config.user_language_639_2 = {"ja": "jpn", "en": "eng"}.get(config.user_language, "eng")
    except Exception as e: return console.print(f"[red]Config error: {e}[/red]")

    fetch_steam_userdata(config, console)

    if args.reset_db: return handle_db_reset(Path(config.sst_db_path), console)
    
    db = DatabaseManager(Path(config.sst_db_path))
    if args.finalize: return handle_finalize(config, db, console)

    log_file = setup_logging(config, console, is_dev=args.dev)
    logger.info(f"SST starting. Log level: {config.log_level}. File: {log_file}")

    scanner = SteamScanner(
        install_path=config.steam_install_path, 
        db=db,
        bridge_url=config.steam_pics_bridge_url,
        api_key=config.steam_web_api_key,
        override_library_path=config.steam_library_path,
        cache_path="data/scout_cache.json", 
        language=config.steam_language_full
    )
    processor = LocalProcessor(config, db)
    runner = JobRunner(config, processor, console)

    soundtracks = scanner.find_soundtracks(force=args.force, limit=args.limit, is_processed_callback=db.is_already_processed, target_appid=args.appid)
    if not soundtracks: return logger.info("No soundtracks found.")

    start_time = datetime.now()
    results = runner.run(soundtracks)
    duration_str = str(datetime.now() - start_time).split('.')[0]

    console.print(f"\n[bold blue]🏁 Complete! Total Time: {duration_str}[/bold blue]\n")
    
    # Notify completion
    reviews = [r for r in results if r.status == "review"]
    summary_str = f"Processed {len(results)} albums. {len(reviews)} need review."
    processor.notifier.notify_completion("Run Complete", summary_str, [{"name": "Success", "value": str(len(results)-len(reviews)), "inline": True}, {"name": "Review", "value": str(len(reviews)), "inline": True}])
    
    render_summary_table(results, config.user_language, console)

if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
