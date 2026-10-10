from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..models import LocalProcessResult, SteamMetadata
from ..report_generator import ReportGenerator


def save_album_package(
    app_id: int,
    status: str,
    steam_meta: SteamMetadata,
    summary_meta: Dict[str, Any],
    llm_log: Dict[str, Any],
    mbz_log: Dict[str, Any],
    processed_tracks_meta: List[Dict[str, Any]],
    mbz_candidates: List[Dict[str, Any]],
    localized_now_str: str,
    message: str,
    score: Any,
    reason: str,
    alignment_inputs_bundle: Dict[str, Any],
    quality: Any,
    unassigned_manifest: List[Dict[str, Any]],
    discord_msg: Any,
    temp_output: Path,
    *,
    config: Any,
    db: Any,
    package_manager: Any,
    get_localized_now: Callable[[], datetime],
    diagnostics: Dict[str, Any],
    diag: Callable[..., None],
) -> LocalProcessResult:
    log_bundle = {
        "mbz_log.json": mbz_log,
        "metadata.json": summary_meta,
        "llm_log.json": llm_log,
        "AUDIT_REPORT.html": ReportGenerator.generate_html_report(
            app_id,
            steam_meta,
            status,
            message,
            score,
            reason,
            processed_tracks_meta,
            llm_log,
            mbz_candidates,
            localized_now_str,
            config.resolved_metadata_source_priority,
            quality=quality,
            alignment_inputs=alignment_inputs_bundle,
            format_selection_audit=(summary_meta.get("audit") or {}).get("format_selection"),
            field_provenance_audit=(summary_meta.get("audit") or {}).get("field_provenance"),
        ),
    }
    review_candidates = (
        (llm_log.get("diagnostics") or {}).get("review_candidates") or []
    )
    if unassigned_manifest or review_candidates:
        log_bundle["review_manifest.json"] = {
            "app_id": app_id,
            "album_name": steam_meta.name,
            "status": status,
            "unassigned_files": unassigned_manifest,
            "review_candidates": review_candidates,
        }
    if discord_msg:
        log_bundle["DISCORD_MESSAGE.md"] = discord_msg

    p1_log = llm_log.get("phase1_log", {})
    if p1_log.get("human_prompt"):
        log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
    elif p1_log.get("prompt"):
        log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]

    diagnostics["packager_invoked"] = True
    diag("PACKAGE_SAVE_START", status=status, output_root=config.sst_output_dir)
    package_manager.save_local_package(
        app_id,
        status,
        steam_meta.name,
        temp_output,
        log_bundle,
        config.sst_output_dir,
        compression_strategy=getattr(config, "zip_compression_strategy", "auto"),
        deflate_level=getattr(config, "zip_deflate_level", 1),
    )
    diag("PACKAGE_SAVE_DONE", status=status)
    db.record_processed(
        app_id,
        status,
        steam_meta.name,
        get_localized_now().isoformat(),
        summary_meta,
    )
    return LocalProcessResult(
        app_id=app_id,
        status=status,
        album_name=steam_meta.name,
        confidence_score=score,
        confidence_reason=reason,
        message=message,
        metadata=summary_meta,
    )