import logging
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Any

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from .track_grouper import TrackManager
from .models import SteamMetadata

logger = logging.getLogger("sst.prefetcher")

class DataGatherer:
    """
    Phase 1: Pre-Fetch (事前フェッチ) を担当するクラス。
    LLM推論(Phase 2)の前に、全対象アルバムの重い処理（fpcalcによる波形計算と外部API通信）を
    マルチスレッドで一気に実行し、SQLiteにキャッシュを生成します。
    """
    def __init__(self, config: Any, acoustid_client, mbz_client, console: Console):
        self.config = config
        self.acoustid = acoustid_client
        self.mbz = mbz_client
        self.console = console

    def _prefetch_mbz(self, ost: dict):
        app_id = ost["app_id"]
        steam_meta = SteamMetadata(**ost)
        
        local_baseline = {
            "publisher": steam_meta.publisher,
            "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
            "tracks": [] # テキスト検索のキャッシュ目的のため厳密なトラック構成は不要
        }
        
        self.mbz.search_release(
            album_name=steam_meta.name,
            expected_track_count=len(steam_meta.store_tracklist),
            app_id=app_id,
            parent_app_id=None,
            year=local_baseline["year"],
            local_baseline=local_baseline
        )

    def run(self, soundtracks: List[dict]):
        if not soundtracks:
            return

        logger.info(f"Phase 1: 事前フェッチ (Pre-Fetch) を開始します。対象アルバム: {len(soundtracks)} 件")
        self.console.print(f"[bold cyan]🚀 Phase 1: Data Gathering & Pre-Fetch ({len(soundtracks)} albums)[/bold cyan]")
        
        all_audio_files = []
        mbz_tasks = []
        
        for ost in soundtracks:
            install_dir = Path(ost["install_dir"])
            audio_files = TrackManager.list_audio_files(install_dir)
            all_audio_files.extend(audio_files)
            mbz_tasks.append(ost)
            
        # AcoustID(fpcalc)はCPUバウンドなのでコア数ベースで多重化
        workers = min(multiprocessing.cpu_count() * 2, 32)
        
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            BarColumn(), TaskProgressColumn(), TimeRemainingColumn(),
            console=self.console, expand=True
        ) as progress:
            
            # --- 1. AcoustID (fpcalc & API) ---
            task_acoustid = progress.add_task("[yellow]AcoustID (指紋照合) の事前フェッチ...", total=len(all_audio_files))
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []
                for file_path in all_audio_files:
                    futures.append(executor.submit(self.acoustid.identify_track, file_path))
                    
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"AcoustID 事前フェッチエラー: {e}")
                    finally:
                        progress.advance(task_acoustid)
                        
            # --- 2. MusicBrainz Search (API) ---
            task_mbz = progress.add_task("[green]MusicBrainz (メタデータ) の事前フェッチ...", total=len(mbz_tasks))
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                mbz_futures = []
                for ost in mbz_tasks:
                    mbz_futures.append(executor.submit(self._prefetch_mbz, ost))
                    
                for future in as_completed(mbz_futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"MBZ 事前フェッチエラー: {e}")
                    finally:
                        progress.advance(task_mbz)

        logger.info("Phase 1: 事前フェッチが完了しました。すべてのデータがキャッシュされました。")
        self.console.print("[bold green]✅ Phase 1: Pre-Fetch Completed![/bold green]")
