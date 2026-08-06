import logging
from typing import Dict, Any, Optional, Tuple
from .models import SteamMetadata
from .alignment_inputs import AlignmentInputBuilder

logger = logging.getLogger("sst.alignment_flow")

def collect_alignment_inputs(
    app_id: int,
    steam_meta: SteamMetadata,
    track_groups: Dict,
    alignment_input_builder: AlignmentInputBuilder,
    _diag: callable,
    on_track_complete: Optional[callable] = None,
 ) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Builds the canonical STEAM structure plus local and auxiliary signal bundles.
    """
    logger.info(f"[{app_id}] STEAM 骨格と補助 signal bundle を構築しています...")
    
    # 1. STEAM canonical structure
    v_steam = alignment_input_builder.build_steam_album(steam_meta)
    
    # 2. LOCAL file signals
    v_local = alignment_input_builder.build_local_album(track_groups)
    
    # 3. ACOUSTID / MBZ_RELEASE auxiliary signals
    v_fingerprint = alignment_input_builder.build_fingerprint_album(
        track_groups, on_track_complete=on_track_complete
    )
    _diag("AUXILIARY_SIGNAL_FINGERPRINT_BUILT", has_fingerprint=bool(v_fingerprint))
    
    # 4. MBZ_SEARCH auxiliary signals
    local_baseline = {
        "publisher": steam_meta.publisher,
        "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
        "tracks": [(t.get("title", ""), t.get("duration_ms", 0)) for t in v_local["tracks"]]
    }
    v_mbz_search = alignment_input_builder.build_mbz_search_album(
        app_id, steam_meta.name, len(steam_meta.store_tracklist), steam_meta, local_baseline
    )
    _diag("AUXILIARY_SIGNAL_MBZ_SEARCH_BUILT", has_mbz_search=bool(v_mbz_search))
    
    # Unification logic
    if v_fingerprint and v_mbz_search and v_fingerprint.get("mbid") == v_mbz_search.get("mbid"):
        logger.info(f"[{app_id}] ACOUSTID と MBZ_SEARCH が同一 MBID を指したため、補助 signal を verified として統合します。")
        v_fingerprint["source"] = "VERIFIED_MBZ"
        v_fingerprint["evidence"] = v_mbz_search.get("evidence", []) + ["AUDIO_TEXT_PERFECT_MATCH"]
        v_mbz_search = None # Drop the duplicate
    
    mbz_log = {"status": "signal_alignment_inputs"}
    return v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log


def consolidate_alignment_inputs(
    app_id: int,
    llm: Any,
    execution_profile: Any,
    v_steam: Dict[str, Any],
    v_local: Dict[str, Any],
    v_fingerprint: Optional[Dict[str, Any]],
    v_mbz_search: Optional[Dict[str, Any]],
    _diag: callable,
    llm_progress_callback: Optional[callable] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    final_metadata, llm_log = llm.align_slots(
        app_id,
        v_steam,
        v_fingerprint,
        v_mbz_search,
        v_local,
        execution_profile=execution_profile,
        progress_callback=llm_progress_callback,
    )
    _diag(
        "LLM_CONSOLIDATED",
        final_metadata_type=type(final_metadata).__name__,
        phase1_has_result=isinstance(llm_log.get("phase1_res"), dict),
        phase1_has_log=isinstance(llm_log.get("phase1_log"), dict),
    )
    
    return final_metadata, llm_log


def collect_alignment_inputs_and_consolidate(
    app_id: int,
    steam_meta: SteamMetadata,
    track_groups: Dict,
    alignment_input_builder: AlignmentInputBuilder,
    llm: Any,
    execution_profile: Any,
    _diag: callable,
    on_track_complete: Optional[callable] = None,
    llm_progress_callback: Optional[callable] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
    v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log = collect_alignment_inputs(
        app_id,
        steam_meta,
        track_groups,
        alignment_input_builder,
        _diag,
        on_track_complete=on_track_complete,
    )
    final_metadata, llm_log = consolidate_alignment_inputs(
        app_id,
        llm,
        execution_profile,
        v_steam,
        v_local,
        v_fingerprint,
        v_mbz_search,
        _diag,
        llm_progress_callback=llm_progress_callback,
    )
    return final_metadata, llm_log, v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log
