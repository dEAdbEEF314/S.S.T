from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..tagger import AudioTagger
from ..track_grouper import TrackManager
from .fast_track import apply_mbz_track_artists
from .file_selection import (
    adopt_best_file_per_slot,
    select_best_unassigned_files,
    select_slot_conflict_candidates,
)


def _convert_review_candidates(
    tagger: AudioTagger,
    temp_output: Path,
    candidates: List[Dict[str, Any]],
    start_index: int = 0,
) -> List[Dict[str, Any]]:
    manifests = []
    for index, candidate in enumerate(candidates, start=start_index + 1):
        source_path = Path(candidate["path"])
        candidate_subdir = Path("review_candidates") / f"candidate_{index:03d}"
        output_dir = temp_output / candidate_subdir
        manifest = {
            "candidate_type": candidate.get("candidate_type", "unassigned"),
            "original_filename": source_path.name,
            "file_id": candidate.get("file_id"),
            "track_id": candidate.get("track_id"),
            "slot_key": (
                "_".join(str(part) for part in candidate["slot_key"])
                if candidate.get("slot_key") is not None
                else None
            ),
            "reason": candidate.get("reason", "No matching Steam slot"),
            "included": False,
            "converted": False,
        }
        try:
            converted_path, conversion_warning = tagger.convert_and_limit(
                source_path,
                candidate["tier"],
                subdir=candidate_subdir.as_posix(),
            )
            converted_path = Path(converted_path)
            try:
                relative_path = converted_path.resolve().relative_to(temp_output.resolve())
            except ValueError:
                relative_path = candidate_subdir / converted_path.name
            manifest.update(
                {
                    "file_path": relative_path.as_posix(),
                    "output_filename": converted_path.name,
                    "output_format": converted_path.suffix.lower().lstrip("."),
                    "included": converted_path.is_file(),
                    "converted": converted_path.is_file(),
                    "conversion_warning": bool(conversion_warning),
                }
            )
            if not manifest["included"]:
                raise OSError("Converted candidate output is missing")
        except Exception as conversion_error:
            shutil.rmtree(output_dir, ignore_errors=True)
            manifest["conversion_error_type"] = type(conversion_error).__name__
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, output_dir / source_path.name)
                manifest.update(
                    {
                        "file_path": (candidate_subdir / source_path.name).as_posix(),
                        "output_filename": source_path.name,
                        "output_format": source_path.suffix.lower().lstrip("."),
                        "included": True,
                        "converted": False,
                    }
                )
            except OSError as copy_error:
                manifest["copy_error_type"] = type(copy_error).__name__
        manifests.append(manifest)
    return manifests


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
        llm_diagnostics = llm_log.setdefault("diagnostics", {})
        raw_album_artwork = fetch_artwork(
            steam_meta,
            mbz_candidates,
            track_groups,
            allow_mbz_artwork_search=llm_log.get("processing_route") == "FAST_TRACK",
            on_mbz_candidate=apply_fast_track_mbz_artists,
            on_artwork_source=lambda source: llm_diagnostics.__setitem__(
                "album_artwork_source", source
            ),
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
            album_artwork_source=(llm_log.get("diagnostics") or {}).get(
                "album_artwork_source", "UNKNOWN"
            ),
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
    # Review候補は採用曲のslot検証から分離して、後から確認・修正できる形で保存する。
    candidate_inputs: List[Dict[str, Any]] = []
    unassigned_candidates = select_best_unassigned_files(
        track_groups,
        final_metadata,
        alignment_unassigned_ids or None,
        slot_variant_index=slot_variant_index,
        track_to_slot_index=track_to_slot_index,
    ) if include_unassigned else []
    for unassigned in unassigned_candidates:
        candidate_inputs.append(
            {
                **unassigned,
                "candidate_type": "unassigned",
                "reason": "No matching Steam slot",
            }
        )

    if include_unassigned:
        candidate_inputs.extend(
            select_slot_conflict_candidates(
                track_groups, slot_variant_index, adopted_files
            )
        )

    for (record_key, adopted_info), result in zip(adopted_files.items(), track_results):
        if not result.get("failed"):
            continue
        io_retry_log = result.get("io_retry_log") or {}
        if result.get("copy_failed"):
            errors = [
                attempt.get("error_type")
                for attempt in io_retry_log.get("attempts", [])
                if attempt.get("error_type")
            ]
            reason = f"Source copy failed ({errors[-1] if errors else 'OSError'})"
            candidate_type = "copy_failure"
        else:
            stage = result.get("failure_stage", "track_processing")
            failure_type = result.get("failure_type", "Error")
            reason = f"Track processing failed during {stage} ({failure_type})"
            candidate_type = "processing_failure"
        candidate_inputs.append(
            {
                "track_id": f"{record_key[0]}_{record_key[1]}",
                "path": adopted_info["path"],
                "file_id": adopted_info.get("file_id"),
                "tier": adopted_info["tier"],
                "tier_rank": adopted_info.get("tier_rank", 999),
                "slot_key": adopted_info.get("slot_key"),
                "candidate_type": candidate_type,
                "reason": reason,
            }
        )

    llm_diagnostics = llm_log.get("diagnostics")
    if not isinstance(llm_diagnostics, dict):
        llm_diagnostics = {}
        llm_log["diagnostics"] = llm_diagnostics
    existing_review_candidates = llm_diagnostics.get("review_candidates") or []
    seen_candidate_ids = {
        candidate.get("file_id")
        for candidate in existing_review_candidates
        if candidate.get("file_id")
    }
    unique_candidates = []
    for candidate in candidate_inputs:
        candidate_id = candidate.get("file_id") or str(Path(candidate["path"]).resolve())
        if candidate_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(candidate_id)
        unique_candidates.append(candidate)

    added_review_candidates = _convert_review_candidates(
        tagger,
        temp_output,
        unique_candidates,
        start_index=len(existing_review_candidates),
    )
    review_candidate_manifest = existing_review_candidates + added_review_candidates
    unassigned_manifest = [
        candidate
        for candidate in review_candidate_manifest
        if candidate.get("candidate_type") == "unassigned"
    ]
    llm_diagnostics["review_candidates"] = review_candidate_manifest

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