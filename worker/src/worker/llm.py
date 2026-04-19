import os
import json
import logging
import requests
import time
import collections
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("worker.llm")

class DistributedRateLimiter:
    """
    Handles RPM, TPM (local) and RPD (distributed via S3).
    """
    def __init__(self, storage: Any, rpm: int, tpm: int, rpd: int):
        self.storage = storage
        self.limit_rpm = rpm
        self.limit_tpm = tpm
        self.limit_rpd = rpd
        self.lock = threading.Lock()
        self.request_times = collections.deque()
        self.token_times = collections.deque() # list of (timestamp, tokens)
        
    def _get_daily_key(self):
        return f"system/llm_usage_{datetime.utcnow().strftime('%Y%m%d')}.json"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, total_chars // 4)

    def _get_remote_usage(self) -> int:
        try:
            data = self.storage.download_json(self._get_daily_key())
            return data.get("requests", 0) if data else 0
        except Exception:
            return 0

    def _increment_remote_usage(self, current: int):
        try:
            self.storage.upload_json(
                {"requests": current + 1, "last_update": datetime.utcnow().isoformat()},
                self._get_daily_key()
            )
        except Exception as e:
            logger.warning(f"Failed to sync RPD to storage: {e}")

    def acquire(self, messages: List[Dict[str, str]]) -> bool:
        tokens = self._estimate_tokens(messages)
        
        while True:
            with self.lock:
                now = time.time()
                
                # 1. Clear expired windows (60s)
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                # 2. Check RPM
                if len(self.request_times) >= self.limit_rpm:
                    wait = self.request_times[0] + 60.1 - now
                    logger.info(f"Rate Limit: RPM reached. Waiting {wait:.1f}s")
                # 3. Check TPM
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    wait = self.token_times[0][0] + 60.1 - now
                    logger.info(f"Rate Limit: TPM reached. Waiting {wait:.1f}s")
                else:
                    # 4. Check RPD (Distributed)
                    remote_count = self._get_remote_usage()
                    if remote_count >= self.limit_rpd:
                        logger.error(f"Rate Limit: RPD reached ({remote_count}/{self.limit_rpd}). Blocking.")
                        return False
                    
                    # Passed all checks
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    self._increment_remote_usage(remote_count)
                    return True
            
            time.sleep(max(0.1, wait))

class LLMService:
    """Handles communication with OpenAI-compatible APIs with strict rate limiting."""
    
    def __init__(self, config: dict, storage: Any):
        self.api_url = config.get("LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = config.get("LLM_API_KEY", "ollama")
        self.model = config.get("LLM_MODEL", "llama3.1")
        self.storage = storage
        self.app_id = None
        self.album_name = None
        
        # Rate Limiting configuration
        rpm = int(config.get("GEMINI_LIMIT_RPM", 30))
        tpm = int(config.get("GEMINI_LIMIT_TPM", 15000))
        rpd = int(config.get("GEMINI_LLM_LIMIT_RPD", 14400))
        self.limiter = DistributedRateLimiter(storage, rpm, tpm, rpd)

    def set_context(self, app_id: int, album_name: str):
        """Sets the current album context for logging."""
        self.app_id = app_id
        self.album_name = album_name

    def ask(self, task_type: str, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Sends a request to the LLM with rate limiting and logging.
        """
        if not self.limiter.acquire(messages):
            return None

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Retry loop for 429 or transient errors
        retries = 0
        max_retries = 3
        backoff = [10, 30, 60]

        while retries <= max_retries:
            try:
                logger.debug(f"Sending LLM request for {task_type} (Attempt {retries+1})...")
                response = requests.post(f"{self.api_url}/chat/completions", json=payload, headers=headers, timeout=60)
                
                if response.status_code == 429:
                    wait = backoff[min(retries, len(backoff)-1)]
                    logger.warning(f"LLM 429 Too Many Requests. Backing off {wait}s...")
                    time.sleep(wait)
                    retries += 1
                    continue

                if response.status_code != 200:
                    logger.error(f"LLM request failed: {response.status_code} - {response.text}")
                    return None
                
                result = response.json()
                answer = result["choices"][0]["message"]["content"]
                
                # Log to S3
                self._log_interaction(task_type, messages, answer)
                return answer

            except Exception as e:
                logger.error(f"Exception during LLM request: {e}")
                if retries < max_retries:
                    time.sleep(5)
                    retries += 1
                    continue
                return None
        
        return None

    def _log_interaction(self, task_type: str, messages: List[Dict[str, str]], answer: str):
        if not self.app_id:
            return
            
        log_data = {
            "app_id": self.app_id,
            "album_name": self.album_name,
            "task_type": task_type,
            "messages": messages + [{"role": "assistant", "content": answer}],
            "model": self.model,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            log_key = f"logs/llm/{self.app_id}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{task_type}.json"
            self.storage.upload_json(log_data, log_key)
            logger.info(f"LLM log uploaded to S3: {log_key}")
        except Exception as e:
            logger.warning(f"Failed to upload LLM log: {e}")
