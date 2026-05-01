import os
import re
import json
import logging
import requests
import time
import collections
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("scout.llm")

class DistributedRateLimiter:
    def __init__(self, rpm: int, tpm: int, rpd: int):
        self.limit_rpm = rpm
        self.limit_tpm = int(tpm * 0.9) if tpm > 0 else 10**9
        self.limit_rpd = rpd
        self.lock = threading.Lock()
        self.request_times = collections.deque()
        self.token_times = collections.deque() 
        
    def _get_usage_file(self):
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        return log_dir / f"llm_usage_{datetime.now().strftime('%Y%m%d')}.json"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, total_chars // 3)

    def _get_usage(self) -> int:
        try:
            path = self._get_usage_file()
            if not path.exists(): return 0
            with open(path, "r") as f:
                data = json.load(f)
                return data.get("requests", 0)
        except: return 0

    def _increment_usage(self, current: int):
        try:
            path = self._get_usage_file()
            with open(path, "w") as f:
                json.dump({"requests": current + 1, "last_update": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.warning(f"Failed to save LLM usage: {e}")

    def acquire(self, messages: List[Dict[str, str]]) -> bool:
        tokens = self._estimate_tokens(messages)
        while True:
            with self.lock:
                now = time.time()
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                req_count = len(self.request_times)
                load_factor = req_count / self.limit_rpm if self.limit_rpm > 0 else 0
                
                remote_count = self._get_usage()
                if remote_count >= self.limit_rpd:
                    logger.info(f"Daily LLM request limit reached ({self.limit_rpd}).")
                    raise SystemExit(0)

                if load_factor >= 0.9:
                    wait = self.request_times[0] + 61.0 - now
                elif load_factor >= 0.7:
                    import random
                    wait = 2.0 + random.uniform(0, 3.0)
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    if self.token_times:
                        wait = self.token_times[0][0] + 61.0 - now
                    else: return True
                else:
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    self._increment_usage(remote_count)
                    return True
            time.sleep(max(0.1, wait))

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = "ja",
                 llm_backend: str = "GEMINI"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.user_language = user_language
        self.llm_backend = llm_backend.upper()
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        full_logs = []
        
        # --- Phase 1: Determine Global Identity (The "Soul") ---
        global_id_prompt = f"""
あなたは音楽メタデータ管理の極めて厳格な監査官です。
複数の情報源から、このアルバムの「唯一の真実（Identity）」を決定してください。

### 【判定基準：100点からの減点方式】
1. **初期値**: 100点
2. **減点対象**:
    - 曲名が一部でも異なる: -10点
    - 曲数が一致しない: -20点
    - リリース年が一致しない: -5点
    - Dirty Tags（番号混入等）がある: -50点
    - 曖昧な表現（〜ですが、〜と思われる）を理由に含める: -10点

### 【重要】出力項目:
- **`archive_vs_review_ratio`**: Archiveにすべきか、Reviewにすべきかの確信度を「比率（合計100）」で答えなさい。（例：Archive: 20, Review: 80）
- **`confidence_score`**: 上記減点方式を適用した最終スコア（0-100）。

### ALBUM CONTEXT (Locked Truth):
- アルバム名: {steam_info.get('name')}
- 開発者: {steam_info.get('developer')}
- リリース年: {steam_info.get('release_date', '')[:4]}

### MUSICBRAINZ CANDIDATES:
{json.dumps(mbz_candidates, indent=2, ensure_ascii=False)}

### LOCAL TRACK LIST SUMMARY:
{json.dumps([{"id": tid, "duration": s[0].get("duration")} for tid, s in track_sources.items()], indent=2)}

### MANDATORY OUTPUT FORMAT (JSON ONLY):
{{
  "confidence_score": number,
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "日本語による減点根拠の詳細",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "semantic_label": "日本語 40文字以内",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "chosen_mbz_index": number
  }}
}}
"""
        global_res, global_log = self._call_llm(global_id_prompt)
        full_logs.append(global_log)
        
        if not global_res:
            return None, {"phase1_log": global_log}
            
        # Archive判定の厳格なクロスチェック
        # Act-14: If LLM explicitly chose REVIEW_REQUIRED, we HONOR it immediately.
        # If score or ratio is low, we force review.
        final_score = int(global_res.get("confidence_score", 0))
        archive_ratio = int(global_res.get("archive_vs_review_ratio", {}).get("archive", 0))
        
        if final_score < 95 or archive_ratio < 95 or global_res.get("strategy") == "REVIEW_REQUIRED":
            # Force empty instructions to trigger REVIEW status in processor
            return {}, {"phase1_res": global_res, "phase1_log": global_log}

        # --- Phase 2: Sequential Track Mapping (The "Body") ---
        global_identity = global_res.get("global_tags", {})
        strategy = global_res.get("strategy")
        all_instructions = {}
        
        track_ids = list(track_sources.keys())
        chunk_size = 10 if self.llm_backend == "OLLAMA" else 30

        for i in range(0, len(track_ids), chunk_size):
            chunk_ids = track_ids[i:i + chunk_size]
            chunk_sources = {tid: track_sources[tid] for tid in chunk_ids}
            
            mapping_prompt = f"""
以下のトラックを正確にマッピングしてください。推測は死罪に値します。
根拠がない場合は action: "needs_review" としなさい。

### FIXED IDENTITY:
{json.dumps(global_identity, indent=2)}

### TRACKS TO MAP:
{json.dumps(chunk_sources, indent=2, ensure_ascii=False)}

### MANDATORY OUTPUT FORMAT (JSON ONLY):
{{
  "track_instructions": {{
     "TRACK_ID": {{
        "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
        "mbz_track_index": number,
        "override_title": string | null,
        "reason": "日本語判断理由"
     }}
  }}
}}
"""
            chunk_res, chunk_log = self._call_llm(mapping_prompt)
            full_logs.append(chunk_log)
            
            if chunk_res and "track_instructions" in chunk_res:
                instructions = chunk_res["track_instructions"]
                for tid in instructions:
                    instructions[tid].update({
                        "TPE2": global_identity.get("canonical_album_artist"),
                        "TCON": global_identity.get("canonical_genre"),
                        "TDRC": global_identity.get("canonical_year"),
                        "confidence_score": final_score,
                        "confidence_reason": global_res.get("confidence_reason"),
                        "strategy": strategy,
                        "semantic_label": global_res.get("semantic_label"),
                        "chosen_mbz_index": global_identity.get("chosen_mbz_index", 0)
                    })
                all_instructions.update(instructions)

        return all_instructions, {"phase1_res": global_res, "phase1_log": global_log, "chunks": full_logs}

    def _call_llm(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        messages = [{"role": "user", "content": prompt}]
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "prompt": prompt, "response": None, "error": None}
        
        # Act-14: Log full prompt for absolute transparency
        logger.debug(f"--- [LLM PROMPT START] ---\n{prompt}\n--- [LLM PROMPT END] ---")

        if self.llm_backend not in ["OLLAMA"] and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5
        
        if self.llm_backend == "OLLAMA":
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model, "messages": messages, "stream": False, "format": "json",
                "options": {"num_ctx": 32768, "num_predict": 8192, "temperature": 0.0}
            }
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{self.base_url}/v1beta/openai/chat/completions" if self.llm_backend == "GEMINI" else f"{self.base_url}/v1/chat/completions"
            payload = {"model": self.model, "messages": messages, "temperature": 0.0, "response_format": {"type": "json_object"}}
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=300)
                if response.status_code == 200:
                    res_json = response.json()
                    content = res_json.get("message", {}).get("content", "") if self.llm_backend == "OLLAMA" else res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    # Act-14: Log full response for absolute transparency
                    logger.debug(f"--- [LLM RESPONSE START] ---\n{content}\n--- [LLM RESPONSE END] ---")
                    
                    if not content or not content.strip(): raise ValueError("Empty response")
                    log_entry["response"] = content
                    
                    clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    start_idx = clean_content.find('{')
                    end_idx = clean_content.rfind('}')
                    
                    if start_idx != -1 and end_idx != -1:
                        json_str = clean_content[start_idx:end_idx + 1]
                        return json.loads(json_str), log_entry
                    else:
                        raise ValueError("No valid JSON found in response (possible truncation)")
                
                log_entry["error"] = f"HTTP {response.status_code}"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                return None, log_entry

            except Exception as e:
                logger.warning(f"LLM {self.llm_backend} attempt {attempt+1} failed: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                log_entry["error"] = str(e)
                return None, log_entry
        return None, log_entry
