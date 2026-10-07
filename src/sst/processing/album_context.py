import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..models import SteamMetadata
from ..track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def initialize_album_context(
    app_id: int,
    install_dir: Path,
    steam_meta: SteamMetadata,
    diag: Callable[..., Any],
    llm: Any,
    db: Any,
    build_execution_profile: Callable[[int], Any],
    pre_scanned_files: Optional[List[Path]] = None,
) -> Optional[Tuple[List[Path], Dict, int, int, Any]]:
    diag("PROCESS_START", install_dir=str(install_dir))
    all_files = pre_scanned_files if pre_scanned_files is not None else TrackManager.list_audio_files(install_dir)
    diag("FILES_SCANNED", audio_file_count=len(all_files))
    if not all_files:
        diag("SKIP_NO_AUDIO")
        return None

    track_groups = TrackManager.build_file_records(all_files, album_name=steam_meta.name)
    diag("FILE_RECORDS_BUILT", file_count=len(track_groups))

    store_description = steam_meta.store_description
    if not steam_meta.store_tracklist and store_description:
        from ..steam_web_api import SteamWebClient

        description_text = SteamWebClient._description_text(store_description)
        if description_text:
            logger.info(f"[{app_id}] ストアトラックリスト未設定のため、オンデマンドLLM抽出を実行します。")
            llm_tracks, llm_log = llm.extract_steam_tracklist(app_id, description_text)
            if llm_tracks:
                steam_meta.store_tracklist = llm_tracks
                steam_meta.store_tracklist_source = "STEAM_TEXT_TRACKLIST_LLM"
                db.save_store_data(
                    app_id,
                    llm_tracks,
                    steam_meta.store_credits or "",
                    tracklist_language=getattr(steam_meta, "store_tracklist_language", None),
                )
                logger.info(f"[{app_id}] オンデマンドLLM抽出成功: {len(llm_tracks)} トラックを取得しました。")
                diag("STORE_TRACKLIST_EXTRACTED_ON_DEMAND", track_count=len(llm_tracks))

    max_local_disc = max((disc for disc, _ in track_groups.keys()), default=1) if track_groups else 1
    max_store_disc = max((int(track.get("disc", 1)) for track in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
    total_discs = max(max_local_disc, max_store_disc)

    track_count = max(len(track_groups), len(steam_meta.store_tracklist) if steam_meta.store_tracklist else 0)
    execution_profile = build_execution_profile(track_count)
    logger.info(f"[{app_id}] 実行プロファイル: {execution_profile.tier_name} (Tracks: {track_count}, num_ctx: {execution_profile.num_ctx_cap}, workers: {execution_profile.phase2_parallel_workers})")
    return all_files, track_groups, total_discs, track_count, execution_profile