import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple, Callable

from ..config import DEFAULT_METADATA_SOURCE_PRIORITY
from .client import LLMClient
from .prompts import build_mapping_prompt, build_identity_prompt, build_steam_tracklist_extraction_prompt
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
                 metadata_source_priority: str = DEFAULT_METADATA_SOURCE_PRIORITY):
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
        
        self.client = LLMClient(
            api_key=api_key, base_url=base_url, model=model, rpm=rpm, tpm=tpm, rpd=rpd,
            llm_backend=llm_backend, draft_model=draft_model, llm_cloud_max_tokens=llm_cloud_max_tokens,
            ollama_num_ctx=ollama_num_ctx, ollama_num_predict=ollama_num_predict,
            llm_vram_scheduling_enabled=llm_vram_scheduling_enabled,
            request_timeout=request_timeout, chunk_output_tokens_per_track=chunk_output_tokens_per_track
        )

    def set_vram_manager(self, vram_manager: Any):
        self.client.set_vram_manager(vram_manager)

    def check_availability(self) -> bool:
        return self.client.check_availability()

    def extract_steam_tracklist(
        self,
        app_id: int,
        description_text: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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
    ) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        normalized_track_res = self._normalize_track_mapping_result(track_res, full_ref_steam)
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
            if data.get("action") == "use_fingerprint" and mv_idx is not None:
                if mv_idx < len(ref_fingerprint):
                    ref_track = ref_fingerprint[mv_idx]
                    data["mbz_track_index"] = ref_track.get("mbz_idx")
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))
            elif data.get("action") == "use_mbz_search" and mv_idx is not None and v_mbz_search:
                if mv_idx < len(full_ref_mbz_search):
                    ref_track = full_ref_mbz_search[mv_idx]
                    data["mbz_track_index"] = ref_track.get("mbz_idx")
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))
            elif data.get("action") == "use_steam" and mv_idx is not None and full_ref_steam:
                if mv_idx < len(full_ref_steam):
                    ref_track = full_ref_steam[mv_idx]
                    if data.get("override_track") is None and ref_track.get("n") is not None:
                        data["override_track"] = str(ref_track.get("n"))

            tags = global_res.get("global_tags", {})
            if not isinstance(tags, dict): tags = {}
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

        normalized_slot_key = str(slot_key).strip()
        direct_matches = [track.get("v_idx") for track in full_ref_steam if str(track.get("n")) == normalized_slot_key]
        direct_matches = [match for match in direct_matches if match is not None]
        if len(direct_matches) == 1:
            return int(direct_matches[0])

        try:
            fallback_index = int(normalized_slot_key) - 1
        except (TypeError, ValueError):
            return None

        if 0 <= fallback_index < len(full_ref_steam):
            return int(full_ref_steam[fallback_index].get("v_idx", fallback_index))
        return None

    @classmethod
    def _normalize_track_mapping_result(
        cls,
        track_res: Dict[str, Any],
        full_ref_steam: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if not isinstance(track_res, dict):
            return {}
        if "track_instructions" in track_res:
            return track_res
        if not isinstance(track_res.get("slots"), dict):
            return track_res

        track_instructions: Dict[str, Dict[str, Any]] = {}
        for slot_key, slot_data in track_res.get("slots", {}).items():
            if not isinstance(slot_data, dict):
                continue
            matched_v_idx = cls._resolve_slot_key_to_v_idx(str(slot_key), full_ref_steam)
            if matched_v_idx is None:
                continue
            for file_idx in slot_data.get("files", []):
                file_key = str(file_idx)
                track_instructions[file_key] = {
                    "action": "use_steam",
                    "matched_v_idx": matched_v_idx,
                    "override_title": None,
                    "override_track": str(slot_key) if str(slot_key).isdigit() else None,
                    "override_disc": None,
                    "composer": None,
                    "lyricist": None,
                    "arranger": None,
                    "reason": slot_data.get("reason"),
                }

        normalized = dict(track_res)
        normalized["track_instructions"] = track_instructions
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
    ) -> Tuple[int, Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        segment_logs: List[Dict[str, Any]] = []
        segment_instructions: Dict[str, Dict[str, Any]] = {}
        current_base_chunk_size = max(1, base_chunk_size)
        offset = 0

        while offset < len(segment_tracks):
            current_chunk_size = min(current_base_chunk_size, len(segment_tracks) - offset)
            chunk_start = start_idx + offset
            chunk = segment_tracks[offset:offset + current_chunk_size]
            s_chunk = []
            for idx, track in enumerate(chunk):
                s_chunk.append({
                    "file_ids": track.get("file_ids", []),
                    "t": track.get("title"),
                    "d": track.get("disc"),
                    "dur": (track.get("duration_ms", 0) // 1000) if track.get("duration_ms") else None,
                })

            ref_steam, ref_fingerprint = self._resolve_mapping_references(
                chunk_start,
                full_ref_steam,
                full_ref_fingerprint,
                coherence_mappings,
            )
            mapping_prompt = build_mapping_prompt(
                global_res,
                s_mbz_search,
                v_mbz_search,
                ref_steam,
                ref_fingerprint,
                s_chunk,
                chunk_start,
                self.user_language,
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
        if not v: return None
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
                "d": t.get("disc"),
                "n": t.get("track_num"),
                "t": t.get("title")
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
        
        # Simplify albums to save context
        s_steam = self._simplify_v_album(v_steam, sampled=True)
        s_fingerprint = self._simplify_v_album(v_fingerprint, sampled=True)
        s_mbz_search = self._simplify_v_album(v_mbz_search, sampled=True)
        s_local = self._simplify_v_album(v_local, sampled=True)
        
        resolved_num_ctx = num_ctx
        if execution_profile:
            resolved_num_ctx = execution_profile.num_ctx_cap

        # Identity and album-level confidence
        identity_prompt = build_identity_prompt(s_steam, s_fingerprint, s_mbz_search, s_local, self.user_language)
        local_tracks = v_local.get("tracks", [])
        global_res, global_log = self._call_llm(
            app_id,
            identity_prompt,
            num_ctx=resolved_num_ctx,
            request_kind="identity",
            request_units=len(local_tracks),
            progress_callback=progress_callback,
        )
        full_logs.append(global_log)

        if not global_res:
             return None, {"phase1_res": None, "phase1_log": global_log}

        global_res = self._normalize_identity_result(global_res)

        # --- SYSTEM-LEVEL HEURISTICS (PRE-NORMALIZE) ---
        # 1. STEAM-TRUST Path: If STEAM count matches LOCAL count exactly
        # and LLM was conservative (conf < 95), trust the structural match.
        steam_count = len(v_steam.get("tracks", []))
        local_count = len(v_local.get("tracks", []))
        current_conf = global_res.get("identity_confidence", 0)
        
        if steam_count > 0 and steam_count == local_count:
            if current_conf < 100 and (not v_fingerprint or current_conf >= 80):
                logger.info(f"[{app_id}] Applying STEAM-TRUST: Structural match detected ({steam_count} tracks). Boosting confidence to 100%.")
                global_res["identity_confidence"] = 100
                global_res["archive_vs_review_ratio"] = {"archive": 100, "review": 0}
                global_res["strategy"] = "STEAM_BASED"
                global_res["confidence_reason"] = f"SYSTEM: STEAM-TRUSTにより確信度を100%に引き上げました ({steam_count}トラックとの構造的一致)"

        # Normalize confidence if in 0-1 range
        conf = int(global_res.get("identity_confidence", 0))
        if 0 < conf <= 1:
            conf = int(conf * 100)
            global_res["identity_confidence"] = conf
        
        # Ensure ratio is valid
        ratio = global_res.get("archive_vs_review_ratio", {})
        if not isinstance(ratio, dict) or not ratio:
            global_res["archive_vs_review_ratio"] = {"archive": 0, "review": 100}
        if conf < 85:
            concerns = global_res.setdefault("concerns", [])
            concerns.append("Low album confidence before slot alignment")

        # Slot alignment with chunking
        final_instructions = {}

        # The specification uses direct STEAM-slot alignment; legacy coherence
        # routing is retained only as an unused compatibility method.
        coherence_mappings = None

        # Prepare full simplified reference tracks for slot alignment (not sampled)
        full_ref_steam = self._simplify_v_album(v_steam, sampled=False).get("tracks", [])
        full_ref_fingerprint = self._simplify_v_album(v_fingerprint, sampled=False).get("tracks", []) if v_fingerprint else []
        full_ref_mbz_search = self._simplify_v_album(v_mbz_search, sampled=False).get("tracks", []) if v_mbz_search else []

        dynamic_chunk_size = max(1, self._adaptive_chunk_size(self.chunk_size_virtual))
        segments = [
            (start_idx, local_tracks[start_idx:start_idx + dynamic_chunk_size])
            for start_idx in range(0, len(local_tracks), dynamic_chunk_size)
        ]

        should_parallelize = self.llm_backend == "OLLAMA" and self.llm_request_parallelism_enabled and len(segments) > 1
        segment_results: Dict[int, Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]] = {}

        if should_parallelize:
            worker_count = min(self.llm_request_parallelism_max_workers, len(segments))
            if execution_profile:
                worker_count = min(execution_profile.phase2_parallel_workers, len(segments))
            worker_count = max(1, worker_count)
            logger.info(f"[{app_id}] Slot alignment chunks を並列実行します。segments={len(segments)} workers={worker_count}")
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
                        full_ref_steam,
                        full_ref_fingerprint,
                        full_ref_mbz_search,
                        coherence_mappings,
                        resolved_num_ctx,
                        dynamic_chunk_size,
                        progress_callback,
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
                    full_ref_steam,
                    full_ref_fingerprint,
                    full_ref_mbz_search,
                    coherence_mappings,
                    resolved_num_ctx,
                    dynamic_chunk_size,
                    progress_callback,
                )
                segment_results[start_idx] = (instructions, segment_logs)

        for start_idx in sorted(segment_results):
            instructions, segment_logs = segment_results[start_idx]
            final_instructions.update(instructions)
            full_logs.extend(segment_logs)

        alignment_res = self._build_slot_view_from_final_instructions(final_instructions, local_tracks)
        if alignment_res.get("slots"):
            slot_confidences = [slot.get("confidence", 0) for slot in alignment_res["slots"].values() if isinstance(slot, dict)]
            if slot_confidences:
                global_res["mapping_confidence"] = int(min(slot_confidences) * 100) if min(slot_confidences) <= 1 else int(min(slot_confidences))

        return final_instructions, {"phase1_res": global_res, "alignment_res": alignment_res, "logs": full_logs}