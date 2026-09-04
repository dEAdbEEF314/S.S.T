import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .builder import MetadataBuilder
from .models import SteamMetadata
from .processor_support import merge_embedded_tags_for_slot
from .track_grouper import TrackManager

logger = logging.getLogger("sst.processor")


def copy_with_retry(src: Path, dst: Path, retries: int = 3, initial_delay: float = 1.0) -> Dict[str, Any]:
    """Copy a file with retry, returning a structured record of attempts.

    The record preserves the failure type and final state so the caller can
    audit I/O resilience without weakening the verification contract: a final
    copy failure still surfaces as a track failure upstream.
    """
    attempts: List[Dict[str, Any]] = []
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            attempts.append({
                "attempt": attempt + 1,
                "error_type": None,
                "error": None,
                "success": True,
            })
            return {
                "source": src.name,
                "attempts": attempts,
                "final_state": "success",
                "retried": attempt > 0,
            }
        except (OSError, IOError, PermissionError) as e:
            attempts.append({
                "attempt": attempt + 1,
                "error_type": type(e).__name__,
                "error": str(e),
                "success": False,
            })
            if attempt == retries - 1:
                break
            delay = initial_delay * (2 ** attempt)
            logger.warning(f"File copy failed for {src.name} ({e}), retrying in {delay}s (Attempt {attempt+1}/{retries})...")
            time.sleep(delay)
    return {
        "source": src.name,
        "attempts": attempts,
        "final_state": "failed",
        "retried": len(attempts) > 1,
    }


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
    slot_variant_index: Dict[tuple[int, str], list],
    track_to_slot_index: Dict[str, tuple[int, str]],
    album_artwork: Optional[Path],
    notifier: Any,
    on_track_complete: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """
    Processes one logical track end-to-end and returns result metadata plus status flags.
    """
    (disc, clean_title), adopted_info = track_data

    try:
        track_id = f"{disc}_{clean_title}"
        slot_key = track_to_slot_index.get(track_id, (disc, clean_title))
        instr = final_metadata.get(track_id)
        if not instr:
            instr = final_metadata.get(f"{slot_key[0]}_{slot_key[1]}")
        if not instr:
            instr = final_metadata.get(clean_title)
        if not instr:
            instr = {"action": "use_local_tag"}

        slot_variants = slot_variant_index.get(slot_key)
        if slot_variants is None:
            slot_variants = track_groups[(disc, clean_title)]
        merged_slot_tags = merge_embedded_tags_for_slot(slot_variants)
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
            merged_slot_tags,
            global_identity,
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
        io_retry_log = copy_with_retry(adopted_info["path"], local_source_path)

        processed_path, has_warnings = tagger.convert_and_limit(
            local_source_path,
            adopted_info["tier"],
            subdir=disc_subdir,
        )
        if local_source_path.exists():
            local_source_path.unlink()

        track_art = TrackManager.get_best_artwork(slot_variants)
        final_art = tagger.process_artwork(track_art) if track_art else album_artwork
        tagger.write_tags(processed_path, tag_map, final_art)

        warned_track_label = None
        if has_warnings:
            track_val = tag_map.get("track") or (slot_key[1] if len(slot_key) > 1 else None) or clean_title
            if track_val:
                t_str = str(track_val).split("/")[0].strip()
                if t_str.isdigit():
                    warned_track_label = f"Track {int(t_str):02d}"
                else:
                    warned_track_label = f"Track {t_str}"
            else:
                warned_track_label = f"Track {clean_title}"

        if on_track_complete:
            on_track_complete()

        return {
            "track_meta": {
                "file_path": f"{disc_subdir}/{processed_path.name}",
                "original_filename": local_source_path.name,
                "tags": tag_map,
                "source": instr.get("reason", "Fallback"),
                "title_source": tag_map.get("title_source", "UNKNOWN"),
                "slot_key": f"{slot_key[0]}_{slot_key[1]}",
                "tier_rank": adopted_info.get("tier_rank", 999),
            },
            "had_warning": bool(has_warnings),
            "warned_track_label": warned_track_label,
            "failed": False,
            "io_retry_log": io_retry_log,
        }

    except Exception as e:
        logger.error(f"[{app_id}] トラック処理の失敗 {clean_title}: {e}")
        notifier.notify_critical(f"トラック処理エラー: {steam_meta_name}", str(e))
        return {
            "track_meta": None,
            "had_warning": False,
            "warned_track_label": None,
            "failed": True,
            "io_retry_log": io_retry_log,
        }
