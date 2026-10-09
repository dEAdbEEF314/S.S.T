import logging
from typing import Callable, Dict, Any, List, Optional, Tuple
from .models import SteamMetadata
from .alignment_inputs import (
    AlignmentInputBuilder,
    verify_steam_linked_mbz_release,
)

logger = logging.getLogger("sst.alignment_flow")

def collect_alignment_inputs(
    app_id: int,
    steam_meta: SteamMetadata,
    track_groups: Dict,
    alignment_input_builder: AlignmentInputBuilder,
    _diag: Callable[..., Any],
    on_track_complete: Optional[Callable[..., Any]] = None,
 ) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Builds the canonical STEAM structure plus local and auxiliary signal bundles.
    """
    logger.info(f"[{app_id}] STEAM 骨格と補助 signal bundle を構築しています...")
    
    # 1. STEAM canonical structure
    v_steam = alignment_input_builder.build_steam_album(steam_meta)
    
    # 2. LOCAL file signals
    v_local = alignment_input_builder.build_local_album(track_groups)
    
    # 3. MBZ_SEARCH first, so a direct product link can trigger full-track verification.
    local_baseline = {
        "publisher": steam_meta.publisher,
        "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
        "tracks": [(t.get("title", ""), t.get("duration_ms", 0)) for t in v_local["tracks"]]
    }
    v_mbz_search = alignment_input_builder.build_mbz_search_album(
        app_id, steam_meta.name, len(steam_meta.store_tracklist), steam_meta, local_baseline
    )
    _diag("AUXILIARY_SIGNAL_MBZ_SEARCH_BUILT", has_mbz_search=bool(v_mbz_search))

    # 4. ACOUSTID / MBZ_RELEASE auxiliary signals. A direct Steam-linked release
    # must be checked against every local source file before it can be authoritative.
    acoustid_candidates_by_key: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    v_fingerprint = alignment_input_builder.build_fingerprint_album(
        track_groups,
        on_track_complete=on_track_complete,
        force_all=bool(v_mbz_search and v_mbz_search.get("direct_steam_link")),
        on_track_candidates=lambda key, candidates: acoustid_candidates_by_key.__setitem__(
            key, candidates
        ),
    )
    _diag("AUXILIARY_SIGNAL_FINGERPRINT_BUILT", has_fingerprint=bool(v_fingerprint))

    verified_mapping = verify_steam_linked_mbz_release(
        v_mbz_search,
        track_groups,
        acoustid_candidates_by_key,
    )
    if verified_mapping is not None and v_mbz_search is not None:
        v_mbz_search["steam_link_verified"] = True
        v_mbz_search["verified_local_mapping"] = verified_mapping
        v_mbz_search["authoritative_tracklist"] = [
            {
                "disc": track["disc"],
                "number": str(track["position"]),
                "title": track["title"],
                "duration_s": (
                    track["duration_ms"] / 1000
                    if track.get("duration_ms") is not None
                    else None
                ),
                "recording_id": track["mbid"],
            }
            for track in v_mbz_search["tracks"]
        ]
        v_mbz_search["evidence"] = list(v_mbz_search.get("evidence") or []) + [
            "ALL_LOCAL_FILES_UNIQUELY_MATCHED_TO_RELEASE_RECORDINGS"
        ]
        _diag(
            "MBZ_STEAM_LINK_VERIFIED",
            release_id=v_mbz_search.get("mbid"),
            local_file_count=len(track_groups),
            release_recording_count=len(v_mbz_search["tracks"]),
            matched_release_recording_count=len(
                {track["recording_id"] for track in verified_mapping.values()}
            ),
        )
    elif v_mbz_search and v_mbz_search.get("direct_steam_link"):
        _diag(
            "MBZ_STEAM_LINK_NOT_VERIFIED",
            release_id=v_mbz_search.get("mbid"),
            local_file_count=len(track_groups),
            acoustid_track_count=len(acoustid_candidates_by_key),
        )
    
    # Unification logic
    if (
        v_fingerprint
        and v_mbz_search
        and not v_mbz_search.get("steam_link_verified")
        and v_fingerprint.get("mbid") == v_mbz_search.get("mbid")
    ):
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
    _diag: Callable[..., Any],
    llm_progress_callback: Optional[Callable[..., Any]] = None,
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
    _diag: Callable[..., Any],
    on_track_complete: Optional[Callable[..., Any]] = None,
    llm_progress_callback: Optional[Callable[..., Any]] = None,
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


def execute_alignment_flow(
    app_id: int,
    steam_meta: SteamMetadata,
    track_groups: Dict,
    execution_profile: Any,
    alignment_input_builder: AlignmentInputBuilder,
    llm: Any,
    diagnostics: Dict[str, Any],
    diag: Callable[..., Any],
    on_track_complete: Optional[Callable[[], None]],
    llm_progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    check_fast_track: Callable[..., Any],
    build_fast_track_alignment_result: Callable[..., Dict[str, Any]],
    build_mbz_candidates: Callable[..., List[Dict[str, Any]]],
    resolve_duplicate_mappings: Callable[..., None],
    reconcile_unassigned_slots: Callable[..., List[Dict[str, Any]]],
    build_slot_variant_index: Callable[..., Any],
    collect_inputs: Callable[..., Any],
    consolidate_inputs: Callable[..., Any],
) -> Tuple[
    Dict[str, Any],
    Dict[str, Any],
    List[Dict[str, Any]],
    Dict[tuple[int, str], List[Dict[str, Any]]],
    Dict[str, tuple[int, str]],
    str,
    Dict[str, Any],
    Dict[str, Any],
    Optional[Dict[str, Any]],
    Optional[Dict[str, Any]],
    Optional[Dict[str, Any]],
    Optional[Dict[str, Any]],
]:
    fast_track_ok, fast_track_map, fast_track_identity = check_fast_track(
        app_id, steam_meta, track_groups, mbz_candidates=[], fingerprint_bundle=None
    )

    if fast_track_ok:
        processing_route = "FAST_TRACK"
        diagnostics["processing_route"] = processing_route
        v_steam = alignment_input_builder.build_steam_album(steam_meta)
        v_local = alignment_input_builder.build_local_album(track_groups)
        v_fingerprint = None
        mbz_log = {"status": "fast_track_artist_from_lazy_artwork_search"}
        v_mbz_search = None
        mbz_candidates = []
        final_metadata = fast_track_map or {}
        fast_track_alignment_res = build_fast_track_alignment_result(final_metadata, v_local)
        llm_log = {
            "fast_track": True,
            "processing_route": processing_route,
            "phase1_res": {
                "album_confidence": 100,
                "mapping_confidence": 100,
                "data_quality": 100,
                "identity_confidence": 100,
                "integrity_quality": 100,
                "archive_vs_review_ratio": {"archive": 100, "review": 0},
                "confidence_reason": "SYSTEM: Deterministic fast-track (LLM/API bypassed)",
                "strategy": "FAST_TRACK",
                "semantic_label": "Archive",
                "global_tags": fast_track_identity or {},
                "concerns": [],
            },
            "alignment_res": fast_track_alignment_res,
        }
        diag("FAST_TRACK_SELECTED", mapped_track_count=len(final_metadata))
    else:
        diag("ON_DEMAND_SIGNAL_GATHERING_START")
        v_steam, v_local, v_fingerprint, v_mbz_search, mbz_log = collect_inputs(
            app_id, steam_meta, track_groups, alignment_input_builder, diag, on_track_complete
        )
        mbz_candidates = build_mbz_candidates(v_fingerprint, v_mbz_search)
        if v_mbz_search and v_mbz_search.get("steam_link_verified"):
            processing_route = "MBZ_STEAM_VERIFIED"
            diagnostics["processing_route"] = processing_route
            final_metadata = {}
            for track_id, mbz_track in v_mbz_search[
                "verified_local_mapping"
            ].items():
                final_metadata[track_id] = {
                    "matched_v_idx": mbz_track["mbz_track_index"],
                    "override_track": str(mbz_track["position"]),
                    "override_disc": str(mbz_track["disc"]),
                    "chosen_mbz_index": 0,
                    "mbz_track_index": mbz_track["mbz_track_index"],
                    "mbz_track_artist": mbz_track.get("recording_artist"),
                    "acoustid_mbid": mbz_track["recording_id"],
                    "alignment_evidence": [
                        "direct_steam_link",
                        "unique_acoustid_recording_id",
                    ],
                    "reason": "Direct Steam-linked MBZ release verified by one-to-one AcoustID Recording matches",
                }

            global_tags = {
                "canonical_album": v_mbz_search.get("album_name"),
                "canonical_album_artist": v_mbz_search.get("artist"),
                "canonical_year": v_mbz_search.get("year"),
                "canonical_label": v_mbz_search.get("label"),
                "chosen_mbz_index": 0,
            }
            mbz_slots: Dict[str, Dict[str, Any]] = {}
            local_tracks = v_local.get("tracks", []) if isinstance(v_local, dict) else []
            file_ids_by_tid = {
                f"{track['local_key'][0]}_{track['local_key'][1]}": [
                    str(file_id) for file_id in track.get("file_ids", [])
                ]
                for track in local_tracks
                if track.get("local_key")
            }
            for track_id, instruction in final_metadata.items():
                slot = v_mbz_search["verified_local_mapping"][track_id]
                slot_key = f"{slot['disc']}_{slot['position']}"
                mbz_slots.setdefault(
                    slot_key,
                    {
                        "files": [],
                        "confidence": 1.0,
                        "reason": instruction["reason"],
                    },
                )
                mbz_slots[slot_key]["files"].extend(file_ids_by_tid.get(track_id, []))
            all_file_ids = [
                str(file_id)
                for track in local_tracks
                for file_id in track.get("file_ids", [])
            ]
            assigned_file_ids = {
                file_id
                for slot in mbz_slots.values()
                for file_id in slot["files"]
            }
            alignment_res = {
                "slots": mbz_slots,
                "unassigned_files": [
                    file_id for file_id in all_file_ids if file_id not in assigned_file_ids
                ],
                "unassigned_reason": None,
            }
            llm_log = {
                "fast_track": False,
                "processing_route": processing_route,
                "phase1_res": {
                    "album_confidence": 100,
                    "mapping_confidence": 100,
                    "data_quality": 100,
                    "identity_confidence": 100,
                    "integrity_quality": 100,
                    "archive_vs_review_ratio": {"archive": 100, "review": 0},
                    "confidence_reason": (
                        "Direct MusicBrainz release link to this Steam AppID, with every local "
                        "audio file uniquely matched to a distinct release Recording."
                    ),
                    "strategy": "MBZ_STEAM_VERIFIED",
                    "semantic_label": "Archive",
                    "global_tags": global_tags,
                    "concerns": [],
                },
                "alignment_res": alignment_res,
                "verified_mbz_release": {
                    "mbid": v_mbz_search.get("mbid"),
                    "direct_steam_link": True,
                    "recording_count": len(v_mbz_search["tracks"]),
                    "local_file_count": len(track_groups),
                },
            }
            diag(
                "MBZ_STEAM_VERIFIED_ALIGNMENT_SELECTED",
                mapped_track_count=len(final_metadata),
                release_id=v_mbz_search.get("mbid"),
            )
        else:
            processing_route = "LLM_ONE_SHOT" if execution_profile.prefer_one_shot else "LLM_CHUNKED"
            diagnostics["processing_route"] = processing_route
            final_metadata, llm_log = consolidate_inputs(
                app_id,
                llm,
                execution_profile,
                v_steam,
                v_local,
                v_fingerprint,
                v_mbz_search,
                diag,
                llm_progress_callback=llm_progress_callback,
            )
            llm_log["processing_route"] = processing_route

    final_metadata = final_metadata or {}
    effective_steam_meta = steam_meta
    if v_mbz_search and v_mbz_search.get("steam_link_verified"):
        effective_steam_meta = steam_meta.model_copy(
            update={
                "store_tracklist": v_mbz_search["authoritative_tracklist"],
                "store_tracklist_source": "MBZ_STEAM_LINK_VERIFIED",
            }
        )

    if final_metadata:
        resolve_duplicate_mappings(
            app_id, final_metadata, effective_steam_meta, track_groups
        )

    phase1_result = llm_log.get("phase1_res", {})
    global_identity = phase1_result.get("global_tags", {}) if phase1_result else {}

    if final_metadata:
        reconciled = reconcile_unassigned_slots(
            final_metadata, track_groups, effective_steam_meta, global_identity
        )
        if reconciled:
            diag("DETERMINISTIC_RECONCILED", reconciled_count=len(reconciled))

    slot_variant_index, track_to_slot_index = build_slot_variant_index(
        final_metadata, track_groups, effective_steam_meta
    )
    multi_variant_slot_count = sum(
        1 for variants in slot_variant_index.values() if len(variants) > 1
    )
    diag(
        "SLOT_VARIANT_BUILT",
        slot_count=len(slot_variant_index),
        variant_count=sum(len(variants) for variants in slot_variant_index.values()),
        multi_variant_slot_count=multi_variant_slot_count,
    )

    alignment_inputs_bundle = {
        "STEAM": v_steam,
        "ACOUSTID_MBID": v_fingerprint,
        "MBZ_SEARCH": v_mbz_search,
        "LOCAL_SIGNALS": v_local,
    }

    return (
        final_metadata,
        llm_log,
        mbz_candidates,
        slot_variant_index,
        track_to_slot_index,
        processing_route,
        alignment_inputs_bundle,
        mbz_log,
        v_steam,
        v_local,
        v_fingerprint,
        v_mbz_search,
    )
