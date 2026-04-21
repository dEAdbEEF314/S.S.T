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
    Currently using a local JSON file to track usage to bypass S3 signature issues.
    """
    def __init__(self, rpm: int, tpm: int, rpd: int):
        self.limit_rpm = rpm
        # Apply a 10% safety buffer to TPM to avoid exceeding limits due to estimation errors
        self.limit_tpm = int(tpm * 0.9)
        self.limit_rpd = rpd
        self.lock = threading.Lock()
        self.request_times = collections.deque()
        self.token_times = collections.deque() # list of (timestamp, tokens)
        
    def _get_daily_key(self):
        return f"llm_usage_{datetime.utcnow().strftime('%Y%m%d')}.json"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Conservatively estimate tokens. Using 1 token per 3 chars for safety."""
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
                # Clear expired windows (60s)
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                # Check RPM
                if len(self.request_times) >= self.limit_rpm:
                    wait = self.request_times[0] + 62.0 - now # Use 62s for extra safety
                    logger.info(f"Rate Limit: RPM reached. Waiting {wait:.1f}s")
                # Check TPM with the 90% threshold
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    if self.token_times:
                        wait = self.token_times[0][0] + 62.0 - now
                        logger.info(f"Rate Limit: TPM reached (Current sum + est: {sum(t[1] for t in self.token_times) + tokens}). Waiting {wait:.1f}s")
                    else:
                        logger.warning(f"Request estimation ({tokens}) exceeds TPM limit ({self.limit_tpm}). Proceeding anyway but expect 429.")
                        return True
                else:
                    remote_count = self._get_usage()
                    if remote_count >= self.limit_rpd:
                        logger.error(f"Rate Limit: RPD reached ({remote_count}).")
                        return False
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    self._increment_usage(remote_count)
                    return True
            time.sleep(max(0.2, wait))

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, storage: Any, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 30, tpm: int = 15000, rpd: int = 14400):
        if not base_url.endswith("/chat/completions"):
            self.api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            self.api_url = base_url
            
        self.api_key = api_key
        self.model = model
        self.storage = storage
        self.app_id = None
        self.album_name = None
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def set_context(self, app_id: int, album_name: str):
        self.app_id = app_id
        self.album_name = album_name

    def consolidate_metadata(self, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        instructions = """
You are a Factual Metadata Organizer for a game soundtrack tagging system.
Your goal is to consolidate multiple metadata sources into a single, accurate, and consistent JSON structure.

### STRICT RULES:
1. ABSOLUTE PROHIBITION ON HALLUCINATION: Do not invent track names, artists, or dates. If a piece of information is missing across ALL sources, leave it blank or use "Unknown".
2. NO INFERENCE: Do not guess based on your training data. Use ONLY the provided source data.
3. CONFLICT RESOLUTION: If sources conflict, prioritize accuracy. MusicBrainz is generally authoritative for tracklists, but Steam is authoritative for Publisher/Developer.
4. LANGUAGE PRIORITY: If multiple languages exist, select in this order: User's Configured Language > English > Original Language.
5. FORMATTING: Return ONLY a valid JSON object.

### TARGET MAPPING (JSON per track):
Map the consolidated truth to these specific fields:
- TIT2: Original Track Title (most detailed).
- TPE1: Artist (Composer/Performer names).
- TALB: Album Name (exactly as provided in .acf source).
- TPE2: Album Artist (format: "[Developer] | [Publisher]").
- TCON: Genre (format: "STEAM VGM, [Original Game Genre]").
- TIT1: Grouping (format: "[Series or Game Title] | Steam").
- COMM: Comment (format: "[Game Title] | [Steam Tags] | [AppID] | [URL]").
- TCOM: Composer (Individual/Unit names).
- TDRC: Year (YYYY).
- TRCK: Track Number.
- TPOS: Disc Number (format: "Disc/Total", e.g., "1/1").
- TLAN: Language Code.
- source: A string describing the origin of this track's metadata (e.g., "LLM Consolidated", "MusicBrainz Match", "Embedded Tag Fallback").
"""
        global_context = {
            "app_id": self.app_id,
            "album_name": self.album_name,
            "steam_metadata": steam_info,
            "total_tracks": len(track_sources)
        }

        messages = [
            {"role": "user", "content": f"{instructions}\n\nHere is the global context for the album: {json.dumps(global_context, indent=2, ensure_ascii=False)}\n\nI will now provide track data one by one. Please respond with a single JSON object for the track provided."}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        full_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": self.model,
            "app_id": self.app_id,
            "album_name": self.album_name,
            "session": []
        }

        consolidated_results = {}
        
        # Max history of tracks to keep (to stay under TPM)
        # Each track is ~2 messages (user + assistant)
        MAX_TRACK_HISTORY = 3 
        track_history = []

        for track_id, sources in track_sources.items():
            # Build current message set: instructions + history + current track
            current_messages = [messages[0]] # System instructions & Global context
            for h in track_history[-(MAX_TRACK_HISTORY * 2):]:
                current_messages.append(h)
            
            track_prompt = f"Consolidate metadata for Track ID: {track_id}\nSources: {json.dumps(sources, indent=2, ensure_ascii=False)}"
            current_messages.append({"role": "user", "content": track_prompt})

            logger.info(f"Processing track {track_id} for {self.album_name} (History: {len(track_history)//2} tracks)...")
            
            if not self.limiter.acquire(current_messages):
                return None, {"error": "Rate limit reached during track processing", "log": full_log}

            payload = {
                "model": self.model,
                "messages": current_messages,
                "temperature": 0.0,
            }

            try:
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=90)
                
                if response.status_code != 200:
                    error_msg = f"ERROR {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    full_log["session"].append({"track_id": track_id, "error": error_msg})
                    return None, full_log
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # Record full interaction in log
                full_log["session"].append({
                    "track_id": track_id,
                    "prompt": track_prompt,
                    "response": content
                })

                # Add current exchange to history for next tracks
                track_history.append({"role": "user", "content": track_prompt})
                track_history.append({"role": "assistant", "content": content})
                
                json_str = content
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                
                track_json = json.loads(json_str)
                consolidated_results[track_id] = track_json

            except Exception as e:
                logger.error(f"Exception during track {track_id} consolidation: {e}")
                full_log["session"].append({"track_id": track_id, "exception": str(e)})
                return None, full_log

        return consolidated_results, full_log
