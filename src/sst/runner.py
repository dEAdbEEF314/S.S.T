import logging
import multiprocessing
from typing import List, Any
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from .models import SteamMetadata, LocalProcessResult
from .processor import LocalProcessor
from .track_grouper import TrackManager
from .vram_manager import VramResourceManager

logger = logging.getLogger("sst.runner")

class JobRunner:
    def __init__(self, config: Any, processor: LocalProcessor, console: Console):
        self.config = config
        self.processor = processor
        self.console = console
        self.vram_manager = None
        
        if self.config.llm_backend == "OLLAMA":
            self.vram_manager = VramResourceManager(
                base_url=self.config.llm_base_url,
                model=self.config.llm_model
            )
            if getattr(self.config, "llm_vram_scheduling_enabled", True):
                self.processor.set_vram_manager(self.vram_manager)

    def run(self, soundtracks: List[dict]) -> List[LocalProcessResult]:
        """Orchestrates the parallel processing of soundtracks with adaptive routing."""
        results: List[LocalProcessResult] = []
        start_time = datetime.now()

        # Determine track counts for VRAM estimation and sorting
        logger.info("動的スケジューリングのためにトラック数をスキャンしています...")
        for ost in soundtracks:
            try:
                install_dir = Path(ost["install_dir"])
                audio_files = TrackManager.list_audio_files(install_dir)
                ost["_track_count"] = len(audio_files)
            except Exception as e:
                logger.error(f"[{ost.get('app_id')}] 初期トラック数スキャン中にエラーが発生しました: {e}")
                ost["_track_count"] = 0

        # Sort soundtracks by track count to process small ones first (better packing)
        soundtracks.sort(key=lambda x: x["_track_count"])

        if self.config.llm_backend == "OLLAMA":
            logger.info("Ollamaバックエンドを検出しました。動的VRAMディスパッチャー (Token Stingy) による自律的並列処理を開始します。")
            # メタデータ抽出でCPU/Diskがサチュレートしない程度の適度な上限を設定しつつ、VRAMセマフォに制御を委ねる
            max_workers = min(len(soundtracks), max(10, self.config.max_parallel_albums * 3))
        else:
            cpu_count = multiprocessing.cpu_count()
            cloud_workers = min(int(self.config.llm_limit_rpm * 0.5), cpu_count, 5)
            max_workers = min(self.config.max_parallel_albums, cloud_workers)
            logger.info(f"外部APIバックエンドを検出しました。標準スレッドプール ({max_workers} ワーカー) を使用します。")

        def _process_single_album(ost, progress, overall_task):
            app_id = ost["app_id"]
            install_dir = Path(ost["install_dir"])
            album_task = progress.add_task(f"[cyan]待機中: {ost['name']}", total=None)

            def _llm_progress(event: dict):
                phase = event.get("phase")
                request_kind = event.get("request_kind", "llm")
                if phase == "llm_waiting_vram":
                    progress.update(album_task, description=f"[cyan]LLM VRAM待機 ({request_kind}): {ost['name']}")
                elif phase == "llm_vram_acquired":
                    reserved_mb = event.get("reserved_mb")
                    progress.update(album_task, description=f"[cyan]LLM VRAM確保 {reserved_mb}MB ({request_kind}): {ost['name']}")
                elif phase == "llm_request_running":
                    progress.update(album_task, description=f"[yellow]LLM実行中 ({request_kind}): {ost['name']}")
                elif phase == "llm_request_retry":
                    progress.update(album_task, description=f"[magenta]LLM再試行 ({request_kind}): {ost['name']}")
                elif phase == "llm_request_done":
                    progress.update(album_task, description=f"[yellow]LLM完了 ({request_kind}): {ost['name']}")
                elif phase == "llm_request_failed":
                    progress.update(album_task, description=f"[red]LLM失敗 ({request_kind}): {ost['name']}")

            vram_cost = 0
            if self.vram_manager:
                vram_cost = self.vram_manager.estimate_album_vram(ost["_track_count"], ost["name"])
                if getattr(self.config, "llm_vram_scheduling_enabled", True):
                    progress.update(album_task, description=f"[cyan]LLM VRAM見積り ({vram_cost/(1024**2):.1f}MB): {ost['name']}")
                else:
                    progress.update(album_task, description=f"[cyan]VRAM確保待ち ({vram_cost/(1024**2):.1f}MB): {ost['name']}")
                    vram_cost = self.vram_manager.acquire(vram_cost)
                
            progress.update(album_task, description=f"[yellow]処理中: {ost['name']}")

            result = None
            try:
                # Use dict unpacking to ensure all fields from ost are included in SteamMetadata
                steam_meta = SteamMetadata(**ost)

                all_files = TrackManager.list_audio_files(install_dir)
                progress.update(album_task, total=len(all_files))

                result = self.processor.process_album(
                    app_id,
                    install_dir,
                    steam_meta,
                    on_track_complete=lambda: progress.advance(album_task),
                    llm_progress_callback=_llm_progress,
                )
                
                if result is None:
                    result = LocalProcessResult(
                        app_id=app_id, status="error", album_name=ost["name"], 
                        message="Process returned None", confidence_score=0
                    )
            except Exception as e:
                logger.error(f"[{app_id}] アルバム処理中にエラーが発生しました ({ost['name']}): {e}", exc_info=True)
                result = LocalProcessResult(
                    app_id=app_id, status="error", album_name=ost["name"],
                    message=str(e), confidence_score=0
                )
            finally:
                if self.vram_manager and not getattr(self.config, "llm_vram_scheduling_enabled", True):
                    self.vram_manager.release(vram_cost)

            results.append(result)
            progress.remove_task(album_task)
            progress.update(overall_task, advance=1)
            
            status_color = "green" if result.status == "archive" else ("yellow" if result.status == "review" else "red")
            self.console.print(f"[bold {status_color}]✓[/bold {status_color}] {ost['name']} -> [bold]{result.status.upper()}[/bold]")

        try:
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                BarColumn(), TaskProgressColumn(), TimeRemainingColumn(),
                console=self.console, expand=True
            ) as progress:
                overall_task = progress.add_task("[bold blue]全体の進捗", total=len(soundtracks))
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    list(executor.map(lambda ost: _process_single_album(ost, progress, overall_task), soundtracks))
                    
        finally:
            self.console.show_cursor(True)

        return results
