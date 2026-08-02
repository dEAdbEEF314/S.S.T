import logging
from typing import Dict, Any, Optional, Tuple
from .models import SteamMetadata
from .virtual_album import VirtualAlbumBuilder

logger = logging.getLogger("sst.virtual_album_flow")

def build_and_consolidate_virtual_albums(
    app_id: int,
    steam_meta: SteamMetadata,
    track_groups: Dict,
    virtual_album_builder: VirtualAlbumBuilder,
    llm: Any,
    execution_profile: Any,
    _diag: callable,
    on_track_complete: Optional[callable] = None,
    llm_progress_callback: Optional[callable] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Builds the four Virtual Albums (STEAM, LOCAL, FINGERPRINT, MBZ_SEARCH),
    resolves conflicts, and invokes the LLM to consolidate them into final metadata.
    
    Returns:
        (final_metadata, llm_log, v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log)
    """
    logger.info(f"[{app_id}] アイデンティティ統合のために仮想アルバムを構築しています...")
    
    # 1. STEAM Virtual Album
    v_steam = virtual_album_builder.build_steam_album(steam_meta)
    
    # 2. LOCAL Virtual Album
    v_local = virtual_album_builder.build_local_album(track_groups)
    
    # 3. FINGERPRINT Virtual Album (Majority Vote)
    v_fingerprint = virtual_album_builder.build_fingerprint_album(
        track_groups, on_track_complete=on_track_complete
    )
    _diag("VIRTUAL_ALBUM_FINGERPRINT_BUILT", has_fingerprint=bool(v_fingerprint))
    
    # 4. MBZ_SEARCH Virtual Album (Semantic Truth)
    local_baseline = {
        "publisher": steam_meta.publisher,
        "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
        "tracks": [(t.get("title", ""), t.get("duration_ms", 0)) for t in v_local["tracks"]]
    }
    v_mbz_search = virtual_album_builder.build_mbz_search_album(
        app_id, steam_meta.name, len(steam_meta.store_tracklist), steam_meta, local_baseline
    )
    _diag("VIRTUAL_ALBUM_MBZ_SEARCH_BUILT", has_mbz_search=bool(v_mbz_search))
    
    # Unification logic
    if v_fingerprint and v_mbz_search and v_fingerprint.get("mbid") == v_mbz_search.get("mbid"):
        logger.info(f"[{app_id}] FINGERPRINT and MBZ_SEARCH point to the same MBID. Creating VERIFIED Virtual Album.")
        v_fingerprint["source"] = "VERIFIED_MBZ"
        v_fingerprint["evidence"] = v_mbz_search.get("evidence", []) + ["AUDIO_TEXT_PERFECT_MATCH"]
        v_mbz_search = None # Drop the duplicate
    
    # LLM Consolidation
    mbz_log = {"status": "virtual_album_flow"} # Initialize for log bundle
    final_metadata, llm_log = llm.consolidate_virtual_albums(
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
    
    return final_metadata, llm_log, v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log
