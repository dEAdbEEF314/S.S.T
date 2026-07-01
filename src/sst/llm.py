import re
import json
import logging
import requests
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .config import (
    DEFAULT_METADATA_SOURCE_PRIORITY,
    DEFAULT_PRIORITY_APIC,
    DEFAULT_PRIORITY_TIT2,
    DEFAULT_PRIORITY_TPE1,
    DEFAULT_PRIORITY_TPOS,
    DEFAULT_PRIORITY_TRCK,
    DEFAULT_PRIORITY_TPUB,
    DEFAULT_PRIORITY_TYER,
)
from .rate_limit import DistributedRateLimiter

logger = logging.getLogger("sst.llm")

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = "ja",
                 llm_backend: str = "GEMINI",
                 draft_model: Optional[str] = None,
                 llm_cloud_max_tokens: int = 8192,
                 ollama_num_ctx: int = 32768,
                 ollama_num_predict: int = 4096,
                 coherence_threshold: int = 75,
                 chunk_size_virtual: int = 20,
                 chunk_size_metadata_ollama: int = 10,
                 chunk_size_metadata_cloud: int = 30,
                 chunk_adaptive: bool = True,
                 chunk_output_tokens_per_track: int = 180,
                 chunk_output_safety_ratio: float = 0.75,
                 metadata_source_priority: str = DEFAULT_METADATA_SOURCE_PRIORITY,
                 priority_tit2: str = DEFAULT_PRIORITY_TIT2,
                 priority_tpe1: str = DEFAULT_PRIORITY_TPE1,
                 priority_trck: str = DEFAULT_PRIORITY_TRCK,
                 priority_tpos: str = DEFAULT_PRIORITY_TPOS,
                 priority_tyer: str = DEFAULT_PRIORITY_TYER,
                 priority_tpub: str = DEFAULT_PRIORITY_TPUB,
                 priority_apic: str = DEFAULT_PRIORITY_APIC):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.draft_model = draft_model
        self.llm_cloud_max_tokens = llm_cloud_max_tokens
        self.llm_limit_tpm = tpm
        self.ollama_num_ctx = ollama_num_ctx
        self.ollama_num_predict = ollama_num_predict
        self.coherence_threshold = coherence_threshold
        self.chunk_size_virtual = chunk_size_virtual
        self.chunk_size_metadata_ollama = chunk_size_metadata_ollama
        self.chunk_size_metadata_cloud = chunk_size_metadata_cloud
        self.chunk_adaptive = chunk_adaptive
        self.chunk_output_tokens_per_track = max(1, chunk_output_tokens_per_track)
        self.chunk_output_safety_ratio = max(0.2, min(0.95, chunk_output_safety_ratio))
        self.user_language = user_language
        self.llm_backend = llm_backend.upper()
        self.metadata_source_priority = metadata_source_priority
        self.priority_tit2 = priority_tit2
        self.priority_tpe1 = priority_tpe1
        self.priority_trck = priority_trck
        self.priority_tpos = priority_tpos
        self.priority_tyer = priority_tyer
        self.priority_tpub = priority_tpub
        self.priority_apic = priority_apic
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

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

    @staticmethod
    def _is_truncation_log(log_data: Dict[str, Any]) -> bool:
        if not isinstance(log_data, dict):
            return False
        if log_data.get("error_code") == "response_truncated":
            return True
        err = str(log_data.get("error") or "").lower()
        return "truncat" in err or "max_tokens" in err or "length" in err

    def check_availability(self) -> bool:
        """起動時にLLMサービスの可用性をチェックする"""
        try:
            if self.llm_backend == "OLLAMA":
                url = f"{self.base_url}/api/tags"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    logger.info(f"Ollamaサーバーとの接続に成功しました: {self.base_url}")
                    return True
                else:
                    logger.error(f"Ollamaサーバーから予期せぬ応答がありました: HTTP {response.status_code}")
                    return False

            elif self.llm_backend in ["GEMINI", "OPENAI_COMPATIBLE"]:
                if not self.api_key or self.api_key == "your_api_key":
                    logger.error(f"{self.llm_backend} のAPIキーが設定されていません。.env ファイルを確認してください。")
                    return False
                
                # Modelsエンドポイントで簡易接続テスト
                if self.llm_backend == "GEMINI":
                    url = f"{self.base_url}/v1beta/openai/models"
                else:
                    url = f"{self.base_url}/v1/models"
                    
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"{self.llm_backend} との接続およびAPIキーの有効性を確認しました。")
                    return True
                elif response.status_code in [401, 403]:
                    logger.error(f"{self.llm_backend} のAPIキーが無効です (HTTP {response.status_code})。.env を確認してください。")
                    return False
                else:
                    logger.warning(f"{self.llm_backend} のAPIキーチェックで予期せぬ応答がありました (HTTP {response.status_code})。")
                    return True # Some compatible servers might not implement /models properly

            else:
                logger.error(f"未知のLLM_BACKENDです: {self.llm_backend}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"LLMサーバー ({self.llm_backend}) との接続テストに失敗しました: {e}")
            return False

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
                "v_idx": idx, # Unique index in this virtual album
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

    def _build_skeleton(self, tracks: list, step: int = 10) -> list:
        if not tracks: return []
        skel = []
        for i in range(0, len(tracks), step):
            skel.append({"v_idx": tracks[i].get("v_idx", 0), "title": tracks[i].get("title", "")})
        if tracks[-1].get("v_idx", 0) != skel[-1]["v_idx"]:
            skel.append({"v_idx": tracks[-1].get("v_idx", 0), "title": tracks[-1].get("title", "")})
        return skel

    def _map_coherences(self, app_id: str, v_local: dict, v_steam: dict, v_fingerprint: dict, num_ctx: int) -> dict:
        local_tracks = v_local.get("tracks", [])
        coherences = {}
        for i in range(0, len(local_tracks), 30):
            c_tracks = local_tracks[i:i+30]
            c_key = f"Coherence_{(i//30)+1}"
            skel = []
            if c_tracks:
                skel.append({"v_idx": c_tracks[0].get("v_idx", 0), "title": c_tracks[0].get("title", "")})
                if len(c_tracks) > 2:
                    mid = len(c_tracks)//2
                    skel.append({"v_idx": c_tracks[mid].get("v_idx", 0), "title": c_tracks[mid].get("title", "")})
                if len(c_tracks) > 1:
                    skel.append({"v_idx": c_tracks[-1].get("v_idx", 0), "title": c_tracks[-1].get("title", "")})
            coherences[c_key] = skel
        
        steam_skel = self._build_skeleton(v_steam.get("tracks", []), 10)
        fp_skel = self._build_skeleton(v_fingerprint.get("tracks", []), 10) if v_fingerprint else []

        prompt = f"""
Generate a Coherence Routing Map for a massive album.
We have split the LOCAL album into logical 'Coherences' (blocks of ~30 tracks).
For each Coherence, identify the corresponding track range (start_v_idx to end_v_idx) in the REFERENCE albums.

### LOCAL COHERENCES (Skeleton):
{json.dumps(coherences, ensure_ascii=False, indent=2)}

### STEAM REFERENCE SKELETON:
{json.dumps(steam_skel, ensure_ascii=False, indent=2)}

### FINGERPRINT REFERENCE SKELETON:
{json.dumps(fp_skel, ensure_ascii=False, indent=2) if fp_skel else "NOT AVAILABLE"}

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE):
```json
{{
  "coherence_mappings": {{
    "Coherence_1": {{
      "steam_start_v_idx": 0,
      "steam_end_v_idx": 29,
      "fingerprint_start_v_idx": 0,
      "fingerprint_end_v_idx": 29
    }}
  }}
}}
```
"""
        res, log = self._call_llm(app_id, prompt, num_ctx=num_ctx)
        if not res or "coherence_mappings" not in res:
            return {}
        return res["coherence_mappings"]

    def consolidate_virtual_albums(self, app_id: int, v_steam: Dict, v_fingerprint: Optional[Dict], v_mbz_search: Optional[Dict], v_local: Dict, num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Consolidates the four virtual albums into a final tag set using LLM.
        """
        full_logs = []
        
        # Simplify albums to save context
        s_steam = self._simplify_v_album(v_steam, sampled=True)
        s_fingerprint = self._simplify_v_album(v_fingerprint, sampled=True)
        s_mbz_search = self._simplify_v_album(v_mbz_search, sampled=True)
        s_local = self._simplify_v_album(v_local, sampled=True)

        # Phase 1: Identity & Global Tags
        identity_prompt = f"""
Generate an audit JSON object based on these three "Virtual Albums".
(Note: Tracklists are sampled/simplified)

### 1. STEAM VIRTUAL ALBUM (Official Store Info)
{json.dumps(s_steam, ensure_ascii=False)}

### 2. FINGERPRINT VIRTUAL ALBUM (Physical Waveform Match / Ground Truth)
{json.dumps(s_fingerprint, ensure_ascii=False) if v_fingerprint else "NOT AVAILABLE"}

### 3. MBZ_SEARCH VIRTUAL ALBUM (Semantic Truth / Text Match)
{json.dumps(s_mbz_search, ensure_ascii=False) if v_mbz_search else "NOT AVAILABLE"}

### 4. LOCAL VIRTUAL ALBUM (Current File Tags/Filenames)
{json.dumps(s_local, ensure_ascii=False)}

### [MASTER AUDIT GUIDELINE]
1. GROUND TRUTH: FINGERPRINT matches are based on physical waveforms. 
   If physical_match_ratio > 80%, set Identity Confidence to 95-100% even if names vary.
   If source is "VERIFIED_MBZ" (FINGERPRINT and MBZ_SEARCH match perfectly), use 100% confidence.
2. STEAM-TRUST PATH: If STEAM tracklist structurally matches LOCAL (same count/order) and titles align, TRUST STEAM as Ground Truth and set Identity Confidence to 100%, EVEN IF FINGERPRINT is missing or has a low match ratio. FINGERPRINT incompleteness must NEVER lower the score when STEAM is a perfect structural match.
3. DISC NUMBER FLEXIBILITY: LOCAL disc numbers (d) are often incorrect or defaulted to 1. 
   If STEAM or FINGERPRINT define multiple discs, you MUST re-assign tracks to the correct discs in Phase 2.
4. IDENTITY ALIASES: Game Developer (Steam) == Artist (MBZ), Publisher (Steam) == Label (MBZ). 
   These are NOT contradictions.
5. JUDGEMENT: Choose ARCHIVE if Confidence >= 100 and Quality >= 95. 
   When ARCHIVE is chosen, you MUST set "archive_vs_review_ratio" to {{"archive": 100, "review": 0}}.

**NOTE: All reasoning and text values (confidence_reason, semantic_label, global_tags) MUST be output in the language code: {self.user_language}. If {self.user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary.**

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE, NO THINKING):
```json
{{
  "identity_confidence": number (0-100 integer),
  "integrity_quality": number (0-100 integer),
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "Reasoning in {self.user_language}",
  "strategy": "FINGERPRINT_BASED" | "STEAM_BASED" | "LOCAL_BASED" | "MBZ_SEARCH_BASED" | "HYBRID",
  "semantic_label": "Label in {self.user_language}",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "canonical_label": "...",
    "chosen_mbz_id": "..."
  }}
}}
```
"""
        global_res, global_log = self._call_llm(app_id, identity_prompt, num_ctx=num_ctx)
        full_logs.append(global_log)

        if not global_res:
             return None, {"phase1_res": None, "phase1_log": global_log}

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
        
        if conf < 100:
             return {}, {"phase1_res": global_res, "phase1_log": global_log}

        # Phase 2: Track-by-Track Mapping with Chunking
        final_instructions = {}
        local_tracks = v_local.get("tracks", [])

        coherence_mappings = None
        if len(local_tracks) >= getattr(self, "coherence_threshold", 75):
            logger.info(f"[{app_id}] Track count ({len(local_tracks)}) exceeds coherence threshold ({self.coherence_threshold}). Initiating Phase 1.5 Map-Reduce (Coherence Routing)...")
            coherence_mappings = self._map_coherences(app_id, v_local, v_steam, v_fingerprint, num_ctx)
            if not coherence_mappings:
                logger.error(f"[{app_id}] Coherence Map-Reduce failed or timed out. Falling back to review.")
                global_res["identity_confidence"] = 0
                global_res["confidence_reason"] = "SYSTEM: 巨大アルバムのCoherence分割（Map-Reduce）に失敗したため、安全のために手動レビューへフォールバックしました。"
                return {}, {"phase1_res": global_res, "phase1_log": global_log}
            logger.info(f"[{app_id}] Coherence Map-Reduce successful. Mappings: {list(coherence_mappings.keys())}")

        # Prepare full simplified reference tracks for Phase 2 (not sampled)
        full_ref_steam = self._simplify_v_album(v_steam, sampled=False).get("tracks", [])
        full_ref_fingerprint = self._simplify_v_album(v_fingerprint, sampled=False).get("tracks", []) if v_fingerprint else []

        base_chunk_size = self.chunk_size_virtual
        i = 0
        while i < len(local_tracks):
            dynamic_base = self._adaptive_chunk_size(base_chunk_size)
            current_chunk_size = min(dynamic_base, len(local_tracks) - i)
            chunk = local_tracks[i:i + current_chunk_size]
            s_chunk = []
            for idx, t in enumerate(chunk):
                s_chunk.append({
                    "chunk_idx": i + idx,
                    "t": t.get("title"),
                    "d": t.get("disc"),
                    "dur": (t.get("duration_ms", 0) // 1000) if t.get("duration_ms") else None
                })

            # Slice reference tracks based on coherence if available
            ref_steam = full_ref_steam
            ref_fingerprint = full_ref_fingerprint
            
            if coherence_mappings:
                c_key = f"Coherence_{(i // 30) + 1}"
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
            
            ref_fingerprint_str = json.dumps(ref_fingerprint, ensure_ascii=False) if ref_fingerprint else "NOT AVAILABLE"

            mapping_prompt = f"""
        Generate track mapping instructions for tracks {i+1} to {i+len(chunk)}.
        Identity: {json.dumps(global_res.get("global_tags"), ensure_ascii=False)}

        ### REFERENCE VIRTUAL ALBUMS (TRACKS ONLY):
        STEAM: {json.dumps(ref_steam, ensure_ascii=False)}
        FINGERPRINT: {ref_fingerprint_str}
        MBZ_SEARCH: {json.dumps(s_mbz_search.get("tracks", []) if s_mbz_search else [], ensure_ascii=False) if v_mbz_search else "NOT AVAILABLE"}

        ### LOCAL_CHUNK TO PROCESS:
        {json.dumps(s_chunk, ensure_ascii=False)}

        ### RULES:
        1. Match LOCAL_CHUNK to FINGERPRINT (if available) first, then MBZ_SEARCH, then STEAM. NEVER select a "use_*" action for a source that is NOT AVAILABLE.
        2. **Unique Mapping**: Each track in the LOCAL_CHUNK MUST map to a **UNIQUE** reference track (v_idx). Do NOT map multiple local tracks to the same "matched_v_idx".
        3. **Automatic Numbering**: If action is "use_steam", "use_fingerprint", or "use_mbz_search", LEAVE "override_track" and "override_disc" as **null**. The system will automatically adopt the numbers from the reference album.

4. **Override Only When Necessary**: Use "override_track" or "override_disc" ONLY if the reference album has WRONG or MISSING numbers (e.g., track number is 0 or null).
5. **Disc Alignment**: If the matched reference track belongs to a different disc than the local "d", you MUST ensure the final output reflects the correct disc.
6. If action is "use_fingerprint", "use_steam", or "use_mbz_search", MUST provide "matched_v_idx" from the respective reference album.
7. No Duplicate Tracks: Ensure that the final mapping does not result in duplicate track numbers within the same disc.
8. Output JSON ONLY. No preamble, no thinking.

**NOTE: All reasoning (reason) MUST be output in the language code: {self.user_language}. If {self.user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary.**

### MANDATORY OUTPUT FORMAT (JSON ONLY):
```json
{{
  "track_instructions": {{
     "CHUNK_INDEX": {{
        "action": "use_fingerprint" | "use_mbz_search" | "use_steam" | "use_local",
        "matched_v_idx": number | null,
        "override_title": string | null,
        "override_track": number | null,
        "override_disc": number | null,
        "composer": string | null,
        "lyricist": string | null,
        "arranger": string | null,
        "reason": "Reasoning in {self.user_language}"
     }}
  }}
}}
```
"""
            track_res, track_log = self._call_llm(app_id, mapping_prompt, num_ctx=num_ctx)

            # If output was truncated, retry this segment with smaller chunks.
            if not track_res and self._is_truncation_log(track_log) and current_chunk_size > 1:
                shrink_to = max(1, current_chunk_size // 2)
                logger.warning(
                    f"[{app_id}] LLM response appears truncated for virtual chunk at index={i}. "
                    f"Reducing chunk size {current_chunk_size} -> {shrink_to}."
                )
                base_chunk_size = shrink_to
                continue

            full_logs.append(track_log)
            
            if track_res and "track_instructions" in track_res:
                for c_idx_str, data in track_res["track_instructions"].items():
                    try:
                        c_idx = int(c_idx_str)
                        if c_idx < 0 or c_idx >= len(local_tracks): continue
                        matching_track = local_tracks[c_idx]
                    except ValueError:
                        # Fallback for LLM title keys (legacy support or hallucination)
                        matching_track = next((t for t in chunk if t["title"] == c_idx_str), None)
                    
                    if matching_track:
                        tid = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"
                        
                        # Pass through MBZ track index if matched with fingerprint or mbz_search
                        mv_idx = data.get("matched_v_idx")
                        if data.get("action") == "use_fingerprint" and mv_idx is not None:
                            if mv_idx < len(ref_fingerprint):
                                data["mbz_track_index"] = ref_fingerprint[mv_idx].get("mbz_track_index")
                        elif data.get("action") == "use_mbz_search" and mv_idx is not None and v_mbz_search:
                            ref_mbz = self._simplify_v_album(v_mbz_search, sampled=False).get("tracks", [])
                            if mv_idx < len(ref_mbz):
                                data["mbz_track_index"] = ref_mbz[mv_idx].get("mbz_idx")
                        
                        data.update({
                            "TPE2": global_res["global_tags"].get("canonical_album_artist"),
                            "TCON": global_res["global_tags"].get("canonical_genre"),
                            "TDRC": global_res["global_tags"].get("canonical_year"),
                            "TPUB": global_res["global_tags"].get("canonical_label"),
                            "TEXT": data.get("lyricist"),
                            "TCOM": data.get("composer"),
                            "TPE4": data.get("arranger"),
                            "identity_confidence": global_res["identity_confidence"],
                            "integrity_quality": global_res.get("integrity_quality", 0),
                            "archive_vs_review_ratio": global_res.get("archive_vs_review_ratio", {"archive": 0, "review": 100}),
                            "confidence_score": global_res["identity_confidence"],
                            "strategy": global_res["strategy"],
                            "semantic_label": global_res["semantic_label"]
                        })
                        final_instructions[tid] = data

            i += len(chunk)

        return final_instructions, {"phase1_res": global_res, "logs": full_logs}

    def _call_llm(self, app_id: int, prompt: str, num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        system_prompt = """You are a [Metadata Audit JSON Generator].
Your ONLY output is a raw JSON object. 

RULES:
1. Start your response with "{" immediately.
2. DO NOT use reasoning blocks, "Thinking Process", or any preamble.
3. Output MUST be valid JSON.
4. If uncertain, default to judgment "REVIEW" and confidence 0."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "prompt": prompt, "response": None, "error": None}

        logger.debug(f"[{app_id}] --- [LLM PROMPT START] ---\n{prompt}\n--- [LLM PROMPT END] ---")

        if self.llm_backend not in ["OLLAMA"] and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5

        if self.llm_backend == "OLLAMA":
            url = f"{self.base_url}/api/chat"
            options = {"temperature": 0.0, "num_predict": -1}
            if num_ctx:
                options["num_ctx"] = num_ctx
            payload = {
                "model": self.model, "messages": messages, "stream": False, "format": "json",
                "options": options
            }
            if self.draft_model:
                payload["draft_model"] = self.draft_model
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{self.base_url}/v1beta/openai/chat/completions" if self.llm_backend == "GEMINI" else f"{self.base_url}/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            payload["max_tokens"] = self.llm_cloud_max_tokens
                
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=600)
                if response.status_code == 200:
                    res_json = response.json()
                    message = res_json.get("message", {})
                    content = message.get("content", "")
                    thinking = message.get("thinking", "")
                    done_reason = res_json.get("done_reason")
                    log_entry["meta"] = {
                        "done": res_json.get("done"),
                        "done_reason": done_reason,
                        "prompt_eval_count": res_json.get("prompt_eval_count"),
                        "eval_count": res_json.get("eval_count"),
                    }

                    if done_reason in {"length", "max_tokens"}:
                        log_entry["error"] = f"response truncated by backend (done_reason={done_reason})"
                        log_entry["error_code"] = "response_truncated"
                        logger.warning(f"[{app_id}] LLM output truncated by backend: done_reason={done_reason}")
                        return None, log_entry
                    
                    if self.llm_backend != "OLLAMA":
                        content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")

                    logger.debug(f"[{app_id}] --- [LLM RESPONSE START] ---\n{content}\n--- [LLM RESPONSE END] ---")
                    if thinking:
                        logger.debug(f"[{app_id}] --- [LLM THINKING START] ---\n{thinking}\n--- [LLM THINKING END] ---")
                    
                    if not content or not content.strip():
                        if thinking and '{' in thinking:
                            # Attempt to salvage JSON from thinking if content is empty
                            content = thinking
                        else:
                            raise ValueError("Empty response")
                    
                    log_entry["response"] = content
                    
                    try:
                        clean_content = re.sub(r'```json\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL)
                        clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
                        start_idx = clean_content.find('{')
                        end_idx = clean_content.rfind('}')
                        if start_idx != -1 and end_idx != -1:
                            json_str = clean_content[start_idx:end_idx + 1]
                            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                            return json.loads(json_str), log_entry
                        else:
                            raise ValueError("No valid JSON object found in response")
                    except Exception as e:
                        logger.warning(f"[{app_id}] JSON strict parsing failed: {e}")
                        log_entry["error_code"] = "json_parse_error"
                        raise
                
                log_entry["error"] = f"HTTP {response.status_code}"
                logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed with HTTP {response.status_code}: {response.text}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                return None, log_entry

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed: {e}")
                    time.sleep(retry_delay)
                    continue
                log_entry["error"] = str(e)
                return None, log_entry
        return None, log_entry
