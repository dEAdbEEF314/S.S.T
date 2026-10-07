from typing import Any, Callable, Dict, List, Optional, Tuple

from ..steam_tracklist import validate_llm_tracklist
from .prompts import build_steam_tracklist_extraction_prompt

ProgressCallback = Callable[[Dict[str, Any]], None]


def extract_steam_tracklist(
    app_id: int,
    description_text: str,
    user_language: str,
    cache: Any,
    call_llm: Callable[..., Tuple[Optional[Dict[str, Any]], Dict[str, Any]]],
    progress_callback: Optional[ProgressCallback] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cache_key_input = description_text or ""
    request_kind = "steam_tracklist_extraction"
    cached = cache.get(cache_key_input, request_kind, user_language)
    if cached is not None:
        log_entry: Dict[str, Any] = {
            "request_kind": request_kind,
            "cache": cache.audit_hit(cache_key_input, request_kind, user_language),
            "response": cached,
        }
        tracks, errors = validate_llm_tracklist(cached)
        log_entry["validation_errors"] = errors
        if tracks:
            log_entry["tracklist_source"] = "STEAM_TEXT_TRACKLIST_LLM"
        return tracks, log_entry

    prompt = build_steam_tracklist_extraction_prompt(description_text, user_language)
    response, log_entry = call_llm(
        app_id,
        prompt,
        request_kind=request_kind,
        request_units=1,
        progress_callback=progress_callback,
    )
    tracks, errors = validate_llm_tracklist(response)
    log_entry["validation_errors"] = errors
    if not tracks:
        return [], log_entry
    log_entry["tracklist_source"] = "STEAM_TEXT_TRACKLIST_LLM"
    log_entry["cache"] = cache.put(
        cache_key_input,
        request_kind,
        user_language,
        response,
    )
    return tracks, log_entry