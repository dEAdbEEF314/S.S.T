import os
import json
import logging
import argparse
import multiprocessing
import time
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.logging import RichHandler
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from .scanner import SteamScanner
from .processor import LocalProcessor
from .models import SteamMetadata, LocalProcessResult

# Setup Logging
logger = logging.getLogger("scout")

class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore",
        env_ignore_empty=True,
        case_sensitive=False,
        env_prefix=""
    )

    steam_library_path: str
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "data/sst_local_state.db"
    user_language: str = "ja"
    steam_language_full: str = "japanese"
    user_language_639_2: str = "jpn"
    env_mode: str = "production"
    log_level: str = "INFO"
    llm_base_url: str
    llm_api_key: Optional[str] = None
    llm_model: str = "gemma-4-31b-it"
    llm_limit_rpm: int = 15
    llm_limit_tpm: int = 10000000
    llm_limit_rpd: int = 1500
    llm_force_local: bool = False
    max_encoding_tasks: int = 4
    metadata_source_priority: str = "MBZ,STEAM,EMBEDDED"
    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"

    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None

def setup_logging(config: Config, console: Console):
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    handlers = []
    
    console_level = logging.ERROR if config.env_mode == "production" else numeric_level
    rich_handler = RichHandler(
        level=console_level,
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        show_level=True,
        show_time=True
    )
    handlers.append(rich_handler)
    
    log_file = None
    if config.env_mode == "production" or numeric_level <= logging.INFO:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"sst_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        handlers.append(file_handler)

    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)
    
    # Silence noisy libs
    for logger_name in ["urllib3", "PIL", "musicbrainzngs", "requests", "mutagen"]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)
    
    return log_file

def handle_db_reset(db_path: Path, console: Console):
    if not db_path.exists():
        console.print("Database file does not exist. Nothing to reset.")
        return
        
    console.print(f"[bold red]!!! WARNING: You are about to delete the database: {db_path} !!![/bold red]")
    if not Confirm.ask("Are you absolutely sure you want to reset the database?", console=console): return
    if not Confirm.ask("This will clear ALL history of processed albums. Continue?", console=console): return
    
    final_check = input("FINAL CONFIRMATION: Type 'DELETE' to confirm: ")
    if final_check == 'DELETE':
        db_path.unlink()
        console.print(f"[green]Database {db_path} has been successfully reset.[/green]")
    else:
        console.print("[yellow]Reset cancelled.[/yellow]")

