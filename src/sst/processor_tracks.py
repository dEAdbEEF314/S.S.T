import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .builder import MetadataBuilder
from .config import PriorityConfig
from .models import SteamMetadata
from .track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def process_single_track(
    app_id: int,
    steam_meta_name: str,
    track_data: Tuple[Tuple[int, str], Dict[str, Any]],
    final_metadata: Dict[str, Any],
    config: Any,
    steam_meta: SteamMetadata,
    mbz_candidates: list,
    track_sources: Dict[str, list],
    global_identity: Dict[str, Any],
    total_discs: int,
    buffer_dir: Path,
    tagger: Any,
    track_groups: Dict,
    album_artwork: Optional[bytes],
    notifier: Any,
    on_track_complete: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """
    Processes one logical track end-to-end and returns result metadata plus status flags.
    """
    (disc, clean_title), adopted_info = track_data

    try:
        instr = final_metadata.get(f"{disc}_{clean_title}") or {"action": "use_local_tag"}
        priorities: PriorityConfig = config.build_priority_config()
        tag_map = MetadataBuilder.build_tag_map(
            app_id,
            disc,
            clean_title,
            adopted_info,
            steam_meta,
            instr,
            mbz_candidates,
            track_sources,
            config.user_language_639_2,
            global_identity,
            priorities=priorities,
            total_discs=total_discs,
        )

        final_disc = disc
        if tag_map.get("disc_number"):
            try:
                final_disc = int(str(tag_map["disc_number"]).split("/")[0])
            except Exception:
                pass

        disc_subdir = f"disc_{final_disc}"

        local_raw_dir = buffer_dir / disc_subdir
        local_raw_dir.mkdir(parents=True, exist_ok=True)
        local_source_path = local_raw_dir / adopted_info["path"].name
        shutil.copy2(adopted_info["path"], local_source_path)

        processed_path, has_warnings = tagger.convert_and_limit(
            local_source_path,
            adopted_info["tier"],
            subdir=disc_subdir,
        )
        if local_source_path.exists():
            local_source_path.unlink()

        track_art = TrackManager.get_best_artwork(track_groups[(disc, clean_title)])
        final_art = tagger.process_artwork(track_art) if track_art else album_artwork
        tagger.write_tags(processed_path, tag_map, final_art)

        if on_track_complete:
            on_track_complete()

        return {
            "track_meta": {
                "file_path": f"{disc_subdir}/{processed_path.name}",
                "original_filename": local_source_path.name,
                "tags": tag_map,
                "source": instr.get("reason", "Fallback"),
                "title_source": tag_map.get("title_source", "UNKNOWN"),
            },
            "had_warning": bool(has_warnings),
            "failed": False,
        }

    except Exception as e:
        logger.error(f"[{app_id}] トラック処理の失敗 {clean_title}: {e}")
        notifier.notify_critical(f"トラック処理エラー: {steam_meta_name}", str(e))
        return {
            "track_meta": None,
            "had_warning": False,
            "failed": True,
        }
