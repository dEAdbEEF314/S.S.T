from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..tagger import AudioTagger
from ..track_grouper import TrackManager
from .fast_track import apply_mbz_track_artists
from .file_selection import adopt_best_file_per_slot, select_best_unassigned_files


def encode_and_tag_tracks(
    config: Any,
    notifier: Any,
    process_track: Callable[..., Dict[str, Any]],
    fetch_artwork: Callable[..., Optional[bytes]],
    normalize_processed_tracks: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    app_id: int,
    steam_meta: Any,
    final_metadata: Dict[str, Any],
    mbz_candidates: List[Dict[str, Any]],
    track_groups: Dict,
    slot_variant_index: Dict,
    track_to_slot_index: Dict,
    llm_log: Dict[str, Any],
    total_discs: int,
    temp_output: Path,
    buffer_dir: Path,
    on_track_complete: Optional[Callable[[], None]],
    diag: Callable[..., Any],
    adopted_file_subset: Optional[List[Tuple[Tuple[int, str], Dict[str, Any]]]] = None,
    defer_copy_failures: bool = False,
    include_unassigned: bool = True,
    artwork_prepared: bool = False,
    prepared_album_artwork_path: Optional[Path] = None,
) -> Tuple[
    List[Dict[str, Any]],
    bool,
    bool,
    List[str],
    List[Dict[str, Any]],
    int,
    List[Dict[str, Any]],
    int,
    int,
    List[Tuple[Tuple[int, str], Dict[str, Any]]],
    Optional[Path],
]:
    tagger = AudioTagger(
        temp_output,
        ffmpeg_timeout=getattr(config, "ffmpeg_timeout", 600.0),
        ffprobe_timeout=getattr(config, "ffprobe_timeout", 10.0),
    )

    def apply_fast_track_mbz_artists(candidate: Optional[Dict[str, Any]]) -> None:
        if llm_log.get("processing_route") != "FAST_TRACK" or not candidate:
            return

        applied = apply_mbz_track_artists(
            final_metadata,
            steam_meta.store_tracklist or [],
            candidate,
        )
        diag("FAST_TRACK_MBZ_ARTISTS_APPLIED", enriched_track_count=applied)

    if artwork_prepared:
        album_artwork_path = prepared_album_artwork_path
    else:
        raw_album_artwork = fetch_artwork(
            steam_meta,
            mbz_candidates,
            track_groups,
            allow_mbz_artwork_search=llm_log.get("processing_route") == "FAST_TRACK",
            on_mbz_candidate=apply_fast_track_mbz_artists,
        )
        album_artwork_path = tagger.process_artwork(raw_album_artwork) if raw_album_artwork else None

    track_sources = TrackManager.prepare_llm_track_context(track_groups)
    phase1_result = llm_log.get("phase1_res", {})
    global_identity = phase1_result.get("global_tags", {}) if phase1_result else {}

    def process_track_with_context(track_data):
        return process_track(
            app_id=app_id,
            steam_meta_name=steam_meta.name,
            track_data=track_data,
            final_metadata=final_metadata,
            config=config,
            steam_meta=steam_meta,
            mbz_candidates=mbz_candidates,
            track_sources=track_sources,
            global_identity=global_identity,
            total_discs=total_discs,
            buffer_dir=buffer_dir,
            tagger=tagger,
            track_groups=track_groups,
            slot_variant_index=slot_variant_index,
            track_to_slot_index=track_to_slot_index,
            album_artwork=album_artwork_path,
            notifier=notifier,
            on_track_complete=on_track_complete,
            defer_copy_failure=defer_copy_failures,
        )

    if adopted_file_subset is None:
        adopted_files = adopt_best_file_per_slot(
            track_groups, slot_variant_index, track_to_slot_index
        )
        diag(
            "TRACKS_ADOPTED",
            adopted_slot_count=len(adopted_files),
            adopted_file_count=len(adopted_files),
        )
    else:
        adopted_files = dict(adopted_file_subset)
        diag("DEFERRED_COPY_RETRY_TRACKS", track_count=len(adopted_files))

    with ThreadPoolExecutor(max_workers=config.max_encoding_tasks) as executor:
        track_results = list(executor.map(process_track_with_context, adopted_files.items()))
    deferred_track_data = [
        track_data
        for track_data, result in zip(adopted_files.items(), track_results)
        if result.get("copy_pending")
    ]

    processed_tracks_meta = normalize_processed_tracks(
        [result["track_meta"] for result in track_results if result.get("track_meta")]
    )
    io_retry_logs = [result["io_retry_log"] for result in track_results if result.get("io_retry_log")]
    io_retry_count = sum(1 for retry_log in io_retry_logs if retry_log.get("retried"))
    alignment_unassigned_ids = {
        str(file_id)
        for file_id in (llm_log.get("alignment_res", {}) or {}).get("unassigned_files", [])
    }
    unassigned_manifest = []
    unassigned_candidates = select_best_unassigned_files(
        track_groups,
        final_metadata,
        alignment_unassigned_ids or None,
        slot_variant_index=slot_variant_index,
        track_to_slot_index=track_to_slot_index,
    ) if include_unassigned else []
    for unassigned in unassigned_candidates:
        manifest = {
            "track_id": unassigned["track_id"],
            "original_filename": unassigned["path"].name,
            "file_id": unassigned.get("file_id"),
            "unassigned_file_ids": unassigned.get("unassigned_file_ids", []),
            "tier_rank": unassigned["tier_rank"],
            "original_tags": unassigned.get("original_tags", {}),
            "reason": "No matching Steam slot",
        }
        try:
            converted_path, conversion_warning = tagger.convert_and_limit(
                unassigned["path"], unassigned["tier"], subdir="unassigned"
            )
            tagger.mark_unassigned(converted_path, manifest["reason"])
            manifest["file_path"] = f"unassigned/{converted_path.name}"
            manifest["converted"] = True
            manifest["conversion_warning"] = bool(conversion_warning)
        except Exception as error:
            manifest["converted"] = False
            manifest["conversion_error"] = str(error)
        unassigned_manifest.append(manifest)

    any_audio_warnings = any(result.get("had_warning") for result in track_results)
    any_audio_failures = any(result.get("failed") for result in track_results)
    audio_warned_tracks: List[str] = []
    for result in track_results:
        warned_track_label = result.get("warned_track_label")
        if result.get("had_warning") and isinstance(warned_track_label, str) and warned_track_label:
            audio_warned_tracks.append(warned_track_label)

    return (
        processed_tracks_meta,
        any_audio_failures,
        any_audio_warnings,
        audio_warned_tracks,
        unassigned_manifest,
        io_retry_count,
        io_retry_logs,
        len(adopted_files),
        len(track_results),
        deferred_track_data,
        album_artwork_path,
    )