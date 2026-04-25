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
                 user_language: str = "ja"):
        if not base_url.endswith("/chat/completions"):
            self.api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            self.api_url = base_url
            
        self.api_key = api_key
        self.model = model
        self.user_language = user_language
        self.app_id = None
        self.album_name = None
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def set_context(self, app_id: int, album_name: str):
        self.app_id = app_id
        self.album_name = album_name

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Act-12: Uses Differential Mapping to minimize token usage and resolve truncation issues.
        """
        full_log = {
          "timestamp": datetime.utcnow().isoformat(),
          "model": self.model,
          "app_id": self.app_id,
          "album_name": self.album_name,
          "input_summary": {
            "track_count": len(track_sources),
            "mbz_candidate_count": len(mbz_candidates)
          },
          "response": None
        }

        # Build Differential Mapping Prompt
        prompt = f"""
You are an expert Music Metadata Librarian. Your task is to analyze multiple metadata sources and provide a "Canonical Mapping Instruction" for a game soundtrack album.

### ALBUM CONTEXT (Locked Truth):
- Steam Album Name: {steam_info.get('name')}
- Developers: {steam_info.get('developer')}
- Publishers: {steam_info.get('publisher')}
- Release Year: {steam_info.get('release_date', '')[:4]}

### INFORMATION SOURCES & WEIGHTS:
1. [Embedded Tags]: Metadata (Title/Track) found inside files. (HIGH PRIORITY/RELIABILITY)
2. [MusicBrainz]: External database candidates. (MODERATE RELIABILITY)
3. [Filenames]: Inferred names/numbers from files. (LOW PRIORITY/FALLBACK)

### MUSICBRAINZ CANDIDATES:
{json.dumps(mbz_candidates, indent=2, ensure_ascii=False)}

### LOCAL TRACK DATA:
{json.dumps(track_sources, indent=2, ensure_ascii=False)}

### MANDATORY OUTPUT FORMAT:
Return ONLY a valid JSON object:
{{
  "confidence_score": 0-100,
  "confidence_reason": "Explain your score. Write this in language: {self.user_language}",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "global_tags": {{
    "canonical_album_artist": "Chosen artist for the whole album.",
    "canonical_album_title": "Chosen album title.",
    "canonical_genre": "Main genre.",
    "canonical_year": "YYYY"
  }},
  "track_instructions": {{
     "TRACK_ID": {{
        "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
        "mbz_index": 0, // Only if action is use_mbz. Index in the candidate list.
        "mbz_track_index": 0, // Only if action is use_mbz. Index in the chosen MBZ candidate's tracklist.
        "override_title": null, // Use ONLY if all sources have typos.
        "override_track": null, // Use ONLY if track order is missing or clearly wrong.
        "reason": "Why this action was chosen. Write this in language: {self.user_language}"
     }},
     ...
  }}
}}

### STRICT RULES:
1. DURATION CHECK: If a local track's duration differs from a MusicBrainz track by >5s, DO NOT use 'use_mbz' for that track unless it is a clear match.
2. INDIE PRIORITIZATION: For indie games, prefer [Embedded Tags] over MusicBrainz if MBZ data seems sparse or incorrect.
3. TRACK ID MATCHING: Use the exact "TRACK_ID" strings provided in Local Track Data.
4. ZERO HALLUCINATION: If no reliable source exists, use "needs_review".
"""
        messages = [{"role": "user", "content": prompt}]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        logger.info(f"Consolidating metadata for {self.album_name} in one pass...")
        
        if not self.limiter.acquire(messages):
            return None, {"error": "Rate limit reached", "log": full_log}

        max_retries = 5
        retry_delay = 5
        last_response_text = ""
        
        for attempt in range(max_retries + 1):
            try:
                # Build standard OpenAI-compatible payload
                payload = {
                    "model": self.model, 
                    "messages": messages, 
                    "temperature": 0.0
                }
                
                # Add Ollama-specific options ONLY if using local Ollama (Undertale fix)
                if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                    payload["options"] = {
                        "num_ctx": 32768,  # Expand context window to 32k
                        "num_predict": 4096 # Allow long JSON responses
                    }
                
                response = requests.post(self.api_url, 
                                      json=payload, 
                                      headers=headers, 
                                      timeout=300) # Extend to 5 mins
                
                if response.status_code == 200:
                    last_response_text = response.text.strip()
                    if last_response_text:
                        break # Real success
                    else:
                        logger.warning(f"LLM attempt {attempt+1} returned empty 200 OK. Retrying...")
                
                if response.status_code in [500, 503, 504, 429] and attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt+1} failed with {response.status_code}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                
                logger.error(f"LLM Error {response.status_code}: {response.text}")
                return None, full_log

            except (requests.exceptions.RequestException, Exception) as e:
                if attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt+1} exception: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                logger.error(f"LLM Batch Consolidation failed after retries: {e}")
                return None, full_log

        try:
            content = response.json()["choices"][0]["message"]["content"]
            
            # Extract JSON
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            
            # Act-12: Robust JSON Repair
            # 1. Remove trailing commas in objects/arrays
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            # 2. Basic brace matching check (optional, but helps with truncation)
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            if open_braces > close_braces:
                json_str += '}' * (open_braces - close_braces)

            result = json.loads(json_str)
            full_log["response"] = result
            
            # Map back to the expected internal format for processor.py
            instructions = result.get("track_instructions", {})
            global_tags = result.get("global_tags", {})
            
            # Inject global fields and scores into each track entry for compatibility with processor.py's expectation
            for tid in instructions:
                instructions[tid]["TALB"] = global_tags.get("canonical_album_title")
                instructions[tid]["TPE2"] = global_tags.get("canonical_album_artist")
                instructions[tid]["TCON"] = global_tags.get("canonical_genre")
                instructions[tid]["TDRC"] = global_tags.get("canonical_year")
                instructions[tid]["confidence_score"] = result.get("confidence_score")
                instructions[tid]["confidence_reason"] = result.get("confidence_reason")
                instructions[tid]["strategy"] = result.get("strategy")

            return instructions, full_log

        except Exception as e:
            logger.error(f"LLM Batch Consolidation failed: {e}")
            return None, full_log
