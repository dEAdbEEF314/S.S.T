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

logger = logging.getLogger("sst.runner")

class JobRunner:
    def __init__(self, config: Any, processor: LocalProcessor, console: Console):
        self.config = config
        self.processor = processor
        self.console = console

    def run(self, soundtracks: List[dict]) -> List[LocalProcessResult]:
        """Orchestrates the parallel processing of soundtracks with adaptive routing."""
        results: List[LocalProcessResult] = []
        start_time = datetime.now()

        # Determine track counts for sorting and categorization
        logger.info("Scanning track counts for adaptive routing...")
        for ost in soundtracks:
            install_dir = Path(ost["install_dir"])
            # Estimate track count by counting audio files
            audio_files = TrackManager.list_audio_files(install_dir)
            ost["_track_count"] = len(audio_files)

        # Sort soundtracks by track count to process small ones first
        soundtracks.sort(key=lambda x: x["_track_count"])

        # Group by tiers to minimize model switching overhead
        tiers = {
            "SMALL (<=50)": [s for s in soundtracks if s["_track_count"] <= 50],
            "MEDIUM (51-100)": [s for s in soundtracks if 50 < s["_track_count"] <= 100],
            "LARGE (>100)": [s for s in soundtracks if s["_track_count"] > 100]
        }

        max_album_workers = self.config.max_parallel_albums
        if self.config.llm_backend not in ["OLLAMA", "OPENAI_COMPATIBLE"]:
            # For cloud APIs, respect the config but allow slightly more if the rate limit allows, capped at a safe number
            cpu_count = multiprocessing.cpu_count()
            cloud_workers = min(int(self.config.llm_limit_rpm * 0.5), cpu_count, 5)
            max_album_workers = max(max_album_workers, cloud_workers)

        logger.info(f"Runner starting with {max_album_workers} workers. Using Adaptive Routing.")

        def _process_single_album(ost, progress, overall_task):
            app_id = ost["app_id"]
            install_dir = Path(ost["install_dir"])
            album_task = progress.add_task(f"[cyan]Mapping: {ost['name']}", total=None)

            # Use dict unpacking to ensure all fields from ost are included in SteamMetadata
            steam_meta = SteamMetadata(**ost)

            all_files = TrackManager.list_audio_files(install_dir)
            progress.update(album_task, description=f"[yellow]Processing: {ost['name']}", total=len(all_files))

            result = self.processor.process_album(app_id, install_dir, steam_meta, on_track_complete=lambda: progress.advance(album_task))
            
            if result is None:
                result = LocalProcessResult(
                    app_id=app_id, status="error", album_name=ost["name"], 
                    message="Process returned None", confidence_score=0
                )
            
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
                
                for tier_name, tier_soundtracks in tiers.items():
                    if not tier_soundtracks:
                        continue
                    
                    # Tier-based dynamic worker allocation
                    if "SMALL" in tier_name:
                        tier_workers = self.config.max_parallel_small
                    elif "MEDIUM" in tier_name:
                        tier_workers = self.config.max_parallel_medium
                    else: # LARGE
                        tier_workers = self.config.max_parallel_large
                    
                    logger.info(f"--- Starting {tier_name} Tier ({len(tier_soundtracks)} albums) with {tier_workers} workers ---")
                    with ThreadPoolExecutor(max_workers=tier_workers) as executor:
                        list(executor.map(lambda ost: _process_single_album(ost, progress, overall_task), tier_soundtracks))
                    
                    # Cool-down period between tiers to allow VRAM to clear
                    if self.config.llm_backend == "OLLAMA" and len(tier_soundtracks) > 0:
                        logger.info(f"Cooling down after {tier_name} tier...")
                        import time
                        time.sleep(5)
        finally:
            self.console.show_cursor(True)

        return results
