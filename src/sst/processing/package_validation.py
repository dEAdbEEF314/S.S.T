import logging
from typing import Any, Callable, Dict, List, Tuple

from ..models import SteamMetadata
from ..validator import ResultValidator

logger = logging.getLogger("sst.processing.package_validation")


def validate_album_package(
    app_id: int,
    steam_meta: SteamMetadata,
    processed_tracks_meta: List[Dict[str, Any]],
    llm_log: Dict[str, Any],
    mbz_candidates: List[Dict[str, Any]],
    any_audio_failures: bool,
    any_audio_warnings: bool,
    audio_warned_tracks: List[str],
    unassigned_manifest: List[Dict[str, Any]],
    temp_output: Any,
    validate_archive_artifacts: Callable[..., List[str]],
) -> Tuple[str, str, Any, Any, str, List[str]]:
    status, message, score, quality, reason = ResultValidator.validate(
        app_id,
        processed_tracks_meta,
        llm_log,
        mbz_candidates,
        steam_meta,
        any_audio_failures,
        any_audio_warnings,
        audio_warned_tracks=audio_warned_tracks,
        unassigned_manifest=unassigned_manifest,
    )
    if audio_warned_tracks:
        logger.info(
            "[%s] %s: 本来Archive相当ですが、微小問題（音声品質警告）を含むためReview送りとなりました。対象トラック: %s",
            app_id,
            steam_meta.name,
            ", ".join(audio_warned_tracks),
        )
    artifact_issues = validate_archive_artifacts(
        app_id,
        temp_output,
        processed_tracks_meta,
        steam_meta,
    )
    if status == "archive" and artifact_issues:
        status = "review"
        existing_message = message.strip("[]") if message else ""
        all_issues = [part for part in [existing_message, *artifact_issues] if part]
        message = f"[{', '.join(all_issues)}]"
        reason = f"{reason}; archive artifact preflight failed"
    return status, message, score, quality, reason, artifact_issues