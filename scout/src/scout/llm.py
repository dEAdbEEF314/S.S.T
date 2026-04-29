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
                 model: str = "gemma-4-31b-it", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = "ja",
                 force_local: bool = False):
        if not base_url.endswith("/chat/completions"):
            self.api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            self.api_url = base_url
            
        self.api_key = api_key
        self.model = model
        self.user_language = user_language
        self.force_local = force_local
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        full_logs = []
        
        # --- Phase 1: Determine Global Identity (The "Soul") ---
        global_id_prompt = f"""
あなたは音楽メタデータ管理の専門家です。
複数の情報源から、このアルバムの「唯一の真実（Identity）」を決定してください。

### 【重要】判定ゲートとスコアリング基準 (SST.md 準拠):
あなたの主な任務は、メタデータに少しでも疑念がある場合に「REVIEW」へ送ることです。
- **Rank S (100点)**: Steam, MBZ, 埋め込みタグの3者が「曲名・曲数ともに完璧に一致」する場合。 -> ARCHIVE
- **Rank A (95点)**: 高い一貫性があり、"Dirty Tags"（曲名への番号混入など）が存在しない場合。 -> ARCHIVE
- **Rank B (80-90点)**: わずかな不一致、曲数の相違、または "Dirty Tags" が検出された場合。 -> REVIEW
- **Rank C (80点未満)**: 証拠不十分、または重大な競合がある場合。 -> REVIEW

### 【重要】思考・出力言語:
- 思考および "confidence_reason", "semantic_label" は【日本語】のみを使用してください。

### ALBUM CONTEXT (Locked Truth):
- アルバム名: {steam_info.get('name')}
- 開発者: {steam_info.get('developer')}
- 出版社: {steam_info.get('publisher')}
- リリース年: {steam_info.get('release_date', '')[:4]}

### MUSICBRAINZ CANDIDATES:
{json.dumps(mbz_candidates, indent=2, ensure_ascii=False)}

### LOCAL TRACK LIST SUMMARY:
{json.dumps([{"id": tid, "duration": s[0].get("duration")} for tid, s in track_sources.items()], indent=2)}

### MANDATORY OUTPUT FORMAT:
Return ONLY a valid JSON object:
{{
  "confidence_score": 100 | 95 | 90 | 80 | 0,
  "confidence_reason": "日本語による詳細な根拠",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "semantic_label": "データ異常の要約ラベル（日本語 40文字以内）",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "chosen_mbz_index": 0
  }}
}}
"""
        global_res, global_log = self._call_llm(global_id_prompt)
        full_logs.append(global_log)
        
        if not global_res or global_res.get("strategy") == "REVIEW_REQUIRED":
            return None, {"phase1_log": global_log}

        # --- Phase 2: Sequential Track Mapping (The "Body") ---
        global_identity = global_res.get("global_tags", {})
        strategy = global_res.get("strategy")
        all_instructions = {}
        
        track_ids = list(track_sources.keys())
        chunk_size = 20 if self.force_local else 40

        for i in range(0, len(track_ids), chunk_size):
            chunk_ids = track_ids[i:i + chunk_size]
            chunk_sources = {tid: track_sources[tid] for tid in chunk_ids}
            
            mapping_prompt = f"""
以下のトラックを、決定されたアルバム Identity に基づいてマッピングしてください。

### 【重要】スコアリングリマインダー:
- Rank S (100点) または Rank A (95点) 以外はすべて REVIEW 送りとなります。
- 曲名に "01. " などの番号が混入している（Dirty Tags）場合は、必ず 90点以下としてください。

### 【重要】思考・出力言語:
- "reason" は必ず【日本語】で記述してください。英中混じりは厳禁です。

### 【重要】推測の禁止:
- ファイル名からタイトルを勝手に憶測しないでください。
- 根拠がない場合は action: "needs_review", reason: "証拠不足" としてください。

### FIXED ALBUM IDENTITY:
{json.dumps(global_identity, indent=2)}

### TRACKS TO MAP:
{json.dumps(chunk_sources, indent=2, ensure_ascii=False)}

### MANDATORY OUTPUT FORMAT:
Return ONLY a valid JSON object:
{{
  "track_instructions": {{
     "TRACK_ID": {{
        "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
        "mbz_track_index": 0,
        "override_title": null, 
        "override_track": null,
        "reason": "日本語による判断理由"
     }},
     ...
  }}
}}
"""
            chunk_res, chunk_log = self._call_llm(mapping_prompt)
            full_logs.append(chunk_log)
            
            if chunk_res and "track_instructions" in chunk_res:
                instructions = chunk_res["track_instructions"]
                for tid in instructions:
                    instructions[tid]["TPE2"] = global_identity.get("canonical_album_artist")
                    instructions[tid]["TCON"] = global_identity.get("canonical_genre")
                    instructions[tid]["TDRC"] = global_identity.get("canonical_year")
                    instructions[tid]["confidence_score"] = global_res.get("confidence_score")
                    instructions[tid]["confidence_reason"] = global_res.get("confidence_reason")
                    instructions[tid]["strategy"] = strategy
                    instructions[tid]["semantic_label"] = global_res.get("semantic_label")
                all_instructions.update(instructions)

        return all_instructions, {"chunks": full_logs}

    def _call_llm(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        messages = [{"role": "user", "content": prompt}]
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "response": None, "error": None}
        
        if not self.force_local and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries + 1):
            try:
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }
                if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                    payload["options"] = {"num_ctx": 32768, "num_predict": 4096}

                response = requests.post(self.api_url, headers=headers, json=payload, timeout=300)
                
                if response.status_code == 200:
                    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not content or not content.strip(): raise ValueError("Empty response")
                    log_entry["response"] = content
                    
                    # Act-14: Detailed debug logging of raw response
                    logger.debug(f"LLM Raw Response ({self.model}): {content[:500]}...")
                    
                    # Robust Extract
                    clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    start_idx = clean_content.find('{')
                    end_idx = clean_content.rfind('}')
                    
                    if start_idx != -1 and end_idx != -1:
                        json_str = clean_content[start_idx:end_idx + 1]
                        json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                        try:
                            return json.loads(json_str), log_entry
                        except json.JSONDecodeError as e:
                            logger.warning(f"Repairing JSON for {self.model}: {e}")
                            open_braces = json_str.count('{')
                            close_braces = json_str.count('}')
                            if open_braces > close_braces: json_str += '}' * (open_braces - close_braces)
                            try:
                                return json.loads(json_str), log_entry
                            except:
                                logger.error(f"JSON repair failed. Content: {content[:200]}...")
                                raise
                
                if response.status_code in [500, 503, 504, 429] and attempt < max_retries:
                    logger.warning(f"LLM {self.model} failed with HTTP {response.status_code}. Retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                
                log_entry["error"] = f"HTTP {response.status_code}"
                logger.error(f"LLM Call failed with HTTP {response.status_code}: {response.text[:200]}")
                return None, log_entry

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"LLM {self.model} attempt {attempt+1} error: {e}. Retrying...")
                    time.sleep(retry_delay)
                    continue
                log_entry["error"] = str(e)
                logger.error(f"LLM Call completely failed: {e}")
                return None, log_entry
        return None, log_entry
