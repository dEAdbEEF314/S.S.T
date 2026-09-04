import logging
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple, Callable

from ..config import DEFAULT_METADATA_SOURCE_PRIORITY
from .client import LLMClient
from .prompts import build_mapping_prompt, build_identity_prompt, build_steam_tracklist_extraction_prompt
from .prematch import resolve_prematch_signals
from ..steam_tracklist import validate_llm_tracklist

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
                 llm_cache_enabled: bool = True,
                 llm_cache_ttl_seconds: int = 86400,
                 llm_cache_path: str = "data/llm_cache.json"):
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
            llm_vram_scheduling_enabled=llm_vram_scheduling_enabled,
            request_timeout=request_timeout, chunk_output_tokens_per_track=chunk_output_tokens_per_track
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
        cache_key_input = description_text or ""
        cached = self.llm_cache.get(cache_key_input, "steam_tracklist_extraction", self.user_language)
        if cached is not None:
            log_entry: Dict[str, Any] = {
                "request_kind": "steam_tracklist_extraction",
                "cache": self.llm_cache.audit_hit(cache_key_input, "steam_tracklist_extraction", self.user_language),
                "response": cached,
            }
            tracks, errors = validate_llm_tracklist(cached)
            log_entry["validation_errors"] = errors
            if tracks:
                log_entry["tracklist_source"] = "STEAM_TEXT_TRACKLIST_LLM"
            return tracks, log_entry

        prompt = build_steam_tracklist_extraction_prompt(description_text, self.user_language)
        response, log_entry = self._call_llm(
            app_id,
            prompt,
            request_kind="steam_tracklist_extraction",
            request_units=1,
            progress_callback=progress_callback,
        )
        tracks, errors = validate_llm_tracklist(response)
        log_entry["validation_errors"] = errors
        if not tracks:
            return [], log_entry
        log_entry["tracklist_source"] = "STEAM_TEXT_TRACKLIST_LLM"
        log_entry["cache"] = self.llm_cache.put(cache_key_input, "steam_tracklist_extraction", self.user_language, response)
        return tracks, log_entry

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
        ref_steam = full_ref_steam
        ref_fingerprint = full_ref_fingerprint

        if coherence_mappings:
            c_key = f"Segment_{(start_idx // 30) + 1}"
            cmap = coherence_mappings.get(c_key, {})
            if cmap:
                s_start = cmap.get("steam_start_v_idx")
                s_end = cmap.get("steam_end_v_idx")
                if s_start is not None and s_end is not None:
                    ref_steam = [t for t in full_ref_steam if s_start <= t.get("v_idx", 0) <= s_end]
                else:
                    ref_steam = []

                f_start = cmap.get("fingerprint_start_v_idx")
                f_end = cmap.get("fingerprint_end_v_idx")
                if f_start is not None and f_end is not None:
                    ref_fingerprint = [t for t in full_ref_fingerprint if f_start <= t.get("v_idx", 0) <= f_end]
                else:
                    ref_fingerprint = []

        return ref_steam, ref_fingerprint

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
        merged: Dict[str, Dict[str, Any]] = {}
        normalized_track_res = self._normalize_track_mapping_result(track_res, full_ref_steam, prematch_map=prematch_map)
        if not normalized_track_res or "track_instructions" not in normalized_track_res:
            return merged

        assigned_file_ids: set[str] = set()
        known_file_ids = {
            str(file_id)
            for track in local_tracks
            for file_id in track.get("file_ids", [])
        }
        for c_idx_str, data in normalized_track_res["track_instructions"].items():
            file_id = str(c_idx_str)
            if known_file_ids:
                if file_id not in known_file_ids or file_id in assigned_file_ids:
                    continue
                matching_track = next(
                    (track for track in local_tracks if file_id in {str(value) for value in track.get("file_ids", [])}),
                    None,
                )
                assigned_file_ids.add(file_id)
            else:
                try:
                    c_idx = int(c_idx_str)
                    if c_idx < 0 or c_idx >= len(local_tracks):
                        continue
                    matching_track = local_tracks[c_idx]
                except ValueError:
                    matching_track = next((t for t in chunk if t["title"] == c_idx_str), None)

            if not matching_track:
                continue

            tid = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"

            mv_idx = data.get("matched_v_idx")
            # 互換性フォールバック（旧形式のtrack_instructionsが渡された場合）
            if data.get("mbz_track_index") is None:
                if data.get("action") == "use_fingerprint" and mv_idx is not None and mv_idx < len(ref_fingerprint):
                    ref_track = ref_fingerprint[mv_idx]
                    data["mbz_track_index"] = ref_track.get("mbz_idx")
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))
                elif data.get("action") == "use_mbz_search" and mv_idx is not None and v_mbz_search and mv_idx < len(full_ref_mbz_search):
                    ref_track = full_ref_mbz_search[mv_idx]
                    data["mbz_track_index"] = ref_track.get("mbz_idx")
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))
                elif mv_idx is not None and full_ref_steam and mv_idx < len(full_ref_steam):
                    ref_track = full_ref_steam[mv_idx]
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))

            tags = global_res.get("global_tags", {})
            if not isinstance(tags, dict):
                tags = {}
            data.update({
                "TPE2": tags.get("canonical_album_artist") or global_res.get("canonical_album_artist"),
                "TCON": tags.get("canonical_genre") or global_res.get("canonical_genre"),
                "TDRC": tags.get("canonical_year") or global_res.get("canonical_year"),
                "TPUB": tags.get("canonical_label") or global_res.get("canonical_label"),
                "TEXT": data.get("lyricist"),
                "TCOM": data.get("composer"),
                "TPE4": data.get("arranger"),
                "identity_confidence": global_res["identity_confidence"],
                "integrity_quality": global_res.get("integrity_quality", 0),
                "archive_vs_review_ratio": global_res.get("archive_vs_review_ratio", {"archive": 0, "review": 100}),
                "confidence_score": global_res.get("identity_confidence", 0),
                "strategy": global_res.get("strategy", "UNKNOWN"),
                "semantic_label": global_res.get("semantic_label", "Review")
            })
            merged[tid] = data

        return merged

    @staticmethod
    def _resolve_slot_key_to_v_idx(slot_key: str, full_ref_steam: Optional[List[Dict[str, Any]]]) -> Optional[int]:
        if not full_ref_steam:
            return None

        def _norm_key(k: Any) -> str:
            s = str(k).strip()
            return s.lstrip('0') or '0'

        normalized_slot_key = str(slot_key).strip()
        norm_key = _norm_key(normalized_slot_key)
        direct_matches = [
            track.get("v_idx") for track in full_ref_steam
            if _norm_key(track.get("n", "")) == norm_key
        ]
        direct_matches = [match for match in direct_matches if match is not None]
        if len(direct_matches) == 1:
            return int(direct_matches[0])

        # プレフィックス除去 / 数字抽出 (例: "STEAM_SLOT_0" -> "0", "SLOT_1" -> "1", "Track 2" -> "2")
        extracted_digits = None
        digits_match = re.search(r'\d+', normalized_slot_key)
        if digits_match:
            extracted_digits = digits_match.group(0)
            norm_extracted = _norm_key(extracted_digits)
            direct_matches_ext = [
                track.get("v_idx") for track in full_ref_steam
                if _norm_key(track.get("n", "")) == norm_extracted
            ]
            direct_matches_ext = [m for m in direct_matches_ext if m is not None]
            if len(direct_matches_ext) == 1:
                return int(direct_matches_ext[0])

        # 数値インデックスとしてのフォールバック解決
        num_str = extracted_digits if extracted_digits is not None else normalized_slot_key
        try:
            val = int(num_str)
        except (TypeError, ValueError):
            return None

        # 0-indexed キー（"0"〜）: 0 は先頭スロット（インデックス 0）
        if val == 0 and len(full_ref_steam) > 0:
            return int(full_ref_steam[0].get("v_idx", 0))

        # 1-indexed キー（"1"〜）: fallback_index = val - 1
        fallback_index = val - 1
        if 0 <= fallback_index < len(full_ref_steam):
            return int(full_ref_steam[fallback_index].get("v_idx", fallback_index))

        # 0-indexed で直接範囲内にある場合
        if 0 <= val < len(full_ref_steam):
            return int(full_ref_steam[val].get("v_idx", val))

        return None

    @classmethod
    def _normalize_track_mapping_result(
        cls,
        track_res: Dict[str, Any],
        full_ref_steam: Optional[List[Dict[str, Any]]],
        prematch_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(track_res, dict):
            return {}
        if "track_instructions" in track_res:
            return track_res
        if not isinstance(track_res.get("slots"), dict):
            return track_res

        track_instructions: Dict[str, Dict[str, Any]] = {}
        rejected_slot_keys: List[str] = []
        for slot_key, slot_data in track_res.get("slots", {}).items():
            if not isinstance(slot_data, dict):
                continue
            matched_v_idx = cls._resolve_slot_key_to_v_idx(str(slot_key), full_ref_steam)
            if matched_v_idx is None:
                rejected_slot_keys.append(str(slot_key))
                continue
            for file_idx in slot_data.get("files", []):
                file_key = str(file_idx)
                pm = prematch_map.get(file_key) if prematch_map else None
                track_instructions[file_key] = {
                    "matched_v_idx": matched_v_idx,
                    "mbz_track_index": pm.mbz_track_index if pm else None,
                    "override_title": None,
                    "override_track": str(slot_key) if str(slot_key).isdigit() else (pm.override_track if pm else None),
                    "override_disc": None,
                    "composer": None,
                    "lyricist": None,
                    "arranger": None,
                    "reason": slot_data.get("reason"),
                }

        normalized = dict(track_res)
        normalized["track_instructions"] = track_instructions
        normalized["rejected_slot_keys"] = rejected_slot_keys
        return normalized

    @staticmethod
    def _normalize_identity_result(global_res: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(global_res, dict):
            return {}

        normalized = dict(global_res)
        album_confidence = int(normalized.get("album_confidence", normalized.get("identity_confidence", 0) or 0))
        data_quality = int(normalized.get("data_quality", normalized.get("integrity_quality", 0) or 0))
        normalized["identity_confidence"] = int(normalized.get("identity_confidence", album_confidence) or album_confidence)
        normalized["integrity_quality"] = int(normalized.get("integrity_quality", data_quality) or data_quality)
        normalized["album_confidence"] = album_confidence
        normalized["data_quality"] = data_quality
        normalized.setdefault("mapping_confidence", 0)
        normalized.setdefault("concerns", [])
        return normalized

    @staticmethod
    def _build_slot_view(track_res: Dict[str, Any], local_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(track_res, dict):
            return {"slots": {}, "unassigned_files": [], "unassigned_reason": None}

        if isinstance(track_res.get("slots"), dict):
            known_file_ids = {
                str(file_id)
                for track in local_tracks
                for file_id in track.get("file_ids", [])
            }
            seen_file_ids: set[str] = set()
            rejected_file_ids: List[str] = []
            validated_slots: Dict[str, Dict[str, Any]] = {}
            for slot_key, slot_data in track_res.get("slots", {}).items():
                if not isinstance(slot_data, dict):
                    continue
                valid_files = []
                for file_id in slot_data.get("files", []):
                    normalized_file_id = str(file_id)
                    if known_file_ids and (
                        normalized_file_id not in known_file_ids
                        or normalized_file_id in seen_file_ids
                    ):
                        rejected_file_ids.append(normalized_file_id)
                        continue
                    valid_files.append(normalized_file_id)
                    seen_file_ids.add(normalized_file_id)
                validated_slots[str(slot_key)] = {**slot_data, "files": valid_files}
            local_file_ids = [
                str(file_id)
                for track in local_tracks
                for file_id in track.get("file_ids", [])
            ]
            return {
                "slots": validated_slots,
                "unassigned_files": [file_id for file_id in local_file_ids if file_id not in seen_file_ids],
                "unassigned_reason": track_res.get("unassigned_reason"),
                "rejected_file_ids": sorted(set(rejected_file_ids)),
            }

        slots: Dict[str, Dict[str, Any]] = {}
        assigned_files: set[str] = set()
        for file_id, data in (track_res.get("track_instructions") or {}).items():
            if not isinstance(data, dict):
                continue
            matched_v_idx = data.get("matched_v_idx")
            if matched_v_idx is None:
                continue
            try:
                slot_key = str(int(matched_v_idx) + 1)
            except (TypeError, ValueError):
                continue
            slots.setdefault(slot_key, {"files": [], "confidence": 0.9, "reason": data.get("reason")})
            slots[slot_key]["files"].append(str(file_id))
            assigned_files.add(str(file_id))

        local_file_ids = [file_id for track in local_tracks for file_id in track.get("file_ids", [])]
        unassigned_files = [str(file_id) for file_id in local_file_ids if str(file_id) not in assigned_files]
        return {
            "slots": slots,
            "unassigned_files": unassigned_files,
            "unassigned_reason": "No slot assignment returned" if unassigned_files else None,
        }

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
    def _build_slot_view_from_final_instructions(
        final_instructions: Dict[str, Dict[str, Any]],
        local_tracks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        track_instruction_map: Dict[str, Dict[str, Any]] = {}
        local_file_ids_by_tid: Dict[str, List[str]] = {}

        for track in local_tracks:
            local_key = track.get("local_key")
            if not local_key:
                continue
            tid = f"{local_key[0]}_{local_key[1]}"
            local_file_ids_by_tid[tid] = [str(file_id) for file_id in track.get("file_ids", [])]

        for tid, data in final_instructions.items():
            file_ids = local_file_ids_by_tid.get(tid)
            if not file_ids:
                continue
            for file_id in file_ids:
                track_instruction_map[file_id] = {
                    "matched_v_idx": data.get("matched_v_idx"),
                    "reason": data.get("reason"),
                }

        return LLMOrganizer._build_slot_view({"track_instructions": track_instruction_map}, local_tracks)

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

    def _adaptive_chunk_size(self, base_chunk_size: int) -> int:
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
            # Ollamaの場合: VRAMはセマフォで管理されるため、出力限界までOne-shot化
            return by_output
        else:
            # 外部APIの場合: 毎分トークン(TPM)の枯渇による429エラーを防止する
            # 1曲あたりの総消費見積もり(入力150+出力180=330)、オーバーヘッド約1000
            tpm_limit = self.llm_limit_tpm
            safe_tpm_budget = int(tpm_limit * 0.8) # 80%の安全マージン
            by_tpm = max(1, (safe_tpm_budget - 1000) // 330)
            
            # 出力破綻限界とTPM枯渇限界の、より厳しい方（小さい方）を最終的な限界チャンクとして採用
            dynamic_limit = min(by_output, by_tpm)
            return dynamic_limit

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
        identity_prompt = build_identity_prompt(s_steam, s_fingerprint, s_mbz_search, s_local, self.user_language)
        local_tracks = v_local.get("tracks", [])
        cache_key_input = json.dumps(
            {"steam": s_steam, "fingerprint": s_fingerprint, "mbz_search": s_mbz_search, "local": s_local},
            sort_keys=True, ensure_ascii=False,
        )
        cached_identity = self.llm_cache.get(cache_key_input, "identity", self.user_language)
        if cached_identity is not None:
            global_log: Dict[str, Any] = {
                "request_kind": "identity",
                "cache": self.llm_cache.audit_hit(cache_key_input, "identity", self.user_language),
                "response": cached_identity,
            }
            full_logs.append(global_log)
            global_res = cached_identity
        else:
            global_res, global_log = self._call_llm(
                app_id,
                identity_prompt,
                num_ctx=resolved_num_ctx,
                request_kind="identity",
                request_units=len(local_tracks),
                progress_callback=progress_callback,
            )
            full_logs.append(global_log)
            if global_res:
                global_log["cache"] = self.llm_cache.put(cache_key_input, "identity", self.user_language, global_res)

        steam_count = len(v_steam.get("tracks", []))
        local_count = len(v_local.get("tracks", []))

        if not global_res:
            if steam_count > 0 and steam_count == local_count:
                logger.warning(f"[{app_id}] Identity LLM call failed/truncated. Activating STEAM-TRUST fallback ({steam_count} tracks).")
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

        global_res = self._normalize_identity_result(global_res)

        unique_local_slots = len({
            (
                str(track.get("disc", 1)),
                str(track.get("track_num") or track.get("filename_track") or track.get("title") or track.get("norm_stem") or "")
            )
            for track in local_tracks
        }) if local_tracks else 0
        structural_match = (steam_count > 0 and (steam_count == local_count or steam_count == unique_local_slots))
        current_conf = global_res.get("identity_confidence", 0)

        if structural_match:
            if current_conf < 100 and (not v_fingerprint or current_conf >= 80):
                logger.info(f"[{app_id}] Applying STEAM-TRUST: Structural match detected (Steam: {steam_count}, Local: {local_count}, Unique: {unique_local_slots}). Boosting confidence to 100%.")
                global_res["identity_confidence"] = 100
                global_res["album_confidence"] = 100
                global_res["mapping_confidence"] = 100
                global_res["integrity_quality"] = 100
                global_res["data_quality"] = 100
                global_res["archive_vs_review_ratio"] = {"archive": 100, "review": 0}
                global_res["strategy"] = "STEAM_BASED"
                global_res["confidence_reason"] = f"SYSTEM: STEAM-TRUSTにより確信度を100%に引き上げました ({steam_count}トラックとの構造的一致)"

        conf = int(global_res.get("identity_confidence", 0))
        if 0 < conf <= 1:
            conf = int(conf * 100)
            global_res["identity_confidence"] = conf

        ratio = global_res.get("archive_vs_review_ratio", {})
        if not isinstance(ratio, dict) or not ratio:
            global_res["archive_vs_review_ratio"] = {"archive": 0, "review": 100}
        if conf < 85:
            concerns = global_res.setdefault("concerns", [])
            concerns.append("Low album confidence before slot alignment")

        return global_res, None

    def _extract_deterministic_prematches(
        self,
        local_tracks: List[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
        prematch_map: Dict[str, Any],
        global_res: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], set[int], List[Dict[str, Any]], List[Dict[str, Any]]]:
        deterministic_instructions: Dict[str, Dict[str, Any]] = {}
        resolved_v_indices: set[int] = set()
        resolved_local_indices: set[int] = set()

        fid_to_track_idx = {}
        for idx, track in enumerate(local_tracks):
            for fid in track.get("file_ids", []):
                fid_to_track_idx[str(fid)] = idx

        for fid_str, pm in prematch_map.items():
            if not pm or not pm.is_deterministic:
                continue
            matched_v_idx = pm.target_v_idx
            if matched_v_idx is None and pm.deterministic_steam_slot is not None:
                matched_v_idx = self._resolve_slot_key_to_v_idx(str(pm.deterministic_steam_slot), full_ref_steam)

            if matched_v_idx is not None and 0 <= matched_v_idx < len(full_ref_steam):
                resolved_v_indices.add(matched_v_idx)
                track_idx = fid_to_track_idx.get(fid_str)
                if track_idx is not None:
                    resolved_local_indices.add(track_idx)
                    matching_track = local_tracks[track_idx]
                    tid = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"
                    tags = global_res.get("global_tags", {}) if isinstance(global_res.get("global_tags"), dict) else {}
                    steam_slot = full_ref_steam[matched_v_idx]
                    slot_n = steam_slot.get("n") or pm.override_track or (matched_v_idx + 1)
                    deterministic_instructions[tid] = {
                        "matched_v_idx": matched_v_idx,
                        "mbz_track_index": pm.mbz_track_index,
                        "override_title": None,
                        "override_track": str(slot_n),
                        "override_disc": str(steam_slot.get("d") or steam_slot.get("disc") or 1),
                        "reason": f"SYSTEM: Deterministic match ({pm.evidence[0] if pm.evidence else 'exact'})",
                        "TPE2": tags.get("canonical_album_artist"),
                        "TCON": tags.get("canonical_genre"),
                        "TDRC": tags.get("canonical_year"),
                        "TPUB": tags.get("canonical_label"),
                    }

        unmatched_local_tracks = [
            track for idx, track in enumerate(local_tracks)
            if idx not in resolved_local_indices
        ]
        unfilled_steam_slots = [
            slot for slot in full_ref_steam
            if slot.get("v_idx") not in resolved_v_indices
        ]
        return deterministic_instructions, resolved_v_indices, unmatched_local_tracks, unfilled_steam_slots

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
        segment_results: Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]] = {}
        dynamic_chunk_size = max(1, self._adaptive_chunk_size(self.chunk_size_virtual))
        segments = [
            (start_idx, unmatched_local_tracks[start_idx:start_idx + dynamic_chunk_size])
            for start_idx in range(0, len(unmatched_local_tracks), dynamic_chunk_size)
        ]
        should_parallelize = self.llm_backend == "OLLAMA" and self.llm_request_parallelism_enabled and len(segments) > 1

        if should_parallelize:
            worker_count = self._resolve_phase2_worker_count(execution_profile, len(segments))
            logger.info(f"[{app_id}] Phase 2 differential mapping chunk を並列実行します。segments={len(segments)} workers={worker_count}")
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        self._process_track_mapping_segment,
                        app_id,
                        start_idx,
                        segment_tracks,
                        local_tracks,
                        global_res,
                        s_mbz_search,
                        v_mbz_search,
                        unfilled_steam_slots,
                        full_ref_fingerprint,
                        full_ref_mbz_search,
                        coherence_mappings,
                        resolved_num_ctx,
                        dynamic_chunk_size,
                        progress_callback,
                        prematch_map=prematch_map,
                    ): start_idx
                    for start_idx, segment_tracks in segments
                }
                for future in as_completed(future_map):
                    start_idx, instructions, segment_logs = future.result()
                    segment_results[start_idx] = (instructions, segment_logs)
        else:
            for start_idx, segment_tracks in segments:
                start_idx, instructions, segment_logs = self._process_track_mapping_segment(
                    app_id,
                    start_idx,
                    segment_tracks,
                    local_tracks,
                    global_res,
                    s_mbz_search,
                    v_mbz_search,
                    unfilled_steam_slots,
                    full_ref_fingerprint,
                    full_ref_mbz_search,
                    coherence_mappings,
                    resolved_num_ctx,
                    dynamic_chunk_size,
                    progress_callback,
                    prematch_map=prematch_map,
                )
                segment_results[start_idx] = (instructions, segment_logs)
        return segment_results

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

        alignment_res = self._build_slot_view_from_final_instructions(final_instructions, local_tracks)
        alignment_res["diagnostics"] = self._build_alignment_diagnostics(
            final_instructions,
            local_tracks,
            segment_results,
        )
        if alignment_res.get("slots"):
            slot_confidences = [slot.get("confidence", 0) for slot in alignment_res["slots"].values() if isinstance(slot, dict)]
            if slot_confidences:
                global_res["mapping_confidence"] = int(min(slot_confidences) * 100) if min(slot_confidences) <= 1 else int(min(slot_confidences))

        return final_instructions, {"phase1_res": global_res, "alignment_res": alignment_res, "logs": full_logs}