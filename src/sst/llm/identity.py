import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .prompts import build_identity_prompt

logger = logging.getLogger("sst.llm.identity")

ProgressCallback = Callable[[Dict[str, Any]], None]


def resolve_album_identity(
    app_id: int,
    s_steam: Dict[str, Any],
    s_fingerprint: Dict[str, Any],
    s_mbz_search: Dict[str, Any],
    s_local: Dict[str, Any],
    v_steam: Dict[str, Any],
    v_local: Dict[str, Any],
    v_fingerprint: Optional[Dict[str, Any]],
    resolved_num_ctx: Optional[int],
    progress_callback: Optional[ProgressCallback],
    full_logs: List[Dict[str, Any]],
    *,
    user_language: str,
    cache: Any,
    call_llm: Callable[..., Tuple[Optional[Dict[str, Any]], Dict[str, Any]]],
    normalize_result: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    identity_prompt = build_identity_prompt(
        s_steam,
        s_fingerprint,
        s_mbz_search,
        s_local,
        user_language,
    )
    local_tracks = v_local.get("tracks", [])
    cache_key_input = json.dumps(
        {
            "steam": s_steam,
            "fingerprint": s_fingerprint,
            "mbz_search": s_mbz_search,
            "local": s_local,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    cached_identity = cache.get(cache_key_input, "identity", user_language)
    if cached_identity is not None:
        global_log: Dict[str, Any] = {
            "request_kind": "identity",
            "cache": cache.audit_hit(cache_key_input, "identity", user_language),
            "response": cached_identity,
        }
        full_logs.append(global_log)
        global_res = cached_identity
    else:
        global_res, global_log = call_llm(
            app_id,
            identity_prompt,
            num_ctx=resolved_num_ctx,
            request_kind="identity",
            request_units=len(local_tracks),
            progress_callback=progress_callback,
        )
        full_logs.append(global_log)
        if global_res:
            global_log["cache"] = cache.put(
                cache_key_input,
                "identity",
                user_language,
                global_res,
            )

    steam_count = len(v_steam.get("tracks", []))
    local_count = len(v_local.get("tracks", []))

    if not global_res:
        if steam_count > 0 and steam_count == local_count:
            logger.warning(
                "[%s] Identity LLM call failed/truncated. Activating STEAM-TRUST fallback (%s tracks).",
                app_id,
                steam_count,
            )
            global_res = {
                "album_confidence": 100,
                "mapping_confidence": 90,
                "data_quality": 80,
                "identity_confidence": 100,
                "integrity_quality": 100,
                "archive_vs_review_ratio": {"archive": 100, "review": 0},
                "confidence_reason": "SYSTEM: STEAM-TRUSTフォールバック (LLM応答切断のため構造一致を採用)",
                "strategy": "STEAM_BASED",
                "semantic_label": "Steam Tracklist",
                "global_tags": {
                    "canonical_album_artist": v_steam.get("artist"),
                    "canonical_genre": "Soundtrack",
                    "canonical_year": v_steam.get("year"),
                    "canonical_label": v_steam.get("label"),
                    "chosen_mbz_id": None,
                },
                "concerns": ["LLM identity truncated; fallen back to Steam metadata"],
            }
        else:
            return None, {"phase1_res": None, "phase1_log": global_log}

    global_res = normalize_result(global_res)

    unique_local_slots = len({
        (
            str(track.get("disc", 1)),
            str(
                track.get("track_num")
                or track.get("filename_track")
                or track.get("title")
                or track.get("norm_stem")
                or ""
            ),
        )
        for track in local_tracks
    }) if local_tracks else 0
    structural_match = (
        steam_count > 0
        and (steam_count == local_count or steam_count == unique_local_slots)
    )
    current_conf = global_res.get("identity_confidence", 0)

    if structural_match and current_conf < 100 and (not v_fingerprint or current_conf >= 80):
        logger.info(
            "[%s] Applying STEAM-TRUST: Structural match detected "
            "(Steam: %s, Local: %s, Unique: %s). Boosting confidence to 100%%.",
            app_id,
            steam_count,
            local_count,
            unique_local_slots,
        )
        global_res["identity_confidence"] = 100
        global_res["album_confidence"] = 100
        global_res["mapping_confidence"] = 100
        global_res["integrity_quality"] = 100
        global_res["data_quality"] = 100
        global_res["archive_vs_review_ratio"] = {"archive": 100, "review": 0}
        global_res["strategy"] = "STEAM_BASED"
        global_res["confidence_reason"] = (
            f"SYSTEM: STEAM-TRUSTにより確信度を100%に引き上げました "
            f"({steam_count}トラックとの構造的一致)"
        )

    confidence = int(global_res.get("identity_confidence", 0))
    if 0 < confidence <= 1:
        confidence = int(confidence * 100)
        global_res["identity_confidence"] = confidence

    ratio = global_res.get("archive_vs_review_ratio", {})
    if not isinstance(ratio, dict) or not ratio:
        global_res["archive_vs_review_ratio"] = {"archive": 0, "review": 100}
    if confidence < 85:
        concerns = global_res.setdefault("concerns", [])
        concerns.append("Low album confidence before slot alignment")

    return global_res, None