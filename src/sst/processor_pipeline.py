import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Callable, Dict, Any, Optional

from .models import SteamMetadata, LocalProcessResult
from .report_generator import ReportGenerator
from .packager import PackageManager

logger = logging.getLogger("sst.processor_pipeline")

def handle_early_review_return(
    app_id: int,
    steam_meta: SteamMetadata,
    track_count: int,
    llm_log: Dict[str, Any],
    v_steam: Dict[str, Any],
    v_local: Dict[str, Any],
    v_fingerprint: Optional[Dict[str, Any]],
    v_mbz_search: Optional[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    _diag: Callable[..., Any],
    get_localized_now: Callable[[], Any],
    send_notifications: Callable[..., Any],
    working_dir: Path,
    output_dir: str,
    db: Any,
    config: Any,
    preserve_working_files: bool = False,
) -> LocalProcessResult:
    p1_log = llm_log.get("phase1_log", {})
    p1_res = llm_log.get("phase1_res", {})
    score = p1_res.get("album_confidence", p1_res.get("identity_confidence", 0)) if isinstance(p1_res, dict) else 0
    error_msg = p1_res.get("confidence_reason") if isinstance(p1_res, dict) else (p1_log.get("error") or "Manual Review Required")
    if error_msg is None:
        error_msg = "No reason provided by LLM."
        
    diagnostics["review_cause_code"] = "EARLY_REVIEW_RETURN"
    steam_expected_slots = len(steam_meta.store_tracklist or [])
    if not p1_res:
        diagnostics["upstream_cause_code"] = "LLM_RESPONSE_MISSING"
        final_msg = f"LLM Failure: {error_msg}"
    elif score >= 90 and steam_expected_slots > 0:
        diagnostics["upstream_cause_code"] = "TRACK_MAPPING_FAILURE"
        final_msg = f"Track Mapping Failure (No valid slot assignments): {error_msg}"
    else:
        diagnostics["upstream_cause_code"] = "PRE_ALIGNMENT_REVIEW_GATE"
        if steam_expected_slots == 0:
            final_msg = f"Low Confidence (PRE_ALIGNMENT_REVIEW_GATE: Steam Tracklist Missing): {error_msg}"
        else:
            final_msg = f"Low Confidence ({diagnostics['upstream_cause_code']}): {error_msg}"
    
    adopted_slots = 0
    unassigned_slots = steam_expected_slots
    diagnostics["steam_expected_slots"] = steam_expected_slots
    diagnostics["adopted_slots"] = adopted_slots
    diagnostics["unassigned_slots"] = unassigned_slots
    diagnostics["primary_review_cause"] = final_msg
    diagnostics["secondary_review_causes"] = []
    _diag(
        "EARLY_REVIEW_RETURN",
        review_cause_code=diagnostics["review_cause_code"],
        upstream_cause_code=diagnostics["upstream_cause_code"],
        album_confidence=score,
        error=error_msg,
    )
    
    summary_meta = {
        "app_id": app_id,
        "album_name": steam_meta.name,
        "status": "review",
        "message": final_msg,
        "confidence_score": score,
        "album_confidence": score,
        "mapping_confidence": p1_res.get("mapping_confidence") if isinstance(p1_res, dict) else None,
        "data_quality": p1_res.get("data_quality") if isinstance(p1_res, dict) else None,
        "confidence_reason": error_msg,
        "processed_at": get_localized_now().isoformat(),
        "tracks": [],
        "steam_info": steam_meta.model_dump(),
        "audit": {
            "steam_expected_slots": steam_expected_slots,
            "final_adopted_slots": adopted_slots,
            "final_duplicate_slots": 0,
            "steam_legitimate_unknown": 0,
            "anomalous_unknown": 0,
            "input_file_count": len(steam_meta.store_tracklist or []),
            "adopted_file_count": 0,
            "unassigned_file_count": len(steam_meta.store_tracklist or []),
            "archive_artifact_issues": [],
            "review_phase": "EARLY_REVIEW",
        },
        "diagnostics": diagnostics,
    }
    
    mbz_candidates = []
    discord_msg = send_notifications(app_id, steam_meta.name, "review", final_msg, score, error_msg, llm_log, False, track_count, mbz_candidates)
    
    alignment_inputs_bundle = {
        "STEAM": v_steam,
        "ACOUSTID_MBID": v_fingerprint,
        "MBZ_SEARCH": v_mbz_search,
        "LOCAL_SIGNALS": v_local
    }
    
    localized_now_str = get_localized_now().strftime('%Y-%m-%d %H:%M:%S')
    log_bundle = {
        "metadata.json": summary_meta,
        "llm_log.json": llm_log,
        "AUDIT_REPORT.html": ReportGenerator.generate_html_report(
            app_id, steam_meta, "review", final_msg, score, error_msg, [], llm_log, mbz_candidates, localized_now_str, config.resolved_metadata_source_priority, quality=0, alignment_inputs=alignment_inputs_bundle
        )
    }
    if discord_msg:
        log_bundle["DISCORD_MESSAGE.md"] = discord_msg
    if p1_log.get("human_prompt"):
        log_bundle["LLM_PROMPT.md"] = p1_log["human_prompt"]
    elif p1_log.get("prompt"):
        log_bundle["LLM_PROMPT.md"] = p1_log["prompt"]
    
    run_id = datetime.now().strftime('%H%M%S')
    temp_output = working_dir / f"early_review_{app_id}_{run_id}"
    temp_output.mkdir(parents=True, exist_ok=True)
    
    diagnostics["packager_invoked"] = True
    _diag("PACKAGE_SAVE_START", status="review", output_root=output_dir)
    PackageManager.save_local_package(app_id, "review", steam_meta.name, temp_output, log_bundle, output_dir)
    _diag("PACKAGE_SAVE_DONE", status="review")
    
    if preserve_working_files:
        logger.info(
            "[%s] 早期Reviewの中間ファイルを保持します "
            "(preserve_working_files=true): %s",
            app_id,
            temp_output,
        )
    else:
        shutil.rmtree(temp_output, ignore_errors=True)
        logger.info("[%s] 早期Reviewの中間ディレクトリを削除しました: %s", app_id, temp_output)
    
    if db:
        db.record_processed(app_id, "review", steam_meta.name, get_localized_now().isoformat(), summary_meta)
    return LocalProcessResult(app_id=app_id, status="review", album_name=steam_meta.name, confidence_score=score, confidence_reason=error_msg, message=final_msg, metadata=summary_meta)