def render_summary_table(results: List[LocalProcessResult], user_language: str, console: Console):
    review_items = [r for r in results if r.status == "review"]
    if not review_items:
        console.print("\n[bold green]All items processed successfully! No reviews required.[/bold green]")
        return

    headers_map = {
        "ja": ["AppID", "アルバム名", "判定", "確信度", "分析"],
        "en": ["AppID", "Album Name", "Status", "Conf.", "Analysis"]
    }
    lang = user_language if user_language in headers_map else "en"
    h = headers_map[lang]

    table = Table(title=f"\nItems Requiring Review ({len(review_items)})", title_style="bold yellow")
    table.add_column(h[0], style="cyan", no_wrap=True)
    table.add_column(h[1], style="magenta", min_width=20)
    table.add_column(h[2], style="yellow", width=12)
    table.add_column(h[3], justify="right", style="green")
    table.add_column(h[4], style="white", width=60)

    for item in review_items:
        table.add_row(str(item.app_id), item.album_name, item.status.capitalize(), f"{item.confidence_score}%", item.message)
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="SST Scout - Local Processor for Steam Soundtracks.")
    parser.add_argument("--limit", "-n", type=int, help="Limit number of soundtracks.")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-processing.")
    parser.add_argument("--appid", type=int, help="Target specific AppID.")
    parser.add_argument("--reset-db", action="store_true", help="Reset database.")

    args = parser.parse_args()
    console = Console()

    # Priority cleanup
    for key in ["LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"]:
        if key in os.environ: del os.environ[key]

    load_dotenv()
    try:
        config = Config()
        config.steam_language_full = {"ja": "japanese", "en": "english", "zh": "chinese", "ko": "korean"}.get(config.user_language, "english")
        config.user_language_639_2 = {"ja": "jpn", "en": "eng", "zh": "zho", "ko": "kor"}.get(config.user_language, "eng")
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        return

    if args.reset_db:
        handle_db_reset(Path(config.sst_db_path), console)
        return

    log_file = setup_logging(config, console)
    logger.info(f"SST Local Processor starting in [bold cyan]{config.env_mode}[/bold cyan] mode")
    if config.env_mode == "production": logger.info(f"Logs: [yellow]{log_file}[/yellow]")

    # Worker calculation
    cpu_count = multiprocessing.cpu_count()
    if config.llm_force_local:
        max_album_workers = min(cpu_count, 4)
    else:
        max_album_workers = max(1, min(int(config.llm_limit_rpm * 0.7), cpu_count * 2, 10))

    scanner = SteamScanner(config.steam_library_path, cache_path="data/scout_cache.json", language=config.steam_language_full)
    processor = LocalProcessor(config)
    
    soundtracks = scanner.find_soundtracks(force=args.force, limit=args.limit, 
                                           is_processed_callback=processor.is_processed, target_appid=args.appid)
    if not soundtracks:
        logger.info("No active soundtracks found.")
        return

    from concurrent.futures import ThreadPoolExecutor
    results: List[LocalProcessResult] = []
    start_time = datetime.now()

    def _process_single_album(ost, progress, overall_task):
        album_task = progress.add_task(f"[cyan]Mapping: {ost['name']}", total=None)
        steam_meta = SteamMetadata(app_id=ost["app_id"], name=ost["name"], developer=ost.get("developer"),
                                    publisher=ost.get("publisher"), url=ost.get("url"), tags=ost.get("tags", []),
                                    genre=ost.get("genre"), release_date=ost.get("release_date"),
                                    parent_app_id=ost.get("parent_app_id"), parent_name=ost.get("parent_name"),
                                    parent_tags=ost.get("parent_tags", []), parent_genre=ost.get("parent_genre"),
                                    parent_release_date=ost.get("parent_release_date"), header_image_url=ost.get("header_image_url"))

        all_files = processor._list_audio_files(Path(ost["install_dir"]))
        progress.update(album_task, description=f"[yellow]Processing: {ost['name']}", total=len(all_files))

        result = processor.process_album(ost["app_id"], Path(ost["install_dir"]), steam_meta,
                                         on_track_complete=lambda: progress.advance(album_task))
        results.append(result)
        progress.remove_task(album_task)
        progress.update(overall_task, advance=1)
        
        status_color = "green" if result.status == "archive" else "yellow"
        console.print(f"[bold {status_color}]✓[/bold {status_color}] {ost['name']} -> [bold]{result.status.upper()}[/bold]")

    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                      BarColumn(), TaskProgressColumn(), TimeRemainingColumn(), 
                      console=console, expand=True) as progress:
            overall_task = progress.add_task("[bold blue]Overall Progress", total=len(soundtracks))
            with ThreadPoolExecutor(max_workers=max_album_workers) as executor:
                list(executor.map(lambda ost: _process_single_album(ost, progress, overall_task), soundtracks))
    finally:
        console.show_cursor(True)
    
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0] # Simple H:M:S

    console.print(f"\n[bold blue]🏁 Processing Complete![/bold blue]")
    console.print(f"  - Total Time: [bold green]{duration_str}[/bold green]\n")
    
    # Notifications
    review_items = [r for r in results if r.status == "review"]
    review_list_str = "\n\n**Review Required:**\n" + "\n".join([f"• `{r.app_id}` {r.album_name} ({r.confidence_score}%)" for r in review_items[:15]])
    if len(review_items) > 15: review_list_str += f"\n*...and {len(review_items) - 15} more.*"
    
    comp_fields = [{"name": "Total", "value": str(len(results)), "inline": True},
                   {"name": "Success", "value": str(len(results)-len(review_items)), "inline": True},
                   {"name": "Review", "value": str(len(review_items)), "inline": True},
                   {"name": "Duration", "value": duration_str, "inline": False}]
    processor.notifier.notify_completion("Run Complete", f"Processed {len(results)} albums.{review_list_str}", comp_fields)
    
    render_summary_table(results, config.user_language, console)

if __name__ == "__main__":
    main()
