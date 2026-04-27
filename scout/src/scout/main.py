import os
import json
import logging
import argparse
import multiprocessing
from typing import Optional, List
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.logging import RichHandler
from rich.table import Table
from rich.console import Console

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
        env_prefix="" # Ensure no prefix issues
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

    # Notification Settings
    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None

def main():
    # Argument Parsing
    parser = argparse.ArgumentParser(description="SST Scout - Local Processor for Steam Soundtracks.")
    parser.add_argument("--limit", "-n", type=int, help="Limit the number of soundtracks to process.")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-processing of already completed albums.")
    parser.add_argument("--appid", type=int, help="Target a specific AppID for processing.")
    parser.add_argument("--reset-db", action="store_true", help="Reset the local processed database (requires 3 confirmations).")

    args = parser.parse_args()

    # Act-11: Forcefully prioritize .env by cleaning OS environment variables first
    for key in ["LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"]:
        if key in os.environ:
            del os.environ[key]

    load_dotenv()
    try:
        config = Config()
        
        # ISO 639-1 to Steam Full Name Mapping
        steam_lang_map = {"ja": "japanese", "en": "english", "zh": "chinese", "ko": "korean"}
        config.steam_language_full = steam_lang_map.get(config.user_language, "english")
        
        # ISO 639-1 to ISO 639-2 Mapping for ID3 TLAN
        iso639_2_map = {"ja": "jpn", "en": "eng", "zh": "zho", "ko": "kor"}
        config.user_language_639_2 = iso639_2_map.get(config.user_language, "eng")
        
    except Exception as e:
        print(f"Configuration error: {e}")
        return

    # Handle DB Reset
    if args.reset_db:
        from rich.prompt import Confirm
        db_file = Path(config.sst_db_path)
        if not db_file.exists():
            print("Database file does not exist. Nothing to reset.")
            return
            
        console = Console()
        console.print(f"[bold red]!!! WARNING: You are about to delete the database: {db_file} !!![/bold red]")
        
        try:
            if not Confirm.ask("Are you absolutely sure you want to reset the database?", console=console):
                return
            if not Confirm.ask("This will clear ALL history of processed albums. Continue?", console=console):
                return
            
            # Final text confirmation
            final_check = input("FINAL CONFIRMATION: Type 'DELETE' to confirm: ")
            if final_check != 'DELETE':
                console.print("[yellow]Reset cancelled.[/yellow]")
                return
            
            db_file.unlink()
            console.print(f"[green]Database {db_file} has been successfully reset.[/green]")
            return
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Reset aborted.[/yellow]")
            return

    # Logging Setup with Rich
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    log_format = "%(message)s" 
    
    handlers = []
    
    # 1. Stdout Handler (Console via Rich)
    # In production, we keep console clean for the progress bars
    console_level = logging.WARNING if config.env_mode == "production" else numeric_level
    rich_handler = RichHandler(
        level=console_level,
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        show_level=True,
        show_time=True
    )
    handlers.append(rich_handler)
    
    # 2. File Handler (Persistent logs)
    if config.env_mode == "production" or numeric_level <= logging.INFO:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"sst_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        handlers.append(file_handler)

    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True
    )
    
    console = Console()
    logger.info(f"SST Local Processor starting in [bold cyan]{config.env_mode}[/bold cyan] mode")
    if config.env_mode == "production":
        logger.info(f"Detailed logs redirected to [yellow]{log_file}[/yellow]")

    # Act-12: Dynamic Album Workers Calculation
    cpu_count = multiprocessing.cpu_count()
    
    if config.llm_force_local:
        # Act-12: Limit parallel albums in local mode to avoid server overload/timeouts
        calculated_workers = min(cpu_count, 4)
        logger.info(f"Force Local Mode: Bypassing RPM limits. Using load-balanced limit: {calculated_workers}")
    else:
        calculated_workers = min(int(config.llm_limit_rpm * 0.7), cpu_count * 2, 10)
    
    max_album_workers = max(1, calculated_workers)
    
    logger.info(f"Execution Profile: Max Album Workers={max_album_workers}, Parallel Encoding={config.max_encoding_tasks}")

    scanner = SteamScanner(
        config.steam_library_path,
        cache_path="data/scout_cache.json",
        language=config.steam_language_full
    )

    processor = LocalProcessor(config)
    notifier = processor.notifier # Re-use the same notifier

    logger.info(f"Scanning library: {config.steam_library_path}")
    soundtracks = scanner.find_soundtracks(
        force=args.force, 
        limit=args.limit,
        is_processed_callback=processor.is_processed,
        target_appid=args.appid
    )
    
    if not soundtracks:
        logger.info("No active soundtracks found.")
        return

    logger.info(f"Queueing {len(soundtracks)} soundtracks for local processing.")

    from concurrent.futures import ThreadPoolExecutor
    
    results: List[LocalProcessResult] = []
    start_time = datetime.now()

    def _process_single_album(ost, progress, task_id):
        app_id = ost["app_id"]
        install_dir = Path(ost["install_dir"])
        
        steam_meta = SteamMetadata(
            app_id=app_id,
            name=ost["name"],
            developer=ost.get("developer"),
            publisher=ost.get("publisher"),
            url=ost.get("url"),
            tags=ost.get("tags", []),
            genre=ost.get("genre"),
            release_date=ost.get("release_date"),
            parent_app_id=ost.get("parent_app_id"),
            parent_name=ost.get("parent_name"),
            parent_tags=ost.get("parent_tags", []),
            parent_genre=ost.get("parent_genre"),
            parent_release_date=ost.get("parent_release_date"),
            header_image_url=ost.get("header_image_url")
        )

        result = processor.process_album(app_id, install_dir, steam_meta)
        results.append(result)
        
        # Advance the progress bar
        progress.update(task_id, advance=1, description=f"Finished: {ost['name']}")
        
        if result.status == "archive":
            logger.info(f"Successfully archived App ID {app_id}: {ost['name']}")
        elif result.status == "review":
            logger.warning(f"Sent App ID {app_id} to review: {result.message}")
        else:
            logger.error(f"Failed to process App ID {app_id}: {result.message}")

    try:
        # Use Rich Progress Bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            overall_task = progress.add_task("Processing Albums...", total=len(soundtracks))
            
            with ThreadPoolExecutor(max_workers=max_album_workers) as executor:
                list(executor.map(lambda ost: _process_single_album(ost, progress, overall_task), soundtracks))
    finally:
        # Act-12: Ensure terminal state is clean
        console.show_cursor(True)
    
    end_time = datetime.now()
    duration = end_time - start_time
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

    # --- Final Summary Table (Review Items Only) ---
    review_items = [r for r in results if r.status == "review"]
    
    console.print(f"\n[bold blue]🏁 Processing Complete![/bold blue]")
    console.print(f"  - Start Time:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  - End Time:    {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  - Total Time:   [bold green]{duration_str}[/bold green]\n")
    
    # --- Act-13: Send Completion Summary to Discord ---
    review_list_str = ""
    if review_items:
        review_list_str = "\n\n**Review Required:**\n" + "\n".join([f"• `{r.app_id}` {r.album_name} ({r.confidence_score}%)" for r in review_items[:15]])
        if len(review_items) > 15:
            review_list_str += f"\n*...and {len(review_items) - 15} more.*"

    comp_fields = [
        {"name": "Total Albums", "value": str(len(results)), "inline": True},
        {"name": "Success", "value": str(len([r for r in results if r.status == "archive"])), "inline": True},
        {"name": "Review Required", "value": str(len(review_items)), "inline": True},
        {"name": "Start Time", "value": start_time.strftime('%Y-%m-%d %H:%M:%S'), "inline": False},
        {"name": "Duration", "value": duration_str, "inline": True}
    ]
    notifier.notify_completion(
        "Total Processing Run Complete", 
        f"Finished processing {len(results)} albums.{review_list_str}", 
        comp_fields
    )
    
    if review_items:
        # Localization
        headers_map = {
            "ja": ["AppID", "アルバム名", "判定", "確信度", "分析"],
            "en": ["AppID", "Album Name", "Status", "Conf.", "Analysis"]
        }
        lang = config.user_language if config.user_language in headers_map else "en"
        h = headers_map[lang]

        table = Table(title=f"\nItems Requiring Review ({len(review_items)})", title_style="bold yellow")
        table.add_column(h[0], style="cyan", no_wrap=True)
        table.add_column(h[1], style="magenta", min_width=20)
        table.add_column(h[2], style="yellow", width=12)
        table.add_column(h[3], justify="right", style="green")
        table.add_column(h[4], style="white", width=60) # Allow wrapping within 60 chars

        for item in review_items:
            table.add_row(
                str(item.app_id),
                item.album_name,
                item.status.capitalize(),
                f"{item.confidence_score}%",
                item.message # Show the semantic reason here
            )
        
        console.print(table)
    else:
        console.print("\n[bold green]All items processed successfully! No reviews required.[/bold green]")

if __name__ == "__main__":
    main()
