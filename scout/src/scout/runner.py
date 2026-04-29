import logging
import multiprocessing
from typing import List, Optional, Any
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from .models import SteamMetadata, LocalProcessResult
from .processor import LocalProcessor

logger = logging.getLogger("scout.runner")

class JobRunner:
    def __init__(self, config: Any, processor: LocalProcessor, console: Console):
        self.config = config
        self.processor = processor
        self.console = console

    def run(self, soundtracks: List[dict]) -> List[LocalProcessResult]:
        """Orchestrates the parallel processing of soundtracks with rich progress bars."""
        results: List[LocalProcessResult] = []
        start_time = datetime.now()

        # Calculate workers
        cpu_count = multiprocessing.cpu_count()
        if self.config.llm_force_local:
            max_album_workers = min(cpu_count, 4)
        else:
            max_album_workers = max(1, min(int(self.config.llm_limit_rpm * 0.7), cpu_count * 2, 10))

        logger.info(f"Runner starting with {max_album_workers} workers.")

        def _process_single_album(ost, progress, overall_task):
            app_id = ost["app_id"]
            install_dir = Path(ost["install_dir"])
            album_task = progress.add_task(f"[cyan]Mapping: {ost['name']}", total=None)

            steam_meta = SteamMetadata(
                app_id=app_id, name=ost["name"], developer=ost.get("developer"), publisher=ost.get("publisher"),
                url=ost.get("url"), tags=ost.get("tags", []), genre=ost.get("genre"), release_date=ost.get("release_date"),
                parent_app_id=ost.get("parent_app_id"), parent_name=ost.get("parent_name"), parent_tags=ost.get("parent_tags", []),
                parent_genre=ost.get("parent_genre"), parent_release_date=ost.get("parent_release_date"),
                header_image_url=ost.get("header_image_url")
            )

            all_files = self.processor._list_audio_files(install_dir)
            progress.update(album_task, description=f"[yellow]Processing: {ost['name']}", total=len(all_files))

            result = self.processor.process_album(app_id, install_dir, steam_meta, on_track_complete=lambda: progress.advance(album_task))
            results.append(result)

            progress.remove_task(album_task)
            progress.update(overall_task, advance=1)
            
            status_color = "green" if result.status == "archive" else "yellow"
            self.console.print(f"[bold {status_color}]✓[/bold {status_color}] {ost['name']} -> [bold]{result.status.upper()}[/bold]")

        try:
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                BarColumn(), TaskProgressColumn(), TimeRemainingColumn(),
                console=self.console, expand=True
            ) as progress:
                overall_task = progress.add_task("[bold blue]Overall Progress", total=len(soundtracks))
                with ThreadPoolExecutor(max_workers=max_album_workers) as executor:
                    list(executor.map(lambda ost: _process_single_album(ost, progress, overall_task), soundtracks))
        finally:
            self.console.show_cursor(True)

        return results
