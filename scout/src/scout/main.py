import os
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
    handlers = [RichHandler(level=logging.ERROR if config.env_mode == "production" else numeric_level, console=console, rich_tracebacks=True, markup=True, show_path=False)]
    
    log_file = None
    if config.env_mode == "production" or numeric_level <= logging.INFO:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"sst_{datetime.now().strftime('%Y%m%d')}.log"
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)
    for lib in ["urllib3", "PIL", "musicbrainzngs", "requests", "mutagen"]: logging.getLogger(lib).setLevel(logging.ERROR)
    return log_file

def handle_db_reset(db_path: Path, console: Console):
    if not db_path.exists(): return console.print("Database not found.")
    console.print(f"[bold red]!!! WARNING: RESETTING DATABASE: {db_path} !!![/bold red]")
    if not Confirm.ask("Clear ALL history?", console=console): return
    if input("Type 'DELETE' to confirm: ") == 'DELETE':
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

def main():
    parser = argparse.ArgumentParser(description="SST Scout")
    parser.add_argument("--limit", "-n", type=int)
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--appid", type=int)
    parser.add_argument("--reset-db", action="store_true")
    args = parser.parse_args()
    console = Console()

    for key in ["LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"]: 
        if key in os.environ: del os.environ[key]
    load_dotenv()
    try:
        config = Config()
        config.steam_language_full = {"ja": "japanese", "en": "english"}.get(config.user_language, "english")
        config.user_language_639_2 = {"ja": "jpn", "en": "eng"}.get(config.user_language, "eng")
    except Exception as e: return console.print(f"[red]Config error: {e}[/red]")

    if args.reset_db: return handle_db_reset(Path(config.sst_db_path), console)

    log_file = setup_logging(config, console)
    logger.info(f"SST starting in {config.env_mode} mode. Logs: {log_file}")

    db = DatabaseManager(Path(config.sst_db_path))
    scanner = SteamScanner(config.steam_library_path, cache_path="data/scout_cache.json", language=config.steam_language_full)
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
