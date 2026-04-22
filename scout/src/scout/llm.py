import os
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
    """
    Strictly manages RPM, TPM and RPD. 
    Currently using a local JSON file to track usage.
    """
    def __init__(self, rpm: int, tpm: int, rpd: int):
        self.limit_rpm = rpm
        self.limit_tpm = int(tpm * 0.9)
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
        wait = 0
        while True:
            with self.lock:
                now = time.time()
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                if len(self.request_times) >= self.limit_rpm:
                    wait = self.request_times[0] + 62.0 - now
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    if self.token_times:
                        wait = self.token_times[0][0] + 62.0 - now
                    else:
                        return True
                else:
                    remote_count = self._get_usage()
                    if remote_count >= self.limit_rpd:
                        return False
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    self._increment_usage(remote_count)
                    return True
            time.sleep(max(0.2, wait))

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, storage: Any = None, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 30, tpm: int = 15000, rpd: int = 14400):
        if not base_url.endswith("/chat/completions"):
            self.api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            self.api_url = base_url
            
        self.api_key = api_key
        self.model = model
        self.app_id = None
        self.album_name = None
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def set_context(self, app_id: int, album_name: str):
        self.app_id = app_id
        self.album_name = album_name

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        full_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": self.model,
            "app_id": self.app_id,
            "album_name": self.album_name,
            "steps": {}
        }

        # --- STEP 1: Global Summary Pass ---
        global_decision = self._get_global_decision(steam_info, track_sources)
        if not global_decision:
            return None, {"error": "Failed to get global decision", "log": full_log}
        
        full_log["steps"]["global_decision"] = global_decision

        # --- STEP 2: Iterative Track Consolidation ---
        instructions = f"""
You are a Factual Metadata Organizer.
Use the following GLOBAL RULES determined for this album to consolidate metadata for the specific track provided.

### GLOBAL RULES:
{json.dumps(global_decision, indent=2, ensure_ascii=False)}

### TARGET MAPPING (JSON output keys):
Return ONLY a pure JSON object without markdown code blocks.
Map the consolidated truth to these specific ID3v2.3 fields:
- TIT2: Original Track Title (most detailed).
- TPE1: Artist (Composer/Performer names).
- TALB: Album Name (Use canonical_album_title from Global Rules).
- TPE2: Album Artist (Use canonical_album_artist from Global Rules).
- TCON: Genre (Use canonical_genre from Global Rules).
- TIT1: Grouping (Format: "[Series or Game Title] | Steam").
- COMM: Comment (Format: "[Game Title] | [Steam Tags] | [AppID] | [URL]").
- TCOM: Composer (Individual/Unit names).
- TDRC: Year (YYYY).
- TRCK: Track Number (Mandatory, integer).
- TPOS: Disc Number (Format: "Disc/Total", e.g., "1/1").
- TLAN: Language Code.
- source: Origin of this metadata (e.g., "MusicBrainz Match", "Steam API", "Embedded").

### STRICT RULES:
1. ABSOLUTE PROHIBITION ON HALLUCINATION: You are a factual organizer, NOT a creative writer. Do NOT invent artists, dates, or titles. 
2. NO INFERENCE: Do not guess based on your training data. Use ONLY the provided JSON sources.
3. SOURCE PRIORITY: If MusicBrainz source name contains "(ultra_confirmed)", its tracklist and titles are the ABSOLUTE TRUTH. Use them exactly.
4. UNKNOWN DATA: If a field cannot be determined from ANY provided source, you MUST output "Unknown".
5. OUTPUT: Return ONLY a valid, pure JSON object. Do not include markdown code blocks.
"""
        consolidated_results = {}
        full_log["steps"]["tracks"] = []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for track_id, sources in track_sources.items():
            full_prompt = f"{instructions}\n\nConsolidate metadata for Track ID: {track_id}\nSources: {json.dumps(sources, indent=2, ensure_ascii=False)}"
            messages = [{"role": "user", "content": full_prompt}]

            logger.info(f"Processing track {track_id} using global rules...")
            
            if not self.limiter.acquire(messages):
                return None, {"error": f"Rate limit reached at track {track_id}", "log": full_log}

            try:
                response = requests.post(self.api_url, json={"model": self.model, "messages": messages, "temperature": 0.0}, headers=headers, timeout=90)
                if response.status_code != 200:
                    logger.error(f"Error {response.status_code}: {response.text}")
                    return None, full_log
                
                content = response.json()["choices"][0]["message"]["content"]
                
                json_str = content
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                
                track_json = json.loads(json_str)
                consolidated_results[track_id] = track_json
                
                full_log["steps"]["tracks"].append({
                    "track_id": track_id, 
                    "response": track_json 
                })
            except Exception as e:
                logger.error(f"Exception at track {track_id}: {e}")
                return None, full_log

        return consolidated_results, full_log

    def _get_global_decision(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        summary = {
            "album_name": self.album_name,
            "steam_info": steam_info,
            "tracks_found": list(track_sources.keys())
        }
        
        prompt = f"""
Analyze the following album metadata sources and determine a consistent set of GLOBAL RULES for tagging.
Focus on resolving inconsistencies in Artist names, Album titles, and Genre across all sources.

### STRICT RULES:
1. NO GUESSING: If information is missing, leave it as "Unknown".
2. ABSOLUTE TRUTH: If MusicBrainz source name contains "(ultra_confirmed)", follow its structure.

### ALBUM SUMMARY:
{json.dumps(summary, indent=2, ensure_ascii=False)}

### TASK:
Return a JSON object with these fields:
- canonical_album_artist: Standardized Artist/Composer name.
- canonical_album_title: Exact album title to use for TALB.
- canonical_genre: Consolidated genre string.
- total_discs: Total number of discs identified.
- tagging_notes: Any specific naming conventions to follow for tracks.
- conflict_report: If high-conflict metadata is found, summarize it here.
"""
        messages = [{"role": "user", "content": prompt}]
        
        if not self.limiter.acquire(messages):
            return None

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            response = requests.post(self.api_url, json={"model": self.model, "messages": messages, "temperature": 0.0}, headers=headers, timeout=90)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                json_str = content
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"Global decision failed: {e}")
        return None
