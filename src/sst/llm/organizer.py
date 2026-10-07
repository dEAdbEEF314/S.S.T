import logging
from typing import List, Dict, Any, Optional, Tuple, Callable

from ..config import DEFAULT_METADATA_SOURCE_PRIORITY
from .client import LLMClient
from .normalization import (
    build_slot_view,
    build_slot_view_from_final_instructions,
    normalize_identity_result,
    normalize_track_mapping_result,
    resolve_slot_key_to_v_idx,
)
from .prompts import build_mapping_prompt
from .identity import resolve_album_identity
from .coherence import merge_track_instructions, resolve_mapping_references
from .alignment_segments import run_differential_segments
from .prematch import extract_deterministic_prematches, resolve_prematch_signals
from .assignment_validation import (
    reject_contradictory_slot_assignments,
    titles_are_compatible,
)
from .tracklist_extractor import extract_steam_tracklist

logger = logging.getLogger('sst.llm.organizer')

ProgressCallback = Callable[[Dict[str, Any]], None]

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = 'gemini-1.5-pro', 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = 'ja',
                 llm_backend: str = 'GEMINI',
                 draft_model: Optional[str] = None,
                 llm_cloud_max_tokens: int = 8192,
                 ollama_num_ctx: int = 32768,
                 ollama_num_predict: int = 4096,
                 ollama_think: bool = False,
                 llm_vram_scheduling_enabled: bool = True,
                 llm_request_parallelism_enabled: bool = True,
                 llm_request_parallelism_max_workers: int = 4,
                 request_timeout: int = 3600,
                 chunk_size_virtual: int = 20,
                 chunk_size_metadata_ollama: int = 10,
                 chunk_size_metadata_cloud: int = 30,
                 chunk_adaptive: bool = True,
                 chunk_output_tokens_per_track: int = 180,
                 chunk_output_safety_ratio: float = 0.75,
                 metadata_source_priority: str = DEFAULT_METADATA_SOURCE_PRIORITY,
                 max_retries: int = 3,
                 output_budget_safety_ratio: float = 0.25,
                 adaptive_degraded_prompt_enabled: bool = True,
                 llm_cache_enabled: bool = True,
                 llm_cache_ttl_seconds: int = 86400,
                 llm_cache_path: str = "data/llm_cache.json",
                 retry_delay: float = 5.0,
                 retry_backoff: float = 1.5,
                 health_check_timeout: float = 10.0,
                 **kwargs):
        self.user_language = user_language
        self.llm_backend = llm_backend.upper()
        self.llm_request_parallelism_enabled = llm_request_parallelism_enabled
        self.llm_request_parallelism_max_workers = max(1, llm_request_parallelism_max_workers)
        self.chunk_size_virtual = chunk_size_virtual
        self.chunk_adaptive = chunk_adaptive
        self.ollama_num_predict = ollama_num_predict
        self.llm_cloud_max_tokens = llm_cloud_max_tokens
        self.chunk_output_safety_ratio = max(0.2, min(0.95, chunk_output_safety_ratio))
        self.chunk_output_tokens_per_track = max(1, chunk_output_tokens_per_track)
        self.llm_limit_tpm = tpm
        from .llm_cache import LLMResultCache
        self.llm_cache = LLMResultCache(
            cache_path=llm_cache_path,
            ttl_seconds=llm_cache_ttl_seconds,
            enabled=llm_cache_enabled,
        )
        
        self.client = LLMClient(
            api_key=api_key, base_url=base_url, model=model, rpm=rpm, tpm=tpm, rpd=rpd,
            llm_backend=llm_backend, draft_model=draft_model, llm_cloud_max_tokens=llm_cloud_max_tokens,
            ollama_num_ctx=ollama_num_ctx, ollama_num_predict=ollama_num_predict,
            ollama_think=ollama_think,
            llm_vram_scheduling_enabled=llm_vram_scheduling_enabled,
            request_timeout=request_timeout, chunk_output_tokens_per_track=chunk_output_tokens_per_track,
            max_retries=max_retries,
            output_budget_safety_ratio=output_budget_safety_ratio,
            adaptive_degraded_prompt_enabled=adaptive_degraded_prompt_enabled,
            retry_delay=retry_delay,
            retry_backoff=retry_backoff,
            health_check_timeout=health_check_timeout,
        )

    def set_vram_manager(self, vram_manager: Any):
        self.client.set_vram_manager(vram_manager)

    def _resolve_execution_num_ctx(
        self,
        execution_profile: Optional[Any],
        requested_num_ctx: Optional[int],
    ) -> Optional[int]:
        resolved_num_ctx = requested_num_ctx or self.client.ollama_num_ctx
        if not execution_profile or resolved_num_ctx is None:
            return resolved_num_ctx
        return min(max(1, int(execution_profile.num_ctx_cap)), max(1, int(resolved_num_ctx)))

    def _resolve_phase2_worker_count(
        self,
        execution_profile: Optional[Any],
        segment_count: int,
    ) -> int:
        if segment_count <= 0:
            return 1
        worker_cap = self.llm_request_parallelism_max_workers
        if execution_profile and getattr(execution_profile, "phase2_parallel_workers", None) is not None:
            worker_cap = min(worker_cap, max(1, int(execution_profile.phase2_parallel_workers)))
        return max(1, min(worker_cap, segment_count))

    def check_availability(self) -> bool:
        return self.client.check_availability()

    def extract_steam_tracklist(
        self,
        app_id: int,
        description_text: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        return extract_steam_tracklist(
            app_id,
            description_text,
            self.user_language,
            self.llm_cache,
            self._call_llm,
            progress_callback,
        )

    def _call_llm(
        self,
        app_id: int,
        prompt: str,
        num_ctx: Optional[int] = None,
        request_kind: str = "generic",
        request_units: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        return self.client.call_llm(
            app_id,
            prompt,
            num_ctx=num_ctx,
            request_kind=request_kind,
            request_units=request_units,
            progress_callback=progress_callback,
        )

    def _resolve_mapping_references(
        self,
        start_idx: int,
        full_ref_steam: List[Dict[str, Any]],
        full_ref_fingerprint: List[Dict[str, Any]],
        coherence_mappings: Optional[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return resolve_mapping_references(
            start_idx,
            full_ref_steam,
            full_ref_fingerprint,
            coherence_mappings,
        )

    def _merge_track_instructions(
        self,
        track_res: Dict[str, Any],
        local_tracks: List[Dict[str, Any]],
        chunk: List[Dict[str, Any]],
        global_res: Dict[str, Any],
        ref_fingerprint: List[Dict[str, Any]],
        full_ref_mbz_search: List[Dict[str, Any]],
        v_mbz_search: Optional[Dict[str, Any]],
        full_ref_steam: Optional[List[Dict[str, Any]]] = None,
        prematch_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return merge_track_instructions(
            track_res,
            local_tracks,
            chunk,
            global_res,
            ref_fingerprint,
            full_ref_mbz_search,
            v_mbz_search,
            full_ref_steam,
            prematch_map,
            normalize_mapping_result=self._normalize_track_mapping_result,
        )

    @staticmethod
    def _resolve_slot_key_to_v_idx(slot_key: str, full_ref_steam: Optional[List[Dict[str, Any]]]) -> Optional[int]:
        return resolve_slot_key_to_v_idx(slot_key, full_ref_steam)

    @classmethod
    def _normalize_track_mapping_result(
        cls,
        track_res: Dict[str, Any],
        full_ref_steam: Optional[List[Dict[str, Any]]],
        prematch_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return normalize_track_mapping_result(track_res, full_ref_steam, prematch_map)

    @staticmethod
    def _normalize_identity_result(global_res: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_identity_result(global_res)

    @staticmethod
    def _build_slot_view(track_res: Dict[str, Any], local_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return build_slot_view(track_res, local_tracks)

    @staticmethod
    def _build_alignment_diagnostics(
        final_instructions: Dict[str, Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
        segment_results: Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]],
    ) -> Dict[str, Any]:
        """Summarize merge completeness without changing the validation decision."""
        expected_file_ids = [
            str(file_id)
            for track in local_tracks
            for file_id in track.get("file_ids", [])
        ]
        local_file_ids_by_tid = {}
        for track in local_tracks:
            local_key = track.get("local_key")
            if local_key:
                local_file_ids_by_tid[f"{local_key[0]}_{local_key[1]}"] = [
                    str(file_id) for file_id in track.get("file_ids", [])
                ]

        assigned_file_ids = [
            file_id
            for tid in final_instructions
            for file_id in local_file_ids_by_tid.get(tid, [])
        ]
        expected_set = set(expected_file_ids)
        assigned_set = set(assigned_file_ids)
        duplicate_assignments = sorted(
            file_id for file_id in assigned_file_ids
            if assigned_file_ids.count(file_id) > 1
        )
        chunk_diagnostics = []
        rejected_slot_keys: List[str] = []
        rejected_file_ids: List[str] = []
        for start_idx in sorted(segment_results):
            instructions, segment_logs = segment_results[start_idx]
            chunk_diagnostics.append({
                "start_idx": start_idx,
                "instruction_count": len(instructions),
                "log_count": len(segment_logs),
            })
            for log in segment_logs:
                if isinstance(log, dict):
                    rejected_slot_keys.extend(log.get("rejected_slot_keys") or [])
                    rejected_file_ids.extend(log.get("rejected_file_ids") or [])

        return {
            "input_file_count": len(expected_file_ids),
            "final_instruction_count": len(final_instructions),
            "final_assigned_file_count": len(assigned_set),
            "final_unassigned_file_ids": sorted(expected_set - assigned_set),
            "unknown_instruction_tids": sorted(
                set(final_instructions) - set(local_file_ids_by_tid)
            ),
            "duplicate_assignment_file_ids": sorted(set(duplicate_assignments)),
            "rejected_slot_keys": sorted(set(rejected_slot_keys)),
            "rejected_file_ids": sorted(set(rejected_file_ids)),
            "chunk_count": len(segment_results),
            "chunks": chunk_diagnostics,
        }

    @staticmethod
    def _titles_are_compatible(left: str, right: str) -> bool:
        return titles_are_compatible(left, right)

    @classmethod
    def _reject_contradictory_slot_assignments(
        cls,
        final_instructions: Dict[str, Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        return reject_contradictory_slot_assignments(
            final_instructions,
            local_tracks,
            full_ref_steam,
            title_compatibility=cls._titles_are_compatible,
        )

    @staticmethod
    def _build_slot_view_from_final_instructions(
        final_instructions: Dict[str, Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return build_slot_view_from_final_instructions(final_instructions, local_tracks)

    @staticmethod
    def _prepare_chunk_payload(
        chunk: List[Dict[str, Any]],
        prematch_map: Optional[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        s_chunk = []
        chunk_prematch_hints = {}
        for track in chunk:
            fids = track.get("file_ids", [])
            s_chunk.append({
                "file_ids": fids,
                "t": track.get("title"),
                "d": track.get("disc"),
                "dur": (track.get("duration_ms", 0) // 1000) if track.get("duration_ms") else None,
            })
            if prematch_map:
                for fid in fids:
                    pm = prematch_map.get(str(fid))
                    if pm and pm.evidence:
                        chunk_prematch_hints[str(fid)] = pm.to_dict()
        return s_chunk, chunk_prematch_hints

    @staticmethod
    def _recover_prematch_fallback_slots(
        chunk: List[Dict[str, Any]],
        prematch_map: Optional[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback_slots = {}
        for track in chunk:
            for fid in track.get("file_ids", []):
                fid_str = str(fid)
                pm = prematch_map.get(fid_str) if prematch_map else None
                if pm and (pm.acoustid_steam_slot or pm.mbz_search_steam_slot or pm.override_track):
                    target_slot = str(pm.acoustid_steam_slot or pm.mbz_search_steam_slot or pm.override_track)
                    fallback_slots[target_slot] = {
                        "files": [fid_str],
                        "confidence": 0.95,
                        "reason": f"SYSTEM: Prematch fallback ({pm.evidence[0] if pm.evidence else 'rule'})",
                    }
                else:
                    t_num = track.get("n") or track.get("track_num")
                    if t_num and str(t_num).isdigit() and full_ref_steam and 0 < int(t_num) <= len(full_ref_steam):
                        fallback_slots[str(t_num)] = {
                            "files": [fid_str],
                            "confidence": 0.90,
                            "reason": f"SYSTEM: Number match fallback (#{t_num})",
                        }
        return fallback_slots

    def _process_track_mapping_segment(
        self,
        app_id: int,
        start_idx: int,
        segment_tracks: List[Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
        global_res: Dict[str, Any],
        s_mbz_search: Dict[str, Any],
        v_mbz_search: Optional[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
        full_ref_fingerprint: List[Dict[str, Any]],
        full_ref_mbz_search: List[Dict[str, Any]],
        coherence_mappings: Optional[Dict[str, Any]],
        num_ctx: Optional[int],
        base_chunk_size: int,
        progress_callback: Optional[ProgressCallback],
        prematch_map: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        segment_logs: List[Dict[str, Any]] = []
        segment_instructions: Dict[str, Dict[str, Any]] = {}
        current_base_chunk_size = max(1, base_chunk_size)
        offset = 0

        while offset < len(segment_tracks):
            current_chunk_size = min(current_base_chunk_size, len(segment_tracks) - offset)
            chunk_start = start_idx + offset
            chunk = segment_tracks[offset:offset + current_chunk_size]
            s_chunk, chunk_prematch_hints = self._prepare_chunk_payload(chunk, prematch_map)

            ref_steam, ref_fingerprint = self._resolve_mapping_references(
                chunk_start,
                full_ref_steam,
                full_ref_fingerprint,
                coherence_mappings,
            )
            mapping_prompt = build_mapping_prompt(
                global_res,
                s_mbz_search or {},
                v_mbz_search,
                ref_steam,
                ref_fingerprint,
                s_chunk,
                chunk_start,
                self.user_language,
                prematch_hints=chunk_prematch_hints or None,
            )
            track_res, track_log = self._call_llm(
                app_id,
                mapping_prompt,
                num_ctx=num_ctx,
                request_kind="track_mapping",
                request_units=len(chunk),
                progress_callback=progress_callback,
            )

            if not track_res and self._is_truncation_log(track_log) and current_chunk_size > 1:
                shrink_to = max(1, current_chunk_size // 2)
                logger.warning(
                    f"[{app_id}] LLM response appears truncated for virtual chunk at index={chunk_start}. "
                    f"Reducing chunk size {current_chunk_size} -> {shrink_to}."
                )
                current_base_chunk_size = shrink_to
                continue

            segment_logs.append(track_log)
            if track_res is None:
                fallback_slots = self._recover_prematch_fallback_slots(chunk, prematch_map, full_ref_steam)
                if fallback_slots:
                    logger.info(f"[{app_id}] Truncation/LLM failure at index={chunk_start}: recovered {len(fallback_slots)} slots via deterministic prematch fallback.")
                    track_res = {"slots": fallback_slots, "unassigned_files": []}
                else:
                    logger.warning(
                        "[%s] Track mapping returned no result for virtual chunk at index=%s; "
                        "continuing with an empty instruction set.",
                        app_id,
                        chunk_start,
                    )
                    track_res = {}
            segment_instructions.update(
                self._merge_track_instructions(
                    track_res,
                    local_tracks,
                    chunk,
                    global_res,
                    ref_fingerprint,
                    full_ref_mbz_search,
                    v_mbz_search,
                    full_ref_steam,
                    prematch_map=prematch_map,
                )
            )
            offset += len(chunk)

        return start_idx, segment_instructions, segment_logs

    def _adaptive_chunk_size(self, base_chunk_size: int, execution_profile: Optional[Any] = None) -> int:
        if not self.chunk_adaptive:
            return max(1, base_chunk_size)

        # 1. 出力限界(Max Tokens)の算出
        if self.llm_backend == "OLLAMA":
            budget_limit = self.ollama_num_predict
        else:
            budget_limit = self.llm_cloud_max_tokens
            
        safe_output_budget = int(budget_limit * self.chunk_output_safety_ratio)
        by_output = max(1, safe_output_budget // self.chunk_output_tokens_per_track)
        
        if self.llm_backend == "OLLAMA":
            dynamic_limit = by_output
        else:
            # 外部APIの場合: 毎分トークン(TPM)の枯渇による429エラーを防止する
            # 1曲あたりの総消費見積もり(入力150+出力180=330)、オーバーヘッド約1000
            tpm_limit = self.llm_limit_tpm
            safe_tpm_budget = int(tpm_limit * 0.8) # 80%の安全マージン
            by_tpm = max(1, (safe_tpm_budget - 1000) // 330)
            dynamic_limit = min(by_output, by_tpm)

        prefer_one_shot = getattr(execution_profile, "prefer_one_shot", False) if execution_profile else False
        if not prefer_one_shot:
            return max(1, min(base_chunk_size, dynamic_limit))
        else:
            # One-shot を選好する場合でも、1リクエストの巨大化によるトークン爆発とモデル精度劣化を防ぐため安全上限(50曲)を設ける
            max_safe_one_shot = max(base_chunk_size, min(50, dynamic_limit))
            return max(1, max_safe_one_shot)

    def _is_truncation_log(self, log_data: Dict[str, Any]) -> bool:
        if not isinstance(log_data, dict):
            return False
        if log_data.get("error_code") == "response_truncated":
            return True
        err = str(log_data.get("error") or "").lower()
        return "truncat" in err or "max_tokens" in err or "length" in err

    def _simplify_v_album(self, v: Optional[Dict], sampled: bool = False) -> Optional[Dict]:
        if not v:
            return None
        v_copy = v.copy()
        tracks = v_copy.get("tracks", [])
        
        # Remove heavy/redundant fields for LLM context, but KEEP credits for FINGERPRINT
        simplified_tracks = []
        for idx, t in enumerate(tracks):
            if not isinstance(t, dict): 
                simplified_tracks.append(t)
                continue
            st = {
                "v_idx": idx, # Unique index in this alignment input bundle
                "d": t.get("disc") or t.get("d"),
                "n": t.get("track_num") or t.get("n") or t.get("number"),
                "t": t.get("title") or t.get("t")
            }
            # Keep credits if they exist (FINGERPRINT source)
            if t.get("credits"):
                st["c"] = t["credits"]
            
            # Keep internal mapping hint for fingerprint
            if t.get("mbz_track_index") is not None:
                st["mbz_idx"] = t["mbz_track_index"]
                
            simplified_tracks.append(st)
        
        if sampled and len(simplified_tracks) > 20:
            v_copy["tracks"] = simplified_tracks[:15] + [{"note": f"... skipping {len(simplified_tracks)-20} tracks ..."}] + simplified_tracks[-5:]
        else:
            v_copy["tracks"] = simplified_tracks
            
        return v_copy

    def _resolve_album_identity(
        self,
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
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        return resolve_album_identity(
            app_id,
            s_steam,
            s_fingerprint,
            s_mbz_search,
            s_local,
            v_steam,
            v_local,
            v_fingerprint,
            resolved_num_ctx,
            progress_callback,
            full_logs,
            user_language=self.user_language,
            cache=self.llm_cache,
            call_llm=self._call_llm,
            normalize_result=self._normalize_identity_result,
        )

    def _extract_deterministic_prematches(
        self,
        local_tracks: List[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
        prematch_map: Dict[str, Any],
        global_res: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], set[int], List[Dict[str, Any]], List[Dict[str, Any]]]:
        return extract_deterministic_prematches(
            local_tracks,
            full_ref_steam,
            prematch_map,
            global_res,
            resolve_slot_key=self._resolve_slot_key_to_v_idx,
        )

    def _run_differential_segments(
        self,
        app_id: int,
        unmatched_local_tracks: List[Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
        unfilled_steam_slots: List[Dict[str, Any]],
        global_res: Dict[str, Any],
        s_mbz_search: Dict[str, Any],
        v_mbz_search: Optional[Dict[str, Any]],
        full_ref_fingerprint: List[Dict[str, Any]],
        full_ref_mbz_search: List[Dict[str, Any]],
        coherence_mappings: Optional[Dict[str, Any]],
        resolved_num_ctx: Optional[int],
        execution_profile: Optional[Any],
        progress_callback: Optional[ProgressCallback],
        prematch_map: Optional[Dict[str, Any]],
    ) -> Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]]:
        dynamic_chunk_size = max(1, self._adaptive_chunk_size(self.chunk_size_virtual, execution_profile))
        segments = (len(unmatched_local_tracks) + dynamic_chunk_size - 1) // dynamic_chunk_size
        return run_differential_segments(
            app_id,
            unmatched_local_tracks,
            local_tracks,
            unfilled_steam_slots,
            global_res,
            s_mbz_search,
            v_mbz_search,
            full_ref_fingerprint,
            full_ref_mbz_search,
            coherence_mappings,
            resolved_num_ctx,
            dynamic_chunk_size,
            progress_callback,
            prematch_map,
            should_parallelize=(
                self.llm_backend == "OLLAMA"
                and self.llm_request_parallelism_enabled
                and segments > 1
            ),
            resolve_worker_count=self._resolve_phase2_worker_count,
            execution_profile=execution_profile,
            process_segment=self._process_track_mapping_segment,
        )

    def align_slots(
        self,
        app_id: int,
        v_steam: Dict,
        v_fingerprint: Optional[Dict],
        v_mbz_search: Optional[Dict],
        v_local: Dict,
        execution_profile: Optional[Any] = None,
        num_ctx: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Consolidates the STEAM structure and auxiliary signal bundles into final slot alignment instructions.
        """
        full_logs = []
        
        s_steam = self._simplify_v_album(v_steam, sampled=True) or {}
        s_fingerprint = self._simplify_v_album(v_fingerprint, sampled=True) or {}
        s_mbz_search = self._simplify_v_album(v_mbz_search, sampled=True) or {}
        s_local = self._simplify_v_album(v_local, sampled=True) or {}
        
        resolved_num_ctx = self._resolve_execution_num_ctx(execution_profile, num_ctx)

        global_res, early_failure = self._resolve_album_identity(
            app_id,
            s_steam,
            s_fingerprint,
            s_mbz_search,
            s_local,
            v_steam,
            v_local,
            v_fingerprint,
            resolved_num_ctx,
            progress_callback,
            full_logs,
        )
        if early_failure is not None or global_res is None:
            return None, early_failure or {}

        local_tracks = v_local.get("tracks", [])
        coherence_mappings = None

        full_ref_steam = (self._simplify_v_album(v_steam, sampled=False) or {}).get("tracks", [])
        full_ref_fingerprint = (self._simplify_v_album(v_fingerprint, sampled=False) or {}).get("tracks", []) if v_fingerprint else []
        full_ref_mbz_search = (self._simplify_v_album(v_mbz_search, sampled=False) or {}).get("tracks", []) if v_mbz_search else []

        prematch_map = resolve_prematch_signals(
            local_tracks=local_tracks,
            full_ref_steam=full_ref_steam,
            full_ref_fingerprint=full_ref_fingerprint,
            full_ref_mbz_search=full_ref_mbz_search,
            v_mbz_search=v_mbz_search,
        )

        (
            deterministic_instructions,
            resolved_v_indices,
            unmatched_local_tracks,
            unfilled_steam_slots,
        ) = self._extract_deterministic_prematches(local_tracks, full_ref_steam, prematch_map, global_res)

        logger.info(
            f"[{app_id}] 差分推論アライメント: 確定済みスロット={len(resolved_v_indices)}/{len(full_ref_steam)}, "
            f"未確定ローカルトラック={len(unmatched_local_tracks)}/{len(local_tracks)}, "
            f"空きSteamスロット={len(unfilled_steam_slots)}"
        )

        final_instructions = dict(deterministic_instructions)
        segment_results: Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]] = {}

        if not unmatched_local_tracks or not unfilled_steam_slots:
            logger.info(f"[{app_id}] すべてのトラックが決定論的プレマッチで確定しました。LLM Phase 2 をバイパスし、確信度を100%に設定します。")
            global_res["identity_confidence"] = 100
            global_res["album_confidence"] = 100
            global_res["mapping_confidence"] = 100
            global_res["integrity_quality"] = 100
            global_res["data_quality"] = 100
            global_res["strategy"] = "STEAM_BASED"
            global_res["semantic_label"] = "Archive"
            global_res["archive_vs_review_ratio"] = {"archive": 100, "review": 0}
            global_res["confidence_reason"] = f"SYSTEM: すべてのトラックが決定論的プレマッチで確定 ({len(deterministic_instructions)}/{len(full_ref_steam)}スロット)"
            segment_results[0] = (deterministic_instructions, [])
        else:
            segment_results = self._run_differential_segments(
                app_id,
                unmatched_local_tracks,
                local_tracks,
                unfilled_steam_slots,
                global_res,
                s_mbz_search,
                v_mbz_search,
                full_ref_fingerprint,
                full_ref_mbz_search,
                coherence_mappings,
                resolved_num_ctx,
                execution_profile,
                progress_callback,
                prematch_map,
            )
            for start_idx in sorted(segment_results):
                instructions, segment_logs = segment_results[start_idx]
                final_instructions.update(instructions)
                full_logs.extend(segment_logs)

        final_instructions, contradictory_slot_assignments = self._reject_contradictory_slot_assignments(
            final_instructions,
            local_tracks,
            full_ref_steam,
        )
        alignment_res = self._build_slot_view_from_final_instructions(final_instructions, local_tracks)
        alignment_res["contradictory_slot_assignments"] = contradictory_slot_assignments
        alignment_res["diagnostics"] = self._build_alignment_diagnostics(
            final_instructions,
            local_tracks,
            segment_results,
        )
        alignment_res["diagnostics"]["contradictory_slot_assignments"] = contradictory_slot_assignments
        if alignment_res.get("slots"):
            slot_confidences = [slot.get("confidence", 0) for slot in alignment_res["slots"].values() if isinstance(slot, dict)]
            if slot_confidences:
                global_res["mapping_confidence"] = int(min(slot_confidences) * 100) if min(slot_confidences) <= 1 else int(min(slot_confidences))

        return final_instructions, {"phase1_res": global_res, "alignment_res": alignment_res, "logs": full_logs}