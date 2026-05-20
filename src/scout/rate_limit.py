import time
import collections
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger("scout.rate_limit")

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
                    return True
            time.sleep(max(0.1, wait))
