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
        self.limit_tpm = int(tpm * 0.9) if tpm > 0 else 10**9 # 0 means practically unlimited
        self.limit_rpd = rpd
        self.lock = threading.Lock()
        self.request_times = collections.deque()
        self.token_times = collections.deque() 
        
    def _get_daily_key(self):
        return f"llm_usage_{datetime.utcnow().strftime('%Y%m%d')}.json"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, total_chars // 3)

    def _get_usage(self) -> int:
        try:
            path = Path(self._get_daily_key())
            if not path.exists(): return 0
            with open(path, "r") as f:
                data = json.load(f)
                return data.get("requests", 0)
        except: return 0

    def _increment_usage(self, current: int):
        try:
            path = Path(self._get_daily_key())
            with open(path, "w") as f:
                json.dump({"requests": current + 1, "last_update": datetime.utcnow().isoformat()}, f)
        except Exception as e:
            logger.warning(f"Failed to save LLM usage: {e}")

    def acquire(self, messages: List[Dict[str, str]]) -> bool:
        tokens = self._estimate_tokens(messages)
        while True:
            with self.lock:
                now = time.time()
                # Clean old history
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                req_count = len(self.request_times)
                load_factor = req_count / self.limit_rpm if self.limit_rpm > 0 else 0
                
                # Check Daily Limit
                remote_count = self._get_usage()
                if remote_count >= self.limit_rpd:
                    logger.info(f"Daily LLM request limit reached ({self.limit_rpd}). Stopping S.S.T system.")
                    raise SystemExit(0)

                # 90% Critical Threshold: Strict Block
                if load_factor >= 0.9:
                    wait = self.request_times[0] + 61.0 - now
                
                # 70% Warning Threshold: Add Jitter/Throttling
                elif load_factor >= 0.7:
                    import random
                    wait = 2.0 + random.uniform(0, 3.0) # Slow down slightly
                
                # Check Token Limit (TPM)
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    if self.token_times:
                        wait = self.token_times[0][0] + 61.0 - now
                    else: return True
                
                else:
                    # Within safe limits ( < 70% RPM )
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    self._increment_usage(remote_count)
                    return True
            
            # If we are here, we need to wait
            time.sleep(max(0.1, wait))

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, storage: Any = None, 
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
        self.app_id = None
        self.album_name = None
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def set_context(self, app_id: int, album_name: str):
        self.app_id = app_id
        self.album_name = album_name

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Act-11 Hotfix: Stateful Sequential Processing.
        1. Determine Global Identity (Artist, Album, MBID).
        2. Map tracks in chunks using Global Identity as a constraint.
        """
        full_logs = []
        
        # --- Phase 1: Determine Global Identity (The "Soul") ---
        global_id_prompt = f"""
You are an expert Music Metadata Librarian.
Your task: Analyze the sources and determine the Canonical Album Identity.

### ALBUM CONTEXT (Locked Truth):
- Fixed Album Title: {steam_info.get('name')}
- Developers: {steam_info.get('developer')}
- Publishers: {steam_info.get('publisher')}
- Release Year: {steam_info.get('release_date', '')[:4]}

### INFORMATION SOURCES:
1. [Embedded Tags]: Found inside files. High priority.
2. [MusicBrainz]: External database candidates.
3. [Filenames]: Low priority fallback.

### MUSICBRAINZ CANDIDATES:
{json.dumps(mbz_candidates, indent=2, ensure_ascii=False)}

### LOCAL TRACK LIST SUMMARY:
{json.dumps([{"id": tid, "duration": s[0].get("duration"), "has_tags": any(x.get("type").startswith("embedded") for x in s)} for tid, s in track_sources.items()], indent=2)}

### MANDATORY OUTPUT FORMAT:
Return ONLY a valid JSON object:
{{
  "confidence_score": 0-100,
  "confidence_reason": "Write this in language: {self.user_language}",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "chosen_mbz_index": 0 // Index of best MBZ candidate. -1 if none.
  }}
}}

### STRICT RULES:
1. BANDCAMP ALLOWANCE: If no direct Steam AppID link is found in MBZ, Bandcamp links (context) are VALID and reliable sources for Indie games.
2. ZERO HALLUCINATION: If sources are empty/conflicting, use "REVIEW_REQUIRED".
3. LANGUAGE CONSISTENCY: Write reasoning ONLY in {self.user_language}.
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
        # Act-12: Use smaller chunk size for local LLMs to save memory, larger for remote
        chunk_size = 20 if self.force_local else 40

        for i in range(0, len(track_ids), chunk_size):
            chunk_ids = track_ids[i:i + chunk_size]
            chunk_sources = {tid: track_sources[tid] for tid in chunk_ids}
            
            mapping_prompt = f"""
Now map the following tracks using the FIXED ALBUM IDENTITY.

### FIXED ALBUM IDENTITY:
{json.dumps(global_identity, indent=2)}
- Strategy: {strategy}

### TRACKS TO MAP:
{json.dumps(chunk_sources, indent=2, ensure_ascii=False)}

### MANDATORY OUTPUT FORMAT:
Return ONLY a valid JSON object:
{{
  "track_instructions": {{
     "TRACK_ID": {{
        "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
        "mbz_track_index": 0, // Only if action is use_mbz. Index in the tracks list of chosen MBZ candidate.
        "override_title": null, 
        "override_track": null,
        "reason": "Write this in language: {self.user_language}"
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
                all_instructions.update(instructions)
            else:
                logger.error(f"Failed to get instructions for chunk {i//chunk_size + 1}")

        return all_instructions, {"chunks": full_logs}

    def _call_llm(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Helper to call LLM and handle JSON parsing/repair."""
        messages = [{"role": "user", "content": prompt}]
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "response": None,
            "error": None
        }
        
        # Act-12: Bypassing limiter if force_local is set
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
                    "temperature": 0.0
                }
                if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                    payload["options"] = {"num_ctx": 32768, "num_predict": 4096}

                response = requests.post(self.api_url, headers=headers, json=payload, timeout=300)
                
                if response.status_code == 200:
                    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if not content or not content.strip():
                        raise ValueError("Received empty content from LLM.")
                        
                    log_entry["response"] = content
                    
                    # Extract and Repair JSON
                    json_str = content
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0].strip()
                    
                    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                    open_braces = json_str.count('{')
                    close_braces = json_str.count('}')
                    if open_braces > close_braces:
                        json_str += '}' * (open_braces - close_braces)

                    try:
                        return json.loads(json_str), log_entry
                    except json.JSONDecodeError as e:
                        raise ValueError(f"JSON parsing failed: {e}. Raw content snippet: {content[:200]}...")
                
                if response.status_code in [500, 503, 504, 429] and attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt+1} failed with HTTP {response.status_code}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                
                log_entry["error"] = f"HTTP {response.status_code}: {response.text}"
                return None, log_entry

            except requests.exceptions.Timeout:
                log_entry["error"] = "Timeout: LLM took too long to respond (>300s)"
                if attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt+1} timed out. Retrying...")
                    time.sleep(retry_delay)
                    continue
            except Exception as e:
                logger.warning(f"LLM attempt {attempt+1} encountered error: {e}")
                if attempt < max_retries:
                    logger.warning(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                log_entry["error"] = str(e)
                logger.error(f"LLM Call completely failed after {max_retries} retries: {e}")
                return None, log_entry
        return None, log_entry
