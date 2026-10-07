import random
import time
from typing import Optional


class LLMRetryPolicy:
    def __init__(
        self,
        max_retries: int,
        retry_delay: float,
        retry_backoff: float,
        adaptive_degraded_prompt_enabled: bool,
        llm_backend: str,
        max_output_tokens: int,
    ):
        self.max_retries = max(0, max_retries)
        self.retry_delay = float(retry_delay)
        self.retry_backoff = float(retry_backoff)
        self.adaptive_degraded_prompt_enabled = adaptive_degraded_prompt_enabled
        self.llm_backend = llm_backend.upper()
        self.max_output_tokens = max_output_tokens

    def can_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries

    def should_degrade_for_http(self, status_code: int, is_degraded_active: bool) -> bool:
        return (
            self.adaptive_degraded_prompt_enabled
            and not is_degraded_active
            and status_code in (408, 500, 502, 503, 504)
        )

    def should_degrade_for_exception(self, error: Exception, is_degraded_active: bool) -> bool:
        error_text = str(error).lower()
        return (
            self.adaptive_degraded_prompt_enabled
            and not is_degraded_active
            and any(token in error_text for token in ("timeout", "timed out", "json", "408"))
        )

    def should_degrade_for_truncation(self, is_degraded_active: bool) -> bool:
        return self.adaptive_degraded_prompt_enabled and not is_degraded_active

    def next_output_tokens(self, current_tokens: int) -> Optional[int]:
        if self.llm_backend != "OLLAMA":
            return None
        next_tokens = min(current_tokens * 2, self.max_output_tokens)
        return next_tokens if next_tokens > current_tokens else None

    def wait_before_retry(self) -> None:
        jitter = random.uniform(0.8, 1.2)
        time.sleep(self.retry_delay * jitter)
        self.retry_delay *= self.retry_backoff