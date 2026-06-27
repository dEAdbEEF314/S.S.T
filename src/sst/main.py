import json
import requests
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List

from rich.logging import RichHandler
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from .scanner import SteamScanner
from .processor import LocalProcessor
from .db import DatabaseManager
from .runner import JobRunner
from .models import LocalProcessResult
from .config import Config

# Setup Logging
logger = logging.getLogger("sst")

def setup_logging(config: Config, console: Console, is_dev: bool = False):
    log_level_str = "DEBUG" if is_dev else config.log_level.upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    
    # Standard format with timestamps
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers = [RichHandler(
        level=numeric_level, 
        console=console, 
        rich_tracebacks=True, 
        markup=True, 
        show_path=False,
        omit_repeated_times=False
    )]
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if is_dev or numeric_level == logging.DEBUG:
        # Unique log file per run for auditing
        log_file = log_dir / f"SST_DEBUG_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
    else:
        # Standard daily append log
        log_file = log_dir / f"SST_{datetime.now().strftime('%Y%m%d')}.log"

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(file_handler)
    
    logging.basicConfig(
        level=numeric_level, 
        handlers=handlers, 
        force=True
    )
    for lib in ["urllib3", "PIL", "musicbrainzngs", "requests", "mutagen"]: logging.getLogger(lib).setLevel(logging.ERROR)
    return log_file

def handle_db_reset(db_path: Path, console: Console):
    if not db_path.exists(): return console.print("データベースが見つかりません。")
    console.print(f"[bold red]!!! 警告: データベースをリセットします: {db_path} !!![/bold red]")
    # 3-Step Confirmation
    if not Confirm.ask("[Step 1/3] すべての履歴を消去しますか？", console=console): return
    if input("[Step 2/3] 続行するには 'YES' と入力してください: ") != 'YES': return
    if input("[Step 3/3] 完了するには 'DELETE' と入力してください: ") == 'DELETE':
        db_path.unlink()
        console.print("[green]データベースがリセットされました。[/green]")

def render_summary_table(results: List[LocalProcessResult], lang: str, console: Console):
    reviews = [r for r in results if r.status == "review"]
    if not reviews: return console.print("\n[bold green]すべて正常にアーカイブされました！[/bold green]")
    h = {"ja": ["AppID", "アルバム名", "判定", "確信度", "分析"], "en": ["AppID", "Album Name", "Status", "Conf.", "Analysis"]}.get(lang, ["AppID", "Album", "Status", "Conf.", "Analysis"])
    table = Table(title=f"\nレビューが必要なアイテム ({len(reviews)})", title_style="bold yellow")
    for col in h: table.add_column(col)
    for r in reviews: table.add_row(str(r.app_id), r.album_name, r.status.capitalize(), f"{r.confidence_score}%", r.message)
    console.print(table)

def fetch_steam_userdata(config: Config, console: Console):
    if not config.steam_login_secure:
        return
    
    console.print("[dim]Steamのuserdata.jsonを取得しています...[/dim]")
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
        console.print("[green]✓ Steamのuserdata.jsonが更新されました。[/green]")
    except Exception as e:
        console.print(f"[yellow]! Steamのuserdataの取得に失敗しました: {e}[/yellow]")

def handle_all_confirm(console: Console):
    console.print("[bold red]!!! 警告: ライブラリ全体の処理を開始します !!![/bold red]")
    console.print("[dim]これには長い時間と大量のLLMトークンがかかる可能性があります。[/dim]")
    # 3-Step Confirmation
    if not Confirm.ask("[Step 1/3] 未処理のサウンドトラックをすべて処理しますか？", console=console): return False
    if input("[Step 2/3] 続行するには 'YES' と入力してください: ") != 'YES': return False
    if input("[Step 3/3] 開始するには 'START' と入力してください: ") != 'START': return False
    return True

def handle_fingerprint_all_confirm(console: Console):
    console.print("[bold red]!!! 警告: 全トラックフィンガープリントモードを有効にします !!![/bold red]")
    console.print("[yellow]このモードではAcoustIDを使用してアルバムの全トラックをスキャンします。[/yellow]")
    console.print("[dim]APIのレート制限により、トラックごとに1.5〜2.0秒の遅延が発生します。[/dim]")
    console.print("[dim]100トラックのアルバムの場合、1アルバムあたり少なくとも3〜4分かかります。[/dim]")
    
    # 3-Step Confirmation
    if not Confirm.ask("[Step 1/3] 低速ですが高精度のモードで続行しますか？", console=console): return False
    if input("[Step 2/3] 確認するには 'SLOW' と入力してください: ") != 'SLOW': return False
    if input("[Step 3/3] 完了するには 'CONFIRM' と入力してください: ") != 'CONFIRM': return False
    return True

def main():
    parser = argparse.ArgumentParser(description="SST Scout")
    parser.add_argument("--all", action="store_true", help="Process all unprocessed soundtracks")
    parser.add_argument("--limit", "-n", type=int)
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--appid", type=str, help="Single AppID or comma-separated list of AppIDs")
    parser.add_argument("--dev", action="store_true", help="Run in development mode (DEBUG logs, unique log files)")
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--fingerprint-all", action="store_true", help="Scan every track with AcoustID (slow but extremely precise)")
    parser.add_argument("--yes", "-y", action="store_true", help="Bypass confirmation prompts (Automated mode)")
    parser.add_argument("--prefetch-only", action="store_true", help="Run only Phase 1 (Data Gathering & Caching) without invoking the LLM")
    args = parser.parse_args()
    console = Console()

    # If no specific action is provided, show help and exit (safety gate)
    if not any([args.all, args.limit, args.appid, args.reset_db]):
        parser.print_help()
        return

    # Load configuration
    try:
        config = Config()
        
        # Handle Fingerprint-all confirmation
        if args.fingerprint_all:
            if args.yes or handle_fingerprint_all_confirm(console):
                config.fingerprint_all = True
            else:
                return console.print("[yellow]中止しました。[/yellow]")
                
    except Exception as e: return console.print(f"[red]設定エラー: {e}[/red]")

    fetch_steam_userdata(config, console)

    if args.reset_db: return handle_db_reset(Path(config.sst_db_path), console)
    
    # --- Singleton Lock ---
    lock_file = Path("data/sst.lock")
    if lock_file.exists():
        # Check if the process is actually running (simple PID check could be added, but for now just block)
        console.print("[bold red]❌ エラー: S.S.Tの別のインスタンスが既に実行中です。[/bold red]")
        console.print(f"[dim]実行されていないことが確実な場合は、手動で {lock_file} を削除してください。[/dim]")
        return
    lock_file.touch()

    try:
        db = DatabaseManager(Path(config.sst_db_path))
        if args.all:
            if not (args.yes or handle_all_confirm(console)): return

        log_file = setup_logging(config, console, is_dev=args.dev)
        logger.info(f"S.S.Tを開始します。ログレベル: {config.log_level}。ファイル: {log_file}")

        scanner = SteamScanner(
            install_path=config.steam_install_path, 
            db=db,
            bridge_url=config.steam_pics_bridge_url,
            bridge_api_key=config.steam_pics_bridge_api_key,
            api_key=config.steam_web_api_key,
            override_library_path=config.steam_library_path,
            cache_path="data/sst_cache.json", 
            language=config.steam_language_full
        )
        processor = LocalProcessor(config, db)
        runner = JobRunner(config, processor, console)

        # Handle batch AppIDs
        target_appids = None
        if args.appid:
            try:
                target_appids = [int(aid.strip()) for aid in args.appid.split(',')]
            except ValueError:
                return console.print(f"[bold red]❌ エラー: 無効なAppIDリストです: {args.appid}[/bold red]")

        soundtracks = scanner.find_soundtracks(force=args.force, limit=args.limit, is_processed_callback=db.is_already_processed, target_appids=target_appids)
        if not soundtracks: return logger.info("サウンドトラックが見つかりませんでした。")

        if not args.prefetch_only:
            console.print("[dim]LLMサービスの可用性を確認しています...[/dim]")
            if not processor.llm.check_availability():
                console.print("[bold red]❌ LLMサービスの準備ができていません。設定(.env)やサーバーの起動状態を確認してください。[/bold red]")
                return

        # --- Phase 1: Data Gathering (Pre-Fetch) ---
        from .prefetcher import DataGatherer
        gatherer = DataGatherer(config, processor.acoustid, processor.mbz, console)
        gatherer.run(soundtracks)

        if args.prefetch_only:
            logger.info("事前フェッチ専用モードのため、LLM推論へ進まずに終了します。")
            console.print("[bold green]✅ 事前フェッチ専用モードが完了しました。[/bold green]")
            return

        # --- Phase 2: LLM Processing ---
        start_time = datetime.now()
        results = runner.run(soundtracks)
        duration_str = str(datetime.now() - start_time).split('.')[0]

        # Generate Batch Report
        from .report_generator import ReportGenerator
        from .utils import ensure_wsl_path
        output_root = ensure_wsl_path(config.sst_output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_root / f"Result_{timestamp}.html"
        ReportGenerator.generate_batch_report(results, report_path)
        logger.info(f"バッチレポートが生成されました: {report_path}")

        console.print(f"\n[bold blue]🏁 完了！ 合計時間: {duration_str}[/bold blue]\n")
        
        # Notify completion
        archives = [r for r in results if r.status == "archive"]
        reviews = [r for r in results if r.status == "review"]
        skips = [r for r in results if r.status == "skip"]
        errors = [r for r in results if r.status == "error"]
        
        summary_str = f"S.S.Tは {len(results)} 件のアルバムを {duration_str} で処理完了しました。"
        fields = [
            {"name": "📁 合計", "value": str(len(results)), "inline": True},
            {"name": "🛡️ アーカイブ", "value": str(len(archives)), "inline": True},
            {"name": "🔍 レビュー", "value": str(len(reviews)), "inline": True},
            {"name": "⏩ スキップ", "value": str(len(skips)), "inline": True},
            {"name": "❌ エラー", "value": str(len(errors)), "inline": True},
        ]
        processor.notifier.notify_completion("バッチ実行完了", summary_str, fields)
        
        render_summary_table(results, config.user_language, console)

    except Exception as e:
        logger.error(f"致命的なシステムエラー: {e}", exc_info=True)
        console.print(f"[bold red]致命的なエラー: {e}[/bold red]")
    finally:
        if lock_file.exists():
            lock_file.unlink()

if __name__ == "__main__":
    main()
